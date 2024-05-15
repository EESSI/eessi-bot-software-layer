# Tests for functions defined in 'tools/pr_comments.py' of the EESSI
# build-and-deploy bot, see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Kenneth Hoste (@boegel)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
import os
import re
from unittest.mock import patch

# Third party imports (anything installed into the local Python environment)
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools.pr_comments import (
    get_comment, get_submitted_job_comment, update_comment)


class MockIssueComment:
    def __init__(self, body, edit_raises='0', edit_exception=Exception, comment_id=1):
        self.body = body
        self.edit_raises = edit_raises
        self.edit_exception = edit_exception
        self.edit_call_count = 0
        self.id = comment_id

    def edit(self, body):
        def should_raise_exception():
            """
            Determine whether or not an exception should be raised, based on value
            of $TEST_RAISE_EXCEPTION
            0: don't raise exception, return value as expected (call succeeds)
            >0: decrease value by one, raise exception (call fails, retry may succeed)
            always_raise: raise exception (call fails always)
            get_issue_comments -> GetIssueCommentsException
            """
            should_raise = False

            count_regex = re.compile('^[0-9]+$')

            if self.edit_raises == 'always_raise':
                should_raise = True
            # if self.edit_raises is a number, raise exception when > 0 and
            # decrement with 1
            elif count_regex.match(self.edit_raises):
                if int(self.edit_raises) > 0:
                    should_raise = True
                    self.edit_raises = str(int(self.edit_raises) - 1)

            return should_raise

        def no_sleep_after_edit(delay):
            print(f"issue_comment.edit failed - sleeping {delay} s (mocked)")

        self.edit_call_count = self.edit_call_count + 1
        with patch('retry.api.time.sleep') as mock_sleep:
            mock_sleep.side_effect = no_sleep_after_edit

            if should_raise_exception():
                raise self.edit_exception

            self.body = body


class GetIssueCommentsException(Exception):
    "Raised when pr.get_issue_comments fails in a test."
    pass


class GetIssueCommentException(Exception):
    "Raised when pr.get_issue_comment fails in a test."
    pass


class IssueCommentEditException(Exception):
    "Raised when issue_comment.edit fails in a test."
    pass


@pytest.fixture
def pr_with_no_comments():
    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance = mock_pr.return_value
        instance.get_issue_comments.return_value = ()
        yield instance


@pytest.fixture
def pr_with_any_comment():
    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance = mock_pr.return_value
        instance.issue_comments = [MockIssueComment("foo")]
        instance.get_issue_comments.return_value = instance.issue_comments
        yield instance


@pytest.fixture
def pr_with_job_comment():
    issue_comments = [MockIssueComment("submitted ... job id `42`")]
    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance = mock_pr.return_value
        instance.get_issue_comments.return_value = issue_comments
        yield instance


@pytest.fixture
def pr_any_get_comment_retry():

    issue_comments = [MockIssueComment("foo")]

    def should_raise_exception():
        """
        Determine whether or not an exception should be raised, based on value
        of $TEST_RAISE_EXCEPTION
        0: don't raise exception, return value as expected (call succeeds)
        >0: decrease value by one, raise exception (call fails, retry may succeed)
        always_raise: raise exception (call fails always)
        get_issue_comments -> GetIssueCommentsException
        """
        should_raise = False

        test_raise_exception = os.getenv('TEST_RAISE_EXCEPTION')
        count_regex = re.compile('^[0-9]+$')

        if test_raise_exception == 'always_raise':
            should_raise = True
        # if $TEST_RAISE_EXCEPTION is a number, raise exception when > 0 and
        # decrement with 1
        elif count_regex.match(test_raise_exception):
            test_raise_exception = int(test_raise_exception)
            if test_raise_exception > 0:
                should_raise = True
                os.environ['TEST_RAISE_EXCEPTION'] = str(test_raise_exception - 1)

        return should_raise

    def get_issue_comments_maybe_raise_exception():
        if should_raise_exception():
            raise GetIssueCommentsException

        return issue_comments

    def no_sleep_really(delay):
        print(f"    get_issue_comments failed - sleeping {delay} s (mocked)")

    with patch('github.PullRequest.PullRequest') as mock_pr, \
            patch('retry.api.time.sleep') as mock_sleep:
        instance = mock_pr.return_value
        instance.get_issue_comments.side_effect = get_issue_comments_maybe_raise_exception
        mock_sleep.side_effect = no_sleep_really

        yield instance


@pytest.fixture
def pr_job_get_comment_retry():

    issue_comments = [MockIssueComment("submitted ... job id `42`")]

    def should_raise_exception():
        """
        Determine whether or not an exception should be raised, based on value
        of $TEST_RAISE_EXCEPTION
        0: don't raise exception, return value as expected (call succeeds)
        >0: decrease value by one, raise exception (call fails, retry may succeed)
        always_raise: raise exception (call fails always)
        get_issue_comments -> GetIssueCommentsException
        """
        should_raise = False

        test_raise_exception = os.getenv('TEST_RAISE_EXCEPTION')
        count_regex = re.compile('^[0-9]+$')

        if test_raise_exception == 'always_raise':
            should_raise = True
        # if $TEST_RAISE_EXCEPTION is a number, raise exception when > 0 and
        # decrement with 1
        elif count_regex.match(test_raise_exception):
            test_raise_exception = int(test_raise_exception)
            if test_raise_exception > 0:
                should_raise = True
                os.environ['TEST_RAISE_EXCEPTION'] = str(test_raise_exception - 1)

        return should_raise

    def get_issue_comments_maybe_raise_exception():
        if should_raise_exception():
            raise GetIssueCommentsException

        return issue_comments

    def no_sleep_really(delay):
        print(f"    get_issue_comments failed - sleeping {delay} s (mocked)")

    with patch('github.PullRequest.PullRequest') as mock_pr, \
            patch('retry.api.time.sleep') as mock_sleep:
        instance = mock_pr.return_value
        instance.get_issue_comments.side_effect = get_issue_comments_maybe_raise_exception
        mock_sleep.side_effect = no_sleep_really

        yield instance


@pytest.fixture
def issue_comment_edit_calls_fail_or_succeed():

    def should_raise_exception():
        """
        Determine whether or not an exception should be raised, based on value
        of $TEST_RAISE_EXCEPTION
        0: don't raise exception, return value as expected (call succeeds)
        >0: decrease value by one, raise exception (call fails, retry may succeed)
        always_raise: raise exception (call fails always)
        edit(str + str) -> IssueCommentEditException
        edit(str + int) -> TypeError
        """
        should_raise = False

        test_raise_exception = os.getenv('TEST_RAISE_EXCEPTION')
        count_regex = re.compile('^[0-9]+$')

        if test_raise_exception == 'always_raise':
            should_raise = True
        # if $TEST_RAISE_EXCEPTION is a number, raise exception when > 0 and
        # decrement with 1
        elif count_regex.match(test_raise_exception):
            test_raise_exception = int(test_raise_exception)
            if test_raise_exception > 0:
                should_raise = True
                os.environ['TEST_RAISE_EXCEPTION'] = str(test_raise_exception - 1)

        return should_raise

    def edit_maybe_raise_exception(arg):
        if should_raise_exception():
            raise IssueCommentEditException

        return None

    def no_sleep_really(delay):
        print(f"issue_comment.edit failed - sleeping {delay} s (mocked)")

    with patch('tests.test_tools_pr_comments.MockIssueComment') as mock_ic, \
            patch('retry.api.time.sleep') as mock_sleep:
        instance = mock_ic.return_value
        instance.edit.side_effect = edit_maybe_raise_exception
        mock_sleep.side_effect = no_sleep_really

        yield instance


@pytest.fixture
def issue_edit_first_call_succeeds():

    def should_raise_exception():
        """
        Determine whether or not an exception should be raised, based on value
        of $TEST_RAISE_EXCEPTION
        0: don't raise exception, return value as expected (call succeeds)
        >0: decrease value by one, raise exception (call fails, retry may succeed)
        always_raise: raise exception (call fails always)
        get_issue_comment -> GetIssueCommentException
        """
        should_raise = False

        test_raise_exception = os.getenv('TEST_RAISE_EXCEPTION')
        count_regex = re.compile('^[0-9]+$')

        if test_raise_exception == 'always_raise':
            should_raise = True
        # if $TEST_RAISE_EXCEPTION is a number, raise exception when > 0 and
        # decrement with 1
        elif count_regex.match(test_raise_exception):
            test_raise_exception = int(test_raise_exception)
            if test_raise_exception > 0:
                should_raise = True
                os.environ['TEST_RAISE_EXCEPTION'] = str(test_raise_exception - 1)

        return should_raise

    def get_issue_comment_maybe_raise_exception(cmnt_id):
        if should_raise_exception():
            raise GetIssueCommentException

        return instance.issue_comments[0]

    def do_not_sleep_really(delay):
        print(f"edit_first_call_succeeds - retry - sleeping {delay} s (mocked)")

    with patch('github.PullRequest.PullRequest') as mock_pr, \
            patch('retry.api.time.sleep') as mock_sleep:
        instance = mock_pr.return_value
        instance.get_issue_comment.side_effect = get_issue_comment_maybe_raise_exception
        instance.issue_comments = [
                MockIssueComment("foo",
                                 edit_raises='0',
                                 edit_exception=IssueCommentEditException)]
        mock_sleep.side_effect = do_not_sleep_really

        yield instance


@pytest.fixture
def issue_edit_second_call_succeeds():

    def should_raise_exception():
        """
        Determine whether or not an exception should be raised, based on value
        of $TEST_RAISE_EXCEPTION
        0: don't raise exception, return value as expected (call succeeds)
        >0: decrease value by one, raise exception (call fails, retry may succeed)
        always_raise: raise exception (call fails always)
        get_issue_comment -> GetIssueCommentException
        """
        should_raise = False

        test_raise_exception = os.getenv('TEST_RAISE_EXCEPTION')
        count_regex = re.compile('^[0-9]+$')

        if test_raise_exception == 'always_raise':
            should_raise = True
        # if $TEST_RAISE_EXCEPTION is a number, raise exception when > 0 and
        # decrement with 1
        elif count_regex.match(test_raise_exception):
            test_raise_exception = int(test_raise_exception)
            if test_raise_exception > 0:
                should_raise = True
                os.environ['TEST_RAISE_EXCEPTION'] = str(test_raise_exception - 1)

        return should_raise

    def get_issue_comment_maybe_raise_exception(cmnt_id):
        if should_raise_exception():
            raise GetIssueCommentException

        return instance.issue_comments[0]

    def do_not_sleep_really(delay):
        print(f"edit_second_call_succeeds - retry - sleeping {delay} s (mocked)")

    with patch('github.PullRequest.PullRequest') as mock_pr, \
            patch('retry.api.time.sleep') as mock_sleep:
        instance = mock_pr.return_value
        instance.get_issue_comment.side_effect = get_issue_comment_maybe_raise_exception
        mock_sleep.side_effect = do_not_sleep_really
        instance.issue_comments = [
                MockIssueComment("foo",
                                 edit_raises='1',
                                 edit_exception=IssueCommentEditException)]

        yield instance


@pytest.fixture
def issue_edit_five_calls_fail():

    def should_raise_exception():
        """
        Determine whether or not an exception should be raised, based on value
        of $TEST_RAISE_EXCEPTION
        0: don't raise exception, return value as expected (call succeeds)
        >0: decrease value by one, raise exception (call fails, retry may succeed)
        always_raise: raise exception (call fails always)
        get_issue_comment -> GetIssueCommentException
        """
        should_raise = False

        test_raise_exception = os.getenv('TEST_RAISE_EXCEPTION')
        count_regex = re.compile('^[0-9]+$')

        if test_raise_exception == 'always_raise':
            should_raise = True
        # if $TEST_RAISE_EXCEPTION is a number, raise exception when > 0 and
        # decrement with 1
        elif count_regex.match(test_raise_exception):
            test_raise_exception = int(test_raise_exception)
            if test_raise_exception > 0:
                should_raise = True
                os.environ['TEST_RAISE_EXCEPTION'] = str(test_raise_exception - 1)

        return should_raise

    def get_issue_comment_maybe_raise_exception(cmnt_id):
        if should_raise_exception():
            raise GetIssueCommentException

        return instance.issue_comments[0]

    def do_not_sleep_really(delay):
        print(f"edit_five_calls_fail - retry - sleeping {delay} s (mocked)")

    with patch('github.PullRequest.PullRequest') as mock_pr, \
            patch('retry.api.time.sleep') as mock_sleep:
        instance = mock_pr.return_value
        instance.get_issue_comment.side_effect = get_issue_comment_maybe_raise_exception
        mock_sleep.side_effect = do_not_sleep_really
        instance.issue_comments = [
                MockIssueComment("foo",
                                 edit_raises='5',
                                 edit_exception=IssueCommentEditException)]

        yield instance


@pytest.fixture
def issue_edit_all_calls_fail():

    def should_raise_exception():
        """
        Determine whether or not an exception should be raised, based on value
        of $TEST_RAISE_EXCEPTION
        0: don't raise exception, return value as expected (call succeeds)
        >0: decrease value by one, raise exception (call fails, retry may succeed)
        always_raise: raise exception (call fails always)
        get_issue_comment -> GetIssueCommentException
        """
        should_raise = False

        test_raise_exception = os.getenv('TEST_RAISE_EXCEPTION')
        count_regex = re.compile('^[0-9]+$')

        if test_raise_exception == 'always_raise':
            should_raise = True
        # if $TEST_RAISE_EXCEPTION is a number, raise exception when > 0 and
        # decrement with 1
        elif count_regex.match(test_raise_exception):
            test_raise_exception = int(test_raise_exception)
            if test_raise_exception > 0:
                should_raise = True
                os.environ['TEST_RAISE_EXCEPTION'] = str(test_raise_exception - 1)

        return should_raise

    def get_issue_comment_maybe_raise_exception(cmnt_id):
        if should_raise_exception():
            raise GetIssueCommentException

        return instance.issue_comments[0]

    def do_not_sleep_really(delay):
        print(f"edit_always_fails - retry - sleeping {delay} s (mocked)")

    with patch('github.PullRequest.PullRequest') as mock_pr, \
            patch('retry.api.time.sleep') as mock_sleep:
        instance = mock_pr.return_value
        instance.get_issue_comment.side_effect = get_issue_comment_maybe_raise_exception
        mock_sleep.side_effect = do_not_sleep_really
        instance.issue_comments = [
                MockIssueComment("foo",
                                 edit_raises='always_raise',
                                 edit_exception=IssueCommentEditException)]

        yield instance


# tests for get_comment
# cases Ax:
#  - A1: no comment exist
#  - A2: search string should be found
#  - A3: search string should not be found
#  - A4: calling get_issue_comments raises an Exception


# case A1: no comment exist
def test_get_comment_no_comment(pr_with_no_comments):
    expected = None
    actual = get_comment(pr_with_no_comments, "foo")
    assert expected == actual


# case A2: search string should be found
def test_get_comment_found(pr_with_any_comment):
    expected = MockIssueComment("foo").body
    actual = get_comment(pr_with_any_comment, "foo").body
    assert expected == actual


# case A3: search string should not be found
def test_get_comment_not_found(pr_with_any_comment):
    expected = None
    actual = get_comment(pr_with_any_comment, "bar")
    assert expected == actual


# case A4: calling get_issue_comments raises an Exception
#   sub cases: always raises exception, raises exception ones,
#              raises exception N times (N > tries)
def test_get_comment_retry(pr_any_get_comment_retry):
    # test whether get_comment retries multiple times when problems occur
    #   when getting the comment;
    # start with specifying that getting the comment should always fail
    print("get_comment: always fail")
    os.environ['TEST_RAISE_EXCEPTION'] = 'always_raise'
    with pytest.raises(Exception) as err:
        get_comment(pr_any_get_comment_retry, "foo")
    assert err.type == GetIssueCommentsException

    # getting comment should succeed on 2nd try (fail once)
    print("get_comment: fail once")
    os.environ['TEST_RAISE_EXCEPTION'] = '1'
    expected = "foo"
    actual = get_comment(pr_any_get_comment_retry, "foo").body
    assert expected == actual

    # getting comment should fail 5 times, and get_comment only retries twice,
    # so get_comment should fail with exception
    print("get_comment: fail 5 times")
    os.environ['TEST_RAISE_EXCEPTION'] = '5'
    with pytest.raises(Exception) as err:
        get_comment(pr_any_get_comment_retry, "foo")
    assert err.type == GetIssueCommentsException


# tests for get_submitted_job_comment
# cases: same as/similar for get_comment (because get_submitted_job_comment is
#   just a wrapper around get_comment)
# cases Bx:
#  - B1: no comment exist
#  - B2: searched jobid should be found
#  - B3: searched jobid should not be found
#  - B4: calling get_comment raises an Exception


# case B1: no comment exist
def test_get_submitted_job_comment_no_comment(pr_with_no_comments):
    expected = None
    actual = get_submitted_job_comment(pr_with_no_comments, -1)
    assert expected == actual


# case B2: searched jobid should be found
def test_get_submitted_job_comment_found(pr_with_job_comment):
    expected = MockIssueComment("submitted ... job id `42`").body
    actual = get_submitted_job_comment(pr_with_job_comment, 42).body
    assert expected == actual


# case B3: searched jobid should not be found
def test_get_submitted_job_comment_not_found(pr_with_job_comment):
    expected = None
    actual = get_submitted_job_comment(pr_with_job_comment, 33)
    assert expected == actual


# case B4: calling get_comment raises an Exception
#   sub cases: always raises exception, raises exception ones,
#              raises exception N times (N > tries)
def test_get_submitted_job_comment_retry(pr_job_get_comment_retry):
    # test whether get_comment retries multiple times when problems occur
    #   when getting the comment;
    # start with specifying that getting the comment should always fail
    print("get_submitted_job_comment: always fail")
    os.environ['TEST_RAISE_EXCEPTION'] = 'always_raise'
    with pytest.raises(Exception) as err:
        get_submitted_job_comment(pr_job_get_comment_retry, 42)
    assert err.type == GetIssueCommentsException

    # getting comment should succeed on 2nd try (fail once)
    print("get_submitted_job_comment: fail once")
    os.environ['TEST_RAISE_EXCEPTION'] = '1'
    expected = "submitted ... job id `42`"
    actual = get_submitted_job_comment(pr_job_get_comment_retry, 42).body
    assert expected == actual

    # getting comment should fail 5 times, and get_comment only retries twice,
    # so get_comment should fail with exception
    print("get_submitted_job_comment: fail 5 times")
    os.environ['TEST_RAISE_EXCEPTION'] = '5'
    with pytest.raises(Exception) as err:
        get_submitted_job_comment(pr_job_get_comment_retry, 42)
    assert err.type == GetIssueCommentsException


# tests for update_comment
# cases:
#  - pr.get_issue_comment(cmnt_id): 1st None ==> no edit
#      (patching pr.get_issue_comment via ContextManager to return None)
#
#  - pr.get_issue_comment(cmnt_id): 1st !None
#      (TEST_RAISE_EXCEPTION='0')
#    ==> edit: 1st succeeds
#          (edit_raises='0')
#      update_comment called with (str)
#
#  - pr.get_issue_comment(cmnt_id): 1st !None
#      (TEST_RAISE_EXCEPTION='0')
#    ==> edit: 1st-(N-1)th fail(err1), 2nd-Nth succeeds
#          (edit_raises='1')
#      update_comment called with (str)
#
#  - pr.get_issue_comment(cmnt_id): 1st !None
#      (TEST_RAISE_EXCEPTION='0')
#    ==> edit: 1st-Nth fail(err1)
#          (edit_raises='N') or
#          (edit_raises='always_raise')
#      update_comment called with (str)
#
#  - SKIPPED pr.get_issue_comment(cmnt_id): 1st !None
#      (TEST_RAISE_EXCEPTION='0')
#    ==> edit: always fails (err2)
#      update_comment called with (int)
#
#  - pr.get_issue_comment(cmnt_id): 1st-Nth fail(err0) ==> no edit
#      (TEST_RAISE_EXCEPTION='N')
#      (TEST_RAISE_EXCEPTION='always_raise')
#
#  - pr.get_issue_comment(cmnt_id): 1st-(N-1)th fail(err0), Nth !None
#      (TEST_RAISE_EXCEPTION='1')
#    ==> edit: 1st succeeds
#          (edit_raises='0')
#      update_comment called with (str)
#
#  - pr.get_issue_comment(cmnt_id): 1st-(N-1)th fail(err0), Nth !None
#      (TEST_RAISE_EXCEPTION='1')
#    ==> edit: 1st-(N-1)th fail(err1), 2nd-Nth succeeds
#          (edit_raises='1')
#      update_comment called with (str)
#
#  - pr.get_issue_comment(cmnt_id): 1st-(N-1)th fail(err0), Nth !None
#      (TEST_RAISE_EXCEPTION='1')
#    ==> edit: 1st-Nth fail(err1)
#          (edit_raises='N') or
#          (edit_raises='always_raise')
#      update_comment called with (str)
#  Note, no need to repeat always failing(err2) edit. Plus it does not seem to be
#  easy to test for TypeError of arguments in string concatenation when one
#  operand is of type MockObject.
#

#  - pr.get_issue_comment(cmnt_id): 1st None ==> no edit
#      (patching pr.get_issue_comment via ContextManager to return None)
def test_update_comment_none(tmpdir):
    log_file = os.path.join(tmpdir, "log.txt")

    with patch('github.PullRequest.PullRequest') as mock_pr:
        instance = mock_pr.return_value
        instance.get_issue_comment.return_value = None

        cmnt_id = 0
        update = "body-0"
        update_comment(cmnt_id, instance, update, log_file=log_file)

        # log_file should exists
        assert os.path.exists(log_file)

        # log_file should contain error message ""
        expected = f"no comment with id {cmnt_id}, skipping update '{update}'"
        file = tmpdir.join("log.txt")
        actual = file.read()
        # actual log message starts with a timestamp, hence we use 'in'
        assert expected in actual


#  - pr.get_issue_comment(cmnt_id): 1st !None
#      (TEST_RAISE_EXCEPTION='0')
#    ==> edit: 1st succeeds
#          (edit_raises='0')
#      update_comment called with (str)
def test_update_comment_first_edit_succeeds(issue_edit_first_call_succeeds):
    # issue_edit_first_call_succeeds provides one comment with "foo"
    os.environ['TEST_RAISE_EXCEPTION'] = '0'
    update_comment(0, issue_edit_first_call_succeeds, "-update")
    expected = "foo-update"
    actual = issue_edit_first_call_succeeds.issue_comments[0].body
    assert expected == actual


#  - pr.get_issue_comment(cmnt_id): 1st !None
#      (TEST_RAISE_EXCEPTION='0')
#    ==> edit: 1st-(N-1)th fail(err1), 2nd-Nth succeeds
#          (edit_raises='1')
#      update_comment called with (str)
def test_update_comment_second_edit_succeeds(issue_edit_second_call_succeeds):
    # issue_edit_second_call_succeeds provides one comment with "foo"
    os.environ['TEST_RAISE_EXCEPTION'] = '0'
    update_comment(0, issue_edit_second_call_succeeds, "-update")
    expected = "foo-update"
    actual = issue_edit_second_call_succeeds.issue_comments[0].body
    assert expected == actual


#  - pr.get_issue_comment(cmnt_id): 1st !None
#      (TEST_RAISE_EXCEPTION='0')
#    ==> edit: 1st-Nth fail(err1)
#          (edit_raises='N') or
#          (edit_raises='always_raise')
#      update_comment called with (str)
def test_update_comment_five_edit_fail(tmpdir, issue_edit_five_calls_fail):
    log_file = os.path.join(tmpdir, "log.txt")
    # issue_edit_five_calls_fail provides one comment with "foo"
    os.environ['TEST_RAISE_EXCEPTION'] = '0'
    with pytest.raises(IssueCommentEditException):
        update_comment(0, issue_edit_five_calls_fail, "-update", log_file=log_file)

    # log_file should not exists
    assert not os.path.exists(log_file)

    # check that body has not been updated
    expected = "foo"
    actual = issue_edit_five_calls_fail.issue_comments[0].body
    assert expected == actual

    # check if edit function was called 5 times
    expected = 5
    actual = issue_edit_five_calls_fail.issue_comments[0].edit_call_count
    assert expected == actual


def test_update_comment_all_edit_fail(tmpdir, issue_edit_all_calls_fail):
    log_file = os.path.join(tmpdir, "log.txt")
    # issue_edit_all_calls_fail provides one comment with "foo"
    os.environ['TEST_RAISE_EXCEPTION'] = '0'
    with pytest.raises(IssueCommentEditException):
        update_comment(0, issue_edit_all_calls_fail, "-update", log_file=log_file)

    # log_file should not exists
    assert not os.path.exists(log_file)

    # check that body has not been updated
    expected = "foo"
    actual = issue_edit_all_calls_fail.issue_comments[0].body
    assert expected == actual

    # check if edit function was called 5 times
    expected = 5
    actual = issue_edit_all_calls_fail.issue_comments[0].edit_call_count
    assert expected == actual


# SKIP this test: update_comment concatenates the update (42) to the current
# body which is a MockObject. It doesn't raise a TypeError as we would expect
# in a real scenario where the current body is of type str.
#  - pr.get_issue_comment(cmnt_id): 1st !None
#      (TEST_RAISE_EXCEPTION='0')
#    ==> edit: always fails (err2)
#      update_comment called with (int)
# def test_update_comment_edit_type_error(tmpdir, pr_with_any_comment):
#     log_file = os.path.join(tmpdir, "log.txt")
#     # pr_with_any_comment provides one comment with "foo"
#     os.environ['TEST_RAISE_EXCEPTION'] = '0'
#     #with pytest.raises(Exception) as err:
#     update_comment(0, pr_with_any_comment, 42, log_file=log_file)
#
#     # we expect a TypeError
#     #print(f"err.type = {err.type}")
#     #assert err.type == TypeError
#
#     # log_file should not exists
#     assert not os.path.exists(log_file)
#
#     # check that body has not been updated
#     expected = "foo"
#     actual = pr_with_any_comment.issue_comments[0].body
#     assert expected == actual


#  - pr.get_issue_comment(cmnt_id): 1st-Nth fail(err0) ==> no edit
#      (TEST_RAISE_EXCEPTION='N')
def test_update_comment_five_get_issue_comment_fail(tmpdir, issue_edit_five_calls_fail):
    log_file = os.path.join(tmpdir, "log.txt")
    # issue_edit_five_calls_fail just provides retry testing for
    # get_issue_comment
    # since all calls to this shall fail, we don't use the edit part here
    os.environ['TEST_RAISE_EXCEPTION'] = '5'
    with pytest.raises(GetIssueCommentException):
        update_comment(0, issue_edit_five_calls_fail, "-update", log_file=log_file)

    # log_file should not exists
    assert not os.path.exists(log_file)

    # check that body has not been updated
    expected = "foo"
    actual = issue_edit_five_calls_fail.issue_comments[0].body
    assert expected == actual

    # check if get_issue_comment function was called 5 times
    expected = 5
    actual = issue_edit_five_calls_fail.get_issue_comment.call_count
    assert expected == actual


#  - pr.get_issue_comment(cmnt_id): 1st-Nth fail(err0) ==> no edit
#      (TEST_RAISE_EXCEPTION='always_raise')
def test_update_comment_all_get_issue_comment_fail(tmpdir, issue_edit_all_calls_fail):
    log_file = os.path.join(tmpdir, "log.txt")
    # issue_edit_all_calls_fail just provides retry testing for
    # get_issue_comment
    # since all calls to this shall fail, we don't use the edit part here
    os.environ['TEST_RAISE_EXCEPTION'] = 'always_raise'
    with pytest.raises(GetIssueCommentException):
        update_comment(0, issue_edit_all_calls_fail, "-update", log_file=log_file)

    # log_file should not exists
    assert not os.path.exists(log_file)

    # check that body has not been updated
    expected = "foo"
    actual = issue_edit_all_calls_fail.issue_comments[0].body
    assert expected == actual

    # check if get_issue_comment function was called 5 times
    expected = 5
    actual = issue_edit_all_calls_fail.get_issue_comment.call_count
    assert expected == actual


#  - pr.get_issue_comment(cmnt_id): 1st-(N-1)th fail(err0), Nth !None
#      (TEST_RAISE_EXCEPTION='1')
#    ==> edit: 1st succeeds
#          (edit_raises='0')
#      update_comment called with (str)
def test_update_comment_second_get_call_first_edit(tmpdir, issue_edit_first_call_succeeds):
    log_file = os.path.join(tmpdir, "log.txt")
    os.environ['TEST_RAISE_EXCEPTION'] = '1'
    update_comment(0, issue_edit_first_call_succeeds, "-update", log_file=log_file)

    # log_file should not exists
    assert not os.path.exists(log_file)

    # check that body has been updated
    expected = "foo-update"
    actual = issue_edit_first_call_succeeds.issue_comments[0].body
    assert expected == actual

    # check if get_issue_comment function was called 2 times
    expected = 2
    actual = issue_edit_first_call_succeeds.get_issue_comment.call_count
    assert expected == actual

    # check if edit function was called once
    expected = 1
    actual = issue_edit_first_call_succeeds.issue_comments[0].edit_call_count
    assert expected == actual


#  - pr.get_issue_comment(cmnt_id): 1st-(N-1)th fail(err0), Nth !None
#      (TEST_RAISE_EXCEPTION='1')
#    ==> edit: 1st-(N-1)th fail(err1), 2nd-Nth succeeds
#          (edit_raises='1')
#      update_comment called with (str)
def test_update_comment_second_get_call_second_edit(tmpdir, issue_edit_second_call_succeeds):
    log_file = os.path.join(tmpdir, "log.txt")
    os.environ['TEST_RAISE_EXCEPTION'] = '1'
    update_comment(0, issue_edit_second_call_succeeds, "-update", log_file=log_file)

    # log_file should not exists
    assert not os.path.exists(log_file)

    # check that body has been updated
    expected = "foo-update"
    actual = issue_edit_second_call_succeeds.issue_comments[0].body
    assert expected == actual

    # check if get_issue_comment function was called 2 times
    expected = 2
    actual = issue_edit_second_call_succeeds.get_issue_comment.call_count
    assert expected == actual

    # check if edit function was called 2 times
    expected = 2
    actual = issue_edit_second_call_succeeds.issue_comments[0].edit_call_count
    assert expected == actual


#  - pr.get_issue_comment(cmnt_id): 1st-(N-1)th fail(err0), Nth !None
#      (TEST_RAISE_EXCEPTION='1')
#    ==> edit: 1st-Nth fail(err1)
#          (edit_raises='N') or
#      update_comment called with (str)
def test_update_comment_second_get_call_five_edits_fail(tmpdir, issue_edit_five_calls_fail):
    log_file = os.path.join(tmpdir, "log.txt")
    os.environ['TEST_RAISE_EXCEPTION'] = '1'
    with pytest.raises(IssueCommentEditException):
        update_comment(0, issue_edit_five_calls_fail, "-update", log_file=log_file)

    # log_file should not exists
    assert not os.path.exists(log_file)

    # check that body has NOT been updated
    expected = "foo"
    actual = issue_edit_five_calls_fail.issue_comments[0].body
    assert expected == actual

    # check if get_issue_comment function was called 2 times
    expected = 2
    actual = issue_edit_five_calls_fail.get_issue_comment.call_count
    assert expected == actual

    # check if edit function was called 5 times
    expected = 5
    actual = issue_edit_five_calls_fail.issue_comments[0].edit_call_count
    assert expected == actual


#  - pr.get_issue_comment(cmnt_id): 1st-(N-1)th fail(err0), Nth !None
#      (TEST_RAISE_EXCEPTION='1')
#    ==> edit: 1st-Nth fail(err1)
#          (edit_raises='always_raise')
#      update_comment called with (str)
def test_update_comment_second_get_call_all_edits_fail(tmpdir, issue_edit_all_calls_fail):
    log_file = os.path.join(tmpdir, "log.txt")
    os.environ['TEST_RAISE_EXCEPTION'] = '1'
    with pytest.raises(IssueCommentEditException):
        update_comment(0, issue_edit_all_calls_fail, "-update", log_file=log_file)

    # log_file should not exists
    assert not os.path.exists(log_file)

    # check that body has NOT been updated
    expected = "foo"
    actual = issue_edit_all_calls_fail.issue_comments[0].body
    assert expected == actual

    # check if get_issue_comment function was called 2 times
    expected = 2
    actual = issue_edit_all_calls_fail.get_issue_comment.call_count
    assert expected == actual

    # check if edit function was called 5 times
    expected = 5
    actual = issue_edit_all_calls_fail.issue_comments[0].edit_call_count
    assert expected == actual
