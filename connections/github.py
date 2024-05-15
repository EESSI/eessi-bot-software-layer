# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Bob Droege (@bedroge)
# author: Hafsa Naeem (@hafsa-naeem)
# author: Jacob Ziemke (@jacobz137)
# author: Lara Ramona Peeters (@laraPPr)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
from datetime import datetime, timedelta, timezone
import time

# Third party imports (anything installed into the local Python environment)
import github

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools import config, logging

_token = None
_gh = None


def get_token():
    """
    Generates a new access token for the installation (defined via app.cfg)
    using the private key (path to key file defined via app.cfg). Attempts
    to generate the token up to three times if the exception
    (NotImplementedError) is caught.

    Note that installation access tokens last only for 1 hour. Expired tokens
    need to be regenerated.

    Args:
        No arguments

    Returns:
        Created token or None
    """

    global _token
    cfg = config.read_config()
    github_cfg = cfg[config.SECTION_GITHUB]
    app_id = github_cfg.get(config.GITHUB_SETTING_APP_ID)
    installation_id = github_cfg.get(config.GITHUB_SETTING_INSTALLATION_ID)
    private_key_path = github_cfg.get(config.GITHUB_SETTING_PRIVATE_KEY)
    private_key = ''

    with open(private_key_path, 'r') as private_key_file:
        private_key = private_key_file.read()

    tries = 3
    for i in range(tries):
        # If the config keys are not set, get_access_token will raise a NotImplementedError
        # Returning NoneType token will stop the connection in get_instance
        try:
            github_integration = github.GithubIntegration(app_id, private_key)
            _token = github_integration.get_access_token(installation_id)
            break
        except NotImplementedError as err:
            if i < tries - 1:
                # Increase wait times linearily for subsequent attempts.
                n = 0.8
                t = n*(i+1)
                time.sleep(t)
                continue
            else:
                logging.error(err)
                _token = None

    return _token


def connect():
    """
    Creates an instance of Github using a newly created access token

    Args:
        No arguments

    Returns:
        Instance of Github
    """
    return github.Github(get_token().token)


def get_instance():
    """
    Returns an instance of Github (connection to GitHub) using an existing
    instance or a renewed one if the access token has expired.

    Args:
        No arguments

    Returns:
        Instance of Github
    """
    global _gh, _token

    # Check if PyGithub version is < 1.56
    if hasattr(github, 'GithubRetry'):
        # Pygithub 2.x
        time_now = datetime.now(timezone.utc)
    else:
        # Pygithub 1.x
        time_now = datetime.utcnow()

    # Renew token already if expiry date is less then 30 min away.
    refresh_time = timedelta(minutes=30)

    if not _gh or (_token and time_now > (_token.expires_at - refresh_time)):
        _gh = connect()
    return _gh


def token():
    """
    Returns the globally defined _token.

    Args:
        No arguments

    Returns:
        Token
    """
    global _token
    return _token
