from astropy.coordinates import SkyCoord
from astropy.io import fits
from astropy.wcs import WCS
from astropy.time import Time
import astropy.units as u
from dominate import document
from dominate.tags import *
import json
from matplotlib import pyplot as plt
import numpy as np
import os
import pandas as pd
from astropy.table import Table
from matplotlib.patches import Circle
from astropy.visualization.mpl_normalize import simple_norm
from astropy.visualization import make_lupton_rgb
import time
import astropy

# Dave Debug
import pdb;


def get_config(config_file='config.json'):
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
    except FileNotFoundError:
        print('Could not open config file.')
        config = False
        pass

    return config


def getMJD():
    """ Returns the current date+time in MJD. """

    return Time.now().mjd


class Logging():

    def __init__(self):
        self.log_name = 'log.txt'
        return

    def log(self, message):
        f = open(self.log_name, 'a')

        logtime = str(Time.now())

        f.write(logtime + ': ' + message + '\n')

        f.close()

        return


def create_det_fig_par(args):
    index, snid, _self, sources, phot_table = args
    phot_tbl = phot_table[phot_table['snid'] == snid]
    # if snid=='5058_5058_315':
    #    print(phot_tbl)

    # phot_tbl = phot_tbl[np.isfinite(phot_tbl['mag'])]
    if len(phot_tbl) == 0:
        print('no data')
        return
    ra, dec = sources['ra'][index], sources['dec'][index]

    # filts = ['F115W','F150W','F277W','F444W']

    # sci_cols = ['F115W_sci_file','F150W_sci_file','F277W_sci_file','F444W_sci_file']
    # ref_cols = ['F115W_ref_file','F150W_ref_file','F277W_ref_file','F444W_ref_file']
    # diff_cols = ['F115W_diff_file','F150W_diff_file','F277W_diff_file','F444W_diff_file']

    # filts = ['f115w','f150w','f277w','f444w']
    phot_tbl.sort('filter')

    filts = [x for x in phot_tbl['filter']]

    nfilts = len(filts)
    if nfilts == 1:
        nfilts = 2
        filts = ['F110W', 'F125W']
        # return

    outname = '{image_path}{field_name}_source_mjd{:.3f}_{:.5f}_{:.5f}.png'.format(
        float(np.median(phot_tbl['mjd'])), float(ra), float(dec), image_path=_self.image_path,
        field_name=_self.field_name)
    # print(outname)
    # if '150.14299_2.21907.png' not in outname:
    #    return os.path.basename(outname)
    # fig, axes = plt.subplots(3, nfilts, figsize=(10,8), sharex=False, sharey=False)
    fig, axes = plt.subplots(3, nfilts, figsize=(2 * nfilts, 8), sharex=False, sharey=False)
    # filts = ['f277w','f444w','f115w','f150w']
    max_snr = np.argmax(phot_tbl['flux'] / phot_tbl['fluxerr'])
    ngood = 0
    for idx, filt in enumerate(filts):

        # diff_stamp, dvmin, dvmax = self.get_stamp(ra, dec, row[diff_cols[idx]])
        # sci_stamp, vmin, vmax = self.get_stamp(ra, dec, row[sci_cols[idx]])
        # ref_stamp, _, _ = self.get_stamp(ra, dec, row[ref_cols[idx]])

        # diff_stamp, dvmin, dvmax = self.get_stamp(ra, dec, diff_cols[idx])
        # sci_stamp, vmin, vmax = self.get_stamp(ra, dec, sci_cols[idx])
        # ref_stamp, _, _ = self.get_stamp(ra, dec, ref_cols[idx])
        # pdb.set_trace()
        # diff_stamp, dvmin, dvmax,dxpos,dypos = self.get_stamp(ra, dec, self.diff_dict[filt][0])
        # sci_stamp, vmin, vmax,sxpos,sypos = self.get_stamp(ra, dec, self.sci_dict[filt][0])
        # ref_stamp, rmin, rmax,rxpos,rypos = self.get_stamp(ra, dec, self.ref_dict[filt][0])

        diff_stamp, dvmin, dvmax, dxpos, dypos = _self.get_stamp(ra, dec, phot_tbl[idx]['diffim'])
        sci_stamp, vmin, vmax, sxpos, sypos = _self.get_stamp(ra, dec, phot_tbl[idx]['sciim'])
        ref_stamp, rmin, rmax, rxpos, rypos = _self.get_stamp(ra, dec, phot_tbl[idx]['refim'])
        if np.all(np.isnan(diff_stamp.ravel())) or \
                np.all(np.isnan(sci_stamp.ravel())) or \
                np.all(np.isnan(ref_stamp.ravel())):
            return

        ref_date = os.path.basename(phot_tbl[idx]['refim']).split("_")[1]
        sci_date = os.path.basename(phot_tbl[idx]['sciim']).split("_")[1]
        if idx == max_snr:
            snr_text = '**'
        else:
            snr_text = ''
        if phot_tbl[idx]['flux'] / phot_tbl['fluxerr'][idx] > 3:
            patch_color = 'g'
        else:
            patch_color = 'r'

        axes[0, idx].set_title(snr_text + filt.upper() + snr_text + '\n' + sci_date + '-' + ref_date, fontsize=12)

        # axes[0,idx].imshow(diff_stamp, vmin=dvmin, vmax=dvmax, origin='lower')
        axes[0, idx].imshow(diff_stamp, norm=simple_norm(diff_stamp, stretch='linear', power=1.5,
                                                         min_cut=dvmin, max_cut=dvmax), origin='lower',
                            cmap='gray')  # optional min_cut, max_cut

        axes[0, idx].add_patch(Circle((dxpos - int(dxpos) + diff_stamp.shape[0] / 2,
                                       dypos - int(dypos) + diff_stamp.shape[1] / 2), diff_stamp.shape[0] / 10,
                                      facecolor=None, edgecolor=patch_color, alpha=1, fill=False))

        axes[1, idx].set_title(snr_text + 'SCI: ' + sci_date + snr_text, fontsize=15)
        # axes[1,idx].imshow(sci_stamp, vmin=vmin, vmax=vmax, origin='lower')
        axes[1, idx].imshow(sci_stamp, norm=simple_norm(sci_stamp, stretch='power', power=2,
                                                        min_cut=vmin, max_cut=vmax), origin='lower', cmap='gray')
        axes[1, idx].add_patch(Circle((sxpos - int(sxpos) + sci_stamp.shape[0] / 2,
                                       sypos - int(sypos) + sci_stamp.shape[1] / 2), sci_stamp.shape[0] / 10,
                                      facecolor=None, edgecolor=patch_color, alpha=1, fill=False))

        axes[2, idx].set_title(snr_text + 'REF: ' + ref_date + snr_text, fontsize=15)
        # axes[2,idx].imshow(ref_stamp, vmin=vmin, vmax=vmax, origin='lower')
        axes[2, idx].imshow(ref_stamp, norm=simple_norm(ref_stamp, stretch='power', power=2,
                                                        min_cut=rmin, max_cut=rmax), origin='lower', cmap='gray')
        axes[2, idx].add_patch(Circle((rxpos - int(rxpos) + ref_stamp.shape[0] / 2,
                                       rypos - int(rypos) + ref_stamp.shape[1] / 2), ref_stamp.shape[0] / 10,
                                      facecolor=None, edgecolor='r', alpha=1, fill=False))

        sciflux = 10 ** (-.4 * (phot_tbl[idx][filt + '_mag_sci'] - phot_tbl[idx]['zp']))
        refflux = 10 ** (-.4 * (phot_tbl[idx][filt + '_mag_ref'] - phot_tbl[idx]['zp']))
        pred_mag = -2.5 * np.log10(sciflux - refflux) + phot_tbl[idx]['zp']
        if patch_color == 'g' and not np.isnan(pred_mag) and \
                np.abs(phot_tbl[idx]['mag'] - pred_mag) / phot_tbl[idx]['magerr'] < 3:
            ngood += 1
        axes[0, idx].annotate('%.1f±%.2f' % (phot_tbl[idx]['mag'], phot_tbl[idx]['magerr']),
                              (.03, .9), xycoords='axes fraction', color='cyan', fontsize=14)
        axes[0, idx].annotate('Forced: %.1f' % (pred_mag),
                              (.03, .8), xycoords='axes fraction', color='cyan', fontsize=14)
        axes[1, idx].annotate('%.1f±%.2f' % (phot_tbl[idx][filt + '_mag_sci'], phot_tbl[idx][filt + '_magerr_sci']),
                              (.03, .9), xycoords='axes fraction', color='cyan', fontsize=14)
        axes[2, idx].annotate('%.1f±%.2f' % (phot_tbl[idx][filt + '_mag_ref'], phot_tbl[idx][filt + '_magerr_ref']),
                              (.03, .9), xycoords='axes fraction', color='cyan', fontsize=14)

        for n in range(3):
            axes[n, idx].tick_params(
                axis='x',  # changes apply to the x-axis
                which='both',  # both major and minor ticks are affected
                bottom=False,  # ticks along the bottom edge are off
                top=False,  # ticks along the top edge are off
                labelbottom=False)  # labels along the bottom edge are off
            axes[n, idx].tick_params(
                axis='y',  # changes apply to the x-axis
                which='both',  # both major and minor ticks are affected
                bottom=False,  # ticks along the bottom edge are off
                top=False,  # ticks along the top edge are off
                labelbottom=False,
                labelleft=False,
                left=False)  # labels along the bottom edge are off

        # pdb.set_trace()
    plt.tight_layout()
    # plt.savefig('test')
    # pdb.set_trace()
    if ngood >= 1:
        plt.savefig(outname)
    else:
        plt.close()
        return

    plt.close()

    # return outname

    # Only return the base file name
    return os.path.basename(outname), snid


class CandidateVisualizer():
    """
    This class provides a method to create an html view of each source in a
    list of candidate detections. It will create a figure showing the location
    in each filter in the diff, sci, and ref images, and an SED plot.

    Note 11/13/23:
    This is currently set-up specifically for the COSMOS-Webb data and filters.
    It will need to be generalized in the future.

    ==============================
    Usage:
    --------
    from utils import CandidateVisualizer

    ...

    det_file = "<>/<>/example.csv"

    cv = CandidateVisualizer()
    cv.create_html_file(det_file)
    ===============================

    """

    def __init__(self, field_name,  # sci_dict, ref_dict, diff_dict,
                 html_base_dir='html/',
                 html_root="https://www.stsci.edu/~tsst/cosmos_sniff", overwrite=False):
        self.html_dir = html_base_dir
        if not os.path.exists(self.html_dir):
            os.mkdir(self.html_dir)
        elif not overwrite:
            raise RuntimeError('Your CV directory already exists but overwrite is False.')

        self.image_dir_name = "images"
        self.image_path = '{html_dir}/{image_dir_name}/'.format(
            html_dir=self.html_dir,
            image_dir_name=self.image_dir_name)

        if not os.path.exists(self.image_path):
            os.mkdir(self.image_path)

        self.plot_SEDs = False

        self.field_name = field_name
        # Each dictionary is keyed by the filter name, with the value == to the file
        # self.sci_dict = sci_dict
        # self.ref_dict = ref_dict
        # self.diff_dict = diff_dict
        self.html_root = html_root
        return

    def create_det_fig(self, row, ra, dec, phot_tbl):

        # filts = ['F115W','F150W','F277W','F444W']

        # sci_cols = ['F115W_sci_file','F150W_sci_file','F277W_sci_file','F444W_sci_file']
        # ref_cols = ['F115W_ref_file','F150W_ref_file','F277W_ref_file','F444W_ref_file']
        # diff_cols = ['F115W_diff_file','F150W_diff_file','F277W_diff_file','F444W_diff_file']

        # filts = ['f115w','f150w','f277w','f444w']
        phot_tbl.sort('filter')

        filts = [x.lower() for x in phot_tbl['filter']]
        # sci_cols = [
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f115w.ut20230514.01837003001_1.fits',
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f150w.ut20230514.01837003001_1.fits',
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f277w.ut20230514.01837003001_1.fits',
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f444w.ut20230514.01837003001_1.fits'
        # ]

        # ref_cols = [
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f115w.ut20230101.01837004001_1.fits',
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f150w.ut20230101.01837004002_1.fits',
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f277w.ut20230101.01837004001_1.fits',
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f444w.ut20230101.01837004002_1.fits'
        # ]

        # diff_cols = [
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f115w.ut20230514.01837003001_1_f115w.ut20230101.01837004001_1.diff.fits',
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f150w.ut20230514.01837003001_1_f150w.ut20230101.01837004002_1.diff.fits',
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f277w.ut20230514.01837003001_1_f277w.ut20230101.01837004001_1.diff.fits',
        #     '/astro/armin/Dave/JOUST/joust_results/p20.f444w.ut20230514.01837003001_1_f444w.ut20230101.01837004002_1.diff.fits'
        # ]

        nfilts = len(filts)

        outname = '{image_path}{field_name}_source_mjd{:.3f}_{:.5f}_{:.5f}.png'.format(
            float(np.median(phot_tbl['mjd'])), float(ra), float(dec), image_path=self.image_path,
            field_name=self.field_name)
        # print(outname)
        # if '150.14299_2.21907.png' not in outname:
        #    return os.path.basename(outname)
        # fig, axes = plt.subplots(3, nfilts, figsize=(10,8), sharex=False, sharey=False)
        fig, axes = plt.subplots(3, nfilts, figsize=(2 * nfilts, 8), sharex=False, sharey=False)
        # filts = ['f277w','f444w','f115w','f150w']
        max_snr = np.argmax(phot_tbl['flux'] / phot_tbl['fluxerr'])
        for idx, filt in enumerate(filts):

            # diff_stamp, dvmin, dvmax = self.get_stamp(ra, dec, row[diff_cols[idx]])
            # sci_stamp, vmin, vmax = self.get_stamp(ra, dec, row[sci_cols[idx]])
            # ref_stamp, _, _ = self.get_stamp(ra, dec, row[ref_cols[idx]])

            # diff_stamp, dvmin, dvmax = self.get_stamp(ra, dec, diff_cols[idx])
            # sci_stamp, vmin, vmax = self.get_stamp(ra, dec, sci_cols[idx])
            # ref_stamp, _, _ = self.get_stamp(ra, dec, ref_cols[idx])
            # pdb.set_trace()
            # diff_stamp, dvmin, dvmax,dxpos,dypos = self.get_stamp(ra, dec, self.diff_dict[filt][0])
            # sci_stamp, vmin, vmax,sxpos,sypos = self.get_stamp(ra, dec, self.sci_dict[filt][0])
            # ref_stamp, rmin, rmax,rxpos,rypos = self.get_stamp(ra, dec, self.ref_dict[filt][0])
            diff_stamp, dvmin, dvmax, dxpos, dypos = self.get_stamp(ra, dec, phot_tbl[idx]['diffim'])
            sci_stamp, vmin, vmax, sxpos, sypos = self.get_stamp(ra, dec, phot_tbl[idx]['sciim'])
            ref_stamp, rmin, rmax, rxpos, rypos = self.get_stamp(ra, dec, phot_tbl[idx]['refim'])

            ref_date = os.path.basename(phot_tbl[idx]['diffim']).split(".")[5][2:]
            sci_date = os.path.basename(phot_tbl[idx]['diffim']).split(".")[2][2:]
            if idx == max_snr:
                snr_text = '**'
            else:
                snr_text = ''
            if phot_tbl[idx]['flux'] / phot_tbl['fluxerr'][idx] > 3:
                patch_color = 'g'
            else:
                patch_color = 'r'

            axes[0, idx].set_title(snr_text + filt.upper() + snr_text + '\n' + sci_date + '-' + ref_date, fontsize=12)
            # axes[0,idx].imshow(diff_stamp, vmin=dvmin, vmax=dvmax, origin='lower')
            axes[0, idx].imshow(diff_stamp, norm=simple_norm(diff_stamp, stretch='linear', power=1.5,
                                                             min_cut=dvmin, max_cut=dvmax), origin='lower',
                                cmap='gray')  # optional min_cut, max_cut

            axes[0, idx].add_patch(Circle((dxpos - int(dxpos) + diff_stamp.shape[0] / 2,
                                           dypos - int(dypos) + diff_stamp.shape[1] / 2), diff_stamp.shape[0] / 10,
                                          facecolor=None, edgecolor=patch_color, alpha=1, fill=False))

            axes[1, idx].set_title(snr_text + 'SCI: ' + sci_date + snr_text, fontsize=15)
            # axes[1,idx].imshow(sci_stamp, vmin=vmin, vmax=vmax, origin='lower')
            axes[1, idx].imshow(sci_stamp, norm=simple_norm(sci_stamp, stretch='power', power=2,
                                                            min_cut=vmin, max_cut=vmax), origin='lower', cmap='gray')
            axes[1, idx].add_patch(Circle((sxpos - int(sxpos) + sci_stamp.shape[0] / 2,
                                           sypos - int(sypos) + sci_stamp.shape[1] / 2), sci_stamp.shape[0] / 10,
                                          facecolor=None, edgecolor=patch_color, alpha=1, fill=False))

            axes[2, idx].set_title(snr_text + 'REF: ' + ref_date + snr_text, fontsize=15)
            # axes[2,idx].imshow(ref_stamp, vmin=vmin, vmax=vmax, origin='lower')
            axes[2, idx].imshow(ref_stamp, norm=simple_norm(ref_stamp, stretch='power', power=2,
                                                            min_cut=rmin, max_cut=rmax), origin='lower', cmap='gray')
            axes[2, idx].add_patch(Circle((rxpos - int(rxpos) + ref_stamp.shape[0] / 2,
                                           rypos - int(rypos) + ref_stamp.shape[1] / 2), ref_stamp.shape[0] / 10,
                                          facecolor=None, edgecolor='r', alpha=1, fill=False))

            sciflux = 10 ** (-.4 * (phot_tbl[idx][filt + '_mag_sci'] - phot_tbl[idx]['zp']))
            refflux = 10 ** (-.4 * (phot_tbl[idx][filt + '_mag_ref'] - phot_tbl[idx]['zp']))
            pred_mag = -2.5 * np.log10(sciflux - refflux) + phot_tbl[idx]['zp']
            axes[0, idx].annotate('%.1f±%.2f' % (phot_tbl[idx]['mag'], phot_tbl[idx]['magerr']),
                                  (.03, .9), xycoords='axes fraction', color='cyan', fontsize=14)
            axes[0, idx].annotate('Forced: %.1f' % (pred_mag),
                                  (.03, .8), xycoords='axes fraction', color='cyan', fontsize=14)
            axes[1, idx].annotate('%.1f±%.2f' % (phot_tbl[idx][filt + '_mag_sci'], phot_tbl[idx][filt + '_magerr_sci']),
                                  (.03, .9), xycoords='axes fraction', color='cyan', fontsize=14)
            axes[2, idx].annotate('%.1f±%.2f' % (phot_tbl[idx][filt + '_mag_ref'], phot_tbl[idx][filt + '_magerr_ref']),
                                  (.03, .9), xycoords='axes fraction', color='cyan', fontsize=14)

            for n in range(3):
                axes[n, idx].tick_params(
                    axis='x',  # changes apply to the x-axis
                    which='both',  # both major and minor ticks are affected
                    bottom=False,  # ticks along the bottom edge are off
                    top=False,  # ticks along the top edge are off
                    labelbottom=False)  # labels along the bottom edge are off
                axes[n, idx].tick_params(
                    axis='y',  # changes apply to the x-axis
                    which='both',  # both major and minor ticks are affected
                    bottom=False,  # ticks along the bottom edge are off
                    top=False,  # ticks along the top edge are off
                    labelbottom=False,
                    labelleft=False,
                    left=False)  # labels along the bottom edge are off

            # pdb.set_trace()
        plt.tight_layout()
        # plt.savefig('test')
        # pdb.set_trace()

        plt.savefig(outname)
        plt.close()

        # return outname

        # Only return the base file name
        return os.path.basename(outname)

    def create_sed_fig(self, phot_tbl, ra, dec):

        outname = '{image_path}{field_name}_source_mjd{:.3f}_{:.5f}_{:.5f}_sed.png'.format(
            Time.now().mjd, float(ra), float(dec), image_path=self.image_path, field_name=self.field_name)

        filts = ['F115W', 'F150W', 'F277W', 'F444W']
        waves = [1.15, 1.5, 2.77, 4.44]
        # mags = [row['f115w_mag'], row['f150w_mag'], row['f277w_mag'], row['f444w_mag']]
        # magerrs = [row['f115w_magerr'], row['f150w_magerr'], row['f277w_magerr'], row['f444w_magerr']]

        mags = [
            phot_tbl[phot_tbl['filter'] == 'F115W']['mag'][0],
            phot_tbl[phot_tbl['filter'] == 'F150W']['mag'][0],
            phot_tbl[phot_tbl['filter'] == 'F277W']['mag'][0],
            phot_tbl[phot_tbl['filter'] == 'F444W']['mag'][0]
        ]
        magerrs = [
            phot_tbl[phot_tbl['filter'] == 'F115W']['magerr'][0],
            phot_tbl[phot_tbl['filter'] == 'F150W']['magerr'][0],
            phot_tbl[phot_tbl['filter'] == 'F277W']['magerr'][0],
            phot_tbl[phot_tbl['filter'] == 'F444W']['magerr'][0]
        ]

        # Bug in Matplotlib Errorbar if all error values are nan:
        # https://github.com/matplotlib/matplotlib/issues/24818
        cleaned_magerrs = [0.0 if np.isnan(m) else m for m in magerrs]

        positive_waves = []
        positive_mags = []
        positive_magerrs = []
        # Toss out negative magnitudes?
        for i, m in enumerate(mags):
            if m >= 0.0:
                positive_mags.append(m)
                positive_magerrs.append(cleaned_magerrs[i])
                positive_waves.append(waves[i])

        # plt.errorbar(x=waves,y=mags,yerr=cleaned_magerrs)
        plt.errorbar(x=positive_waves, y=positive_mags, yerr=positive_magerrs, linestyle="None")
        plt.gca().invert_yaxis()

        plt.xlabel(r'$\lambda (\mu m)$', fontsize=15)
        plt.ylabel('AB Magnitude', fontsize=15)
        plt.title('source_mjd{:.3f}_{:.5f}_{:.5f}_sed'.format(Time.now().mjd, float(ra), float(dec)), fontsize=15)

        plt.savefig(outname)
        plt.close()

        # return outname

        # Only return the base file name
        return os.path.basename(outname)

    def get_stamp(self, ra, dec, f):

        import astropy.units as u

        hdu = fits.open(f)

        if 'diff' in f:
            wcs_ext = 0
        else:
            wcs_ext = 1

        head = hdu[0].header
        # wcs = WCS(head)
        wcs = WCS(hdu[0])

        data = hdu[0].data

        c = SkyCoord(ra, dec, unit=(u.deg, u.deg))

        try:
            x_real, y_real = wcs.world_to_pixel(c)
        except:
            head = hdu[1].header
            # wcs = WCS(head)
            wcs = WCS(hdu[1])
            data = hdu[1].data
            x_real, y_real = wcs.world_to_pixel(c)

        x = int(x_real)
        y = int(y_real)

        pxscale = astropy.wcs.utils.proj_plane_pixel_scales(wcs)[0] * wcs.wcs.cunit[0].to('arcsec')
        # pxscale = np.sqrt(head['PIXAR_A2'])

        npix = int(2 / pxscale / 2)  # 2 arcsec diameter

        stamp = data[y - npix:y + npix, x - npix:x + npix]

        mean = np.nanmedian(stamp)
        std = np.nanstd(stamp)
        vmin = mean - std * 3
        vmax = mean + std * 3

        hdu.close()
        # pdb.set_trace()
        return stamp, vmin, vmax, x_real, y_real

    def create_html_file_par(self, det_file, phot_file):
        import multiprocessing
        from multiprocessing import Pool

        outfile_name = "{field_name}.candidates.html".format(field_name=self.field_name)
        html_name = os.path.join(self.html_dir, outfile_name)
        title = 'Detection Images and SEDs'

        import astropy.units as u

        sources = Table.read(det_file, format='ascii')
        source_coords = SkyCoord(sources['ra'], sources['dec'], unit=u.deg)
        source_ids = list(sources['snid'])
        phots = Table.read(phot_file, format='ascii')
        phots.sort('mag')
        indices = np.arange(0, len(sources), 1)
        # create_det_fig_par([0,source_ids[0],self,sources,phots])
        with Pool(processes=multiprocessing.cpu_count()) as pool:
            res = pool.map(create_det_fig_par, [[x, snid, self, sources, phots] for x, snid in enumerate(source_ids)])

        # print(res)
        # sys.exit()
        # import pdb
        # pdb.set_trace()

        print("Creating cut outs for %s candidates..." % len(source_ids))
        with document(title=title) as doc:
            n = -1
            for r in res:
                if r is None:
                    continue
                det_image, snid = r
                n += 1
                # # Dave Debug
                # if index == 3:
                #     break # break loop

                # curr = index + 1
                print("\tGenerating [%s/%s]..." % (n, len(source_ids)))
                t1_thumbnails = time.time()

                import astropy.units as u

                ra = sources[sources['snid'] == snid]['ra']
                dec = sources[sources['snid'] == snid]['dec']
                phot_subtable = phots[phots['snid'] == snid]
                phot_subtable = phot_subtable[np.isfinite(phot_subtable['mag'])]

                if 'host_ra' in sources.colnames:
                    host_ra = list(sources[sources['snid'] == snid]["host_ra"])[0]
                    host_dec = list(sources[sources['snid'] == snid]["host_dec"])[0]
                    host_z = list(sources[sources['snid'] == snid]["host_z"])[0]
                    host_sep = list(sources[sources['snid'] == snid]["host_sep"])[0]
                    host_id = list(sources[sources['snid'] == snid]["host_ID"])[0]
                else:
                    host_id = None

                # det_image = self.create_det_fig(row=sources[index], ra=ra, dec=dec, phot_tbl=phot_subtable)

                with div(id='%s' % snid).add(div()):

                    with table():
                        with tbody():
                            tr(td(b("ID")),
                               td(a("%s/%s#%s" % (self.html_root, outfile_name, snid), id=snid,
                                    href="{field_name}.candidates.html#{snid}".format(field_name=self.field_name,
                                                                                      snid=snid)),
                                  colspan=6)
                               )
                            if host_id is None:
                                tr(
                                    td(b("RA")),
                                    td(b("Dec")),
                                ),
                                tr(
                                    td(p("%0.8f" % ra)),
                                    td(p("%0.8f" % dec)),
                                )
                            else:
                                tr(
                                    td(b("RA")),
                                    td(b("Dec")),
                                    td(b("Host ID")),
                                    td(b("Host RA")),
                                    td(b("Host Dec")),
                                    td(b("Host Sep (arcsec)")),
                                    td(b("Host z")),
                                ),
                                tr(
                                    td(p("%0.8f" % ra)),
                                    td(p("%0.8f" % dec)),
                                    td(p("%0.0f" % host_id)),
                                    td(p("%0.8f" % host_ra)),
                                    td(p("%0.8f" % host_dec)),
                                    td(p("%0.3f" % host_sep)),
                                    td(p("%0.3f" % host_z))
                                )

                    div(img(src="{image_dir_name}/{file_name}".format(
                        image_dir_name=self.image_dir_name, file_name=det_image),
                        _class='photo'))

                    hr()

                    t2_thumbnails = time.time()
                    print("\t\t...Complete [%0.2f]" % (t2_thumbnails - t1_thumbnails))

        # import pdb
        # pdb.set_trace()
        with open(html_name, 'w') as f:
            f.write(doc.render())

        return html_name

    def create_html_file(self, det_file, phot_file):

        outfile_name = "{field_name}.candidates.html".format(field_name=self.field_name)
        html_name = self.html_dir + outfile_name
        title = 'Detection Images and SEDs'

        import astropy.units as u

        sources = Table.read(det_file, format='ascii')
        source_coords = SkyCoord(sources['ra'], sources['dec'], unit=u.deg)
        source_ids = list(sources['snid'])
        phots = Table.read(phot_file, format='ascii')

        print("Creating cut outs for %s candidates..." % len(source_ids))
        with document(title=title) as doc:
            for index, (snid, c) in enumerate(zip(source_ids, source_coords)):
                # # Dave Debug
                # if index == 3:
                #     break # break loop

                curr = index + 1
                print("\tGenerating [%s/%s]..." % (curr, len(source_ids)))
                t1_thumbnails = time.time()

                import astropy.units as u

                ra = c.ra.deg
                dec = c.dec.deg
                phot_subtable = phots[phots['snid'] == snid]
                phot_subtable = phot_subtable[np.isfinite(phot_subtable['mag'])]

                host_ra = list(sources[sources['snid'] == snid]["host_ra"])[0]
                host_dec = list(sources[sources['snid'] == snid]["host_dec"])[0]
                host_z = list(sources[sources['snid'] == snid]["host_z"])[0]
                host_sep = list(sources[sources['snid'] == snid]["host_sep"])[0]
                host_id = list(sources[sources['snid'] == snid]["host_ID"])[0]

                det_image = self.create_det_fig(row=sources[index], ra=ra, dec=dec, phot_tbl=phot_subtable)

                with div(id='%s' % snid).add(div()):
                    with table():
                        with tbody():
                            tr(td(b("ID")),
                               td(a("%s/%s#%s" % (self.html_root, outfile_name, snid), id=snid,
                                    href="{field_name}.candidates.html#{snid}".format(field_name=self.field_name,
                                                                                      snid=snid)),
                                  colspan=6)
                               )
                            tr(
                                td(b("RA")),
                                td(b("Dec")),
                                td(b("Host ID")),
                                td(b("Host Coord")),
                                td(b("Host Sep (arcsec)")),
                                td(b("Host z")),
                            ),
                            tr(
                                td(p("%0.8f" % ra)),
                                td(p("%0.8f" % dec)),
                                td(p("%0.0f" % host_id)),
                                td(p("%0.8f" % host_ra)),
                                td(p("%0.8f" % host_dec)),
                                td(p("%0.5f" % host_sep))
                            )

                    div(img(src="{image_dir_name}/{file_name}".format(
                        image_dir_name=self.image_dir_name, file_name=det_image),
                        _class='photo'))

                    hr()

                    t2_thumbnails = time.time()
                    print("\t\t...Complete [%0.2f]" % (t2_thumbnails - t1_thumbnails))

        # for index, (snid, c) in enumerate(zip(source_ids, source_coords)):

        #     import astropy.units as u

        #     ra = c.ra.deg
        #     dec = c.dec.deg
        #     phot_subtable = phots[phots['snid'] == snid]
        #     phot_subtable = phot_subtable[np.isfinite(phot_subtable['mag'])]

        #     det_images.append(self.create_det_fig(row=sources[index],ra=ra,dec=dec,phot_tbl=phot_subtable))
        #     if self.plot_SEDs:
        #         sed_images.append(self.create_sed_fig(phot_tbl=phot_subtable,ra=ra,dec=dec))

        # if self.plot_SEDs:
        #     with document(title=title) as doc:
        #         for det_path, sed_path in zip(det_images, sed_images):

        #             # a(det_path, href=os.getcwd()+'/'+det_path)
        #             a(det_path, href="{image_dir_name}/{file_name}".format(
        #                 image_dir_name=self.image_dir_name,
        #                 file_name=det_path))

        #             # div(img(src=os.getcwd()+'/'+det_path), _class='photo')
        #             # div(img(src=os.getcwd()+'/'+sed_path), _class='photo')
        #             div(img(src="{image_dir_name}/{file_name}".format(
        #                 image_dir_name=self.image_dir_name, file_name=det_path),
        #             _class='photo'))
        #             div(img(src="{image_dir_name}/{file_name}".format(
        #                 image_dir_name=self.image_dir_name, file_name=sed_path),
        #             _class='photo'))
        # else:
        #     with document(title=title) as doc:
        #         for det_path in det_images:
        #             # a(det_path, href=os.getcwd()+'/'+det_path)
        #             a(det_path, href="{image_dir_name}/{file_name}".format(
        #                 image_dir_name=self.image_dir_name,
        #                 file_name=det_path))

        #             # div(img(src=os.getcwd()+'/'+det_path), _class='photo')
        #             div(img(src="{image_dir_name}/{file_name}".format(
        #                 image_dir_name=self.image_dir_name, file_name=det_path),
        #             _class='photo'))

        with open(html_name, 'w') as f:
            f.write(doc.render())

        return html_name
