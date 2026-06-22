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
from contextlib import nullcontext
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


# Test get_git_hosting_platform()
@pytest.mark.parametrize("cfg,expectation", [
    # 'hosting_platform' set to 'github'
    (CFG, nullcontext(git.GITHUB)),
    (GITHUB_CFG, nullcontext(git.GITHUB)),

    # 'hosting_platform' set to 'gitlab'
    (GITLAB_CFG, nullcontext(git.GITLAB)),

    # 'hosting_platform' set to an invalid value - should exit
    (UNSUPPORTED_PLATFORM_CFG, pytest.raises(SystemExit)),

    # 'hosting_platform' not set - should exit
    (NO_HOSTING_PLATFORM_CFG, pytest.raises(SystemExit)),
])
@patch("tools.config.read_config")
def test_get_git_hosting_platform(mock_read_config, cfg, expectation):
    # Ensure that the Git hosting platform is not cached
    git._git_host = None

    mock_read_config.return_value = cfg

    git._git_host = None

    # Test with provided cfg
    with expectation as expected:
        assert git.get_git_hosting_platform(cfg) == expected
    mock_read_config.assert_not_called()

    git._git_host = None

    # Test without provided cfg
    with expectation as expected:
        assert git.get_git_hosting_platform() == expected
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
