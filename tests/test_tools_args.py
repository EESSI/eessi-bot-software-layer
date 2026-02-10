# Tests for 'tools/args.py' of the EESSI build-and-deploy bot,
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
from argparse import Namespace
from contextlib import nullcontext

# Third party imports (anything installed into the local Python environment)
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools import args


# Test parse_common_args()
@pytest.mark.parametrize("test_args,expected_parsed,expected_unknown", [
    # No args
    ([], Namespace(debug=False), []),

    # Short-form args
    (["-d"], Namespace(debug=True), []),

    # Long-form args
    (["--debug"], Namespace(debug=True), []),

    # Unknown args
    (["-u", "--unknown"], Namespace(debug=False), ["-u", "--unknown"]),
])
def test_parse_common_args(test_args, expected_parsed, expected_unknown):
    parsed_args, unknown = args.parse_common_args(test_args)

    assert parsed_args == expected_parsed
    assert sorted(unknown) == sorted(expected_unknown)


# Test event_handler_parse()
@pytest.mark.parametrize("test_args,expectation", [
    # No args
    ([], nullcontext(Namespace(debug=False, build=False, test=False, cron=False, file=None, port=3000))),

    # Short-form args
    (["-d", "-b", "-t", "-c", "-f", "file.json", "-p", "8000"],
     nullcontext(Namespace(debug=True, build=True, test=True, cron=True, file="file.json", port="8000"))),

    # Long-form args
    (["--debug", "--build", "--test", "--cron", "--file", "file2.json", "--port", "9000"],
     nullcontext(Namespace(debug=True, build=True, test=True, cron=True, file="file2.json", port="9000"))),

    # Unknown args - should fail and exit
    (["-u"], pytest.raises(SystemExit)),
    (["--unknown"], pytest.raises(SystemExit)),
])
def test_event_handler_parse_known_args(test_args, expectation):
    with expectation as expected:
        assert args.event_handler_parse(test_args) == expected


# Test job_manager_parse()
@pytest.mark.parametrize("test_args,expectation", [
    # No args
    ([], nullcontext(Namespace(debug=False, max_manager_iterations=-1, jobs=None))),

    # Short-form args
    (["-d", "-i", "0", "-j", "17"],
     nullcontext(Namespace(debug=True, max_manager_iterations="0", jobs="17"))),

    # Long-form args
    (["--debug", "--max-manager-iterations", "10", "--jobs", "4,18,48"],
     nullcontext(Namespace(debug=True, max_manager_iterations="10", jobs="4,18,48"))),

    # Unknown args - should fail and exit
    (["-u"], pytest.raises(SystemExit)),
    (["--unknown"], pytest.raises(SystemExit)),
])
def test_job_manager_parse_known_args(test_args, expectation):
    with expectation as expected:
        assert args.job_manager_parse(test_args) == expected
