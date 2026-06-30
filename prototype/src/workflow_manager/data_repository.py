import os, sys, glob
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
import json
import healpy as hp
import copy


from data_utils import DataUtils

class AbstractRepository(abc.ABC):
    """
    Abstract base class for a generic data repository.
    Defines the interface that all concrete repositories must implement.
    """
    @abc.abstractmethod
    def save_images(self):
        """
        Saves all items in the repository.
        """
        pass

    @abc.abstractmethod
    def retrieve_images(self):
        """
        Lists all items in the repository.
        """
        pass

    @abc.abstractmethod
    def save_tiles(self, tile_dataframe, project_name, clobber=False):
        """
        save tiles to the repo
        """
        pass

    @abc.abstractmethod
    def retrieve_tiles(self, project_name):
        """
        save tiles to the repo
        """
        pass

    @abc.abstractmethod
    def save_tile_image_association(self, tile_dataframe, image_dataframe):
        """
        save tiles-image to the repo
        """
        pass

    @abc.abstractmethod
    def retrieve_tile_image(self, tile_dataframe):
        """
        save tiles-image to the repo
        """
        pass

    @abc.abstractmethod
    def save_tile_epochs(self, start_times, end_times, tile_id, project_id):
        """
        save tiles-image to the repo
        """
        pass

    @abc.abstractmethod
    def retrieve_tile_epochs(self, tile_id, project_id):
        """
        save tiles-image to the repo
        """
        pass


    @abc.abstractmethod
    def save_project(self, project_name):
        """
        save tiles to the repo
        """
        pass

    @abc.abstractmethod
    def retrieve_project(self, project_name):
        """
        save tiles to the repo
        """
        pass

class MySQLRepository(AbstractRepository):
    """
    Concrete implementation of the repository pattern for MySQL.
    In this mock-up, we're simulating interactions.
    """

    def __init__(self, global_config: dict, pool_name="mypool", pool_size=5):

        # Set internal collections
        self.data_util = DataUtils(moc_max_depth=global_config["moc_settings"]["moc_max_depth"])
        self.global_config = global_config
        self.db_config = self.global_config["mysql_config"]
        self.pool_name = pool_name
        self.pool_size = pool_size
        self.mast_proxy_dir = self.global_config["filesystem_config"]["mast_proxy"]
        self.base_filesystem_dir = self.global_config["filesystem_config"]["base_dir"]

        # Need to set Project Context to populate these directories!!
        self.proj_path = ""
        self.rawimage_dir = ""
        self.workingimage_dir = ""
        self.log_dir = ""
        self.project = "" # tuple to hold the project ID and name

        # If directory doesn't exist, create it
        os.makedirs(self.base_filesystem_dir, exist_ok=True)

        self.cnx_pool = None
        self._init_connection_pool()

        # Initialize internal convenience dictionaries
        band_result = self._execute_single(sql_query="SELECT id, name FROM Band", fetch_results=True)
        self.bands = {band_result_tuple[1]: band_result_tuple[0] for band_result_tuple in band_result}
        self.reverse_bands = {band_result_tuple[0]: band_result_tuple[1] for band_result_tuple in band_result}

        lvl2_status_result = self._execute_single(sql_query="SELECT id, name FROM Lvl2Cal_Status", fetch_results=True)
        self.lvl2_statuses = {status_result_tuple[1]: status_result_tuple[0] for status_result_tuple in lvl2_status_result}
        self.reverse_lvl2_statuses = {status_result_tuple[0]: status_result_tuple[1] for status_result_tuple in
                              lvl2_status_result}

        lvl3_status_result = self._execute_single(sql_query="SELECT id, name FROM Lvl3Mosaic_Status", fetch_results=True)
        self.lvl3_statuses = {status_result_tuple[1]: status_result_tuple[0] for status_result_tuple in
                              lvl3_status_result}
        self.reverse_lvl3_statuses = {status_result_tuple[0]: status_result_tuple[1] for status_result_tuple in
                              lvl3_status_result}

        instrument_result = self._execute_single(sql_query="SELECT id, name FROM Instrument", fetch_results=True)
        self.instruments = {instrument_result_tuple[1]: instrument_result_tuple[0] for instrument_result_tuple in
                            instrument_result}
        self.reverse_instruments = {instrument_result_tuple[0]: instrument_result_tuple[1] for instrument_result_tuple in
                            instrument_result}

        # Hack - this should be calculated on each images CD Matrix (sqrt(abs(det(CD_matrix))))
        self.platescales = {
            'F090W': 30,
            'F115W': 30,
            'F150W': 30,
            'F200W': 30,
            'F212N': 30,
            'F277W': 60,
            'F356W': 60,
            'F410M': 60,
            'F444W': 60,
            'F335M': 60,
            'F480M': 60,
            'F210M': 60,
            'F182M': 30,
            'F460M': 60,
            'F430M': 60,
            'F360M': 60
        }

    def set_project_context(self, project_df):

        project_id = project_df.loc[0, 'id']
        project_name = project_df.loc[0, 'name']
        self.project = (project_id, project_name)

        # Create project subdir
        proj_path = os.path.join(self.base_filesystem_dir, project_name)
        os.makedirs(proj_path, exist_ok=True)

        # Create project subsubdirs
        rawimage_dir = os.path.join(proj_path, "rawimage")
        workingimage_dir = os.path.join(proj_path, "working")
        log_dir = os.path.join(proj_path, "logs")
        os.makedirs(rawimage_dir, exist_ok=True)
        os.makedirs(workingimage_dir, exist_ok=True)
        os.makedirs(log_dir, exist_ok=True)

        try:
            self.proj_path = proj_path
            self.rawimage_dir = rawimage_dir
            self.workingimage_dir = workingimage_dir
            self.log_dir = log_dir

            print("Project directories created.")
        except Error as e:
            print(f"Error initializing project directories!: {e}")

    def _init_connection_pool(self):
        """Initializes the MySQL connection pool."""
        try:
            self.cnx_pool = MySQLConnectionPool(
                pool_name=self.pool_name,
                pool_size=self.pool_size,
                **self.db_config
            )
            print(f"Connection pool '{self.pool_name}' initialized with size {self.pool_size}.")
        except Error as e:
            print(f"Error initializing connection pool: {e}")
            self.cnx_pool = None

    def _get_connection(self):
        """
        Retrieves a connection from the pool.
        It's crucial to release this connection after use.
        """
        if not self.cnx_pool:
            print("Connection pool not initialized.")
            return None
        try:
            connection = self.cnx_pool.get_connection()
            if connection.is_connected():
                # print("Connection retrieved from pool.") # Optional: for debugging
                return connection
            else:
                print("Failed to get a connected connection from pool.")
                return None
        except Error as e:
            print(f"Error getting connection from pool: {e}")
            return None

    def _release_connection(self, connection):
        """Releases a connection back to the pool."""
        if connection:
            connection.close()
            # print("Connection released back to pool.") # Optional: for debugging

    def _execute_single(self, sql_query: str, values: tuple = None, fetch_results: bool = False):
        """
        Executes a raw SQL query.

        WARNING: Executing raw SQL directly without proper input sanitization
        is a significant security risk (SQL Injection). Ensure that any
        user-supplied data is meticulously sanitized before constructing
        the `sql_query` string. This method is provided as requested,
        but parameterized queries are generally safer for dynamic input.

        Args:
            sql_query (str): The raw SQL query string to execute.
            fetch_results (bool): If True, fetches results (for SELECT queries).

        Returns:
            list or None: List of fetched rows for SELECT, None for other operations
                          or on error.
            int: Number of affected rows for INSERT/UPDATE/DELETE operations, or -1 on error.
        """
        connection = None
        cursor = None
        try:
            connection = self._get_connection()
            if not connection:
                raise Exception("Can't get connection!")

            cursor = connection.cursor(buffered=True)

            if values:
                cursor.execute(sql_query, values)
            else:
                cursor.execute(sql_query)  # For queries without parameters

            if fetch_results:
                return cursor.fetchall()
            else:
                connection.commit()  # Commit changes for DML operations
                return cursor.rowcount  # Return affected rows

        except Error as e:
            print(f"Error executing SQL query: {e}\nQuery: {sql_query}\nValues: {values}")
            if connection:
                connection.rollback()  # Rollback on error
            return None if fetch_results else -1  # Return None for fetch failure, -1 for DML failure
        finally:
            if cursor:
                cursor.close()
            self._release_connection(connection)

    def _execute_batch(self, sql_query: str, batch_values: list[tuple]):
        """
        Executes a SQL query in batch mode using executemany.
        Ideal for multiple INSERT, UPDATE, or DELETE operations with varying data.

        Args:
            sql_query (str): The SQL query string with %s placeholders for each item in the batch.
            batch_values (list[tuple]): A list of tuples, where each tuple contains values
                                       for one row/operation.

        Returns:
            int: Number of affected rows, or -1 on error.
        """
        connection = None
        cursor = None
        try:
            connection = self._get_connection()
            if not connection:
                raise Exception("Database connection unavailable.")

            cursor = connection.cursor()
            cursor.executemany(sql_query, batch_values)
            connection.commit()

            return cursor.rowcount

        except Error as e:
            print(f"Error executing batch SQL query: {e}\nQuery: {sql_query}\nSample batch values: {batch_values[:5]}")
            if connection:
                connection.rollback()
            return -1  # Indicate failure
        finally:
            if cursor:
                cursor.close()
            self._release_connection(connection)

    # HACK - this is emulating a query to MAST, which will load files onto memory. Then the file metadata will be saved
    # to the db, and the files written to disk
    def get_images_from_MAST(self):

        # Stashing this code here in case we need to parse s_regions directly
        # from regions import CircleSkyRegion, CirclePixelRegion, PolygonSkyRegion, Regions
        # from shapely.geometry import Polygon
        # r = Regions.parse(poly_str, format='ds9')
        # print(r[0].vertices)
        # sn1_moc = MOC.from_polygon_skycoord(r[0].vertices, max_depth=20)
        # sn1_coord = SkyCoord(150.139013, 2.39575, unit=u.degree, frame="icrs")
        # poly_tuples = [(150.160431166, 2.355291744), (150.127280667, 2.369755527), (150.141143546, 2.402341359),
        #                (150.174383362, 2.388767403), (150.160431166, 2.355291744)]
        # sci_poly = Polygon(poly_tuples)

        file_path_list = DataUtils.GlobFITSFiles(self.mast_proxy_dir)

        for file_path in file_path_list:
            # Get just the filename from the full path
            file_name = os.path.basename(file_path)
            # Construct the full path for the symlink in the target directory
            symlink_path = os.path.join(self.rawimage_dir, file_name)

            # Check if symlink already exists to avoid errors
            if os.path.exists(symlink_path) or os.path.islink(symlink_path):
                print(f"Symlink '{symlink_path}' already exists, skipping.")
                continue

            try:
                # Create the symbolic link
                os.symlink(file_path, symlink_path)
                print(f"Created symlink: '{symlink_path}' -> '{file_path}'")
            except OSError as e:
                print(f"Error creating symlink for '{file_path}': {e}")

        symlink_files = DataUtils.GlobFITSFiles(self.rawimage_dir)
        df = DataUtils.ConvertFITStoDataFrame(symlink_files)
        return self.save_images(df)

    # HACK? I am going to save the image to the Image table, and the related properties to the Lv2Cal Table
    def save_images(self, image_dataframe):

        cols = ['ra', 'decl', 'obs_start', 'exp_time', 'target_name', 'base_filename', 'filter_name', 'instrument_name',
                'mjd_avg']
        extra_cols = ['band_id', 'instrument_id']

        # HACK - prune the instrument_name amd filter_name since we're going to add an IDs here instead
        cols.remove('instrument_name')
        cols.remove('filter_name')

        all_cols = cols + extra_cols
        df = DataUtils.CreateEmptyDataFrame(all_cols)

        # sanity - check if tile_dataframe is empty
        if len(image_dataframe) <= 0:
            print("`image_dataframe` is empty")
            return df

        UPSERT_IMAGE_SQL = """
        INSERT INTO Image (ra, decl, obs_start, exp_time, target_name, base_filename, band_id, instrument_id, mjd_avg)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            ra = VALUES(ra),
            decl = VALUES(decl),
            obs_start = VALUES(obs_start),
            exp_time = VALUES(exp_time),
            target_name = VALUES(target_name),
            band_id = VALUES(band_id),
            instrument_id = VALUES(instrument_id),
            mjd_avg = VALUES(mjd_avg);
        """

        batch_insert_arr = []
        for index, image_row in image_dataframe.iterrows():

            ra, dec, obs_date, exp_time, tgt_name, base_filename, filt_name, inst_name, mjd_avg = list(image_row)
            band_id = self.bands[filt_name]
            inst_id = self.instruments[inst_name]

            batch_insert_arr.append(tuple([ra, dec, obs_date, exp_time, tgt_name, base_filename, band_id,
                                           inst_id, mjd_avg]))


        print("Performing UPSERT of raw images to the database...")
        self._execute_batch(sql_query=UPSERT_IMAGE_SQL, batch_values=batch_insert_arr)

        # return newly created Images
        df = self.retrieve_images()
        return df

    # UNSAFE!! This is a direct SQL Injection -- to be used only by adults!!
    def import_images_to_lvl2cals(self, image_where):

        # 1. Get files from db that match query
        # 2. Resolve the filenames into the paths in the rawdata_dir
        # 3. Unpack those files on disk (create value-added objects like polygons, etc)
        # 4. INSERT those into the Lvl2Cal table

        predicate = ' AND '.join(image_where)
        image_select = 'SELECT id, base_filename FROM Image WHERE %s;' % predicate

        db_results = self._execute_single(image_select, fetch_results=True)
        rows_to_insert = []
        for img in db_results:
            image_id = img[0]
            base_filename = img[1]
            img_path = os.path.join(self.rawimage_dir, base_filename)

            h_sci = fits.getheader(img_path, 'SCI')
            h_pri = fits.getheader(img_path, 'PRIMARY')
            f_wcs = WCS(h_sci)

            poly = f_wcs.calc_footprint()
            skycoord_poly = SkyCoord(poly, unit="deg", frame="icrs")
            filt_name = h_pri["FILTER"]
            ps = self.platescales[filt_name]
            current_file_ext = os.path.splitext(base_filename)[-1]

            rows_to_insert.append(tuple([current_file_ext, json.dumps(skycoord_poly.to_string()), ps,
                                         image_id, self.lvl2_statuses["NotStarted"]]))

        UPSERT_LVL2_SQL = """
                        INSERT INTO Lvl2Cal (current_file_ext, poly, plate_scale, image_id, lvl2cal_status_id)
                        VALUES (%s, %s, %s, %s, %s)
                        ON DUPLICATE KEY UPDATE
                            current_file_ext = VALUES(current_file_ext),
                            poly = VALUES(poly),
                            plate_scale = VALUES(plate_scale),
                            lvl2cal_status_id = VALUES(lvl2cal_status_id);
                        """

        print("Performing UPSERT of lvl2 cals to the database...")
        self._execute_batch(sql_query=UPSERT_LVL2_SQL, batch_values=rows_to_insert)

        # return newly created Images
        df = self.retrieve_lvl2_cals()
        return df

    def save_lvl2_cals(self, lvl2cal_dataframe):

        # image_id is UNIQUE, and should act as the UPSERT key
        rows_to_upsert = []

        for index, row in lvl2cal_dataframe.iterrows():
            image_id = row["image_id"]
            current_file_ext = row["current_file_ext"]
            poly = row["poly"]
            plate_scale = row["plate_scale"]
            lvl2cal_status_id = row["lvl2cal_status_id"]

            rows_to_upsert.append(tuple([
                current_file_ext, json.dumps(poly.to_string()), plate_scale, image_id, lvl2cal_status_id
            ]))

        UPSERT_LVL2_SQL = """
            INSERT INTO Lvl2Cal (current_file_ext, poly, plate_scale, image_id, lvl2cal_status_id)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                current_file_ext = VALUES(current_file_ext),
                poly = VALUES(poly),
                plate_scale = VALUES(plate_scale),
                lvl2cal_status_id = VALUES(lvl2cal_status_id);
            """

        print("Performing UPSERT of lvl2 cals to the database...")
        self._execute_batch(sql_query=UPSERT_LVL2_SQL, batch_values=rows_to_upsert)

        # return newly created Images
        df = self.retrieve_lvl2_cals()
        return df


    def retrieve_lvl2_cals(self):

        dataframe_cols = ['lvl2cal_id', 'image_id', 'ra', 'decl', 'obs_start', 'exp_time', 'target_name', 'base_filename',
                       'current_file_ext', 'mjd_avg', 'poly', 'plate_scale', 'band_id', 'instrument_id', 'lvl2cal_status_id',
                       'moc', 'central_coord']

        df = DataUtils.CreateEmptyDataFrame(dataframe_cols)

        SELECT_JOINED_IMAGE_LVL2 = '''
            SELECT
                 lvl2.id as lvl2cal_id, i.id as image_id, i.ra, i.decl, i.obs_start, i.exp_time, i.target_name, i.base_filename,
                 lvl2.current_file_ext, i.mjd_avg, lvl2.poly, lvl2.plate_scale, i.band_id, i.instrument_id, lvl2.lvl2cal_status_id
            FROM Lvl2Cal lvl2
            JOIN Image i on i.id = lvl2.image_id;
        '''
        db_results = self._execute_single(SELECT_JOINED_IMAGE_LVL2, fetch_results=True)

        # Sanity, return empty DataFrame if there's no data in the Image table
        data_rows_populated = db_results is not None and len(db_results) > 0
        if not data_rows_populated:
            return df

        # HACK - 'tis a bit dirty.
        poly_index = 10
        ra_index = 2
        dec_index = 3
        for i, result in enumerate(db_results):
            # Can't replace indices in a tuple -> convert to list
            _result = list(result)

            # Generate SkyCoord poly -> MOC
            skycoord_poly = SkyCoord(json.loads(_result[poly_index]), unit=u.degree, frame="icrs")
            _result[poly_index] = skycoord_poly

            _result.append(MOC.from_polygon_skycoord(skycoord_poly, complement=False,
                                                     max_depth=self.data_util.moc_max_depth))
            _result.append(SkyCoord(_result[ra_index], _result[dec_index], unit=u.degree, frame='icrs'))

            # re-cast as a tuple
            db_results[i] = tuple(_result)

        df = DataUtils.CreateDataFrame(dataframe_cols, db_results)

        if len(df) <= 0:
            print("Lvl2s do not exist")

        print("Returning Image JOIN with Lvl2s table from database.")
        return df

    def retrieve_images(self):

        select_cols = ['id', 'ra', 'decl', 'obs_start', 'exp_time', 'target_name', 'base_filename',
                      'band_id', 'instrument_id', 'mjd_avg']

        col_str = ", ".join(select_cols)
        df = DataUtils.CreateEmptyDataFrame(select_cols)

        select_image_sql = "SELECT %s FROM Image;"
        query2execute = select_image_sql % col_str
        db_results = self._execute_single(query2execute, fetch_results=True)

        # Sanity, return empty DataFrame if there's no data in the Image table
        data_rows_populated = db_results is not None and len(db_results) > 0
        if not data_rows_populated:
            return df

        df = DataUtils.CreateDataFrame(select_cols, db_results)

        if len(df) <= 0:
            print("Images do not exist")

        print("Returning image table from database.")
        return df

    def save_project(self, project_name):
        '''
        Creates a project record.
        Args:
            project_name (str): The project name to save
        Returns:
            returns a tuple of (Row_id, Project_Name) if successful, or (-1, Project_Name) on error
        '''
        # Sanity - check if it exists first:
        df = self.retrieve_project(project_name)
        if len(df) > 0:
            print("Record already exists! Returning existing...")
        else:
            sql_project_insert = '''
                INSERT INTO Project (name) VALUES ('%s');
            '''
            query2execute = sql_project_insert % project_name
            self._execute_single(sql_query=query2execute)
            sql_project_select = "SELECT id, name FROM Project WHERE name='%s';" % project_name
            db_results = self._execute_single(sql_query=sql_project_select, fetch_results=True)
            project_id = db_results[0][0]
            print(project_id)

            if project_id > -1:
                df = self.retrieve_project(project_name)
            else:
                raise Exception("Project INSERT failed!")
        return df

    def retrieve_project(self, project_name):
        '''
       Retrieves a project record by name
       Args:
           project_name (str): The project name to retrieve
       Returns:
           returns a tuple of (Row_id, Project_Name) if successful, or (-1, Project_Name) on error
       '''

        cols = ['id', 'name']
        col_str = ", ".join(cols)
        sql_project_select = '''
            SELECT %s FROM Project WHERE name='%s';
        '''
        query2execute = sql_project_select % (col_str, project_name)
        db_results = self._execute_single(sql_query=query2execute, fetch_results=True)
        df = DataUtils.CreateDataFrame(cols, db_results)

        print("Returning Project: %s" % project_name)
        return df

    def retrieve_tiles(self, project_name):
        '''
       Retrieves tiles for a project
       Args:
           project_name (str): The project name to retrieve
       Returns:
           returns a dataframe of Tile objects
        '''
        select_cols = ['id', 'name', 'ra', 'decl', 'delta_ra', 'delta_decl', 'coord_sys', 'project_id', 'poly']
        return_cols = copy.deepcopy(select_cols)
        return_cols.append('moc')
        return_cols.append('central_coord')
        df = DataUtils.CreateEmptyDataFrame(return_cols)

        col_str = ", ".join(select_cols)
        sql_tile_select = '''
            SELECT %s FROM Tile WHERE project_id=%s;
        '''
        project_df = self.retrieve_project(project_name)

        if len(project_df) > 0:
            project_id = project_df.loc[0, 'id']
            query2execute = sql_tile_select % (col_str, project_id)
            db_results = self._execute_single(query2execute, fetch_results=True)

            # HACK - 'tis a bit dirty. Replace last field with MOC object
            for i, result in enumerate(db_results):
                # Can't replace indices in a tuple -> convert to list
                _result = list(result)

                # Generate SkyCoord poly -> MOC
                skycoord_poly = SkyCoord(json.loads(_result[-1]), unit=u.degree, frame="icrs")
                _result[-1] = skycoord_poly
                _result.append(MOC.from_polygon_skycoord(skycoord_poly, complement=False, max_depth=self.data_util.moc_max_depth))
                _result.append(SkyCoord(_result[2], _result[3], unit=u.degree, frame="icrs"))

                # re-cast as a tuple
                db_results[i] = tuple(_result)

            df = DataUtils.CreateDataFrame(return_cols, db_results)

            if len(df) <= 0:
                print("Tiles for `%s` do not exist" % project_name)
        else:
            print("Project `%s` does not exist" % project_name)

        print("Returning tiles for Project: %s" % project_name)
        return df

    def delete_tiles(self, project_name):
        project_df = self.retrieve_project(project_name)
        if len(project_df) > 0:
            project_id = project_df["id"][0]
            # Delete tile dependencies and then Delete tiles
            delete_tile_image_sql = '''
                DELETE ti
                FROM Tile_Image ti
                JOIN Tile t ON ti.tile_id = t.id
                JOIN Project p ON t.project_id = p.id
                WHERE p.id = %s;
            '''
            query2execute = delete_tile_image_sql % project_id
            self._execute_single(sql_query=query2execute)

            delete_tile_sql = '''
                DELETE FROM Tile t WHERE t.project_id = %s;
            '''
            query2execute = delete_tile_sql % project_id
            self._execute_single(sql_query=query2execute)

    def save_tiles(self, tile_dataframe, project_name, clobber=False):

        select_cols = ['id', 'name', 'ra', 'decl', 'delta_ra', 'delta_decl', 'coord_sys', 'project_id', 'poly']
        return_cols = copy.deepcopy(select_cols)
        return_cols.append('moc')
        return_cols.append('central_coord')
        df = DataUtils.CreateEmptyDataFrame(return_cols)

        # sanity - check if tile_dataframe is empty
        if len(tile_dataframe) <= 0:
            print("`tile_dataframe` is empty")
            return df

        # sanity - check for tile existence. if they exist, and clobber not True, return
        tile_df = self.retrieve_tiles(project_name)
        if len(tile_df) > 0:
            if not clobber:
                print("Tiles exist for Project `%s`. You must set `clobber=True` to overwrite. " % project_name)
                return df
            else:
                print("Clobbering existing tiles...")
                # Delete tile and dependencies
                self.delete_tiles(project_name)

        # Queries
        sql_tile_insert = '''
            INSERT INTO Tile
                (name, ra, decl, delta_ra, delta_decl, coord_sys, project_id, poly)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s);
        '''

        batch_insert_arr = []
        for index, tile_row in tile_dataframe.iterrows():

            tile_name = tile_row["name"]
            ra = tile_row["ra"]
            decl = tile_row["decl"]
            delta_ra = tile_row["delta_ra"]
            delta_decl = tile_row["delta_decl"]
            coord_sys = tile_row["coord_sys"]
            proj_id = tile_row["project_id"]
            poly = json.dumps(tile_row["poly"].to_string())

            values_to_insert = (
                tile_name,
                ra,
                decl,
                delta_ra,
                delta_decl,
                coord_sys,
                proj_id,
                poly
            )
            batch_insert_arr.append(tuple(values_to_insert))
        self._execute_batch(sql_query=sql_tile_insert, batch_values=batch_insert_arr)

        # return newly created tiles
        df = self.retrieve_tiles(project_name)
        return df

    def retrieve_tile_image(self, project_name, tile_dataframe, lvl2cal_dataframe):

        project_df = self.retrieve_project(project_name)
        if len(project_df) <= 0:
            print("No project by name `%s` exists! Returning empty dict..." % project_name)
            return {}

        project_id = project_df.loc[0, 'id']

        # lvl2cal_dataframe.iloc[0:0] => initialize a dataframe with the columns of lvl2cal_dataframe
        return_dict = { tile["id"]:lvl2cal_dataframe.iloc[0:0] for i, tile in tile_dataframe.iterrows() }
        select_cols = ['lvl2.id', 'lvl2.tile_id', 'lvl2.lvl2cal_id']
        return_cols = [s.replace('lvl2.', '') for s in select_cols]
        col_str = ",".join(select_cols)
        id_str = ",".join(str(x) for x in tile_dataframe["id"].to_list())

        tile_image_select = '''
            SELECT 
                %s 
            FROM Tile_Lvl2Cal lvl2
            JOIN Tile t on t.id = lvl2.tile_id
            WHERE Tile_id IN (%s) AND project_id = %s
        ''' % (col_str, id_str, project_id)
        tile_image_tuples = self._execute_single(tile_image_select, fetch_results=True)
        df = pd.DataFrame(data=tile_image_tuples, columns=return_cols)

        for index, datarow in tile_dataframe.iterrows():
            tile_id = datarow["id"]
            img_ids = df[df["tile_id"] == tile_id]["lvl2cal_id"].to_list()
            sub_df = lvl2cal_dataframe[lvl2cal_dataframe["lvl2cal_id"].isin(img_ids)].copy(deep=True)
            return_dict[tile_id] = sub_df

        print("Returning tile-lvl2 relation for Project: %s" % project_name)
        return return_dict

    # TODO: Plumb through the project name
    def save_tile_image_association(self, project_name, tile_dataframe, lvl2cal_dataframe):

        project_df = self.retrieve_project(project_name)
        if len(project_df) <= 0:
            print("No project by name `%s` exists! Returning empty dict..." % project_name)
            return {}

        project_id = project_df.loc[0, 'id']

        # Queries
        sql_tile_image_insert = '''
            INSERT INTO Tile_Lvl2Cal
                (lvl2cal_id, tile_id)
            VALUES (%s, %s);
        '''

        batch_insert_arr = []
        for t_index, tile in tile_dataframe.iterrows():

            tile_moc = tile["moc"]
            tile_id = tile["id"]

            for i_index, image in lvl2cal_dataframe.iterrows():

                image_moc = image["moc"]
                lvl2cal_id = image["lvl2cal_id"]
                intersection_moc = tile_moc.intersection(image_moc)

                if intersection_moc.sky_fraction > 0:
                    batch_insert_arr.append((lvl2cal_id, tile_id))

        self._execute_batch(sql_query=sql_tile_image_insert, batch_values=batch_insert_arr)

        return self.retrieve_tile_image(project_name, tile_dataframe, lvl2cal_dataframe)

    def retrieve_tile_epochs(self, tile_id, band_id, project_id):
        """
        retrieve epochs wrt project and tile from the repo
        """
        select_cols = ['id', 'start_date', 'end_date', 'start_mjd', 'end_mjd', 'tile_id', 'band_id', 'project_id']
        df = DataUtils.CreateEmptyDataFrame(select_cols)

        # sanity - check if tile_dataframe is empty
        if tile_id is None or project_id is None:
            print("Incomplete epoch data! Exiting...")
            return df

        # Queries
        sql_epoch_select = '''
            SELECT id, start_date, end_date, start_mjd, end_mjd, tile_id, band_id, project_id FROM Epoch 
            WHERE tile_id=%s AND band_id=%s AND project_id =%s;
        '''
        query2execute = sql_epoch_select % (tile_id, band_id, project_id)
        db_results = self._execute_single(query2execute, fetch_results=True)

        if len(db_results) > 0:
            df = DataUtils.CreateDataFrame(select_cols, db_results)

        return df

    # For now, don't allow clobbering... if epochs exist, then you can't add a duplicate.
    # TODO: implement logic to allow for clobbering/alterning epochs
    def save_tile_epochs(self, start_mjds, end_mjds, tile_id, band_id, project_id):
        """
        save epochs wrt project and tile to the repo
        """

        select_cols = ['id', 'start_date', 'end_date', 'start_mjd', 'end_mjd', 'tile_id', 'band_id', 'project_id']
        return_df = DataUtils.CreateEmptyDataFrame(select_cols)

        # sanity - check if tile_dataframe is empty
        if len(start_mjds) <= 0 or len(end_mjds) <= 0 or len(start_mjds) != len(end_mjds):
            print("`MJDs` are empty or are not equal dimension")
            return return_df

        # sanity - check for epoch existence. if they exist, don't re-add
        check_df = self.retrieve_tile_epochs(tile_id, band_id, project_id)
        existing_mjd_tups = []
        for index, epoch_row in check_df.iterrows():
            existing_mjd_tups.append((epoch_row['start_mjd'], epoch_row["end_mjd"]))

        # rows to potentially save
        candidate_epochs = [(s, e) for s, e in zip(start_mjds, end_mjds)]
        unique_start_mjds = []
        unique_end_mjds = []
        for epoch_tuple in candidate_epochs:
            if epoch_tuple not in existing_mjd_tups:
                unique_start_mjds.append(epoch_tuple[0])
                unique_end_mjds.append(epoch_tuple[1])
            else:
                mjd_str = "%s-%s" % epoch_tuple
                print("Epoch exists for Project=`%s`, Band=`%s`, and Tile=`%s` for MJDs:%s."
                    % (project_id, band_id, tile_id, mjd_str))

        if len(unique_start_mjds) <= 0:
            print("No unique epochs to save!")
            return return_df


        # if len(df) > 0 and dupes:
        #     # if not clobber:
        #     mjd_str = ",".join(["%s - %s" % (s,e) for s, e in zip(start_mjds, end_mjds)])
        #
        #     print("Epochs exist for Project=`%s`, Band=`%s`, and Tile=`%s` for MJDs:%s . You must set `clobber=True` to overwrite. "
        #           % (project_id, band_id, tile_id, mjd_str))
        #     return df
            # else:
            #     print("Clobbering existing epochs...")
                # Delete tile and dependencies
                # self.delete_tiles(project_name)


        # insert_cols = ['start_date', 'end_date', 'start_mjd', 'end_mjd', 'tile_id', 'band_id', 'project_id', ]

        # return_cols = copy.deepcopy(insert_cols)
        # return_cols.insert(0, 'id')
        # # return_cols.append('start_mjd')
        # # return_cols.append('end_mjd')
        # df = DataUtils.CreateEmptyDataFrame(return_cols)
        #
        # # sanity - check if tile_dataframe is empty
        # if len(start_mjds) <= 0 or len(start_mjds) != len(end_mjds) or tile_id is None or project_id is None:
        #     print("Incomplete epoch data! Exiting...")
        #     return df

        # obs_starts = Time(start_mjds, format='mjd').isot
        # obs_ends = Time(end_mjds, format='mjd').isot
        obs_starts = Time(unique_start_mjds, format='mjd').isot
        obs_ends = Time(unique_end_mjds, format='mjd').isot

        # Queries
        sql_epoch_insert = '''
            INSERT INTO Epoch
                (start_date, end_date, start_mjd, end_mjd, tile_id, band_id, project_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s);
        '''

        batch_insert_arr = []
        for start, end, s_mjd, e_mjd in zip(obs_starts, obs_ends, start_mjds, end_mjds):
            values_to_insert = (
                start,
                end,
                int(s_mjd),
                int(e_mjd),
                int(tile_id),
                int(band_id),
                int(project_id)
            )
            batch_insert_arr.append(values_to_insert)
        self._execute_batch(sql_query=sql_epoch_insert, batch_values=batch_insert_arr)

        # return newly created Epochs
        return_df = self.retrieve_tile_epochs(tile_id, band_id, project_id)
        return return_df

    # TODO: I don't like this method... it's inconsistent and I am not sure it's needed
    def retrieve_epoch_lvl2cal_association(self, epoch_id):

        select_cols = ['id', 'epoch_id', 'lvl2cal_id']
        col_str = ",".join(select_cols)

        epoch_lvl2_select = '''
            SELECT %s FROM Lvl2Cal_Epoch WHERE epoch_id =%s
        ''' % (col_str, epoch_id)
        epoch_lvl2_tuples = self._execute_single(epoch_lvl2_select, fetch_results=True)

        df = pd.DataFrame(data=epoch_lvl2_tuples, columns=select_cols)

        return df

    def save_epoch_lvl2cal_association(self, epoch_id, lvl2cal_dataframe):
        insert_cols = ['id', 'epoch_id', 'lvl2cal_id']
        return_df = DataUtils.CreateEmptyDataFrame(insert_cols)

        # sanity - check if tile_dataframe is empty
        if epoch_id <= 0 or len(lvl2cal_dataframe) <= 0:
            print("No epoch ID or lvl2cal dataframe is empty! Skipping...")
            return return_df

        # sanity - check for epoch existence. if they exist, don't re-add
        check_df = self.retrieve_epoch_lvl2cal_association(epoch_id)
        existing_associations = []
        for index, epoch_lvl2_row in check_df.iterrows():
            lvl2cal_id = epoch_lvl2_row["lvl2cal_id"]
            existing_associations.append(lvl2cal_id)

        # print(existing_associations)

        # rows to potentially save
        new_lvl2cal_associations = []
        for lvl2cal_id in lvl2cal_dataframe.lvl2cal_id:
            if lvl2cal_id not in existing_associations:
                new_lvl2cal_associations.append(lvl2cal_id)
            else:
                print("Lvl2Cal-Epoch association exists for Epoch ID:%s and Lvl2Cal ID: %s"
                      % (epoch_id, lvl2cal_id))

        # print(new_lvl2cal_associations)

        if len(new_lvl2cal_associations) <= 0:
            print("No unique lvl2-epochs to save!")
            return return_df

        # Queries
        sql_lvl2_epoch_insert = '''
            INSERT INTO Lvl2Cal_Epoch
                (epoch_id, lvl2cal_id)
            VALUES (%s, %s);
        '''

        batch_insert_arr = []
        for lvl2cal_id in new_lvl2cal_associations:
            values_to_insert = (
                epoch_id,
                lvl2cal_id
            )
            batch_insert_arr.append(values_to_insert)
        self._execute_batch(sql_query=sql_lvl2_epoch_insert, batch_values=batch_insert_arr)

        # return newly created associations
        return_df = self.retrieve_epoch_lvl2cal_association(epoch_id)
        return return_df

    def retrieve_tile_lvl3mosaic(self, project_id, tile_id):

        return_dict = {}
        for i, tile in tile_dataframe.iterrows():
            return_dict[tile["id"]] = []

        select_cols = ['id', 'tile_id', 'lvl2cal_id']
        col_str = ",".join(select_cols)
        id_str = ",".join(str(x) for x in tile_dataframe["id"].to_list())
        tile_image_select = '''
            SELECT %s FROM Tile_Lvl2Cal WHERE Tile_id IN (%s)
        ''' % (col_str, id_str)
        tile_image_tuples = self._execute_single(tile_image_select, fetch_results=True)
        df = pd.DataFrame(data=tile_image_tuples, columns=select_cols)

        select_cols = ['lvl3.id', 'target_plate_scale', 'filename', 'lvl3.band_id', 'epoch_id',
                       'instrument_id', 'lvl3mosaic_status_id', 'lvl3.tile_id', 'moc_str',
                       'lvl3.project_id', 'ra', 'decl', 'poly', 'start_mjd', 'end_mjd']

        return_cols = [s.replace('lvl3.id', 'lvl3mosaic_id') for s in select_cols]
        return_cols = [s.replace('lvl3.', '') for s in return_cols]
        # return_cols = [s.replace('lvl3.tile_id', 'tile_id') for s in return_cols]
        return_cols = [s.replace('moc_str', 'footprint_moc') for s in return_cols]
        return_cols = [s.replace('poly', 'tile_moc') for s in return_cols]
        return_cols.append('central_coord')

        col_str = ",".join(select_cols)
        lvl3mosaic_select = '''
            SELECT
                %s
            FROM Lvl3Mosaic lvl3 
            JOIN Tile t on t.id = lvl3.tile_id
            JOIN Epoch e on e.id = lvl3.epoch_id
            WHERE
                lvl3.epoch_id = %s AND
                lvl3.band_id = %s AND
                lvl3.tile_id = %s AND
                lvl3.project_id = %s
        ''' % (col_str, epoch_id, band_id, tile_id, project_id)

        # print(lvl3mosaic_select)

        db_results = self._execute_single(lvl3mosaic_select, fetch_results=True)



        for index, datarow in tile_dataframe.iterrows():
            tile_id = datarow["id"]
            img_ids = df[df["tile_id"] == tile_id]["lvl2cal_id"].to_list()
            sub_df = lvl2cal_dataframe[lvl2cal_dataframe["lvl2cal_id"].isin(img_ids)].copy(deep=True)
            return_dict[tile_id].append(sub_df)





    def retrieve_lvl3mosaic(self, project_id, tile_id, band_id, epoch_id):
        select_cols = ['lvl3.id', 'target_plate_scale', 'filename', 'lvl3.band_id', 'epoch_id',
                       'instrument_id', 'lvl3mosaic_status_id', 'lvl3.tile_id', 'moc_str',
                       'lvl3.project_id', 'ra', 'decl', 'poly', 'start_mjd', 'end_mjd']

        return_cols = [s.replace('lvl3.id', 'lvl3mosaic_id') for s in select_cols]
        return_cols = [s.replace('lvl3.', '') for s in return_cols]
        return_cols = [s.replace('moc_str', 'footprint_moc') for s in return_cols]
        return_cols = [s.replace('poly', 'tile_moc') for s in return_cols]
        return_cols.append('central_coord')

        df = DataUtils.CreateEmptyDataFrame(return_cols)

        col_str = ",".join(select_cols)
        lvl3mosaic_select = '''
                    SELECT
                        %s
                    FROM Lvl3Mosaic lvl3 
                    JOIN Tile t on t.id = lvl3.tile_id
                    JOIN Epoch e on e.id = lvl3.epoch_id
                    WHERE
                        lvl3.epoch_id = %s AND
                        lvl3.band_id = %s AND
                        lvl3.tile_id = %s AND
                        lvl3.project_id = %s
                ''' % (col_str, epoch_id, band_id, tile_id, project_id)

        db_results = self._execute_single(lvl3mosaic_select, fetch_results=True)

        # Sanity, return empty DataFrame if there's no data in the Image table
        data_rows_populated = db_results is not None and len(db_results) > 0

        if not data_rows_populated:
            print("Lvl3Mosaic does not exist for Project ID=`%s`, Tile ID=`%s`, Band ID=`%s`, Epoch ID=`%s`. Returning... "
                  % (project_id, tile_id, band_id, epoch_id))
            return df

        # HACK - 'tis a bit dirty.
        moc_index = 8
        ra_index = 10
        decl_index = 11
        poly_index = 12
        for i, result in enumerate(db_results):
            # Can't replace indices in a tuple -> convert to list
            _result = list(result)

            moc_str = _result[moc_index]
            moc = MOC.from_str(moc_str)
            _result[moc_index] = moc

            # Generate SkyCoord poly -> MOC
            skycoord_poly = SkyCoord(json.loads(_result[poly_index]), unit=u.degree, frame="icrs")
            _result[poly_index] = MOC.from_polygon_skycoord(skycoord_poly, complement=False,
                                                            max_depth=self.data_util.moc_max_depth)

            _result.append(SkyCoord(_result[ra_index], _result[decl_index], unit=u.degree, frame='icrs'))

            # re-cast as a tuple
            db_results[i] = tuple(_result)

        df = DataUtils.CreateDataFrame(return_cols, db_results)

        if len(df) <= 0:
            print("Lvl3 mosaic does not exist")

        print("Returning Lvl3Mosaic JOIN with Tile and Epoch from database.")
        return df

    def retrieve_lvl3mosaic_by_project(self, project_name):

        project_df = self.retrieve_project(project_name)
        if len(project_df) <= 0:
            print("No project by name `%s` exists! Returning empty dict..." % project_name)
            return {}
        project_id = project_df.loc[0, 'id']

        select_cols = ['lvl3.id', 'target_plate_scale', 'filename', 'lvl3.band_id', 'epoch_id',
                       'instrument_id', 'lvl3mosaic_status_id', 'lvl3.tile_id', 'moc_str',
                       'lvl3.project_id', 'ra', 'decl', 'poly', 'start_mjd', 'end_mjd']

        return_cols = [s.replace('lvl3.id', 'lvl3mosaic_id') for s in select_cols]
        return_cols = [s.replace('lvl3.', '') for s in return_cols]
        return_cols = [s.replace('moc_str', 'footprint_moc') for s in return_cols]
        return_cols = [s.replace('poly', 'tile_moc') for s in return_cols]
        return_cols.append('central_coord')

        df = DataUtils.CreateEmptyDataFrame(return_cols)

        col_str = ",".join(select_cols)
        lvl3mosaic_select = '''
                    SELECT
                        %s
                    FROM Lvl3Mosaic lvl3 
                    JOIN Tile t on t.id = lvl3.tile_id
                    JOIN Epoch e on e.id = lvl3.epoch_id
                    WHERE
                        lvl3.project_id = %s
                ''' % (col_str, project_id)

        db_results = self._execute_single(lvl3mosaic_select, fetch_results=True)

        # Sanity, return empty DataFrame if there's no data in the Image table
        data_rows_populated = db_results is not None and len(db_results) > 0

        if not data_rows_populated:
            print(
                "Lvl3Mosaic does not exist for Project ID=`%s`. Returning... "
                % (project_id))
            return df

        # HACK - 'tis a bit dirty.
        moc_index = 8
        ra_index = 10
        decl_index = 11
        poly_index = 12
        for i, result in enumerate(db_results):
            # Can't replace indices in a tuple -> convert to list
            _result = list(result)

            moc_str = _result[moc_index]
            moc = MOC.from_str(moc_str)
            _result[moc_index] = moc

            # Generate SkyCoord poly -> MOC
            skycoord_poly = SkyCoord(json.loads(_result[poly_index]), unit=u.degree, frame="icrs")
            _result[poly_index] = MOC.from_polygon_skycoord(skycoord_poly, complement=False,
                                                            max_depth=self.data_util.moc_max_depth)

            _result.append(SkyCoord(_result[ra_index], _result[decl_index], unit=u.degree, frame='icrs'))

            # re-cast as a tuple
            db_results[i] = tuple(_result)

        df = DataUtils.CreateDataFrame(return_cols, db_results)

        if len(df) <= 0:
            print("Lvl3 mosaic does not exist")

        print("Returning Lvl3Mosaic JOIN with Tile and Epoch from database for Project: `%s`" % project_name)
        return df

    def save_lvl3mosaic(self, project_id, tile_id, band_id, epoch_id, in_epoch_lvl2):
        dataframe_cols = ['id', 'target_plate_scale', 'filename', 'band_id', 'epoch_id', 'instrument_id',
                       'lvl3mosaic_status_id', 'tile_id', 'moc_str', 'project_id'
        ]
        df = DataUtils.CreateEmptyDataFrame(dataframe_cols)

        col_str = ",".join(dataframe_cols)
        lvl3mosaic_select = '''
            SELECT
                %s
            FROM Lvl3Mosaic
            WHERE
                epoch_id = %s AND
                band_id = %s AND
                tile_id = %s AND
                project_id = %s
        ''' % (col_str, epoch_id, band_id, tile_id, project_id)
        db_results = self._execute_single(lvl3mosaic_select, fetch_results=True)

        # Sanity, return empty DataFrame if there's no data in the Image table
        data_rows_populated = db_results is not None and len(db_results) > 0
        if data_rows_populated:
            print("Lvl3Mosaic exists for Project ID=`%s`, Tile ID=`%s`, Band ID=`%s`, Epoch ID=`%s`. You must remove "
                  "downstream dependencies and this record to re-create."
                  % (project_id, tile_id, band_id, epoch_id))
            return df

        # Sanity - retrieve tile and epoch data
        # TODO: What does this look like to fail?
        tile_select = 'SELECT id, name FROM Tile WHERE id=%s' % tile_id
        tile_result = self._execute_single(tile_select, fetch_results=True)
        if tile_result is None or len(tile_result) != 1:
            print("Unknown tile id! `%s`. Returning..." % tile_id)
            return df

        epoch_select = 'SELECT id, start_mjd, end_mjd FROM Epoch WHERE id=%s' % epoch_id
        epoch_result = self._execute_single(epoch_select, fetch_results=True)
        if epoch_result is None or len(epoch_result) != 1:
            print("Unknown epoch id! `%s`. Returning..." % epoch_id)
            return df

        # Resolve the instrument ID and the platescale (will be the same for all included images)
        lv3_status_id = self.lvl3_statuses['NotStarted']
        instrument_id = in_epoch_lvl2['instrument_id'].unique()[0]
        instrument_name = self.reverse_instruments[instrument_id].replace(" ", "_")
        plate_scale = in_epoch_lvl2['plate_scale'].unique()[0]
        filt_name = self.reverse_bands[band_id].replace(" ", "_")
        tile_name = tile_result[0][1].replace(" ", "_")
        start_mjd = epoch_result[0][1]
        end_mjd = epoch_result[0][2]
        proj_name = self.project[1].replace(" ", "_")

        lvl3_mosaic_filename = "{project_name}_{instr_name}_{tile_name}_{filter_name}_{mjd_start}_{mjd_end}_{plate_scale}.lvl3.fits".format(
            project_name=proj_name, instr_name=instrument_name, tile_name=tile_name, filter_name=filt_name,
            mjd_start=start_mjd, mjd_end=end_mjd, plate_scale=plate_scale
        )

        UPSERT_LVL3_SQL = """
            INSERT INTO Lvl3Mosaic 
                (target_plate_scale, filename, band_id, epoch_id, instrument_id, lvl3mosaic_status_id, tile_id, moc_str, 
                project_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                target_plate_scale = VALUES(target_plate_scale),
                band_id = VALUES(band_id),
                epoch_id = VALUES(epoch_id),
                instrument_id = VALUES(instrument_id),
                lvl3mosaic_status_id = VALUES(lvl3mosaic_status_id),
                tile_id = VALUES(tile_id),
                moc_str = VALUES(moc_str),
                project_id = VALUES(project_id);
        """

        # print(len(in_epoch_lvl2.moc))
        #
        # raise Exception("Stop!")

        lvl3_moc = DataUtils.Get_Unioned_MOC(list(in_epoch_lvl2.moc))
        moc_str = lvl3_moc.to_string(format='ascii')

        lvl3mosaic_payload = tuple([str(plate_scale), lvl3_mosaic_filename, str(band_id), str(epoch_id),
                                    str(instrument_id), str(lv3_status_id), str(tile_id), moc_str, str(project_id)])
        print("Performing UPSERT of lvl3mosaic to the database...")
        self._execute_batch(sql_query=UPSERT_LVL3_SQL, batch_values=[lvl3mosaic_payload])

        return self.retrieve_lvl3mosaic(project_id, tile_id, band_id, epoch_id)



    # def retrieve_lvl3_mosaics(self, project_id):
    #     """
    #     Retrieves Lvl3Mosaic records from the database.
    #     Returns all model fields as DataFrame columns, including MOC and central_coord.
    #     """
    #     select_cols = [
    #         'id', 'tile_id', 'epoch_id', 'band_id', 'instrument_id',
    #         'target_plate_scale', 'filename', 'lvl3mosaic_status_id', 'poly', 'plate_scale'
    #     ]
    #     return_cols = copy.deepcopy(select_cols)
    #     return_cols.append('moc')
    #     return_cols.append('central_coord')
    #     df = self.data_util.CreateEmptyDataFrame(return_cols)
    #
    #     # SQL query to select all fields from Lvl3Mosaic
    #     col_str = ", ".join(select_cols)
    #     SELECT_LVL3_MOSAIC_SQL = f"SELECT {col_str} FROM Lvl3Mosaic WHERE project_id = {project_id};"
    #     db_results = self._execute_single(sql_query=SELECT_LVL3_MOSAIC_SQL, fetch_results=True)
    #
    #     if not db_results:
    #         print("No Lvl3 Mosaics found.")
    #         return df
    #
    #     processed_results = []
    #     # Indices for poly, tile_id, epoch_id, band_id, instrument_id
    #     poly_idx = select_cols.index('poly')
    #     # Assuming ra/decl for central_coord can be derived from the tile, or from poly centroid
    #     # For simplicity, we'll derive central_coord from poly if available, otherwise set to None
    #     # In a real scenario, you might join with Tile table to get its RA/Decl for central_coord
    #     # For this example, we'll use the centroid of the poly if it exists.
    #
    #     for result in db_results:
    #         _result = list(result)
    #         current_poly_str = _result[poly_idx]
    #         skycoord_poly = None
    #         moc = None
    #         central_coord = None
    #
    #         if current_poly_str:
    #             try:
    #                 skycoord_poly = SkyCoord(json.loads(current_poly_str), unit=u.degree, frame="icrs")
    #                 moc = MOC.from_polygon_skycoord(skycoord_poly, complement=False,
    #                                                 max_depth=self.data_util.moc_max_depth)
    #                 # For central_coord, using the centroid of the polygon
    #                 if skycoord_poly.shape[0] > 0:  # Check if polygon has points
    #                     # Simple centroid approximation for demonstration
    #                     avg_ra = np.mean(skycoord_poly.ra.deg)
    #                     avg_dec = np.mean(skycoord_poly.dec.deg)
    #                     central_coord = SkyCoord(avg_ra, avg_dec, unit=u.degree, frame='icrs')
    #             except json.JSONDecodeError:
    #                 print(f"Warning: Could not decode JSON for poly in Lvl3Mosaic: {current_poly_str}")
    #             except Exception as e:
    #                 print(f"Error processing poly for Lvl3Mosaic: {e}")
    #
    #         _result[poly_idx] = skycoord_poly  # Replace string with SkyCoord object
    #         _result.append(moc)
    #         _result.append(central_coord)
    #         processed_results.append(tuple(_result))
    #
    #     df = self.data_util.CreateDataFrame(return_cols, processed_results)
    #     print("Returning Lvl3 Mosaics from database.")
    #     return df


class RepositoryFactory:
    """
    Factory class to create and provide the correct repository instance.
    """

    @staticmethod
    def get_repository(repo_type: str, config: dict) -> AbstractRepository:

        if repo_type.lower() == "mysql":
            return MySQLRepository(config)

        else:
            raise ValueError(f"Unknown repository type: {repo_type}")