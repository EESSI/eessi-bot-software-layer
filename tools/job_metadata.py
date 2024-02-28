# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
import configparser
import os
import sys

# Third party imports (anything installed into the local Python environment)
from pyghee.utils import log

# Local application imports (anything from EESSI/eessi-bot-software-layer)
# (none yet)


def create_metadata_file(job, job_id, pr_comment):
    """
    Create job metadata file in job working directory

    Args:
        job (named tuple): key data about job that has been submitted
        job_id (string): id of submitted job
        pr_comment (PRComment): contains repo_name, pr_number and pr_comment_id

    Returns:
        None (implicitly)
    """
    fn = sys._getframe().f_code.co_name

    repo_name = pr_comment.repo_name
    pr_number = pr_comment.pr_number
    pr_comment_id = pr_comment.pr_comment_id

    # create _bot_job<jobid>.metadata file in the job's working directory
    bot_jobfile = configparser.ConfigParser()
    bot_jobfile['PR'] = {'repo': repo_name,
                         'pr_number': pr_number,
                         'pr_comment_id': pr_comment_id}
    bot_jobfile_path = os.path.join(job.working_dir, f'_bot_job{job_id}.metadata')
    with open(bot_jobfile_path, 'w') as bjf:
        bot_jobfile.write(bjf)
    log(f"{fn}(): created job metadata file {bot_jobfile_path}")


def read_metadata_file(metadata_path, log_file=None):
    """
    Read metadata file into ConfigParser instance

    Args:
        metadata_path (string): path to metadata file
        log_file (string): path to log file

    Returns:
        metadata as ConfigParser instance or None in case of failure
    """
    # TODO use function name in log messages

    # check if metadata file exists
    if os.path.isfile(metadata_path):
        log(f"Found metadata file at {metadata_path}", log_file)
        metadata = configparser.ConfigParser()
        try:
            metadata.read(metadata_path)
        except Exception as err:
            # Using error() would let the process exit. This is too harsh.
            # We just log() a message, return None and let the caller decide
            # what to do.
            log(f"Unable to read metadata file {metadata_path}: {err}")
            return None

        return metadata
    else:
        log(f"No metadata file found at {metadata_path}.", log_file)
        return None


def read_job_metadata_from_file(filepath, log_file=None):
    """
    Read job metadata from file

    Args:
        filepath (string): path to job metadata file
        log_file (string): path to log file

    Returns:
        job_metadata (dict): dictionary containing job metadata or None
    """

    metadata = read_metadata_file(filepath, log_file=log_file)
    if metadata:
        # get PR section
        if "PR" in metadata:
            metadata_pr = metadata["PR"]
        else:
            metadata_pr = {}
        return metadata_pr
    else:
        log(f"Metadata file '{filepath}' does not exist or could not be read")
        return None
