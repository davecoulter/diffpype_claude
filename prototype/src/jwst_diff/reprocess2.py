#! /usr/bin/python

import sys, os, glob, shutil
from astropy.io import fits
from astropy.coordinates import SkyCoord
from astropy import wcs
import pprint, pdb
import os
import space_phot
from astropy.wcs.utils import skycoord_to_pixel
from astropy import units as u
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from astroquery.mast import Observations
from astroquery.mast import Catalogs
from astropy.table import Table
from astropy.stats import sigma_clipped_stats
import astropy
import sewpy
import shapely
import shapely.wkt
from photutils.detection import DAOStarFinder

from image1overf import sub1fimaging

import space_phot
from jhat import jwst_photclass, st_wcs_align

from jwst.pipeline import Detector1Pipeline, Image2Pipeline, Image3Pipeline
from jwst.associations import asn_from_list
from jwst.associations.lib.rules_level2_base import DMSLevel2bBase
from jwst.associations.lib.rules_level3_base import DMS_Level3_Base
from jwst import datamodels
from tweakwcs.correctors import FITSWCSCorrector

import gwcs

from configparser import RawConfigParser

os.environ['CRDS_SERVER_URL'] = 'https://jwst-crds.stsci.edu'


# os.environ['CRDS_PATH'] = '/Users/mengesser/Documents/JW_tutorial/CRDS/'

def create_pixregionfile(x, y, regionname, color, coords='image', radius=1):
    if isinstance(radius, (int, float)):
        radius = [radius] * len(x)
    with open(regionname, 'w') as f:
        if isinstance(color, str):
            f.write('global color={0} dashlist=8 3 width=2 font=\"helvetica 10 normal roman\" select=1 highlite=1 dash=0 fixed=0 edit=1 move=1 delete=1 inc\
lude=1 source=1 \n'.format(color))
            do_col = False
        else:
            do_col = True
            f.write('global dashlist=8 3 width=2 font=\"helvetica 10 normal roman\" select=1 highlite=1 dash=0 fixed=0 edit=1 move=1 delete=1 include=1 sou\
rce=1 \n')
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


class AutoProcessNRC():

    def __init__(self):

        self.obs_id = "jw01727-o149_t143_nircam_clear-f150w"
        self.token = '7b8d6992489f44a1b7a14809f6e04b46'
        self.download_dir = "./"
        self.get_level3 = False
        self.pixel_scale = 'native'
        self.single_module = False
        self.jhat_refcat = None
        self.jhat_file = None
        self.level3_ref = None
        self.start_level2 = False
        self.check_lvl2_overlap = None
        self.maxmjd = 9999999
        self.minmjd = 0
        self.expid_substring = None
        self.extra_key = ''
        self.filter_name = None
        self.pid = None
        self.field_name = None
        self.sn_location = None
        return

    def query_mast(self):
        """Query OBS and download"""

        # mikes most recent tokenn

        os.environ["MAST_API_TOKEN"] = self.token

        Observations.login(token=self.token)
        # try:
        obs = Observations.query_criteria(
            # obs_collection='JWST',
            # proposal_id = '6434',
            # instrument_name=['NIRCAM/IMAGE'],
            # calib_level=2,
            # target_name=['ABELL2744']
            # filters=[self.filter_name],
            obs_id=self.obs_id,
            # t_min=[self.minmjd,self.maxmjd],
            # dataproduct_type=['image']
        )

        # except RuntimError:
        #     #self.filter_name is not None:
        #     #pdb.set_trace()
        #     #self.minmjd = 60712
        #     obs = Observations.query_criteria(
        #         #obs_collection='JWST',
        #         proposal_id = proc.pid,
        #         #instrument_name=['NIRCAM/IMAGE'],
        #         calib_level=2,
        #         #target_name=['ABELL2744']
        #         filters=self.filter_name,
        #         #obs_id=self.obs_id,
        #         t_min=[self.minmjd,self.maxmjd],
        #         #dataproduct_type=['image']
        #     )
        # else:

        data_products_by_obs = Observations.get_product_list(obs)
        # pdb.set_trace()
        if self.get_level3:
            mosaic_data_products = data_products_by_obs[data_products_by_obs['calib_level'] == 3]
            mosaic_data_products = mosaic_data_products[mosaic_data_products['productSubGroupDescription'] == 'I2D']
            Observations.download_products(mosaic_data_products, extension='fits', download_dir=self.download_dir)
        # pdb.set_trace()
        if True:
            if self.start_level2:
                uncal_data_products = data_products_by_obs[data_products_by_obs['calib_level'] == 2]
                uncal_data_products = uncal_data_products[uncal_data_products['productSubGroupDescription'] == 'CAL']
                print(uncal_data_products)
                Observations.download_products(uncal_data_products, extension='fits', download_dir=self.download_dir)
                try:
                    os.mkdir('./Image2Output/')
                except:
                    pass
                # pdb.set_trace()
                if self.check_lvl2_overlap is not None:
                    jw_reg = [float(i) for i in fits.open(self.check_lvl2_overlap)[1].header['S_REGION'].split() if
                              i not in ['POLYGON', 'ICRS']]
                    fcheck = shapely.Polygon([jw_reg[i:i + 2] for i in range(0, len(jw_reg), 2)])
                else:
                    fcheck = None

                all_files = glob.glob(os.path.join(self.download_dir, 'mastDownload', 'JWST', '*', '*_cal.fits'))
                if self.sn_location is not None:
                    all_files_d = space_phot.util.filter_dict_from_list(all_files, self.sn_location)
                    # pdb.set_trace()
                    if self.filter_name is None:
                        all_files = all_files_d[list(all_files_d.keys())[0]]
                    else:
                        all_files = all_files_d[self.filter_name]
                for f in all_files:
                    if fcheck is not None:
                        temp_f = fits.open(f)
                        if 'S_REGION' not in temp_f[1].header.keys():
                            continue

                        temp_reg = [float(i) for i in temp_f[1].header['S_REGION'].split() if
                                    i not in ['POLYGON', 'ICRS']]
                        temp_shape = shapely.Polygon([temp_reg[i:i + 2] for i in range(0, len(temp_reg), 2)])
                        try:
                            x = fcheck.intersection(temp_shape)
                        except:
                            continue
                        fov_overlap = x.area * (u.degree ** 2).to(u.arcsecond ** 2)
                        # print(fov_overlap)
                        if fov_overlap / (temp_shape.area * (u.degree ** 2).to(u.arcsecond ** 2)) < .25:
                            continue
                    shutil.copyfile(f, os.path.join('Image2Output', os.path.basename(f)))
                # sys.exit()
            else:
                uncal_data_products = data_products_by_obs[data_products_by_obs['calib_level'] == 1]
                uncal_data_products = uncal_data_products[uncal_data_products['productSubGroupDescription'] == 'UNCAL']
                print(uncal_data_products)
                Observations.download_products(uncal_data_products, extension='fits', download_dir=self.download_dir)

        return

    def query_reg(self):

        sn_location = SkyCoord('3.4936809', '-30.3254398', unit=u.deg)

        obs = Observations.query_region(sn_location, radius=1 * u.arcsec)

        df = obs.to_pandas()
        df = df[df.obs_collection == 'JWST']
        df = df[df.instrument_name.isin(['NIRCAM/IMAGE', 'NIRISS/IMAGE'])]

        obs = Table.from_pandas(df)

        prod = Observations.get_product_list(obs)

        prod = prod[prod['productSubGroupDescription'] == 'UNCAL']

        Observations.download_products(prod, extension='fits', download_dir=self.download_dir)

        return

    def create_lvl1_asn(self):
        # can you even do this?

        uncal_list = glob.glob(self.download_dir + 'mastDownload/JWST/*/*_uncal.fits')

        uncal_list = [x for x in uncal_list if not os.path.exists(x.replace('_uncal', '_rate'))]

        return uncal_list

    def create_lvl2_asn(self):

        rate_list = glob.glob(self.download_dir + 'mastDownload/JWST/*/*_rate.fits')

        asn = asn_from_list.asn_from_list(rate_list,
                                          rule=DMSLevel2bBase)

        with open('./rate_asn.json', "w") as outfile:
            name, serialized = asn.dump(format='json')
            outfile.write(serialized)

        return

    def create_lvl3_asn(self):
        if self.expid_substring is None:
            full_cal_list = glob.glob('./Image2Output/*_1overf.fits')
            expid = ''
        else:
            full_cal_list = glob.glob('./Image2Output/*%s*_1overf.fits' % self.expid_substring)
            expid = '_' + self.expid_substring
        if self.pixel_scale == 30:
            ps = '_30mas'
        elif self.pixel_scale == 60:
            ps = '_60mas'
        else:
            ps = ''
        if self.field_name is None:
            field_name = ''
        else:
            field_name = '_' + self.field_name
        filters = space_phot.util.filter_dict_from_list(full_cal_list)
        import pprint
        # pprint.pprint(filters)
        # sys.exit()
        for filt in filters.keys():
            cal_list = filters[filt]
            temp = fits.open(cal_list[0])
            obs_id = 'jw%s_%i_%s%s' % (temp[0].header['PROGRAM'],
                                       temp[0].header['EXPMID'],
                                       filt.lower(), field_name)

            self.fnames = []
            if self.single_module:
                for module in 'ab':
                    print(filt, module, ps)
                    fname = 'Image3Output/' + obs_id + '_module_%s%s%s%s_i2d.fits' % (module, ps, expid, self.extra_key)
                    self.fnames.append(fname)
                    if os.path.exists(fname):
                        print('found')
                        continue
                    cal_list = filters[filt]
                    cal_list = [x for x in cal_list if 'nrc' + module in x]
                    print(filt, module, cal_list)
                    if len(cal_list) == 0:
                        continue
                    # lvl3file = self.obs_id#glob.glob('./mastDownload/JWST/*/*i2d.fits')

                    # basename = os.path.basename(lvl3file[0]).replace('_i2d.fits','')

                    asn = asn_from_list.asn_from_list(cal_list,
                                                      product_name=obs_id + '_module_%s%s%s%s' % (module,
                                                                                                  ps,
                                                                                                  self.expid_substring,
                                                                                                  self.extra_key),
                                                      rule=DMS_Level3_Base)
                    with open('./cal_asn_%s%s_%s.json' % (filt, ps, module), "w") as outfile:
                        name, serialized = asn.dump(format='json')
                        outfile.write(serialized)


            else:

                self.fnames.append(os.path.join('Image3Output', obs_id + ps + expid + self.extra_key + '_i2d.fits'))
                # cal_list = glob.glob('./Image2Output/*_1overf.fits')
                asn = asn_from_list.asn_from_list(cal_list,
                                                  product_name=obs_id + ps + expid + self.extra_key,
                                                  rule=DMS_Level3_Base)
                with open('./cal_asn_%s%s.json' % (filt, ps), "w") as outfile:
                    name, serialized = asn.dump(format='json')
                    outfile.write(serialized)

        # sys.exit()
        return

    def run_detector1(self, uncal_list):

        pipe1 = Detector1Pipeline()

        # pipe1.dark_current.skip = True
        # pipe1.lastframe.skip = True
        # pipe1.linearity.skip = True

        # pipe1.refpix.skip = True
        pipe1.jump.rejection_threshold = 3.5
        pipe1.jump.expand_large_events = True
        # pipe1.jump.find_showers = True
        pipe1.jump.maximum_cores = 'half'
        # pipe1.jump.save_output = True
        # pipe1.emicorr.skip == False
        # pipe1.ipc.skip = True
        # pipe1.reset.skip = True
        # pipe1.rscd.skip=False
        # pipe1.ramp_fit.skip = True
        pipe1.ramp_fit.maximum_cores = 'half'

        for f in uncal_list:
            pipe1.output_dir = os.path.dirname(f)
            pipe1.output_file = os.path.basename(f).replace('uncal', 'rate')

            pipe1.run(f)

        return

    def run_image2(self):
        try:
            os.mkdir('./Image2Output/')
        except:
            pass

        pipe2 = Image2Pipeline()

        pipe2.resample.skip = True
        pipe2.save_results = True
        pipe2.output_dir = './Image2Output/'

        pipe2.run('./rate_asn.json')

        return

    def run_image3(self):

        if not os.path.exists('./Image3Output/'):
            os.mkdir('./Image3Output/')
        # pdb.set_trace()
        if self.level3_ref is None:

            pipe3 = Image3Pipeline()

            pipe3.tweakreg.skip = True

            pipe3.outlier_detection.save_intermediate_results = False
            pipe3.outlier_detection.save_results = False
            pipe3.outlier_detection.skip = False
            pipe3.skymatch.skymethod = 'global+match'
            pipe3.skymatch.subtract = True
            pipe3.skymatch.skip = True
            pipe3.source_catalog.skip = True
            pipe3.save_results = True
            if self.pixel_scale != 'native':
                pipe3.resample.pixel_scale = self.pixel_scale / 1000

            pipe3.output_dir = './Image3Output/'
            asns = glob.glob('cal_asn*.json')
            for asn in asns:
                # if self.single_module:
                #    for module in 'ab':
                #        pipe3.run('./cal_asn_%s_%s.json'%module)
                # else:
                pipe3.run(asn)
        else:
            params = {'assign_mtwcs': {'skip': True},
                      'tweakreg': {'skip': True},
                      'skymatch': {'skip': True, 'skymethod': 'global+match', 'subtract': True},
                      'outlier_detection': {'skip': False},
                      'resample': {'pixfrac': 1.,
                                   'kernel': 'square',
                                   # 'pixel_scale'  : float(ref_pix),
                                   # 'rotation'     : ref_pa,#0, #-66.8983245393371,
                                   # 'output_shape' : list(ref_image.shape),
                                   # 'crpix'        : [0,0],
                                   # 'crval'        : ref_crval,
                                   'fillval': 'indef',
                                   'weight_type': 'ivm',
                                   # 'output_wcs': 'ref_wcs.asdf',
                                   # 'single'       : True,
                                   # 'blendheaders' : False,
                                   'in_memory': False,
                                   'save_results': True},
                      'source_catalog': {'skip': True}}
            asns = glob.glob('./cal_asn*.json')
            for asn in asns:

                # if os.path.exists(os.path.join('jw05451_60583_
                if asn.endswith('_a.json') or asn.endswith('_b.json'):
                    module = 'a' if asn.endswith('_a.json') else 'b'
                    i = 0 if asn.endswith('_a.json') else 1
                    if self.level3_ref is not None:
                        ref_image = fits.open(self.level3_ref[i])[1]

                        ref_wcs = wcs.WCS(ref_image)
                        sc = ref_wcs.pixel_to_world(0, 0)
                        ref_crval = [sc.ra.value, sc.dec.value]
                        ref_pa = ref_image.header['PA_V3']
                        ref_pix = astropy.wcs.utils.proj_plane_pixel_scales(ref_wcs)[0] * ref_wcs.wcs.cunit[0].to(
                            'arcsec')
                        params['resample']['pixel_scale'] = float(ref_pix)
                        params['resample']['rotation'] = ref_pa
                        params['resample']['output_shape'] = list(ref_image.shape)
                        params['resample']['crpix'] = [0, 0]
                        params['resample']['crval'] = ref_crval
                    Image3Pipeline.call(asn, steps=params, output_dir='./Image3Output/', save_results=True)
                else:
                    ref_image = fits.open(self.level3_ref)['SCI', 1]
                    ref_dm = datamodels.open(self.level3_ref)
                    ref_wcs = wcs.WCS(ref_image)
                    try:
                        ref_gwcs = ref_dm.meta.wcs
                    except:
                        ref_gwcs = FITSWCSCorrector(ref_wcs)
                    from asdf import AsdfFile

                    # ref_wcs = #gwcs.wcs.WCS(ref_image)
                    tree = {"wcs": ref_gwcs}
                    wcs_file = AsdfFile(tree)
                    wcs_file.write_to("ref_wcs.asdf")
                    params['resample']['output_wcs'] = 'ref_wcs.asdf'
                    sc = ref_wcs.pixel_to_world(0, 0)
                    ref_crval = [sc.ra.value, sc.dec.value]
                    ref_pa = ref_image.header['PA_V3']
                    ref_pix = astropy.wcs.utils.proj_plane_pixel_scales(ref_wcs)[0] * ref_wcs.wcs.cunit[0].to('arcsec')
                    if self.pixel_scale != 'native':
                        params['resample']['pixel_scale'] = self.pixel_scale / 1000
                    else:
                        params['resample']['pixel_scale'] = float(ref_pix)

                    # params['resample']['rotation'] = ref_pa
                    # print(list(np.array(ref_image.shape).astype(int).T))
                    # params['resample']['output_shape'] = [ref_image.shape[1],ref_image.shape[0]]
                    # params['resample']['crpix'] = [ref_image.header['CRPIX1'],ref_image.header['CRPIX2']]#[0,0]
                    # params['resample']['crval'] = [ref_image.header['CRVAL1'],ref_image.header['CRVAL2']]#ref_crval
                    # pprint.pprint(params)
                    # pdb.set_trace()
                    Image3Pipeline.call(asn, steps=params, output_dir='./Image3Output/', save_results=True)
        return

    def correct_1overf(self):

        cal_list = glob.glob('./Image2Output/*jhat.fits')
        if len(cal_list) == 0:
            cal_list = glob.glob('./Image2Output/*cal.fits')
            jhatdone = False
        else:
            jhatdone = True

        for cal2file in cal_list:
            if jhatdone:
                cal21overffile = cal2file.replace('_jhat.fits', '_jhat_1overf.fits')
            else:
                cal21overffile = cal2file.replace('_cal.fits', '_cal_1overf.fits')
            print('Running 1/f correction on {} to produce {}'.format(cal2file, cal21overffile))

            if os.path.exists(cal21overffile):
                print('{} already exists.'.format(cal21overffile))
                continue

            with fits.open(cal2file) as cal2hdulist:
                if cal2hdulist['PRIMARY'].header['SUBARRAY'] == 'FULL' or cal2hdulist['PRIMARY'].header[
                    'SUBARRAY'] == 'SUB256':
                    sigma_bgmask = 3.0
                    sigma_1fmask = 2.0
                    splitamps = False  # Set to True only in a sparse field so each amplifier will be fit separately.
                    correcteddata = sub1fimaging(cal2hdulist, sigma_bgmask, sigma_1fmask, splitamps)
                    if cal2hdulist['PRIMARY'].header['SUBARRAY'] == 'FULL':
                        cal2hdulist['SCI'].data[4:2044, 4:2044] = correcteddata
                    elif cal2hdulist['PRIMARY'].header['SUBARRAY'] == 'SUB256':
                        cal2hdulist['SCI'].data[:252, :252] = correcteddata
                    cal2hdulist.writeto(cal21overffile, overwrite=True)

        return

    def run_jhat(self):

        configFile = './Settings.ini'
        config = RawConfigParser()

        config.read(configFile)
        app_settings = config["diff_test"]

        if self.jhat_refcat is None:
            lvl3file = self.jhat_file

            sew = sewpy.SEW(
                sexpath="source-extractor",
                workdir="%s" % app_settings["IN_DIR"],
                params=["X_IMAGE", "Y_IMAGE", "FLUX_RADIUS(3)", "FLAGS", "XPEAK_WORLD", "YPEAK_WORLD", "CLASS_STAR"],
                config={"DETECT_MINAREA": 3, "PHOT_FLUXFRAC": "0.3, 0.5, 0.8", 'DETECT_THRESH': 10,
                        'BACKPHOTO_TYPE': 'LOCAL'})  # ,'FILTER_NAME':'gauss_2.0_5x5.conv'})

            temp = fits.open(lvl3file)
            temp[1].writeto('test.fits', overwrite=True)
            out = sew('test.fits')
            temp_wcs = wcs.WCS(temp[1])

            os.remove('test.fits')

            # radec = temp_wcs.pixel_to_world(out['table']['Y_IMAGE'],out['table']['X_IMAGE'])#
            # pdb.set_trace()
            # out['table'] = out['table'][out['table']['CLASS_STAR']>.01]
            out['table']['ra'] = out['table']['XPEAK_WORLD']  # [x.ra.value for x in radec]
            out['table']['dec'] = out['table']['YPEAK_WORLD']  # [x.dec.value for x in radec]#
            out['table']['x'] = out['table']['X_IMAGE'] - 1
            out['table']['y'] = out['table']['Y_IMAGE'] - 1
            out['table']['mag'] = space_phot.cal.calibrate_JWST_flux(out['table']['FLUX_RADIUS_1'].value, 0, temp_wcs)[
                2]
            out['table'].write('sewpy.txt', format='ascii', overwrite=True)
            ref3_catname = 'sewpy.txt'

            ref3_cat = Table.read(ref3_catname, format='ascii')
            # ref3_cat = ref3_cat[ref3_cat['mag']<23]
            # ref3_cat = ref3_cat[ref3_cat['mag']>16]
            # ref3_cat = ref3_cat[(ref3_cat['sharpness']>.55)&(ref3_cat['sharpness']<0.75)]

            cat_sc = SkyCoord(ref3_cat['ra'], ref3_cat['dec'], unit=u.deg)
            to_rem = []
            for i in range(len(cat_sc)):
                if len(np.where(cat_sc[i].separation(cat_sc).arcsec < 1)[0]) > 3:
                    to_rem.append(i)
                elif ref3_cat[i]['x'] < 100 or ref3_cat[i]['x'] > temp[1].data.shape[1] - 100 or \
                        ref3_cat[i]['y'] < 100 or ref3_cat[i]['y'] > temp[1].data.shape[0] - 100:
                    to_rem.append(i)
            ref3_cat['dmag'] = .01  # 2.5*np.log10(1.0+(comb['fluxerr']/comb['flux']))
            ref3_cat.remove_rows(to_rem)
            # create_pixregionfile(ref3_cat['ra'],ref3_cat['dec'],ref3_catname.replace('.txt','.reg'),'yellow',coords='icrs')
            ref3_cat.write(ref3_catname.replace('.txt', '_cut.txt'), overwrite=True, format='ascii')
            # create_pixregionfile(out['table']['XPEAK_WORLD'],out['table']['YPEAK_WORLD'],'sewpy_miri_2100.reg',coords='icrs',color='red',radius=[.5]*len(out['table']))
            # lvl3file = ['processed_data/jw05451-o001_t004_nircam_clear-f200w_i2d.fits']
            # jwst_phot = jwst_photclass()
            # jwst_phot.run_phot(imagename=lvl3file[0],photfilename='auto',overwrite=True)

            refcatname = 'sewpy_cut.txt'

        else:
            refcatname = self.jhat_refcat
        temp = Table.read(refcatname, format='ascii')

        create_pixregionfile(temp['ra'], temp['dec'], str(refcatname.replace(os.path.splitext(refcatname)[1], '.reg')),
                             'red', coords='icrs', radius=[.5] * len(temp))

        # df = pd.read_csv('/astro/armin/mike/auto-process2/files.csv')
        # all_files = df['files'].to_list()

        all_files = glob.glob('./Image2Output/*cal.fits')

        wcs_align = st_wcs_align()

        for f in all_files:
            if os.path.exists(f.replace('cal.fits', 'jhat.fits')):
                print('done')
                continue

            #             head = fits.getheader(f)

            #             ra = head['TARG_RA']
            #             dec = head['TARG_DEC']

            #             coord = SkyCoord(ra=ra,dec=dec, unit=u.deg)

            #             catalog_data = Catalogs.query_region(coord, catalog="HSC",radius=1,version=3)

            #             df_cat = catalog_data.to_pandas()
            #             #df_cat = df_cat.dropna()
            #             catalog_data = Table.from_pandas(df_cat)

            #             refcatname = 'cat.txt'
            #             catalog_data.write(refcatname, format='ascii',overwrite=True)
            # try:
            wcs_align.run_all(f,
                              telescope='jwst',
                              outrootdir='./Image2Output',
                              outsubdir='',
                              refcat_racol='ra',
                              refcat_deccol='dec',
                              refcat_magcol='mag',
                              refcat_magerrcol='dmag',
                              overwrite=True,
                              d2d_max=2,
                              # xshift=10,
                              # yshift=-15,
                              iterate_with_xyshifts=True,
                              use_dq=True,
                              verbose=True,
                              showplots=0,
                              saveplots=2,
                              savephottable=True,
                              refcatname=refcatname,
                              histocut_order='dxdy',
                              sharpness_lim=(0.1, 0.9),
                              roundness1_lim=(-0.9, 0.9),
                              SNR_min=3,
                              dmag_max=10,
                              objmag_lim=(14, 30),
                              use_sextractor=True,
                              sexpath="source-extractor",
                              sexworkdir="%s" % app_settings["IN_DIR"],
                              )
            # except:
            #  print("JHAT FAILED")#, MOVING OG FILE.")
            #  newf = f.replace('cal','jhat')
            #  shutil.copyfile(f, newf)
            # sys.exit()

        return

    def do_bsub(self):

        flist = glob.glob('Image2Output/*1overf.fits')

        for f in flist:
            hdu = fits.open(f)
            data = hdu[1].data

            bkg = self.interp_bkg(data)

            bsub = data - bkg

            outname = f.replace('1overf', 'bsub')

            hdu[1].data = bsub

            hdu.writeto(outname, overwrite=True)

            hdu.close()

        return

    def interp_bkg(self, data):

        m, n = data.shape

        bkg_h = np.zeros_like(data)
        bkg_v = np.zeros_like(data)

        for j in range(m):
            bkg_h[j, :] = np.nanmedian(data[j, :])

        for i in range(n):
            bkg_h[:, i] = np.nanmedian(data[:, i])

        bkg = np.average([bkg_h, bkg_v], axis=0)

        return bkg

    def save_output(self):

        if not os.path.exists('processed_data/'):
            os.mkdir('processed_data/')

        # self.outfile = glob.glob('Image3Output/*i2d.fits')[0]

        # shutil.copy(self.outfile, 'processed_data/')

        lvl2files = glob.glob('Image2Output/*1overf.fits')
        print(lvl2files)

        if not os.path.exists('image2data/'):
            os.mkdir('image2data/')

        for f in lvl2files:
            shutil.copy(f, 'image2data/')

        return

    def cleanup(self):

        shutil.rmtree('mastDownload/')
        shutil.rmtree('Image2Output/')
        # shutil.rmtree('Image3Output/')

        outliers = glob.glob('./jw*outlier_i2d.fits')

        for f in outliers:
            os.remove(f)

        crfs = glob.glob('./Image3Output/jw*crf.fits')

        for f in crfs:
            os.remove(f)

        meds = glob.glob('./Image3Output/jw*median.fits')

        for f in meds:
            os.remove(f)

        # os.remove('cat.txt')
        try:
            for f in glob.glob('rate_asn*.json'):
                os.remove(f)
        except:
            pass
        try:
            for f in glob.glob('cal_asn*.json'):
                os.remove(f)
        except:
            pass

        return

    def process(self):

        if True:
            obs = self.query_mast()

            # uncal_list = self.create_lvl1_asn()

        # self.run_detector1(uncal_list)

        # self.create_lvl2_asn()

        # self.run_image2()

        self.run_jhat()

        self.correct_1overf()

        # self.create_lvl3_asn()

        # self.run_image3()

        # self.save_output()

        # self.cleanup()

        return


if __name__ == "__main__":

    obslist = ['jw04793-o001_t001_nircam_clear-f150w']  # ,'jw03707-o004_t003_nircam_clear-f150w']
    # f = 'Proposal_IDs_5451.csv'
    # import pandas as pd
    # from astropy.table import Table
    # tab = Table.read(f,format='ascii')

    proc = AutoProcessNRC()
    proc.jhat_refcat = '/astro/armin/data/jwst/casA/sewpy_cut.txt'
    proc.start_level2 = True
    for obs in obslist:  # tab['obs_id']:
        print(obs)
        proc.obs_id = obs
        for ps in [60]:
            if ps == 30:
                proc.level3_ref = [
                    glob.glob('/astro/armin/data/jwst/casA/aligned_new2s/F200W*single_module_a_i2d.fits')[0],
                    glob.glob('/astro/armin/data/jwst/casA/aligned_new2s/F200W*single_module_b_i2d.fits')[0]]
            else:
                proc.level3_ref = [
                    glob.glob('/astro/armin/data/jwst/casA/aligned_new2s/F200W*single_module_a_60_i2d.fits')[0],
                    glob.glob('/astro/armin/data/jwst/casA/aligned_new2s/F200W*single_module_b_60_i2d.fits')[0]]
            proc.pixel_scale = ps
            proc.process()
