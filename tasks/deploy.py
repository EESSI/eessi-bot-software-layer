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
    print("jobs_base_dir = %s" % jobs_base_dir)
    date_pr_pattern = '[0-9][0-9][0-9][0-9].[0-9][0-9]/pr_%s/[0-9]*' % pr_number
    print("date_pr_pattern = %s" % date_pr_pattern)
    glob_str = os.path.join(jobs_base_dir,date_pr_pattern)
    print("glob_str = %s" % glob_str)
    pr_directories = glob.glob(glob_str)

    return pr_directories

def deploy_built_artefacts(pr, event_info):
    """
    Deploy built artefacts.
    """
    log("Deploy built artefacts: PR#%s" % pr.number)
    # 1) determine what has been built for the PR
    #    - PRs are under jobs_base_dir/YYYY.MM/pr_<id> ---> we may have
    #      to scan multiple YYYY.MM directories
    # 2) for each build check the status of jobs (SUCCESS or FAILURE)
    #    - scan slurm*out file for: No modules missing! & created messages
    # 3) for the successful ones, only use the last (use timestamp in
    #    filename) for each software subdir
    # 4) call function to deploy a single artefact per software subdir

    # 1) determine what has been built for the PR
    #    - PRs are under jobs_base_dir/YYYY.MM/pr_<id> ---> we may have
    #      to scan multiple YYYY.MM directories
    pr_dirs = determine_pr_dirs(pr.number)
    print("pr_dirs = '%s'" % ','.join(pr_dirs))


#    tarball_pattern = 
#    for pr_dir in pr_dirs:
#        eessi_tarballs = glob.glob(os.path.join(pr_dir,tarball_pattern))

