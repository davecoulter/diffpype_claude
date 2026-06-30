import os, sys, glob
import pdb

from astropy.coordinates import Angle, SkyCoord
import astropy.units as u
from astropy.io import fits
from mocpy import MOC
from astropy.wcs import WCS
from astropy.time import Time
import numpy as np
import pandas as pd
from pprint import pprint
import math
import json
from sklearn.cluster import KMeans
from scipy.signal import find_peaks

class DataUtilMeta(type):
    """
    This is a metaclass that will be used to create a Singleton of DataUtil.
    It manages the single instance of the class it is applied to.
    """
    _instances = {} # A dictionary to store instances of singleton classes.

    def __call__(cls, *args, **kwargs):
        """
        Overrides the call method for the class.
        This method is called when an instance of the class is created (e.g., DataUtil()).
        It checks if an instance already exists; if not, it creates one.
        """
        if cls not in cls._instances:
            # If no instance exists for this class, create one using the super's __call__ method.
            instance = super().__call__(*args, **kwargs)
            cls._instances[cls] = instance
        # Always return the single stored instance.
        return cls._instances[cls]

class DataUtils(metaclass=DataUtilMeta):
    """
    This is the Singleton class.
    It uses the DataUtilMeta metaclass to enforce the singleton pattern.
    """
    def __init__(self, moc_max_depth:int = 21):
        """
        The constructor for the singleton.
        Note: __init__ will be called every time MySingleton() is called,
        even if an instance already exists.
        """
        if not hasattr(self, '_initialized'): # Check if the instance has been truly initialized
            self.moc_max_depth = moc_max_depth
            self._initialized = True
            print(f"DataUtils instance initialized with `moc_max_depth`: {self.moc_max_depth}")
        else:
            print(f"DataUtils instance already exists. Current `moc_max_depth`: {self.moc_max_depth}")

    # TODO: Decide what the correct thing to do is if there's an image that is corrupted. See Try-Catch.
    @staticmethod
    def ConvertFITStoDataFrame(file_path_list: list):

        # Unpack FITS files and transform to a data frame
        # cols = ['ra', 'decl', 'obs_start', 'mjd_avg', 'exp_time', 'target_name', 'base_filename',
        #         'current_file_ext', 'poly', 'instrument_name', 'filter_name']
        cols = ['ra', 'decl', 'obs_start', 'exp_time', 'target_name', 'base_filename', 'band_id', 'instrument_id',
                'mjd_avg']
        df = DataUtils.CreateEmptyDataFrame(cols)

        rows_to_append = []
        for i in file_path_list:

            data_row = []

            try:
                h_sci = fits.getheader(i, 'SCI')
                h_pri = fits.getheader(i, 'PRIMARY')
                tgt_name = h_pri['TARGPROP']
                coord = SkyCoord(float(h_sci["CRVAL1"]), float(h_sci["CRVAL2"]), unit="deg", frame="icrs")
                exp_time = float(h_sci['XPOSURE'])
                mjd_avg = float(h_sci["MJD-AVG"])
                obs_date = Time(mjd_avg, format='mjd').isot
                base_filename = os.path.basename(i)

                filt_name = h_pri["FILTER"]
                instrument_name = h_pri['INSTRUME']

                data_row.append(coord.ra.degree)
                data_row.append(coord.dec.degree)
                data_row.append(obs_date)
                data_row.append(exp_time)
                data_row.append(tgt_name)
                data_row.append(base_filename)
                data_row.append(filt_name)
                data_row.append(instrument_name)
                data_row.append(mjd_avg)

                rows_to_append.append(tuple(data_row))
            except Exception as e:
                print(e)
                print("Continuing...")
                continue

        df = DataUtils.CreateDataFrame(cols, rows_to_append)
        return df


    @staticmethod
    def UnpackFITStoLvl2Cal(file_path_list: list):
        # Unpack FITS files and transform to a data frame
        cols = ['ra', 'decl', 'obs_start', 'mjd_avg', 'exp_time', 'target_name', 'base_filename',
                'current_file_ext', 'poly', 'instrument_name', 'filter_name']
        df = DataUtils.CreateEmptyDataFrame(cols)

        rows_to_append = []
        for i in file_path_list:
            data_row = []

            h_sci = fits.getheader(i, 'SCI')
            h_pri = fits.getheader(i, 'PRIMARY')
            tgt_name = h_pri['TARGPROP']
            f_wcs = WCS(h_sci)
            coord = SkyCoord(float(h_sci["CRVAL1"]), float(h_sci["CRVAL2"]), unit="deg", frame="icrs")
            exp_time = float(h_sci['XPOSURE'])
            poly = f_wcs.calc_footprint()
            skycoord_poly = SkyCoord(poly, unit="deg", frame="icrs")
            # moc = MOC.from_polygon_skycoord(skycoord_poly, complement=False, max_depth=21)
            mjd_avg = float(h_sci["MJD-AVG"])
            obs_date = Time(mjd_avg, format='mjd').isot
            base_filename = os.path.basename(i)
            current_file_ext = os.path.splitext(base_filename)[-1]

            filt_name = h_pri["FILTER"]
            instrument_name = h_pri['INSTRUME']

            data_row.append(coord.ra.degree)
            data_row.append(coord.dec.degree)
            data_row.append(obs_date)
            data_row.append(mjd_avg)
            data_row.append(exp_time)
            data_row.append(tgt_name)
            data_row.append(base_filename)
            data_row.append(current_file_ext)
            data_row.append(json.dumps(skycoord_poly.to_string()))
            data_row.append(instrument_name)
            data_row.append(filt_name)

            rows_to_append.append(tuple(data_row))

        df = DataUtils.CreateDataFrame(cols, rows_to_append)
        return df

    @staticmethod
    def GlobFITSFiles(base_file_path: str):
        items = []

        for filename in os.listdir(base_file_path):

            if filename.endswith(".fits"):
                items.append("%s/%s" % (base_file_path, filename))

        return items

    @staticmethod
    def test_sky_tiles():

        def find_nearest(array, value):
            array = np.asarray(array)
            idx = (np.abs(array - value)).argmin()
            return idx

        northern_limit = 89.99999
        southern_limit = -89.99999
        eastern_limit = 359.99999
        western_limit = 0.0


        dec_range = 179.99999
        ra_range = 359.99999

        frac_dec_tile, num_dec_tiles = math.modf(dec_range / 0.0375)

        total_dec_tiles = int(num_dec_tiles) + 1
        if num_dec_tiles == 0:
            num_dec_tiles = 1

        dec_differential = (0.0375 - (frac_dec_tile * 0.0375)) / num_dec_tiles

        dec_delta = 0.0375 - dec_differential
        starting_dec = southern_limit + 0.0375 / 2.0

        decs = []
        for i in range(total_dec_tiles):
            d = starting_dec + i * dec_delta
            decs.append(d)

        ras_over_decs = []
        for d in decs:

            adjusted_tile_width = 0.0375 / np.abs(np.cos(np.radians(d)))

            frac_ra_tile, num_ra_tiles = math.modf(ra_range / adjusted_tile_width)
            total_ra_tiles = int(num_ra_tiles) + 1

            if num_ra_tiles == 0:
                num_ra_tiles = 1

            ra_differential = (adjusted_tile_width - (frac_ra_tile * adjusted_tile_width)) / num_ra_tiles
            ra_delta = adjusted_tile_width - ra_differential

            ras = []
            starting_ra = adjusted_tile_width / 2.0
            for i in range(total_ra_tiles):
                r = starting_ra + i * ra_delta
                ras.append(r)

            ras_over_decs.append(ras)

        print("All Sky statistics for %s..." % "Massimo BB")
        print("\tNum of dec strips: %s" % len(decs))

        north_index = find_nearest(decs, northern_limit)
        south_index = find_nearest(decs, southern_limit)
        equator_index = find_nearest(decs, 0.0)

        print("\tNorthern most dec: %s" % decs[north_index])
        print("\tSouthern most dec: %s" % decs[south_index])

        east_index = find_nearest(ras_over_decs[equator_index], eastern_limit)
        west_index = find_nearest(ras_over_decs[equator_index], western_limit)

        print("\tEastern most ra: %s" % ras_over_decs[equator_index][east_index])
        print("\tWestern most ra: %s" % ras_over_decs[equator_index][west_index])

        print("\tNum of ra tiles in northern most dec slice: %s" % len(ras_over_decs[north_index]))
        print("\tNum of ra tiles at celestial equator: %s" % len(ras_over_decs[equator_index]))

        print("Constructing grid of coordinates...")
        RA = []
        DEC = []
        for i, d in enumerate(decs):
            for ra in ras_over_decs[i]:
                RA.append(ra)
                DEC.append(d)

        all_sky_coords = list(zip(RA, DEC))
        print("Total coords for %s: %s" % ("Massimo BB", len(all_sky_coords)))

        print("\n******\n")

        print("\n********* start DEBUG ***********")
        print("`generate_all_sky_coords`")
        print("********* end DEBUG ***********\n")

        return all_sky_coords

    @staticmethod
    def GenerateSkyTiles(project_id:int, tile_side_length_arc_min: float, moc_to_tile: MOC, overlap_in_arc_min: float = 0.0):
        '''
            GenerateSkyTiles creates a regular grid of points on a sphere with tiles with side length
            `tile_side_length` in arcminutes
        '''

        def find_nearest(array, value):
            array = np.asarray(array)
            idx = (np.abs(array - value)).argmin()
            return idx

        # Convert tile dimensions to degrees
        orig_deg_height = tile_side_length_arc_min / 60.0
        orig_deg_width = tile_side_length_arc_min / 60.0

        deg_height = (tile_side_length_arc_min - overlap_in_arc_min) / 60.0
        deg_width = (tile_side_length_arc_min - overlap_in_arc_min) / 60.0

        print(deg_height)
        print(deg_width)

        # Hack - Avoiding multiplicity
        threshold = 0.1 / 3600.  # 0.1 arcsecond
        northern_limit = 90.0 - threshold - deg_height
        southern_limit = -90.0
        eastern_limit = 360.0 - threshold - deg_width
        western_limit = 0.0

        # Calculate ranges
        dec_range = northern_limit - southern_limit
        ra_range = eastern_limit - western_limit

        # print(dec_range)
        # print(ra_range)

        # Modulo arithmetic: how many tiles fit in this range, and what's the remainder?
        #   We can add the requested overlap here
        frac_dec_tile, num_dec_tiles = math.modf(dec_range / (deg_height))

        # Add a final tile to get the ceiling of tiles required
        total_dec_tiles = int(num_dec_tiles) + 1
        if num_dec_tiles == 0:
            num_dec_tiles = 1

        # Use the fractional tile to create a vertical spacing (`dec_delta`)
        dec_differential = (deg_height - (frac_dec_tile * deg_height)) / num_dec_tiles
        dec_delta = deg_height - dec_differential
        starting_dec = southern_limit + deg_height / 2.0

        decs = []
        for i in range(total_dec_tiles):
            d = starting_dec + i * dec_delta
            decs.append(d)

        ras_over_decs = []
        for d in decs:

            adjusted_tile_width = deg_width / np.abs(np.cos(np.radians(d)))

            frac_ra_tile, num_ra_tiles = math.modf(ra_range / (adjusted_tile_width))
            total_ra_tiles = int(num_ra_tiles) + 1

            if num_ra_tiles == 0:
                num_ra_tiles = 1

            ra_differential = (adjusted_tile_width - (frac_ra_tile * adjusted_tile_width)) / num_ra_tiles
            ra_delta = adjusted_tile_width - ra_differential

            ras = []
            starting_ra = adjusted_tile_width / 2.0
            for i in range(total_ra_tiles):
                r = starting_ra + i * ra_delta
                ras.append(r)

            ras_over_decs.append(ras)

        print("All Sky statistics")
        print("\tNum of dec strips: %s" % len(decs))

        north_index = find_nearest(decs, northern_limit)
        south_index = find_nearest(decs, southern_limit)
        equator_index = find_nearest(decs, 0.0)

        print("\tNorthern most dec: %s" % decs[north_index])
        print("\tSouthern most dec: %s" % decs[south_index])

        east_index = find_nearest(ras_over_decs[equator_index], eastern_limit)
        west_index = find_nearest(ras_over_decs[equator_index], western_limit)

        print("\tEastern most ra: %s" % ras_over_decs[equator_index][east_index])
        print("\tWestern most ra: %s" % ras_over_decs[equator_index][west_index])

        print("\tNum of ra tiles in northern most dec slice: %s" % len(ras_over_decs[north_index]))
        print("\tNum of ra tiles at celestial equator: %s" % len(ras_over_decs[equator_index]))

        print("Constructing grid of coordinates...")
        RA = []
        DEC = []
        for i, d in enumerate(decs):
            for ra in ras_over_decs[i]:
                RA.append(float(ra))
                DEC.append(float(d))

        all_sky_coords = SkyCoord(np.asarray(RA), np.asarray(DEC), unit=(u.degree, u.degree), frame="icrs")

        # Get the region around the MOC to set which tiles we consider
        covered_area = moc_to_tile.sky_fraction * 41252.96
        bary = moc_to_tile.barycenter()
        fov_degrees = 2 * np.sqrt(covered_area)  # deg

        mask = all_sky_coords.separation(bary).degree <= fov_degrees
        nearby_coords = all_sky_coords[mask]
        print("Number of coords near (%0.4f, %0.4f) within a %0.4f deg radius: %s" %
              (bary.ra.degree, bary.dec.degree, fov_degrees, len(nearby_coords)))

        # Create Tile MOCs
        x_step = orig_deg_width / 2.0
        y_step = orig_deg_height / 2.0

        cols = ['name', 'ra', 'decl', 'delta_ra', 'delta_decl', 'coord_sys', 'project_id', 'poly', 'moc', 'central_coord']
        tile_rows = []
        tile_num = 1
        for i, c in enumerate(nearby_coords):

            x_step_new = x_step/np.cos(np.radians(c.dec.degree))

            # _ras = np.asarray([ (c.ra.degree + x_step), c.ra.degree + x_step, c.ra.degree - x_step, c.ra.degree - x_step])
            _ras = np.asarray(
                [(c.ra.degree + x_step_new), c.ra.degree + x_step_new, c.ra.degree - x_step_new, c.ra.degree - x_step_new])
            _decs = np.asarray(
                [c.dec.degree + y_step, c.dec.degree - y_step, c.dec.degree - y_step, c.dec.degree + y_step])
            _p = SkyCoord(_ras, _decs, unit="deg", frame="icrs")
            _moc = MOC.from_polygon_skycoord(_p, complement=False, max_depth=21)

            if moc_to_tile.intersection(_moc).sky_fraction > 0:
                tile_row = []
                tile_row.append("Tile_%s" % (tile_num))
                tile_row.append(c.ra.degree)
                tile_row.append(c.dec.degree)
                tile_row.append(deg_width)
                tile_row.append(deg_height)
                tile_row.append(2000)
                tile_row.append(project_id)
                tile_row.append(_p)
                tile_row.append(_moc)
                tile_row.append(c)

                tile_rows.append(tuple(tile_row))
                tile_num += 1

        df = DataUtils.CreateDataFrame(cols, tile_rows)
        return df

    @staticmethod
    def CreateEmptyDataFrame(column_names: list):
        '''
        Creates an empty dataframe from a column name list
        Args:
            column_names (list[str]): The Column names
        Returns:
            returns a dataframe representation
        '''
        # sanity: check if column_names is the same length as data_rows
        col_len = 0
        if column_names is not None and len(column_names) > 0:
            col_len = len(column_names)
        else:
            raise Exception("No column names specified!")

        df = pd.DataFrame({col_name:[] for col_name in column_names})
        # df = pd.DataFrame(columns=column_names)
        return df

    @staticmethod
    def CreateDataFrame(column_names: list, data_rows:list):
        '''
        Creates a dataframe from a column name list, and a list of rows
        Args:
            column_names (list[str]): The Column names
            data_rows (list[tuple]): A list of tuples, each tuple the same dimension as column_names
        Returns:
            returns a dataframe representation
        '''

        # Create empty DF
        col_len = len(column_names)
        df = DataUtils.CreateEmptyDataFrame(column_names)

        data_rows_populated = data_rows is not None and len(data_rows) > 0
        if data_rows_populated and len(data_rows[0]) != col_len:
            raise Exception("Column names and data_rows fields are different shapes!")

        df_dict = {col_name:[] for col_name in column_names}
        if data_rows_populated:
            for row in data_rows:
                for col_name, col_val in zip(column_names, row):
                    df_dict[col_name].append(col_val)
        df = pd.DataFrame(df_dict)
        return df

    @staticmethod
    def Get_Unioned_MOC(moc_list):
        union_moc = moc_list[0]
        for img in moc_list:
            union_moc = union_moc.union(img)

        return union_moc

    @staticmethod
    def CreateEpochsFromMJDs(mjd_list, peak_distance_thresh):

        mjd = np.array(mjd_list)
        mjd_reshaped = mjd.reshape(-1, 1)

        start = int(np.floor(np.min(mjd)))
        end = int(np.ceil(np.max(mjd)))

        # set bins to daily
        nbins = (end - start) + 2
        bins = np.linspace(start, end + 1, nbins)
        hist, bin_edges = np.histogram(mjd, bins=nbins, range=[mjd.min() - 1, mjd.max() + 1])

        # distance is the min spacing between histogram peaks before counting as a new peak
        peaks, _ = find_peaks(hist, height=None, distance=peak_distance_thresh)
        num_peaks = len(peaks)

        # num_peaks = k clusters
        kmeans = KMeans(n_clusters=num_peaks, random_state=0)
        kmeans.fit(mjd_reshaped)

        cluster_centers = np.sort(kmeans.cluster_centers_.flatten())
        cluster_intervals = np.asarray([(cc - peak_distance_thresh, cc + peak_distance_thresh) for cc in cluster_centers])
        # cluster_edges = (cluster_centers[:-1] + cluster_centers[1:]) / 2

        # Force the MJD ranges to be integers
        truncated_epochs = []
        for ci in cluster_intervals:
            truncated_epochs.append([int(np.floor(ci[0])), int(np.ceil(ci[1]))])
        truncated_epochs = np.asarray(truncated_epochs)

        # return cluster_intervals
        return truncated_epochs



