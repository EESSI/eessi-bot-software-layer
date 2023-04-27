import json
import os

from collections import namedtuple
from pyghee.lib import get_event_info
from requests.structures import CaseInsensitiveDict


def replay_event(app, event_id):
        """Replay an event stored in the file system

        Args:
            app (EESSIBotSoftwareLayer): the app that is supposed to handle the event
            event_id (string): The id of the event that should be replayed
        """
        event = namedtuple('Request', ['headers', 'json', 'data'])

        for (dir, _subdirs, files) in os.walk("events_log"):
            if any([event_id in file for file in files]):
                with open(f"{dir}/{event_id}_headers.json", 'r') as jf:
                    headers = json.load(jf)
                    event.headers = CaseInsensitiveDict(headers)
                with open(f"{dir}/{event_id}_body.json", 'r') as jf:
                    body = json.load(jf)
                    event.json = body

        event_info = get_event_info(event)
        app.handle_event(event_info)
