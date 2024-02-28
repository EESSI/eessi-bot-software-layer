# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
import re
import sys

# Third party imports (anything installed into the local Python environment)
from pyghee.utils import log

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools.filter import EESSIBotActionFilter, EESSIBotActionFilterError


def contains_any_bot_command(body):
    """
    Checks if argument contains any bot command.

    Args:
        body (string): possibly multi-line string that may contain a bot command

    Returns:
        (bool): True if bot command found, False otherwise
    """
    return any(map(get_bot_command, body.split('\n')))


def get_bot_command(line):
    """
    Retrieve bot command from a line.

    Args:
        line (string): string that is scanned for a command

    Returns:
        command (string): the command if any found or None
    """
    fn = sys._getframe().f_code.co_name

    log(f"{fn}(): searching for bot command in '{line}'")
    match = re.search('^bot: (.*)$', line)
    # TODO add log messages for both cases
    if match:
        return match.group(1).rstrip()
    else:
        return None


class EESSIBotCommandError(Exception):
    """
    Exception to be raised when encountering an error with a bot command
    """
    pass


class EESSIBotCommand:
    """
    Class for representing a bot command which includes the command itself and
    a filter to limit for which architecture, repository and bot instance the
    command should be applied to.
    """

    def __init__(self, cmd_str):
        """
        Initializes the command and action filters from a command string

        Args:
            cmd_str (string): full bot command (command itself and arguments)

        Raises:
            EESSIBotCommandError: if EESSIBotActionFilterError is caught while
                creating and EESSIBotActionFilter
            Exception: if any other exception was caught
        """
        # TODO add function name to log messages
        cmd_as_list = cmd_str.split()
        self.command = cmd_as_list[0]
        # TODO always init self.action_filters with empty EESSIBotActionFilter?
        if len(cmd_as_list) > 1:
            arg_str = " ".join(cmd_as_list[1:])
            try:
                self.action_filters = EESSIBotActionFilter(arg_str)
            except EESSIBotActionFilterError as err:
                log(f"ERROR: EESSIBotActionFilterError - {err.args}")
                self.action_filters = None
                raise EESSIBotCommandError("invalid action filter")
            except Exception as err:
                log(f"Unexpected err={err}, type(err)={type(err)}")
                raise
        else:
            self.action_filters = EESSIBotActionFilter("")

    def to_string(self):
        """
        Creates string representing the command including action filters if any

        Args:
            No arguments

        Returns:
            string: the string representation created by the method
        """
        action_filters_str = self.action_filters.to_string()
        return f"{' '.join([self.command, action_filters_str]).rstrip()}"
