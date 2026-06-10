# Tests for 'tools/permissions.py' of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Sondre Bergsvaag Risanger (@sondrebr)
#
# license: GPLv2
#

# Third party imports (anything installed into the local Python environment)
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools import permissions


# Test check_command_permission()
@pytest.mark.parametrize("user,expected", [
    # In test_app.cfg:
    # command_permission = user01 second_user

    # Users in test config
    ("user01", True),
    ("second_user", True),

    # Users not in test config
    ("user03", False),
    ("another_user_not_in_cfg", False),
])
def test_check_command_permission(user, expected):
    assert permissions.check_command_permission(user) is expected
