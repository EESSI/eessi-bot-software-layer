# Tests for 'tools/commands.py' of the EESSI build-and-deploy bot,
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
from unittest.mock import patch

# Third party imports (anything installed into the local Python environment)
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools import commands, git


# Test SUPPORTED_COMMANDS_PER_GIT_HOST
@pytest.mark.parametrize("git_host", git.SUPPORTED_GIT_HOSTS)
def test_support_commands_per_git_host(git_host):
    # There should be an entry for each supported Git hosting platform
    assert git_host in commands.SUPPORTED_COMMANDS_PER_GIT_HOST

    # Each entry should be a list of commands
    supported_commands = commands.SUPPORTED_COMMANDS_PER_GIT_HOST[git_host]
    assert isinstance(supported_commands, list)
    assert all([command in commands.ALL_COMMANDS for command in supported_commands])


# Test get_supported_commands()
def test_get_supported_commands():
    HOSTING_PLATFORM = "hosting_platform"

    github_supported_commands = commands.SUPPORTED_COMMANDS_PER_GIT_HOST[git.GITHUB]
    gitlab_supported_commands = commands.SUPPORTED_COMMANDS_PER_GIT_HOST[git.GITLAB]

    # Use as mock get_git_hosting_platform()
    def get_git_host(cfg=None):
        if cfg is None:
            return git.GITHUB
        return cfg.get(HOSTING_PLATFORM)

    with patch("tools.commands.get_git_hosting_platform", side_effect=get_git_host) as mock_get_git_host:
        # Test without provided cfg - mock get_git_hosting_platform() defaults to 'github'
        assert commands.get_supported_commands() is github_supported_commands
        mock_get_git_host.assert_called_once()

        # Test with provided cfg - 'hosting_platform' set to 'github'
        assert commands.get_supported_commands({HOSTING_PLATFORM: git.GITHUB}) == github_supported_commands
        assert mock_get_git_host.call_count == 2

        # Test with provided cfg - 'hosting_platform' set to 'gitlab'
        assert commands.get_supported_commands({HOSTING_PLATFORM: git.GITLAB}) == gitlab_supported_commands
        assert mock_get_git_host.call_count == 3


# Test contains_any_bot_command() with both single-line and multi-line comments
@pytest.mark.parametrize("body,expected", [
    # Test single-line comments
    # Existing command, no space after ':'
    ("bot:help", True),
    # Existing command, space after ':'
    ("bot: help", True),

    # Command does not exist, no space after ':'
    ("bot:nohelp", True),
    # Command does not exist, space after ':'
    ("bot: nohelp", True),

    # Leading whitespace, no space after ':'
    ("  bot:help", False),
    # Leading whitespace, space after ':'
    ("  bot: help", False),

    # Test multi-line comments
    # Valid command in first line, no space after ':'
    ("\n".join(["bot:help", "not a command", "also not a command"]), True),
    # Valid command in first line, space after ':'
    ("\n".join(["bot: help", "not a command", "also not a command"]), True),

    # Valid command after first line, no space after ':'
    ("\n".join(["not a command", "bot:help", "also not a command"]), True),
    # Valid command after first line, space after ':'
    ("\n".join(["not a command", "bot: help", "also not a command"]), True),

    # Multiple valid commands, no space after ':'
    ("\n".join(["bot:help", "bot:nohelp", "also not a command"]), True),
    # Multiple valid commands, space after ':'
    ("\n".join(["bot: help", "bot: nohelp", "also not a command"]), True),

    # No commands
    ("\n".join(["not a command", "also not a command"]), False),

    # Command with leading whitespace after second line, no space after ':'
    ("\n".join(["not a command", "  bot:help", "also not a command"]), False),
    # Command with leading whitespace after second line, space after ':'
    ("\n".join(["not a command", "  bot: help", "also not a command"]), False),
])
def test_contains_any_bot_command(body, expected):
    assert commands.contains_any_bot_command(body) is expected


def test_get_bot_command():
    # Test non-command
    no_cmd = commands.get_bot_command("not a command")
    assert no_cmd is None

    # Test different commands with varying formatting
    test_cmds = [
        # All existing commands
        *commands.ALL_COMMANDS,
        # Build command with filters
        "build on:arch=icelake for:arch=x86_64/intel/icelake,accel=nvidia/cc90 repo:eessi.io-2025.06-software",
        # Non-existant command
        "this_command_does_not_exist",
    ]
    for test_cmd in test_cmds:
        # Valid formatting, with and without space after ':'
        cmd = commands.get_bot_command(f"bot:{test_cmd}")
        assert cmd == test_cmd
        cmd = commands.get_bot_command(f"bot: {test_cmd}")
        assert cmd == test_cmd

        # Leading whitespace, with and without space after ':' - should return None
        cmd = commands.get_bot_command(f"  bot:{test_cmd}")
        assert cmd is None
        cmd = commands.get_bot_command(f"  bot: {test_cmd}")
        assert cmd is None

        # Without ':' - should return None
        cmd = commands.get_bot_command(f"bot {test_cmd}")
        assert cmd is None


# Helper classes for EESSIBotCommand test
class MockActionFilter():
    def __init__(self, action_filters=None):
        self.action_filters = action_filters or []

    def __eq__(self, other):
        return self.action_filters == other.action_filters

    def to_string(self):
        return " ".join([":".join(af) for af in self.action_filters])


class MockCommand():
    def __init__(self, command, general_args=None, action_filters=None, build_params=None):
        self.command = command
        self.general_args = general_args or []
        self.action_filters = action_filters
        self.build_params = build_params

    def __eq__(self, other):
        return (self.command == other.command
                and self.general_args == other.general_args
                and self.action_filters == other.action_filters
                and self.build_params == other.build_params)

    def to_string(self):
        if self.action_filters is None:
            return ""
        string = self.command
        if self.action_filters != MockActionFilter():
            string += f" {self.action_filters.to_string()}"
        return string


# Test EESSIBotCommand class
@pytest.mark.parametrize("cmd_str,expectation", [
    # Test invalid filter
    ("build for:arch=", pytest.raises(commands.EESSIBotCommandError)),

    # Test 'help' command
    ("help", nullcontext(MockCommand("help", action_filters=MockActionFilter()))),

    # Test 'status' command with last_build arg
    ("status last_build", nullcontext(MockCommand("status", general_args=["last_build"]))),

    # Test 'build' command
    ("build on:arch=icelake for:arch=x86_64/intel/icelake,accel=nvidia/cc90 repo:eessi.io-2025.06-software",
     nullcontext(MockCommand("build",
                             action_filters=MockActionFilter([("architecture", "icelake"),
                                                              ("repository", "eessi.io-2025.06-software")]),
                             build_params={"architecture": "x86_64/intel/icelake", "accelerator": "nvidia/cc90"})))
])
def test_EESSIBotCommand(cmd_str, expectation):
    with expectation as expected_command:
        command = commands.EESSIBotCommand(cmd_str)
        assert command == expected_command
        assert command.to_string() == expected_command.to_string()
