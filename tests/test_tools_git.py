# Tests for 'tools/git.py' of the EESSI build-and-deploy bot,
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
import copy
import os
import sys
from unittest.mock import MagicMock, patch

# Third party imports (anything installed into the local Python environment)
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools import config, git


# Set up configs
CFG = config.read_config()

GITHUB_CFG = copy.deepcopy(CFG)
GITHUB_CFG.set(config.SECTION_GIT, config.GIT_SETTING_HOSTING_PLATFORM, git.GITHUB)

GITLAB_CFG = copy.deepcopy(CFG)
GITLAB_CFG.set(config.SECTION_GIT, config.GIT_SETTING_HOSTING_PLATFORM, git.GITLAB)

UNSUPPORTED_PLATFORM = "unsupported_platform"
UNSUPPORTED_PLATFORM_CFG = copy.deepcopy(CFG)
UNSUPPORTED_PLATFORM_CFG.set(config.SECTION_GIT, config.GIT_SETTING_HOSTING_PLATFORM, UNSUPPORTED_PLATFORM)

NO_HOSTING_PLATFORM_CFG = copy.deepcopy(CFG)
NO_HOSTING_PLATFORM_CFG.remove_option(config.SECTION_GIT, config.GIT_SETTING_HOSTING_PLATFORM)

# Get configured app/bot name
GITHUB_APP_NAME = GITHUB_CFG.get(config.SECTION_GITHUB, config.GITHUB_SETTING_APP_NAME)
GITLAB_BOT_NAME = GITLAB_CFG.get(config.SECTION_GITLAB, config.GITLAB_SETTING_BOT_NAME)

# For use in GitRepository tests
REPO_URL = "https://example.org/testuser/software-layer.git"


# Subclass for use in BaseGitRepository tests
class GenericGitRepository(git.BaseGitRepository):
    pass


# Test get_git_hosting_platform() - valid configs
@pytest.mark.parametrize("cfg,expected", [
    # 'hosting_platform' set to 'github'
    (CFG, git.GITHUB),
    (GITHUB_CFG, git.GITHUB),

    # 'hosting_platform' set to 'gitlab'
    (GITLAB_CFG, git.GITLAB),
])
@patch("tools.config.read_config")
def test_get_git_hosting_platform_valid(mock_read_config, cfg, expected):
    mock_read_config.return_value = cfg

    # Test with provided cfg
    git._git_host = None
    assert git.get_git_hosting_platform(cfg) == expected
    mock_read_config.assert_not_called()

    # Test without provided cfg
    git._git_host = None
    assert git.get_git_hosting_platform() == expected
    mock_read_config.assert_called_once()

    git._git_host = None


# Test get_git_hosting_platform() - invalid configs, should exit
@pytest.mark.parametrize("cfg", [
    # 'hosting_platform' set to an invalid value
    UNSUPPORTED_PLATFORM_CFG,

    # 'hosting_platform' not set
    NO_HOSTING_PLATFORM_CFG,
])
@patch("tools.config.read_config")
def test_get_git_hosting_platform_invalid(mock_read_config, cfg):
    mock_read_config.return_value = cfg

    # Test with provided cfg
    git._git_host = None
    with pytest.raises(SystemExit):
        git.get_git_hosting_platform(cfg)
    mock_read_config.assert_not_called()

    # Test without provided cfg
    git._git_host = None
    with pytest.raises(SystemExit):
        git.get_git_hosting_platform()
    mock_read_config.assert_called_once()

    git._git_host = None


# Test connect_to_git_hosting_platform()
@pytest.mark.parametrize("hosting_platform,context", [
    # 'hosting_platform' set to 'github'
    (git.GITHUB, patch("connections.github.connect")),

    # 'hosting_platform' set to 'gitlab'
    (git.GITLAB, patch("connections.gitlab.connect")),

    # 'hosting_platform' set to an invalid value - should exit
    (UNSUPPORTED_PLATFORM, pytest.raises(SystemExit)),

    # 'hosting_platform' not set - should exit
    (None, pytest.raises(SystemExit)),
])
@patch("tools.git.get_git_hosting_platform")
def test_connect_to_git_hosting_platform(mock_get_git_host, hosting_platform, context):
    mock_get_git_host.return_value = hosting_platform
    with context as context_obj:
        git.connect_to_git_hosting_platform()
        # For the valid 'hosting_platform' values, assert that connect() is called
        if isinstance(context_obj, MagicMock):
            context_obj.assert_called_once()


# Test get_app_name()
@pytest.mark.parametrize("cfg,expected", [
    # 'hosting_platform' set to 'github', test_app.cfg has 'app_name' set to 'test-app-github'
    (CFG, GITHUB_APP_NAME),
    (GITHUB_CFG, GITHUB_APP_NAME),

    # 'hosting_platform' set to 'gitlab', test_app.cfg has 'bot_name' set to 'test-bot-gl'
    (GITLAB_CFG, GITLAB_BOT_NAME),

    # 'hosting_platform' set to an invalid value
    (UNSUPPORTED_PLATFORM_CFG, None),

    # 'hosting_platform' not set
    (NO_HOSTING_PLATFORM_CFG, None),
])
@patch("tools.config.read_config")
@patch("tools.git.get_git_hosting_platform")
def test_get_app_name(mock_get_git_host, mock_read_config, cfg, expected):
    hosting_platform = cfg.get(config.SECTION_GIT, config.GIT_SETTING_HOSTING_PLATFORM, fallback=None)
    mock_get_git_host.return_value = hosting_platform
    mock_read_config.return_value = cfg

    # Test with provided cfg
    assert git.get_app_name(cfg) == expected
    mock_read_config.assert_not_called()

    # Test without provided cfg
    assert git.get_app_name() == expected
    mock_read_config.assert_called_once()


# Test BaseGitRepository class
def test_BaseGitRepository(tmp_path):
    # Creating a BaseGitRepository instance should fail
    with pytest.raises(NotImplementedError):
        git.BaseGitRepository(REPO_URL, tmp_path)

    # GenericGitRepository is a subclass of BaseGitRepository without any overrides
    # Test properties
    repo = GenericGitRepository(REPO_URL, tmp_path)
    assert repo._cloned is False
    assert repo._directory == tmp_path
    assert repo._repo_url == REPO_URL


# Test BaseGitRepository._get_pr_diff()
@pytest.mark.parametrize("fetch_return,diff_return,error_stage", [
    # Test fetch() fails
    (
        ("", "Fetch failed", 128, git.ERROR_GIT_FETCH),
        ("", "", 0, git.ERROR_NONE),
        git.ERROR_GIT_FETCH,
    ),

    # Test diff() fails
    (
        ("Fetch successful", "", 0, git.ERROR_NONE),
        ("", "Diff failed", 128, git.ERROR_GIT_DIFF),
        git.ERROR_GIT_DIFF,
    ),

    # Test _get_pr_diff() successful
    (
        ("Fetch successful", "", 0, git.ERROR_NONE),
        ("Diff successful", "", 0, git.ERROR_NONE),
        git.ERROR_NONE,
    ),
])
@patch("tools.git.BaseGitRepository.fetch")
@patch("tools.git.BaseGitRepository.diff")
def test_BaseGitRepository_get_pr_diff(mock_diff, mock_fetch, tmp_path, fetch_return, diff_return, error_stage):
    pr_number = 42
    src_ref = f"pull/{pr_number}/head"
    dst_ref = f"pr{pr_number}"
    diff_filename = f"{pr_number}.diff"

    if error_stage == git.ERROR_GIT_FETCH:
        expected_output = fetch_return
    elif error_stage == git.ERROR_GIT_DIFF:
        expected_output = diff_return
    else:
        expected_output = ("Obtaining PR diff succeeded", "", git.BaseGitRepository._EC_OK, git.ERROR_NONE)

    mock_fetch.return_value = fetch_return
    mock_diff.return_value = diff_return

    actual_output = GenericGitRepository(REPO_URL, tmp_path)._get_pr_diff(pr_number, diff_filename)

    mock_fetch.assert_called_once_with(src_ref, dst_ref)
    if error_stage == git.ERROR_GIT_FETCH:
        mock_diff.assert_not_called()
    else:
        mock_diff.assert_called_once_with("HEAD", dst_ref, diff_filename, merge_base=True)
    assert actual_output == expected_output


# Test BaseGitRepository._make_dirs()
@pytest.mark.parametrize("test_case,is_success_case", [
    # Failure cases
    ("exists-as-file", False),
    pytest.param(
        "no-write-permission", False,
        marks=pytest.mark.skipif(
            (sys.platform != "linux") or (os.geteuid() == 0),
            reason="Test case must be run on Linux as non-root user."
        )
    ),

    # Success cases
    ("dir-missing", True),
    ("parent-dir-missing", True),
    ("dir-exists", True),
    ("dir-given-as-string", True),
])
def test_BaseGitRepository_make_dirs(tmp_path, test_case, is_success_case):
    repo_path = tmp_path / "software-layer"

    # Set up test
    if test_case == "exists-as-file":
        repo_path.touch()
    elif test_case == "no-write-permission":
        # Create parent directory without write permission
        repo_path.mkdir(mode=0o500)
        repo_path = repo_path / "subdir"
    elif test_case == "dir-missing":
        # No extra setup required
        pass
    elif test_case == "parent-dir-missing":
        repo_path = repo_path / "subdir"
    elif test_case == "dir-exists":
        repo_path.mkdir(parents=True, exist_ok=True)
    elif test_case == "dir-given-as-string":
        repo_path = repo_path.as_posix()
    else:
        pytest.skip(reason=f"Unknown test case: {test_case}")

    stdout, stderr, exit_code, error_stage = GenericGitRepository(REPO_URL, repo_path)._make_dirs()

    if is_success_case:
        assert os.path.exists(repo_path) and os.path.isdir(repo_path)
        assert stdout == "Creating directories succeeded"
        assert stderr == ""
        assert exit_code == git.BaseGitRepository._EC_OK
        assert error_stage == git.ERROR_NONE
    else:
        if test_case == "exists-as-file":
            # _make_dirs should leave the existing file untouched
            assert repo_path.is_file()
        else:
            assert not repo_path.exists()
        assert stdout == ""
        assert stderr.startswith(f"Unable to set up directory '{repo_path}' for Git repository '{REPO_URL}': ")
        assert exit_code == git.BaseGitRepository._EC_NOT_OK
        assert error_stage == git.ERROR_MAKE_DIRS


# Test BaseGitRepository.clone()
@pytest.mark.parametrize("cloned,make_dirs_return,run_cmd_return,error_stage", [
    # Test _make_dirs() fails
    (
        False,
        ("", "Failed to create directory", git.BaseGitRepository._EC_NOT_OK, git.ERROR_MAKE_DIRS),
        ("", "", 0),
        git.ERROR_MAKE_DIRS,
    ),

    # Test cloning fails
    (
        False,
        ("Directory created successfully", "", git.BaseGitRepository._EC_OK, git.ERROR_NONE),
        ("", "Cloning failed", 128),
        git.ERROR_GIT_CLONE,
    ),

    # Test clone() successful
    (
        False,
        ("Directory created successfully", "", git.BaseGitRepository._EC_OK, git.ERROR_NONE),
        ("", "Cloning into dir...", 0),  # git logs to stderr by default
        git.ERROR_NONE,
    ),

    # Test clone() has succeeded previously (i.e., _cloned is true)
    (
        True,
        ("", "", git.BaseGitRepository._EC_OK, git.ERROR_NONE),
        ("", "", 0),
        git.ERROR_NONE,
    ),
])
@patch("tools.git.BaseGitRepository._make_dirs")
@patch("tools.git.run_cmd")
def test_BaseGitRepository_clone(mock_run_cmd, mock_make_dirs, tmp_path,
                                 cloned, make_dirs_return, run_cmd_return, error_stage):
    mock_make_dirs.return_value = make_dirs_return
    mock_run_cmd.return_value = run_cmd_return

    repo = GenericGitRepository(REPO_URL, tmp_path)
    repo._cloned = cloned
    actual_return = repo.clone()

    # Check calls and arguments
    if cloned:
        mock_make_dirs.assert_not_called()
    else:
        mock_make_dirs.assert_called_once_with()

    if cloned or error_stage == git.ERROR_MAKE_DIRS:
        mock_run_cmd.assert_not_called()
    else:
        cmd = f"git clone {REPO_URL} {tmp_path}"
        msg = f"Cloning repository '{REPO_URL}' to '{tmp_path}'"
        mock_run_cmd.assert_called_once_with(cmd, msg, tmp_path, raise_on_error=False)

    # Check output
    if cloned:
        expected_return = git.BaseGitRepository._ALREADY_CLONED
    elif error_stage == git.ERROR_MAKE_DIRS:
        expected_return = make_dirs_return
    else:
        # Verify that clone() uses correct logic for exit code -> error stage
        expected_error_stage = git.ERROR_NONE if (run_cmd_return[2] == 0) else git.ERROR_GIT_CLONE
        expected_return = *run_cmd_return, expected_error_stage

    # _cloned should only be true if it was already true or if the cloning succeeded
    should_be_cloned = error_stage == git.ERROR_NONE

    assert actual_return == expected_return
    assert repo._cloned is should_be_cloned


# Test BaseGitRepository.checkout()
@pytest.mark.parametrize("cloned,run_cmd_return", [
    # Test pre-clone checkout
    (False, ("", "", 0)),

    # Test checkout fails
    (True, ("", "Checkout failed", 128)),

    # Test checkout succeeds
    (True, ("", "Switched to branch", 0)),
])
@patch("tools.git.run_cmd")
def test_BaseGitRepository_checkout(mock_run_cmd, tmp_path, cloned, run_cmd_return):
    branch_name = "main"

    mock_run_cmd.return_value = run_cmd_return

    repo = GenericGitRepository(REPO_URL, tmp_path)
    repo._cloned = cloned
    actual_return = repo.checkout(branch_name)

    # Check calls and arguments
    if not cloned:
        mock_run_cmd.assert_not_called()
    else:
        cmd = f"git checkout {branch_name}"
        msg = f"Checkout branch '{branch_name}'"
        mock_run_cmd.assert_called_once_with(cmd, msg, tmp_path, raise_on_error=False)

    # Check output
    if not cloned:
        expected_return = *git.BaseGitRepository._NOT_CLONED_YET, git.ERROR_GIT_CHECKOUT
    else:
        # Verify that checkout() uses correct logic for exit code -> error stage
        expected_error_stage = git.ERROR_NONE if (run_cmd_return[2] == 0) else git.ERROR_GIT_CHECKOUT
        expected_return = *run_cmd_return, expected_error_stage

    assert actual_return == expected_return


# Test BaseGitRepository.fetch()
@pytest.mark.parametrize("cloned,run_cmd_return", [
    # Test pre-clone fetch
    (False, ("", "", 0)),

    # Test fetch fails
    (True, ("", "Fetch failed", 128)),

    # Test fetch succeeds
    (True, ("", "Fetched new ref", 0)),
])
@patch("tools.git.run_cmd")
def test_BaseGitRepository_fetch(mock_run_cmd, tmp_path, cloned, run_cmd_return):
    pr_number = 42
    src_ref = f"pull/{pr_number}/head"
    dst_ref = f"pr{pr_number}"

    mock_run_cmd.return_value = run_cmd_return

    repo = GenericGitRepository(REPO_URL, tmp_path)
    repo._cloned = cloned
    actual_return = repo.fetch(src_ref, dst_ref)

    # Check calls and arguments
    if not cloned:
        mock_run_cmd.assert_not_called()
    else:
        cmd = f"git fetch origin {src_ref}:{dst_ref}"
        msg = f"Fetching ref '{src_ref}' as '{dst_ref}'"
        mock_run_cmd.assert_called_once_with(cmd, msg, tmp_path, raise_on_error=False)

    # Check output
    if not cloned:
        expected_return = *git.BaseGitRepository._NOT_CLONED_YET, git.ERROR_GIT_FETCH
    else:
        # Verify that fetch() uses correct logic for exit code -> error stage
        expected_error_stage = git.ERROR_NONE if (run_cmd_return[2] == 0) else git.ERROR_GIT_FETCH
        expected_return = *run_cmd_return, expected_error_stage

    assert actual_return == expected_return


# Test BaseGitRepository.diff()
@pytest.mark.parametrize("cloned,merge_base,run_cmd_return", [
    # Test pre-clone diff
    (False, False, ("", "", 0)),

    # Test diff fails
    (True, False, ("", "Unknown revision", 128)),

    # Test diff succeeds
    (True, False, ("", "", 0)),

    # Test diff w/ merge-base succeeds
    (True, True, ("", "", 0)),
])
@patch("tools.git.run_cmd")
def test_BaseGitRepository_diff(mock_run_cmd, tmp_path, cloned, merge_base, run_cmd_return):
    pr_number = 42
    commit_a = "HEAD"
    commit_b = f"pr{pr_number}"
    diff_filename = f"{pr_number}.diff"

    mock_run_cmd.return_value = run_cmd_return

    repo = GenericGitRepository(REPO_URL, tmp_path)
    repo._cloned = cloned
    actual_return = repo.diff(commit_a, commit_b, diff_filename, merge_base=merge_base)

    # Check calls and arguments
    if not cloned:
        mock_run_cmd.assert_not_called()
    else:
        if merge_base:
            cmd = f"git diff --merge-base {commit_a} {commit_b} > {diff_filename}"
            msg = f"Storing diff of '{commit_b}' compared to its merge base with '{commit_a}' in '{diff_filename}'"
        else:
            cmd = f"git diff {commit_a} {commit_b} > {diff_filename}"
            msg = f"Storing diff of '{commit_b}' compared to '{commit_a}' in '{diff_filename}'"
        mock_run_cmd.assert_called_once_with(cmd, msg, tmp_path, raise_on_error=False)

    # Check output
    if not cloned:
        expected_return = *git.BaseGitRepository._NOT_CLONED_YET, git.ERROR_GIT_DIFF
    else:
        # Verify that diff() uses correct logic for exit code -> error stage
        expected_error_stage = git.ERROR_NONE if (run_cmd_return[2] == 0) else git.ERROR_GIT_DIFF
        expected_return = *run_cmd_return, expected_error_stage

    assert actual_return == expected_return


# Test BaseGitRepository.apply()
@pytest.mark.parametrize("cloned,run_cmd_return", [
    # Test pre-clone apply
    (False, ("", "", 0)),

    # Test apply fails
    (True, ("", "Apply failed", 128)),

    # Test apply succeeds
    (True, ("", "", 0)),
])
@patch("tools.git.run_cmd")
def test_BaseGitRepository_apply(mock_run_cmd, tmp_path, cloned, run_cmd_return):
    patch_file = "42.diff"

    mock_run_cmd.return_value = run_cmd_return

    repo = GenericGitRepository(REPO_URL, tmp_path)
    repo._cloned = cloned
    actual_return = repo.apply(patch_file)

    # Check calls and args
    if not cloned:
        mock_run_cmd.assert_not_called()
    else:
        cmd = f"git apply {patch_file}"
        msg = f"Applying patch '{patch_file}'"
        mock_run_cmd.assert_called_once_with(cmd, msg, tmp_path, raise_on_error=False)

    # Check output
    if not cloned:
        expected_return = *git.BaseGitRepository._NOT_CLONED_YET, git.ERROR_GIT_APPLY
    else:
        # Verify that apply() uses correct logic for exit code -> error stage
        expected_error_stage = git.ERROR_NONE if (run_cmd_return[2] == 0) else git.ERROR_GIT_APPLY
        expected_return = *run_cmd_return, expected_error_stage

    assert actual_return == expected_return


# Test BaseGitRepository.download_pr()
@pytest.mark.parametrize("clone_return,checkout_return,get_pr_diff_return,apply_return,error_stage", [
    # Test clone() fails
    (
        ("", "Cloning failed", 128, git.ERROR_GIT_CLONE),
        ("", "", 0, git.ERROR_NONE),
        ("", "", 0, git.ERROR_NONE),
        ("", "", 0, git.ERROR_NONE),
        git.ERROR_GIT_CLONE,
    ),

    # Test checkout() fails
    (
        ("", "Cloning into dir...", 0, git.ERROR_NONE),
        ("", "Checkout failed", 128, git.ERROR_GIT_CHECKOUT),
        ("", "", 0, git.ERROR_NONE),
        ("", "", 0, git.ERROR_NONE),
        git.ERROR_GIT_CHECKOUT,
    ),

    # Test _get_pr_diff() fetch stage fails
    (
        ("", "Cloning into dir...", 0, git.ERROR_NONE),
        ("", "Switched to branch", 0, git.ERROR_NONE),
        ("", "Fetch failed", 128, git.ERROR_GIT_FETCH),
        ("", "", 0, git.ERROR_NONE),
        git.ERROR_GIT_FETCH,
    ),

    # Test _get_pr_diff() diff stage fails
    (
        ("", "Cloning into dir...", 0, git.ERROR_NONE),
        ("", "Switched to branch", 0, git.ERROR_NONE),
        ("", "Diff failed", 128, git.ERROR_GIT_DIFF),
        ("", "", 0, git.ERROR_NONE),
        git.ERROR_GIT_DIFF,
    ),

    # Test apply() fails
    (
        ("", "Cloning into dir...", 0, git.ERROR_NONE),
        ("", "Switched to branch", 0, git.ERROR_NONE),
        ("Obtaining PR diff succeeded", "", git.BaseGitRepository._EC_OK, git.ERROR_NONE),
        ("", "Apply failed", 128, git.ERROR_GIT_APPLY),
        git.ERROR_GIT_APPLY,
    ),

    # Test download_pr() succeeds
    (
        ("", "Cloning into dir...", 0, git.ERROR_NONE),
        ("", "Switched to branch", 0, git.ERROR_NONE),
        ("Obtaining PR diff succeeded", "", git.BaseGitRepository._EC_OK, git.ERROR_NONE),
        ("", "", 0, git.ERROR_NONE),
        git.ERROR_NONE,
    ),
])
@patch("tools.git.BaseGitRepository.clone")
@patch("tools.git.BaseGitRepository.checkout")
@patch("tools.git.BaseGitRepository._get_pr_diff")
@patch("tools.git.BaseGitRepository.apply")
def test_BaseGitRepository_download_pr(mock_apply, mock_get_pr_diff, mock_checkout, mock_clone, tmp_path,
                                       clone_return, checkout_return, get_pr_diff_return, apply_return, error_stage):
    pr_number = 42
    diff_filename = f"{pr_number}.diff"
    base_branch = "main"

    mock_clone.return_value = clone_return
    mock_checkout.return_value = checkout_return
    mock_get_pr_diff.return_value = get_pr_diff_return
    mock_apply.return_value = apply_return

    actual_output = GenericGitRepository(REPO_URL, tmp_path).download_pr(pr_number, base_branch)

    # Check calls and args
    mock_clone.assert_called_once_with()

    if error_stage == git.ERROR_GIT_CLONE:
        mock_checkout.assert_not_called()
    else:
        mock_checkout.assert_called_once_with(base_branch)

    if error_stage in (git.ERROR_GIT_CLONE, git.ERROR_GIT_CHECKOUT):
        mock_get_pr_diff.assert_not_called()
    else:
        mock_get_pr_diff.assert_called_once_with(pr_number, diff_filename)

    if error_stage in (git.ERROR_GIT_CLONE, git.ERROR_GIT_CHECKOUT, git.ERROR_GIT_FETCH, git.ERROR_GIT_DIFF):
        mock_apply.assert_not_called()
    else:
        mock_apply.assert_called_once_with(diff_filename)

    # Check output
    if error_stage == git.ERROR_GIT_CLONE:
        expected_output = clone_return
    elif error_stage == git.ERROR_GIT_CHECKOUT:
        expected_output = checkout_return
    elif error_stage in (git.ERROR_GIT_FETCH, git.ERROR_GIT_DIFF):
        # Verify that download_pr() passes the error stage (fetch/diff)
        # directly from _get_pr_diff() instead of returning ERROR_PR_DIFF
        expected_output = get_pr_diff_return
    elif error_stage == git.ERROR_GIT_APPLY:
        expected_output = apply_return
    else:
        expected_output = ("Downloading PR succeeded", "", git.BaseGitRepository._EC_OK, git.ERROR_NONE)

    assert actual_output == expected_output


# Verify GitRepository type definition
def test_GitRepository():
    expected_git_repository_types = {git.GitHubGitRepository, git.GitLabGitRepository}
    # Need to use __args__ for Python 3.9 compatibility
    actual_git_repository_types = set(git.GitRepository.__args__)
    assert actual_git_repository_types == expected_git_repository_types


# List of constants and methods defined in BaseGitRepository - used in subclass tests
BASE_GIT_REPOSITORY_ATTRIBUTES = [
    # Constants
    "_EC_OK", "_EC_NOT_OK",
    "_MSG_REPO_ALREADY_CLONED", "_ERR_MSG_REPO_NOT_CLONED_YET",
    "_ALREADY_CLONED", "_NOT_CLONED_YET",

    # Methods
    "__init__", "_get_pr_diff", "_make_dirs",
    "clone", "checkout", "fetch", "diff", "apply",
    "download_pr",
]


# Test GitRepository classes
@pytest.mark.parametrize("subclass,overrides", [
    # GitHubGitRepository should not override anything
    (git.GitHubGitRepository, []),

    # GitLabGitRepository should only override _get_pr_diff()
    (git.GitLabGitRepository, ["_get_pr_diff"]),
])
def test_GitRepository_subclasses(tmp_path, subclass, overrides):
    # The subclass should be a proper subclass of BaseGitRepository
    assert issubclass(subclass, git.BaseGitRepository)
    assert not issubclass(git.BaseGitRepository, subclass)

    subclass_repo = subclass(REPO_URL, tmp_path)
    base_repo = GenericGitRepository(REPO_URL, tmp_path)

    # Check overrides in subclass
    for attr in BASE_GIT_REPOSITORY_ATTRIBUTES:
        subclass_attr = getattr(subclass_repo, attr)
        base_attr = getattr(base_repo, attr)
        should_be_overridden = attr in overrides

        if callable(base_attr):
            is_overridden = subclass_attr.__func__ is not base_attr.__func__
        else:
            is_overridden = subclass_attr is not base_attr

        assert is_overridden is should_be_overridden


# Test GitLabGitRepository._get_pr_diff()
@pytest.mark.parametrize("fetch_return,diff_return,error_stage", [
    # Test fetch() fails
    (
        ("", "Fetch failed", 128, git.ERROR_GIT_FETCH),
        ("", "", 0, git.ERROR_NONE),
        git.ERROR_GIT_FETCH,
    ),

    # Test diff() fails
    (
        ("Fetch successful", "", 0, git.ERROR_NONE),
        ("", "Diff failed", 128, git.ERROR_GIT_DIFF),
        git.ERROR_GIT_DIFF,
    ),

    # Test _get_pr_diff() successful
    (
        ("Fetch successful", "", 0, git.ERROR_NONE),
        ("Diff successful", "", 0, git.ERROR_NONE),
        git.ERROR_NONE,
    ),
])
@patch("tools.git.BaseGitRepository.fetch")
@patch("tools.git.BaseGitRepository.diff")
def test_GitLabGitRepository_get_pr_diff(mock_diff, mock_fetch, tmp_path, fetch_return, diff_return, error_stage):
    pr_number = 42
    src_ref = f"merge-requests/{pr_number}/head"
    dst_ref = f"pr{pr_number}"
    diff_filename = f"{pr_number}.diff"

    if error_stage == git.ERROR_GIT_FETCH:
        expected_output = fetch_return
    elif error_stage == git.ERROR_GIT_DIFF:
        expected_output = diff_return
    else:
        expected_output = ("Obtaining PR diff succeeded", "", git.BaseGitRepository._EC_OK, git.ERROR_NONE)

    mock_fetch.return_value = fetch_return
    mock_diff.return_value = diff_return

    actual_output = git.GitLabGitRepository(REPO_URL, tmp_path)._get_pr_diff(pr_number, diff_filename)

    mock_fetch.assert_called_once_with(src_ref, dst_ref)
    if error_stage == git.ERROR_GIT_FETCH:
        mock_diff.assert_not_called()
    else:
        mock_diff.assert_called_once_with("HEAD", dst_ref, diff_filename, merge_base=True)
    assert actual_output == expected_output


# Test create_git_repository_instance()
@pytest.mark.parametrize("git_host,expected_type", [
    (git.GITHUB, git.GitHubGitRepository),
    (git.GITLAB, git.GitLabGitRepository),
    ("unknown", type(None)),
])
def test_create_git_repository_instance(tmp_path, git_host, expected_type):
    repo = git.create_git_repository_instance(REPO_URL, tmp_path, git_host)
    assert type(repo) is expected_type
