# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Sondre Bergsvaag Risanger (@sondrebr)
#
# license: GPLv2
#

# Standard library imports
import os
from typing import Union

# Third party imports (anything installed into the local Python environment)
# (none)

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from connections import github, gitlab
from tools import config, logging, run_cmd


GITHUB = "github"
GITLAB = "gitlab"

SUPPORTED_GIT_HOSTS = {
    GITHUB,
    GITLAB,
}

_git_host = None

# Error codes used to indicate failed stages in Git operations
ERROR_CURL = "curl"
ERROR_GIT_APPLY = "git apply"
ERROR_GIT_CHECKOUT = "git checkout"
ERROR_GIT_CLONE = "git clone"
ERROR_GIT_FETCH = "git fetch"
ERROR_GIT_DIFF = "git diff"
ERROR_MAKE_DIRS = "makedirs"
ERROR_PR_DIFF = "pr_diff"
ERROR_NONE = "none"


def get_git_hosting_platform(cfg=None):
    """
    Read the config and get the Git hosting platform the bot is configured for.
    Exit if the setting is invalid or not set.

    Args:
        cfg (ConfigParser): Instance of ConfigParser containing the configuration.
            May be passed by caller to avoid re-reading the configuration file.

    Returns:
        (str): The configured Git hosting platform
    """
    global _git_host
    if not _git_host:
        if not cfg:
            cfg = config.read_config()
        _git_host = cfg.get(config.SECTION_GIT, config.GIT_SETTING_HOSTING_PLATFORM, fallback=None)
        if _git_host not in SUPPORTED_GIT_HOSTS:
            logging.error(f"Invalid Git host configured: '{_git_host}'")
    return _git_host


def connect_to_git_hosting_platform():
    """
    Establish connection to Git hosting platform. Exit if the configured hosting
    platform is not supported by the bot.

    Args:
        No arguments

    Returns:
        None (implicit)
    """
    git_host = get_git_hosting_platform()
    if git_host == GITHUB:
        github.connect()
    elif git_host == GITLAB:
        gitlab.connect()
    else:
        logging.error(f"Git host not supported: '{git_host}'")


# TODO: We might consider merging these settings later, for example as an 'app_name' setting in the 'git' section
def get_app_name(cfg=None):
    """
    Get the configured app/bot name.

    Args:
        cfg (ConfigParser): Instance of ConfigParser containing the configuration.
            May be passed by caller to avoid re-reading the configuration file.

    Returns:
        (str): The configured app/bot name or None
    """
    if not cfg:
        cfg = config.read_config()
    git_host = get_git_hosting_platform(cfg)
    if git_host == GITHUB:
        return cfg.get(config.SECTION_GITHUB, config.GITHUB_SETTING_APP_NAME)
    elif git_host == GITLAB:
        return cfg.get(config.SECTION_GITLAB, config.GITLAB_SETTING_BOT_NAME)
    return None


class BaseGitRepository:
    """
    Base class to use for interacting with Git repositories using Git commands.

    Args:
        repo_url (str): The repository URL, as used by 'git clone'
        directory (str or pathlib.Path): The directory the repository should be cloned to, as used
            by 'git clone'. The directory and its parents will be created when running the clone()
            method if they do not already exist.
    """
    def __init__(self, repo_url, directory):
        if self.__class__ is BaseGitRepository:
            err_msg = "Do not use this base class directly. "
            err_msg += "Please use one of its subclasses instead."
            raise NotImplementedError(err_msg)
        self._repo_url = repo_url
        self._directory = directory
        self._cloned = False

    _EC_OK = 0
    _EC_NOT_OK = 1
    _MSG_REPO_ALREADY_CLONED = "The repository has already been cloned!"
    _ERR_MSG_REPO_NOT_CLONED_YET = "The repository has not been cloned yet!"
    _ALREADY_CLONED = (_MSG_REPO_ALREADY_CLONED, "", _EC_OK, ERROR_NONE)
    _NOT_CLONED_YET = ("", _ERR_MSG_REPO_NOT_CLONED_YET, _EC_NOT_OK)

    def _get_pr_diff(self, pr_number, diff_filename):
        # 'pull/#/head' is used for PR ref names on GitHub, Codeberg, Gitea, ...
        src_ref = f"pull/{pr_number}/head"
        dst_ref = f"pr{pr_number}"

        stdout, stderr, exit_code, error_stage = self.fetch(src_ref, dst_ref)
        if exit_code != 0:
            return stdout, stderr, exit_code, error_stage

        stdout, stderr, exit_code, error_stage = self.diff("HEAD", dst_ref, diff_filename, merge_base=True)
        if exit_code != 0:
            return stdout, stderr, exit_code, error_stage

        return "Obtaining PR diff succeeded", "", self._EC_OK, ERROR_NONE

    def _make_dirs(self):
        try:
            os.makedirs(self._directory, exist_ok=True)
        except Exception as err:
            err_msg = f"Unable to set up directory '{self._directory}' for Git repository '{self._repo_url}': '{err}'"
            return "", err_msg, self._EC_NOT_OK, ERROR_MAKE_DIRS
        return "Creating directories succeeded", "", self._EC_OK, ERROR_NONE

    def clone(self):
        if self._cloned:
            return self._ALREADY_CLONED

        # Ensure 'self._directory' exists
        stdout, stderr, exit_code, error_stage = self._make_dirs()
        if exit_code != 0:
            return stdout, stderr, exit_code, error_stage

        clone_cmd = f"git clone {self._repo_url} {self._directory}"
        clone_msg = f"Cloning repository '{self._repo_url}' to '{self._directory}'"
        stdout, stderr, exit_code = run_cmd(clone_cmd, clone_msg, self._directory, raise_on_error=False)
        if exit_code == 0:
            self._cloned = True
            error_stage = ERROR_NONE
        else:
            error_stage = ERROR_GIT_CLONE
        return stdout, stderr, exit_code, error_stage

    def checkout(self, branch_name):
        if not self._cloned:
            return *self._NOT_CLONED_YET, ERROR_GIT_CHECKOUT
        checkout_cmd = f"git checkout {branch_name}"
        checkout_msg = f"Checkout branch '{branch_name}'"
        stdout, stderr, exit_code = run_cmd(checkout_cmd, checkout_msg, self._directory, raise_on_error=False)
        error_stage = ERROR_NONE if (exit_code == 0) else ERROR_GIT_CHECKOUT
        return stdout, stderr, exit_code, error_stage

    def fetch(self, src_ref, dst_ref):
        if not self._cloned:
            return *self._NOT_CLONED_YET, ERROR_GIT_FETCH
        fetch_cmd = f"git fetch origin {src_ref}:{dst_ref}"
        fetch_msg = f"Fetching ref '{src_ref}' as '{dst_ref}'"
        stdout, stderr, exit_code = run_cmd(fetch_cmd, fetch_msg, self._directory, raise_on_error=False)
        error_stage = ERROR_NONE if (exit_code == 0) else ERROR_GIT_FETCH
        return stdout, stderr, exit_code, error_stage

    def diff(self, commit_a, commit_b, diff_filename, merge_base=False):
        if not self._cloned:
            return *self._NOT_CLONED_YET, ERROR_GIT_DIFF
        diff_cmd = "git diff "
        diff_msg = f"Storing diff of '{commit_b}' compared to "
        if merge_base:
            diff_cmd += "--merge-base "
            diff_msg += "its merge base with "
        diff_cmd += f"{commit_a} {commit_b} > {diff_filename}"
        diff_msg += f"'{commit_a}' in '{diff_filename}'"
        stdout, stderr, exit_code = run_cmd(diff_cmd, diff_msg, self._directory, raise_on_error=False)
        error_stage = ERROR_NONE if (exit_code == 0) else ERROR_GIT_DIFF
        return stdout, stderr, exit_code, error_stage

    def apply(self, patch):
        if not self._cloned:
            return *self._NOT_CLONED_YET, ERROR_GIT_APPLY
        apply_cmd = f"git apply {patch}"
        apply_msg = f"Applying patch '{patch}'"
        stdout, stderr, exit_code = run_cmd(apply_cmd, apply_msg, self._directory, raise_on_error=False)
        error_stage = ERROR_NONE if (exit_code == 0) else ERROR_GIT_APPLY
        return stdout, stderr, exit_code, error_stage

    def download_pr(self, pr_number, base_branch):
        # Steps to download a PR:
        # - Clone repository
        # - Checkout base branch
        # - Get PR diff (i.e. diff of target branch compared to its merge base with base branch)
        #   - This step must be implemented per Git hosting platform, as e.g. target branch ref naming may vary
        # - Apply PR diff
        diff_filename = f"{pr_number}.diff"

        # Clone repo - if it is already cloned it returns _EC_OK = 0
        stdout, stderr, exit_code, error_stage = self.clone()
        if exit_code != 0:
            return stdout, stderr, exit_code, error_stage

        stdout, stderr, exit_code, error_stage = self.checkout(base_branch)
        if exit_code != 0:
            return stdout, stderr, exit_code, error_stage

        stdout, stderr, exit_code, error_stage = self._get_pr_diff(pr_number, diff_filename)
        if exit_code != 0:
            return stdout, stderr, exit_code, error_stage

        stdout, stderr, exit_code, error_stage = self.apply(diff_filename)
        if exit_code != 0:
            return stdout, stderr, exit_code, error_stage

        return "Downloading PR succeeded", "", self._EC_OK, ERROR_NONE


class GitHubGitRepository(BaseGitRepository):
    # No overrides needed
    pass


class GitLabGitRepository(BaseGitRepository):
    def _get_pr_diff(self, pr_number, diff_filename):
        # Requires override for GitLab. Contrary to most other Git hosting
        # platforms, GitLab uses 'merge-requests/#/head' for PR ref names.
        src_ref = f"merge-requests/{pr_number}/head"
        dst_ref = f"pr{pr_number}"

        stdout, stderr, exit_code, error_stage = self.fetch(src_ref, dst_ref)
        if exit_code != 0:
            return stdout, stderr, exit_code, error_stage

        stdout, stderr, exit_code, error_stage = self.diff("HEAD", dst_ref, diff_filename, merge_base=True)
        if exit_code != 0:
            return stdout, stderr, exit_code, error_stage

        return "Obtaining PR diff succeeded", "", self._EC_OK, ERROR_NONE


GitRepository = Union[GitHubGitRepository, GitLabGitRepository]


def create_git_repository_instance(repo_url, directory, git_host):
    """
    Creates a GitRepository instance for the given Git hosting platform.

    Args:
        repo_url (str): The HTTPS or SSH URL of the repository, as used by 'git clone'
        directory (str or pathlib.Path): The directory the repository should be cloned to. The
            directory will be created when calling clone() if it does not exist. If it already
            exists it must be empty, otherwise cloning will fail.
        git_host (str): The Git hosting platform the repository given as 'repo_url' is hosted on.
            Must be either 'github' or 'gitlab'. Can be set independently of the configured Git
            hosting platform (e.g. 'github' can be given even if the bot is configured for GitLab).

    Returns:
        GitRepository instance or None
    """
    if git_host == GITHUB:
        return GitHubGitRepository(repo_url, directory)
    elif git_host == GITLAB:
        return GitLabGitRepository(repo_url, directory)
    return None
