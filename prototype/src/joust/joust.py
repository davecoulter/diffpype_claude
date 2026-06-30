from astropy.time import Time
from astropy.io import fits
from astroquery.mast import Observations
from astropy.coordinates import SkyCoord
import astropy.units as u
from astropy.table import Table
from QueryInterface import QueryInterface
from utils import get_config, Logging
from make_diffs import ImageSub
# from reprocess.reprocess import AutoProcess
import os


class Joust():

    # ================================================================
    def __init__(self):

        self.mode = 'custom'

        self.file = None
        self.template_file = None
        self.my_obs_id = None

        self.pid = 1783
        self.instrument = None
        self.filter = None

        self.file_mode = False
        self.obs_id_mode = False
        self.program_mode = False

        self.template_observatory = 'JWST'

        self.min_baseline = 30
        self.max_baseline = 365

        self.t_start = 60000

        self.verbose = False

        self.log = Logging()
        self.log_name = 'log.txt'

        self.reprocess = False

        self.run_jhat = True
        self.run_reproject = True
        self.reproject_sci = True  # DC: Hack -- trying to propagate a flag to flip the direction of reprojection

        self.save_intermediate_files = False
        self.output_dir = ''
        self.level = 3

        self.perform_dir_ops = True
        self.save_to_output = True
        self.is_jades = False
        self.is_cosmos = False
        self.is_aaih = False
        self.is_jhat_generic = False
        self.jhat_file = None
        self.custom_mask = None

        return

    # ================================================================

    # ================================================================
    def run(self, verbose=False):

        # Set verbosity
        self.verbose = verbose

        self.log.log('Starting up JOUST')
        if self.verbose:
            print('Starting up JOUST')

        if self.mode == 'custom':
            self.custom_mode()
        elif self.mode == 'query':
            self.query_mode()
        else:
            self.log.log("You must select either 'custom' or 'query' mode.")
            self.log.log("Exiting JOUST.")

            if self.verbose:
                print("You must select either 'custom' or 'query' mode.")
                print("Exiting JOUST.")

        return

    # ================================================================

    # ================================================================
    def custom_mode(self):

        #############################################################
        # Determine operating mode
        a = self.file is not None
        b = self.my_obs_id is not None
        c = self.pid is not None

        if a:
            self.file_mode = True
        elif ~a and b:
            self.obs_id_mode = True
        elif ~a and ~b and c:
            self.program_mode = True
        else:
            self.log.log("If using 'custom' mode, you must provide either a file path, an observation ID, or a PID.")

            if self.verbose:
                print("If using 'custom' mode, you must provide either a file path, an observation ID, or a PID.")

            return
        #############################################################

        # Create instance of MAST query class
        qi = QueryInterface()

        # Create instance of the reprocessing module
        # proc = AutoProcess()

        # Create instance of the image subtraction
        imsub = ImageSub()

        # Dave Hack -- stopping the native directory building since I am doing that in the driver program... temp fix
        imsub.perform_dir_ops = self.perform_dir_ops
        imsub.save_to_output = self.save_to_output
        imsub.working_dir = self.output_dir
        imsub.reproject_sci = self.reproject_sci
        imsub.is_jades = self.is_jades
        imsub.is_cosmos = self.is_cosmos
        imsub.is_aaih = self.is_aaih
        imsub.is_jhat_generic = self.is_jhat_generic
        imsub.jhat_file = self.jhat_file
        imsub.custom_mask = self.custom_mask

        #############################################################

        # If using a given input image with or without a template
        if self.file_mode:
            if self.template_file is not None:
                self.log.log('Using supplied template file.')
                if self.verbose:
                    print('Using supplied template file.')

                # DC: why does this get re-written?
                # self.output_dir = os.path.dirname(self.file)

                print("Processing image subtraction")
                imsub.process(self.file, self.template_file,
                              run_jhat=self.run_jhat,
                              run_reproject=self.run_reproject,
                              save_intermediate_files=self.save_intermediate_files,
                              output_dir=self.output_dir,
                              level=self.level)

            else:
                self.log.log('Getting observation information from file')
                if self.verbose:
                    print('Getting observation information from file.')

                # Get info from the input file for the query
                self.get_input_file_info()

                # Query for templates
                self.log.log('Querying MAST for template images near {},{}'.format(self.ra, self.dec))
                if self.verbose:
                    print('Querying MAST for template images near {},{}'.format(self.ra, self.dec))

                # Query using the coordinates of the input image
                obs = qi.query_coord(ra=self.ra, dec=self.dec)

                # Filter the query results by the input filter
                obs_filtered = qi.filter_obs(obs,
                                             filt=self.filter,
                                             t_start=self.t_start,
                                             t_min=self.min_baseline,
                                             t_max=self.max_baseline,
                                             telescope=self.template_observatory,
                                             instrument=self.instrument)

                # Query results might be empty, exit
                if len(obs_filtered) == 0:
                    self.log.log('Filtered table contains no entries. Quitting.')
                    if self.verbose:
                        print('Filtered table contains no entries. Quitting.')
                    return

                # Download the results
                else:
                    self.log.log('Downloading data from MAST.')
                    if self.verbose:
                        print('Downloading data from MAST.')
                    qi.download_obs(obs_filtered)

                # reprocess if desired
                if self.reprocess:
                    templates = []
                    proc.download_dir == 'mastDownload/'
                    for row in obs_filtered:
                        proc.obs_id = row['obs_id']
                        proc.process()

                        templates.append('processed_data/{}'.format(proc.outfile))

                # run subtraction
                for template in templates:
                    imsub.process(self, path, self.file, template)
        #############################################################

    #         if self.program_mode:
    #             # Query for template

    # Download Data
    # If Reprocess, Reprocess
    # make_diffs
    # Report results?

    # ================================================================

    # ================================================================
    def get_input_file_info(self):

        head1 = fits.open(self.file)[0].header
        head2 = fits.open(self.file)[1].header

        self.filter = head1['FILTER']
        self.t_start = head1['EXPSTART']
        self.pid = head1['PROGRAM']

        self.ra = head1['TARG_RA']
        self.dec = head1['TARG_DEC']

        self.targ_name = head1['TARGNAME']
        self.s_reg = head2['S_REGION']

        return
    # ================================================================
