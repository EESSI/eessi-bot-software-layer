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
# author: Sam Moors (@smoors)
# author: Sondre Bergsvaag Risanger (@sondrebr)
#
# license: GPLv2
#

# Standard library imports
from collections import namedtuple
from enum import Enum
import re
import sys
from typing import Union

# Third party imports (anything installed into the local Python environment)
from pyghee.utils import log
from retry import retry
from retry.api import retry_call

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from connections import github, gitlab
from tools import config
from tools.git import get_git_hosting_platform, GITHUB, GITLAB


PRCommentInfo = namedtuple('PRCommentInfo', ('repo_name', 'pr_number', 'pr_comment_id'))


class ChatLevels(Enum):
    "chattiness levels"
    INCOGNITO = 0
    MINIMAL = 1
    BASIC = 2
    CHATTY = 3


def create_comment(repo_name, pr_number, comment, req_chatlevel):
    """
    Create a comment to a pull request

    Args:
        repo_name (string): name of the repository
        pr_number (int): number of the pull request within the repository
        comment (string): comment body
        req_chatlevel (member of ChatLevels Enum): minimum required chattiness level for creating the PR comment

    Returns:
        PRComment instance or None
    """
    fn = sys._getframe().f_code.co_name

    cfg = config.read_config()
    chatlevel = cfg[config.SECTION_BOT_CONTROL].get(
        config.BOT_CONTROL_SETTING_CHATLEVEL, ChatLevels.BASIC.name).upper()

    if ChatLevels[chatlevel].value >= req_chatlevel.value:
        pr_comment = create_pr_comment_instance(repo_name, pr_number, body=comment)
        pr_comment.create()
        # If 'id' is not set, something went wrong
        if not pr_comment.id:
            return None
        return pr_comment

    else:
        log(f"{fn}(): not creating PR comment: "
            f"chatlevel {ChatLevels[chatlevel].value} < required chatlevel {req_chatlevel.value}")

    return None


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


class BasePRComment():
    """
    Base class to use for handling PR comments, which works differently for GitHub vs. GitLab.
    """
    def __init__(self, repo_name, pr_number, body=None, id=None):
        if self.__class__ is BasePRComment:
            err_msg = "Do not use this base class directly. "
            err_msg += "Please use one of its subclasses instead."
            raise NotImplementedError(err_msg)

        # 'body' should be provided when creating a new comment
        # 'id' should be provided when dealing with an existing comment
        if (body and id) or not (body or id):
            err_msg = "Exactly one of 'body' and 'id' must be "
            err_msg += "set when initializing a comment class."
            raise Exception(err_msg)

        self.body = body
        self.id = id
        self.repo_name = repo_name
        self.pr_number = pr_number
        self._pr_obj = None
        self._comment_obj = None

    @property
    def html_url(self):
        raise NotImplementedError()

    def get(self):
        raise NotImplementedError()

    def create(self):
        raise NotImplementedError()

    def edit(self):
        raise NotImplementedError()

    def append(self):
        raise NotImplementedError()


class GitHubPRComment(BasePRComment):
    """
    PRComment class for use with GitHub.
    """
    def __init__(self, repo_name, pr_number, body=None, id=None):
        super().__init__(repo_name, pr_number, body, id)
        gh = github.get_instance()
        repo = gh.get_repo(self.repo_name)
        self._pr_obj = repo.get_pull(self.pr_number)

    @property
    def html_url(self):
        if self._comment_obj:
            return self._comment_obj.html_url
        return None

    def get(self):
        if not self.id:
            raise Exception("'id' must be set to get a comment.")
        self._comment_obj = retry_call(self._pr_obj.get_issue_comment, fargs=[self.id],
                                       exceptions=Exception, tries=5, delay=1, backoff=2, max_delay=30)
        if self._comment_obj:
            self.body = self._comment_obj.body

    def create(self):
        if not self.body:
            raise Exception("'body' must be set to create a comment.")
        if self.id:
            # Return early if 'id' is set to avoid creating duplicate comments
            return
        self._comment_obj = retry_call(self._pr_obj.create_issue_comment, fargs=[self.body],
                                       exceptions=Exception, tries=3, delay=1, backoff=2, max_delay=10)
        if self._comment_obj:
            self.id = self._comment_obj.id

    def edit(self, new_body):
        if not self.id:
            raise Exception("'id' must be set to edit a comment.")
        # Ensure comment object is present
        if not self._comment_obj:
            self.get()
        self.body = new_body
        retry_call(self._comment_obj.edit, fargs=[self.body], exceptions=Exception,
                   tries=5, delay=1, backoff=2, max_delay=30)

    def append(self, text_to_append):
        if not self.id:
            raise Exception("'id' must be set to append to a comment.")
        # Ensure comment object is present and up to date
        self.get()
        self.edit(self.body + text_to_append)


class GitLabPRComment(BasePRComment):
    """
    PRComment class for use with GitLab.
    """
    def __init__(self, repo_name, pr_number, body=None, id=None):
        super().__init__(repo_name, pr_number, body, id)
        gl = gitlab.get_instance()
        proj = gl.projects.get(self.repo_name)
        self._pr_obj = proj.mergerequests.get(self.pr_number)

    @property
    def html_url(self):
        if self._comment_obj:
            # GitLab comment object does not include a comment URL
            return f"{self._pr_obj.web_url}#note_{self._comment_obj.id}"
        return None

    def get(self):
        if not self.id:
            raise Exception("'id' must be set to get a comment.")
        self._comment_obj = self._pr_obj.notes.get(self.id)
        self.body = self._comment_obj.body

    def create(self):
        if not self.body:
            raise Exception("'body' must be set to create a comment.")
        if self.id:
            # Return early if 'id' is set to avoid creating duplicate comments
            return
        self._comment_obj = self._pr_obj.notes.create({"body": self.body})
        if self._comment_obj:
            self.id = self._comment_obj.id

    def edit(self, new_body):
        if not self.id:
            raise Exception("'id' must be set to edit a comment.")
        # Ensure comment object is present
        if not self._comment_obj:
            self.get()
        self.body = new_body
        self._comment_obj.body = self.body
        self._comment_obj.save()

    def append(self, text_to_append):
        if not self.id:
            raise Exception("'id' must be set to append to a comment.")
        # Ensure comment object and body are present and up to date
        self.get()
        self.edit(self.body + text_to_append)


# Type for subclasses of BasePRComment
PRComment = Union[GitHubPRComment, GitLabPRComment]


def create_pr_comment_instance(repo_name, pr_number, body=None, id=None):
    """
    Creates a PRComment instance for the configured Git hosting platform.

    Args:
        repo_name (string): The name of the repository
        pr_number (int): The number of the pull request in the repository
        body (string): The comment body. Required when creating a new comment.
            Cannot be set at the same time as 'id'.
        id (int): The ID of the comment. Required when getting and/or updating
            an existing comment. Cannot be set at the same time as 'body'.

    Returns:
        PRComment instance or None
    """
    git_host = get_git_hosting_platform()
    if git_host == GITHUB:
        return GitHubPRComment(repo_name=repo_name, pr_number=pr_number, body=body, id=id)
    elif git_host == GITLAB:
        return GitLabPRComment(repo_name=repo_name, pr_number=pr_number, body=body, id=id)
    return None
