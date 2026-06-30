import sys
from jhat import st_wcs_align

def WCSAlignment(input_img, file_ext, lvl2_id, input_dir, output_dir, log_dir):


    file_log = '/'.join([log_dir, input_img]).replace('.fits','_1overf_skymatch.log')
    file_logcfg = '/'.join([log_dir, 'tmp', input_img]).replace('.fits','_1overf_skymatch.cfg')
    new_ext = file_ext.replace('.fits','_skymatch.fits')
    
    wcs_align = st_wcs_align()

    try:
        wcs_align.run_all(input_image, # file name of lvl2
            telescope='jwst',
            outrootdir=output_dir,
            outsubdir='',
            refcat_racol='ra',
            refcat_deccol='dec',
            refcat_magcol='mag',
            refcat_magerrcol='dmag',
            overwrite=True,
            d2d_max=2,
            #xshift=10,
            #yshift=-15,
            iterate_with_xyshifts=True,
            use_dq=True,
            verbose=True,
            showplots=0,
            saveplots=2,
            savephottable=True,
            refcatname=input_catalog, # input catalog -> ra dec
            histocut_order='dxdy',
            sharpness_lim=(0.1,0.9),
            roundness1_lim=(-0.9, 0.9),
            SNR_min= 3,
            dmag_max=10,
            objmag_lim =(14,30),
            use_sextractor=True)
    
    except Exception as e:
         print("JHAT FAILED")
         print(e)

    return





