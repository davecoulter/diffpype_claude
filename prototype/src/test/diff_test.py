import os, shutil, glob, sys
import pprint
import time
import pdb
from renameFITS import generate_filename, get_id_if_exists
from astropy.io import fits
from astropy.table import Table, vstack
import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as u
import space_phot
import subprocess

from configparser import RawConfigParser


def copy_out_fits(input_file_path, output_dir, clobber=False):
    # Process science file:
    # 1. Give it new naming convention
    # 2. Copy out the Science and Error extensions into separate files
    # 3. Add 50x the median noise value as a pedastal to the science data
    # 4. RETURNS: (sci_dest_path, err_dest_path, max_sci_value)

    index_of_field_name = 1
    if "60mas" in input_file_path:
        index_of_field_name = 2

    outfile = generate_filename(input_file_path, index_of_field_name)

    tokens = outfile.split(".")
    field_name = tokens[0]
    filter_name = tokens[1]
    ut_date = tokens[2]
    file_id = tokens[3]

    destination_id = get_id_if_exists(output_dir, outfile)

    if file_id != destination_id:
        outfile = "{field_name}.{filter_name}.{ut_date}.{file_id}.fits".format(
            field_name=field_name, filter_name=filter_name, ut_date=ut_date, file_id=destination_id)

    sci_dest_path = os.path.join(output_dir, outfile)
    err_dest_path = sci_dest_path.replace(".fits", ".noise.fits")
    max_val_sci_im = -9999

    # check existence
    if (not clobber and os.path.exists(sci_dest_path)) or (not clobber and os.path.exists(err_dest_path)):
        print("\n****** Stop! Files `%s` and `%s` exist! Re-run with clobber=True. Returning existing files. ******" % (
        sci_dest_path, err_dest_path))

        sci_obs3 = space_phot.observation3(sci_dest_path)
        max_val_sci_im = np.max(sci_obs3.data)
        return sci_dest_path, err_dest_path, max_val_sci_im

    # copy the original file to the temp location with the descriptive name
    t1_move = time.time()
    try:

        print("\tCopying `%s` to `%s`..." % (input_file_path, sci_dest_path))

        # Copy out the science data
        dat = fits.open(input_file_path, output_verify='fix')

        sci_data = dat['SCI', 1].data
        err_data = dat['ERR', 1].data
        err_median = np.median(err_data)
        sci_pedastal = 50.0 * err_median
        print("\n\tMedian error value: `%0.4f`; Pedastal to add to Sci Im: `%0.4f`" % (err_median, sci_pedastal))

        dat[0].data = sci_data + sci_pedastal
        max_val_sci_im = np.max(dat[0].data)

        dat[0].header = dat[0].header + dat[1].header
        dat[0].writeto(sci_dest_path, overwrite=clobber)

        # Copy out the err information, keep the main headers
        dat[0].data = err_data
        dat[0].writeto(err_dest_path, overwrite=clobber)

    except:
        print('\t***** Could not copy {} to the working directory! *****'.format(sci_dest_path))

    t2_move = time.time()
    print("\t\t\t...Done [%0.2f] seconds" % (t2_move - t1_move))

    return sci_dest_path, err_dest_path, max_val_sci_im


def create_pixregionfile(x, y, regionname, color, coords='image', radius=1):
    if isinstance(radius, int):
        radius = [radius] * len(x)
    with open(regionname, 'w') as f:
        if isinstance(color, str):
            f.write(
                'global color={0} dashlist=8 3 width=2 font=\"helvetica 10 normal roman\" select=1 highlite=1 dash=0 fixed=0 edit=1 move=1 delete=1 include=1 source=1 \n'.format(
                    color))
            do_col = False
        else:
            do_col = True
            f.write(
                'global dashlist=8 3 width=2 font=\"helvetica 10 normal roman\" select=1 highlite=1 dash=0 fixed=0 edit=1 move=1 delete=1 include=1 source=1 \n')
        f.write('%s \n' % coords)
        for star in range(len(x)):
            xval = x[star]
            yval = y[star]
            if do_col:
                f.write('circle({ra},{dec},{radius}") # color={color}\n'.format(ra=xval, dec=yval, radius=radius[star],
                                                                                color=color[star]))
            else:
                f.write('circle({ra},{dec},{radius}")\n'.format(ra=xval, dec=yval, radius=radius[star]))

    #     return (ra_wcs,dec_wcs,flux)
    f.close()


if __name__ == "__main__":

    configFile = './Settings.ini'
    config = RawConfigParser()

    config.read(configFile)
    app_settings = config["diff_test"]




    filters = {}
    filters['NIRCAM'] = {'F070W': 0.987, 'F090W': 1.103, 'F115W': 1.298, 'F140M': 1.553, 'F150W2': 1.628,
                         'F150W': 1.770,
                         'F162M': 1.801, 'F164N': 1.494, 'F182M': 1.990, 'F187N': 2.060, 'F200W': 2.141, 'F210M': 2.304,
                         'F212N': 2.341, 'F250M': 1.340, 'F277W': 1.444, 'F300M': 1.585, 'F322W2': 1.547,
                         'F323N': 1.711,
                         'F335M': 1.760, 'F356W': 1.830, 'F360M': 1.901, 'F405N': 2.165, 'F410M': 2.179, 'F430M': 2.300,
                         'F444W': 2.302, 'F460M': 2.459, 'F466N': 2.507, 'F470N': 2.535, 'F480M': 2.574}
    filters['NIRISS'] = {'F090W': 1.40, 'F115W': 1.40, 'F140M': 1.50, 'F150W': 1.50, 'F158M': 1.50, 'F200W': 1.50,
                         'F277W': 1.50, 'F356W': 1.60, 'F380M': 1.70, 'F430M': 1.80, 'F444W': 1.80, 'F480M': 1.80}
    filters['MIRI'] = {'F560W': 1.636, 'F770W': 2.187, 'F1000W': 2.888, 'F1130W': 3.318, 'F1280W': 3.713,
                       'F1500W': 4.354, 'F1800W': 5.224, 'F2100W': 5.989, 'F2550W': 7.312}
    filters['WFC3'] = {'F105W': 1.001, 'F110W': 1.019, 'F125W': 1.053, 'F140W': 1.100, 'F160W': 1.176}
    filters['ACS'] = {'F814W': 1.0}

    field_name = "p11"


    source_dir = "%s" %  app_settings["IN_DIR"]
    output_dir = "%s" % app_settings["OUT_DIR"]
    src_cat = "%s/primer-cosmos-grizli-v0.3.fits" % source_dir

    sci_file = "psub_60mas_p11_f277w_epoch3_v2_i2d.fits.gz"
    sci_src_path = "{source_dir}/{sci_file}".format(source_dir=source_dir, sci_file=sci_file)
    sci_dest_path, sci_err_dest_path, max_val_sci_im = copy_out_fits(sci_src_path, output_dir, clobber=True)

    temp_file = "psub_60mas_p11_f277w_epoch2_v2_i2d.fits.gz"
    temp_src_path = "{source_dir}/{temp_file}".format(source_dir=source_dir, temp_file=temp_file)
    temp_dest_path, temp_err_dest_path, max_val_temp_im = copy_out_fits(temp_src_path, output_dir, clobber=True)

    # Construct paths
    diff_file = os.path.basename(sci_dest_path).replace('.fits', "_") + os.path.basename(temp_dest_path).replace(
        '.fits', '.diff.fits')
    diff_path = "{output_dir}/{diff_file}".format(output_dir=output_dir, diff_file=diff_file)

    sci_mask_path = sci_dest_path.replace('.fits', '.mask.fits')
    temp_mask_path = temp_dest_path.replace('.fits', '.mask.fits')

    diff_mask_path = diff_path.replace('.fits', '.mask.fits')
    diff_noise_path = diff_path.replace('.fits', '.noise.fits')
    diff_kernel_path = diff_path.replace('.fits', '.kernel.fits')

    sci_stampxy_path = sci_dest_path.replace('.fits', '.stampxy.txt')
    diff_stampxy_reg_path = diff_path.replace('.fits', '.stampxy.reg')

    # 1. Make sure brightness sort order is correct
    # 2. Does it kick out the bright stuff because it can't find the kernel?
    #   overplot the first 50 objects
    #   try omitting the last faintest amount
    #   compare the KRON vs aperture fluxes
    #

    # Check if files already exist, and if so, bail out
    # TODO: implement a Clobber flag
    if not os.path.exists(sci_stampxy_path):
        cat_filt_keys = {
            "f115w": "FLUX_KRON_F115W",
            "f150w": "FLUX_KRON_F150W",
            "f277w": "FLUX_KRON_F277W",
            "f444w": "FLUX_KRON_F444W"
        }
        # Construct the diff im substamp catalog
        dat = Table.read(src_cat, format='fits')
        ras = dat["RA"]
        decs = dat["DEC"]
        fluxes = dat[cat_filt_keys["f277w"]]

        indices = (-fluxes).argsort()

        sorted_ra = ras[indices]
        sorted_dec = decs[indices]
        sorted_fluxes = fluxes[indices]

        bright_ind = np.where(sorted_fluxes > 0.0)[0]

        bright_ra = sorted_ra[bright_ind]
        bright_dec = sorted_dec[bright_ind]
        bright_flux = sorted_fluxes[bright_ind]

        # coords = SkyCoord(sorted_ra, sorted_dec, unit=(u.deg, u.deg))
        coords = SkyCoord(bright_ra, bright_dec, unit=(u.deg, u.deg))

        sci_obs3 = space_phot.observation3(sci_dest_path)
        temp_obs3 = space_phot.observation3(temp_dest_path)
        y_max, x_max = sci_obs3.data.shape

        xs, ys = sci_obs3.wcs.world_to_pixel(coords)
        in_img_indices = np.where((xs >= 0) & (xs <= x_max) & (ys >= 0) & (ys <= y_max))[0]

        # output_tbl = Table(
        #     [xs[in_img_indices],
        #     ys[in_img_indices],
        #     sorted_ra[in_img_indices],
        #     sorted_dec[in_img_indices],
        #     sorted_fluxes[in_img_indices]], names=["X", "Y", "RA", "DEC", cat_filt_keys["f277w"]])
        output_tbl = Table(
            [xs[in_img_indices],
             ys[in_img_indices],
             bright_ra[in_img_indices],
             bright_dec[in_img_indices],
             bright_flux[in_img_indices]], names=["X", "Y", "RA", "DEC", cat_filt_keys["f277w"]])

        output_tbl.write(sci_stampxy_path, format="ascii", overwrite=True)
        create_pixregionfile(xs[in_img_indices], ys[in_img_indices], "%s/p11_full_cat.reg" % output_dir, color="red",
                             coords="image", radius=[0.4] * len(ys[in_img_indices]))
    # pdb.set_trace()

    # Create Science and Template Masks
    with fits.open(sci_err_dest_path, output_verify='fix') as dat:

        sci_mask = np.zeros_like(dat[0].data)
        sci_mask[dat[0].data == 0] = 0x80
        sci_mask[np.isnan(dat[0].data)] = 0x80

        dat[0].data = sci_mask
        dat[0].scale('int16')
        dat.writeto(sci_mask_path, overwrite=True)

    with fits.open(temp_err_dest_path, output_verify='fix') as dat:

        temp_mask = np.zeros_like(dat[0].data)
        temp_mask[dat[0].data == 0] = 0x80
        temp_mask[np.isnan(dat[0].data)] = 0x80

        dat[0].data = temp_mask
        dat[0].scale('int16')
        dat[0].writeto(temp_mask_path, overwrite=True)

    print("world2")

    # Get filter and instrument
    sci_filt = ""
    sci_instrument = ""
    with fits.open(sci_dest_path) as sci_in:
        sci_filt = sci_in[0].header['FILTER']
        sci_instrument = sci_in[0].header['INSTRUME']

    # If filter and instrument combo are not found, default to FWHM = 1.8 pixels
    sci_fwhm = 1.8
    if sci_instrument in filters:
        if sci_filt in filters[sci_instrument]:
            sci_fwhm = filters[sci_instrument][sci_filt]
    else:
        print(f'{sci_instrument} not found in {list(filters.keys())}, FWHM fixed to 1.8 pixels.')

    temp_filt = ""
    temp_instrument = ""
    with fits.open(temp_dest_path) as temp_in:
        temp_filt = temp_in[0].header['FILTER']
        temp_instrument = temp_in[0].header['INSTRUME']

    # If filter and instrument combo are not found, default to FWHM = 1.8 pixels
    temp_fwhm = 1.8
    if temp_instrument in filters:
        if temp_filt in filters[temp_instrument]:
            temp_fwhm = filters[temp_instrument][temp_filt]
    else:
        print(f'{temp_instrument} not found in {list(filters.keys())}, FWHM fixed to 1.8 pixels.')

    # hotpants args
    ko = 2  # spatial order of kernel variation within region (2)
    bgo = 2  # spatial order of background variation within region (1)
    ssig = 3.0  # threshold for sigma clipping statistics  (3.0)

    ks = 2.0  # high sigma rejection for bad stamps in kernel fit (2.0)
    r = 2.5 * sci_fwhm  # FWHM * 2.5         # convolution kernel half width (10)
    kfm = 0.99  # fraction of abs(kernel) sum for ok pixel (0.990)

    il = 0  # lower valid data count, image (0)
    iu = max_val_sci_im  # dynamically take the highest in the science img        # upper valid data count, image (25000)
    iuk = iu  # set to 'iu' for now     # upper valid data count for kernel, image (iuthresh)

    tl = 0  # lower valid data count, template (0)
    tu = max_val_temp_im  # upper valid data count, template (25000)
    tuk = tu  # upper valid data count for kernel, template (tuthresh)

    nrx = 1  # number of image regions in x dimension (1)
    nry = 1  # number of image regions in y dimension (1)

    nsx = 70  # number of each region's stamps in x dimension (10)
    nsy = 90  # number of each region's stamps in y dimension (10)
    nss = 7  # number of centroids to use for each stamp (3) # DC: got a segmentation fault using "10"

    # ngauss degree0 sigma0 .. degreeN sigmaN]
    # : ngauss = number of gaussians which compose kernel (3)
    # : degree = degree of polynomial associated with gaussian #
    #            (6 4 2)
    # : sigma  = width of gaussian #
    #            (0.70 1.50 3.00)
    # : N = 0 .. ngauss - 1

    # : (3 6 0.70 4 1.50 2 3.00
    ng = (3, 6, sci_fwhm / 2.0, 4, sci_fwhm, 2, sci_fwhm * 2.0)

    rss = 2.5 * sci_fwhm  # 2.5 * FWHM scaled by the fwhm - radius of the substamp # half width substamp to extract around each centroid (15)
    ft = 5.0  # RMS threshold for good centroid in kernel fit (20.0)

    # -okn          # rescale noise for 'ok' pixels (0)
    c = "t"  # force convolution on (t)emplate or (i)mage (undef)
    n = "i"  # normalize to (t)emplate, (i)mage, or (u)nconvolved (t)
    # -sconv        # all regions convolved in same direction (0)

    afssc = 0  # autofind stamp centers so #=-nss when -ssf,-cmp (1)
    gridssc = 0

    fi = 0.0  # value for invalid (bad) pixels (1.0e-30)
    fin = 0.0  # noise image only fillvalue (0.0e+00)

    mins = 2.0  # Fraction of kernel half width to spread input mask (1.0)
    mous = 0.0  # Ditto output mask, negative = no diffim masking (1.0)

    v = 2  # level of verbosity, 0-2 (1)
    # -savexy = set file name . saves the X,Y positions of used, clipped, and all substamps in different colors
    # save as a reg file

    hotpants_arg = 'hotpants -inim {sci_file} -tmplim {temp_file} -outim {diff_file} -ini {sci_noise_im} \
                   -imi {sci_mask} -il {il} -iu {iu} -iuk {iuk} -tni {temp_noise_im} -tmi {temp_mask} \
                   -tl {tl} -tu {tu} -tuk {tuk} -nrx {nrx} -nry {nry} -nsx {nsx} -nsy {nsy} -nss {nss} -ng {ng_tuple} \
                   -rss {rss} -ft {ft} -r {r} -ko {ko} -bgo {bgo} -ssig {ssig} -ks {ks} -kfm {kfm} -okn -c {c} -n {n} -sconv \
                   -cmp {diff_substamps} -afssc {afssc} -gridssc {gridssc} -fi {fi} \
                   -oni {diff_noise_im}  -fin {fin} -mins {mins} \
                   -omi {diff_mask} -mous {mous} -oki {diff_kernel} -v {v} -savexy {savexy}'.format(
        sci_file=sci_dest_path, temp_file=temp_dest_path, diff_file=diff_path,
        sci_noise_im=sci_err_dest_path, sci_mask=sci_mask_path, il=il, iu=iu, iuk=iuk, temp_noise_im=temp_err_dest_path,
        temp_mask=temp_mask_path, tl=tl, tu=tu, tuk=tuk, nrx=nrx, nry=nry, nsx=nsx, nsy=nsy, nss=nss,
        ng_tuple=" ".join([str(_ng) for _ng in ng]),
        rss=rss, ft=ft, r=r, ko=ko, bgo=bgo, ssig=ssig, ks=ks, kfm=kfm, c=c, n=n, diff_substamps=sci_stampxy_path,
        afssc=afssc, gridssc=gridssc, fi=fi, diff_noise_im=diff_noise_path, fin=fin,
        mins=mins, diff_mask=diff_mask_path, mous=mous, diff_kernel=diff_kernel_path, v=v, savexy=diff_stampxy_reg_path)

    print("Hotpants invocation:\n\t%s" % hotpants_arg)
    process = subprocess.Popen(hotpants_arg, shell=True)

    try:
        process.wait(timeout=600)
    except subprocess.TimeoutExpired:
        process.kill()
        print('HOTPANTS execution timeout.')
        pass

'''
    Image 
    Noise im
        use the ERR image for this

    Mask

        0x01 = bad pixel
        0x02 = saturation
        0x04 = spikes


        0x80 = set if you want to ignore a pixel


        Unsigned int array
        the hex code should be added - 0x80 (for NaN and counts < 0 in the sci)

        * look at saturated star and pixels
            * what are the bad pixels? how to identify


    Look at the error image. Say that the err image is "10"
        -> uncertainty is 10 counts
        -> look at the real image in that region - it the std dev should match the this
'''
# hotpants
#

# NOISE IMAGES
#


# need
# -fin -fi -> set them to zero
# -rss choose this to have some realestate based on the FWHM (and bounded by a min/max)

# -r is the radius for the kernemt


# DIFFIM Parameters
#
# use 1x1 for region
# x = 70 y = 40 stamps for 2k x 4k
#   how many substamps per the above scaling, is like 7 substamps
#
#
# if one side is 2x longer than the other side, use 2x more stamps on that side. Check dimensions of images.
#   stamp has to be substantially bigger than the substamp
#       substamp has to be substantially bigger than the kernel
#
#   you want at least 3 substamps per stamp
#   max of 7 substamps (maybe go higher)
#


#





