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
