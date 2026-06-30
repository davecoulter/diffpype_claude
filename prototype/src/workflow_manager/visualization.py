import os, sys, glob
# from abc import ABCMeta, abstractmethod, abstractproperty
import abc
from enum import Enum
from astropy.coordinates import Angle, SkyCoord
import astropy.units as u
import json

import space_phot
from astropy.io import fits
from jwst.associations import asn_from_list
from jwst.associations.lib.rules_level3_base import DMS_Level3_Base
from jwst.pipeline import Image3Pipeline
from jwst.skymatch import SkyMatchStep
from jwst.datamodels import ModelLibrary

import matplotlib.cm as cm


from shapely.geometry import Point
from shapely.geometry.polygon import Polygon

from mocpy import MOC
from mocpy import WCS as mocWCS
from astropy.wcs import WCS
import matplotlib.pyplot as plt
from astropy.time import Time
import numpy as np

import pandas as pd
import mysql.connector

import mysql.connector
from mysql.connector import Error
from mysql.connector.pooling import MySQLConnectionPool
from pprint import pprint
import math

import pdb

import healpy as hp
from data_utils import DataUtils

class Visualizer:
    def __init__(self, image_dir: str):
        self.image_dir = image_dir

    def plot_footprint_and_epochs(self, moc_list: list, epoch_list: list, footprint_title: str, hist_title: str,
                                  central_coord: SkyCoord, fov_degrees: float, tile_df=None, thick=False, test_vertices=None):

        extra_width = 1
        if thick:
            extra_width = 10

        # fig = plt.figure(figsize=(6, 7.2), constrained_layout=True)
        fig = plt.figure(figsize=(10, 12), constrained_layout=True)
        gs = fig.add_gridspec(4, 4)

        with mocWCS(
                fig,
                fov=fov_degrees * u.degree,
                center=central_coord,
                coordsys="icrs",
                rotation=Angle(0, u.degree),
                # The gnomonic projection transforms great circles into straight lines.
                projection="TAN",
        ) as _wcs:
            ax1 = fig.add_subplot(gs[0:3, :], projection=_wcs)
            ax1.set_aspect("equal")

            for img in moc_list:
                # img.moc.fill(ax=ax, wcs=_wcs, alpha=0.5, fill=True, linewidth=1)
                img.border(ax=ax1, wcs=_wcs, alpha=0.3)

            if tile_df is not None:
                for df_i, df in tile_df.iterrows():
                    clr = 'red'
                    # if i == tile_index:
                    #     clr = 'blue'
                    tm = df["moc"]

                    tm.border(ax=ax1, wcs=_wcs, alpha=1.0, color=clr)
                    tm.fill(ax=ax1, wcs=_wcs, alpha=0.15, fill=True, linewidth=0, color=clr)

                    c = df["central_coord"]
                    lbl = df["name"]
                    ax1.plot(c.ra.degree, c.dec.degree, 'x', color="blue", markersize=1, transform=ax1.get_transform("world"))
                    # ax1.text(c.ra.degree, c.dec.degree, lbl, transform=ax1.get_transform("world"))

            # for akc in test_vertices:
            #     ax1.plot(akc[0], akc[1], '+', color="red", markersize=1,
            #              transform=ax1.get_transform("world"))

        ax1.set_xlabel("RA")
        ax1.set_ylabel("Dec")
        ax1.set_title(footprint_title)
        ax1.grid(color="black", linestyle="dotted")

        # Create Epoch plot
        ax2 = fig.add_subplot(gs[3:4, :])

        start = int(np.floor(np.min(epoch_list)))
        end = int(np.ceil(np.max(epoch_list)))
        num_bins = (end - start) + 2
        bins = np.linspace(start, end + 1, num_bins)

        counts, bin_edges = np.histogram(epoch_list, bins=bins)
        bin_centers = (bin_edges[1:] + bin_edges[:-1]) / 2
        ax2.bar(bin_centers, counts, width=np.diff(bin_edges)*extra_width, edgecolor='black')

        ax2.ticklabel_format(useOffset=False, style='plain')
        ax2.set_ylabel('Number of Images')
        ax2.set_xlabel('MJD')
        ax2.set_title(hist_title)

        fig.savefig("%s/Footprint_and_Epochs.png" % self.image_dir, bbox_inches='tight', format="png")  # ,dpi=840

    def plot_tile_contents(self, image_dataframe, tile_dataframe, filter_tuples, tile_id, fov_scale, thick=False):

        _tile = tile_dataframe[tile_dataframe["id"] == tile_id]
        _tile_obj = _tile.iloc[0]
        tile_name = _tile_obj["name"]
        _covered_area = _tile_obj.moc.sky_fraction * 41253
        _fov_proxy = np.sqrt(_covered_area)
        _barycenter = _tile_obj.moc.barycenter()

        # iterate over all filters
        for filt_tup in filter_tuples:
            filt_id = filt_tup[0]
            filt_name = filt_tup[1]

            sub_sub_img_df = image_dataframe[image_dataframe["band_id"] == filt_id]

            self.plot_footprint_and_epochs(moc_list=sub_sub_img_df.moc,
                                           epoch_list=sub_sub_img_df.mjd_avg,
                                           footprint_title="%s Footprint - %s" % (tile_name, filt_name),
                                           hist_title="%s: %s - Total Epochs" % (tile_name, filt_name),
                                           central_coord=_barycenter,
                                           fov_degrees=fov_scale * _fov_proxy,
                                           tile_df=_tile,
                                           thick=thick)


    def plot_epochs(self, all_image_dataframe, epoch_image_dataframe, tile_dataframe, filter_tuple, tile_id, fov_scale,
                    epoch_record):

        _tile = tile_dataframe[tile_dataframe["id"] == tile_id]
        _tile_obj = _tile.iloc[0]
        tile_name = _tile_obj["name"]
        _covered_area = _tile_obj.moc.sky_fraction * 41253
        _fov_proxy = np.sqrt(_covered_area)
        _barycenter = _tile_obj.moc.barycenter()

        epoch_record_id = epoch_record["id"]
        start_mjd = epoch_record["start_mjd"]
        stop_mjd = epoch_record["end_mjd"]

        filt_id = filter_tuple[0]
        filt_name = filter_tuple[1]

        footprint_title = ("Tile ID: %s - Tile Name: `%s` - Filter: %s\n Epoch ID: %s\nMJDs: %s-%s\n" %
                           (tile_id, tile_name, filt_name, epoch_record_id, int(start_mjd), int(stop_mjd)))
        hist_title = "%s: %s - All MJDs" % (tile_name, filt_name)

        moc_list = list(epoch_image_dataframe.moc)
        file_list = list(epoch_image_dataframe.base_filename)
        epoch_list = all_image_dataframe[all_image_dataframe.band_id == filt_id].mjd_avg

        epoch_moc = DataUtils.Get_Unioned_MOC(moc_list)
        mosaic_moc = epoch_moc.intersection(_tile_obj.moc)

        # fig = plt.figure(figsize=(6, 7.2), constrained_layout=True)
        fig = plt.figure(figsize=(10, 8), constrained_layout=True)
        gs = fig.add_gridspec(4, 4)

        with mocWCS(
                fig,
                fov=fov_scale * _fov_proxy * u.degree,
                center=_barycenter,
                coordsys="icrs",
                rotation=Angle(0, u.degree),
                # The gnomonic projection transforms great circles into straight lines.
                projection="TAN",
        ) as _wcs:
            ax1 = fig.add_subplot(gs[0:3, :], projection=_wcs)
            ax1.set_aspect("equal")

            cmap = plt.get_cmap('plasma')
            normalize = plt.Normalize(vmin=0, vmax=len(moc_list) - 1)

            for ii, (file_name, img) in enumerate(zip(file_list, moc_list)):
                clr = cmap(normalize(ii))
                img.border(ax=ax1, wcs=_wcs, alpha=1.0, color=clr, label=file_name)

            if _tile is not None:
                for df_i, df in _tile.iterrows():
                    clr = 'red'
                    tm = df["moc"]

                    tm.border(ax=ax1, wcs=_wcs, alpha=1.0, color=clr)
                    tm.fill(ax=ax1, wcs=_wcs, alpha=0.15, fill=True, linewidth=0, color=clr)

                    c = df["central_coord"]
                    lbl = df["name"]
                    ax1.text(c.ra.degree, c.dec.degree, lbl, transform=ax1.get_transform("world"))

            mosaic_moc.border(ax=ax1, wcs=_wcs, alpha=1.0, color="blue")
            mosaic_moc.fill(ax=ax1, wcs=_wcs, alpha=0.5, fill=True, color="blue", linewidth=0.0)

        ax1.set_xlabel("RA")
        ax1.set_ylabel("Dec")
        ax1.set_title(footprint_title)
        ax1.grid(color="black", linestyle="dotted")
        ax1.legend(loc='upper left', bbox_to_anchor=(1.0, 1), fontsize=8)

        # Create Epoch plot
        ax2 = fig.add_subplot(gs[3:4, :])

        start = int(np.floor(np.min(epoch_list)))
        end = int(np.ceil(np.max(epoch_list)))
        num_bins = (end - start) + 2
        bins = np.linspace(start, end + 1, num_bins)

        ax2.axvspan(start_mjd, stop_mjd, hatch="X", edgecolor="orange", linewidth=3.0) # alpha=1.0, facecolor="none",
        # _bins = ax2.hist(epoch_list, bins=bins, color="red")
        counts, bin_edges = np.histogram(epoch_list, bins=bins)
        ax2.bar(bin_edges[:-1], counts, width=np.diff(bin_edges), edgecolor='red')

        ax2.ticklabel_format(useOffset=False, style='plain')
        ax2.set_ylabel('Number of Images')
        ax2.set_xlabel('MJD')
        ax2.set_title(hist_title)

        # plt.show()
        fig.savefig("%s/%s_%s_%s_%s_footprint.png" % (self.image_dir, tile_name, start_mjd, stop_mjd, filt_name),
                    bbox_inches='tight', format="png")  # ,dpi=840