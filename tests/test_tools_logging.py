# Tests for 'tools/logging.py' of the EESSI build-and-deploy bot,
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
import os

# Third party imports (anything installed into the local Python environment)
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools import logging


# Test error() - should write to stderr and exit
def test_error(capfd):
    # Test exit code 1 (default)
    msg = "this is the first error message"
    with pytest.raises(SystemExit, check=lambda err: int(err.code) == 1):
        logging.error(msg)
    assert msg in capfd.readouterr().err

    # Test exit code 0
    msg2 = "this is the second error message"
    with pytest.raises(SystemExit, check=lambda err: int(err.code) == 0):
        logging.error(msg2, rc=0)
    assert msg2 in capfd.readouterr().err


# Test log()
def test_log(monkeypatch, tmp_path):
    # Use a new log file
    log_file = os.path.join(tmp_path, "test.log")
    monkeypatch.setattr(logging, "LOG", log_file)

    # log() should create the file if it does not exist
    msg = "this is the first test message"
    logging.log(msg)
    assert os.path.exists(tmp_path)
    with open(log_file, "r") as fp:
        assert msg in fp.read()

    # log() should not truncate the file if it already exists
    msg2 = "this is the second test message"
    logging.log(msg2)
    with open(log_file, "r") as fp:
        log_contents = fp.read()
    assert msg in log_contents
    assert msg2 in log_contents
