# Tests for 'connections/gitlab.py' of the EESSI build-and-deploy bot,
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
from unittest.mock import patch

# Third party imports (anything installed into the local Python environment)
from gitlab.exceptions import GitlabAuthenticationError, GitlabHttpError
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from connections import gitlab
from tools import config


PAT_ENV_VAR_NAME = "GITLAB_PROJECT_ACCESS_TOKEN"
ACCESS_TOKEN = "gl_access_token_123"

CFG = config.read_config()
GITLAB_CFG = CFG[config.SECTION_GITLAB]
INSTANCE_URL = GITLAB_CFG.get(config.GITLAB_SETTING_INSTANCE_URL)
API_TIMEOUT = int(GITLAB_CFG.get(config.GITLAB_SETTING_API_TIMEOUT))


class MockCurrentUser:
    pass


class MockObjects:
    pass


class MockGitlab:
    # python-gitlab Gitlab class has lots of arguments and attributes
    # Only the ones currently used are included here
    def __init__(self, url=None, private_token=None, timeout=None, retry_transient_errors=False):
        if not url:
            url = "https://gitlab.com"
        self.url = url
        self.private_token = private_token
        self.retry_transient_errors = retry_transient_errors
        self.timeout = timeout
        self.user = None
        self._objects = MockObjects()
        self._objects.CurrentUser = MockCurrentUser

        if not self.private_token:
            raise ValueError("'private_token' not set")

    def auth(self):
        # Set 'user' when calling auth()
        self.user = self._objects.CurrentUser()


# Test verify_connection()
def test_verify_connection(capfd):
    # Token is valid and current user is successfully retrieved and stored
    mock_gl = MockGitlab(private_token="irrelevant-for-auth-but-needed-or-constructor-would-raise-ValueError")
    with patch.object(mock_gl, "auth", wraps=mock_gl.auth) as mock_auth:
        # verify_connection() calls gl.auth() and checks gl.user;
        # MockGitlab.auth() and thus mock_gl.auth() sets user without any network I/O.
        gitlab.verify_connection(mock_gl)
        mock_auth.assert_called_once()

    with patch.object(MockGitlab, "auth") as mock_auth:
        # Token is invalid - should exit
        INVALID_TOKEN_MSG = "Invalid access token"
        mock_auth.side_effect = GitlabAuthenticationError(INVALID_TOKEN_MSG)
        with pytest.raises(SystemExit):
            gitlab.verify_connection(mock_gl)
        assert INVALID_TOKEN_MSG in capfd.readouterr().err

        # HTTP error occurs - should exit
        HTTP_ERROR_MSG = "Unable to retrieve user"
        mock_auth.side_effect = GitlabHttpError(HTTP_ERROR_MSG)
        with pytest.raises(SystemExit):
            gitlab.verify_connection(mock_gl)
        assert HTTP_ERROR_MSG in capfd.readouterr().err

        # 'user' is not of type 'CurrentUser' - should exit
        # Make auth() do nothing
        mock_auth.side_effect = None
        mock_gl.user = "Not CurrentUser"
        with pytest.raises(SystemExit):
            gitlab.verify_connection(mock_gl)
        # Error message should mention the 'user' attribute and the 'CurrentUser' type
        err_msg = capfd.readouterr().err
        assert "'user'" in err_msg
        assert "'CurrentUser'" in err_msg


# Test connect()
@patch("connections.gitlab.gitlab.Gitlab", MockGitlab)
def test_connect(capfd):
    # connect() is expected to read the access token from the environment
    # variable $GITLAB_PROJECT_ACCESS_TOKEN (defined via constant PAT_ENV_VAR_NAME)
    os.environ[PAT_ENV_VAR_NAME] = ACCESS_TOKEN
    with patch("connections.gitlab.verify_connection") as mock_verify_connection:
        gitlab.connect()
        # Verify that connect() called verify_connection()
        mock_verify_connection.assert_called()
    # connect() creates the client via
    # gitlab.Gitlab(url, access_token, timeout=timeout, retry_transient_errors=True)
    # with 'url' and 'timeout' from the bot's config and 'access_token' from the
    # environment variable 'GITLAB_PROJECT_ACCESS_TOKEN', and stores it as module-level
    # '_gl'. Since Gitlab is patched with MockGitlab, which simply stores all
    # constructor arguments as attributes, the asserts below verify that connect()
    # passed the expected values.
    gl = gitlab._gl
    assert isinstance(gl, MockGitlab)
    assert gl.url == INSTANCE_URL
    assert gl.private_token == ACCESS_TOKEN
    assert gl.timeout == API_TIMEOUT
    assert gl.retry_transient_errors is True
    # connect() should unset environment variable 'GITLAB_PROJECT_ACCESS_TOKEN'
    assert os.getenv(PAT_ENV_VAR_NAME) is None

    # Test with missing environment variable 'GITLAB_PROJECT_ACCESS_TOKEN' - should exit
    with pytest.raises(SystemExit):
        gitlab.connect()
    # Error message should mention the environment variable
    assert PAT_ENV_VAR_NAME in capfd.readouterr().err


# Test get_instance()
def test_get_instance():
    gitlab._gl = None
    mock_gl = MockGitlab(private_token=ACCESS_TOKEN)

    # To be used as mock connect()
    def set_gl():
        gitlab._gl = mock_gl

    # No existing connection - Connect and return
    with patch("connections.gitlab.connect", side_effect=set_gl) as mock_connect:
        gl = gitlab.get_instance()
        mock_connect.assert_called_once()
        assert gl is gitlab._gl
        assert gl is mock_gl

    # Existing connection - Verify and return
    with patch("connections.gitlab.connect") as mock_connect:
        with patch("connections.gitlab.verify_connection") as mock_verify_connection:
            gl = gitlab.get_instance()
            mock_verify_connection.assert_called()
            mock_connect.assert_not_called()
