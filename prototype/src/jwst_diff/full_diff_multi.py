import os, glob, pickle, sys
# sys.path.append('/astro/armin/data/jpierel/auto-process2')
from reprocess2 import AutoProcessNRC

sys.path.append('/app/src/joust')
from joust import Joust
from astropy.io import fits
import space_phot
import numpy as np
from astropy.table import Table, vstack
from astropy.coordinates import SkyCoord
import astropy.units as u
from source_match import spatial_coincidence_search, aperture_photometry
from utils import CandidateVisualizer
import copy

from configparser import RawConfigParser

# class diffClass():

# class observation3(diffClass):

# class observation2(diffClass):


if __name__ == '__main__':

    configFile = './Settings.ini'
    config = RawConfigParser()

    config.read(configFile)
    app_settings = config["diff_test"]


    sci3_processed = []  # 'jw06511_60646_f200w_30mas_i2d.fits','jw06511_60646_f444w_60mas_i2d.fits']
    ref3_processed = []  # 'jw02079_59976_f200w_30mas_i2d.fits','jw02079_59975_f444w_60mas_i2d.fits']
    field_name = 'massimo_bb'

    # Breaking change -- Sextractor has been initialized to IN_DIR but everything else expects /Image3Output

    # working_dir = '/astro/armin/data/jwst/mkdiffs'
    # working_dir = "%s" % app_settings["IN_DIR"]
    working_dir = "./"

    base_dir = os.path.join(working_dir, 'Image3Output')
    next_level3_ref = None
    next_level3_refs = [None] * 4
    restart = False
    # sci3_processed = [os.path.join('Image3Output',x) for x in ['jw06434-c1041_t000_nircam_clear-f090w',
    #                                                             'jw06434-c1041_t000_nircam_clear-f200w',
    #                                                             'jw05058_60703_f200w_30mas_i2d.fits',
    #                                                             'jw05058_60702_f277w_60mas_i2d.fits',
    #                                                             'jw05058_60706_f356w_60mas_i2d.fits',
    #                                                             'jw05058_60703_f444w_60mas_i2d.fits']]
    # ref3_processed = [os.path.join('Image3Output',x) for x in ['jw05058_60698_f115w_30mas_i2d.fits',
    #                                                             'jw05058_60698_f150w_30mas_i2d.fits',
    #                                                             'jw05058_60698_f200w_30mas_i2d.fits',
    #                                                             'jw05058_60698_f277w_60mas_i2d.fits',
    #                                                             'jw05058_60698_f356w_60mas_i2d.fits',
    #                                                             'jw05058_60698_f444w_60mas_i2d.fits']]
    # pickle.dump([sci3_processed,ref3_processed],open('last_run_%s.pkl'%field_name,'wb'))
    # sci3_processed, ref3_processed = pickle.load(open('last_run_%s.pkl' % field_name, 'rb'))
    # next_level3_refs = copy.deepcopy(sci3_processed)
    # ref3_processed = []
    # next_level3_ref = next_level3_refs[0]
    # sci3_processed = ['Image3Output/jw06434_60721_f200w_30mas_i2d.fits',
    #                     'Image3Output/jw06434_60722_f090w_30mas_i2d.fits',
    #                     'Image3Output/jw06434_60721_f444w_60mas_i2d.fits']
    # ref3_processed = ['Image3Output/jw01181_59979_f200w_30mas_i2d.fits',
    #                 'Image3Output/jw01181_59982_f090w_30mas_i2d.fits',
    #                 'Image3Output/jw01181_59980_f444w_60mas_i2d.fits']
    # pickle.dump([sci3_processed,ref3_processed],open('last_run_%s.pkl'%field_name,'wb'))
    # sci3_processed,ref3_processed = pickle.load(open('last_run_%s.pkl'%field_name.replace('_og',''),'rb'))
    # ref3_processed = [x for x in ref3_processed if x is not None and 'f444w' not in x]
    # print(sci3_processed,ref3_processed)
    # sys.exit()
    iter_i = -1
    if restart:

        # for scilist,reflist,ps in zip([['jw06434-c1041_t000_nircam_clear-f200w'],
        #                     ['jw06434-c1041_t000_nircam_clear-f090w'],
        #                     ['jw06434-c1041_t000_nircam_clear-f444w']],
        #             [['jw01181-o005_t008_nircam_clear-f200w'],
        #                 ['jw01181-o005_t008_nircam_clear-f090w'],
        #                  ['jw01181-o005_t008_nircam_clear-f444w'],
        #                 ],
        #             [30,30,60]):

        sci_arr = [['jw06434-c1040_t000_nircam_clear-f444w']]
        ref_arr = [['jw06434-c1033_t000_nircam_clear-f444w']]
        # for scilist, reflist, ps in zip(
        #         [['jw05893-o018_t018_nircam_clear-f115w'], ['jw05893-o018_t018_nircam_clear-f200w'],
        #          ['jw05893-o018_t018_nircam_clear-f356w']],
        #         [['jw01837-o003_t003_nircam_clear-f115w', 'jw01837-o004_t004_nircam_clear-f115w'],
        #          ['jw01837-o003_t003_nircam_clear-f200w', 'jw01837-o004_t004_nircam_clear-f200w'],
        #          ['jw01837-o003_t003_nircam_clear-f356w', 'jw01837-o004_t004_nircam_clear-f356w']],
        #         [30, 30, 60]):
        for scilist, reflist, ps in zip(sci_arr, ref_arr, [60]):
            iter_i += 1
            # if iter_i==0:
            #     continue
            # if 'f200w' in scilist[0]:
            #     sci3_processed,ref3_processed = pickle.load(open('last_run_%s.pkl'%field_name,'rb'))

            #     next_level3_ref = sci3_processed[0]
            #     next_level3_refs = sci3_processed
            #     continue

            # elif 'f444w' in sci2:
            #     continue
            #     sci3_processed = ['Image3Output/jw04793_60699_f150w_30mas_i2d.fits']
            #     ref3_processed = ['Image3Output/jw03707_60318_f150w_30mas_i2d.fits']
            #     #next_level3_refs = ['Image3Output/jw05890_60682_f150w_30mas_i2d.fits']
            #     continue
            # elif 'f460m' in sci2:
            #    sci3_processed = np.append(sci3_processed,['Image3Output/jw05890_60683_f460m_30mas_i2d.fits'])
            #    ref3_processed = np.append(ref3_processed,['Image3Output/jw03538_60302_f460m_30mas_i2d.fits'])
            #    continue
            # else:
            #     sci3_processed = np.append(sci3_processed,['Image3Output/jw04793_60699_f335m_60mas_i2d.fits'])
            #     ref3_processed = np.append(ref3_processed,['Image3Output/jw03707_60318_f335m_60mas_i2d.fits'])
            #     continue

            print(scilist)
            print(reflist)
            print(ps)
            # sys.exit()
            proc = AutoProcessNRC()
            proc.single_module = False
            proc.pixel_scale = ps
            proc.field_name = field_name
            proc.jhat_file = None
            # proc.sn_location = SkyCoord(150.1390125, 2.3957500, unit=u.deg)

            # proc.maxmjd = 60665
            # ref2 = 'jw04793-o001_t001_nircam_clear-f150w'
            # sci2 = 'jw03707-o004_t003_nircam_clear-f150w'
            # sci2='jw06511-o002_t001_nircam_clear-f444w'
            # reflist=['jw02079-o001_t001_nircam_clear-f444w',
            #     'jw02079-o004_t001_nircam_clear-f444w']
            # obslist = [ref2,sci2]
            # if iter_i<2:
            #    continue
            # proc.jhat_file = 'Image3Output/jw06434_60715_f200w_6434_z42_30mas_i2d.fits'
            if False:
                for sci2 in scilist:
                    proc.filter_name = sci2.split('-')[-1].upper()
                    proc.obs_id = sci2
                    proc.start_level2 = True
                    # proc.minmjd = 60720
                    # proc.pid=5398
                    if proc.jhat_file is None and next_level3_ref is None:
                        proc.jhat_file = 'mastDownload/JWST/{}/{}_i2d.fits'.format(proc.obs_id, proc.obs_id)
                        # proc.level3_ref =  proc.jhat_file
                        proc.get_level3 = True


                    else:
                        proc.get_level3 = False
                        proc.jhat_refcat = 'sewpy_cut.txt'
                        # proc.jhat_file = next_level3_refs[0]

                        # proc.jhat_file = next_level3_ref
                        # proc.level3_ref = next_level3_ref

                    # if iter_i==0:
                    # proc.level3_ref = None
                    #    proc.check_lvl2_overlap = proc.jhat_file

                    if iter_i > 0:
                        proc.level3_ref = next_level3_refs[0]
                        proc.check_lvl2_overlap = proc.jhat_file
                    if True:
                        proc.query_mast()

                    proc.run_jhat()
                    proc.correct_1overf()
                proc.create_lvl3_asn()

                proc.run_image3()
                try:
                    for f in glob.glob('cal_asn*.json'):
                        os.remove(f)
                except:
                    pass

                proc.cleanup()
                # sys.exit()
                # else:
                # sci3_processed = ['Image3Output/']
                # proc.fnames = ['Image3Output/jw05398_60728_f200w_30mas_i2d.fits']
                # sci3_processed = ['Image3Output/jw06434_60721_f200w_30mas_i2d.fits',
                #         'Image3Output/jw06434_60722_f090w_30mas_i2d.fits',
                #         'Image3Output/jw06434_60721_f444w_60mas_i2d.fits']
                # ref3_processed = ['Image3Output/jw01181_59979_f200w_30mas_i2d.fits',
                #                 'Image3Output/jw01181_59982_f090w_30mas_i2d.fits',
                #                 'Image3Output/jw01181_59980_f444w_60mas_i2d.fits']

                # break
                next_level3_refs = proc.fnames

                sci3_processed = np.append(sci3_processed, proc.fnames)



            else:
                sci3_processed = ['Image3Output/jw06434_60731_f444w_massimo_bb_60mas_i2d.fits']
                #     ref3_processed = ['Image3Output/jw05058_60698_f115w_30mas_i2d.fits']
                #    ref3_processed = ref3_processed[:-1]
                #    print(ref3_processed)
                next_level3_refs = copy.deepcopy([sci3_processed[iter_i]])

            # proc.save_output()

            # sys.exit()

            for i, next_level3_ref in enumerate(next_level3_refs):

                # next_level3_ref = proc.fnames[0]

                # else:
                #    sci3_processed=np.append(sci3_processed,['jw05893_60638_f115w_30mas_i2d.fits'])
                #    next_level3_ref = 'Image3Output/jw05893_60638_f115w_30mas_i2d.fits'
                #    ref3_processed = np.append(ref3_processed,['jw01727_60309_f115w_30mas_i2d.fits'])
                #    continue
                proc = AutoProcessNRC()
                proc.field_name = field_name
                # proc.extra_key = '_'+['018001','018003','018005','018007'][i]
                proc.single_module = False
                proc.pixel_scale = ps
                proc.get_level3 = False
                # proc.sn_location = SkyCoord(150.1390125, 2.3957500, unit=u.deg)
                proc.check_lvl2_overlap = next_level3_ref
                proc.level3_ref = next_level3_ref
                if os.path.exists('sewpy_cut.txt'):
                    proc.jhat_refcat = 'sewpy_cut.txt'
                else:
                    proc.jhat_file = next_level3_ref
                proc.start_level2 = True
                # proc.maxmjd = 60720
                # proc.minmjd = 60700
                # pdb.set_trace()
                if True:

                    for obsid in reflist:
                        proc.obs_id = obsid

                        obs = proc.query_mast()

                    proc.run_jhat()

                    proc.correct_1overf()

                proc.create_lvl3_asn()

                proc.run_image3()

                proc.save_output()
                proc.cleanup()

                # proc.create_lvl3_asn()

                # proc.save_output()
                # proc.process()
                try:
                    ref3_processed = np.append(ref3_processed, proc.fnames)
                except:
                    ref3_processed = np.append(ref3_processed, [None])
                    # 'Image3Output/jw05997_60598_f150w_module_b_30mas_i2d.fits']#
            pickle.dump([sci3_processed, ref3_processed], open('last_run_%s.pkl' % field_name, 'wb'))



    else:
        sci3_processed, ref3_processed = pickle.load(open('last_run_%s.pkl' % field_name, 'rb'))
        # sci3_processed = np.append(sci3_processed,['Image3Output/jw06434_60714_f090w_30mas_i2d.fits'])
        # ref3_processed = np.append(ref3_processed,['Image3Output/jw03577_60352_f090w_30mas_i2d.fits'])
    # sci3_processed = ['Image3Output/jw06434_60715_f200w_30mas_i2d.fits',
    #                     'Image3Output/jw06434_60715_f444w_30mas_i2d.fits',
    #                     'Image3Output/jw06434_60714_f090w_30mas_i2d.fits']
    # ref3_processed = ['Image3Output/jw01181_59980_f200w_30mas_i2d.fits',
    #                     'Image3Output/jw01895_59987_f444w_30mas_i2d.fits',
    #                     'Image3Output/jw03577_60352_f090w_30mas_i2d.fits']
    # ref3_processed = ref3_processed[1:]
    print(sci3_processed)
    print(ref3_processed)
    # pdb.set_trace()
    # sys.exit()
    if True:

        diff_list = []
        filter_list = []
        ps_list = []
        for i in range(len(sci3_processed)):
            if ref3_processed[i] is None:
                continue
            j = Joust()

            # custom mode allows use of specific data
            j.mode = 'custom'

            # Define files to subtract
            j.file = os.path.join(base_dir, os.path.basename(sci3_processed[i]))
            j.template_file = os.path.join(base_dir, os.path.basename(ref3_processed[i]))
            print(j.file, j.template_file)
            # Define JOUST Parameters
            j.run_jhat = False
            j.run_reproject = False
            j.reproject_sci = False  # reproject the template NOT the science image
            j.perform_dir_ops = False
            j.save_intermediate_files = False
            # j.output_dir = os.path.join(working_dir, 'Image3Output/')
            j.output_dir = os.path.join('Image3Output/')
            print(j.output_dir)
            j.is_cosmos = False
            j.is_jhat_generic = True
            j.jhat_file = os.path.join(working_dir, 'sewpy_cut.txt')  # sci3_processed[i]).replace('_i2d.fits',
            # '.goodmatches.phot.txt')
            print("Running JOUST...")
            # run the subtraction
            if True:  # or 'f200w' in j.file.lower():
                j.run(verbose=True)

            sci = fits.open(j.file)
            ref = fits.open(j.template_file)  # .replace('.fits','_reprojected.fits'))

            sci_obs = space_phot.observation3(j.file)
            ps_list.append(sci_obs.pixel_scale)
            filter_list.append(sci_obs.filter)
            diff_list.append(
                os.path.basename(j.file)[:-5] + '_' + os.path.basename(j.template_file)[:-5] + '_1.diff.fits')
            if True:  # 'f090w' in filter_list[-1].lower():
                sci['SCI'].data -= ref[
                    'SCI'].data  # -np.nanmedian(ref['SCI'].data)+np.nanmedian(sci['SCI'].data))
                temp = fits.open(os.path.join(j.output_dir, diff_list[-1]))
                # pdb.set_trace()
                temp[0].data = sci["SCI"].data
                # temp[0].header+=sci['SCI'].header
                # temp[0].header+=sci[0].header
                # sci.writeto(j.file.replace('.fits','_straight.fits'),overwrite=True)
                temp.writeto(os.path.join(j.output_dir, diff_list[-1]), overwrite=True)
                # temp[0].data = np.zeros_like(temp[0].data)

                # temp.writeto(diff_list[-1].replace('diff.fits','diff_1.mask.fits'),overwrite=True)

    if True:
        # diff_list = ['jw06511_60646_f200w_30mas_i2d_jw02079_59976_f200w_30mas_i2d_1.diff.fits',
        #        'jw06511_60646_f444w_60mas_i2d_jw02079_59975_f444w_60mas_i2d_1.diff.fits']
        # filter_list = ['F200W', 'F444W']
        # ps_list = [0.02999999999999999, 0.05999999999999976]
        print('diffs', diff_list)
        print('filts', filter_list)
        print('ps', ps_list)

        # diffs = [x for x in glob.glob(os.path.join(base_dir,'*diff.fits')) if '02561' in x or '06434' in x]
        diffs = [os.path.join(base_dir, x) for x in diff_list]
        print(diffs)
        # sys.exit()
        masks = [x.replace('diff.fits', 'diff_1.mask.fits') for x in diffs]
        science = [x.split('_jw')[0] + '.fits' for x in diffs]
        reference = [os.path.join(os.path.dirname(x), 'jw_' + x.split('_jw')[1].replace('_1.diff.fits', '.fits')) for x
                     in diffs]

        spatial_coincidence_search(  # list(np.array(diffs)[keep]),
            # list(np.array(glob.glob(os.path.join(base_dir,'*o035_t039*/*mask.fits')))[keep]),
            # list(np.array(science)[keep]),
            # list(np.array(reference)[keep]),
            diffs,
            masks,
            science,
            reference,
            '.',
            field_name,
            detection_limit={filt: 30 for filt in filter_list},  # in AB mag
            n_detections=1,  # across all filters
            fwhm=None,
            # required_filters=['F150W'],
            max_separation={filter_list[i]: ps_list[i] * 1 for i in range(len(filter_list))},  # arcseconds
            max_deltat=np.inf,
            # max_host_sep=4, # arcseconds
            # redshift_catalog='goods_n_z.txt',#'magnif_combined_z.txt',
            # truth_catalog=None,
            # required_sc=SkyCoord(73.5462622,-3.0146953,unit=u.deg),
            # required_sc_sep=60,
            # redshift_catalog_zcol='EAZY_z_a',
            # redshift_catalog_othercols=['ID'],
        ),
        # sharplo=0,sharphi=1,roundlo=-10,roundhi=10)

        sources = Table.read('%s.diff.cat.txt' % field_name, format='ascii')
        source_coords = SkyCoord(sources['ra'], sources['dec'], unit=u.deg)
        all_phot = None
        for d, filt, science_im, ref_im in zip(diff_list, filter_list, sci3_processed, ref3_processed):
            if ref_im is None:
                continue
            science_im = os.path.join('Image3Output', os.path.basename(science_im).replace('.fits', '_1.fits'))
            ref_im = os.path.join('Image3Output', os.path.basename(ref_im).replace('.fits', '_1.fits'))
            d = os.path.join('Image3Output', d)
            phot = aperture_photometry(
                diffim=d,
                source_locs=source_coords,
                filter_name=filt,
                headerim=science_im,
                errorim=d.replace('diff.fits', 'diff_1.noise.fits'))

            if phot is not None:
                phot['snid'] = sources['snid']  # .astype(int)
                phot['refim'] = ref_im
                phot['diffim'] = d
                phot['sciim'] = science_im

                sci_phot = aperture_photometry(
                    diffim=science_im,
                    source_locs=source_coords,
                    filter_name=filt,
                    headerim=science_im,
                    errorim=science_im.replace('.fits', '.noise.fits'))

                ref_phot = aperture_photometry(
                    diffim=ref_im,
                    source_locs=source_coords,
                    filter_name=filt,
                    headerim=ref_im,
                    errorim=ref_im.replace('.fits', '.noise.fits'))

                phot[filt + '_mag_sci'] = sci_phot['mag']
                phot[filt + '_magerr_sci'] = sci_phot['magerr']
                phot[filt + '_mag_ref'] = ref_phot['mag']
                phot[filt + '_magerr_ref'] = ref_phot['magerr']

            # pdb.set_trace()
            if all_phot is None:
                if phot is not None:
                    all_phot = phot.copy()
                else:
                    continue
            else:
                if phot is not None:
                    all_phot = vstack([all_phot, phot])
                else:
                    continue

        if all_phot is not None:
            all_phot.write('%s.phot.txt' % field_name.format(
                output_dir='.',
                field_name=field_name
            ), format='ascii.ecsv', overwrite=True)
        else:
            print("No sources for field: `%s`" % field_name)

    cv = CandidateVisualizer(field_name,  # sci_dict, ref_dict, diff_dict,
                             html_base_dir=os.path.join('html/', field_name), overwrite=True)
    cv.plot_SEDs = False
    cv.create_html_file_par('%s.diff.cat.txt' % field_name, '%s.phot.txt' % field_name)
