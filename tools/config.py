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
# author: Thomas Roeblitz (@trz42)
# author: Sam Moors (@smoors)
#
# license: GPLv2
#

# Standard library imports
import configparser
import sys

# Third party imports (anything installed into the local Python environment)
# (none yet)

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from .logging import error

# define configuration constants
#   SECTION_sectionname for any section name in app.cfg
#   sectionname_SETTING_settingname for any setting with name settingname in
#     section sectionname
SECTION_ARCHITECTURETARGETS = 'architecturetargets'
ARCHITECTURETARGETS_SETTING_ARCH_TARGET_MAP = 'arch_target_map'

SECTION_BOT_CONTROL = 'bot_control'
BOT_CONTROL_SETTING_COMMAND_PERMISSION = 'command_permission'
BOT_CONTROL_SETTING_COMMAND_RESPONSE_FMT = 'command_response_fmt'
BOT_CONTROL_SETTING_CHATLEVEL = 'chatlevel'

SECTION_BUILDENV = 'buildenv'
BUILDENV_SETTING_ALLOWED_EXPORTVARS = 'allowed_exportvars'
BUILDENV_SETTING_ALLOW_UPDATE_SUBMIT_OPTS = 'allow_update_submit_opts'
BUILDENV_SETTING_BUILD_JOB_SCRIPT = 'build_job_script'
BUILDENV_SETTING_BUILD_LOGS_DIR = 'build_logs_dir'
BUILDENV_SETTING_BUILD_PERMISSION = 'build_permission'
BUILDENV_SETTING_CLONE_GIT_REPO_VIA = 'clone_git_repo_via'
BUILDENV_SETTING_CONTAINER_CACHEDIR = 'container_cachedir'
BUILDENV_SETTING_CVMFS_CUSTOMIZATIONS = 'cvmfs_customizations'
BUILDENV_SETTING_HTTPS_PROXY = 'https_proxy'
BUILDENV_SETTING_HTTP_PROXY = 'http_proxy'
BUILDENV_SETTING_JOB_DELAY_BEGIN_FACTOR = 'job_delay_begin_factor'
BUILDENV_SETTING_JOB_HANDOVER_PROTOCOL = 'job_handover_protocol'
BUILDENV_SETTING_JOB_NAME = 'job_name'
BUILDENV_SETTING_JOBS_BASE_DIR = 'jobs_base_dir'
BUILDENV_SETTING_LOAD_MODULES = 'load_modules'
BUILDENV_SETTING_LOCAL_TMP = 'local_tmp'
BUILDENV_SETTING_NO_BUILD_PERMISSION_COMMENT = 'no_build_permission_comment'
BUILDENV_SETTING_SHARED_FS_PATH = 'shared_fs_path'
BUILDENV_SETTING_SITE_CONFIG_SCRIPT = 'site_config_script'
BUILDENV_SETTING_SLURM_PARAMS = 'slurm_params'
BUILDENV_SETTING_SUBMIT_COMMAND = 'submit_command'

SECTION_DEPLOYCFG = 'deploycfg'
DEPLOYCFG_SETTING_ARTEFACT_PREFIX = 'artefact_prefix'
DEPLOYCFG_SETTING_ARTEFACT_UPLOAD_SCRIPT = 'artefact_upload_script'
DEPLOYCFG_SETTING_BUCKET_NAME = 'bucket_name'
DEPLOYCFG_SETTING_DEPLOY_PERMISSION = 'deploy_permission'
DEPLOYCFG_SETTING_ENDPOINT_URL = 'endpoint_url'
DEPLOYCFG_SETTING_METADATA_PREFIX = 'metadata_prefix'
DEPLOYCFG_SETTING_NO_DEPLOY_PERMISSION_COMMENT = 'no_deploy_permission_comment'
DEPLOYCFG_SETTING_SIGNING = 'signing'
DEPLOYCFG_SETTING_SIGNING_CONTAINER_RUNTIME = 'container_runtime'
DEPLOYCFG_SETTING_SIGNING_KEY = 'key'
DEPLOYCFG_SETTING_SIGNING_SCRIPT = 'script'
DEPLOYCFG_SETTING_UPLOAD_POLICY = 'upload_policy'

SECTION_DOWNLOAD_PR_COMMENTS = 'download_pr_comments'
DOWNLOAD_PR_COMMENTS_SETTING_CURL_FAILURE = 'curl_failure'
DOWNLOAD_PR_COMMENTS_SETTING_CURL_TIP = 'curl_tip'
DOWNLOAD_PR_COMMENTS_SETTING_GIT_APPLY_FAILURE = 'git_apply_failure'
DOWNLOAD_PR_COMMENTS_SETTING_GIT_APPLY_TIP = 'git_apply_tip'
DOWNLOAD_PR_COMMENTS_SETTING_GIT_CHECKOUT_FAILURE = 'git_checkout_failure'
DOWNLOAD_PR_COMMENTS_SETTING_GIT_CHECKOUT_TIP = 'git_checkout_tip'
DOWNLOAD_PR_COMMENTS_SETTING_GIT_CLONE_FAILURE = 'git_clone_failure'
DOWNLOAD_PR_COMMENTS_SETTING_GIT_CLONE_TIP = 'git_clone_tip'
DOWNLOAD_PR_COMMENTS_SETTING_PR_DIFF_FAILURE = 'pr_diff_failure'
DOWNLOAD_PR_COMMENTS_SETTING_PR_DIFF_TIP = 'pr_diff_tip'

SECTION_EVENT_HANDLER = 'event_handler'
EVENT_HANDLER_SETTING_LOG_PATH = 'log_path'

SECTION_FINISHED_JOB_COMMENTS = 'finished_job_comments'
FINISHED_JOB_COMMENTS_SETTING_JOB_RESULT_UNKNOWN_FMT = 'job_result_unknown_fmt'
FINISHED_JOB_COMMENTS_SETTING_JOB_TEST_UNKNOWN_FMT = 'job_test_unknown_fmt'

SECTION_GITHUB = 'github'
GITHUB_SETTING_APP_ID = 'app_id'
GITHUB_SETTING_APP_NAME = 'app_name'
GITHUB_SETTING_INSTALLATION_ID = 'installation_id'
GITHUB_SETTING_PRIVATE_KEY = 'private_key'

SECTION_JOB_MANAGER = 'job_manager'
JOB_MANAGER_SETTING_LOG_PATH = 'log_path'
JOB_MANAGER_SETTING_JOB_IDS_DIR = 'job_ids_dir'
JOB_MANAGER_SETTING_POLL_COMMAND = 'poll_command'
JOB_MANAGER_SETTING_POLL_INTERVAL = 'poll_interval'
JOB_MANAGER_SETTING_SCONTROL_COMMAND = 'scontrol_command'

SECTION_NEW_JOB_COMMENTS = 'new_job_comments'
NEW_JOB_COMMENTS_SETTING_AWAITS_LAUNCH = 'awaits_launch'

SECTION_REPO_TARGETS = 'repo_targets'
REPO_TARGETS_SETTING_REPO_TARGET_MAP = 'repo_target_map'
REPO_TARGETS_SETTING_REPOS_CFG_DIR = 'repos_cfg_dir'

SECTION_RUNNING_JOB_COMMENTS = 'running_job_comments'
RUNNING_JOB_COMMENTS_SETTING_RUNNING_JOB = 'running_job'

SECTION_SUBMITTED_JOB_COMMENTS = 'submitted_job_comments'
# SUBMITTED_JOB_COMMENTS_SETTING_AWAITS_RELEASE is DEPRECATED
SUBMITTED_JOB_COMMENTS_SETTING_AWAITS_RELEASE = 'awaits_release'
SUBMITTED_JOB_COMMENTS_SETTING_AWAITS_RELEASE_DELAYED_BEGIN_MSG = 'awaits_release_delayed_begin_msg'
SUBMITTED_JOB_COMMENTS_SETTING_AWAITS_RELEASE_HOLD_RELEASE_MSG = 'awaits_release_hold_release_msg'
SUBMITTED_JOB_COMMENTS_SETTING_INITIAL_COMMENT = 'initial_comment'
SUBMITTED_JOB_COMMENTS_SETTING_WITH_ACCELERATOR = 'with_accelerator'

SECTION_CLEAN_UP = 'clean_up'
CLEAN_UP_SETTING_TRASH_BIN_ROOT_DIR = 'trash_bin_dir'
CLEAN_UP_SETTING_MOVED_JOB_DIRS_COMMENT = 'moved_job_dirs_comment'

# definition of values
JOB_HANDOVER_PROTOCOL_DELAYED_BEGIN = 'delayed_begin'
JOB_HANDOVER_PROTOCOL_HOLD_RELEASE = 'hold_release'
JOB_HANDOVER_PROTOCOLS_SET = {
    JOB_HANDOVER_PROTOCOL_DELAYED_BEGIN,
    JOB_HANDOVER_PROTOCOL_HOLD_RELEASE
}


def read_config(path='app.cfg'):
    """
    Read the config file

    Args:
        path (string): path to the configuration file

    Returns:
        dict (str, dict): dictionary containing configuration settings or exit
            if Exception is caught
    """
    fn = sys._getframe().f_code.co_name

    try:
        config = configparser.ConfigParser()
        config.read(path)
    except Exception as err:
        error(f"{fn}(): Unable to read configuration file {path}!\n{err}")

    return config


def check_required_cfg_settings(req_settings, path="app.cfg"):
    """
    Reads the config file, checks if it contains the required settings,
    if not logs an error message and exits.

    Args:
        req_settings (dict (str, list)): required settings
        path (string): path to the configuration file

    Returns:
        None (implicitly)
    """
    # TODO argument path is not being used
    cfg = read_config()
    # iterate over keys in req_settings which correspond to sections ([name])
    # in the configuration file (.ini format)
    for section in req_settings.keys():
        if section not in cfg:
            error(f'Missing section "{section}" in configuration file {path}.')
        # iterate over list elements required for the current section
        for item in req_settings[section]:
            if item not in cfg[section]:
                error(f'Missing configuration item "{item}" in section "{section}" of configuration file {path}.')
    return True
