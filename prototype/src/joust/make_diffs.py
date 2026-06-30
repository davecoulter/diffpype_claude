import os
import numpy as np
import json
import subprocess
import os, shutil, glob, sys
from reproject import *
from astropy.io import fits
from astropy.table import Table, vstack
import time
from astropy.coordinates import SkyCoord
import astropy.units as u
import space_phot
import pprint
import copy

# Dave Debug
import pdb

import warnings

warnings.simplefilter('ignore')

import jhat
from jhat import jwst_photclass, hst_photclass, st_wcs_align

from utils import get_config, Logging

# List of filters and their corresponding FWHM in arcsec (from Justin's script)
filters = {}
filters['NIRCAM'] = {'F070W': 0.987, 'F090W': 1.103, 'F115W': 1.298, 'F140M': 1.553, 'F150W2': 1.628, 'F150W': 1.770,
                     'F162M': 1.801, 'F164N': 1.494, 'F182M': 1.990, 'F187N': 2.060, 'F200W': 2.141, 'F210M': 2.304,
                     'F212N': 2.341, 'F250M': 1.340, 'F277W': 1.444, 'F300M': 1.585, 'F322W2': 1.547, 'F323N': 1.711,
                     'F335M': 1.760, 'F356W': 1.830, 'F360M': 1.901, 'F405N': 2.165, 'F410M': 2.179, 'F430M': 2.300,
                     'F444W': 2.302, 'F460M': 2.459, 'F466N': 2.507, 'F470N': 2.535, 'F480M': 2.574}
filters['NIRISS'] = {'F090W': 1.40, 'F115W': 1.40, 'F140M': 1.50, 'F150W': 1.50, 'F158M': 1.50, 'F200W': 1.50,
                     'F277W': 1.50, 'F356W': 1.60, 'F380M': 1.70, 'F430M': 1.80, 'F444W': 1.80, 'F480M': 1.80}
filters['MIRI'] = {'F560W': 1.636, 'F770W': 2.187, 'F1000W': 2.888, 'F1130W': 3.318, 'F1280W': 3.713,
                   'F1500W': 4.354, 'F1800W': 5.224, 'F2100W': 5.989, 'F2550W': 7.312}
filters['WFC3'] = {'F105W': 1.001, 'F110W': 1.019, 'F125W': 1.053, 'F140W': 1.100, 'F160W': 1.176}
filters['ACS'] = {'F814W': 1.0}


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


class ImageSub():

    def __init__(self):

        self.log = Logging()
        self.log.log_name = 'log.txt'

        # Load configuration file
        config = get_config()
        if config:
            self.config = config
        else:
            self.log.log('Could not open config.json. Quitting.')
            sys.exit()

        self.mask = None
        self.fwhm = 1.2
        self.hotpants_dir = self.config['hotpants_dir']
        # self.working_dir = os.getcwd() + '/joust_temp_dir/'

        # Dave hack
        self.perform_dir_ops = True
        self.save_to_output = True
        self.reproject_sci = True
        self.is_jades = False
        self.is_cosmos = False
        self.is_aaih = False
        self.is_jhat_generic = False
        self.jhat_file = None
        self.custom_mask = None

        return

    def process(self, sci_im, ref_im, level=3,
                run_jhat=True, run_reproject=True, save_intermediate_files=False,
                output_dir='joust_results/', save_to_output=True):

        # Dave hack
        if self.perform_dir_ops:
            print("performing directory ops")
            # Create a temporary directory for subtraction
            self.make_working_dir()

            # copy data to the temp directory
            self.copy_data_to_temp(sci_im, ref_im)
        else:
            print("Skipping directory ops")
            # Dave Hack:
            # This gets set in self.copy_data_to_temp()... I am side stepping that so need to set it here.
            self.sci_im = self.working_dir + os.path.basename(sci_im)
            self.ref_im = self.working_dir + os.path.basename(ref_im)

        # if data needs to be aligned, run jhat
        if run_jhat:
            self.sci_im, self.ref_im = self.align_wcs(level)
        else:
            print("Skipping jhat")

        # Reproject data images to match WCS
        if run_reproject:
            # self.sci_im, self.ref_im = self.reproject_images()
            self.sci_im, self.ref_im = self.reproject_images_dave()
        else:
            print("Skipping reproject")

        # Run HOTPANTS to complete subtraction
        if True:
            # print("Running hotpants with jhat")
            # self.run_hotpants(use_stampfile=True)
            print("Running Dave HOTPANTS")
            self.run_hotpants_dave()
        else:

            print('SKIPPING JHAT')
            # print("Running hotpants without jhat")
            # self.run_hotpants(use_stampfile=False)

            #

        # Make Results Directory
        if save_to_output:
            self.make_results_dir(output_dir, save_intermediate_files)

        return

    # Only works on a pair of files
    def copy_data_to_temp(self, sci_im_input, ref_im_input):

        # Set destination files
        sci_im_output = self.working_dir + os.path.basename(sci_im_input).replace('.gz', '')
        ref_im_output = self.working_dir + os.path.basename(ref_im_input).replace('.gz', '')

        sci_dat = fits.open(sci_im_input, output_verify='fix', disable_image_compression=True)
        sci_dat[:2].writeto(sci_im_output, overwrite=True)

        ref_dat = fits.open(ref_im_input, output_verify='fix', disable_image_compression=True)
        ref_dat[:2].writeto(ref_im_output, overwrite=True)

        self.sci_im = sci_im_output
        self.ref_im = ref_im_output

        return

    def make_results_dir(self, output_dir, save_intermediate_files):

        if not os.path.exists(output_dir):
            print("Making `%s`" % output_dir)
            os.mkdir(output_dir)

        if save_intermediate_files:
            print("Saving intermediate files...")
            all_files = glob.glob(self.working_dir + "*")
        else:
            all_files = glob.glob(self.working_dir + "difference.fits")

        for f in all_files:
            src = f
            dst = os.path.join(output_dir, os.path.basename(f))

            print("Saving `%s`..." % dst)

            try:
                shutil.copyfile(src, dst)
                print("\tSaving `%s`... done." % dst)
            except:
                self.log.log('Could not save {} to {}'.format(src, output_dir))

        return

    def make_working_dir(self):

        self.log.log('Creating temporary working directory')

        if os.path.exists(self.working_dir):
            try:
                flist = glob.glob(self.working_dir + '*')
                for f in flist:
                    os.remove(f)
            except:
                pass
        else:
            os.mkdir(self.working_dir)

        return

    def align_wcs(self, level=3, mode='jwst-jwst'):
        """
        Run jwst_wcs_align to correct the WCS of the curent images using the tweak_reg_hack. Attempts to align both
        to GaiaDR2 by default. If either fails, use the output of the photometry step as the reference catalog to align
        to.
        """

        # jhat requires the i2d or cal suffix to be present in the file name
        if mode == 'jwst-jwst':
            if level == 3:
                suffix1 = 'i2d'
                suffix2 = 'i2d'
            else:
                suffix1 = 'cal'
                suffix2 = 'cal'

        elif mode == 'jwst-hst':
            if level == 3:
                suffix1 = 'i2d'
                suffix2 = 'drz'
            else:
                suffix1 = 'cal'
                suffix2 = 'drz'
        else:
            if level == 3:
                suffix1 = 'drz'
                suffix2 = 'drz'
            else:
                suffix1 = 'drz'
                suffix2 = 'drz'

        if suffix1 not in self.sci_im:
            sci_image = self.sci_im.replace('.fits', '_{}.fits'.format(suffix1))
            os.rename(self.sci_im, sci_image)
        else:
            sci_image = self.sci_im

        if suffix2 not in self.ref_im:
            ref_image = self.ref_im.replace('.fits', '_{}.fits'.format(suffix2))
            os.rename(self.ref_im, ref_image)
        else:
            ref_image = self.ref_im

        FILT = fits.getheader(sci_image)['FILTER']
        INSTRUMENT = fits.getheader(sci_image)['INSTRUME']
        REF_TELESCOPE = fits.getheader(ref_image)['TELESCOP']
        fwhm = filters[INSTRUMENT][FILT]

        # tweakreg step
        if REF_TELESCOPE == 'JWST':
            phot = jwst_photclass()
        else:
            phot = hst_photclass()

        phot.run_phot(imagename=ref_image, photfilename='auto', SNR_min=3.0, overwrite=True)
        ref_catname = ref_image.replace('.fits', '.phot.txt')

        # try to align jw im to hst refcat
        self.log.log('Trying to align jwst to template refcat...')
        wcs_align = st_wcs_align()
        wcs_align.outdir = self.working_dir

        wcs_align.run_all(sci_image,
                          telescope='JWST',
                          outrootdir=os.path.dirname(self.working_dir),
                          outsubdir=os.path.basename(self.working_dir),
                          refcatname=ref_catname,
                          refcat_racol='ra',
                          refcat_deccol='dec',
                          refcat_magcol='mag',
                          refcat_magerrcol='dmag',
                          overwrite=True,
                          d2d_max=1,
                          Nfwhm=fwhm,
                          showplots=0,
                          histocut_order='dxdy',
                          sharpness_lim=(0.4, 0.9),
                          roundness1_lim=(-0.4, 0.4),
                          SNR_min=5,
                          dmag_max=1.0,
                          objmag_lim=(19, 26.5),
                          saveplots=False,
                          savephottable=True)

        return sci_image.replace(f'_{suffix1}.fits', '_jhat.fits'), ref_image

    def reproject_images_dave(self):
        print("Running reproject")
        """
        Takes newly aligned JWST images and reprojects them to a matching plane using the WCS.
        Generates a comparison image of the reprojected image before and after, and a comparison to the WCS matched
        image.
        """

        sci_im = self.sci_im
        ref_im = self.ref_im

        target_header = None
        target_reprojected = None

        if self.reproject_sci:

            with fits.open(ref_im) as hdu_ref:
                target_header = hdu_ref['SCI', 1].header

            target_reprojected = sci_im.replace('.fits', '_reprojected.fits')

            with fits.open(sci_im, 'update') as hdu_sci:
                array, _ = reproject_interp(hdu_sci['SCI', 1], target_header)
                repro_cutout = array.astype(np.float32)
                try:
                    hdu_sci['ERR', 1].header += hdu_sci['SCI', 1].header
                except:
                    hdu_sci.append(fits.ImageHDU(data=1. / np.sqrt(hdu_sci["WHT", 1].data),
                                                 header=hdu_sci["WHT", 1].header,
                                                 name="ERR"))
                    hdu_sci['ERR', 1].header += hdu_sci['SCI', 1].header

                err_array, _2 = reproject_interp(hdu_sci['ERR', 1], target_header)
                err_cutout = err_array.astype(np.float32)

                hdu_sci['SCI', 1].data = repro_cutout
                hdu_sci['SCI', 1].header = target_header

                hdu_sci['ERR', 1].data = err_cutout
                err_header = copy.deepcopy(target_header)
                err_header['EXTNAME'] = 'ERR'
                hdu_sci['ERR', 1].header = err_header

                # try:
                hdu_sci[0:3].writeto(target_reprojected, overwrite=True)
                # except:
                #    hdu_sci = hdu_sci[['PRIMARY','SCI','ERR']]
                #    hdu_sci.writeto(target_reprojected, overwrite=True)

                sci_im = target_reprojected
        else:

            with fits.open(sci_im) as hdu_sci:
                target_header = hdu_sci['SCI', 1].header

            target_reprojected = ref_im.replace('.fits', '_reprojected.fits')

            with fits.open(ref_im) as hdu_ref:
                array, _ = reproject_interp(hdu_ref['SCI', 1], target_header)
                repro_cutout = array.astype(np.float32)

                try:
                    hdu_ref['ERR', 1].header += hdu_ref['SCI', 1].header
                except:
                    hdu_ref.append(fits.ImageHDU(data=1. / np.sqrt(hdu_ref["WHT", 1].data),
                                                 header=hdu_ref["WHT", 1].header,
                                                 name="ERR"))
                    hdu_ref['ERR', 1].header += hdu_ref['SCI', 1].header

                err_array, _2 = reproject_interp(hdu_ref['ERR', 1], target_header)
                err_cutout = err_array.astype(np.float32)

                hdu_ref['SCI', 1].data = repro_cutout
                hdu_ref['SCI', 1].header = target_header

                hdu_ref['ERR', 1].data = err_array
                err_header = copy.deepcopy(target_header)
                err_header['EXTNAME'] = 'ERR'
                hdu_ref['ERR', 1].header = err_header
                hdu_ref[0:3].writeto(target_reprojected, overwrite=True)

                ref_im = target_reprojected

        return sci_im, ref_im

    # DC: Adding flag to set the projection order, and defaulting it to what this method originally did
    def reproject_images(self):
        print("Running reproject")
        """
        Takes newly aligned JWST images and reprojects them to a matching plane using the WCS.
        Generates a comparison image of the reprojected image before and after, and a comparison to the WCS matched
        image.
        """

        sci_im = self.sci_im
        ref_im = self.ref_im

        hdu_sci = None
        hdu_ref = None

        try:
            hdu_sci = fits.open(sci_im)
        except:
            self.log.log('Could not open {} for reprojection'.format(sci_im))
            print("Could not open `%s`" % sci_im)
            pass

        try:
            hdu_ref = fits.open(ref_im)
        except:
            self.log.log('Could not open {} for reprojection'.format(ref_im))
            print("Could not open `%s`" % ref_im)
            pass

        # reproject one of the images to the other
        array = None
        _ = None
        ref_im_new = None
        sci_im_new = None

        if self.reproject_sci:  # Original code path
            print("\tReprojecting science to template")
            # ref_im_new = ref_im.replace('.fits','_copy.fits')
            sci_im_new = sci_im.replace('.fits', '_reprojected.fits')

            array, _ = reproject_adaptive(hdu_sci['SCI', 1], hdu_ref[1].header)
            repro_cutout = array.astype(np.float32)

            # save orig data to a copy
            hdu_ref.writeto(ref_im_new, overwrite=True)

            # # Sanity -- check if this already exists
            # if os.path.exists(sci_im_new):
            #     print("Reprojected science already exists! Skipping...")
            #     hdu_sci.close()
            #     hdu_ref.close()
            # else:
            # save reprojected data
            hdu_sci['SCI', 1].data = repro_cutout
            hdu_sci['SCI', 1].header = hdu_ref[1].header
            hdu_sci.writeto(sci_im_new, overwrite=True)

            hdu_sci.close()
            hdu_ref.close()
        else:
            print("\tReprojecting template to science")
            sci_im_new = sci_im.replace('.fits', '_copy.fits')
            ref_im_new = ref_im.replace('.fits', '_reprojected.fits')

            array, _ = reproject_adaptive(hdu_ref['SCI', 1], hdu_sci[1].header)
            repro_cutout = array.astype(np.float32)

            # save orig data to a copy
            hdu_sci.writeto(sci_im_new, overwrite=True)

            # # Sanity -- check if this already exists
            # if os.path.exists(ref_im_new):
            #     print("Reprojected template already exists! Skipping...")
            #     hdu_sci.close()
            #     hdu_ref.close()
            # else:
            # save reprojected data
            hdu_ref['SCI', 1].data = repro_cutout
            hdu_ref['SCI', 1].header = hdu_sci[1].header
            hdu_ref.writeto(ref_im_new, overwrite=True)

            hdu_sci.close()
            hdu_ref.close()

        return sci_im_new, ref_im_new

    def run_hotpants(self, use_stampfile=True):
        t_start_run_hotpants = time.time()

        """
        Function used to run hotpants to convolve one image and subtract
        it from another. hotpants can be obtained from:
        https://github.com/acbecker/hotpants

        Parameters
        ----------
        use_stampfile : bool, default False
            Use a stampfile as opposed to a fixed number of stamps
            for hotpants.

        Returns
        -------
        Saves an output .fits image named:
        align_jwst_jwst/Difference_opposite2.fits
        """

        ##### Hotpants parameters FIXED RIGHT NOW, NEED TO OPTIMZE ######
        # Crop image edge
        edge_crop = 0
        # Image and template count limits
        inim_limit = 100
        tmplim_limit = 100
        # If use_stampfile == True, use this as the file name
        ssf_file = self.working_dir + 'ssf_coords.txt'
        # Number of substamps
        substamps = 3
        # Kernel and background order
        kernelorder = 2
        bgorder = 2

        stampxy = 'stampxy'

        # # Start Original
        # Filenames, GENERALIZE FORMAT, PICKING THESE SO IT WORKS WITH REST OF SCRIPT.
        # inim   = self.sci_im.replace('.fits','_1.fits')
        # tmplim = self.ref_im.replace('.fits','_1.fits')

        # outim  = self.working_dir + 'difference.fits'
        # inmask = self.working_dir + 'mask1_hdu.fits'
        # tpmask = self.working_dir + 'mask2_hdu.fits'

        # diffmask = self.working_dir + 'diff.mask_hdu.fits'
        # # End Original

        # DEBUG: Dave Trying another convention
        inim = self.sci_im.replace('.fits', '_1.fits')
        inmask = inim.replace('.fits', '.mask.fits')

        tmplim = self.ref_im.replace('.fits', '_1.fits')
        tpmask = tmplim.replace('.fits', '.mask.fits')

        outim = inim.replace('_1.fits', "_") + os.path.basename(tmplim).replace('.fits', '.diff.fits')
        diffmask = outim.replace('.fits', '.mask.fits')
        # END DEBUG

        # DEBUG: Start Dave New Naming Convention
        # inim   = self.sci_im.replace('.fits','_1.fits')
        # tmplim = self.ref_im.replace('.fits','_1.fits')

        # inim_file_tokens = os.path.basename(inim).split(".")
        # inim_field_name = inim_file_tokens[0]
        # inim_filt_name = inim_file_tokens[1]
        # inim_utdate = inim_file_tokens[2]
        # inim_id = inim_file_tokens[3]

        # tmplim_file_tokens = os.path.basename(tmplim).split(".")
        # tmplim_filt_name = inim_file_tokens[1]
        # tmplim_utdate = tmplim_file_tokens[2]
        # tmplim_id = tmplim_file_tokens[3]

        # outim = "{field_name}.{inim_filt_name}.{inim_utdate}.{inim_id}_{tmplim_filt_name}.{tmplim_utdate}.{tmplim_id}.diff".format(
        #     field_name=inim_field_name,
        #     inim_filt_name=inim_filt_name,
        #     inim_utdate=inim_utdate,
        #     inim_id=inim_id,
        #     tmplim_filt_name=tmplim_filt_name,
        #     tmplim_utdate=tmplim_utdate,
        #     tmplim_id=tmplim_id)

        # outim  = self.working_dir + outim + ".fits"
        # inmask = inim.replace(".fits", "") + '.mask.fits'
        # tpmask = tmplim.replace(".fits", "") +  '.mask.fits'
        # diffmask = outim.replace(".fits", "") +  '.mask.fits'
        # DEBUG: End Dave New Naming Convention

        print(
            "Files to be processed: \n\tSci File: %s\n\tTemp File: %s\n\tDiff File: %s\n\tIn Mask: %s\n\tTp Mask: %s" %
            (inim, tmplim, outim, inmask, tpmask))

        # Read in input image and template and save it again with data on 0th index
        print("Opening fits files...")
        t1_read = time.time()
        hdu1 = fits.open(self.sci_im)
        hdu2 = fits.open(self.ref_im)
        t2_read = time.time()
        print("\tOpening fits files... [%0.2f] seconds" % (t2_read - t1_read))

        # Replace 0th index with data on first index
        print("Header data copy...")
        t1_open = time.time()
        if hdu1[0].data is None:
            print("Copying data from 1st to 0th header in sci im")
            hdu1[0].data = hdu1[1].data
        if hdu2[0].data is None:
            print("Copying data from 1st to 0th header in ref im")
            hdu2[0].data = hdu2[1].data
        t2_open = time.time()
        print("\tOpening fits files... [%0.2f] seconds" % (t2_open - t1_open))

        # Create mask files
        print("Creating mask files...")
        t1_mask = time.time()
        hdu1_mask = np.zeros_like(hdu1[0].data)  # science
        hdu2_mask = np.zeros_like(hdu2[0].data)  # template
        hdu1_mask[hdu1[0].data <= 0] = 1  # 0x80
        hdu1_mask[np.isnan(hdu1[0].data)] = 1  # 0x80
        if self.custom_mask is not None:
            hdu1_mask[self.custom_mask == 1] = 1  # 0x80

        hdu2_mask[hdu2[0].data <= 0] = 1  # 0x80
        hdu2_mask[np.isnan(hdu2[0].data)] = 1  # 0x80
        if self.custom_mask is not None:
            hdu2_mask[self.custom_mask == 1] = 1  # 0x80

        # dat[0].data = temp_mask
        # dat[0].scale('int16')
        # hdu1_mask[hdu1[0].data <= 0] = 1
        # hdu1_mask[np.isnan(hdu1[0].data)] = 1

        # hdu2_mask[hdu2[0].data <= 0] = 1
        # hdu2_mask[np.isnan(hdu2[0].data)] = 1

        self.mask = hdu1_mask + hdu2_mask
        self.mask[self.mask >= 1] = 0x80

        t2_mask = time.time()
        print("\tCreating mask files... [%0.2f] seconds" % (t2_mask - t1_mask))

        # Add a pedestal to data if necessary
        print("Add pedastal and remove NaNs...")
        t1_nan = time.time()

        if np.nanmin(hdu1[0].data) <= 0:
            hdu1[0].data += np.abs(np.nanmin(hdu1[0].data)) + 1
        if np.nanmin(hdu2[0].data) <= 0:
            hdu2[0].data += np.abs(np.nanmin(hdu2[0].data)) + 1

        # Replace nan's with 1
        hdu1[0].data[np.isnan(hdu1[0].data)] = 1
        hdu2[0].data[np.isnan(hdu2[0].data)] = 1

        t2_nan = time.time()
        print("\tAdd pedastal and remove NaNs... [%0.2f] seconds" % (t2_nan - t1_nan))

        print("Combining headers and saving to HOTPANTS output...")
        t1_out = time.time()
        if len(hdu1) > 1:
            hdu1[0].header = hdu1[0].header + hdu1[1].header

        if len(hdu2) > 1:
            hdu2[0].header = hdu2[0].header + hdu2[1].header

        # Save the output
        hdu1.writeto(inim, overwrite=True)
        hdu2.writeto(tmplim, overwrite=True)

        # Open new files
        hdu1 = fits.open(inim)
        hdu2 = fits.open(tmplim)
        template_for_wcs = fits.open(tmplim)

        # write out correct masks
        hdu2[0].data = self.mask
        hdu2[0].scale('int16')
        hdu2.writeto(inmask, overwrite=True)

        # write out correct masks
        hdu2[0].data = self.mask
        hdu2[0].scale('int16')
        hdu2.writeto(tpmask, overwrite=True)

        # hdu2[0].data = hdu2_mask

        # hdu2.writeto(tpmask, overwrite=True)

        hdu2[0].data = self.mask
        hdu2[0].scale('int16')
        hdu2.writeto(diffmask, overwrite=True)

        # Add one for sci error and one for tmp error
        # 1. create the image from existing
        #   2. grab the err array and overwrite the data
        #   3, serialize to file

        # hdu2[0].data = self.mask
        # hdu2.writeto(diffmask, overwrite=True)

        t2_out = time.time()
        print("\tCombining headers and saving to HOTPANTS output... [%0.2f] seconds" % (t2_out - t1_out))

        # Gain/noise Parameters
        print("Gain/noise Parameters...")
        t1_gain = time.time()

        try:
            i_gain = float(fits.getval(inim, 'GAIN'))
        except:
            self.log.log('Assuming input gain = 1.0')
            i_gain = 1.0

        try:
            i_rdnoise = float(fits.getval(inim, 'RDNOISE'))
        except:
            self.log.log('Assuming input rdnoise = 1.0')
            i_rdnoise = 1.0

        try:
            t_gain = float(fits.getval(tmplim, 'GAIN'))
        except:
            self.log.log('Assuming template gain = 1.0')
            t_gain = 1.0

        try:
            t_rdnoise = float(fits.getval(tmplim, 'RDNOISE'))
        except:
            self.log.log('Assuming template rdnoise = 1.0')
            t_rdnoise = 1.0
        t2_gain = time.time()
        print("\tGain/noise Parameters... [%0.2f] seconds" % (t2_gain - t1_gain))

        # Get filter and instrument
        filtro = hdu1[0].header['FILTER']
        instrument = hdu1[0].header['INSTRUME']

        # If filter and instrument combo are not found, default to FWHM = 1.8 pixels
        if instrument not in list(filters.keys()):
            self.log.log(f'{instrument} not found in {list(filters.keys())}, FWHM fixed to 1.8 pixels.')
            self.fwhm = 1.8
            if filtro not in list(filters[instrument].keys()):
                self.log.log(f'{filtro} not found in {list(filters[instrument].keys())}, FWHM fixed to 1.8 pixels.')
                self.fwhm = 1.8
        else:
            self.fwhm = filters[instrument][filtro]

        # Find FWHM-dependent parameters
        data_shape = hdu1[0].data.shape
        y_size, x_size = hdu1[0].data.shape

        # Set subtamp size to 4 * fwhm
        nss = 18.0
        ks = 11.25
        ns_mult = nss / self.fwhm
        k_mult = ks / self.fwhm

        nsx = int(ns_mult * self.fwhm)
        nsy = int(ns_mult * self.fwhm)

        # Set kernel size to 2.5 * fwhm
        # kernel = 2.5 * fwhm
        kernel = k_mult * self.fwhm

        # Crop image
        xmin, xmax, ymin, ymax = edge_crop, x_size - edge_crop, edge_crop, y_size - edge_crop

        if use_stampfile:
            photf = self.working_dir + 'jwst_rep.goodmatches.phot.txt'

            # DC HACK: I need to actually pipe through a real naming convention fix instead of hard coding.
            # photf = self.working_dir + 'jw06549-o003_t001_nircam_clear-f150w.phot.txt'
            tab = Table.read(photf, format='ascii')

            # make cuts
            # ==================================
            df = tab.to_pandas()
            # sharp cut
            med = np.nanmedian(df.sharpness)
            std = np.nanstd(df.sharpness)
            shi = med + std
            slo = med - std
            df = df[df.sharpness > slo]
            df = df[df.sharpness < shi]

            # round cut
            med = np.nanmedian(df.roundness2)
            std = np.nanstd(df.roundness2)
            rhi = med + std
            rlo = med - std
            df = df[df.roundness2 > rlo]
            df = df[df.roundness2 < rhi]

            tab = Table.from_pandas(df)
            # ==================================

            for c in tab.colnames:
                if 'aper_sum_bkgsub' in c:
                    colname = c

            tab.sort(c)
            tab.reverse()
            tab = np.array(tab[['x', 'y']])
            np.savetxt(self.working_dir + 'ssf_coords.txt', tab, fmt='%10.5f')

        # -imi {sci_mask} -il {il} -iu {iu} -iuk {iuk} \
        #       -tni {temp_noise_im} \
        #       -tmi {temp_mask} \
        # Build hotpants command
        if use_stampfile:
            hotpants_arg = f'{self.hotpants_dir} -inim {inim} -tmplim {tmplim} -outim {outim} -n i -c t \
                             -iu {inim_limit} -tu {tmplim_limit} -ig {i_gain} -ir {i_rdnoise} -tg {t_gain} -tr {t_rdnoise} \
                             -ng 3 6 {self.fwhm / 2} 4 {self.fwhm} 2 {self.fwhm * 2} \
                             -cmp {ssf_file} -r {kernel} -nss {substamps} \
                             -ko {kernelorder} -bgo {bgorder} \
                             -imi {inmask}  -tmi {tpmask} -omi {diffmask}\
                             -gd {xmin} {xmax} {ymin} {ymax} -savexy {stampxy}'
        else:
            hotpants_arg = f'{self.hotpants_dir} -inim {inim} -tmplim {tmplim} -outim {outim} -n i -c t \
                             -iu {inim_limit} -tu {tmplim_limit} -ig {i_gain} -ir {i_rdnoise} -tg {t_gain} -tr {t_rdnoise} \
                             -ng 3 6 {self.fwhm / 2} 4 {self.fwhm} 2 {self.fwhm * 2} \
                             -nsx {nsx} -nsy {nsy} -r {kernel} -nss {substamps} \
                             -ko {kernelorder} -bgo {bgorder} \
                             -imi {inmask}  -tmi {tpmask} \
                             -gd {xmin} {xmax} {ymin} {ymax}'

            # pdb.set_trace()

        # Run hotpants
        print(hotpants_arg)
        process = subprocess.Popen(hotpants_arg, shell=True)

        try:
            process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            process.kill()
            self.log.log('HOTPANTS execution timeout.')
            pass

        t_stop_run_hotpants = time.time()
        print("\n********* start DEBUG ***********")
        print("`run_hotpants` execution time: %s" % (t_stop_run_hotpants - t_start_run_hotpants))
        print("********* end DEBUG ***********\n")

        return

    def run_hotpants_dave(self):

        t_start_run_hotpants = time.time()

        # Construct paths
        # diff_file = os.path.basename(self.sci_im).replace('.fits', "_") + os.path.basename(self.ref_im).replace('.fits', '.diff.fits')
        # diff_path  = "{output_dir}/{diff_file}".format(output_dir=self.working_dir, diff_file=diff_file)
        # diff_mask_path = diff_path.replace('.fits', '.mask.fits')
        # diff_noise_path = diff_path.replace('.fits', '.noise.fits')
        # diff_kernel_path = diff_path.replace('.fits', '.kernel.fits')
        # diff_stampxy_reg_path = diff_path.replace('.fits', '.stampxy.reg')

        # sci_hp_input = self.sci_im.replace(".fits", "_1.fits")
        # sci_err_path = self.sci_im.replace(".fits", ".noise.fits")
        # sci_stampxy_path = self.sci_im.replace('.fits', '.stampxy.txt')
        # sci_mask_path = self.sci_im.replace('.fits', '.mask.fits')

        # temp_hp_input = self.ref_im.replace(".fits", "_1.fits")
        # temp_err_path = self.ref_im.replace(".fits", ".noise.fits")
        # temp_mask_path = self.ref_im.replace('.fits', '.mask.fits')
        sci_im = self.sci_im
        sci_hp_input = sci_im.replace(".fits", "_1.fits")
        sci_err_hp_input = sci_im.replace('.fits', '_1.noise.fits')
        sci_mask_hp_input = sci_im.replace('.fits', '_1.mask.fits')
        sci_stampxy_path = sci_im.replace('.fits', '_1.stampxy.txt')

        ref_im = self.ref_im
        ref_hp_input = ref_im.replace(".fits", "_1.fits")
        ref_err_hp_input = ref_im.replace('.fits', '_1.noise.fits')
        ref_mask_hp_input = ref_im.replace('.fits', '_1.mask.fits')

        diff_file = sci_im.replace('.fits', "_") + os.path.basename(ref_im).replace('.fits', '_1.diff.fits')
        diff_mask_path = diff_file.replace('.fits', '_1.mask.fits')
        diff_noise_path = diff_file.replace('.fits', '_1.noise.fits')
        diff_kernel_path = diff_file.replace('.fits', '_1.kernel.fits')
        diff_stampxy_reg_path = diff_file.replace('.fits', '_1.stampxy.reg')

        # HOTPANTS can only operate on files with single extensions. Create those files:
        # 1. Copy out science and error frames to their own files
        # 2. Add a pedastal to the science data based on the median error data
        # 3. Combine header information

        # Science file
        global_pedestal = 0.0

        with fits.open(self.sci_im, output_verify='fix') as dat:
            sci_data = dat['SCI', 1].data
            try:
                err_data = dat['ERR', 1].data
            except:
                err_data = 1 / np.sqrt(dat['WHT', 1].data)

            err_median = np.nanmedian(err_data[np.nonzero(err_data)])

            global_pedestal = 50.0 * err_median
            if global_pedestal == 0.0:
                print("\tPedastal is zero, default to 1.0")
                global_pedestal = 1.0

            print("\n\tMedian error value: `%0.4f`; Pedastal to add to Sci Im: `%0.4f`" % (err_median, global_pedestal))

            dat[0].data = sci_data + global_pedestal
            dat[0].header = dat[0].header + dat[1].header
            dat[0].writeto(sci_hp_input, overwrite=True)

            # Copy out the err information, keep the main headers
            dat[0].data = err_data
            dat[0].writeto(sci_err_hp_input, overwrite=True)

        # Template/reference file
        with fits.open(self.ref_im, output_verify='fix') as dat:
            sci_data = dat['SCI', 1].data
            try:
                err_data = dat['ERR', 1].data
            except:
                err_data = 1 / np.sqrt(dat['WHT', 1].data)

            # Use same pedestal as the science file...
            dat[0].data = sci_data + global_pedestal
            dat[0].header = dat[0].header + dat[1].header
            dat[0].writeto(ref_hp_input, overwrite=True)

            # Copy out the err information, keep the main headers
            dat[0].data = err_data
            dat[0].writeto(ref_err_hp_input, overwrite=True)

        # if not self.is_jades and not self.is_cosmos:
        #   raise Exception("Unable to create stamp file. Is this JADES or COSMOS?")

        if self.is_cosmos:
            # FOR COSMOS
            # Create catalog for this image set
            # Check if files already exist, and if so, bail out
            if not os.path.exists(sci_stampxy_path):
                cat_filt_keys = {
                    "f115w": "FLUX_KRON_F115W",
                    "f150w": "FLUX_KRON_F150W",
                    "f277w": "FLUX_KRON_F277W",
                    "f444w": "FLUX_KRON_F444W"
                }
                # Construct the diff im substamp catalog
                dat = Table.read('/astro/armin/data/jwst/primer_sources/primer-cosmos-grizli-v0.3.fits', format='fits')
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

                sci_obs3 = space_phot.observation3(self.sci_im)
                temp_obs3 = space_phot.observation3(self.ref_im)
                y_max, x_max = sci_obs3.data.shape

                xs, ys = sci_obs3.wcs.world_to_pixel(coords)
                in_img_indices = np.where((xs >= 0) & (xs <= x_max) & (ys >= 0) & (ys <= y_max))[0]

                output_tbl = Table(
                    [xs[in_img_indices],
                     ys[in_img_indices],
                     bright_ra[in_img_indices],
                     bright_dec[in_img_indices],
                     bright_flux[in_img_indices]], names=["X", "Y", "RA", "DEC", cat_filt_keys["f277w"]])

                output_tbl.write(sci_stampxy_path, format="ascii", overwrite=True)
                output_reg = self.sci_im.replace('.fits', '.primer_cat.reg')
                create_pixregionfile(xs[in_img_indices], ys[in_img_indices], output_reg, color="red", coords="image",
                                     radius=[0.4] * len(ys[in_img_indices]))
        elif self.is_jades:
            # FOR JADES
            # Create catalog for this image set
            # Check if files already exist, and if so, bail out
            if not os.path.exists(sci_stampxy_path):
                # Construct the diff im substamp catalog
                dat = Table.read('/astro/armin/Dave/JADES_data_collab/Catalog/jhat_cat.txt', format='ascii')
                ras = dat["RA"]
                decs = dat["DEC"]
                mags = dat["MAG"]

                indices = mags.argsort()
                sorted_ra = ras[indices]
                sorted_dec = decs[indices]
                sorted_mags = mags[indices]

                # coords = SkyCoord(sorted_ra, sorted_dec, unit=(u.deg, u.deg))
                coords = SkyCoord(sorted_ra, sorted_dec, unit=(u.deg, u.deg))

                sci_obs3 = space_phot.observation3(self.sci_im)
                temp_obs3 = space_phot.observation3(self.ref_im)
                y_max, x_max = sci_obs3.data.shape

                xs, ys = sci_obs3.wcs.world_to_pixel(coords)
                in_img_indices = np.where((xs >= 0) & (xs <= x_max) & (ys >= 0) & (ys <= y_max))[0]

                output_tbl = Table(
                    [xs[in_img_indices],
                     ys[in_img_indices],
                     sorted_ra[in_img_indices],
                     sorted_dec[in_img_indices],
                     sorted_mags[in_img_indices]], names=["X", "Y", "RA", "DEC", "MAGS"])

                output_tbl.write(sci_stampxy_path, format="ascii", overwrite=True)
                output_reg = self.sci_im.replace('.fits', '.jades.reg')
                create_pixregionfile(xs[in_img_indices], ys[in_img_indices], output_reg, color="red", coords="image",
                                     radius=[0.4] * len(ys[in_img_indices]))
        elif self.is_aaih:
            # FOR AAIH
            # Create catalog for this image set
            # Check if files already exist, and if so, bail out
            if not os.path.exists(sci_stampxy_path):
                # Construct the diff im substamp catalog

                dat = Table.read(
                    '/astro/armin/mike/auto-process2/processed_data/jw01324-o001_t001_nircam_clear-f200w_i2d.phot.txt',
                    format='ascii')
                ras = dat["ra"]
                decs = dat["dec"]
                mags = dat["mag"]

                indices = mags.argsort()
                sorted_ra = ras[indices]
                sorted_dec = decs[indices]
                sorted_mags = mags[indices]

                # coords = SkyCoord(sorted_ra, sorted_dec, unit=(u.deg, u.deg))
                coords = SkyCoord(sorted_ra, sorted_dec, unit=(u.deg, u.deg))

                sci_obs3 = space_phot.observation3(self.sci_im)
                temp_obs3 = space_phot.observation3(self.ref_im)
                y_max, x_max = sci_obs3.data.shape

                xs, ys = sci_obs3.wcs.world_to_pixel(coords)
                in_img_indices = np.where((xs >= 0) & (xs <= x_max) & (ys >= 0) & (ys <= y_max))[0]

                output_tbl = Table(
                    [xs[in_img_indices],
                     ys[in_img_indices],
                     sorted_ra[in_img_indices],
                     sorted_dec[in_img_indices],
                     sorted_mags[in_img_indices]], names=["X", "Y", "RA", "DEC", "MAGS"])

                output_tbl.write(sci_stampxy_path, format="ascii", overwrite=True)
                output_reg = self.sci_im.replace('.fits', '.aaih.reg')
                create_pixregionfile(xs[in_img_indices], ys[in_img_indices], output_reg, color="red", coords="image",
                                     radius=[0.4] * len(ys[in_img_indices]))

        elif self.is_jhat_generic:
            print("GENERIC JHAT")
            # FOR AAIH
            # Create catalog for this image set
            # Check if files already exist, and if so, bail out
            if not os.path.exists(sci_stampxy_path) or True:
                # Construct the diff im substamp catalog

                dat = Table.read(self.jhat_file, format='ascii')
                ras = dat["ra"]
                decs = dat["dec"]
                mags = dat["mag"]

                indices = mags.argsort()
                sorted_ra = ras[indices]
                sorted_dec = decs[indices]
                sorted_mags = mags[indices]

                # coords = SkyCoord(sorted_ra, sorted_dec, unit=(u.deg, u.deg))
                coords = SkyCoord(sorted_ra, sorted_dec, unit=(u.deg, u.deg))

                sci_obs3 = space_phot.observation3(self.sci_im)
                temp_obs3 = space_phot.observation3(self.ref_im)
                y_max, x_max = sci_obs3.data.shape

                xs, ys = sci_obs3.wcs.world_to_pixel(coords)
                in_img_indices = np.where((xs >= 0) & (xs <= x_max) & (ys >= 0) & (ys <= y_max))[0]

                output_tbl = Table(
                    [xs[in_img_indices],
                     ys[in_img_indices],
                     sorted_ra[in_img_indices],
                     sorted_dec[in_img_indices],
                     sorted_mags[in_img_indices]], names=["X", "Y", "RA", "DEC", "MAGS"])

                output_tbl.write(sci_stampxy_path, format="ascii", overwrite=True)
                output_reg = self.sci_im.replace('.fits', '.reg')
                create_pixregionfile(xs[in_img_indices], ys[in_img_indices], output_reg, color="red", coords="image",
                                     radius=[0.4] * len(ys[in_img_indices]))
                create_pixregionfile(xs, ys, output_reg, color="red", coords="image", radius=[0.4] * len(ys))

        print('JHAT?', self.is_jhat_generic, self.is_jades, self.is_cosmos, self.is_aaih)
        # Create Science and Template Masks
        with fits.open(sci_err_hp_input, output_verify='fix') as dat:

            sci_err_data = dat[0].data
            sci_mask = np.zeros_like(sci_err_data)
            sci_mask[sci_err_data == 0] = 0x80
            sci_mask[np.isnan(sci_err_data)] = 0x80
            if self.custom_mask is not None:
                sci_mask[self.custom_mask == 1] = 0x80

            dat[0].data = sci_mask
            dat[0].scale('int16')
            dat.writeto(sci_mask_hp_input, overwrite=True)

        with fits.open(ref_err_hp_input, output_verify='fix') as dat:

            ref_err_data = dat[0].data
            temp_mask = np.zeros_like(ref_err_data)
            temp_mask[ref_err_data == 0] = 0x80
            temp_mask[np.isnan(ref_err_data)] = 0x80
            if self.custom_mask is not None:
                sci_mask[self.custom_mask == 1] = 0x80

            dat[0].data = temp_mask
            dat[0].scale('int16')
            dat[0].writeto(ref_mask_hp_input, overwrite=True)

        # Get filter and instrument
        sci_filt = ""
        sci_instrument = ""
        with fits.open(self.sci_im) as sci_in:
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
        with fits.open(self.ref_im) as temp_in:
            temp_filt = temp_in[0].header['FILTER']
            temp_instrument = temp_in[0].header['INSTRUME']

        # If filter and instrument combo are not found, default to FWHM = 1.8 pixels
        temp_fwhm = 1.8
        if temp_instrument in filters:
            if temp_filt in filters[temp_instrument]:
                temp_fwhm = filters[temp_instrument][temp_filt]
        else:
            print(f'{temp_instrument} not found in {list(filters.keys())}, FWHM fixed to 1.8 pixels.')

        max_val_sci_im = -9999
        max_val_temp_im = -9999

        with fits.open(sci_hp_input) as dat:
            max_val_sci_im = np.nanmax(dat[0].data)
            print("Max Sci Val %0.4f" % max_val_sci_im)

        with fits.open(ref_hp_input) as dat:
            max_val_temp_im = np.nanmax(dat[0].data)
            print("Max Temp Val %0.4f" % max_val_temp_im)

        # Sanity - if we don't have sensible max values, bail out
        if max_val_sci_im == -9999 or max_val_temp_im == -9999:
            raise Exception("Can't get real max values from the sci and temp images!")

        # pdb.set_trace()

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
        # iu =
        # iuk =

        tl = 0  # lower valid data count, template (0)
        tu = max_val_temp_im  # upper valid data count, template (25000)
        tuk = tu  # upper valid data count for kernel, template (tuthresh)
        # tu =
        # tuk =

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

        # pdb.set_trace()

        # hotpants_arg = '/astro/armin/pipe/v20.0/photpipe/Cfiles/bin/linux/hotpants -inim {sci_file} -tmplim {temp_file} -outim {diff_file} -ini {sci_noise_im} \
        #                -imi {sci_mask} -il {il} -iu {iu} -iuk {iuk} -tni {temp_noise_im} -tmi {temp_mask} \
        #                -tl {tl} -tu {tu} -tuk {tuk} -nrx {nrx} -nry {nry} -nsx {nsx} -nsy {nsy} -nss {nss} -ng {ng_tuple} \
        #                -rss {rss} -ft {ft} -r {r} -ko {ko} -bgo {bgo} -ssig {ssig} -ks {ks} -kfm {kfm} -okn -c {c} -n {n} -sconv \
        #                -cmp {diff_substamps} -afssc {afssc} -gridssc {gridssc} -fi {fi} \
        #                -oni {diff_noise_im}  -fin {fin} -mins {mins} \
        #                -omi {diff_mask} -mous {mous} -oki {diff_kernel} -v {v} -savexy {savexy}'.format(
        #                 sci_file=sci_hp_input, temp_file=temp_hp_input, diff_file=diff_path,
        #                 sci_noise_im=sci_err_path, sci_mask=sci_mask_path, il=il, iu=iu, iuk=iuk, temp_noise_im=temp_err_path,
        #                 temp_mask=temp_mask_path, tl=tl, tu=tu, tuk=tuk, nrx=nrx, nry=nry, nsx=nsx, nsy=nsy, nss=nss, ng_tuple=" ".join([str(_ng) for _ng in ng]),
        #                 rss=rss, ft=ft, r=r, ko=ko, bgo=bgo, ssig=ssig, ks=ks, kfm=kfm, c=c, n=n, diff_substamps=sci_stampxy_path,
        #                 afssc=afssc, gridssc=gridssc, fi=fi, diff_noise_im=diff_noise_path, fin=fin,
        #                 mins=mins, diff_mask=diff_mask_path, mous=mous, diff_kernel=diff_kernel_path, v=v, savexy=diff_stampxy_reg_path)
        hotpants_arg = 'hotpants -inim {sci_file} -tmplim {temp_file} -outim {diff_file} \
               -ini {sci_noise_im} \
               -imi {sci_mask} -il {il} -iu {iu} -iuk {iuk} \
               -tni {temp_noise_im} \
               -tmi {temp_mask} \
               -tl {tl} -tu {tu} -tuk {tuk} -nrx {nrx} -nry {nry} -nsx {nsx} -nsy {nsy} -nss {nss} -ng {ng_tuple} \
               -rss {rss} -ft {ft} -r {r} -ko {ko} -bgo {bgo} -ssig {ssig} -ks {ks} -kfm {kfm} -okn -c {c} -n {n} -sconv \
               -cmp {diff_substamps} -afssc {afssc} -gridssc {gridssc} -fi {fi} \
               -oni {diff_noise_im}  -fin {fin} -mins {mins} \
               -omi {diff_mask} -mous {mous} -oki {diff_kernel} -v {v} -savexy {savexy}'.format(
            sci_file=sci_hp_input, temp_file=ref_hp_input, diff_file=diff_file,
            sci_noise_im=sci_err_hp_input,
            sci_mask=sci_mask_hp_input, il=il, iu=iu, iuk=iuk,
            temp_noise_im=ref_err_hp_input,
            temp_mask=ref_mask_hp_input, tl=tl, tu=tu, tuk=tuk, nrx=nrx, nry=nry, nsx=nsx, nsy=nsy, nss=nss,
            ng_tuple=" ".join([str(_ng) for _ng in ng]),
            rss=rss, ft=ft, r=r, ko=ko, bgo=bgo, ssig=ssig, ks=ks, kfm=kfm, c=c, n=n, diff_substamps=sci_stampxy_path,
            afssc=afssc, gridssc=gridssc, fi=fi, diff_noise_im=diff_noise_path, fin=fin,
            mins=mins, diff_mask=diff_mask_path, mous=mous, diff_kernel=diff_kernel_path, v=v,
            savexy=diff_stampxy_reg_path)

        print("Hotpants invocation:\n\t%s" % hotpants_arg)
        process = subprocess.Popen(hotpants_arg, shell=True)

        try:
            process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            process.kill()
            print('HOTPANTS execution timeout.')
            pass

        t_stop_run_hotpants = time.time()
        print("\n********* start DEBUG ***********")
        print("`run_hotpants_dave` execution time: %s" % (t_stop_run_hotpants - t_start_run_hotpants))
        print("********* end DEBUG ***********\n")

        return
