import space_phot
import photutils
import astropy
from astropy.table import Table, vstack
from astropy.io import fits
import glob, os, sys
from astropy.wcs import WCS
import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as u
from photutils.detection import DAOStarFinder
import warnings
from astropy.stats import sigma_clipped_stats
import sewpy

from configparser import RawConfigParser

# Dave Debug
import pdb

fwhm_dict = {'F070W': 0.987, 'F090W': 1.103, 'F115W': 1.298, 'F140M': 1.553, 'F150W2': 1.628, 'F150W': 1.770,
             'F162M': 1.801, 'F164N': 1.494, 'F182M': 1.990, 'F187N': 2.060, 'F200W': 2.141, 'F210M': 2.304,
             'F212N': 2.341, 'F250M': 1.340, 'F277W': 1.444, 'F300M': 1.585, 'F322W2': 1.547, 'F323N': 1.711,
             'F335M': 1.760, 'F356W': 1.830, 'F360M': 1.901, 'F405N': 2.165, 'F410M': 2.179, 'F430M': 2.300,
             'F444W': 2.302, 'F460M': 2.459, 'F466N': 2.507, 'F470N': 2.535, 'F480M': 2.574}

warnings.simplefilter('ignore')


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


def aperture_photometry(diffim, source_locs, filter_name, headerim=None, errorim=None, ext=0, err_ext=0):
    if errorim is not None:
        err = fits.open(errorim)[err_ext].data
    else:
        err = None

    if headerim is not None:
        diff = fits.open(diffim)
        obs = space_phot.observation3(headerim)
        obs.data = diff[ext].data
        # obs.err = np.sqrt(obs.data)
        # obs.err[obs.err==0]=np.nan
        # obs.err[np.isnan(obs.err)]=np.nanmedian(obs.err)
        # obs.err*=np.sqrt(2)
        obs.err = err

    else:
        # We don't need this if we have the correct files...
        temp_fits = fits.open(diffim)

        prim = fits.PrimaryHDU(temp_fits[0].data, temp_fits[0].header)
        sci = fits.ImageHDU(temp_fits[0].data, temp_fits[0].header, name='SCI')
        err = fits.ImageHDU(temp_fits[0].data * .1, temp_fits[0].header, name='ERR')
        dq = fits.ImageHDU(np.zeros_like(temp_fits[0].data), temp_fits[0].header, name='DQ')
        prim.header['TELESCOP'] = 'JWST'
        sci.header['TELESCOP'] = 'JWST'
        prim.header['FILTER'] = filter_name
        sci.header['FILTER'] = filter_name
        prim.header['INSTRUME'] = 'NIRCAM'
        sci.header['INSTRUME'] = 'NIRCAM'
        heads = [prim, sci]
        new_hdul = fits.HDUList(heads)
        new_hdul.writeto('test.fits', overwrite=True)
        obs = space_phot.observation3('test.fits')
        obs.err = None
        # obs.data = diff[0].data

    # pdb.set_trace()

    # if headerim is not None:
    #    obs = space_phot.observation3(headerim)
    #    obs.data = fits.open(diffim)[0].data
    # else:
    #    obs = space_phot.obseration3(diffim)
    # xys = obs.wcs.world_to_pixel(source_locs)
    # obs.aperture_photometry(xy_np.atleast_2d([xs,ys]).T
    # source_locs = source_locs.ravel()

    if len(source_locs) > 0 and np.nanmax(obs.data) > 0:
        try:
            if obs.telescope.lower() == 'jwst':
                obs.aperture_photometry(source_locs, encircled_energy=70, alternate_ref=headerim)
            else:
                obs.aperture_photometry(source_locs, radius=3, alternate_ref=headerim)
        except RuntimeError:
            # pdb.set_trace()
            return
        return obs.aperture_result.phot_cal_table
    else:
        return None


def combine_SCS_catalogs(catalog_list, output_name, tolerance=0.045, overwrite=False):  # arcsec

    catalog_tables = [Table.read(cat, format='ascii') for cat in catalog_list]
    catalog_tables = [tab for tab in catalog_tables if len(tab) > 0]
    if len(catalog_tables) == 0:
        return
    if len(catalog_list) == 1 or len(catalog_tables) == 1:
        catalog_tables[0].write(output_name, format='ascii', overwrite=True)
        return
    print('Starting with %i in all cats' % np.sum([len(cat) for cat in catalog_tables]))
    init_cat = vstack(catalog_tables)
    init_scs = SkyCoord(init_cat['ra'], init_cat['dec'], unit=u.deg)
    keep = []
    keep_sc = []
    keep_ra = []
    keep_dec = []
    # pdb.set_trace()
    for i in range(len(init_cat)):

        if len(keep) == 0:
            keep.append(i)
            # keep_sc = init_scs[i]
            # keep_ra.append(keep_sc.ra.value)
            # keep_dec.append(keep_sc.dec.value)
        else:
            seps = init_scs[i].separation(init_scs).arcsec
            if len(np.where(seps < tolerance)[0]) == 1:
                # elif np.min(init_scs[i].separation(keep_sc).arcsec)>tolerance:
                keep.append(i)
            else:
                first = int(np.min(np.where(seps < tolerance)[0]))
                if first not in keep:
                    keep.append(first)
                    # keep_ra.append(init_scs[i].ra.value)
                # keep_dec.append(init_scs[i].dec.value)
                # keep_sc = SkyCoord(keep_ra,keep_dec,unit=u.deg)
        # pdb.set_trace()

    init_cat = init_cat[np.array(keep)]

    init_cat.write(output_name, format='ascii', overwrite=overwrite)
    create_pixregionfile(init_cat['ra'], init_cat['dec'], output_name.replace('.txt', '.reg'), 'red',
                         coords='icrs', radius=[.4] * len(init_cat))
    print('Finished with %i' % len(init_cat))
    return


def spatial_coincidence_search(diffim_list,
                               mask_list,
                               sciim_list,
                               refim_list,
                               working_dir,
                               output_root_name,
                               detection_limit=28,  # in AB mag
                               n_detections=3,  # across all filters
                               fwhm=None,
                               required_filters=[],
                               max_separation=0.08,  # arcseconds
                               max_deltat=np.inf,
                               max_host_sep=4,  # arcseconds
                               redshift_catalog=None,
                               truth_catalog=None,
                               redshift_catalog_zcol='z',
                               redshift_catalog_othercols=[],
                               sharplo=None, sharphi=None, roundlo=None, roundhi=None,
                               required_sc=None, required_sc_sep=10,

                               ):

    configFile = './Settings.ini'
    config = RawConfigParser()

    config.read(configFile)
    app_settings = config["diff_test"]

    output_catalog = "{working_dir}/{field_name}.diff.cat.txt".format(
        working_dir=working_dir,
        field_name=output_root_name
    )
    output_regions = "{working_dir}/{field_name}.diff.cat.reg".format(
        working_dir=working_dir,
        field_name=output_root_name
    )

    # Obtain difference images and diff im masks based on `field_name` in the given `working_dir`
    # diffim_list = glob.glob("{working_dir}/*{field_name}*.diff.fits".format(
    #     working_dir = working_dir,
    #     field_name = output_root_name
    # ))

    # mask_list = glob.glob("{working_dir}/*{field_name}*.diff.mask.fits".format(
    #     working_dir = working_dir,
    #     field_name = output_root_name
    # ))

    data_arr = []
    wcs_arr = []
    peaks_arr = []
    dynamic_cut = False
    dynamic_cut_sharp = False
    dynamic_cut_round = False
    filter_list = []

    if mask_list is None:
        mask_list = [None] * len(diffim_list)
    detection_limit_flux = None
    max_separation_filt = {}
    mjd_list = []
    sew = sewpy.SEW(
        sexpath="source-extractor",
        workdir="%s" % app_settings["IN_DIR"],
        params=["X_IMAGE", "Y_IMAGE", "FLUX_RADIUS(3)", "FLAGS", "XPEAK_WORLD", "YPEAK_WORLD", "CLASS_STAR"],
        config={"DETECT_MINAREA": 3, "PHOT_FLUXFRAC": "0.3, 0.5, 0.8", 'DETECT_THRESH': 1.5,
                'BACKPHOTO_TYPE': 'local'}, loglevel=0)  # ,'FILTER_NAME':'gauss_5.0_9x9.conv'},

    print("\n***** Finding peaks in `%s`... ***** " % output_root_name)
    for i, diffim in enumerate(diffim_list):

        print("Checking `%s`" % diffim)

        # Get mask for matching file
        diffim_mask = diffim.replace(".fits", "_1.mask.fits")
        index_of_mask = mask_list.index(diffim_mask)
        mask_path = mask_list[index_of_mask]
        mask = fits.open(mask_path)[0].data.astype(bool)

        temp = fits.open(diffim)
        try:
            mjd_list.append(temp[0].header['TDB-MID'])
        except:
            try:
                mjd_list.append(temp[0].header['MJD-AVG'])
            except:
                mjd_list.append(temp[0].header['EXPMID'])
        data_arr.append(temp[0].data)
        wcs_arr.append(WCS(temp[0]))

        if isinstance(detection_limit, (float, int)):
            detection_limit_flux = space_phot.cal.JWST_mag_to_flux(detection_limit, wcs_arr[-1])
            if 'FILTER' in temp[0].header.keys():
                filt = temp[0].header['FILTER']
            elif 'FILTER1' in temp[0].header.keys():
                if 'CLEAR' in temp[0].header['FILTER1']:
                    filt = temp[0].header['FILTER2']
                else:
                    filt = temp[0].header['FILTER1']
            else:
                filt = None

        elif isinstance(detection_limit, dict) or isinstance(max_separation, dict):
            if 'FILTER' in temp[0].header.keys():
                filt = temp[0].header['FILTER']
            elif 'FILTER1' in temp[0].header.keys():
                if 'CLEAR' in temp[0].header['FILTER1']:
                    filt = temp[0].header['FILTER2']
                else:
                    filt = temp[0].header['FILTER1']
            else:
                filt = None

            if isinstance(detection_limit, dict):
                if filt is None:
                    print('Could not find filter key in %s, but you tried to set filter-dependent det. thresh' % diffim)
                    print('Exiting...')
                    sys.exit()
                elif filt not in detection_limit.keys():
                    print('Filter %s not found in your detection limit dictionary.' % filt)
                    print('Exiting...')
                    sys.exit()
                else:
                    detection_limit_flux = space_phot.cal.JWST_mag_to_flux(detection_limit[filt], wcs_arr[-1])

            if isinstance(max_separation, dict):
                if filt is None:
                    print(
                        'Could not find filter key in %s, but you tried to set filter-dependent max max_separation' % diffim)
                    print('Exiting...')
                    sys.exit()
                elif filt not in max_separation.keys():
                    print('Filter %s not found in your max_separation dictionary.' % filt)
                    print('Exiting...')
                    sys.exit()
                else:
                    max_separation_filt[filt] = max_separation[filt]
            else:
                max_separation_filt[filt] = max_separation

            filter_list.append(filt)
        else:
            print('Do not understand det limit')
            sys.exit()
        print(filt, detection_limit_flux)
        # peaks_arr.append(photutils.detection.find_peaks(data_arr[-1], detection_limit_flux, wcs=wcs_arr[-1], mask=mask))
        # finder = photutils.detection.DAOStarFinder(fwhm=fwhm_dict[filt], threshold=detection_limit_flux)#, wcs=wcs_arr[-1], mask=mask)
        # found = finder(data_arr[-1],mask=mask)
        data_arr[-1][mask > 0] = np.nan
        fits.HDUList([fits.PrimaryHDU(data_arr[-1])]).writeto('test.fits', overwrite=True)
        found = sew('test.fits')['table']
        # found = found[found['CLASS_STAR']>.01]
        os.remove('test.fits')
        # pdb.set_trace()
        # print(data_arr[-1])
        # pdb.set_trace()
        found['xcentroid'] = found['X_IMAGE'] - 1
        found['ycentroid'] = found['Y_IMAGE'] - 1
        found['skycoord_peak'] = wcs_arr[-1].pixel_to_world(found['xcentroid'], found['ycentroid'])
        if required_sc is not None:
            found = found[found['skycoord_peak'].separation(required_sc).arcsec < required_sc_sep]
        #
        peaks_arr.append(found)

        # print(np.min(peaks_arr[-1]['skycoord_peak'].separation(SkyCoord(64.0522996,-24.1036752,unit=u.deg)).arcsec))

    # sys.exit()
    # DC: Sanity
    # For any images that have no sources, let's remove them to protect against null values downstream...
    print("Any images to remove (i.e., there are no sources detected)?")
    indices_to_remove = []
    any_to_remove = False
    for i, p in enumerate(peaks_arr):
        if p is None:
            any_to_remove = True
            indices_to_remove.append(i)
    print("\t%s" % any_to_remove)

    # remove entries from all arrays where this is the case
    for i in sorted(indices_to_remove, reverse=True):
        print("\t\tRemoving `%s`" % diffim_list[i])
        del data_arr[i]
        del wcs_arr[i]
        del peaks_arr[i]
        del filter_list[i]
        del mjd_list[i]

    n_detections = np.min([n_detections, len(data_arr)])
    good_scs = []

    for i in range(len(data_arr) - 1):

        if len(filter_list) > 0:
            filt = filter_list[i]
        else:
            filt = None

        inds = np.array([j for j in range(len(data_arr)) if j != i])
        idx, seps, _ = astropy.coordinates.match_coordinates_sky(peaks_arr[i]['skycoord_peak'],
                                                                 vstack([peaks_arr[j] for j in range(len(peaks_arr)) if
                                                                         j != i])['skycoord_peak'])

        good = np.where(seps.arcsec < max_separation_filt[filt])[0]

        if len(good) >= 0:
            if len(good_scs) == 0:
                good_scs = np.array(peaks_arr[i]['skycoord_peak'][good])

            else:
                idx, seps, _ = astropy.coordinates.match_coordinates_sky(peaks_arr[i]['skycoord_peak'][good],
                                                                         SkyCoord([x.ra.value for x in good_scs],
                                                                                  [x.dec.value for x in good_scs],
                                                                                  unit=u.deg))
                good_scs = np.append(good_scs, peaks_arr[i]['skycoord_peak'][good][
                    np.where(seps.arcsec > max_separation_filt[filt])[0]])

    print("Number of good sources: %s" % len(good_scs))
    if not len(good_scs) > 0:
        print("\n\tSkipping checks -- no sources found")
    else:
        print("Checking sources...")
        keep = []

        for n in range(len(good_scs)):
            tempkeep = 0
            for j in range(len(wcs_arr)):
                x, y = wcs_arr[j].world_to_pixel(good_scs[n])

                if 0 < x < data_arr[j].shape[1] and 0 < y < data_arr[j].shape[0]:
                    tempkeep += 1

            if tempkeep >= n_detections:
                keep.append(n)

        good_scs = list(np.array(good_scs)[np.array(keep).astype(int)])

        start_inds = np.arange(0, len(good_scs), 1).astype(int)
        good_scs = SkyCoord([x.ra.value for x in good_scs], [x.dec.value for x in good_scs], unit=u.deg)
        ngood = np.zeros(len(good_scs))
        filt_req = np.zeros(len(good_scs))
        # pdb.set_trace()
        if True:
            filt_detected = np.zeros((len(good_scs), len(data_arr)))
            for i in range(len(data_arr)):
                if len(filter_list) > 0:
                    filt = filter_list[i]
                else:
                    filt = None

                xs, ys = wcs_arr[i].world_to_pixel(good_scs)  # [start_inds])
                new_scs = wcs_arr[i].pixel_to_world(peaks_arr[i]['xcentroid'], peaks_arr[i]['ycentroid'])
                idx, seps, _ = astropy.coordinates.match_coordinates_sky(good_scs, new_scs)

                ngood[np.where(seps.arcsec < max_separation_filt[filt])[0]] += 1
                if filt in required_filters:
                    filt_req[np.where(seps.arcsec > max_separation_filt[filt])[0]] = 1
                continue
                # sharp_round_cuts_set = False
                # if dynamic_cut or sharplo is None or sharphi is None or roundlo is None or roundhi is None:

                #     dynamic_cut = True

                #     daofind = DAOStarFinder(fwhm=fwhm_dict[filt], threshold=0,xycoords=np.atleast_2d([xs,ys]).T,
                #         sharplo=0,sharphi=1,roundlo=-10,roundhi=10)

                #     temp = None
                #     try:
                #         temp = daofind(data_arr[i])
                #     except Exception as e:
                #         print('\tError! `%s`' % e)
                #         print("\tExiting daofind stage...")

                #     tempsc = wcs_arr[i].pixel_to_world(temp['xcentroid'],temp['ycentroid'])
                #     #print(temp[np.argmin([tempsc.separation(SkyCoord(39.9706319,-1.5851453))]])

                #     # What to do if `temp` is None?
                #     if temp is not None:

                #         sharp_round_cuts_set = True

                #         if sharplo is None or dynamic_cut_sharp:
                #             dynamic_cut_sharp = True
                #             _,sharp,sharp_std = sigma_clipped_stats(temp['sharpness'])
                #             sharplo = sharp-1.5*sharp_std
                #             sharphi = sharp+1.5*sharp_std
                #         if roundlo is None or dynamic_cut_round:
                #             dynamic_cut_round = True
                #             _,roundl,round_std = sigma_clipped_stats(temp['roundness1'])
                #             roundlo=roundl-1.5*round_std
                #             roundhi = roundl+1.5*round_std
                #         print('\tcuts set to',sharplo,sharphi,roundlo,roundhi)
                #     else:
                #         print('\t`daofind` finds no sources to set sharp/round cuts!')

                # if sharp_round_cuts_set:
                #     daofind = DAOStarFinder(fwhm=fwhm_dict[filt], threshold=0,xycoords=np.atleast_2d([xs,ys]).T,sharplo=sharplo,sharphi=sharphi,roundlo=roundlo,roundhi=roundhi)
                #     sources = daofind(data_arr[i])

                #     if sources is not None:
                #         new_scs = wcs_arr[i].pixel_to_world(sources['xcentroid'],sources['ycentroid'])
                #         idx,seps,_ = astropy.coordinates.match_coordinates_sky(good_scs,new_scs)

                #         ngood[np.where(seps.arcsec<max_separation_filt[filt])[0]]+=1
                #     else:
                #         print("Sharp/round cuts lead to no good sources!")

            good_scs = good_scs[np.where(np.logical_and(ngood >= n_detections,
                                                        filt_req == 0))[0]]

    # DC: Break out the table creation in case there are no good sources --
    #   for booking keeping, let's still generate the catalog files.
    table_cols = ['snid', 'ra', 'dec']
    data = [
        [output_root_name + '_' + str(x) for x in np.arange(0, len(good_scs), 1)],
        [x.ra.value for x in good_scs],
        [x.dec.value for x in good_scs]
    ]

    if redshift_catalog is not None:

        # Add full table column list now that we have a catalog
        table_cols = np.append(['snid', 'ra', 'dec', 'host_z', 'host_sep', 'host_ra', 'host_dec'],
                               ['host_' + x for x in redshift_catalog_othercols])
        done = True
        if isinstance(redshift_catalog, str):
            try:
                zcat = Table.read(redshift_catalog, format='fits')
            except:
                try:
                    zcat = Table.read(redshift_catalog, format='ascii.ecsv')
                except:
                    try:
                        zcat = Table.read(redshift_catalog, format='ascii')
                    except:
                        print('Failed trying to open the z cat, skipping...')
                        done = False
        if done:

            if 'RA' in zcat.colnames:
                host_scs = SkyCoord(zcat['RA'], zcat['DEC'], unit=u.deg)
            elif 'ra' in zcat.colnames:
                host_scs = SkyCoord(zcat['dec'], zcat['dec'], unit=u.deg)
            else:
                print('Need RA or ra in host cat, skipping...')

            try:
                host_scs = host_scs[:, 0]
            except:
                pass
            host_ra = []
            host_dec = []
            host_z = []
            host_sep = []
            host_others = [[] for c in redshift_catalog_othercols]

            if len(good_scs) > 0:
                idx, seps, _ = astropy.coordinates.match_coordinates_sky(good_scs, host_scs)
                # import pdb
                # pdb.set_trace()
                good = np.where(seps.arcsec < max_host_sep)[0]
                print('Cut %i from host cut' % (len(good) - len(good_scs)))

                for best in range(len(good_scs)):
                    if seps.arcsec[best] > max_host_sep:
                        print(seps.arcsec[best])
                        continue
                    host_z.append(zcat[redshift_catalog_zcol][idx[best]])
                    host_sep.append(seps.arcsec[best])
                    host_ra.append(host_scs[idx[best]].ra.value)
                    host_dec.append(host_scs[idx[best]].dec.value)
                    for j, col in enumerate(redshift_catalog_othercols):
                        host_others[j].append(zcat[col][idx[best]])

                good_scs = good_scs[good]
                # Compose the new data with the host information
                data = [
                    np.arange(0, len(good_scs), 1).astype(str),
                    [x.ra.value for x in good_scs],
                    [x.dec.value for x in good_scs],
                    host_z,
                    host_sep,
                    host_ra,
                    host_dec,
                    *host_others
                ]
            else:
                print("No sources to relate to hosts!")

    # Populate the table
    print("Number of final `good` sources: %s" % len(good_scs))
    source_cat = Table(names=table_cols, dtype=[str] + [float] * (len(table_cols) - 1))
    for data_row in zip(*data):
        new_row = {}
        for i, d in enumerate(data_row):
            new_row[table_cols[i]] = d
        source_cat.add_row(new_row)

    # Hack: set data type of snid = to an int
    # source_cat["snid"] = [source_cat["snid"].astype(int)
    source_cat["snid"] = [output_root_name + '_' + str(x) for x in np.arange(0, len(good_scs), 1)]

    source_cat.write(output_catalog, format='ascii', overwrite=True)

    # Check if there is anything to process!
    if truth_catalog is not None and len(data_arr) > 0:
        if isinstance(truth_catalog, str):
            truth_catalog = Table.read(truth_catalog, format='ascii')
        truth_scs = SkyCoord(truth_catalog['ra'], truth_catalog['dec'], unit=u.deg)
        idx, seps, _ = astropy.coordinates.match_coordinates_sky(truth_scs, good_scs)
        found = np.where(seps.arcsec < .04)[0]
        print('final list includes %i/%i truth sne:' % (len(found), len(truth_catalog)))
        print('redshifts:',
              list(zip(truth_scs.ra.value[found], truth_scs.dec.value[found], np.array(host_z)[idx[found]])))
        print(source_cat[idx[found]])
        lost = np.where(seps.arcsec > .04)[0]
        if len(lost) > 0:
            print('lost:')
            print(truth_catalog[lost])

    # Default values so that we at least produce an empty region file...
    reg_radius = [0.4]
    ras = []
    decs = []
    if len(good_scs) > 0:
        reg_radius = [.4] * len(start_inds)
        ras = good_scs.ra.value
        decs = good_scs.dec.value

    create_pixregionfile(ras, decs, output_regions, 'red', coords='icrs', radius=reg_radius)


# if False:
#     spatial_coincidence_search(glob.glob('/astro/armin/data/jwst/primer_subtile2/*/difference.fits'),
#                            mask_list=[fits.open(x)[0].data.astype(bool) for x in glob.glob('/astro/armin/data/jwst/primer_subtile2/*/mask2_hdu.fits')],
#                            n_detections=3,detection_limit=0.1,max_separation=.06,redshift_catalog='primer_zcat.txt',
#                            redshift_catalog_zcol='z_a',redshift_catalog_othercols=['ID','zl68','zu68','zl95','zu95'],truth_catalog='true.txt')

# sources = Table.read('test_sources.txt',format='ascii')
# headers = {}
# for f in glob.glob('../pearls/g165/templates/*i2d.fits'):
#     temp = fits.open(f)
#     if 'FILTER' in temp[0].header:
#         headers[temp[0].header['FILTER']] = f
#     else:
#         f = '../pearls/g165/FINAL_IMAGES/mosaic_plckg165_ep2_nircam_f150w_30mas_20230510_i2d.fits'
#         headers['F150W'] = f
# print(headers)
# diffs = glob.glob('/astro/armin/data/jwst/primer_subtile2/*/difference.fits')
# all_phot = None
# from astropy.table import vstack
# for filt in ['F115W','F150W','F277W','F444W']:
#     diff = [x for x in diffs if filt in x][0]
#     temp = fits.open(diff)
#     phot = aperture_photometry(diff,
#                           SkyCoord(sources['ra'],sources['dec'],unit=u.deg),filt,
#                               headerim=headers[filt])
#     phot['snid'] = sources['snid']
#     if all_phot is None:
#         all_phot = phot.copy()
#     else:
#         all_phot = vstack([all_phot,phot])
# #all_phot.write('source_phot.txt',format='ascii')
# import pickle
# pickle.dump(all_phot,open('source_phot.pkl','wb'))
# sys.exit()

# spatial_coincidence_search(glob.glob('/astro/armin/data/jwst/primer_subtile2/*/difference.fits'),
#                            mask_list=[fits.open(x)[0].data.astype(bool) for x in glob.glob('/astro/armin/data/jwst/primer_subtile2/*/mask2_hdu.fits')],
#                            n_detections=3,detection_limit=0.1,max_separation=.06,redshift_catalog='primer_zcat.txt',
#                            redshift_catalog_zcol='z_a',redshift_catalog_othercols=['ID','zl68','zu68','zl95','zu95'],truth_catalog='true.txt')

# `diffim_list` requires more than one difference image -- since it's trying to match sources between diff ims.
# diff_im_list = glob.glob('/astro/armin/Dave/JOUST/joust_results/*.diff.fits')
# diff_mask_list = glob.glob('/astro/armin/Dave/JOUST/joust_results/*.diff.mask.fits')

# spatial_coincidence_search(diffim_list=diff_im_list,
#                            mask_list=diff_mask_list,
#                            n_detections=3,
#                            detection_limit=0.1,
#                            max_separation=0.06,
#                            redshift_catalog='/astro/armin/Dave/cosmos_data/primer_zcat.txt',
#                            redshift_catalog_zcol='z_a',
#                            redshift_catalog_othercols=['ID','zl68','zu68','zl95','zu95'])

if __name__ == '__main__':
    base_dir = '/astro/armin/data/jwst/mkdiffs/Image3Output/'

    # diffs = [x for x in glob.glob(os.path.join(base_dir,'*diff.fits')) if '02561' in x or '06434' in x]
    diffs = [os.path.join(base_dir, x) for x in
             ['jw06511_60646_f444w_60mas_i2d_jw02079_60332_f444w_60mas_i2d_1.diff.fits',
              'jw06511_60646_f200w_30mas_i2d_jw02079_59976_f200w_30mas_i2d_1.diff.fits']]
    print(diffs)
    # sys.exit()
    masks = [x.replace('diff.fits', 'diff_1.mask.fits') for x in diffs]
    science = [x.split('_jw')[0] + '.fits' for x in diffs]
    reference = [os.path.join(os.path.dirname(x), 'jw_' + x.split('_jw')[1].replace('_1.diff.fits', '.fits')) for x in
                 diffs]
    print(science)
    print(reference)
    # sys.exit()
    import pdb

    # pdb.set_trace()
    # filts = np.unique([x[x.rfind('clear')+len('clear-'):x.rfind('-jw01837')] for x in science])
    # filts = [x[x.rfind('-')+1:x.rfind('/')].upper() for x in science]
    # filt_check = {}
    # for i in range(len(science)):
    #     if 'f410m' in science[i] or 'f150w' in science[i] or 'f444w' in science[i] or 'f090w' in science[i]:
    #         continue
    #     sci = fits.open(science[i])
    #     #filt = sci[0].header['FILTER']
    #     #if filt not in filts:
    #     #    filts.append(filt)
    #     ref = fits.open(reference[i])
    #     diff = fits.open(diffs[i])
    #     if 'FILTER' not in sci[0].header.keys():
    #         sci[0].header['FILTER'] = filts[i]
    #         ref[0].header['FILTER'] = filts[i]
    #         diff[0].header['FILTER'] = filts[i]
    #         sci.writeto(science[i],overwrite=True)
    #         ref.writeto(reference[i],overwrite=True)
    #         diff.writeto(diffs[i],overwrite=True)

    #     sci[0].data = sci[0].data + ref[0].data
    #     sci[0].data[np.isfinite(sci[0].data)]=0
    #     sci[0].data[~np.isfinite(sci[0].data)]=1
    #     if filts[i] not in filt_check:
    #         filt_check[filts[i]] = (np.sum(sci[0].data),i)
    #     else:
    #         if np.sum(sci[0].data)<filt_check[filts[i]][0]:
    #             filt_check[filts[i]] = (np.sum(sci[0].data),i)

    #     sci.writeto(science[i].replace('science.fits','difference.mask.fits'),overwrite=True)

    # filts = np.unique(filts)
    # keep = np.array([filt_check[filt][1] for filt in filt_check.keys()])
    # pdb.set_trace()
    filts = ['F444W', 'F200W']
    spatial_coincidence_search(  # list(np.array(diffs)[keep]),
        # list(np.array(glob.glob(os.path.join(base_dir,'*o035_t039*/*mask.fits')))[keep]),
        # list(np.array(science)[keep]),
        # list(np.array(reference)[keep]),
        diffs,
        masks,
        science,
        reference,
        '.',
        'test',
        detection_limit={filt: 30 for filt in filts},  # in AB mag
        n_detections=2,  # across all filters
        fwhm=None,
        max_separation={filt: .065 if filt != 'F444W' else .065 for filt in filts},  # arcseconds
        max_deltat=np.inf,
        max_host_sep=4,  # arcseconds
        redshift_catalog=None,
        truth_catalog=None,
        redshift_catalog_zcol='z',
        redshift_catalog_othercols=[]),
    # sharplo=0,sharphi=1,roundlo=-10,roundhi=10)

    # Make a MASK TOTAL = a logical OR of image and reference masks
