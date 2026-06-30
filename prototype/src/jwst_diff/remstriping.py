import os
import shutil
from glob import glob
import argparse
import logging
from datetime import datetime
import numpy as np
from astropy.io import fits
from astropy.stats import sigma_clipped_stats, SigmaClip
from astropy.convolution import convolve, convolve_fft
from photutils.segmentation import detect_threshold, detect_sources
from photutils.background import Background2D, SExtractorBackground
from photutils.utils import circular_footprint
from photutils.segmentation import make_2dgaussian_kernel
from scipy.optimize import curve_fit
# jwst-related imports
from stdatamodels.jwst.datamodels import ImageModel, FlatModel, dqflags
from jwst.flatfield.flat_field import do_correction
from stdatamodels import util
import crds
# logging
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)
import concurrent.futures
import multiprocessing as mp

"""
Measure striping by collapsing image over rows and columns, using the
sigma-clipped median value to avoid source flux. 

The measurement/subtraction needs to be done along one axis at a time,
since the measurement along x will depend on what has been subtracted
from y.
"""

### from jwst/refpix/reference_pixels.py:
# NIR Reference section dictionaries are zero indexed and specify the values
# to be used in the following slice: (rowstart: rowstop, colstart:colstop)
# The 'stop' values are one more than the actual final row or column, in
# accordance with how Python slices work
NIR_reference_sections = {'A': {'top': (2044, 2048, 0, 512),
                                'bottom': (0, 4, 0, 512),
                                'side': (0, 2048, 0, 4),
                                'data': (0, 2048, 0, 512)},
                          'B': {'top': (2044, 2048, 512, 1024),
                                'bottom': (0, 4, 512, 1024),
                                'data': (0, 2048, 512, 1024)},
                          'C': {'top': (2044, 2048, 1024, 1536),
                                'bottom': (0, 4, 1024, 1536),
                                'data': (0, 2048, 1024, 1536)},
                          'D': {'top': (2044, 2048, 1536, 2048),
                                'bottom': (0, 4, 1536, 2048),
                                'side': (0, 2048, 2044, 2048),
                                'data': (0, 2048, 1536, 2048)}}


# taking the reference rows/columns into account
NIR_amps = {'A': {'data': (4, 2044, 4, 512)},
            'B': {'data': (4, 2044, 512, 1024)},
            'C': {'data': (4, 2044, 1024, 1536)},
            'D': {'data': (4, 2044, 1536, 2044)}
            }


def gaussian(x, a, mu, sig):
    return a * np.exp(-(x-mu)**2/(2*sig**2))


def fit_sky(data):
    """Fit distribution of sky fluxes with a Gaussian"""
    bins = np.arange(-0.5, 0.5, 0.001)
    h,b = np.histogram(data, bins=bins)
    bc = 0.5 * (b[1:] + b[:-1])
    binsize = b[1] - b[0]

    p0 = [10, bc[np.argmax(h)], 0.01]
    popt,pcov = curve_fit(gaussian, bc, h, p0=p0)

    return popt[1]


def generate_source_mask(data, mask, nsigma=2, bkg_rms=None, kernel_FWHM=3, dilate_radius=8):
    '''
    Generate source mask from data using photutils segmentation
    :param data: input sci image
    :param mask: mask of bad pixels from dq image
    :return: source mask
    '''
    data_copy = data.copy()
    data_copy[np.isnan(data_copy)] = 0.
    if kernel_FWHM == 3:
        kernel = make_2dgaussian_kernel(3.0, size=5)  # FWHM = 3.0
    else:
        kernel = make_2dgaussian_kernel(kernel_FWHM, size=int(2*kernel_FWHM-1))  # FWHM = 3.0
    convolved_data = convolve_fft(data_copy, kernel, allow_huge=True)
    if bkg_rms is None:
        threshold = detect_threshold(data_copy, nsigma=nsigma, mask=mask)  # default sigma_clip = SigmaClip(sigma=3.0, maxiters=10)
    else:
        threshold = nsigma*bkg_rms
    segment_img = detect_sources(convolved_data, threshold, npixels=15, mask=mask)
    footprint = circular_footprint(radius=dilate_radius)  # dilate the mask using a circular footprint with a radius=5 pixel
    try:
        source_mask = segment_img.make_source_mask(footprint=footprint)
    except AttributeError:
        source_mask = np.zeros_like(data_copy, dtype=np.int8).astype(bool)
    # mean, median, std = sigma_clipped_stats(data, sigma=3.0, mask=source_mask)
    return source_mask


def collapse_image(im, mask, dimension='y', sig=2.):
    """collapse an image along one dimension to check for striping.

    By default, collapse columns to show horizontal striping (collapsing
    along columns). Switch to vertical striping (collapsing along rows)
    with dimension='x' 

    Striping is measured as a sigma-clipped median of all unmasked pixels 
    in the row or column.

    Args:
        im (float array): image data array
        mask (bool array): image mask array, True where pixels should be 
            masked from the fit (where DQ>0, source flux has been masked, etc.)
        dimension (Optional [str]): specifies which dimension along which 
            to collapse the image. If 'y', collapses along columns to 
            measure horizontal striping. If 'x', collapses along rows to 
            measure vertical striping. Default is 'y'
        sig (Optional [float]): sigma to use in sigma clipping
    """
    # axis=1 results in array along y
    # axis=0 results in array along x

    if dimension == 'y':
#        collapsed = np.median(im, axis=1)
        res = sigma_clipped_stats(im, mask=mask, sigma=sig, cenfunc=np.median, maxiters=10,
                                        stdfunc=np.nanstd, axis=1)

    elif dimension == 'x':
#        collapsed = np.median(im, axis=0)
        res = sigma_clipped_stats(im, mask=mask, sigma=sig, cenfunc=np.median, maxiters=10,
                                        stdfunc=np.nanstd, axis=0)

    return res[1]
    

def measure_fullimage_striping(fitdata, mask):
    """Measures striping in countrate images using the full rows.

    Measures the horizontal & vertical striping present across the
    full image. The full image median will be used for amp-rows that
    are entirely or mostly masked out.

    Args:
        fitdata (float array): image data array for fitting
        mask (bool array): image mask array, True where pixels should be
            masked from the fit (where DQ>0, source flux has been masked, etc.)

    Returns:
        (horizontal_striping, vertical_striping):
    """

    # fit horizontal striping, collapsing along columns
    horizontal_striping = collapse_image(fitdata, mask, dimension='y')
    # remove horizontal striping, requires taking transpose of image
    temp_image = fitdata.T - horizontal_striping
    # transpose back
    temp_image2 = temp_image.T

    # fit vertical striping, collapsing along rows
    vertical_striping = collapse_image(temp_image2, mask, dimension='x')

    return horizontal_striping, vertical_striping


def measure_striping(image, thresh=None, apply_flat=True, mask_sources=True, save_patterns=False, save_original_rate=True, dilation_radius=None, nsigma=2):
    """Removes striping in .fits files before flat fielding.

    Measures and subtracts the horizontal & vertical striping present in 
    countrate images. The striping is most likely due to 1/f noise, and 
    the RefPixStep with odd_even_columns=True and use_side_ref_pixels=True
    does not fully remove the pattern, no matter what value is chosen for 
    side_smoothing_length. There is also residual vertical striping in NIRCam 
    images simulated with Mirage.

    Modifications:
    1. add source mask function to mask source fluxes before measuring strips
    2. change back pixels values in data array to 0 whose value=0 in error array

    Note: 
        The original rate image file is copied to *_orig.fits, and
        the rate image with the striping patterns removed is saved to 
        *_.fits, overwriting the input filename

    Args:
        image (str): image filename, including full relative path
        thresh (Optional [float]): fraction of masked amp-row pixels above
            which full row fit is used
        apply_flat (Optional [bool]): if True, identifies and applies the 
            corresponding flat field before measuring striping pattern. 
            Applying the flat first allows for a cleaner measure of the 
            striping, especially for the long wavelength detectors. 
            Default is True.
        mask_sources (Optional [bool]): If True, masks out sources in image
            before measuring the striping pattern so that source flux is 
            not included in the calculation of the sigma-clipped median.
            Now use photutils to mask sources.
            Default is True.
        save_patterns (Optional [bool]): if True, saves the horizontal and
            vertical striping patterns to files called *horiz.fits and
            *vert.fits, respectively
    """
    try:
        crds_context = os.environ['CRDS_CONTEXT']
    except KeyError:
        crds_context = crds.get_default_context()

    if thresh is None:
        thresh = 0.65

    model = ImageModel(image)
    log.info('Measuring image striping')
    log.info('Working on %s'%image)

    # check that striping hasn't already been removed
    '''
    for entry in model.history:
        for k,v in entry.items():
            if 'Removed horizontal,vertical striping; remstriping.py' in v:
                print('%s already cleaned. Skipping!'%os.path.basename(image))
                return
    '''
    
    # apply the flat to get a cleaner meausurement of the striping
    if apply_flat:
        log.info('Applying flat for cleaner measurement of striping patterns')
        # pull flat from CRDS using the current context
        crds_dict = {'INSTRUME':'NIRCAM', 
                     'DETECTOR':model.meta.instrument.detector, 
                     'FILTER':model.meta.instrument.filter, 
                     'PUPIL':model.meta.instrument.pupil, 
                     'DATE-OBS':model.meta.observation.date,
                     'TIME-OBS':model.meta.observation.time}
        flats = crds.getreferences(crds_dict, reftypes=['flat'], 
                                   context=crds_context)
        # if the CRDS loopup fails, should return a CrdsLookupError, but 
        # just in case:
        try:
            flatfile = flats['flat']
        except KeyError:
            log.error('Flat was not found in CRDS with the parameters: {}'.format(crds_dict))
            exit()

        log.info('Using flat: %s'%(os.path.basename(flatfile)))
        with FlatModel(flatfile) as flat:
            # use the JWST Calibration Pipeline flat fielding Step 
            model,applied_flat = do_correction(model, flat)
            
    # construct mask for median calculation
    mask = np.zeros(model.data.shape, dtype=bool)
    mask[model.dq%2 == 1] = True  # contain DO_NOT_USE
    
    # mask out sources
    if mask_sources:
        log.info('Using photuils to mask out source flux')

        if 'long' in image:
            dilate_radius = 5
        else:
            dilate_radius = 10
            # dilate_radius = 5
            # nsigma = 2
        if dilation_radius is not None:
            dilate_radius = dilation_radius

        # first run
        source_mask = generate_source_mask(model.data, mask, nsigma=nsigma, dilate_radius=dilate_radius)
        # measure the pedestal in the unmasked parts of the image
        log.info('Measuring the pedestal in the image')
        pedestal_data = model.data[~(mask|source_mask)]
        pedestal_data = pedestal_data.flatten()
        median_image = sigma_clipped_stats(pedestal_data, sigma=3, maxiters=10)[1]
        log.info('Image median (unmasked and DQ==0): %f' % (median_image))
        try:
            pedestal = fit_sky(pedestal_data)
        except RuntimeError as e:
            log.error("Can't fit sky, using median value instead")
            pedestal = median_image
        else:
            log.info('Fit pedestal: %f' % pedestal)
        # subtract a constant sky
        model.data -= pedestal
        # print(pedestal)
        # print(sigma_clipped_stats(model.data[~(mask|source_mask)], sigma=3, maxiters=10))

        source_mask = generate_source_mask(model.data, mask, nsigma=nsigma, dilate_radius=dilate_radius)
        # fits.writeto('test_bp_mask.fits',
        #              (mask).astype(np.int16), overwrite=True)
        # fits.writeto('test_source_msk.fits',
        #              (source_mask).astype(np.int16), overwrite=True)
        # subtract 2d bkg for better source detection since LW images have complicated bkg
        # bkg_estimator1 = SExtractorBackground()  # default
        # bkg1 = Background2D(model.data, (bkg_boxsize, bkg_boxsize), mask=source_mask|mask, bkg_estimator=bkg_estimator1, exclude_percentile=30)
        #
        # # third run
        # source_mask = generate_source_mask(model.data-bkg1.background, mask, bkg_rms=bkg1.background_rms, nsigma=nsigma, dilate_radius=dilate_radius)

        # source_mask_fltr = (source_mask == True)
        # mask[source_mask_fltr] = True
        mask[source_mask] = True

        fits.writeto(image.replace('.fits', '_source_mask.fits'),
                     (source_mask).astype(np.int8), overwrite=True)
    else:
        pedestal = 0.

    # subtract off pedestal to make it easier to fit 
    # model.data -= pedestal

    # measure full pattern across image
    full_horizontal, vertical_striping = measure_fullimage_striping(model.data,
                                                                    mask)

    horizontal_striping = np.zeros(model.data.shape, dtype=np.float32)
    vertical_striping = np.zeros(model.data.shape, dtype=np.float32)

    # keep track of number of number of times the number of masked pixels
    # in an amp-row exceeds thersh and a full-row median is used instead
    ampcounts = []
    for amp in ['A','B','C','D']:
        ampcount = 0
        if model.meta.subarray.name == 'FULL':
            rowstart, rowstop, colstart, colstop = NIR_amps[amp]['data']
            ampdata = model.data[:, colstart:colstop]
            ampmask = mask[:, colstart:colstop]
            # fit horizontal striping in amp, collapsing along columns
            hstriping_amp = collapse_image(ampdata, ampmask, dimension='y')
            # check that at least 1/4 of pixels in each row are unmasked
            nmask = np.sum(ampmask, axis=1)
            for i,row in enumerate(ampmask):
                if nmask[i] > (ampmask.shape[1]*thresh):
                    # use median from full row
                    horizontal_striping[i,colstart:colstop] = full_horizontal[i]
                    ampcount += 1
                else:
                    # use the amp fit
                    horizontal_striping[i,colstart:colstop] = hstriping_amp[i]
            ampcounts.append('%s-%i'%(amp,ampcount))
        else:
            for i,row in enumerate(mask):
                horizontal_striping[i, :] = full_horizontal[i]

    if model.meta.subarray.name == 'FULL':
        ampinfo = ', '.join(ampcounts)
        log.info('%s, full row medians used: %s /%i'%(os.path.basename(image),
                                                      ampinfo, rowstop-rowstart))

    # to avoid NaNs in the horizontal striping, replace NaNs with 0
    horizontal_striping[np.isnan(horizontal_striping)] = 0.

    # remove horizontal striping
    temp_sub = model.data - horizontal_striping

    # fit vertical striping, collapsing along rows
    vstriping = collapse_image(temp_sub, mask, dimension='x')
    vertical_striping[:,:] = vstriping

    # to avoid NaNs in the vertical striping, replace NaNs with 0
    vertical_striping[np.isnan(vertical_striping)] = 0.

    model.close()
    
    # copy image
    if save_original_rate:
        log.info('Copying input to %s'%image.replace('.fits', '_orig.fits'))
        shutil.copy2(image, image.replace('.fits', '_orig.fits'))

    # remove striping from science image
    with ImageModel(image) as immodel:
        sci = immodel.data
        sci -= pedestal # minus pedestal

        # bkg = Background2D(sci, (bkg_boxsize, bkg_boxsize), mask=mask,
        #                    exclude_percentile=30)
        # sci -= bkg.background # minus background

        # save horizontal and vertical patterns
        if save_patterns:
            temp = vertical_striping + horizontal_striping + pedestal #+ bkg.background
            # fits.writeto(image.replace('.fits', '_horiz.fits'),
            #              horizontal_striping, overwrite=True)
            # fits.writeto(image.replace('.fits', '_vert.fits'),
            #              vertical_striping, overwrite=True)
            fits.writeto(image.replace('.fits', '_bkg+strip.fits'),
                         temp.astype(np.float32), overwrite=True)

        temp_sci = sci - horizontal_striping
        # transpose back
        outsci = temp_sci - vertical_striping
        # replace NaNs with zeros and update DQ array
        # the image has NaNs where an entire row/column has been masked out
        # so no median could be calculated.
        # All of the NaNs on LW detectors and most of them on SW detectors
        # are the reference pixels around the image edges. But there is one
        # additional row on some SW detectors
#        refpixflag = dqflags.pixel['REFERENCE_PIXEL']
#        wref = np.bitwise_and(immodel.dq, refpixflag)
#        outsci[np.where(wref)] = 0
        wnan = np.isnan(outsci)
        bpflag = dqflags.pixel['DO_NOT_USE']
        outsci[wnan] = np.nan ## 0 in original file
        immodel.dq[wnan] = np.bitwise_or(immodel.dq[wnan], bpflag)
        # change pixels which are originally 0 back to nan, those are modified by striping
        err_zero_fltr = (immodel.err==0)|(immodel.data==0)
        outsci[err_zero_fltr] = np.nan
        # immodel.err[err_zero_fltr] = np.inf
        immodel.var_poisson[err_zero_fltr] = np.inf
        immodel.var_rnoise[err_zero_fltr] = np.inf

        # write output
        immodel.data = outsci
        # add history entry
        time = datetime.now()
        stepdescription = 'Removed vertical and horizontal striping; remstriping.py %s'%time.strftime('%Y-%m-%d %H:%M:%S')
        # writing to file doesn't save the time stamp or software dictionary
        # with the History object, but left here for completeness
        software_dict = {'name':'remstriping.py',
                         'author':'Micaela Bagley',
                         'version':'1.0',
                         'modifier': 'David Allen Coulter'}
        substr = util.create_history_entry(stepdescription,
                                              software=software_dict)
        immodel.history.append(substr)
        log.info('Saving cleaned image to %s'%image)
        immodel.save(image)


def main():
    parser = argparse.ArgumentParser(description=
        'Measure and remove horizontal/vertical striping from rate images')
    parser.add_argument('--output_dir', type=str, default='calibrated',
        help='Output directory for cleaned images. Default is calibrated.')
    parser.add_argument('--runone', type=str,
        help='Filename of single file to clean. If set, overrides the runall argument')
    parser.add_argument('--runall', action='store_true',
        help='Set to run all *.fits images in the output_dir directory.')
    parser.add_argument('--apply_flat', action='store_true',
        help='Set to apply the flat field before measuring striping pattern.')
    parser.add_argument('--mask_sources', action='store_true',
        help='Set to mask out sources in image before measuring striping pattern.')
    parser.add_argument('--threshold', type=float, default=0.01,
        help='Threshold (in ADU/s) to use in the seed images when identifying pixels to mask. Default is 0.01')

    args = parser.parse_args()

    if args.runone:
        image = os.path.join(args.output_dir, args.runone)
        measure_striping(image, apply_flat=args.apply_flat, mask_sources=args.mask_sources)

    elif args.runall:
        rates = glob(os.path.join(args.output_dir, '*_rate.fits'))
        rates.sort()
        with concurrent.futures.ProcessPoolExecutor(mp_context=mp.get_context('fork'), max_workers=32) as ex:
            [ex.submit(measure_striping, rate, apply_flat=args.apply_flat, mask_sources=args.mask_sources) for rate in rates]
        # for rate in rates:
        #     measure_striping(rate, apply_flat=args.apply_flat, mask_sources=args.mask_sources)

    else:
        print('Specify either --runone with a single input filename or --runall to process all *_.fits files')


if __name__ == '__main__':
    main()

    
