import sys
from jwst.pipeline import Image3Pipeline


def create_mosaic(lvl2_list, filename_out, input_dir, output_dir, log_dir, tile_params):
    
    file_log = '/'.join([log_dir, filename_out]).replace('.fits','.log')
    file_logcfg = '/'.join([log_dir, 'tmp', filename_out]).replace('.fits','.cfg')

    with open(file_logcfg, 'w') as file_handler:
        text = f'''
        [*]
        handler = file:{file_log}
        level = INFO'''
        file_handler.write(text)


    # with open(file_log, 'w') as log:
    #     sys.stdout = log
    #     sys.stderr = log

    # tile_shape: (npix_x, npix_y)
    CRPIX1, CRPIX2, CRVAL1, CRVAL2, pix_scale, rotation, tile_shape = tile_params

    pipe3 = Image3Pipeline()

    params = {
                'assign_mtwcs':         {'skip': True},
                'tweakreg':             {'skip': False, 'save_results': False},
                'outlier_detection':    {'skip': False, 'save_results': False},
                'source_catalog':       {'skip': True},
                'skymatch':             {'skip': False, 'skymethod': 'global+match', 'subtract': True, 'save_results': False}
            }
    
    params['resample'] = {  
                            'skip': False,
                            'pixfrac': 0.8,
                            'kernel': 'square',
                            'fillval': 'indef',
                            'weight_type': 'ivm',
                            'in_memory': True,
                            'save_results': True
                        }


    params['resample']['pixel_scale'] = pix_scale  
    params['resample']['rotation'] = rotation
    params['resample']['output_shape'] = (int(tile_shape[0]), int(tile_shape[1]))
    
    params['resample']['crpix'] = [CRPIX1, CRPIX2]
    params['resample']['crval'] = [CRVAL1, CRVAL2]

    try:
        pipe3.call(['/'.join([input_dir, lvl2_img]) for lvl2_img in lvl2_list], steps=params, output_dir=output_dir, output_file=filename_out, save_results=True, logcfg=f'{file_logcfg}')
    except Exception as e:
        return e

    return filename_out


