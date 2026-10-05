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
@patch("tools.git.BaseGitRepository.fetch")
@patch("tools.git.BaseGitRepository.diff")
def test_BaseGitRepository_get_pr_diff(mock_diff, mock_fetch, tmp_path):
    repo = GenericGitRepository(REPO_URL, tmp_path)
    pr_number = 1234
    diff_filename = f"{pr_number}.diff"
    src_ref = f"pull/{pr_number}/head"
    dst_ref = f"pr{pr_number}"
    # git logs to stderr by default
    successful_fetch_message = "Fetch successful"
    successful_fetch_return = ("", successful_fetch_message, 0, git.ERROR_NONE)
    successful_diff_return = ("", "", 0, git.ERROR_NONE)
    # Failed git fetch/diff returns exit code 128
    failed_fetch_message = "Fetch failed"
    failed_fetch_return = ("", failed_fetch_message, 128, git.ERROR_GIT_FETCH)
    failed_diff_message = "Diff failed"
    failed_diff_return = ("", failed_diff_message, 128, git.ERROR_GIT_DIFF)

    # Test fetch stage fails
    mock_fetch.return_value = failed_fetch_return
    mock_diff.return_value = successful_diff_return
    stdout, stderr, exit_code, error_stage = repo._get_pr_diff(pr_number, diff_filename)
    mock_fetch.assert_called_once_with(src_ref, dst_ref)
    # _get_pr_diff should return early if any stage fails
    mock_diff.assert_not_called()
    assert stdout == ""
    assert failed_fetch_message in stderr
    # _get_pr_diff should pass the exit code if any stage fails
    assert exit_code == 128
    assert error_stage == git.ERROR_GIT_FETCH

    mock_fetch.reset_mock()
    mock_diff.reset_mock()

    # Test diff stage fails
    mock_fetch.return_value = successful_fetch_return
    mock_diff.return_value = failed_diff_return
    stdout, stderr, exit_code, error_stage = repo._get_pr_diff(pr_number, diff_filename)
    mock_fetch.assert_called_once_with(src_ref, dst_ref)
    mock_diff.assert_called_once_with("HEAD", dst_ref, diff_filename, merge_base=True)
    assert stdout == ""
    assert failed_diff_message in stderr
    assert exit_code == 128
    assert error_stage == git.ERROR_GIT_DIFF

    mock_fetch.reset_mock()
    mock_diff.reset_mock()

    # Test _get_pr_diff successful
    mock_fetch.return_value = successful_fetch_return
    mock_diff.return_value = successful_diff_return
    stdout, stderr, exit_code, error_stage = repo._get_pr_diff(pr_number, diff_filename)
    mock_fetch.assert_called_once_with(src_ref, dst_ref)
    mock_diff.assert_called_once_with("HEAD", dst_ref, diff_filename, merge_base=True)
    assert len(stdout) > 0
    assert stderr == ""
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE


# Test BaseGitRepository._make_dirs()
def test_BaseGitRepository_make_dirs(tmp_path):
    repo_path = tmp_path / "software-layer"

    # Test 'directory' exists as a file - should return non-zero exit code and error stage ERROR_MAKEDIRS
    repo_path.touch()
    stdout, stderr, exit_code, error_stage = GenericGitRepository(REPO_URL, repo_path)._make_dirs()
    assert repo_path.is_file()
    assert stdout == ""
    assert len(stderr) > 0
    assert exit_code != 0
    assert error_stage == git.ERROR_MAKE_DIRS
    repo_path.unlink()

    # Test missing write permission - should raise non-zero exit code and error stage ERROR_MAKEDIRS
    # Skip the test if not on Linux or if running as root, otherwise it will fail
    if sys.platform != "linux":
        print("Not running on Linux - skipping BaseGitRepository._make_dirs missing permission test")
    elif os.geteuid() == 0:
        print("Running as root - skipping BaseGitRepository._make_dirs missing permission test")
    else:
        # Create parent directory without write permission
        repo_path.mkdir(mode=0o500, parents=True)
        unable_to_create_path = repo_path / "unable-to-create"
        stdout, stderr, exit_code, error_stage = GenericGitRepository(REPO_URL, unable_to_create_path)._make_dirs()
        assert not unable_to_create_path.exists()
        assert stdout == ""
        assert len(stderr) > 0
        assert exit_code != 0
        assert error_stage == git.ERROR_MAKE_DIRS
        repo_path.rmdir()

    # Test lowest path level missing
    assert not repo_path.exists()
    stdout, stderr, exit_code, error_stage = GenericGitRepository(REPO_URL, repo_path)._make_dirs()
    assert repo_path.exists() and repo_path.is_dir()
    assert len(stdout) > 0
    assert stderr == ""
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE
    repo_path.rmdir()

    # Test two lowest path levels missing
    subdir = repo_path / "subdir"
    assert not repo_path.exists()
    stdout, stderr, exit_code, error_stage = GenericGitRepository(REPO_URL, subdir)._make_dirs()
    assert repo_path.exists() and repo_path.is_dir()
    assert subdir.exists() and subdir.is_dir()
    assert len(stdout) > 0
    assert stderr == ""
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE
    subdir.rmdir()

    # Test 'directory' already exists as a directory
    repo_path.mkdir(parents=True, exist_ok=True)
    assert repo_path.exists() and repo_path.is_dir()
    stdout, stderr, exit_code, error_stage = GenericGitRepository(REPO_URL, repo_path)._make_dirs()
    assert repo_path.exists() and repo_path.is_dir()
    assert len(stdout) > 0
    assert stderr == ""
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE
    repo_path.rmdir()

    # Test 'directory' being given as a string
    stdout, stderr, exit_code, error_stage = GenericGitRepository(REPO_URL, repo_path.as_posix())._make_dirs()
    assert repo_path.exists() and repo_path.is_dir()
    assert len(stdout) > 0
    assert stderr == ""
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE


# Test BaseGitRepository.clone()
@patch("tools.git.run_cmd")
@patch("tools.git.BaseGitRepository._make_dirs")
def test_BaseGitRepository_clone(mock_make_dirs, mock_run_cmd, tmp_path):
    successful_make_dirs_message = "Creating directories succeeded"
    successful_make_dirs_return = (successful_make_dirs_message, "", 0, git.ERROR_NONE)
    # git logs to stderr by default
    successful_clone_message = "Cloning succeeded"
    successful_clone_return = ("", successful_clone_message, 0)

    failed_make_dirs_message = "Creating directories failed"
    failed_make_dirs_return = ("", failed_make_dirs_message, 1, git.ERROR_MAKE_DIRS)
    # Failed git clone returns exit code 128
    failed_clone_message = "Cloning failed"
    failed_clone_return = ("", failed_clone_message, 128)

    # Test _make_dirs fails
    mock_make_dirs.return_value = failed_make_dirs_return
    mock_run_cmd.return_value = successful_clone_return
    repo = GenericGitRepository(REPO_URL, tmp_path)
    stdout, stderr, exit_code, error_stage = repo.clone()
    mock_make_dirs.assert_called_once()
    mock_run_cmd.assert_not_called()
    assert stdout == ""
    assert failed_make_dirs_message in stderr
    assert exit_code == 1
    assert error_stage == git.ERROR_MAKE_DIRS
    assert repo._cloned is False

    mock_make_dirs.reset_mock()
    mock_run_cmd.reset_mock()

    # Test clone fails (e.g. directory is not empty)
    mock_make_dirs.return_value = successful_make_dirs_return
    mock_run_cmd.return_value = failed_clone_return
    repo = GenericGitRepository(REPO_URL, tmp_path)
    stdout, stderr, exit_code, error_stage = repo.clone()
    mock_make_dirs.assert_called_once()
    mock_run_cmd.assert_called_once()
    assert stdout == ""
    assert failed_clone_message in stderr
    assert exit_code == 128
    assert error_stage == git.ERROR_GIT_CLONE
    assert repo._cloned is False

    mock_make_dirs.reset_mock()
    mock_run_cmd.reset_mock()

    # Test clone succeeds
    mock_make_dirs.return_value = successful_make_dirs_return
    mock_run_cmd.return_value = successful_clone_return
    repo = GenericGitRepository(REPO_URL, tmp_path)
    stdout, stderr, exit_code, error_stage = repo.clone()
    mock_make_dirs.assert_called_once()
    mock_run_cmd.assert_called_once()
    assert stdout == ""
    assert successful_clone_message in stderr
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE
    assert repo._cloned is True

    # Check run_cmd arguments
    (cmd, log_msg, working_dir, *_) = mock_run_cmd.call_args.args
    raise_on_error = mock_run_cmd.call_args.kwargs.get("raise_on_error")
    assert cmd == f"git clone {REPO_URL} {tmp_path}"
    assert len(log_msg) > 0
    assert working_dir == tmp_path
    assert raise_on_error is False

    mock_make_dirs.reset_mock()
    mock_run_cmd.reset_mock()

    # Test repo already cloned (i.e. clone() has succeeded previously)
    stdout, stderr, exit_code, error_stage = repo.clone()
    mock_make_dirs.assert_not_called()
    mock_run_cmd.assert_not_called()
    assert len(stdout) > 0
    assert stderr == ""
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE
    assert repo._cloned is True


# Test BaseGitRepository.checkout()
@patch("tools.git.run_cmd")
def test_BaseGitRepository_checkout(mock_run_cmd, tmp_path):
    branch = "main"
    # git logs to stderr by default
    successful_checkout_message = "Checkout succeeded"
    successful_checkout_return = ("", successful_checkout_message, 0)
    # 'fatal' git checkout error returns exit code 128
    failed_checkout_message = "Checkout failed"
    failed_checkout_return = ("", failed_checkout_message, 128)

    # Test pre-clone checkout - should return early with non-zero exit code and error stage ERROR_GIT_CHECKOUT
    repo = GenericGitRepository(REPO_URL, tmp_path)
    assert repo._cloned is False
    stdout, stderr, exit_code, error_stage = repo.checkout(branch)
    mock_run_cmd.assert_not_called()
    assert stdout == ""
    assert len(stderr) > 0
    assert exit_code != 0
    assert error_stage == git.ERROR_GIT_CHECKOUT

    mock_run_cmd.reset_mock()

    # Manually set '_cloned' property
    repo._cloned = True

    # Test checkout fails (e.g. branch does not exist)
    mock_run_cmd.return_value = failed_checkout_return
    stdout, stderr, exit_code, error_stage = repo.checkout(branch)
    mock_run_cmd.assert_called_once()
    assert stdout == ""
    assert failed_checkout_message in stderr
    assert exit_code == 128
    assert error_stage == git.ERROR_GIT_CHECKOUT

    mock_run_cmd.reset_mock()

    # Test successful checkout
    mock_run_cmd.return_value = successful_checkout_return
    stdout, stderr, exit_code, error_stage = repo.checkout(branch)
    mock_run_cmd.assert_called_once()
    assert stdout == ""
    assert successful_checkout_message in stderr
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE

    # Check run_cmd arguments
    (cmd, log_msg, working_dir, *_) = mock_run_cmd.call_args.args
    raise_on_error = mock_run_cmd.call_args.kwargs.get("raise_on_error")
    assert cmd == f"git checkout {branch}"
    assert len(log_msg) > 0
    assert working_dir == tmp_path
    assert raise_on_error is False


# Test BaseGitRepository.fetch()
@patch("tools.git.run_cmd")
def test_BaseGitRepository_fetch(mock_run_cmd, tmp_path):
    pr_number = 42
    src_ref = f"pull/{pr_number}/head"
    dst_ref = f"pr{pr_number}"
    # git logs to stderr by default
    successful_fetch_message = "Fetch succeeded"
    successful_fetch_return = ("", successful_fetch_message, 0)
    # 'fatal' git fetch error returns exit code 128
    failed_fetch_message = "Fetch failed"
    failed_fetch_return = ("", failed_fetch_message, 128)

    # Test pre-clone fetch - should return early with non-zero exit code and error stage ERROR_GIT_FETCH
    repo = GenericGitRepository(REPO_URL, tmp_path)
    assert repo._cloned is False
    stdout, stderr, exit_code, error_stage = repo.fetch(src_ref, dst_ref)
    mock_run_cmd.assert_not_called()
    assert stdout == ""
    assert len(stderr) > 0
    assert exit_code != 0
    assert error_stage == git.ERROR_GIT_FETCH

    mock_run_cmd.reset_mock()

    # Manually set '_cloned' property
    repo._cloned = True

    # Test fetch fails (e.g. 'src_ref' does not exist)
    mock_run_cmd.return_value = failed_fetch_return
    stdout, stderr, exit_code, error_stage = repo.fetch(src_ref, dst_ref)
    mock_run_cmd.assert_called_once()
    assert stdout == ""
    assert failed_fetch_message in stderr
    assert exit_code == 128
    assert error_stage == git.ERROR_GIT_FETCH

    mock_run_cmd.reset_mock()

    # Test successful fetch
    mock_run_cmd.return_value = successful_fetch_return
    stdout, stderr, exit_code, error_stage = repo.fetch(src_ref, dst_ref)
    mock_run_cmd.assert_called_once()
    assert stdout == ""
    assert successful_fetch_message in stderr
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE

    # Check run_cmd arguments
    (cmd, log_msg, working_dir, *_) = mock_run_cmd.call_args.args
    raise_on_error = mock_run_cmd.call_args.kwargs.get("raise_on_error")
    assert cmd == f"git fetch origin {src_ref}:{dst_ref}"
    assert len(log_msg) > 0
    assert working_dir == tmp_path
    assert raise_on_error is False


# Test BaseGitRepository.diff()
@patch("tools.git.run_cmd")
def test_BaseGitRepository_diff(mock_run_cmd, tmp_path):
    pr_number = 42
    commit_a = "HEAD"
    commit_b = f"pr{pr_number}"
    diff_filename = f"{pr_number}.diff"
    # On success, git diff stdout should be saved to 'diff_filename' while nothing is logged to stderr
    successful_diff_return = ("", "", 0)
    # 'fatal' git diff error returns exit code 128
    failed_diff_message = "Diff failed"
    failed_diff_return = ("", failed_diff_message, 128)

    # Test pre-clone diff - should return early with non-zero exit code and error stage ERROR_GIT_DIFF
    repo = GenericGitRepository(REPO_URL, tmp_path)
    assert repo._cloned is False
    stdout, stderr, exit_code, error_stage = repo.diff(commit_a, commit_b, diff_filename)
    mock_run_cmd.assert_not_called()
    assert stdout == ""
    assert len(stderr) > 0
    assert exit_code != 0
    assert error_stage == git.ERROR_GIT_DIFF

    mock_run_cmd.reset_mock()

    # Manually set '_cloned' property
    repo._cloned = True

    # Test diff fails (e.g. commit does not exist)
    mock_run_cmd.return_value = failed_diff_return
    stdout, stderr, exit_code, error_stage = repo.diff(commit_a, commit_b, diff_filename)
    mock_run_cmd.assert_called_once()
    assert stdout == ""
    assert failed_diff_message in stderr
    assert exit_code == 128
    assert error_stage == git.ERROR_GIT_DIFF

    mock_run_cmd.reset_mock()

    # Test successful diff
    mock_run_cmd.return_value = successful_diff_return
    stdout, stderr, exit_code, error_stage = repo.diff(commit_a, commit_b, diff_filename)
    mock_run_cmd.assert_called_once()
    assert stdout == ""
    assert stderr == ""
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE

    # Check run_cmd arguments
    (cmd, log_msg, working_dir, *_) = mock_run_cmd.call_args.args
    raise_on_error = mock_run_cmd.call_args.kwargs.get("raise_on_error")
    # There should be no '--merge-base' by default
    assert cmd == f"git diff {commit_a} {commit_b} > {diff_filename}"
    assert len(log_msg) > 0
    assert working_dir == tmp_path
    assert raise_on_error is False

    mock_run_cmd.reset_mock()

    # Test successful diff with 'merge_base=True'
    mock_run_cmd.return_value = successful_diff_return
    stdout, stderr, exit_code, error_stage = repo.diff(commit_a, commit_b, diff_filename, merge_base=True)
    mock_run_cmd.assert_called_once()
    assert stdout == ""
    assert stderr == ""
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE

    # Check run_cmd arguments
    (cmd, log_msg, working_dir, *_) = mock_run_cmd.call_args.args
    raise_on_error = mock_run_cmd.call_args.kwargs.get("raise_on_error")
    assert cmd == f"git diff --merge-base {commit_a} {commit_b} > {diff_filename}"
    assert len(log_msg) > 0
    assert working_dir == tmp_path
    assert raise_on_error is False


# Test BaseGitRepository.apply()
@patch("tools.git.run_cmd")
def test_BaseGitRepository_apply(mock_run_cmd, tmp_path):
    patch = "42.diff"
    # No output on successful git apply
    successful_apply_return = ("", "", 0)
    # git apply error with exit code 128
    failed_apply_message = "Apply failed"
    failed_apply_return = ("", failed_apply_message, 128)

    # Test pre-clone apply - should return early with non-zero exit code and error stage ERROR_GIT_APPLY
    repo = GenericGitRepository(REPO_URL, tmp_path)
    assert repo._cloned is False
    stdout, stderr, exit_code, error_stage = repo.apply(patch)
    mock_run_cmd.assert_not_called()
    assert stdout == ""
    assert len(stderr) > 0
    assert exit_code != 0
    assert error_stage == git.ERROR_GIT_APPLY

    mock_run_cmd.reset_mock()

    # Manually set '_cloned' property
    repo._cloned = True

    # Test apply fails (e.g. 'patch' does not exist)
    mock_run_cmd.return_value = failed_apply_return
    stdout, stderr, exit_code, error_stage = repo.apply(patch)
    mock_run_cmd.assert_called_once()
    assert stdout == ""
    assert failed_apply_message in stderr
    assert exit_code == 128
    assert error_stage == git.ERROR_GIT_APPLY

    mock_run_cmd.reset_mock()

    # Test successful apply
    mock_run_cmd.return_value = successful_apply_return
    stdout, stderr, exit_code, error_stage = repo.apply(patch)
    mock_run_cmd.assert_called_once()
    assert stdout == ""
    assert stderr == ""
    assert exit_code == 0
    assert error_stage == git.ERROR_NONE

    # Check run_cmd arguments
    (cmd, log_msg, working_dir, *_) = mock_run_cmd.call_args.args
    raise_on_error = mock_run_cmd.call_args.kwargs.get("raise_on_error")
    assert cmd == f"git apply {patch}"
    assert len(log_msg) > 0
    assert working_dir == tmp_path
    assert raise_on_error is False


# Test BaseGitRepository.download_pr()
@patch("tools.git.BaseGitRepository.clone")
@patch("tools.git.BaseGitRepository.checkout")
@patch("tools.git.BaseGitRepository._get_pr_diff")
@patch("tools.git.BaseGitRepository.apply")
def test_BaseGitRepository_download_pr(mock_apply, mock_get_pr_diff, mock_checkout, mock_clone, tmp_path):
    pr_number = 42
    diff_filename = f"{pr_number}.diff"
    base_branch = "main"

    failed_clone_message = "Cloning failed"
    failed_clone_return = ("", failed_clone_message, 128, git.ERROR_GIT_CLONE)
    failed_checkout_message = "Checkout failed"
    failed_checkout_return = ("", failed_checkout_message, 128, git.ERROR_GIT_CHECKOUT)
    failed_get_pr_diff_message = "Fetch failed"
    failed_get_pr_diff_return = ("", failed_get_pr_diff_message, 128, git.ERROR_GIT_FETCH)
    failed_apply_message = "Apply failed"
    failed_apply_return = ("", failed_apply_message, 128, git.ERROR_GIT_APPLY)

    successful_return = ("", "", 0, git.ERROR_NONE)

    # Test clone stage fails
    repo = GenericGitRepository(REPO_URL, tmp_path)
    mock_clone.return_value = failed_clone_return
    mock_checkout.return_value = successful_return
    mock_get_pr_diff.return_value = successful_return
    mock_apply.return_value = successful_return

    stdout, stderr, exit_code, error_stage = repo.download_pr(pr_number, base_branch)

    mock_clone.assert_called_once_with()
    mock_checkout.assert_not_called()
    mock_get_pr_diff.assert_not_called()
    mock_apply.assert_not_called()

    assert stdout == ""
    assert failed_clone_message in stderr
    assert exit_code == 128
    assert error_stage == git.ERROR_GIT_CLONE

    mock_clone.reset_mock()
    mock_checkout.reset_mock()
    mock_get_pr_diff.reset_mock()
    mock_apply.reset_mock()

    # Manually set '_cloned' property
    repo._cloned = True

    # Test checkout stage fails
    mock_clone.return_value = successful_return
    mock_checkout.return_value = failed_checkout_return
    mock_get_pr_diff.return_value = successful_return
    mock_apply.return_value = successful_return

    stdout, stderr, exit_code, error_stage = repo.download_pr(pr_number, base_branch)

    # download_pr() should still call clone() if '_cloned' is true
    mock_clone.assert_called_once_with()
    mock_checkout.assert_called_once_with(base_branch)
    mock_get_pr_diff.assert_not_called()
    mock_apply.assert_not_called()

    assert stdout == ""
    assert failed_checkout_message in stderr
    assert exit_code == 128
    assert error_stage == git.ERROR_GIT_CHECKOUT

    mock_clone.reset_mock()
    mock_checkout.reset_mock()
    mock_get_pr_diff.reset_mock()
    mock_apply.reset_mock()

    # Test _get_pr_diff stage fails
    mock_clone.return_value = successful_return
    mock_checkout.return_value = successful_return
    mock_get_pr_diff.return_value = failed_get_pr_diff_return
    mock_apply.return_value = successful_return

    stdout, stderr, exit_code, error_stage = repo.download_pr(pr_number, base_branch)

    mock_clone.assert_called_once_with()
    mock_checkout.assert_called_once_with(base_branch)
    mock_get_pr_diff.assert_called_once_with(pr_number, diff_filename)
    mock_apply.assert_not_called()

    assert stdout == ""
    assert failed_get_pr_diff_message in stderr
    assert exit_code == 128
    assert error_stage == git.ERROR_GIT_FETCH

    mock_clone.reset_mock()
    mock_checkout.reset_mock()
    mock_get_pr_diff.reset_mock()
    mock_apply.reset_mock()

    # Test apply stage fails
    mock_clone.return_value = successful_return
    mock_checkout.return_value = successful_return
    mock_get_pr_diff.return_value = successful_return
    mock_apply.return_value = failed_apply_return

    stdout, stderr, exit_code, error_stage = repo.download_pr(pr_number, base_branch)

    mock_clone.assert_called_once_with()
    mock_checkout.assert_called_once_with(base_branch)
    mock_get_pr_diff.assert_called_once_with(pr_number, diff_filename)
    mock_apply.assert_called_once_with(diff_filename)

    assert stdout == ""
    assert failed_apply_message in stderr
    assert exit_code == 128
    assert error_stage == git.ERROR_GIT_APPLY

    mock_clone.reset_mock()
    mock_checkout.reset_mock()
    mock_get_pr_diff.reset_mock()
    mock_apply.reset_mock()

    # Test download_pr() succeeds
    mock_clone.return_value = successful_return
    mock_checkout.return_value = successful_return
    mock_get_pr_diff.return_value = successful_return
    mock_apply.return_value = successful_return

    stdout, stderr, exit_code, error_stage = repo.download_pr(pr_number, base_branch)

    mock_clone.assert_called_once_with()
    mock_checkout.assert_called_once_with(base_branch)
    mock_get_pr_diff.assert_called_once_with(pr_number, diff_filename)
    mock_apply.assert_called_once_with(diff_filename)

    assert stdout == "Downloading PR succeeded"
    assert stderr == ""
    assert exit_code == git.BaseGitRepository._EC_OK
    assert error_stage == git.ERROR_NONE


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
