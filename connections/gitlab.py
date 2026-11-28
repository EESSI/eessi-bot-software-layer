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
import os

# Third party imports (anything installed into the local Python environment)
import gitlab

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools import config, logging


_gl = None


def verify_connection(gl):
    """
    Verifies connection to GitLab. Exits if verification fails.

    Args:
        Instance of gitlab.Gitlab (from python-gitlab)

    Returns:
        None (implicit)
    """
    try:
        # auth tests the instance's credentials by retrieving the access token user
        gl.auth()
        if type(gl.user) is not gl._objects.CurrentUser:
            raise Exception("'user' attribute of Gitlab class instance is not of type 'CurrentUser'.")
    except Exception as err:
        logging.error(f"Failed to verify GitLab connection: {err}")


def connect():
    """
    Creates a gitlab.Gitlab instance (from python-gitlab), then verifies the connection to GitLab.

    Args:
        No arguments

    Returns:
        None (implicit)
    """
    global _gl
    cfg = config.read_config()
    gitlab_cfg = cfg[config.SECTION_GITLAB]
    timeout = int(gitlab_cfg.get(config.GITLAB_SETTING_API_TIMEOUT, 10))
    url = gitlab_cfg.get(config.GITLAB_SETTING_INSTANCE_URL)

    access_token = os.getenv('GITLAB_PROJECT_ACCESS_TOKEN')
    if access_token is None:
        logging.error("GitLab token is not available via $GITLAB_PROJECT_ACCESS_TOKEN!")
    else:
        del os.environ['GITLAB_PROJECT_ACCESS_TOKEN']

    _gl = gitlab.Gitlab(url, access_token, timeout=timeout, retry_transient_errors=True)
    verify_connection(_gl)


def get_instance():
    """
    Returns a gitlab.Gitlab instance. Creates an instance if one does not exist,
    otherwise verifies the existing instance.

    Args:
        No arguments

    Returns:
        Instance of gitlab.Gitlab (from python-gitlab)
    """
    if not _gl:
        connect()
    else:
        verify_connection(_gl)
    return _gl
