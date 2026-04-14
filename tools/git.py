# This file is part of the EESSI build-and-deploy bot,
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
# (none)

# Third party imports (anything installed into the local Python environment)
# (none)

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from connections import github, gitlab
from tools import config, logging


GITHUB = "github"
GITLAB = "gitlab"

SUPPORTED_HOSTS = {
    GITHUB,
    GITLAB,
}

_git_host = None


def get_hosting_platform():
    """
    Read the config and get the Git hosting platform the bot is configured for.
    Exit if the setting is invalid or not set.

    Args:
        No arguments

    Returns:
        (str): The configured Git hosting platform
    """
    global _git_host
    if not _git_host:
        cfg = config.read_config()
        _git_host = cfg.get(config.SECTION_GIT, config.GIT_SETTING_HOSTING_PLATFORM, fallback=None)
        if _git_host not in SUPPORTED_HOSTS:
            logging.error(f"Invalid Git host configured: '{_git_host}'")
    return _git_host


def connect_to_host():
    git_host = get_hosting_platform()
    if git_host == GITHUB:
        github.connect()
    elif git_host == GITLAB:
        gitlab.connect()
    else:
        logging.error(f"Git host not supported: '{git_host}'")
