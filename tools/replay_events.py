# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Jonas Qvigstad (@jonas-lq)
#
# license: GPLv2
#
import json

from collections import namedtuple
from pyghee.lib import get_event_info
from requests.structures import CaseInsensitiveDict
from tools import config

EVENT_HANDLER = "event_handler"
EVENT_LINKS_PATH = "event_links_path"


def replay_event(app, event_id):
    """Replay an event stored in the file system

    Args:
        app (EESSIBotSoftwareLayer): the app that is supposed to handle the event
        event_id (string): The id of the event that should be replayed
    """
    event = namedtuple('Request', ['headers', 'json', 'data'])
    events_dir = config.read_config()[EVENT_HANDLER][EVENT_LINKS_PATH] + "/event_links"

    with open(f"{events_dir}/{event_id}_headers.json", 'r') as jf:
        headers = json.load(jf)
        event.headers = CaseInsensitiveDict(headers)
    with open(f"{events_dir}/{event_id}_body.json", 'r') as jf:
        body = json.load(jf)
        event.json = body

    event_info = get_event_info(event)
    app.handle_event(event_info)
