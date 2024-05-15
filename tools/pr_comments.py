# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Bob Droege (@bedroge)
# author: Kenneth Hoste (@boegel)
# author: Hafsa Naeem (@hafsa-naeem)
# author: Jonas Qvigstad (@jonas-lq)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
from collections import namedtuple
import re

# Third party imports (anything installed into the local Python environment)
from pyghee.utils import log
from retry import retry
from retry.api import retry_call

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from connections import github


PRComment = namedtuple('PRComment', ('repo_name', 'pr_number', 'pr_comment_id'))


def create_comment(repo_name, pr_number, comment):
    """
    Create a comment to a pull request on GitHub

    Args:
        repo_name (string): name of the repository
        pr_number (int): number of the pull request within the repository
        comment (string): comment body

    Returns:
        github.IssueComment.IssueComment instance or None (note, github refers to
            PyGithub, not the github from the internal connections module)
    """
    gh = github.get_instance()
    repo = gh.get_repo(repo_name)
    pull_request = repo.get_pull(pr_number)
    return pull_request.create_issue_comment(comment)


def determine_issue_comment(pull_request, pr_comment_id, search_pattern=None):
    """
    Determine issue comment for a given id or using a search pattern.

    Args:
        pull_request (github.PullRequest.PullRequest): instance representing the pull request
        pr_comment_id (int): number of the comment to the pull request to be returned
        search_pattern (string): pattern used to determine the comment to the pull request to be returned

    Returns:
        github.IssueComment.IssueComment instance or None (note, github refers to
            PyGithub, not the github from the internal connections module)
    """

    if pr_comment_id != -1:
        return pull_request.get_issue_comment(pr_comment_id)
    else:
        # use search pattern to determine issue comment
        return get_comment(pull_request, search_pattern)


@retry(Exception, tries=5, delay=1, backoff=2, max_delay=30)
def get_comment(pr, search_pattern):
    """
    Determine instance for comment to a pull request using a search pattern

    Args:
        pr (github.PullRequest.PullRequest): instance representing the pull
            request that is searched for a comment
        search_pattern (string): search pattern to identify comment

    Returns:
        github.IssueComment.IssueComment instance or None (note, github refers to
            PyGithub, not the github from the internal connections module)
    """
    comments = pr.get_issue_comments()
    for comment in comments:
        cms = f".*{search_pattern}.*"
        comment_match = re.search(cms, comment.body)
        if comment_match:
            return comment

    return None


# Note, no @retry decorator used here because it is already used with get_comment.
def get_submitted_job_comment(pr, job_id):
    """
    Determine instance for comment to a pull request using the id of a submitted
    job

    Args:
        pr (github.PullRequest.PullRequest): instance representing the pull
            request that is searched for a comment
        job_id (string): job id of submitted job

    Returns:
        github.IssueComment.IssueComment instance or None (note, github refers to
            PyGithub, not the github from the internal connections module)
    """
    # NOTE adjust search string if format changed by event
    #      handler (separate process running
    #      eessi_bot_event_handler.py)
    job_search_pattern = f"submitted.*job id `{job_id}`"
    return get_comment(pr, job_search_pattern)


def update_comment(cmnt_id, pr, update, log_file=None):
    """
    Update a comment to a pull request

    Args:
        cmnt_id (int): id of the comment to be updated
        pr (github.PullRequest.PullRequest): instance representing the pull
            request the comment to be updated belongs to
        update (string): update to be added to the existing comment
        log_file (string): path to log file

    Returns:
        None (implicitly)
    """
    issue_comment = retry_call(pr.get_issue_comment, fargs=[cmnt_id], exceptions=Exception,
                               tries=5, delay=1, backoff=2, max_delay=30)
    if issue_comment:
        retry_call(issue_comment.edit, fargs=[issue_comment.body + update], exceptions=Exception,
                   tries=5, delay=1, backoff=2, max_delay=30)
    else:
        log(f"no comment with id {cmnt_id}, skipping update '{update}'",
            log_file=log_file)


def update_pr_comment(event_info, update):
    """
    Updates a comment to a pull request determined from an issue_comment event.

    Args:
        event_info (dict): storing all information of an event
        update (string): update to be added to the comment associated with the event

    Returns:
        None (implicitly)
    """
    request_body = event_info['raw_request_body']
    if 'issue' not in request_body:
        log("event is not an issue_comment; cannot update the comment")
        return
    comment_new = request_body['comment']['body']
    repo_name = request_body['repository']['full_name']
    pr_number = int(request_body['issue']['number'])
    issue_id = int(request_body['comment']['id'])

    gh = github.get_instance()
    repo = gh.get_repo(repo_name)
    pull_request = repo.get_pull(pr_number)
    issue_comment = pull_request.get_issue_comment(issue_id)
    issue_comment.edit(comment_new + update)
