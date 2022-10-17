import os
import glob

from tools import config
from pyghee.utils import log
from datetime import datetime

def determine_pr_dirs(pr_number):
    """
    Determine directories of the PR.
    """
    directories = []

    # PRs are under jobs_base_dir/YYYY.MM/pr_<id>
    #   ---> we may have to scan multiple YYYY.MM directories
    buildenv = config.get_section('buildenv')
    jobs_base_dir = buildenv.get('jobs_base_dir')
    date_pr_pattern = '......./pr_%s' % pr_number
    glob_str = os.path.join(jobs_base_dir,date_pr_pattern)
    pr_directories = glob.glob(glob_str)

    return directories

def deploy_built_artefacts(pr, event_info):
    """
    Deploy built artefacts.
    """
    log("Deploy built artefacts: PR#%s" % pr.number)
    # 1) determine if we have built something for PR before
    #    - PRs are under jobs_base_dir/YYYY.MM/pr_<id> ---> we may have to scan multiple YYYY.MM directories
    # 2) if so determine what we have built
    # 3) for each PR that matches check the status of jobs (SUCCESS or FAILURE)
    # 4) only use the last SUCCESSful one if any
    # 5) call function to deploy a single artefact

    # 1) determine if we have built something for PR before
    buildenv = config.get_section('buildenv')
    jobs_base_dir = buildenv.get('jobs_base_dir')
    date_pr_pattern = '......./pr_*'
    eessi_tarballs = glob.glob(os.path.join(sym_dst,tarball_pattern))
