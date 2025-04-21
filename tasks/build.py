# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Bob Droege (@bedroge)
# author: Kenneth Hoste (@boegel)
# author: Hafsa Naeem (@hafsa-naeem)
# author: Jacob Ziemke (@jacobz137)
# author: Jonas Qvigstad (@jonas-lq)
# author: Lara Ramona Peeters (@laraPPr)
# author: Pedro Santos Neves (@Neves-P)
# author: Thomas Roeblitz (@trz42)
# author: Sam Moors (@smoors)
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
from tools import config, cvmfs_repository, job_metadata, pr_comments, run_cmd
import tools.filter as tools_filter


# defaults (used if not specified via, eg, 'app.cfg')
DEFAULT_JOB_TIME_LIMIT = "24:00:00"

# error codes used in this file
_ERROR_CURL = "curl"
_ERROR_GIT_APPLY = "git apply"
_ERROR_GIT_CHECKOUT = "git checkout"
_ERROR_GIT_CLONE = "curl"
_ERROR_NONE = "none"

# other constants
EXPORT_VARS_FILE = 'export_vars.sh'

Job = namedtuple('Job', ('working_dir', 'arch_target', 'repo_id', 'slurm_opts', 'year_month', 'pr_id', 'accelerator'))

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

    config_data = {}
    buildenv = cfg[config.SECTION_BUILDENV]

    job_name = buildenv.get(config.BUILDENV_SETTING_JOB_NAME)
    log(f"{fn}(): job_name '{job_name}'")
    config_data[config.BUILDENV_SETTING_JOB_NAME] = job_name

    jobs_base_dir = buildenv.get(config.BUILDENV_SETTING_JOBS_BASE_DIR)
    log(f"{fn}(): jobs_base_dir '{jobs_base_dir}'")
    config_data[config.BUILDENV_SETTING_JOBS_BASE_DIR] = jobs_base_dir

    local_tmp = buildenv.get(config.BUILDENV_SETTING_LOCAL_TMP)
    log(f"{fn}(): local_tmp '{local_tmp}'")
    config_data[config.BUILDENV_SETTING_LOCAL_TMP] = local_tmp

    site_config_script = buildenv.get(config.BUILDENV_SETTING_SITE_CONFIG_SCRIPT)
    log(f"{fn}(): site_config_script '{site_config_script}'")
    config_data[config.BUILDENV_SETTING_SITE_CONFIG_SCRIPT] = site_config_script

    build_job_script = buildenv.get(config.BUILDENV_SETTING_BUILD_JOB_SCRIPT)
    # figure out whether path to build job script is just a path in current directory (path/to/job_script),
    # or a location in another Git repository (path/to/job_script@repo)
    if '@' in build_job_script:
        build_job_script_path, build_job_script_repo = build_job_script.split('@', 1)
        log(f"{fn}(): build_job_script '{build_job_script_path}' in repo {build_job_script_repo}")
        build_job_script = {
            'path': build_job_script_path,
            'repo': build_job_script_repo,
        }
    else:
        log(f"{fn}(): build_job_script '{build_job_script}'")
    config_data[config.BUILDENV_SETTING_BUILD_JOB_SCRIPT] = build_job_script

    submit_command = buildenv.get(config.BUILDENV_SETTING_SUBMIT_COMMAND)
    log(f"{fn}(): submit_command '{submit_command}'")
    config_data[config.BUILDENV_SETTING_SUBMIT_COMMAND] = submit_command

    job_handover_protocol = buildenv.get(config.BUILDENV_SETTING_JOB_HANDOVER_PROTOCOL)
    slurm_params = buildenv.get(config.BUILDENV_SETTING_SLURM_PARAMS)
    if job_handover_protocol == config.JOB_HANDOVER_PROTOCOL_HOLD_RELEASE:
        # always submit jobs with hold set, so job manager can release them
        slurm_params += ' --hold'
    elif job_handover_protocol == config.JOB_HANDOVER_PROTOCOL_DELAYED_BEGIN:
        # alternative method to submit without '--hold' and
        # '--begin=now+factor*poll_interval' instead
        # 1. remove '--hold' if any
        # 2. add '--begin=now+factor*poll_interval'
        # factor defined by setting 'job_delay_begin_factor' (default: 2)
        slurm_params = slurm_params.replace('--hold', '')
        job_manger_cfg = cfg[config.SECTION_JOB_MANAGER]
        poll_interval = int(job_manger_cfg.get(config.JOB_MANAGER_SETTING_POLL_INTERVAL))
        job_delay_begin_factor = float(buildenv.get(config.BUILDENV_SETTING_JOB_DELAY_BEGIN_FACTOR, 2))
        slurm_params += f' --begin=now+{int(job_delay_begin_factor * poll_interval)}'
    else:
        slurm_params += ' --hold'
        log(
            f"{fn}(): unknown job handover protocol in app.cfg"
            f" ('{config.BUILDENV_SETTING_JOB_HANDOVER_PROTOCOL} = {job_handover_protocol}');"
            f" added '--hold' as default"
        )

    log(f"{fn}(): slurm_params '{slurm_params}'")
    config_data[config.BUILDENV_SETTING_SLURM_PARAMS] = slurm_params

    shared_fs_path = buildenv.get(config.BUILDENV_SETTING_SHARED_FS_PATH)
    log(f"{fn}(): shared_fs_path: '{shared_fs_path}'")
    config_data[config.BUILDENV_SETTING_SHARED_FS_PATH] = shared_fs_path

    container_cachedir = buildenv.get(config.BUILDENV_SETTING_CONTAINER_CACHEDIR)
    log(f"{fn}(): container_cachedir '{container_cachedir}'")
    config_data[config.BUILDENV_SETTING_CONTAINER_CACHEDIR] = container_cachedir

    build_logs_dir = buildenv.get(config.BUILDENV_SETTING_BUILD_LOGS_DIR)
    log(f"{fn}(): build_logs_dir '{build_logs_dir}'")
    config_data[config.BUILDENV_SETTING_BUILD_LOGS_DIR] = build_logs_dir

    cvmfs_customizations = {}
    try:
        cvmfs_customizations_str = buildenv.get(config.BUILDENV_SETTING_CVMFS_CUSTOMIZATIONS)
        log(f"{fn}(): cvmfs_customizations '{cvmfs_customizations_str}'")

        if cvmfs_customizations_str is not None:
            cvmfs_customizations = json.loads(cvmfs_customizations_str)

        log(f"{fn}(): cvmfs_customizations '{json.dumps(cvmfs_customizations)}'")
    except json.JSONDecodeError as e:
        print(e)
        error(f"{fn}(): Value for cvmfs_customizations ({cvmfs_customizations_str}) could not be decoded.")

    config_data[config.BUILDENV_SETTING_CVMFS_CUSTOMIZATIONS] = cvmfs_customizations

    http_proxy = buildenv.get(config.BUILDENV_SETTING_HTTP_PROXY, None)
    log(f"{fn}(): http_proxy '{http_proxy}'")
    config_data[config.BUILDENV_SETTING_HTTP_PROXY] = http_proxy

    https_proxy = buildenv.get(config.BUILDENV_SETTING_HTTPS_PROXY, None)
    log(f"{fn}(): https_proxy '{https_proxy}'")
    config_data[config.BUILDENV_SETTING_HTTPS_PROXY] = https_proxy

    load_modules = buildenv.get(config.BUILDENV_SETTING_LOAD_MODULES, None)
    log(f"{fn}(): load_modules '{load_modules}'")
    config_data[config.BUILDENV_SETTING_LOAD_MODULES] = load_modules

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

    architecture_targets = cfg[config.SECTION_ARCHITECTURETARGETS]

    arch_target_map = json.loads(architecture_targets.get(config.ARCHITECTURETARGETS_SETTING_ARCH_TARGET_MAP))
    log(f"{fn}(): arch target map '{json.dumps(arch_target_map)}'")
    return arch_target_map


def get_allowed_exportvars(cfg):
    """
    Obtain list of allowed export variables

    Args:
        cfg (ConfigParser): ConfigParser instance holding full configuration
            (typically read from 'app.cfg')

    Returns:
        (list): list of allowed export variable-value pairs of the format VARIABLE=VALUE
    """
    fn = sys._getframe().f_code.co_name

    buildenv = cfg[config.SECTION_BUILDENV]
    allowed_str = buildenv.get(config.BUILDENV_SETTING_ALLOWED_EXPORTVARS)
    allowed = []

    if allowed_str:
        try:
            allowed = json.loads(allowed_str)
        except json.JSONDecodeError as err:
            print(err)
            error(f"{fn}(): Value for allowed_exportvars ({allowed_str}) could not be decoded.")

    log(f"{fn}(): allowed_exportvars '{json.dumps(allowed)}'")
    return allowed


def get_repo_cfg(cfg):
    """
    Obtain mappings of architecture targets to repository identifiers and
    associated repository configuration settings

    Args:
        cfg (ConfigParser): ConfigParser instance holding full configuration
            (typically read from 'app.cfg')

    Returns:
        (dict): dictionary containing repository settings as follows
           - {config.REPO_TARGETS_SETTING_REPOS_CFG_DIR: path to repository config directory as defined in 'app.cfg'}
           - {config.REPO_TARGETS_SETTING_REPO_TARGET_MAP: json of
               config.REPO_TARGETS_SETTING_REPO_TARGET_MAP value as defined in 'app.cfg'}
           - for all sections [repo_id] defined in config.REPO_TARGETS_SETTING_REPOS_CFG_DIR/repos.cfg add a
             mapping {repo_id: dictionary containing settings of that section}
    """
    fn = sys._getframe().f_code.co_name

    global repo_cfg

    # if repo_cfg has already been initialized, just return it rather than reading it again
    if repo_cfg:
        return repo_cfg

    repo_cfg_org = cfg[config.SECTION_REPO_TARGETS]
    repo_cfg = {}
    settings_repos_cfg_dir = config.REPO_TARGETS_SETTING_REPOS_CFG_DIR
    repo_cfg[settings_repos_cfg_dir] = repo_cfg_org.get(settings_repos_cfg_dir, None)

    repo_map = {}
    try:
        repo_map_str = repo_cfg_org.get(config.REPO_TARGETS_SETTING_REPO_TARGET_MAP)
        log(f"{fn}(): repo_map '{repo_map_str}'")

        if repo_map_str is not None:
            repo_map = json.loads(repo_map_str)

        log(f"{fn}(): repo_map '{json.dumps(repo_map)}'")
    except json.JSONDecodeError as err:
        print(err)
        error(f"{fn}(): Value for repo_map ({repo_map_str}) could not be decoded.")

    repo_cfg[config.REPO_TARGETS_SETTING_REPO_TARGET_MAP] = repo_map

    if repo_cfg[config.REPO_TARGETS_SETTING_REPOS_CFG_DIR] is None:
        return repo_cfg

    # add entries for sections from repos.cfg (one dictionary per section)
    repos_cfg_file = os.path.join(repo_cfg[config.REPO_TARGETS_SETTING_REPOS_CFG_DIR], 'repos.cfg')
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
            config_map_str = repos_cfg[repo_id].get(cvmfs_repository.REPOS_CFG_CONFIG_MAP)
            log(f"{fn}(): config_map '{config_map_str}'")

            if config_map_str is not None:
                config_map = json.loads(config_map_str)

            log(f"{fn}(): config_map '{json.dumps(config_map)}'")
        except json.JSONDecodeError as err:
            print(err)
            error(f"{fn}(): Value for config_map ({config_map_str}) could not be decoded.")

        repo_cfg[repo_id][cvmfs_repository.REPOS_CFG_CONFIG_MAP] = config_map

    # print full repo_cfg for debugging purposes
    log(f"{fn}(): complete repo_cfg that was just read: {json.dumps(repo_cfg, indent=4)}")

    return repo_cfg


def create_pr_dir(pr, cfg, event_info):
    """
    Create working directory for job to be submitted. Full path to the working
    directory has the format

    config.BUILDENV_SETTING_JOBS_BASE_DIR/<year>.<month>/pr_<pr number>/event_<event id>/run_<run number>

    where config.BUILDENV_SETTING_JOBS_BASE_DIR is defined in the configuration (see 'app.cfg'), year
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
    #   config.BUILDENV_SETTING_JOBS_BASE_DIR/<year>.<month>/pr_<pr number>/event_<event id>/run_<run number>
    #
    #   where config.BUILDENV_SETTING_JOBS_BASE_DIR is defined in the configuration (see 'app.cfg'), year
    #   contains four digits, and month contains two digits

    build_env_cfg = get_build_env_cfg(cfg)
    jobs_base_dir = build_env_cfg[config.BUILDENV_SETTING_JOBS_BASE_DIR]

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


def clone_git_repo(repo, path):
    """
    Clone specified Git repo to specified path
    """
    git_clone_cmd = ' '.join(['git clone', repo, path])
    log(f'cloning with command {git_clone_cmd}')
    clone_output, clone_error, clone_exit_code = run_cmd(
        git_clone_cmd, "Clone repo", path, raise_on_error=False
        )

    return (clone_output, clone_error, clone_exit_code)


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
    clone_output, clone_error, clone_exit_code = clone_git_repo(f'https://github.com/{repo_name}', arch_job_dir)
    if clone_exit_code != 0:
        error_stage = _ERROR_GIT_CLONE
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
        error_stage = _ERROR_GIT_CHECKOUT
        return checkout_output, checkout_err, checkout_exit_code, error_stage

    curl_cmd = ' '.join([
        'curl -L',
        '-H "Accept: application/vnd.github.diff"',
        '-H "X-GitHub-Api-Version: 2022-11-28"',
        f'https://api.github.com/repos/{repo_name}/pulls/{pr.number} > {pr.number}.diff',
    ])
    log(f'curl with command {curl_cmd}')
    curl_output, curl_error, curl_exit_code = run_cmd(
        curl_cmd, "Obtain patch", arch_job_dir, raise_on_error=False
        )
    if curl_exit_code != 0:
        error_stage = _ERROR_CURL
        return curl_output, curl_error, curl_exit_code, error_stage

    git_apply_cmd = f'git apply {pr.number}.diff'
    log(f'git apply with command {git_apply_cmd}')
    git_apply_output, git_apply_error, git_apply_exit_code = run_cmd(
        git_apply_cmd, "Apply patch", arch_job_dir, raise_on_error=False
        )
    if git_apply_exit_code != 0:
        error_stage = _ERROR_GIT_APPLY
        return git_apply_output, git_apply_error, git_apply_exit_code, error_stage

    # need to return four items also in case everything went fine
    return 'downloading PR succeeded', 'no error while downloading PR', 0, _ERROR_NONE


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

        download_pr_comments_cfg = config.read_config()[config.SECTION_DOWNLOAD_PR_COMMENTS]
        if error_stage == _ERROR_GIT_CLONE:
            download_comment = (f"```{download_pr_error}```\n"
                                f"{download_pr_comments_cfg[config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_CLONE_FAILURE]}"
                                f"\n{download_pr_comments_cfg[config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_CLONE_TIP]}")
        elif error_stage == _ERROR_GIT_CHECKOUT:
            download_comment = (f"```{download_pr_error}```\n"
                                f"{download_pr_comments_cfg[config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_CHECKOUT_FAILURE]}"
                                f"\n{download_pr_comments_cfg[config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_CHECKOUT_TIP]}")
        elif error_stage == _ERROR_CURL:
            download_comment = (f"```{download_pr_error}```\n"
                                f"{download_pr_comments_cfg[config.DOWNLOAD_PR_COMMENTS_SETTING_CURL_FAILURE]}"
                                f"\n{download_pr_comments_cfg[config.DOWNLOAD_PR_COMMENTS_SETTING_CURL_TIP]}")
        elif error_stage == _ERROR_GIT_APPLY:
            download_comment = (f"```{download_pr_error}```\n"
                                f"{download_pr_comments_cfg[config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_APPLY_FAILURE]}"
                                f"\n{download_pr_comments_cfg[config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_APPLY_TIP]}")

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


def prepare_export_vars_file(job_dir, exportvars):
    """
    Set up EXPORT_VARS_FILE in directory <job_dir>/cfg. This file will be
    sourced before running the bot/build.sh script.

    Args:
        job_dir (string): working directory of the job
        exportvars (list): strings of the form VAR=VALUE to be exported

    Returns:
        None (implicitly)
    """
    fn = sys._getframe().f_code.co_name

    content = '\n'.join(f'export {x}' for x in exportvars)
    export_vars_path = os.path.join(job_dir, 'cfg', EXPORT_VARS_FILE)

    with open(export_vars_path, 'w') as file:
        file.write(content)

    log(f"{fn}(): created exported variables file {export_vars_path}")


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

    app_name = cfg[config.SECTION_GITHUB].get(config.GITHUB_SETTING_APP_NAME)
    build_env_cfg = get_build_env_cfg(cfg)
    arch_map = get_architecture_targets(cfg)
    repocfg = get_repo_cfg(cfg)
    allowed_exportvars = get_allowed_exportvars(cfg)

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

    # determine accelerator from action_filter argument
    accelerators = action_filter.get_filter_by_component(tools_filter.FILTER_COMPONENT_ACCEL)
    if len(accelerators) == 1:
        accelerator = accelerators[0]
    elif len(accelerators) > 1:
        log(f"{fn}(): found more than one ({len(accelerators)}) accelerator requirement")
        accelerator = None
    else:
        log(f"{fn}(): found no accelerator requirement")
        accelerator = None

    # determine exportvars from action_filter argument
    exportvars = action_filter.get_filter_by_component(tools_filter.FILTER_COMPONENT_EXPORT)

    # all exportvar filters must be allowed in order to run any jobs
    if exportvars:
        not_allowed = [x for x in exportvars if x not in allowed_exportvars]
        if not_allowed:
            log(f"{fn}(): exportvariable(s) {not_allowed} not allowed")
            return []

    jobs = []
    for arch, slurm_opt in arch_map.items():
        arch_dir = arch.replace('/', '_')
        # check if repo_target_map contains an entry for {arch}
        if arch not in repocfg[config.REPO_TARGETS_SETTING_REPO_TARGET_MAP]:
            log(f"{fn}(): skipping arch {arch} because repo target map does not define repositories to build for")
            continue
        for repo_id in repocfg[config.REPO_TARGETS_SETTING_REPO_TARGET_MAP][arch]:
            # ensure repocfg contains information about the repository repo_id if repo_id != EESSI
            # Note, EESSI is a bad/misleading name, it should be more like AS_IN_CONTAINER
            if (repo_id != "EESSI" and repo_id != "EESSI-pilot") and repo_id not in repocfg:
                log(f"{fn}(): skipping repo {repo_id}, it is not defined in repo"
                    "config {repocfg[config.REPO_TARGETS_SETTING_REPOS_CFG_DIR]}")
                continue

            # if filter exists, check filter against context = (arch, repo, app_name)
            #   true --> log & go on in this iteration of for loop
            #   false --> log & continue to next iteration of for loop
            if action_filter:
                log(f"{fn}(): checking filter {action_filter.to_string()}")
                context = {"architecture": arch, "repository": repo_id, "instance": app_name}
                log(f"{fn}(): context is '{json.dumps(context, indent=4)}'")
                if not action_filter.check_build_filters(context):
                    log(f"{fn}(): context does NOT satisfy filter(s), skipping")
                    continue
                else:
                    log(f"{fn}(): context DOES satisfy filter(s), going on with job")
            # we reached this point when the filter matched (otherwise we
            # 'continue' with the next repository)
            # for each match of the filter we create a specific job directory
            #   however, matching CPU architectures works differently to handling
            #   accelerators; multiple CPU architectures defined in arch_target_map
            #   can match the (CPU) architecture component of a filter; in
            #   contrast, the value of the accelerator filter is just passed down
            #   to scripts in bot/ directory of the pull request (see function
            #   prepare_job_cfg and creation of Job tuple below)
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

            log(f"{fn}(): arch = '{arch}' => cpu_target = '{cpu_target}' , os_type = '{os_type}'"
                f", accelerator = '{accelerator}'")

            prepare_job_cfg(job_dir, build_env_cfg, repocfg, repo_id, cpu_target, os_type, accelerator)

            if exportvars:
                prepare_export_vars_file(job_dir, exportvars)

            # enlist jobs to proceed
            job = Job(job_dir, arch, repo_id, slurm_opt, year_month, pr_id, accelerator)
            jobs.append(job)

    log(f"{fn}(): {len(jobs)} jobs to proceed after applying white list")
    if jobs:
        log(json.dumps(jobs, indent=4))

    return jobs


def prepare_job_cfg(job_dir, build_env_cfg, repos_cfg, repo_id, software_subdir, os_type, accelerator):
    """
    Set up job configuration file 'job.cfg' in directory <job_dir>/cfg

    Args:
        job_dir (string): working directory of the job
        build_env_cfg (dict): build environment settings
        repos_cfg (dict): configuration settings for all repositories
        repo_id (string): identifier of the repository to build for
        software_subdir (string): software subdirectory to build for (e.g., 'x86_64/generic')
        os_type (string): type of the os (e.g., 'linux')
        accelerator (string): defines accelerator to build for (e.g., 'nvidia/cc80')

    Returns:
        None (implicitly)
    """
    fn = sys._getframe().f_code.co_name

    jobcfg_dir = os.path.join(job_dir, job_metadata.JOB_CFG_DIRECTORY_NAME)
    # create ini file job.cfg with entries (some values are taken from the
    #   arguments of the function, some from settings in 'app.cfg', some from the
    #   repository's definition, some combine two values):
    # [site_config]
    # local_tmp = config.BUILDENV_SETTING_LOCAL_TMP
    # site_config_script = config.BUILDENV_SETTING_SITE_CONFIG_SCRIPT
    # shared_fs_path = config.BUILDENV_SETTING_SHARED_FS_PATH
    # build_logs_dir = config.BUILDENV_SETTING_BUILD_LOGS_DIR
    #
    # [repository]
    # repos_cfg_dir = job_dir/job_metadata.JOB_CFG_DIRECTORY_NAME
    # repo_id = repo_id
    # container = repos_cfg[cvmfs_repository.REPOS_CFG_CONTAINER]
    # repo_name = repo_cfg[cvmfs_repository.REPOS_CFG_REPO_NAME]
    # repo_version = repo_cfg[cvmfs_repository.REPOS_CFG_REPO_VERSION]
    #
    # [architecture]
    # software_subdir = software_subdir
    # os_type = os_type
    # accelerator = accelerator
    job_cfg = configparser.ConfigParser()
    job_cfg[job_metadata.JOB_CFG_SITE_CONFIG_SECTION] = {}
    build_env_to_job_cfg_keys = {
        config.BUILDENV_SETTING_BUILD_LOGS_DIR: job_metadata.JOB_CFG_SITE_CONFIG_BUILD_LOGS_DIR,
        config.BUILDENV_SETTING_CONTAINER_CACHEDIR: job_metadata.JOB_CFG_SITE_CONFIG_CONTAINER_CACHEDIR,
        config.BUILDENV_SETTING_HTTP_PROXY: job_metadata.JOB_CFG_SITE_CONFIG_HTTP_PROXY,
        config.BUILDENV_SETTING_HTTPS_PROXY: job_metadata.JOB_CFG_SITE_CONFIG_HTTPS_PROXY,
        config.BUILDENV_SETTING_LOAD_MODULES: job_metadata.JOB_CFG_SITE_CONFIG_LOAD_MODULES,
        config.BUILDENV_SETTING_LOCAL_TMP: job_metadata.JOB_CFG_SITE_CONFIG_LOCAL_TMP,
        config.BUILDENV_SETTING_SHARED_FS_PATH: job_metadata.JOB_CFG_SITE_CONFIG_SHARED_FS_PATH,
        config.BUILDENV_SETTING_SITE_CONFIG_SCRIPT: job_metadata.JOB_CFG_SITE_CONFIG_SITE_CONFIG_SCRIPT,
    }
    for build_env_key, job_cfg_key in build_env_to_job_cfg_keys.items():
        if build_env_cfg[build_env_key]:
            job_cfg[job_metadata.JOB_CFG_SITE_CONFIG_SECTION][job_cfg_key] = build_env_cfg[build_env_key]

    job_cfg[job_metadata.JOB_CFG_REPOSITORY_SECTION] = {}
    # directory for repos.cfg
    # NOTE config.REPO_TARGETS_SETTING_REPOS_CFG_DIR is a global configuration
    #      setting for all repositories, hence it is stored in repos_cfg whereas
    #      repo_cfg used further below contains setting for a specific repository
    repo_section_str = job_metadata.JOB_CFG_REPOSITORY_SECTION
    cfg_repos_cfg_dir = config.REPO_TARGETS_SETTING_REPOS_CFG_DIR
    if cfg_repos_cfg_dir in repos_cfg and repos_cfg[cfg_repos_cfg_dir]:
        job_cfg[repo_section_str][job_metadata.JOB_CFG_REPOSITORY_REPOS_CFG_DIR] = jobcfg_dir
    # repo id
    job_cfg[repo_section_str][job_metadata.JOB_CFG_REPOSITORY_REPO_ID] = repo_id

    # settings for a specific repository
    if repo_id in repos_cfg:
        repo_cfg = repos_cfg[repo_id]
        if repo_cfg[cvmfs_repository.REPOS_CFG_CONTAINER]:
            job_cfg_repo_container = job_metadata.JOB_CFG_REPOSITORY_CONTAINER
            job_cfg[repo_section_str][job_cfg_repo_container] = repo_cfg[cvmfs_repository.REPOS_CFG_CONTAINER]
        if repo_cfg[cvmfs_repository.REPOS_CFG_REPO_NAME]:
            job_cfg_repo_name = job_metadata.JOB_CFG_REPOSITORY_REPO_NAME
            job_cfg[repo_section_str][job_cfg_repo_name] = repo_cfg[cvmfs_repository.REPOS_CFG_REPO_NAME]
        if repo_cfg[cvmfs_repository.REPOS_CFG_REPO_VERSION]:
            job_cfg_repo_version = job_metadata.JOB_CFG_REPOSITORY_REPO_VERSION
            job_cfg[repo_section_str][job_cfg_repo_version] = repo_cfg[cvmfs_repository.REPOS_CFG_REPO_VERSION]

    job_cfg_arch_section = job_metadata.JOB_CFG_ARCHITECTURE_SECTION
    job_cfg[job_cfg_arch_section] = {}
    job_cfg[job_cfg_arch_section][job_metadata.JOB_CFG_ARCHITECTURE_SOFTWARE_SUBDIR] = software_subdir
    job_cfg[job_cfg_arch_section][job_metadata.JOB_CFG_ARCHITECTURE_OS_TYPE] = os_type
    job_cfg[job_cfg_arch_section][job_metadata.JOB_CFG_ARCHITECTURE_ACCELERATOR] = accelerator if accelerator else ''

    # copy contents of directory containing repository configuration to directory
    # containing job configuration/metadata
    if cfg_repos_cfg_dir in repos_cfg and repos_cfg[cfg_repos_cfg_dir] and os.path.isdir(repos_cfg[cfg_repos_cfg_dir]):
        src = repos_cfg[cfg_repos_cfg_dir]
        shutil.copytree(src, jobcfg_dir)
        log(f"{fn}(): copied {src} to {jobcfg_dir}")

    # make sure that <jobcfg_dir> exists (in case it wasn't just copied)
    os.makedirs(jobcfg_dir, exist_ok=True)

    jobcfg_file = os.path.join(jobcfg_dir, job_metadata.JOB_CFG_FILENAME)
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
        - (string): path config.BUILDENV_SETTING_JOBS_BASE_DIR/job.year_month/job.pr_id/SLURM_JOBID which
          is a symlink to the job's working directory (job[0] or job.working_dir)
    """
    fn = sys._getframe().f_code.co_name

    build_env_cfg = get_build_env_cfg(cfg)

    # the job_name is used to filter jobs in case multiple bot
    # instances run on the same system
    job_name = cfg[config.SECTION_BUILDENV].get(config.BUILDENV_SETTING_JOB_NAME)

    # add a default time limit of 24h to the job submit command if no other time
    # limit is specified already
    all_opts_str = " ".join([build_env_cfg[config.BUILDENV_SETTING_SLURM_PARAMS], job.slurm_opts])
    all_opts_list = all_opts_str.split(" ")
    if any([(opt.startswith("--time") or opt.startswith("-t")) for opt in all_opts_list]):
        time_limit = ""
    else:
        time_limit = f"--time={DEFAULT_JOB_TIME_LIMIT}"

    # update job.slurm_opts with det_submit_opts(job) in det_submit_opts.py if allowed and available
    do_update_slurm_opts = False
    allow_update_slurm_opts = cfg[config.SECTION_BUILDENV].getboolean(config.BUILDENV_SETTING_ALLOW_UPDATE_SUBMIT_OPTS)

    if allow_update_slurm_opts:
        sys.path.append(job.working_dir)

        try:
            from det_submit_opts import det_submit_opts  # pylint:disable=import-outside-toplevel
            do_update_slurm_opts = True
        except ImportError:
            log(f"{fn}(): not updating job.slurm_opts: "
                "cannot import function det_submit_opts from module det_submit_opts")

    if do_update_slurm_opts:
        job = job._replace(slurm_opts=det_submit_opts(job))
        log(f"{fn}(): updated job.slurm_opts: {job.slurm_opts}")

    build_job_script = build_env_cfg[config.BUILDENV_SETTING_BUILD_JOB_SCRIPT]
    if isinstance(build_job_script, str):
        build_job_script_path = build_job_script
        log(f"{fn}(): path to build job script: {build_job_script_path}")
    elif isinstance(build_job_script, dict):
        build_job_script_repo = build_job_script.get('repo')
        if build_job_script_repo:
            log(f"{fn}(): repository in which build job script is located: {build_job_script_repo}")
        else:
            error(f"Failed to determine repository in which build job script is located from: {build_job_script}")

        build_job_script_path = build_job_script.get('path')
        if build_job_script_path:
            log(f"{fn}(): path to build job script in repository: {build_job_script_path}")
        else:
            error(f"Failed to determine path of build job script in repository from: {build_job_script}")

        # clone repo to temporary directory, and correctly set path to build job script
        repo_subdir = build_job_script_repo.split('/')[-1]
        if repo_subdir.endswith('.git'):
            repo_subdir = repo_subdir[:-4]
        target_dir = os.path.join(job.working_dir, repo_subdir)
        os.makedirs(target_dir, exist_ok=True)

        clone_output, clone_error, clone_exit_code = clone_git_repo(build_job_script_repo, target_dir)
        if clone_exit_code == 0:
            log(f"{fn}(): repository {build_job_script_repo} cloned to {target_dir}")
        else:
            error(f"Failed to clone repository {build_job_script_repo}: {clone_error}")

        build_job_script_path = os.path.join(target_dir, build_job_script_path)
    else:
        error(f"Incorrect build job script specification, unknown type: {build_job_script}")

    if not os.path.exists(build_job_script_path):
        error(f"Build job script not found at {build_job_script_path}")

    command_line = ' '.join([
        build_env_cfg[config.BUILDENV_SETTING_SUBMIT_COMMAND],
        build_env_cfg[config.BUILDENV_SETTING_SLURM_PARAMS],
        time_limit,
        job.slurm_opts] +
        ([f"--job-name='{job_name}'"] if job_name else []) +
        [build_job_script_path])

    cmdline_output, cmdline_error, cmdline_exit_code = run_cmd(command_line,
                                                               "submit job for target '%s'" % job.arch_target,
                                                               working_dir=job.working_dir)

    # sbatch output is 'Submitted batch job JOBID'
    #   parse job id, add it to array of submitted jobs and create a symlink
    #   from config.BUILDENV_SETTING_JOBS_BASE_DIR/job.year_month/job.pr_id/SLURM_JOBID to the job's
    #   working directory
    log(f"{fn}(): sbatch out: {cmdline_output}")
    log(f"{fn}(): sbatch err: {cmdline_error}")

    job_id = cmdline_output.split()[3]

    symlink = os.path.join(build_env_cfg[config.BUILDENV_SETTING_JOBS_BASE_DIR], job.year_month, job.pr_id, job_id)
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

    submitted_job_comments_cfg = config.read_config()[config.SECTION_SUBMITTED_JOB_COMMENTS]

    # set string for accelerator if job.accelerator is defined/set (e.g., not None)
    accelerator_spec_str = ''
    if job.accelerator:
        accelerator_spec = f"{submitted_job_comments_cfg[config.SUBMITTED_JOB_COMMENTS_SETTING_WITH_ACCELERATOR]}"
        accelerator_spec_str = accelerator_spec.format(accelerator=job.accelerator)

    # get current date and time
    dt = datetime.now(timezone.utc)

    # construct initial job comment
    buildenv = config.read_config()[config.SECTION_BUILDENV]
    job_handover_protocol = buildenv.get(config.BUILDENV_SETTING_JOB_HANDOVER_PROTOCOL)
    if job_handover_protocol == config.JOB_HANDOVER_PROTOCOL_DELAYED_BEGIN:
        release_msg_string = config.SUBMITTED_JOB_COMMENTS_SETTING_AWAITS_RELEASE_DELAYED_BEGIN_MSG
        release_comment_template = submitted_job_comments_cfg[release_msg_string]
        # calculate delay from poll_interval and delay_factor
        job_manager_cfg = config.read_config()[config.SECTION_JOB_MANAGER]
        poll_interval = int(job_manager_cfg.get(config.JOB_MANAGER_SETTING_POLL_INTERVAL))
        delay_factor = float(buildenv.get(config.BUILDENV_SETTING_JOB_DELAY_BEGIN_FACTOR, 2))
        eligible_in_seconds = int(poll_interval * delay_factor)
        job_comment = (f"{submitted_job_comments_cfg[config.SUBMITTED_JOB_COMMENTS_SETTING_INITIAL_COMMENT]}"
                       f"\n|date|job status|comment|\n"
                       f"|----------|----------|------------------------|\n"
                       f"|{dt.strftime('%b %d %X %Z %Y')}|"
                       f"submitted|"
                       f"{release_comment_template}|").format(
                           app_name=app_name,
                           arch_name=arch_name,
                           symlink=symlink,
                           repo_id=job.repo_id,
                           job_id=job_id,
                           delay_seconds=eligible_in_seconds,
                           accelerator_spec=accelerator_spec_str)
    else:
        release_msg_string = config.SUBMITTED_JOB_COMMENTS_SETTING_AWAITS_RELEASE_HOLD_RELEASE_MSG
        release_comment_template = submitted_job_comments_cfg[release_msg_string]
        job_comment = (f"{submitted_job_comments_cfg[config.SUBMITTED_JOB_COMMENTS_SETTING_INITIAL_COMMENT]}"
                       f"\n|date|job status|comment|\n"
                       f"|----------|----------|------------------------|\n"
                       f"|{dt.strftime('%b %d %X %Z %Y')}|"
                       f"submitted|"
                       f"{release_comment_template}|").format(
                           app_name=app_name,
                           arch_name=arch_name,
                           symlink=symlink,
                           repo_id=job.repo_id,
                           job_id=job_id,
                           accelerator_spec=accelerator_spec_str)

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
    app_name = cfg[config.SECTION_GITHUB].get(config.GITHUB_SETTING_APP_NAME)

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
        job_metadata.create_metadata_file(job, job_id, pr_comment)

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

    buildenv = cfg[config.SECTION_BUILDENV]

    build_permission = buildenv.get(config.BUILDENV_SETTING_BUILD_PERMISSION, '')

    log(f"{fn}(): build permission '{build_permission}'")

    build_labeler = event_info['raw_request_body']['sender']['login']
    if build_labeler not in build_permission.split():
        log(f"{fn}(): GH account '{build_labeler}' is not authorized to build")
        no_build_permission_comment = buildenv.get(config.BUILDENV_SETTING_NO_BUILD_PERMISSION_COMMENT)
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
            submitted_job_comments_section = cfg[config.SECTION_SUBMITTED_JOB_COMMENTS]
            initial_comment_fmt = submitted_job_comments_section[config.SUBMITTED_JOB_COMMENTS_SETTING_INITIAL_COMMENT]
            if initial_comment_fmt[:20] in comment['body']:

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
