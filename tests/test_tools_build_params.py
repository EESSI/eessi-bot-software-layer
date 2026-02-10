# Tests for 'tools/build_params.py' of the EESSI build-and-deploy bot,
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
from tools import build_params


# Test EESSIBotBuildParams class
@pytest.mark.parametrize("build_parameters,expectation", [
    # Test value error
    ("notaparam", pytest.raises(build_params.EESSIBotBuildParamsValueError)),

    # Test name error
    ("thisparam=doesnotexist", pytest.raises(build_params.EESSIBotBuildParamsNameError)),

    # Test complete component names
    ("architecture=x86_64/amd/zen4,accelerator=nvidia/cc80",
     nullcontext({"architecture": "x86_64/amd/zen4", "accelerator": "nvidia/cc80"})),

    # Test shortened component names
    ("arch=aarch64/nvidia/grace,accel=nvidia/cc90",
     nullcontext({"architecture": "aarch64/nvidia/grace", "accelerator": "nvidia/cc90"})),
])
def test_EESSIBotBuildParams(build_parameters, expectation):
    with expectation as expected_params:
        params = build_params.EESSIBotBuildParams(build_parameters)
        # Verify that the resulting object contains the expected items
        for name, expected_value in expected_params.items():
            assert params[name] == expected_value
