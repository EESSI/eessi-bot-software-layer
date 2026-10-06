# Tests for 'bot: status' handling in the event handler
#
# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Caspar van Leeuwen (@casparvl)
#
# license: GPLv2
#
from unittest.mock import MagicMock, patch

import pytest

import eessi_bot_event_handler as eh
from tools.commands import EESSIBotCommand


def make_handler(app_name):
    handler = eh.EESSIBotSoftwareLayer.__new__(eh.EESSIBotSoftwareLayer)
    handler.cfg = {'github': {'app_name': app_name}}
    handler.log = MagicMock()
    return handler


EVENT_INFO = {'raw_request_body': {'repository': {'full_name': 'org/repo'}, 'issue': {'number': 1}}}


@pytest.mark.parametrize("cmd, expect_comment", [
    ("status", True),
    ("status instance:my-bot", True),
    ("status instance:my", True),
    ("status instance:other-bot", False),
    ("status architecture:x86_64/intel/haswell", True),
])
def test_status_instance_filter(cmd, expect_comment):
    handler = make_handler('my-bot')
    table = {'arch': [], 'date': [], 'status': [], 'url': [], 'result': []}
    with patch.object(eh, 'request_bot_build_issue_comments', return_value=table), \
            patch.object(eh, 'create_comment') as mock_create:
        mock_create.return_value.html_url = 'http://url'
        result = handler.handle_bot_command_status(EVENT_INFO, EESSIBotCommand(cmd))
    assert mock_create.called == expect_comment
    assert isinstance(result, str)
