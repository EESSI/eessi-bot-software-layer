# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Pedro Santos Neves (@Neves-P)
#
# license: GPLv2
#

# Standard library imports
import sys
import os
import shutil

# Third party imports (anything installed into the local Python environment)
from pyghee.utils import log

# Local application imports (anything from EESSI/eessi-bot-software-layer)


def move_to_trash_bin(trash_bin_dir, job_dirs):
    """
    Move directory to trash_bin_dir

    Args:
        trash_bin_dir (string): path to the trash_bin_dir. Defined in .cfg
        job_dirs (list): list with job directory names

    Returns:
        None (implicitly)
    """
    # idea:
    # - shutil.move YYYY.MM/pr_PR_NUM to trash_bin_dir
    # - need to obtain list of YYYY.MM/pr_PR_NUM directories from job dirs
    # - need to ensure that YYYY.MM under trash_bin_dir exists (or create it)
    # - then we can just move YYYY.MM/pr_PR_NUM to trash_bin_dir/YYYY.MM
    # - (LATER) we should also fix the symbolic links under job_ids_dir/finished
    #     (remove it for the job id and add a new one pointing to the new location)
    funcname = sys._getframe().f_code.co_name
    log(f"{funcname}(): trash_bin_dir = {trash_bin_dir}")

    # ensure the 'trash_bin_dir' exists
    os.makedirs(trash_bin_dir, exist_ok=True)

    pr_dirs = []
    for job_dir in job_dirs:
        pr_dir = os.path.dirname(job_dir)
        log(f"{funcname}(): adding PR dir '{pr_dir}' (from job dir '{job_dir}')")
        pr_dirs.append(pr_dir)

    # Move (or copy as fallback) entire pr_PR_NUM directories to trash_bin_dir/YYYY.MM
    pr_dirs = list(set(pr_dirs))  # get only unique dirs
    for pr_dir in pr_dirs:
        # determine YYYY.MM parent of pr_dir
        year_month_dir = pr_dir.split('/')[-2]
        # make sure that directory exists under trash_bin_dir
        target_bin_dir = os.path.join(trash_bin_dir, year_month_dir)
        os.makedirs(target_bin_dir, exist_ok=True)

        log(f"{funcname}(): attempting to move {pr_dir} to {target_bin_dir}")
        destination_dir = shutil.move(pr_dir, target_bin_dir)
        log(f"{funcname}(): moved {pr_dir} to {destination_dir}")

    return True
