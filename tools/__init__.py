# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Bob Droege (@bedroge)
# author: Kenneth Hoste (@boegel)
# author: Hafsa Naeem (@hafsa-naeem)
# author: Jacob Ziemke (@jacobz137)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
import os
import subprocess

# Third party imports (anything installed into the local Python environment)
from pyghee.utils import log


# TODO do we really need two functions (run_cmd and run_subprocess) for
# running a command?
def run_cmd(cmd, log_msg='', working_dir=None, log_file=None, raise_on_error=True):
    """
    Runs a command in the shell and raises an error if one occurs.

    Args:
        cmd (string): command to run
        log_msg (string): message describing the purpose of the command
        working_dir (string): location of the job's working directory
        log_file (string): path to log file
        raise_on_error (bool): if True raise an exception in case of error

    Returns:
        tuple of 3 elements containing
        - stdout (string): stdout of the process
        - stderr (string): stderr of the process
        - exit_code (string): exit code of the process

    Raises:
        RuntimeError: raises a RuntimeError if exit code was not zero and
            raise_on_error is True
    """
    # TODO use common method for logging function name in log messages
    stdout, stderr, exit_code = run_subprocess(cmd, log_msg, working_dir, log_file)

    if exit_code != 0:
        error_msg = (
            f"run_cmd(): Error running '{cmd}' in '{working_dir}\n"
            f"           stdout '{stdout}'\n"
            f"           stderr '{stderr}'\n"
            f"           exit code {exit_code}"
        )
        log(error_msg, log_file=log_file)
        if raise_on_error:
            raise RuntimeError(error_msg)
    else:
        log(f"run_cmd(): Result for running '{cmd}' in '{working_dir}\n"
            f"           stdout '{stdout}'\n"
            f"           stderr '{stderr}'\n"
            f"           exit code {exit_code}", log_file=log_file)

    return stdout, stderr, exit_code


def run_subprocess(cmd, log_msg, working_dir, log_file):
    """
    Runs a command in the shell. No error is raised if the command fails.

    Args:
        cmd (string): command to run
        log_msg (string): purpose of the command
        working_dir (string): location of the job's working directory
        log_file (string): path to log file

    Returns:
        tuple of 3 elements containing
        - stdout (string): stdout of the process
        - stderr (string): stderr of the process
        - exit_code (string): exit code of the process
    """
    # TODO use common method for logging function name in log messages
    if working_dir is None:
        working_dir = os.getcwd()

    if log_msg:
        log(f"run_subprocess(): '{log_msg}' by running '{cmd}' in directory '{working_dir}'", log_file=log_file)
    else:
        log(f"run_subprocess(): Running '{cmd}' in directory '{working_dir}'", log_file=log_file)

    result = subprocess.run(cmd,
                            cwd=working_dir,
                            shell=True,
                            encoding="UTF-8",
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE)
    stdout = result.stdout
    stderr = result.stderr
    exit_code = result.returncode

    return stdout, stderr, exit_code
