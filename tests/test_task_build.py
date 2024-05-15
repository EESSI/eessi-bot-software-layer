# Tests for 'build' task of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Bob Droege (@bedroge)
# author: Kenneth Hoste (@boegel)
# author: Hafsa Naeem (@hafsa-naeem)
# author: Jacob Ziemke (@jacobz137)
# author: Pedro Santos Neves (@Neves-P)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
import filecmp
import os
import re
import shutil
from unittest.mock import patch

# Third party imports (anything installed into the local Python environment)
from collections import namedtuple
from datetime import datetime
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tasks.build import Job, create_pr_comment
from tools import run_cmd, run_subprocess
from tools.job_metadata import create_metadata_file, read_metadata_file
from tools.pr_comments import PRComment, get_submitted_job_comment

# Local tests imports (reusing code from other tests)
from tests.test_tools_pr_comments import MockIssueComment


def test_run_cmd(tmpdir):
    """Tests for run_cmd function."""
    log_file = os.path.join(tmpdir, "log.txt")
    output, err, exit_code = run_cmd("echo hello", 'test', tmpdir, log_file=log_file)

    assert exit_code == 0
    assert output == "hello\n"
    assert err == ""

    with pytest.raises(Exception):
        output, err, exit_code = run_cmd("ls -l /does_not_exists.txt", 'fail test', tmpdir, log_file=log_file)

        assert exit_code != 0
        assert output == ""
        assert "No such file or directory" in err

    output, err, exit_code = run_cmd("ls -l /does_not_exists.txt",
                                     'fail test',
                                     tmpdir,
                                     log_file=log_file,
                                     raise_on_error=False)

    assert exit_code != 0
    assert output == ""
    assert "No such file or directory" in err

    with pytest.raises(Exception):
        output, err, exit_code = run_cmd("this_command_does_not_exist", 'fail test', tmpdir, log_file=log_file)

        assert exit_code != 0
        assert output == ""
        assert ("this_command_does_not_exist: command not found" in err or
                "this_command_does_not_exist: not found" in err)

    output, err, exit_code = run_cmd("this_command_does_not_exist",
                                     'fail test',
                                     tmpdir,
                                     log_file=log_file,
                                     raise_on_error=False)

    assert exit_code != 0
    assert output == ""
    assert ("this_command_does_not_exist: command not found" in err or
            "this_command_does_not_exist: not found" in err)

    output, err, exit_code = run_cmd("echo hello", "test in file", tmpdir, log_file=log_file)
    with open(log_file, "r") as fp:
        assert "test in file" in fp.read()


def test_run_subprocess(tmpdir):
    """Tests for run_subprocess function."""
    log_file = os.path.join(tmpdir, "log.txt")
    output, err, exit_code = run_subprocess("echo hello", 'test', tmpdir, log_file=log_file)

    assert exit_code == 0
    assert output == "hello\n"
    assert err == ""

    output, err, exit_code = run_subprocess("ls -l /does_not_exists.txt", 'fail test', tmpdir, log_file=log_file)

    assert exit_code != 0
    assert output == ""
    assert "No such file or directory" in err

    output, err, exit_code = run_subprocess("this_command_does_not_exist", 'fail test', tmpdir, log_file=log_file)

    assert exit_code != 0
    assert output == ""
    assert ("this_command_does_not_exist: command not found" in err or "this_command_does_not_exist: not found" in err)

    output, err, exit_code = run_subprocess("echo hello", "test in file", tmpdir, log_file=log_file)
    with open(log_file, "r") as fp:
        assert "test in file" in fp.read()


class CreateIssueCommentException(Exception):
    "Raised when pr.create_issue_comment fails in a test."
    pass


# cases for testing create_pr_comment (essentially testing create_issue_comment)
# - create_issue_comment succeeds immediately
#   - returns !None --> create_pr_comment returns comment (with id == 1)
#   - returns None --> create_pr_comment returns None
# - create_issue_comment fails once, then succeeds
#   - returns !None --> create_pr_comment returns comment (with id == 1)
# - create_issue_comment always fails
# - create_issue_comment fails 3 times
#   - symptoms of failure: exception raised or return value of tested func None

# overall course of creating mocked objects
# patch gh.get_repo(repo_name) --> returns a MockRepository
# MockRepository provides repo.get_pull(pr_number) --> returns a MockPullRequest
# MockPullRequest provides pull_request.create_issue_comment

class CreateRepositoryException(Exception):
    "Raised when gh.create_repo fails in a test, i.e., if repository already exists."
    pass


class CreatePullRequestException(Exception):
    "Raised when repo.create_pr fails in a test, i.e., if pull request already exists."
    pass


class MockGitHub:
    def __init__(self):
        self.repos = {}

    def create_repo(self, repo_name):
        if repo_name in self.repos:
            raise CreateRepositoryException
        else:
            self.repos[repo_name] = MockRepository(repo_name)
            return self.repos[repo_name]

    def get_repo(self, repo_name):
        repo = self.repos[repo_name]
        return repo


MockBase = namedtuple('MockBase', ['repo'])


MockRepo = namedtuple('MockRepo', ['full_name'])


class MockRepository:
    def __init__(self, repo_name):
        self.repo_name = repo_name
        self.pull_requests = {}

    def create_pr(self, pr_number, create_raises='0', create_exception=Exception, create_fails=False):
        if pr_number in self.pull_requests:
            raise CreatePullRequestException
        else:
            self.pull_requests[pr_number] = MockPullRequest(pr_number, create_raises,
                                                            CreateIssueCommentException, create_fails)
            self.pull_requests[pr_number].base = MockBase(MockRepo(self.repo_name))
            return self.pull_requests[pr_number]

    def get_pull(self, pr_number):
        pr = self.pull_requests[pr_number]
        return pr


class MockPullRequest:
    def __init__(self, pr_number, create_raises='0', create_exception=Exception, create_fails=False):
        self.number = pr_number
        self.issue_comments = []
        self.create_fails = create_fails
        self.create_raises = create_raises
        self.create_exception = create_exception
        self.create_call_count = 0
        self.base = None

    def create_issue_comment(self, body):
        def should_raise_exception():
            """
            Determine whether or not an exception should be raised, based on value
            of $TEST_RAISE_EXCEPTION
            0: don't raise exception, return value as expected (call succeeds)
            >0: decrease value by one, raise exception (call fails, retry may succeed)
            always_raise: raise exception (call fails always)
            create_issue_comment -> CreateIssueCommentException
            """
            should_raise = False

            count_regex = re.compile('^[0-9]+$')

            if self.create_raises == 'always_raise':
                should_raise = True
            # if self.create_raises is a number, raise exception when > 0 and
            # decrement with 1
            elif count_regex.match(self.create_raises):
                if int(self.create_raises) > 0:
                    should_raise = True
                    self.create_raises = str(int(self.create_raises) - 1)

            return should_raise

        def no_sleep_after_create(delay):
            print(f"pr.create_issue_comment failed - sleeping {delay} s (mocked)")

        self.create_call_count = self.create_call_count + 1
        with patch('retry.api.time.sleep') as mock_sleep:
            mock_sleep.side_effect = no_sleep_after_create

            if should_raise_exception():
                raise self.create_exception

            if self.create_fails:
                return None
            self.issue_comments.append(MockIssueComment(body))
            return self.issue_comments[-1]

    def get_issue_comments(self):
        return self.issue_comments


@pytest.fixture
def mocked_github(request):
    def no_sleep_after_create(delay):
        print(f"pr.create_issue_comment failed - sleeping {delay} s (mocked)")

    with patch('retry.api.time.sleep') as mock_sleep:
        mock_sleep.side_effect = no_sleep_after_create
        mock_gh = MockGitHub()

        repo_name = "e2s2i/no_name"
        marker1 = request.node.get_closest_marker("repo_name")
        if marker1:
            repo_name = marker1.args[0]
        mock_repo = mock_gh.create_repo(repo_name)

        pr_number = 1
        marker2 = request.node.get_closest_marker("pr_number")
        if marker2:
            pr_number = marker2.args[0]
        create_raises = '0'
        marker3 = request.node.get_closest_marker("create_raises")
        if marker3:
            create_raises = marker3.args[0]
        create_exception = CreateIssueCommentException
        create_fails = False
        marker5 = request.node.get_closest_marker("create_fails")
        if marker5:
            create_fails = marker5.args[0]
        mock_repo.create_pr(pr_number, create_raises=create_raises,
                            create_exception=create_exception, create_fails=create_fails)

        yield mock_gh


# case 1: create_issue_comment succeeds immediately
#         returns !None --> create_pr_comment returns comment (with id == 1)
@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
def test_create_pr_comment_succeeds(mocked_github, tmpdir):
    """Tests for function create_pr_comment."""
    shutil.copyfile("tests/test_app.cfg", "app.cfg")
    # creating a PR comment
    print("CREATING PR COMMENT")
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 1
    job = Job(tmpdir, "test/architecture", "EESSI", "--speed-up", ym, pr_number)

    job_id = "123"
    app_name = "pytest"

    repo_name = "EESSI/software-layer"
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    symlink = "/symlink"
    comment = create_pr_comment(job, job_id, app_name, pr, mocked_github, symlink)
    assert comment.id == 1
    # check if created comment includes jobid?
    print("VERIFYING PR COMMENT")
    comment = get_submitted_job_comment(pr, job_id)
    assert job_id in comment.body


# case 2: create_issue_comment succeeds immediately
#         returns None --> create_pr_comment returns None
@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
@pytest.mark.create_fails(True)
def test_create_pr_comment_succeeds_none(mocked_github, tmpdir):
    """Tests for function create_pr_comment."""
    shutil.copyfile("tests/test_app.cfg", "app.cfg")
    # creating a PR comment
    print("CREATING PR COMMENT")
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 1
    job = Job(tmpdir, "test/architecture", "EESSI", "--speed-up", ym, pr_number)

    job_id = "123"
    app_name = "pytest"

    repo_name = "EESSI/software-layer"
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    symlink = "/symlink"
    comment = create_pr_comment(job, job_id, app_name, pr, mocked_github, symlink)
    assert comment is None


# case 3: create_issue_comment fails once, then succeeds
#         returns !None --> create_pr_comment returns comment (with id == 1)
@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
@pytest.mark.create_raises("1")
def test_create_pr_comment_raises_once_then_succeeds(mocked_github, tmpdir):
    """Tests for function create_pr_comment."""
    shutil.copyfile("tests/test_app.cfg", "app.cfg")
    # creating a PR comment
    print("CREATING PR COMMENT")
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 1
    job = Job(tmpdir, "test/architecture", "EESSI", "--speed-up", ym, pr_number)

    job_id = "123"
    app_name = "pytest"

    repo_name = "EESSI/software-layer"
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    symlink = "/symlink"
    comment = create_pr_comment(job, job_id, app_name, pr, mocked_github, symlink)
    assert comment.id == 1
    assert pr.create_call_count == 2


# case 4: create_issue_comment always fails
@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
@pytest.mark.create_raises("always_raise")
def test_create_pr_comment_always_raises(mocked_github, tmpdir):
    """Tests for function create_pr_comment."""
    shutil.copyfile("tests/test_app.cfg", "app.cfg")
    # creating a PR comment
    print("CREATING PR COMMENT")
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 1
    job = Job(tmpdir, "test/architecture", "EESSI", "--speed-up", ym, pr_number)

    job_id = "123"
    app_name = "pytest"

    repo_name = "EESSI/software-layer"
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    symlink = "/symlink"
    with pytest.raises(Exception) as err:
        create_pr_comment(job, job_id, app_name, pr, mocked_github, symlink)
    assert err.type == CreateIssueCommentException
    assert pr.create_call_count == 3


# case 5: create_issue_comment fails 3 times
@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
@pytest.mark.create_raises("3")
def test_create_pr_comment_three_raises(mocked_github, tmpdir):
    """Tests for function create_pr_comment."""
    shutil.copyfile("tests/test_app.cfg", "app.cfg")
    # creating a PR comment
    print("CREATING PR COMMENT")
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 1
    job = Job(tmpdir, "test/architecture", "EESSI", "--speed-up", ym, pr_number)

    job_id = "123"
    app_name = "pytest"

    repo_name = "EESSI/software-layer"
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    symlink = "/symlink"
    with pytest.raises(Exception) as err:
        create_pr_comment(job, job_id, app_name, pr, mocked_github, symlink)
    assert err.type == CreateIssueCommentException
    assert pr.create_call_count == 3


@pytest.mark.repo_name("test_repo")
@pytest.mark.pr_number(999)
def test_create_read_metadata_file(mocked_github, tmpdir):
    """Tests for function create_metadata_file."""
    # create some test data
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 999
    job = Job(tmpdir, "test/architecture", "EESSI", "--speed_up_job", ym, pr_number)

    job_id = "123"

    repo_name = "test_repo"
    pr_comment = PRComment(repo_name, pr_number, 77)
    create_metadata_file(job, job_id, pr_comment)

    expected_file = f"_bot_job{job_id}.metadata"
    expected_file_path = os.path.join(tmpdir, expected_file)
    # assert expected_file exists
    assert os.path.exists(expected_file_path)

    # assert file contents =
    # [PR]
    # repo = test_repo
    # pr_number = 999
    # pr_comment_id = 77
    test_file = "tests/test_bot_job123.metadata"
    assert filecmp.cmp(expected_file_path, test_file, shallow=False)

    # also check reading back of metadata file
    metadata = read_metadata_file(expected_file_path)
    assert "PR" in metadata
    assert metadata["PR"]["repo"] == "test_repo"
    assert metadata["PR"]["pr_number"] == "999"
    assert metadata["PR"]["pr_comment_id"] == "77"
    assert sorted(metadata["PR"].keys()) == ["pr_comment_id", "pr_number", "repo"]

    # use directory that does not exist
    dir_does_not_exist = os.path.join(tmpdir, "dir_does_not_exist")
    job2 = Job(dir_does_not_exist, "test/architecture", "EESSI", "--speed_up_job", ym, pr_number)
    job_id2 = "222"
    with pytest.raises(FileNotFoundError):
        create_metadata_file(job2, job_id2, pr_comment)

    # use directory without write permission
    dir_without_write_perm = os.path.join("/")
    job3 = Job(dir_without_write_perm, "test/architecture", "EESSI", "--speed_up_job", ym, pr_number)
    job_id3 = "333"
    with pytest.raises(OSError):
        create_metadata_file(job3, job_id3, pr_comment)

    # disk quota exceeded (difficult to create and unlikely to happen because
    # partition where file is stored is usually very large)

    # use undefined values for parameters
    # job_id = None
    job4 = Job(tmpdir, "test/architecture", "EESSI", "--speed_up_job", ym, pr_number)
    job_id4 = None
    create_metadata_file(job4, job_id4, pr_comment)

    expected_file4 = f"_bot_job{job_id}.metadata"
    expected_file_path4 = os.path.join(tmpdir, expected_file4)
    # assert expected_file exists
    assert os.path.exists(expected_file_path4)

    # assert file contents =
    test_file = "tests/test_bot_job123.metadata"
    assert filecmp.cmp(expected_file_path4, test_file, shallow=False)

    # use undefined values for parameters
    # job.working_dir = None
    job5 = Job(None, "test/architecture", "EESSI", "--speed_up_job", ym, pr_number)
    job_id5 = "555"
    with pytest.raises(TypeError):
        create_metadata_file(job5, job_id5, pr_comment)
