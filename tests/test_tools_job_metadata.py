# Tests for 'tools/job_metadata.py' of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

import os

from tools.job_metadata import get_section_from_file, JOB_PR_SECTION


def test_get_section_from_file(tmpdir):
    logfile = os.path.join(tmpdir, 'test_get_section_from_file.log')
    # if metadata file does not exist, we should get None as return value
    path = os.path.join(tmpdir, 'test.metadata')
    assert get_section_from_file(path, JOB_PR_SECTION, logfile) is None

    with open(path, 'w') as fp:
        fp.write('''[PR]
        repo=test
        pr_number=12345''')

    metadata_pr = get_section_from_file(path, JOB_PR_SECTION, logfile)
    expected = {
        "repo": "test",
        "pr_number": "12345",
    }
    assert metadata_pr == expected
