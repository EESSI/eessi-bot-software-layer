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

# Standard library imports
import os

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools.job_metadata import determine_job_id_from_job_directory, get_section_from_file, JOB_PR_SECTION


def test_determine_job_id_from_job_directory(tmp_path):
    logfile = os.path.join(tmp_path, "test_determine_job_id_from_job_directory.log")

    job_dir = os.path.join(tmp_path, "5")
    assert determine_job_id_from_job_directory(job_dir, logfile) == 5

    # determine_job_id_from_job_directory() should return 0 for non-job dirs
    not_job_dir = os.path.join(tmp_path, "not-a-job-dir")
    assert determine_job_id_from_job_directory(not_job_dir, logfile) == 0


def test_get_section_from_file(tmp_path):
    logfile = os.path.join(tmp_path, 'test_get_section_from_file.log')
    # if metadata file does not exist, we should get None as return value
    path = os.path.join(tmp_path, 'test.metadata')
    assert get_section_from_file(path, JOB_PR_SECTION, logfile) is None

    # Reading an empty file should return an empty dictionary
    with open(path, 'w') as fp:
        pass
    metadata_pr = get_section_from_file(path, JOB_PR_SECTION, logfile)
    assert metadata_pr == {}

    # Should return None if file exists but is invalid
    with open(path, 'w') as fp:
        fp.write("invalid format")
    metadata_pr = get_section_from_file(path, JOB_PR_SECTION, logfile)
    assert metadata_pr is None

    # Write a valid metadata file
    with open(path, 'w') as fp:
        fp.write('''[PR]
        repo=test
        pr_number=12345
        pr_comment_id=23456
        job_owner=user01''')

    # Verify that the metadata file is read correctly
    metadata_pr = get_section_from_file(path, JOB_PR_SECTION, logfile)
    expected = {
        "repo": "test",
        "pr_number": "12345",
        "pr_comment_id": "23456",
        "job_owner": "user01",
    }
    assert metadata_pr == expected
