import sys
import os
from jwst.pipeline import Image3Pipeline

def subtract_background(input_img, file_ext, lvl2_id, input_dir, output_dir, log_dir):
    
    # input_img = jw*_cal
    new_ext = file_ext.replace('.fits','_skymatch.fits')
    file_log = '/'.join([log_dir, input_img+new_ext.replace('.fits','.log')])
    file_logcfg = '/'.join([log_dir, 'tmp', input_img+new_ext.replace('.fits','.cfg')])
    
    with open(file_logcfg, 'w') as file_handler:
        text = f'''
        [*]
        handler = file:{file_log}
        level = INFO'''
        file_handler.write(text)



    pipe3 = Image3Pipeline()
    
    # here we wanna run the skymatch step only
    params = {
                'assign_mtwcs':         {'skip': True},
                'tweakreg':             {'skip': True},
                'outlier_detection':    {'skip': True},
                'source_catalog':       {'skip': True},
                'resample':             {'skip': True}
            }

    params['skymatch'] = {
                            'skip': False,
                            'skymethod': 'local',
                            'subtract': True,
                            'skystat': 'median',
                            'usigma': 3,
                            'lsigma': 3,
                            'nclip': 5,
                            'save_results': True

                        }

    file_in = '/'.join([input_dir, input_img+file_ext])
    file_out = input_img+file_ext

    try:
        pipe3.call(file_in, steps=params, output_dir=output_dir, output_file=file_out, save_results=True, logcfg=f'{file_logcfg}')
    except Exception as e:
        return e

    with open(file_log, 'w') as log:
        sys.stdout = log
        sys.stderr = log

        try:
            os.rename('/'.join([output_dir, file_out.replace('_cal.fits','_0_skymatch.fits')]), '/'.join([output_dir, file_out.replace('.fits','_skymatch.fits')]))
        except Exception as e:
            return e        

    return 0, lvl2_id, new_ext










