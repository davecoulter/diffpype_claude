import os
from astropy.io import fits
from pprint import pprint
from astropy.time import Time
from random import randint
from pathlib import Path
import os,shutil,glob,sys

# Dave Debug
import pdb;
# print("In `make_results_dir`")
# pdb.set_trace()

# rename based on:
#   1. field name (right now, take tile name)
#   2. filter
#   3. MJD -> utdate
#   4. unique ID (right now, VISIT_ID)


# `science_field_name` is for science images that share a single template, to keep file names of templates unique...
def generate_filename(fits_path, index_of_field_name, manual_field_name=None, science_field_name=None):


    field_name = manual_field_name
    if field_name is None:
        field_name = os.path.basename(fits_path).split("_")[index_of_field_name].lower()

    hdul = fits.open(fits_path)
    hdr = hdul[0].header

    filt = hdr["FILTER"].strip().lower()

    # Convert to datetime
    mjd = hdr["EXPMID"]
    t = Time(mjd, format='mjd')
    utc = t.to_datetime()
    utdate = "ut{year}{month}{day}".format(year=utc.year,
        month=str(utc.month).zfill(2), day=str(utc.day).zfill(2))

    # Just make sure we get a unique number
    id = str(randint(100, 999)).zfill(5)

    output_name = "{field_name}.{filter}.{utdate}.{id}.fits".format(field_name=field_name,
        filter=filt, utdate=utdate, id=id)

    if science_field_name is not None:
        output_name = "{field_name}.{filter}.{utdate}.{id}.{science_field_name}.fits".format(field_name=field_name,
        filter=filt, utdate=utdate, id=id, science_field_name=science_field_name)

    return output_name



def get_id_if_exists(base_dir, destination_file):

    file_name = os.path.basename(destination_file)

    # HACk:
    # split file_name into tokens, see if a file matches these (without matching the random ID)
    # Ex: p30.f444w.ut20231227.00317.fits
    tokens = file_name.split(".")
    field_name = tokens[0]
    filter_name = tokens[1]
    ut_date = tokens[2]

    pre_lim_matches = glob.glob("{base_dir}/{field_name}.{filter_name}.{ut_date}.*.fits".format(base_dir=base_dir, field_name=field_name, filter_name=filter_name, ut_date=ut_date))

    matches = []
    for p in pre_lim_matches:
        # We want to only match on the OG generated file name...
        if "_" in os.path.basename(p) or \
        "diff" in os.path.basename(p) or \
        "mask" in os.path.basename(p) or \
        "noise" in os.path.basename(p) or \
        "reg" in os.path.basename(p) or \
        "txt" in os.path.basename(p):
            continue
        else:
            matches.append(p)

    file_id = None
    if len(matches) == 1:
        # there is a file with these properties, return the ID
        existing_file = matches[0]
        existing_tokens = existing_file.split(".")
        file_id = existing_tokens[3]
    elif len(matches) == 0:
        # no match, return the id from the file path passed in
        file_id = tokens[3]
    else:
        # there is more than one file with the same properties -- this isn't handled, stop execution
        raise Exception("Too many files with the same properties! Check `%s` for duplicates!" % destination_file)

    return file_id