#!/bin/bash
#
# GitHub App for the EESSI project
#
# A bot to help with requests to add software installations to the EESSI software layer,
# see https://github.com/EESSI/software-layer
#
# author: Bob Droege (@bedroge)
# author: Kenneth Hoste (@boegel)
# author: Hafsa Naeem (@hafsa-naeem)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Usage: run with ./event_handler.sh from directory where eessi_bot_event_handler.py is located
python3 -m eessi_bot_event_handler "$@"
