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
from unittest.mock import Mock, patch

# Third party imports (anything installed into the local Python environment)
from collections import namedtuple
from datetime import datetime
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tasks.build import Job, create_pr_comment, request_bot_build_issue_comments
from tools import run_cmd, run_subprocess
from tools.build_params import EESSIBotBuildParams
from tools.job_metadata import create_metadata_file, read_metadata_file
from tools.pr_comments import PRCommentInfo, get_submitted_job_comment

# Local tests imports (reusing code from other tests)
from tests.test_tools_pr_comments import MockIssueComment


def test_run_cmd(tmp_path):
    """Tests for run_cmd function."""
    log_file = os.path.join(tmp_path, "log.txt")
    output, err, exit_code = run_cmd("echo hello", 'test', tmp_path, log_file=log_file)

    assert exit_code == 0
    assert output == "hello\n"
    assert err == ""

    # Command fails and raise_on_error=True
    with pytest.raises(Exception):
        output, err, exit_code = run_cmd("ls -l /does_not_exists.txt", 'fail test', tmp_path, log_file=log_file)

        assert exit_code != 0
        assert output == ""
        assert "No such file or directory" in err

    # Command fails and raise_on_error=False
    output, err, exit_code = run_cmd("ls -l /does_not_exists.txt",
                                     'fail test',
                                     tmp_path,
                                     log_file=log_file,
                                     raise_on_error=False)

    assert exit_code != 0
    assert output == ""
    assert "No such file or directory" in err

    # Command does not exists and raise_on_error=True
    with pytest.raises(Exception):
        output, err, exit_code = run_cmd("this_command_does_not_exist", 'fail test', tmp_path, log_file=log_file)

        assert exit_code != 0
        assert output == ""
        assert ("this_command_does_not_exist: command not found" in err or
                "this_command_does_not_exist: not found" in err)

    # Command does not exists and raise_on_error=False
    output, err, exit_code = run_cmd("this_command_does_not_exist",
                                     'fail test',
                                     tmp_path,
                                     log_file=log_file,
                                     raise_on_error=False)

    assert exit_code != 0
    assert output == ""
    assert ("this_command_does_not_exist: command not found" in err or
            "this_command_does_not_exist: not found" in err)

    # Check that log_msg is written to log_file
    output, err, exit_code = run_cmd("echo hello", "test in file", tmp_path, log_file=log_file)
    with open(log_file, "r") as fp:
        assert "test in file" in fp.read()


def test_run_subprocess(tmp_path):
    """Tests for run_subprocess function."""
    log_file = os.path.join(tmp_path, "log.txt")
    output, err, exit_code = run_subprocess("echo hello", 'test', tmp_path, log_file=log_file)

    assert exit_code == 0
    assert output == "hello\n"
    assert err == ""

    # log_msg=""
    output, err, exit_code = run_subprocess("echo hello", "", tmp_path, log_file=log_file)

    assert exit_code == 0
    assert output == "hello\n"
    assert err == ""
    with open(log_file, "r") as fp:
        # TODO: Better way to do this?
        assert "run_subprocess(): Running" in fp.read()

    # working_dir=tmp_path
    output, err, exit_code = run_subprocess("pwd", "test", tmp_path, log_file=log_file)

    assert exit_code == 0
    assert f"{tmp_path}\n" == output
    assert err == ""

    # working_dir=None
    wd = os.getcwd()
    output, err, exit_code = run_subprocess("pwd", "test", None, log_file=log_file)

    assert exit_code == 0
    assert wd in output
    assert err == ""

    # env is not None
    output, err, exit_code = run_subprocess("env", "test", tmp_path, log_file=log_file, env={"DUMMY": "123"})

    assert exit_code == 0
    assert "DUMMY=123" in output
    assert err == ""

    # Command fails
    output, err, exit_code = run_subprocess("ls -l /does_not_exists.txt", 'fail test', tmp_path, log_file=log_file)

    assert exit_code != 0
    assert output == ""
    assert "No such file or directory" in err

    # Command does not exist
    output, err, exit_code = run_subprocess("this_command_does_not_exist", 'fail test', tmp_path, log_file=log_file)

    assert exit_code != 0
    assert output == ""
    assert ("this_command_does_not_exist: command not found" in err or "this_command_does_not_exist: not found" in err)

    # Check that log_msg is written to log_file
    output, err, exit_code = run_subprocess("echo hello", "test in file", tmp_path, log_file=log_file)
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

    def get_instance(self):
        return self


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
def test_create_pr_comment_succeeds(monkeypatch, mocked_github, tmp_path):
    """Tests for function create_pr_comment."""
    monkeypatch.setattr('tools.pr_comments.github', mocked_github)
    # creating a PR comment
    print("CREATING PR COMMENT")
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 1
    job = Job(tmp_path, "test/architecture", "EESSI", "--speed-up", ym, pr_number, "fpga/magic", "user01", "")
    build_params = EESSIBotBuildParams("arch=amd/zen4,accel=nvidia/cc90")

    job_id = "123"
    app_name = "pytest"

    repo_name = "EESSI/software-layer"
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    symlink = "/symlink"
    comment = create_pr_comment(job, job_id, app_name, pr, symlink, build_params)
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
def test_create_pr_comment_succeeds_none(monkeypatch, mocked_github, tmp_path):
    """Tests for function create_pr_comment."""
    monkeypatch.setattr('tools.pr_comments.github', mocked_github)
    # creating a PR comment
    print("CREATING PR COMMENT")
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 1
    job = Job(tmp_path, "test/architecture", "EESSI", "--speed-up", ym, pr_number, "fpga/magic", "user01", "")
    build_params = EESSIBotBuildParams("arch=amd/zen4,accel=nvidia/cc90")

    job_id = "123"
    app_name = "pytest"

    repo_name = "EESSI/software-layer"
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    symlink = "/symlink"
    comment = create_pr_comment(job, job_id, app_name, pr, symlink, build_params)
    assert comment is None


# case 3: create_issue_comment fails once, then succeeds
#         returns !None --> create_pr_comment returns comment (with id == 1)
@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
@pytest.mark.create_raises("1")
def test_create_pr_comment_raises_once_then_succeeds(monkeypatch, mocked_github, tmp_path):
    """Tests for function create_pr_comment."""
    monkeypatch.setattr('tools.pr_comments.github', mocked_github)
    # creating a PR comment
    print("CREATING PR COMMENT")
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 1
    job = Job(tmp_path, "test/architecture", "EESSI", "--speed-up", ym, pr_number, "fpga/magic", "user01", "")
    build_params = EESSIBotBuildParams("arch=amd/zen4,accel=nvidia/cc90")

    job_id = "123"
    app_name = "pytest"

    repo_name = "EESSI/software-layer"
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    symlink = "/symlink"
    comment = create_pr_comment(job, job_id, app_name, pr, symlink, build_params)
    assert comment.id == 1
    assert pr.create_call_count == 2


# case 4: create_issue_comment always fails
@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
@pytest.mark.create_raises("always_raise")
def test_create_pr_comment_always_raises(monkeypatch, mocked_github, tmp_path):
    """Tests for function create_pr_comment."""
    monkeypatch.setattr('tools.pr_comments.github', mocked_github)
    # creating a PR comment
    print("CREATING PR COMMENT")
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 1
    job = Job(tmp_path, "test/architecture", "EESSI", "--speed-up", ym, pr_number, "fpga/magic", "user01", "")
    build_params = EESSIBotBuildParams("arch=amd/zen4,accel=nvidia/cc90")

    job_id = "123"
    app_name = "pytest"

    repo_name = "EESSI/software-layer"
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    symlink = "/symlink"
    with pytest.raises(Exception) as err:
        create_pr_comment(job, job_id, app_name, pr, symlink, build_params)
    assert err.type == CreateIssueCommentException
    assert pr.create_call_count == 3


# case 5: create_issue_comment fails 3 times
@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
@pytest.mark.create_raises("3")
def test_create_pr_comment_three_raises(monkeypatch, mocked_github, tmp_path):
    """Tests for function create_pr_comment."""
    monkeypatch.setattr('tools.pr_comments.github', mocked_github)
    # creating a PR comment
    print("CREATING PR COMMENT")
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 1
    job = Job(tmp_path, "test/architecture", "EESSI", "--speed-up", ym, pr_number, "fpga/magic", "user01", "")
    build_params = EESSIBotBuildParams("arch=amd/zen4,accel=nvidia/cc90")

    job_id = "123"
    app_name = "pytest"

    repo_name = "EESSI/software-layer"
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    symlink = "/symlink"
    with pytest.raises(Exception) as err:
        create_pr_comment(job, job_id, app_name, pr, symlink, build_params)
    assert err.type == CreateIssueCommentException
    assert pr.create_call_count == 3


@pytest.mark.repo_name("test_repo")
@pytest.mark.pr_number(999)
def test_create_read_metadata_file(mocked_github, tmp_path):
    """Tests for function create_metadata_file."""
    # create some test data
    ym = datetime.today().strftime('%Y.%m')
    pr_number = 999
    job = Job(tmp_path, "test/architecture", "EESSI", "--speed_up_job", ym, pr_number, "fpga/magic", "user01")

    job_id = "123"

    repo_name = "test_repo"
    pr_comment = PRCommentInfo(repo_name, pr_number, 77)
    create_metadata_file(job, job_id, pr_comment)

    expected_file = f"_bot_job{job_id}.metadata"
    expected_file_path = os.path.join(tmp_path, expected_file)
    # assert expected_file exists
    assert os.path.exists(expected_file_path)

    # assert file contents =
    # [PR]
    # repo = test_repo
    # pr_number = 999
    # pr_comment_id = 77
    # job_owner = user01
    test_file = "tests/test_bot_job123.metadata"
    assert filecmp.cmp(expected_file_path, test_file, shallow=False)

    # also check reading back of metadata file
    metadata = read_metadata_file(expected_file_path)
    assert "PR" in metadata
    assert metadata["PR"]["repo"] == "test_repo"
    assert metadata["PR"]["pr_number"] == "999"
    assert metadata["PR"]["pr_comment_id"] == "77"
    assert metadata["PR"]["job_owner"] == "user01"
    assert sorted(metadata["PR"].keys()) == ["job_owner", "pr_comment_id", "pr_number", "repo"]

    # use directory that does not exist
    dir_does_not_exist = os.path.join(tmp_path, "dir_does_not_exist")
    job2 = Job(dir_does_not_exist, "test/architecture", "EESSI", "--speed_up_job", ym, pr_number, "fpga/magic",
               "user01")
    job_id2 = "222"
    with pytest.raises(FileNotFoundError):
        create_metadata_file(job2, job_id2, pr_comment)

    # use directory without write permission
    dir_without_write_perm = os.path.join("/")
    job3 = Job(dir_without_write_perm, "test/architecture", "EESSI", "--speed_up_job", ym, pr_number, "fpga/magic",
               "user01")
    job_id3 = "333"
    with pytest.raises(OSError):
        create_metadata_file(job3, job_id3, pr_comment)

    # disk quota exceeded (difficult to create and unlikely to happen because
    # partition where file is stored is usually very large)

    # use undefined values for parameters
    # job_id = None
    job4 = Job(tmp_path, "test/architecture", "EESSI", "--speed_up_job", ym, pr_number, "fpga/magic", "user01")
    job_id4 = None
    create_metadata_file(job4, job_id4, pr_comment)

    expected_file4 = f"_bot_job{job_id}.metadata"
    expected_file_path4 = os.path.join(tmp_path, expected_file4)
    # assert expected_file exists
    assert os.path.exists(expected_file_path4)

    # assert file contents =
    test_file = "tests/test_bot_job123.metadata"
    assert filecmp.cmp(expected_file_path4, test_file, shallow=False)

    # use undefined values for parameters
    # job.working_dir = None
    job5 = Job(None, "test/architecture", "EESSI", "--speed_up_job", ym, pr_number, "fpga/magic", "user01")
    job_id5 = "555"
    with pytest.raises(TypeError):
        create_metadata_file(job5, job_id5, pr_comment)


@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
def test_create_pr_comment_with_commit_sha(monkeypatch, mocked_github, tmp_path):
    """Tests that create_pr_comment includes commit SHA from cloned repo."""
    import subprocess
    monkeypatch.setattr('tools.pr_comments.github', mocked_github)

    # Set up a git repo in tmp_path with a commit
    subprocess.run(['git', 'init'], cwd=tmp_path, capture_output=True)
    subprocess.run(['git', 'config', 'user.name', 'test'], cwd=tmp_path, capture_output=True)
    subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=tmp_path, capture_output=True)
    test_file = os.path.join(tmp_path, 'test.txt')
    with open(test_file, 'w') as f:
        f.write('test content')
    subprocess.run(['git', 'add', '.'], cwd=tmp_path, capture_output=True)
    subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=tmp_path, capture_output=True)

    ym = datetime.today().strftime('%Y.%m')
    pr_number = 1
    job = Job(tmp_path, "test/architecture", "EESSI", "--speed-up", ym, pr_number, "fpga/magic", "user01", "")
    build_params = EESSIBotBuildParams("arch=amd/zen4,accel=nvidia/cc90")

    job_id = "123"
    app_name = "pytest"

    repo_name = "EESSI/software-layer"
    repo = mocked_github.get_repo(repo_name)
    pr = repo.get_pull(pr_number)
    symlink = "/symlink"
    comment = create_pr_comment(job, job_id, app_name, pr, symlink, build_params)

    # Get the actual commit SHA
    result = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=tmp_path, capture_output=True, text=True)
    expected_sha = result.stdout.strip()

    assert comment.id == 1
    assert f"Commit SHA: `{expected_sha}`" in comment.body


@pytest.mark.repo_name("EESSI/software-layer")
@pytest.mark.pr_number(1)
def test_request_bot_build_issue_comments(monkeypatch):
    """Tests that request_bot_build_issue_comments extracts commit SHA."""
    from tools import config as build_config
    original_read_config = build_config.read_config

    def mock_read_config(path='app.cfg'):
        cfg = original_read_config(path)
        return cfg

    monkeypatch.setattr('tasks.build.config.read_config', mock_read_config)

    # Mock the GitHub token
    token_mock = Mock()
    token_mock.token = 'mock-token'
    monkeypatch.setattr('tasks.build.github.token', lambda: token_mock)
    monkeypatch.setattr('tasks.build.github.get_instance', lambda: Mock())

    # Mock the response from the GitHub API
    comment_body = "\n".join([
        "New job on instance `pytest` for repository `EESSI/software-layer`",
        "Building on: `x86_64/generic`",
        "Building for: `x86_64/generic`",
        "Job dir: `symlink`",
        "Commit SHA: `abc123`",
        "|date|job status|comment|",
        "|----------|----------|------------------------|",
        "|Jan 01 00:00:00 UTC 2025|finished|SUCCESS|",
    ])
    response_mock = Mock()
    response_mock.json.return_value = [{'body': comment_body, 'html_url': 'https://example.com'}]
    response_mock.links = {}
    response_mock.headers = {
        'X-RateLimit-Reset': '0',
        'X-RateLimit-Limit': '5000',
        'X-RateLimit-Remaining': '4999',
    }
    monkeypatch.setattr('tasks.build.requests.get', lambda *args, **kwargs: response_mock)

    status_table = request_bot_build_issue_comments('EESSI/software-layer', 1)

    assert status_table['commit sha'] == ['abc123']
    assert status_table['result'] == [':grin: SUCCESS']


class TestValidateArgs:
    """Tests for validate_args function in tasks/build.py"""

    def test_jobargs_exact_match(self):
        from tasks.build import validate_args
        patterns = [{"key": "^SKIP_TESTS$", "value": "^yes$"}]
        accepted, rejected = validate_args(["SKIP_TESTS=yes"], patterns, arg_type="jobargs")
        assert accepted == ["SKIP_TESTS=yes"]
        assert rejected == []

    def test_jobargs_regex_match(self):
        from tasks.build import validate_args
        patterns = [{"key": "SKIP_.*", "value": "yes|no"}]
        accepted, rejected = validate_args(
            ["SKIP_TESTS=yes", "SKIP_INTEGRATION=no"], patterns, arg_type="jobargs"
        )
        assert accepted == ["SKIP_TESTS=yes", "SKIP_INTEGRATION=no"]
        assert rejected == []

    def test_jobargs_rejected_value(self):
        from tasks.build import validate_args
        patterns = [{"key": "^SKIP_TESTS$", "value": "^yes$"}]
        accepted, rejected = validate_args(["SKIP_TESTS=maybe"], patterns, arg_type="jobargs")
        assert accepted == []
        assert rejected == ["SKIP_TESTS=maybe"]

    def test_jobargs_rejected_key(self):
        from tasks.build import validate_args
        patterns = [{"key": "^SKIP_TESTS$", "value": "^yes$"}]
        accepted, rejected = validate_args(["OTHER=yes"], patterns, arg_type="jobargs")
        assert accepted == []
        assert rejected == ["OTHER=yes"]

    def test_jobargs_missing_equals(self):
        from tasks.build import validate_args
        patterns = [{"key": ".*", "value": ".*"}]
        accepted, rejected = validate_args(["INVALID"], patterns, arg_type="jobargs")
        assert accepted == []
        assert rejected == ["INVALID"]

    def test_submitargs_match(self):
        from tasks.build import validate_args
        patterns = [{"value": "--time=.*"}]
        accepted, rejected = validate_args(["--time=01:00:00"], patterns, arg_type="submitargs")
        assert accepted == ["--time=01:00:00"]
        assert rejected == []

    def test_submitargs_rejected(self):
        from tasks.build import validate_args
        patterns = [{"value": "--time=.*"}]
        accepted, rejected = validate_args(["--partition=gpu"], patterns, arg_type="submitargs")
        assert accepted == []
        assert rejected == ["--partition=gpu"]

    def test_empty_patterns_reject_all(self):
        from tasks.build import validate_args
        accepted, rejected = validate_args(["SKIP_TESTS=yes"], [], arg_type="jobargs")
        assert accepted == []
        assert rejected == ["SKIP_TESTS=yes"]


class TestGetAllowedArgs:
    """Tests for get_allowed_args function in tasks/build.py"""

    def test_auto_migrate_from_exportvars(self):
        from tasks.build import get_allowed_args
        import json
        import configparser
        cfg = configparser.ConfigParser()
        cfg["buildenv"] = {
            "allowed_exportvars": json.dumps(["SKIP_TESTS=yes", "SKIP_TESTS=no"]),
        }
        result = get_allowed_args(cfg, "allowed_jobargs")
        assert len(result) == 2
        assert result[0]["key"] == "^SKIP_TESTS$"
        assert result[0]["value"] == "^yes$"
        assert result[1]["key"] == "^SKIP_TESTS$"
        assert result[1]["value"] == "^no$"

    def test_jobargs_takes_precedence_over_exportvars(self):
        from tasks.build import get_allowed_args
        import json
        import configparser
        cfg = configparser.ConfigParser()
        cfg["buildenv"] = {
            "allowed_exportvars": json.dumps(["SKIP_TESTS=yes"]),
            "allowed_jobargs": json.dumps([{"key": "DEBUG_.*", "value": "true|false"}]),
        }
        result = get_allowed_args(cfg, "allowed_jobargs")
        assert len(result) == 1
        assert result[0]["key"] == "DEBUG_.*"

    def test_submitargs_no_legacy_fallback(self):
        from tasks.build import get_allowed_args
        import json
        import configparser
        cfg = configparser.ConfigParser()
        cfg["buildenv"] = {
            "allowed_exportvars": json.dumps(["SKIP_TESTS=yes"]),
        }
        result = get_allowed_args(cfg, "allowed_submitargs")
        assert result == []

    def test_empty_settings(self):
        from tasks.build import get_allowed_args
        import configparser
        cfg = configparser.ConfigParser()
        cfg["buildenv"] = {}
        assert get_allowed_args(cfg, "allowed_jobargs") == []
        assert get_allowed_args(cfg, "allowed_submitargs") == []

    def test_invalid_json_returns_empty(self):
        # If the JSON cannot be decoded, get_allowed_args should log and
        # return [] rather than calling error() (which exits the process).
        from tasks.build import get_allowed_args
        import configparser
        cfg = configparser.ConfigParser()
        cfg["buildenv"] = {
            "allowed_jobargs": "not valid json",
        }
        assert get_allowed_args(cfg, "allowed_jobargs") == []

    def test_invalid_json_legacy_returns_empty(self):
        # Same for the legacy allowed_exportvars auto-migration path.
        from tasks.build import get_allowed_args
        import configparser
        cfg = configparser.ConfigParser()
        cfg["buildenv"] = {
            "allowed_exportvars": "not valid json",
        }
        assert get_allowed_args(cfg, "allowed_jobargs") == []


class TestCheckAllowedArgsConfig:
    """Tests for check_allowed_args_config function in tasks/build.py"""

    def test_valid_json_passes(self):
        from tasks.build import check_allowed_args_config
        import json
        import configparser
        cfg = configparser.ConfigParser()
        cfg["buildenv"] = {
            "allowed_jobargs": json.dumps([{"key": "SKIP_.*", "value": "yes|no"}]),
            "allowed_submitargs": json.dumps([{"value": "--time=.*"}]),
            "allowed_exportvars": json.dumps(["SKIP_TESTS=yes"]),
        }
        assert check_allowed_args_config(cfg) is True

    def test_invalid_json_fails(self):
        from tasks.build import check_allowed_args_config
        import configparser
        cfg = configparser.ConfigParser()
        cfg["buildenv"] = {
            "allowed_jobargs": "not valid json",
        }
        assert check_allowed_args_config(cfg) is False

    def test_empty_settings_pass(self):
        from tasks.build import check_allowed_args_config
        import configparser
        cfg = configparser.ConfigParser()
        cfg["buildenv"] = {}
        assert check_allowed_args_config(cfg) is True


class TestSanitizeArg:
    """Tests for sanitize_arg function in tasks/build.py"""

    def test_safe_jobargs(self):
        from tasks.build import sanitize_arg
        assert sanitize_arg("SKIP_TESTS=yes", "jobargs")

    def test_safe_jobargs_with_dollar(self):
        # '$' is allowed in jobargs values (e.g. EB_ARGS=--installpath=/tmp/$USER/pr12345)
        # because jobargs are written to export_vars.sh and sourced by the shell.
        from tasks.build import sanitize_arg
        assert sanitize_arg("EB_ARGS=--installpath=/tmp/$USER/pr12345", "jobargs")

    def test_safe_jobargs_empty_value(self):
        # An empty value is allowed (e.g. FOO= to unset a variable).
        from tasks.build import sanitize_arg
        assert sanitize_arg("FOO=", "jobargs")

    def test_safe_submitargs(self):
        from tasks.build import sanitize_arg
        assert sanitize_arg("--time=01:00:00", "submitargs")
        assert sanitize_arg("--export=ALL,FOO=bar", "submitargs")

    def test_rejects_backticks(self):
        from tasks.build import sanitize_arg
        assert not sanitize_arg("VAR=yes`echo dangerous`", "jobargs")

    def test_rejects_dollar_paren(self):
        from tasks.build import sanitize_arg
        assert not sanitize_arg("VAR=$(malicious)", "jobargs")

    def test_rejects_semicolon(self):
        from tasks.build import sanitize_arg
        assert not sanitize_arg("--time=01:00:00;echo dangerous", "submitargs")

    def test_rejects_pipe(self):
        from tasks.build import sanitize_arg
        assert not sanitize_arg("VAR=value|cat /etc/passwd", "jobargs")

    def test_rejects_ampersand(self):
        from tasks.build import sanitize_arg
        assert not sanitize_arg("VAR=value&&malicious", "jobargs")

    def test_rejects_spaces_in_jobargs_value(self):
        # Spaces in jobargs values are still rejected. Note: the upstream parser
        # (tools/commands.py) splits commands on whitespace, so a value with
        # spaces would already be broken before reaching sanitize_arg. Supporting
        # quoted values with spaces would require parser changes.
        from tasks.build import sanitize_arg
        assert not sanitize_arg("VAR=with spaces", "jobargs")

    def test_rejects_spaces_in_submitargs(self):
        from tasks.build import sanitize_arg
        assert not sanitize_arg("--time=01:00:00 echo dangerous", "submitargs")

    def test_rejects_dollar_in_submitargs(self):
        # '$' is not allowed in submitargs because they are appended to an
        # sbatch command line executed with shell=True.
        from tasks.build import sanitize_arg
        assert not sanitize_arg("--time=$FOO", "submitargs")

    def test_rejects_injection_in_key(self):
        # A key like ${UNDEF:-rm -rf} must be rejected: keys must be valid
        # shell identifiers ([a-zA-Z_][a-zA-Z0-9_]*).
        from tasks.build import sanitize_arg
        assert not sanitize_arg("${UNDEF:-echo dangerous}=yes", "jobargs")

    def test_rejects_newline(self):
        from tasks.build import sanitize_arg
        assert not sanitize_arg("VAR=with\nnewline", "jobargs")


class TestValidateArgsSecurity:
    """Tests that validate_args blocks shell injection even with permissive patterns"""

    def test_permissive_pattern_allows_safe_arg(self):
        from tasks.build import validate_args
        patterns = [{"key": ".*", "value": ".*"}]
        accepted, rejected = validate_args(["SKIP_TESTS=yes"], patterns, arg_type="jobargs")
        assert accepted == ["SKIP_TESTS=yes"]
        assert rejected == []

    def test_permissive_pattern_allows_dollar_in_jobargs_value(self):
        # '$' in jobargs values is safe (export_vars.sh is sourced by the shell)
        # and should pass even with a permissive '.*' pattern.
        from tasks.build import validate_args
        patterns = [{"key": ".*", "value": ".*"}]
        accepted, rejected = validate_args(["EB_ARGS=--installpath=/tmp/$USER/pr12345"], patterns, arg_type="jobargs")
        assert accepted == ["EB_ARGS=--installpath=/tmp/$USER/pr12345"]
        assert rejected == []

    def test_permissive_pattern_blocks_injection_jobargs(self):
        from tasks.build import validate_args
        patterns = [{"key": ".*", "value": ".*"}]
        accepted, rejected = validate_args(["EVIL=yes`echo dangerous`"], patterns, arg_type="jobargs")
        assert accepted == []
        assert rejected == ["EVIL=yes`echo dangerous`"]

    def test_permissive_pattern_blocks_injection_submitargs(self):
        from tasks.build import validate_args
        patterns = [{"value": ".*"}]
        accepted, rejected = validate_args(["--time=01:00:00;echo dangerous"], patterns, arg_type="submitargs")
        assert accepted == []
        assert rejected == ["--time=01:00:00;echo dangerous"]

    def test_permissive_pattern_blocks_injection_in_key(self):
        # Even with '.*' for both key and value, a key containing shell
        # metacharacters (e.g. ${UNDEF:-echo dangerous}) must be rejected.
        from tasks.build import validate_args
        patterns = [{"key": ".*", "value": ".*"}]
        accepted, rejected = validate_args(
            ["${UNDEF:-echo dangerous}=yes"], patterns, arg_type="jobargs"
        )
        assert accepted == []
        assert rejected == ["${UNDEF:-echo dangerous}=yes"]


class TestCheckPatternsWellformed:
    """Tests for check_patterns_wellformed function in tasks/build.py.

    check_patterns_wellformed checks that pattern entries read from configuration are
    well-formed dicts with string 'key'/'value' fields. The rules differ
    slightly between jobargs and submitargs:
    - jobargs entries require both 'key' and 'value' to be strings
    - submitargs entries require only 'value' to be a string (no 'key' field)
    Invalid entries are silently dropped. A warning is logged for any entry
    whose 'value' is '.*' (matches anything), but the entry is still kept.
    """

    def test_valid_patterns_pass_through(self):
        from tasks.build import check_patterns_wellformed
        result = check_patterns_wellformed(
            [{"key": "SKIP_.*", "value": "yes|no"}], "allowed_jobargs"
        )
        assert len(result) == 1

    def test_non_dict_entry_dropped(self):
        # For submitargs only the 'value' field is validated (no 'key' required).
        from tasks.build import check_patterns_wellformed
        result = check_patterns_wellformed(["notadict", {"value": "ok"}], "allowed_submitargs")
        assert len(result) == 1

    def test_non_string_value_dropped(self):
        # 123 is not a valid value because 'value' must be a string (regex
        # pattern), not an integer.
        from tasks.build import check_patterns_wellformed
        result = check_patterns_wellformed([{"value": 123}], "allowed_submitargs")
        assert len(result) == 0

    def test_non_string_key_dropped(self):
        from tasks.build import check_patterns_wellformed
        result = check_patterns_wellformed([{"key": 123, "value": "ok"}], "allowed_jobargs")
        assert len(result) == 0

    def test_non_list_returns_empty(self):
        from tasks.build import check_patterns_wellformed
        assert check_patterns_wellformed("notalist", "allowed_jobargs") == []

    def test_get_allowed_args_drops_invalid_config_entries(self):
        # Config contains three entries: a valid dict, a bare string (not a
        # dict), and a dict with a non-string value (123 is an int, not a
        # regex string). Only the first entry should survive validation.
        from tasks.build import get_allowed_args
        import json
        import configparser
        cfg = configparser.ConfigParser()
        cfg["buildenv"] = {
            "allowed_submitargs": json.dumps([{"value": "--time=.*"}, "badentry", {"value": 123}]),
        }
        result = get_allowed_args(cfg, "allowed_submitargs")
        assert len(result) == 1
        assert result[0]["value"] == "--time=.*"
