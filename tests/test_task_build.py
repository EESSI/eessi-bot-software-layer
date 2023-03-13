# Tests for 'build' task of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Kenneth Hoste (@boegel)
# author: Hafsa Naeem (@hafsa-naeem)
# author: Jacob Ziemke (@jacobz137)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
import filecmp
import os

# Third party imports (anything installed into the local Python environment)
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tasks.build import Job, create_metadata_file, create_pr_comment
from tools import run_cmd, run_subprocess
from tools.pr_comments import get_submitted_job_comment

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
#   - returns !None --> create_pr_comment returns 1
#   - returns None --> create_pr_comment returns -1
# - create_issue_comment fails once, then succeeds
#   - returns !None --> create_pr_comment returns 1
# - create_issue_comment always fails
# - create_issue_comment fails 3 times
#   - symptoms of failure: exception raised or return value of tested func -1

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


class MockRepository:
    def __init__(self, repo_name):
        self.repo_name = repo_name
        self.pull_requests = {}

    def create_pr(self, pr_number, create_fails=False):
        if pr_number in self.pull_requests:
            raise CreatePullRequestException
        else:
            self.pull_requests[pr_number] = MockPullRequest(pr_number, create_fails)
            return self.pull_requests[pr_number]

    def get_pull(self, pr_number):
        pr = self.pull_requests[pr_number]
        return pr


class MockPullRequest:
    def __init__(self, pr_number, create_fails=False):
        self.pr_number = pr_number
        self.issue_comments = []
        self.create_fails = create_fails

    def create_issue_comment(self, body):
        if self.create_fails:
            return None
        self.issue_comments.append(MockIssueComment(body))
        return self.issue_comments[-1]

    def get_issue_comments(self):
        return self.issue_comments


@pytest.fixture
def mocked_github(request):
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
    create_fails = False
    marker3 = request.node.get_closest_marker("create_fails")
    if marker3:
        create_fails = marker3.args[0]
    mock_repo.create_pr(pr_number, create_fails=create_fails)

    yield mock_gh


# case 1: create_issue_comment succeeds immediately
#         returns !None --> create_pr_comment returns 1
@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
def test_create_pr_comment_succeeds(mocked_github, tmpdir):
    """Tests for function create_pr_comment."""
    # creating a PR comment
    print("CREATING PR COMMENT")
    job = Job(tmpdir, "test/architecture", "--speed-up")
    job_id = "123"
    app_name = "pytest"
    pr_number = 1
    repo_name = "EESSI/software-layer"
    symlink = "/symlink"
    comment_id = create_pr_comment(job, job_id, app_name, pr_number, repo_name, mocked_github, symlink)
    assert comment_id == 1
    # check if created comment includes jobid?
    print("VERIFYING PR COMMENT")
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    comment = get_submitted_job_comment(pr, job_id)
    assert job_id in comment.body


# case 2: create_issue_comment succeeds immediately
#         returns None --> create_pr_comment returns -1
@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
@pytest.mark.create_fails(True)
def test_create_pr_comment_succeeds_none(mocked_github, tmpdir):
    """Tests for function create_pr_comment."""
    # creating a PR comment
    print("CREATING PR COMMENT")
    job = Job(tmpdir, "test/architecture", "--speed-up")
    job_id = "123"
    app_name = "pytest"
    pr_number = 1
    repo_name = "EESSI/software-layer"
    symlink = "/symlink"
    comment_id = create_pr_comment(job, job_id, app_name, pr_number, repo_name, mocked_github, symlink)
    assert comment_id == -1


def test_create_metadata_file(tmpdir):
    """Tests for function create_metadata_file."""
    # create some test data
    job = Job(tmpdir, "test/architecture", "--speed_up_job")
    job_id = "123"
    repo_name = "test_repo"
    pr_number = 999
    pr_comment_id = 77
    create_metadata_file(job, job_id, repo_name, pr_number, pr_comment_id)

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

    # use directory that does not exist
    dir_does_not_exist = os.path.join(tmpdir, "dir_does_not_exist")
    job2 = Job(dir_does_not_exist, "test/architecture", "--speed_up_job")
    job_id2 = "222"
    with pytest.raises(FileNotFoundError):
        create_metadata_file(job2, job_id2, repo_name, pr_number, pr_comment_id)

    # use directory without write permission
    dir_without_write_perm = os.path.join("/")
    job3 = Job(dir_without_write_perm, "test/architecture", "--speed_up_job")
    job_id3 = "333"
    with pytest.raises(OSError):
        create_metadata_file(job3, job_id3, repo_name, pr_number, pr_comment_id)

    # disk quota exceeded (difficult to create and unlikely to happen because
    # partition where file is stored is usually very large)

    # use undefined values for parameters
    # job_id = None
    job4 = Job(tmpdir, "test/architecture", "--speed_up_job")
    job_id4 = None
    create_metadata_file(job4, job_id4, repo_name, pr_number, pr_comment_id)

    expected_file4 = f"_bot_job{job_id}.metadata"
    expected_file_path4 = os.path.join(tmpdir, expected_file4)
    # assert expected_file exists
    assert os.path.exists(expected_file_path4)

    # assert file contents =
    test_file = "tests/test_bot_job123.metadata"
    assert filecmp.cmp(expected_file_path4, test_file, shallow=False)

    # use undefined values for parameters
    # job.working_dir = None
    job5 = Job(None, "test/architecture", "--speed_up_job")
    job_id5 = "555"
    with pytest.raises(TypeError):
        create_metadata_file(job5, job_id5, repo_name, pr_number, pr_comment_id)
