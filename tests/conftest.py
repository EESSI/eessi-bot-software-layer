# Configuration of pytest settings for the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Thomas Roeblitz (@trz42)
# author: Sondre Bergsvaag Risanger (@sondrebr)
#
# license: GPLv2
#

import os
import shutil


def pytest_configure(config):
    # register custom markers
    config.addinivalue_line(
        "markers", "repo_name(name): parametrize test function with a repo name"
    )
    config.addinivalue_line(
        "markers", "pr_number(num): parametrize test function with a PR number"
    )
    config.addinivalue_line(
        "markers", "create_raises(string): define function behaviour"
    )
    config.addinivalue_line(
        "markers", "create_fails(bool): let function create_issue_comment return None"
    )


def pytest_sessionstart():
    # Back up app.cfg if it exists
    if os.path.exists("app.cfg"):
        shutil.copyfile("app.cfg", "appbackup.cfg")

    # Copy needed app.cfg from tests directory
    shutil.copyfile("tests/test_app.cfg", "app.cfg")


def pytest_sessionfinish():
    # Restore backup if it exists
    if os.path.exists("appbackup.cfg"):
        shutil.copyfile("appbackup.cfg", "app.cfg")
