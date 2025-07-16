# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Caspar van Leeuwen
#
# license: GPLv2
#

from tools.filter import FILTER_COMPONENT_ACCEL, FILTER_COMPONENT_ARCH

# Define these constants with the same values. We want the arguments passed to
# on: and for: to use the same keywords
BUILD_PARAM_ACCEL = FILTER_COMPONENT_ACCEL
BUILD_PARAM_ARCH = FILTER_COMPONENT_ARCH
BUILD_PARAMS = [
    BUILD_PARAM_ACCEL,
    BUILD_PARAM_ARCH
]


class EESSIBotBuildParamsValueError(Exception):
    """
    Exception to be raised when an inappropriate value is specified for a build parameter
    """
    pass


class EESSIBotBuildParamsNameError(Exception):
    """
    Exception to be raised when an unkown build parameter name is specified
    """
    pass


class EESSIBotBuildParams(dict):
    """
    Class for representing build parameters. Essentially, this is a dictionary class
    but with some additional parsing for the constructor
    """
    def __init__(self, build_parameters):
        """
        EESSIBotBuildParams constructor

        Args:
            build_params (string): string containing comma separated build parameters
            Example: "arch:amd/zen4,accel:nvidia/cc90"

        Raises:
            EESSIBotBuildParamsNameError: raised if parsing an unknown build parameter
                string
            EESSIBotBuildParamsValueError: raised if an invalid value is passed for a build parameter
        """
        build_param_dict = {}

        # Loop over defined build parameters argument
        build_params_list = build_parameters.split(',')
        for item in build_params_list:
            # Separate build parameter name and value
            build_param = item.split('=')
            if len(build_param) != 2:
                msg = f"Expected argument {item} to be split into exactly two parts when splitting by '=', "
                msg += f"but the number of items after splitting is {len(build_param)}"
                raise EESSIBotBuildParamsValueError(msg)
            param_found = False
            for full_param_name in BUILD_PARAMS:
                # Identify which build param we are matching
                if full_param_name.startswith(build_param[0]):
                    param_found = True
                    # Store the value of the build parameter by it's full name
                    build_param_dict[full_param_name] = build_param[1]
            if not param_found:
                msg = f"Build parameter {build_param[0]} not found. Known build parameters: {BUILD_PARAMS}"
                raise EESSIBotBuildParamsNameError(msg)

        super().__init__(build_param_dict)
