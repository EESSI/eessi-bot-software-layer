# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Bob Droege (@bedroge)
#
# license: GPLv2
#
import configparser
import sys

from .logging import error


def read_config(path='app.cfg'):
    """Read the config file
    Args:
        path (string): path to the configuration file
    Returns:
        dict (str, dict): dictionary containing configuration settings
    """
    fn = sys._getframe().f_code.co_name

    try:
        config = configparser.ConfigParser()
        config.read(path)
    except Exception as err:
        error(f"{fn}(): Unable to read configuration file {path}!\n{err}")

    return dict(config)


def check_required_cfg_settings(req_settings, path="app.cfg"):
    """
    Reads the config file and checks if it contains the required settings, signaling an error if not
    Args:
        req_settings (dict (str, list)): required settings
        path (string): path to the configuration file
    Returns:
        None
    """
    cfg = read_config()
    for section in req_settings.keys():
        if section not in cfg:
            error(f'Missing section "{section}" in configuration file {path}.')
        for item in req_settings[section]:
            if item not in cfg[section]:
                error(f'Missing configuration item "{item}" in section "{section}" of configuration file {path}.')
