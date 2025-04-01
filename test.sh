#!/bin/bash
#
# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# author: Kenneth Hoste (@boegel)
#
# license: GPLv2
#
PYTHONPATH=$PWD:$PYTHONPATH pytest --verbose --capture=no --cov=$PWD --cov-report=html
