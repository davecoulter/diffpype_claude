import sys

sys.path.append("/Users/mgriggio/diffpype/src/jwst_diff")
from image1overf import sub1fimaging
from astropy.io import fits

def oneoverf(input_img, file_ext, lvl2_id, input_dir, output_dir, log_dir, sigma_bgmask = 3.0, sigma_1fmask = 2.0, splitamps = True, usesegmask = True):

    # splitamps   Set to True only in a sparse field so each amplifier will be fit separately. 
    # usesegmask  Recommend set to True in most cases
    # input_img = jw*_cal (no extension, extension is in file_ext)

    new_ext = file_ext.replace('.fits','_1overf.fits')
    file_log = '/'.join([log_dir, input_img+new_ext.replace('.fits','.log')])

    with open(file_log, 'w') as log:
        sys.stdout = log
        sys.stderr = log

        file_in = '/'.join([input_dir, input_img+file_ext])
        file_out = '/'.join([output_dir, input_img+new_ext])
        

        try:
            print ('Running 1/f correction on {} to produce {}'.format(file_in,file_out))
            with fits.open(file_in) as cal2hdulist:
                if cal2hdulist['PRIMARY'].header['SUBARRAY']=='FULL' or cal2hdulist['PRIMARY'].header['SUBARRAY']=='SUB256':

                    correcteddata = sub1fimaging(cal2hdulist,sigma_bgmask,sigma_1fmask,splitamps,usesegmask)
                    if cal2hdulist['PRIMARY'].header['SUBARRAY']=='FULL':
                        cal2hdulist['SCI'].data[4:2044,4:2044] = correcteddata  
                    elif cal2hdulist['PRIMARY'].header['SUBARRAY']=='SUB256':
                        cal2hdulist['SCI'].data[:252,:252] = correcteddata
                    cal2hdulist.writeto(file_out, overwrite=True)
                    
        except Exception as e:

            return e
    
    return 0, lvl2_id, new_ext

