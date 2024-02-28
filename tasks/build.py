# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Kenneth Hoste (@boegel)
# author: Bob Droege (@bedroge)
# author: Hafsa Naeem (@hafsa-naeem)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
from collections import namedtuple
import configparser
from datetime import datetime, timezone
import json
import os
import shutil
import sys

# Third party imports (anything installed into the local Python environment)
from pyghee.utils import error, log
from retry.api import retry_call

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from connections import github
from tools import config, pr_comments, run_cmd
from tools.job_metadata import create_metadata_file


APP_NAME = "app_name"
ARCHITECTURE_TARGETS = "architecturetargets"
AWAITS_RELEASE = "awaits_release"
BUILDENV = "buildenv"
BUILD_JOB_SCRIPT = "build_job_script"
BUILD_LOGS_DIR = "build_logs_dir"
BUILD_PERMISSION = "build_permission"
CFG_DIRNAME = "cfg"
CONTAINER_CACHEDIR = "container_cachedir"
CURL_FAILURE = "curl_failure"
CURL_TIP = "curl_tip"
CVMFS_CUSTOMIZATIONS = "cvmfs_customizations"
DEFAULT_JOB_TIME_LIMIT = "24:00:00"
DOWNLOAD_PR_COMMENTS = "download_pr_comments"
ERROR_CURL = "curl"
ERROR_GIT_APPLY = "git apply"
ERROR_GIT_CHECKOUT = "git checkout"
ERROR_GIT_CLONE = "curl"
ERROR_NONE = "none"
GITHUB = "github"
GIT_CLONE_FAILURE = "git_clone_failure"
GIT_CLONE_TIP = "git_clone_tip"
GIT_CHECKOUT_FAILURE = "git_checkout_failure"
GIT_CHECKOUT_TIP = "git_checkout_tip"
GIT_APPLY_FAILURE = "git_apply_failure"
GIT_APPLY_TIP = "git_apply_tip"
HTTPS_PROXY = "https_proxy"
HTTP_PROXY = "http_proxy"
INITIAL_COMMENT = "initial_comment"
JOBS_BASE_DIR = "jobs_base_dir"
JOB_ARCHITECTURE = "architecture"
JOB_CFG_FILENAME = "job.cfg"
JOB_CONTAINER = "container"
JOB_LOCAL_TMP = "local_tmp"
JOB_HTTPS_PROXY = "https_proxy"
JOB_HTTP_PROXY = "http_proxy"
JOB_LOAD_MODULES = "load_modules"
JOB_OS_TYPE = "os_type"
JOB_REPOSITORY = "repository"
JOB_REPOS_CFG_DIR = "repos_cfg_dir"
JOB_REPO_ID = "repo_id"
JOB_REPO_NAME = "repo_name"
JOB_REPO_VERSION = "repo_version"
JOB_SITECONFIG = "site_config"
JOB_SOFTWARE_SUBDIR = "software_subdir"
LOAD_MODULES = "load_modules"
LOCAL_TMP = "local_tmp"
NO_BUILD_PERMISSION_COMMENT = "no_build_permission_comment"
REPOS_CFG_DIR = "repos_cfg_dir"
REPOS_REPO_NAME = "repo_name"
REPOS_REPO_VERSION = "repo_version"
REPOS_CONFIG_BUNDLE = "config_bundle"
REPOS_CONFIG_MAP = "config_map"
REPOS_CONTAINER = "container"
REPO_TARGETS = "repo_targets"
REPO_TARGET_MAP = "repo_target_map"
SHARED_FS_PATH = "shared_fs_path"
SLURM_PARAMS = "slurm_params"
SUBMITTED_JOB_COMMENTS = "submitted_job_comments"
SUBMIT_COMMAND = "submit_command"


Job = namedtuple('Job', ('working_dir', 'arch_target', 'repo_id', 'slurm_opts', 'year_month', 'pr_id'))

# global repo_cfg
repo_cfg = {}


def get_build_env_cfg(cfg):
    """
    Gets build environment values from configuration and process some
    (slurm_params and cvmfs_customizations)

    Args:
        cfg (ConfigParser): ConfigParser instance holding full configuration
            (typically read from 'app.cfg')

    Returns:
         (dict): dictionary with configuration settings in the 'buildenv' section
    """
    fn = sys._getframe().f_code.co_name

    buildenv = cfg[BUILDENV]

    jobs_base_dir = buildenv.get(JOBS_BASE_DIR)
    log(f"{fn}(): jobs_base_dir '{jobs_base_dir}'")
    config_data = {JOBS_BASE_DIR: jobs_base_dir}
    local_tmp = buildenv.get(LOCAL_TMP)
    log(f"{fn}(): local_tmp '{local_tmp}'")
    config_data[LOCAL_TMP] = local_tmp

    build_job_script = buildenv.get(BUILD_JOB_SCRIPT)
    log(f"{fn}(): build_job_script '{build_job_script}'")
    config_data[BUILD_JOB_SCRIPT] = build_job_script

    submit_command = buildenv.get(SUBMIT_COMMAND)
    log(f"{fn}(): submit_command '{submit_command}'")
    config_data[SUBMIT_COMMAND] = submit_command

    slurm_params = buildenv.get(SLURM_PARAMS)
    # always submit jobs with hold set, so job manager can release them
    slurm_params += ' --hold'
    log(f"{fn}(): slurm_params '{slurm_params}'")
    config_data[SLURM_PARAMS] = slurm_params

    shared_fs_path = buildenv.get(SHARED_FS_PATH)
    log(f"{fn}(): shared_fs_path: '{shared_fs_path}'")
    config_data[SHARED_FS_PATH] = shared_fs_path

    container_cachedir = buildenv.get(CONTAINER_CACHEDIR)
    log(f"{fn}(): container_cachedir '{container_cachedir}'")
    config_data[CONTAINER_CACHEDIR] = container_cachedir

    build_logs_dir = buildenv.get(BUILD_LOGS_DIR)
    log(f"{fn}(): build_logs_dir '{build_logs_dir}'")
    config_data[BUILD_LOGS_DIR] = build_logs_dir

    cvmfs_customizations = {}
    try:
        cvmfs_customizations_str = buildenv.get(CVMFS_CUSTOMIZATIONS)
        log("{fn}(): cvmfs_customizations '{cvmfs_customizations_str}'")

        if cvmfs_customizations_str is not None:
            cvmfs_customizations = json.loads(cvmfs_customizations_str)

        log(f"{fn}(): cvmfs_customizations '{json.dumps(cvmfs_customizations)}'")
    except json.JSONDecodeError as e:
        print(e)
        error(f"{fn}(): Value for cvmfs_customizations ({cvmfs_customizations_str}) could not be decoded.")

    config_data[CVMFS_CUSTOMIZATIONS] = cvmfs_customizations

    http_proxy = buildenv.get(HTTP_PROXY, None)
    log(f"{fn}(): http_proxy '{http_proxy}'")
    config_data[HTTP_PROXY] = http_proxy

    https_proxy = buildenv.get(HTTPS_PROXY, None)
    log(f"{fn}(): https_proxy '{https_proxy}'")
    config_data[HTTPS_PROXY] = https_proxy

    load_modules = buildenv.get(LOAD_MODULES, None)
    log(f"{fn}(): load_modules '{load_modules}'")
    config_data[LOAD_MODULES] = load_modules

    return config_data


def get_architecture_targets(cfg):
    """
    Obtain mappings of architecture targets to Slurm parameters

    Args:
        cfg (ConfigParser): ConfigParser instance holding full configuration
            (typically read from 'app.cfg')

    Returns:
        (dict): dictionary mapping architecture targets (format
            OS/SOFTWARE_SUBDIR) to architecture specific Slurm job submission
            parameters
    """
    fn = sys._getframe().f_code.co_name

    architecture_targets = cfg[ARCHITECTURE_TARGETS]

    arch_target_map = json.loads(architecture_targets.get('arch_target_map'))
    log(f"{fn}(): arch target map '{json.dumps(arch_target_map)}'")
    return arch_target_map


def get_repo_cfg(cfg):
    """
    Obtain mappings of architecture targets to repository identifiers and
    associated repository configuration settings

    Args:
        cfg (ConfigParser): ConfigParser instance holding full configuration
            (typically read from 'app.cfg')

    Returns:
        (dict): dictionary containing repository settings as follows
           - {REPOS_CFG_DIR: path to repository config directory as defined in 'app.cfg'}
           - {REPO_TARGET_MAP: json of REPO_TARGET_MAP value as defined in 'app.cfg'}
           - for all sections [JOB_REPO_ID] defined in REPOS_CFG_DIR/repos.cfg add a
             mapping {JOB_REPO_ID: dictionary containing settings of that section}
    """
    fn = sys._getframe().f_code.co_name

    global repo_cfg

    # if repo_cfg has already been initialized, just return it rather than reading it again
    if repo_cfg:
        return repo_cfg

    repo_cfg_org = cfg[REPO_TARGETS]
    repo_cfg = {}
    repo_cfg[REPOS_CFG_DIR] = repo_cfg_org.get(REPOS_CFG_DIR, None)

    repo_map = {}
    try:
        repo_map_str = repo_cfg_org.get(REPO_TARGET_MAP)
        log(f"{fn}(): repo_map '{repo_map_str}'")

        if repo_map_str is not None:
            repo_map = json.loads(repo_map_str)

        log(f"{fn}(): repo_map '{json.dumps(repo_map)}'")
    except json.JSONDecodeError as err:
        print(err)
        error(f"{fn}(): Value for repo_map ({repo_map_str}) could not be decoded.")

    repo_cfg[REPO_TARGET_MAP] = repo_map

    if repo_cfg[REPOS_CFG_DIR] is None:
        return repo_cfg

    # add entries for sections from repos.cfg (one dictionary per section)
    repos_cfg_file = os.path.join(repo_cfg[REPOS_CFG_DIR], 'repos.cfg')
    log(f"{fn}(): repos_cfg_file '{repos_cfg_file}'")
    try:
        repos_cfg = configparser.ConfigParser()
        repos_cfg.read(repos_cfg_file)
    except Exception as err:
        error(f"{fn}(): Unable to read repos config file {repos_cfg_file}!\n{err}")

    for repo_id in repos_cfg.sections():
        log(f"{fn}(): process repos.cfg section '{repo_id}'")
        if repo_id in repo_cfg:
            error(f"{fn}(): repo id '{repo_id}' in '{repos_cfg_file}' clashes with bot config")

        repo_cfg[repo_id] = {}
        for (key, val) in repos_cfg.items(repo_id):
            repo_cfg[repo_id][key] = val
            log(f"{fn}(): add ({key}:{val}) to repo_cfg[{repo_id}]")

        config_map = {}
        try:
            config_map_str = repos_cfg[repo_id].get(REPOS_CONFIG_MAP)
            log(f"{fn}(): config_map '{config_map_str}'")

            if config_map_str is not None:
                config_map = json.loads(config_map_str)

            log(f"{fn}(): config_map '{json.dumps(config_map)}'")
        except json.JSONDecodeError as err:
            print(err)
            error(f"{fn}(): Value for config_map ({config_map_str}) could not be decoded.")

        repo_cfg[repo_id][REPOS_CONFIG_MAP] = config_map

    # print full repo_cfg for debugging purposes
    log(f"{fn}(): complete repo_cfg that was just read: {json.dumps(repo_cfg, indent=4)}")

    return repo_cfg


def create_pr_dir(pr, cfg, event_info):
    """
    Create working directory for job to be submitted. Full path to the working
    directory has the format

    JOBS_BASE_DIR/<year>.<month>/pr_<pr number>/event_<event id>/run_<run number>

    where JOBS_BASE_DIR is defined in the configuration (see 'app.cfg'), year
    contains four digits, and month contains two digits

    Args:
        pr (github.PullRequest.PullRequest): instance representing the pull request
        cfg (ConfigParser): ConfigParser instance holding full configuration
            (typically read from 'app.cfg')
        event_info (dict): event received by event_handler

    Returns:
        tuple of 3 elements containing
        - (string): year_month with format '<year>.<month>' (year with four
              digits, month with two digits)
        - (string): pr_id with format 'pr_<pr number>'
        - (string): run_dir which is the complete path to the created directory
              with format as described above
    """
    # create directory structure (see discussion of options in
    #   https://github.com/EESSI/eessi-bot-software-layer/issues/7)
    #
    #   JOBS_BASE_DIR/<year>.<month>/pr_<pr number>/event_<event id>/run_<run number>
    #
    #   where JOBS_BASE_DIR is defined in the configuration (see 'app.cfg'), year
    #   contains four digits, and month contains two digits

    build_env_cfg = get_build_env_cfg(cfg)
    jobs_base_dir = build_env_cfg[JOBS_BASE_DIR]

    year_month = datetime.today().strftime('%Y.%m')
    pr_id = 'pr_%s' % pr.number
    event_id = 'event_%s' % event_info['id']
    event_dir = os.path.join(jobs_base_dir, year_month, pr_id, event_id)
    # NOTE the first call of os.makedirs cannot be deferred (i.e., to only
    # after it has been determined that any job will be created due to the
    # filters provided), because the condition in the 'while' loop below
    # takes the contents of the directory event_dir into account
    os.makedirs(event_dir, exist_ok=True)

    run = 0
    while os.path.exists(os.path.join(event_dir, 'run_%03d' % run)):
        run += 1
    run_dir = os.path.join(event_dir, 'run_%03d' % run)
    os.makedirs(run_dir, exist_ok=True)

    return year_month, pr_id, run_dir


def download_pr(repo_name, branch_name, pr, arch_job_dir):
    """
    Download pull request to job working directory

    Args:
        repo_name (string): name of the repository (format USER_OR_ORGANISATION/REPOSITORY)
        branch_name (string): name of the base branch of the pull request
        pr (github.PullRequest.PullRequest): instance representing the pull request
        arch_job_dir (string): working directory of the job to be submitted

    Returns:
        None (implicitly), in case an error is caught in the git clone, git checkout, curl,
            or git apply commands, returns the output, stderror, exit code and a string
            stating which of these commands failed.
    """
    # download pull request to arch_job_dir
    # - 'git clone' repository into arch_job_dir (NOTE 'git clone' requires that
    #    destination is an empty directory)
    # - 'git checkout' base branch of pull request
    # - 'curl' diff for pull request
    # - 'git apply' diff file
    git_clone_cmd = ' '.join(['git clone', f'https://github.com/{repo_name}', arch_job_dir])
    log(f'cloning with command {git_clone_cmd}')
    clone_output, clone_error, clone_exit_code = run_cmd(
        git_clone_cmd, "Clone repo", arch_job_dir, raise_on_error=False
        )
    if clone_exit_code != 0:
        error_stage = ERROR_GIT_CLONE
        return clone_output, clone_error, clone_exit_code, error_stage

    git_checkout_cmd = ' '.join([
        'git checkout',
        branch_name,
    ])
    log(f'checking out with command {git_checkout_cmd}')
    checkout_output, checkout_err, checkout_exit_code = run_cmd(
        git_checkout_cmd, "checkout branch '%s'" % branch_name, arch_job_dir, raise_on_error=False
        )
    if checkout_exit_code != 0:
        error_stage = ERROR_GIT_CHECKOUT
        return checkout_output, checkout_err, checkout_exit_code, error_stage

    curl_cmd = f'curl -L https://github.com/{repo_name}/pull/{pr.number}.diff > {pr.number}.diff'
    log(f'curl with command {curl_cmd}')
    curl_output, curl_error, curl_exit_code = run_cmd(
        curl_cmd, "Obtain patch", arch_job_dir, raise_on_error=False
        )
    if curl_exit_code != 0:
        error_stage = ERROR_CURL
        return curl_output, curl_error, curl_exit_code, error_stage

    git_apply_cmd = f'git apply {pr.number}.diff'
    log(f'git apply with command {git_apply_cmd}')
    git_apply_output, git_apply_error, git_apply_exit_code = run_cmd(
        git_apply_cmd, "Apply patch", arch_job_dir, raise_on_error=False
        )
    if git_apply_exit_code != 0:
        error_stage = ERROR_GIT_APPLY
        return git_apply_output, git_apply_error, git_apply_exit_code, error_stage

    # need to return four items also in case everything went fine
    return 'downloading PR succeeded', 'no error while downloading PR', 0, ERROR_NONE


def comment_download_pr(base_repo_name, pr, download_pr_exit_code, download_pr_error, error_stage):
    """
    Handle download_pr() exit code and write helpful comment to PR in case of failure

    Args:
        base_repo_name (string): name of the repository (format USER_OR_ORGANISATION/REPOSITORY)
        pr (github.PullRequest.PullRequest): instance representing the pull request
        download_pr_exit_code (int): exit code from download_pr(). 0 if all tasks were successful,
            otherwise it corresponds to the error codes of git clone, git checkout, git apply, or curl.
        download_pr_error (string): none, or the output of stderr from git clone, git checkout, git apply or curl.
        error_stage (string): a string informing the stage where download_pr() failed. Can be 'git clone',
            'git checkout', 'curl', or 'git apply'.

    Return:
        None (implicitly). A comment is created in the appropriate PR.

    """
    if download_pr_exit_code != 0:
        fn = sys._getframe().f_code.co_name

        download_pr_comments_cfg = config.read_config()[DOWNLOAD_PR_COMMENTS]
        if error_stage == ERROR_GIT_CLONE:
            download_comment = (f"`{download_pr_error}`"
                                f"{download_pr_comments_cfg[GIT_CLONE_FAILURE]}"
                                f"{download_pr_comments_cfg[GIT_CLONE_TIP]}")
        elif error_stage == ERROR_GIT_CHECKOUT:
            download_comment = (f"`{download_pr_error}`"
                                f"{download_pr_comments_cfg[GIT_CHECKOUT_FAILURE]}"
                                f"{download_pr_comments_cfg[GIT_CHECKOUT_TIP]}")
        elif error_stage == ERROR_CURL:
            download_comment = (f"`{download_pr_error}`"
                                f"{download_pr_comments_cfg[CURL_FAILURE]}"
                                f"{download_pr_comments_cfg[CURL_TIP]}")
        elif error_stage == ERROR_GIT_APPLY:
            download_comment = (f"`{download_pr_error}`"
                                f"{download_pr_comments_cfg[GIT_APPLY_FAILURE]}"
                                f"{download_pr_comments_cfg[GIT_APPLY_TIP]}")

        download_comment = pr_comments.create_comment(
            repo_name=base_repo_name, pr_number=pr.number, comment=download_comment
            )
        if download_comment:
            log(f"{fn}(): created PR issue comment with id {download_comment.id}")
        else:
            log(f"{fn}(): failed to create PR issue comment")
        raise ValueError("Unable to download PR and/or sync changes")


def apply_cvmfs_customizations(cvmfs_customizations, arch_job_dir):
    """
    Apply cvmfs_customizations to job

    Args:
        cvmfs_customizations (dict): defines both the CVMFS configuration files
            and the contents to be appended to these files
        arch_job_dir (string): path to working directory of the job

    Returns:
        None (implicitly)
    """
    if len(cvmfs_customizations) > 0:
        # for each key, append value to file defined by key
        for key in cvmfs_customizations.keys():
            basename = os.path.basename(key)
            jobcfgfile = os.path.join(arch_job_dir, basename)
            with open(jobcfgfile, "a") as file_object:
                file_object.write(cvmfs_customizations[key]+'\n')

            # TODO (maybe) create mappings_file to be used by
            #      bot-build.slurm to init SINGULARITY_BIND;
            #      for now, only existing mappings may be customized


def prepare_jobs(pr, cfg, event_info, action_filter):
    """
    Prepare all jobs whose context matches the given filter. Preparation includes
    creating a working directory for a job, downloading the pull request into
    that directory and creating a job specific configuration file.

    Args:
        pr (github.PullRequest.PullRequest): instance representing the pull request
        cfg (ConfigParser): instance holding full configuration (typically read from 'app.cfg')
        event_info (dict): event received by event_handler
        action_filter (EESSIBotActionFilter): used to filter which jobs shall be prepared

    Returns:
        (list): list of the prepared jobs
    """
    fn = sys._getframe().f_code.co_name

    app_name = cfg[GITHUB].get(APP_NAME)
    build_env_cfg = get_build_env_cfg(cfg)
    arch_map = get_architecture_targets(cfg)
    repocfg = get_repo_cfg(cfg)

    base_repo_name = pr.base.repo.full_name
    log(f"{fn}(): pr.base.repo.full_name '{base_repo_name}'")

    base_branch_name = pr.base.ref
    log(f"{fn}(): pr.base.repo.ref '{base_branch_name}'")

    # create run dir (base directory for potentially several jobs)
    # TODO may still be too early (before we get to any actual job being
    #      prepared below when calling 'download_pr')
    #      instead of using a run_dir, maybe just create a unique dir for each
    #      job to be submitted? thus we could easily postpone the create_pr_dir
    #      call to just before download_pr
    year_month, pr_id, run_dir = create_pr_dir(pr, cfg, event_info)

    jobs = []
    for arch, slurm_opt in arch_map.items():
        arch_dir = arch.replace('/', '_')
        # check if repo_target_map contains an entry for {arch}
        if arch not in repocfg[REPO_TARGET_MAP]:
            log(f"{fn}(): skipping arch {arch} because repo target map does not define repositories to build for")
            continue
        for repo_id in repocfg[REPO_TARGET_MAP][arch]:
            # ensure repocfg contains information about the repository repo_id if repo_id != EESSI
            # Note, EESSI is a bad/misleading name, it should be more like AS_IN_CONTAINER
            if (repo_id != "EESSI" and repo_id != "EESSI-pilot") and repo_id not in repocfg:
                log(f"{fn}(): skipping repo {repo_id}, it is not defined in repo config {repocfg[REPOS_CFG_DIR]}")
                continue

            # if filter exists, check filter against context = (arch, repo, app_name)
            #   true --> log & go on in this iteration of for loop
            #   false --> log & continue to next iteration of for loop
            if action_filter:
                log(f"{fn}(): checking filter {action_filter.to_string()}")
                context = {"architecture": arch, "repository": repo_id, "instance": app_name}
                log(f"{fn}(): context is '{json.dumps(context, indent=4)}'")
                if not action_filter.check_filters(context):
                    log(f"{fn}(): context does NOT satisfy filter(s), skipping")
                    continue
                else:
                    log(f"{fn}(): context DOES satisfy filter(s), going on with job")
            job_dir = os.path.join(run_dir, arch_dir, repo_id)
            os.makedirs(job_dir, exist_ok=True)
            log(f"{fn}(): job_dir '{job_dir}'")

            # TODO optimisation? download once, copy and cleanup initial copy?
            download_pr_output, download_pr_error, download_pr_exit_code, error_stage = download_pr(
                base_repo_name, base_branch_name, pr, job_dir
                )
            comment_download_pr(base_repo_name, pr, download_pr_exit_code, download_pr_error, error_stage)
            # prepare job configuration file 'job.cfg' in directory <job_dir>/cfg
            cpu_target = '/'.join(arch.split('/')[1:])
            os_type = arch.split('/')[0]
            log(f"{fn}(): arch = '{arch}' => cpu_target = '{cpu_target}' , os_type = '{os_type}'")
            prepare_job_cfg(job_dir, build_env_cfg, repocfg, repo_id, cpu_target, os_type)

            # enlist jobs to proceed
            job = Job(job_dir, arch, repo_id, slurm_opt, year_month, pr_id)
            jobs.append(job)

    log(f"{fn}(): {len(jobs)} jobs to proceed after applying white list")
    if jobs:
        log(json.dumps(jobs, indent=4))

    return jobs


def prepare_job_cfg(job_dir, build_env_cfg, repos_cfg, repo_id, software_subdir, os_type):
    """
    Set up job configuration file 'job.cfg' in directory <job_dir>/cfg

    Args:
        job_dir (string): working directory of the job
        build_env_cfg (dict): build environment settings
        repos_cfg (dict): configuration settings for all repositories
        repo_id (string): identifier of the repository to build for
        software_subdir (string): software subdirectory to build for (e.g., 'x86_64/generic')
        os_type (string): type of the os (e.g., 'linux')

    Returns:
        None (implicitly)
    """
    fn = sys._getframe().f_code.co_name

    jobcfg_dir = os.path.join(job_dir, CFG_DIRNAME)
    # create ini file job.cfg with entries:
    # [site_config]
    # local_tmp = LOCAL_TMP_VALUE
    # shared_fs_path = SHARED_FS_PATH
    # build_logs_dir = BUILD_LOGS_DIR
    #
    # [repository]
    # repos_cfg_dir = JOB_CFG_DIR
    # repo_id = JOB_REPO_ID
    # container = CONTAINER
    # repo_name = REPO_NAME
    # repo_version = REPO_VERSION
    #
    # [architecture]
    # software_subdir = SOFTWARE_SUBDIR
    # os_type = OS_TYPE
    job_cfg = configparser.ConfigParser()
    job_cfg[JOB_SITECONFIG] = {}
    build_env_to_job_cfg_keys = {
        BUILD_LOGS_DIR: BUILD_LOGS_DIR,
        CONTAINER_CACHEDIR: CONTAINER_CACHEDIR,
        HTTP_PROXY: JOB_HTTP_PROXY,
        HTTPS_PROXY: JOB_HTTPS_PROXY,
        LOAD_MODULES: JOB_LOAD_MODULES,
        LOCAL_TMP: JOB_LOCAL_TMP,
        SHARED_FS_PATH: SHARED_FS_PATH,
    }
    for build_env_key, job_cfg_key in build_env_to_job_cfg_keys.items():
        if build_env_cfg[build_env_key]:
            job_cfg[JOB_SITECONFIG][job_cfg_key] = build_env_cfg[build_env_key]

    job_cfg[JOB_REPOSITORY] = {}
    # directory for repos.cfg
    # NOTE REPOS_CFG_DIR is a global configuration setting for all repositories,
    #      hence it is stored in repos_cfg whereas repo_cfg used further below
    #      contains setting for a specific repository
    if REPOS_CFG_DIR in repos_cfg and repos_cfg[REPOS_CFG_DIR]:
        job_cfg[JOB_REPOSITORY][JOB_REPOS_CFG_DIR] = jobcfg_dir
    # repo id
    job_cfg[JOB_REPOSITORY][JOB_REPO_ID] = repo_id

    # settings for a specific repository
    if repo_id in repos_cfg:
        repo_cfg = repos_cfg[repo_id]
        if repo_cfg[REPOS_CONTAINER]:
            job_cfg[JOB_REPOSITORY][JOB_CONTAINER] = repo_cfg[REPOS_CONTAINER]
        if repo_cfg[REPOS_REPO_NAME]:
            job_cfg[JOB_REPOSITORY][JOB_REPO_NAME] = repo_cfg[REPOS_REPO_NAME]
        if repo_cfg[REPOS_REPO_VERSION]:
            job_cfg[JOB_REPOSITORY][JOB_REPO_VERSION] = repo_cfg[REPOS_REPO_VERSION]

    job_cfg[JOB_ARCHITECTURE] = {}
    job_cfg[JOB_ARCHITECTURE][JOB_SOFTWARE_SUBDIR] = software_subdir
    job_cfg[JOB_ARCHITECTURE][JOB_OS_TYPE] = os_type

    # copy repos_cfg[REPOS_CFG_DIR]/repos.cfg to <jobcfg_dir>
    # copy repos_cfg[REPOS_CFG_DIR]/*.tgz to <jobcfg_dir>
    if REPOS_CFG_DIR in repos_cfg and repos_cfg[REPOS_CFG_DIR] and os.path.isdir(repos_cfg[REPOS_CFG_DIR]):
        src = repos_cfg[REPOS_CFG_DIR]
        shutil.copytree(src, jobcfg_dir)
        log(f"{fn}(): copied {src} to {jobcfg_dir}")

    # make sure that <jobcfg_dir> exists
    os.makedirs(jobcfg_dir, exist_ok=True)

    jobcfg_file = os.path.join(jobcfg_dir, JOB_CFG_FILENAME)
    with open(jobcfg_file, "w") as jcf:
        job_cfg.write(jcf)

    # read back job cfg file so we can log contents
    with open(jobcfg_file, "r") as jcf:
        jobcfg_txt = jcf.read()
        log(f"{fn}(): created {jobcfg_file} with '{jobcfg_txt}'")


def submit_job(job, cfg):
    """
    Submit a job, obtain its id and create a symlink for easier management

    Args:
        job (Job): namedtuple containing all information about job to be submitted
        cfg (ConfigParser): instance holding full configuration (typically read from 'app.cfg')

    Returns:
        tuple of 2 elements containing
        - (string): id of the submitted job
        - (string): path JOBS_BASE_DIR/job.year_month/job.pr_id/SLURM_JOBID which
          is a symlink to the job's working directory (job[0] or job.working_dir)
    """
    fn = sys._getframe().f_code.co_name

    build_env_cfg = get_build_env_cfg(cfg)

    # add a default time limit of 24h to the job submit command if no other time
    # limit is specified already
    all_opts_str = " ".join([build_env_cfg[SLURM_PARAMS], job.slurm_opts])
    all_opts_list = all_opts_str.split(" ")
    if any([(opt.startswith("--time") or opt.startswith("-t")) for opt in all_opts_list]):
        time_limit = ""
    else:
        time_limit = f"--time={DEFAULT_JOB_TIME_LIMIT}"

    command_line = ' '.join([
        build_env_cfg[SUBMIT_COMMAND],
        build_env_cfg[SLURM_PARAMS],
        time_limit,
        job.slurm_opts,
        build_env_cfg[BUILD_JOB_SCRIPT],
    ])

    cmdline_output, cmdline_error, cmdline_exit_code = run_cmd(command_line,
                                                               "submit job for target '%s'" % job.arch_target,
                                                               working_dir=job.working_dir)

    # sbatch output is 'Submitted batch job JOBID'
    #   parse job id, add it to array of submitted jobs and create a symlink
    #   from JOBS_BASE_DIR/job.year_month/job.pr_id/SLURM_JOBID to the job's
    #   working directory
    log(f"{fn}(): sbatch out: {cmdline_output}")
    log(f"{fn}(): sbatch err: {cmdline_error}")

    job_id = cmdline_output.split()[3]

    symlink = os.path.join(build_env_cfg[JOBS_BASE_DIR], job.year_month, job.pr_id, job_id)
    log(f"{fn}(): create symlink {symlink} -> {job[0]}")
    os.symlink(job[0], symlink)

    return job_id, symlink


def create_pr_comment(job, job_id, app_name, pr, gh, symlink):
    """
    Create a comment to the pull request for a newly submitted job

    Args:
        job (Job): namedtuple containing information about submitted job
        job_id (string): id of the submitted job
        app_name (string): name of the app
        pr (github.PullRequest.PullRequest): instance representing the pull request
        gh (object): github instance
        symlink (string): symlink from main pr_<ID> dir to job dir

    Returns:
        github.IssueComment.IssueComment instance or None (note, github refers to
            PyGithub, not the github from the internal connections module)
    """
    fn = sys._getframe().f_code.co_name

    # obtain arch from job.arch_target which has the format OS/ARCH
    arch_name = '-'.join(job.arch_target.split('/')[1:])

    # get current date and time
    dt = datetime.now(timezone.utc)

    # construct initial job comment
    submitted_job_comments_cfg = config.read_config()[SUBMITTED_JOB_COMMENTS]
    job_comment = (f"{submitted_job_comments_cfg[INITIAL_COMMENT]}"
                   f"\n|date|job status|comment|\n"
                   f"|----------|----------|------------------------|\n"
                   f"|{dt.strftime('%b %d %X %Z %Y')}|"
                   f"submitted|"
                   f"{submitted_job_comments_cfg[AWAITS_RELEASE]}|").format(app_name=app_name,
                                                                            arch_name=arch_name,
                                                                            symlink=symlink,
                                                                            repo_id=job.repo_id,
                                                                            job_id=job_id)

    # create comment to pull request
    repo_name = pr.base.repo.full_name
    repo = gh.get_repo(repo_name)
    pull_request = repo.get_pull(pr.number)
    issue_comment = retry_call(pull_request.create_issue_comment, fargs=[job_comment],
                               exceptions=Exception, tries=3, delay=1, backoff=2, max_delay=10)
    if issue_comment:
        log(f"{fn}(): created PR issue comment with id {issue_comment.id}")
        return issue_comment
    else:
        log(f"{fn}(): failed to create PR issue comment for job {job_id}")
        return None


def submit_build_jobs(pr, event_info, action_filter):
    """
    Create build jobs for a pull request by preparing jobs which match the given
    filters, submitting them, adding comments to the pull request on GitHub and
    creating a metadata file in the job's working directory

    Args:
        pr (github.PullRequest.PullRequest): instance representing the pull request
        event_info (dict): event received by event_handler
        action_filter (EESSIBotActionFilter): used to filter which jobs shall be prepared

    Returns:
        (dict): dictionary mapping a job id to a github.IssueComment.IssueComment
            instance (corresponding to the pull request comment for the submitted
            job) or an empty dictionary if there were no jobs to be submitted
    """
    fn = sys._getframe().f_code.co_name

    cfg = config.read_config()
    app_name = cfg[GITHUB].get(APP_NAME)

    # setup job directories (one per element in product of architecture x repositories)
    jobs = prepare_jobs(pr, cfg, event_info, action_filter)

    # return if there are no jobs to be submitted
    if not jobs:
        log(f"{fn}(): no jobs ({len(jobs)}) to be submitted")
        return {}

    # obtain handle to GitHub
    gh = github.get_instance()

    # process prepared jobs: submit, create metadata file and add comment to pull
    # request on GitHub
    job_id_to_comment_map = {}
    for job in jobs:
        # submit job
        job_id, symlink = submit_job(job, cfg)

        # create pull request comment to report about the submitted job
        pr_comment = create_pr_comment(job, job_id, app_name, pr, gh, symlink)
        job_id_to_comment_map[job_id] = pr_comment

        pr_comment = pr_comments.PRComment(pr.base.repo.full_name, pr.number, pr_comment.id)

        # create _bot_job<jobid>.metadata file in the job's working directory
        create_metadata_file(job, job_id, pr_comment)

    return job_id_to_comment_map


def check_build_permission(pr, event_info):
    """
    Check if GitHub account whom's action resulted in an event is authorized to
    trigger a build job

    Args:
        pr (github.PullRequest.PullRequest): instance representing the pull request
        event_info (dict): event received by event_handler

    Returns:
        (bool): True -> GitHub account is authorized, False -> GitHub account is
            not authorized
    """
    fn = sys._getframe().f_code.co_name

    log(f"{fn}(): build for PR {pr.number}")

    cfg = config.read_config()

    buildenv = cfg[BUILDENV]

    build_permission = buildenv.get(BUILD_PERMISSION, '')

    log(f"{fn}(): build permission '{build_permission}'")

    build_labeler = event_info['raw_request_body']['sender']['login']
    if build_labeler not in build_permission.split():
        log(f"{fn}(): GH account '{build_labeler}' is not authorized to build")
        no_build_permission_comment = buildenv.get(NO_BUILD_PERMISSION_COMMENT)
        repo_name = event_info["raw_request_body"]["repository"]["full_name"]
        pr_comments.create_comment(repo_name,
                                   pr.number,
                                   no_build_permission_comment.format(build_labeler=build_labeler))
        return False
    else:
        log(f"{fn}(): GH account '{build_labeler}' is authorized to build")
        return True


def request_bot_build_issue_comments(repo_name, pr_number):
    """
    Query the github API for the issue_comments in a pr.

    Archs:
        repo_name (string): name of the repository (format USER_OR_ORGANISATION/REPOSITORY)
        pr_number (int): number og the pr

    Returns:
        status_table (dict): dictionary with 'arch', 'date', 'status', 'url' and 'result'
            for all the finished builds;
    """
    fn = sys._getframe().f_code.co_name

    status_table = {'arch': [], 'date': [], 'status': [], 'url': [], 'result': []}
    cfg = config.read_config()

    # for loop because github has max 100 items per request.
    # if the pr has more than 100 comments we need to use per_page
    # argument at the moment the for loop is for a max of 400 comments could bump this up
    for x in range(1, 5):
        curl_cmd = f'curl -L https://api.github.com/repos/{repo_name}/issues/{pr_number}/comments?per_page=100&page={x}'
        curl_output, curl_error, curl_exit_code = run_cmd(curl_cmd, "fetch all comments")

        comments = json.loads(curl_output)

        for comment in comments:
            # iterate through the comments to find the one where the status of the build was in
            if config.read_config()["submitted_job_comments"]['initial_comment'][:20] in comment['body']:

                # get archictecture from comment['body']
                first_line = comment['body'].split('\n')[0]
                arch_map = get_architecture_targets(cfg)
                for arch in arch_map.keys():
                    # drop the first element in arch (which names the OS type) and join the remaining items with '-'
                    target_arch = '-'.join(arch.split('/')[1:])
                    if target_arch in first_line:
                        status_table['arch'].append(target_arch)
                    else:
                        log(f"{fn}(): target_arch '{target_arch}' not found in first line '{first_line}'")

                # get date, status, url and result from the markdown table
                comment_table = comment['body'][comment['body'].find('|'):comment['body'].rfind('|')+1]

                # Convert markdown table to a dictionary
                lines = comment_table.split('\n')
                rows = []
                keys = []
                for i, row in enumerate(lines):
                    values = {}
                    if i == 0:
                        for key in row.split('|'):
                            keys.append(key.strip())
                    elif i == 1:
                        continue
                    else:
                        for j, value in enumerate(row.split('|')):
                            if j > 0 and j < len(keys) - 1:
                                values[keys[j]] = value.strip()
                        rows.append(values)

                # add date, status, url to  status_table if
                for row in rows:
                    if row['job status'] == 'finished':
                        status_table['date'].append(row['date'])
                        status_table['status'].append(row['job status'])
                        status_table['url'].append(comment['html_url'])
                        if 'FAILURE' in row['comment']:
                            status_table['result'].append(':cry: FAILURE')
                        elif 'SUCCESS' in row['comment']:
                            status_table['result'].append(':grin: SUCCESS')
                        elif 'UNKNOWN' in row['comment']:
                            status_table['result'].append(':shrug: UNKNOWN')
                        else:
                            status_table['result'].append(row['comment'])
        if len(comments) != 100:
            break
    return status_table
