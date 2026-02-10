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

# Third party imports (anything installed into the local Python environment)
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools import commands


def test_contains_any_bot_command():
    # Test without command
    body = "\n".join([
        "not a command",
        "also not a command"
    ])
    assert commands.contains_any_bot_command(body) is False

    # Test with command
    body = "\n".join([
        "not a command",
        "bot: help",
        "also not a command"
    ])
    assert commands.contains_any_bot_command(body) is True


def test_get_bot_command():
    # Test non-command
    no_cmd = commands.get_bot_command("not a command")
    assert no_cmd is None

    # Test command
    test_cmd = "help"
    cmd = commands.get_bot_command(f"bot: {test_cmd}")
    assert cmd == test_cmd


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
