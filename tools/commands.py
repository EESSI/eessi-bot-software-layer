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
from tools.build_params import EESSIBotBuildParams


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
    regex = re.compile('^bot:[ ]?(.*)$')
    match = regex.search(line)
    if match:
        cmd = match.group(1).rstrip()
        log(f"{fn}(): Bot command found in '{line}': {cmd}")
        return cmd
    else:
        log(f"{fn}(): No bot command found using pattern '{regex.pattern}' in: {line}")
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
        self.command = cmd_as_list[0]  # E.g. 'build' or 'help'
        self.general_args = []
        self.action_filters = None
        self.build_params = None

        # TODO always init self.action_filters with empty EESSIBotActionFilter?
        if len(cmd_as_list) > 1:
            # Extract arguments for the action filters
            # By default, everything that follows the 'on:' argument (until the next space) is
            # considered part of the argument list for the action filters
            target_args = []
            other_filter_args = []
            on_found = False
            for arg in cmd_as_list[1:]:
                if arg.startswith('on:'):
                    on_found = True
                    # Extract everything after 'on:' and split by comma
                    filter_content = arg[3:]  # Remove 'on:' prefix
                    target_args.extend(filter_content.split(','))
                elif arg.startswith('for:'):
                    # Anything listed as 'for:' is build parameters
                    build_params = arg[4:]
                    # EESSIBotBuildParams is essentially a dict, but parses the input argument
                    # according to the expected argument format for 'for:'
                    self.build_params = EESSIBotBuildParams(build_params)
                else:
                    # Anything that is not 'on:' or 'for:'
                    # Check if it's a filter argument, if so, pass it on to other_filter_args witout further parsing
                    # If it's not a filter argument, it is a general argument - just store it so any other function
                    # can read it
                    if ':' in arg:
                        other_filter_args.extend([arg])
                    else:
                        self.general_args.append(arg)

            # If no 'on:' is found in the argument list, everything that follows the 'for:' argument
            # (until the next space) is considered the argument list for the action filters
            # Essentially, this represents a native build, i.e. the hardware we build for should be the
            # hardware we build on
            if not on_found:
                for arg in cmd_as_list[1:]:
                    if arg.startswith('for:'):
                        # Extract everything after the 'for:' suffix and split by comma
                        filter_content = arg[4:]
                        target_args.extend(filter_content.split(','))

            # Join the filter arguments and pass to EESSIBotActionFilter
            # At this point, target_args is e.g. ["arch=amd/zen2","accel=nvidia/cc90"]
            # But EESSIBotActionFilter expects e.g. "arch:amd/zen2 accel:nvidia/cc90"
            # First, normalize to the ["arch:amd/zen2", "accel:nvidia/cc90"] format
            normalized_filters = []
            if target_args:
                for filter_item in target_args:
                    if '=' in filter_item:
                        component, pattern = filter_item.split('=', 1)
                        normalized_filters.append(f"{component}:{pattern}")

            # Add the other filter args to the normalized filters. The other_filter_args are already colon-separated
            # so no special parsing needed there
            log(f"Extracted filter arguments related to hardware target: {normalized_filters}")
            log(f"Other extracted filter arguments: {other_filter_args}")
            log(f"Other general arguments: {self.general_args}")
            normalized_filters += other_filter_args

            # Finally, change into a space-separated string, as expected by EESSIBotActionFilter
            # e.g "arch:amd/zen2 accel:nvidia/cc90 repo:my.repo.io"
            if normalized_filters:
                arg_str = " ".join(normalized_filters)
                try:
                    log(f"Passing the following arguments to the EESSIBotActionFilter: {arg_str}")
                    self.action_filters = EESSIBotActionFilter(arg_str)
                except EESSIBotActionFilterError as err:
                    log(f"ERROR: EESSIBotActionFilterError - {err.args}")
                    self.action_filters = None
                    raise EESSIBotCommandError("invalid action filter")
                except Exception as err:
                    log(f"Unexpected err={err}, type(err)={type(err)}")
                    raise
        # No arguments were passed to the command self.command
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
        if self.action_filters is None:
            return ""
        else:
            action_filters_str = self.action_filters.to_string()
            return f"{' '.join([self.command, action_filters_str]).rstrip()}"
