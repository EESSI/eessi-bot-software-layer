# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Bob Droege (@bedroge)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
import datetime
import os
import sys

# Third party imports (anything installed into the local Python environment)
# (none yet)

# Local application imports (anything from EESSI/eessi-bot-software-layer)
# (none yet)

# TODO Either reuse one of the 'log_path' configuration settings or change the
# below when addressing issue https://github.com/EESSI/eessi-bot-software-layer/issues/91
LOG = os.path.join(os.getenv('HOME'), 'eessi-bot-software-layer.log')


def error(msg, rc=1):
    """
    Print an error and exit

    Args:
        msg (string): error message to be printed
        rc (int): error code

    Returns:
        function never returns, but rather exits the program
    """
    sys.stderr.write(msg + "\n")
    sys.exit(rc)


def log(msg):
    """
    Log message

    Args:
        msg (string): error message to be printed

    Returns:
        None (implicitly)
    """
    with open(LOG, 'a') as fh:
        timestamp = datetime.datetime.now().strftime("%Y%m%d-T%H:%M:%S")
        fh.write('[' + timestamp + '] ' + msg + '\n')
