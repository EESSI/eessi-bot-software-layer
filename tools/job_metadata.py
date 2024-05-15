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


# the job's working directory (JWD) and subdirectories may contain various
# files storing metadata for a job
# below, we define constants for sections and 'settings' in these files
#
# job config directory name and filename
JOB_CFG_DIRECTORY_NAME = "cfg"
JOB_CFG_FILENAME = "job.cfg"

# JWD/cfg/$JOB_CFG_FILENAME
JOB_CFG_ARCHITECTURE_SECTION = "architecture"
JOB_CFG_ARCHITECTURE_OS_TYPE = "os_type"
JOB_CFG_ARCHITECTURE_SOFTWARE_SUBDIR = "software_subdir"

JOB_CFG_REPOSITORY_SECTION = "repository"
JOB_CFG_REPOSITORY_CONTAINER = "container"
JOB_CFG_REPOSITORY_REPOS_CFG_DIR = "repos_cfg_dir"
JOB_CFG_REPOSITORY_REPO_ID = "repo_id"
JOB_CFG_REPOSITORY_REPO_NAME = "repo_name"
JOB_CFG_REPOSITORY_REPO_VERSION = "repo_version"

JOB_CFG_SITE_CONFIG_SECTION = "site_config"
JOB_CFG_SITE_CONFIG_BUILD_LOGS_DIR = "build_logs_dir"
JOB_CFG_SITE_CONFIG_CONTAINER_CACHEDIR = "container_cachedir"
JOB_CFG_SITE_CONFIG_HTTP_PROXY = "http_proxy"
JOB_CFG_SITE_CONFIG_HTTPS_PROXY = "https_proxy"
JOB_CFG_SITE_CONFIG_LOAD_MODULES = "load_modules"
JOB_CFG_SITE_CONFIG_LOCAL_TMP = "local_tmp"
JOB_CFG_SITE_CONFIG_SHARED_FS_PATH = "shared_fs_path"

# JWD/_bot_jobJOBID.metadata
JOB_PR_SECTION = "PR"
JOB_PR_REPO = "repo"
JOB_PR_PR_NUMBER = "pr_number"
JOB_PR_PR_COMMENT_ID = "pr_comment_id"

# JWD/_bot_jobJOBID.result
JOB_RESULT_SECTION = "RESULT"
# constants representing settings
JOB_RESULT_ARTEFACTS = "artefacts"
JOB_RESULT_COMMENT_DESCRIPTION = "comment_description"
JOB_RESULT_STATUS = "status"
# constants representing values for JOB_RESULT_STATUS (the values of these
# constants need to correspond to what the `bot/check-build.sh` script uses when
# writing the _bot_jobJOBID.result file)
JOB_RESULT_FAILURE = "FAILURE"
JOB_RESULT_SUCCESS = "SUCCESS"

# JWD/_bot_jobJOBID.test
JOB_TEST_SECTION = "TEST"
JOB_TEST_COMMENT_DESCRIPTION = "comment_description"
JOB_TEST_STATUS = "status"


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
    bot_jobfile[JOB_PR_SECTION] = {'repo': repo_name,
                                   'pr_number': pr_number,
                                   'pr_comment_id': pr_comment_id}
    bot_jobfile_path = os.path.join(job.working_dir, f'_bot_job{job_id}.metadata')
    with open(bot_jobfile_path, 'w') as bjf:
        bot_jobfile.write(bjf)
    log(f"{fn}(): created job metadata file {bot_jobfile_path}")


def determine_job_id_from_job_directory(job_directory, log_file=None):
    """
    Determine job id from a job directory.

    Args:
        job_directory (string): path to job directory
        log_file (string): path to log file

    Returns:
        (int): job id or 0
    """
    # job id could be found in
    # - current directory name
    # - part of a 'slurm-JOB_ID.out' file name
    # - part of a '_bot_jobJOB_ID.metadata' file
    # For now we just use the first alternative.
    job_dir_basename = os.path.basename(job_directory)
    from_dir_job_id = 0
    if job_dir_basename.replace('.', '', 1).isdigit():
        from_dir_job_id = int(job_dir_basename)
    return from_dir_job_id


def get_section_from_file(filepath, section, log_file=None):
    """
    Read filepath (ini/cfg format) and return contents of a section.

    Args:
        filepath (string): path to a metadata file
        section (string): name of the section to obtain contents for
        log_file (string): path to log file

    Returns:
        (ConfigParser): instance of ConfigParser corresponding to the section or None
    """
    # reuse function from module tools.job_metadata to read metadata file
    section_contents = None
    metadata = read_metadata_file(filepath, log_file=log_file)
    if metadata:
        # get section
        if section in metadata:
            section_contents = metadata[section]
        else:
            section_contents = {}

    return section_contents


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
