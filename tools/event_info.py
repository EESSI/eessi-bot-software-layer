# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Sondre Bergsvaag Risanger (@sondrebr)
#
# license: GPLv2
#

# Standard library imports
from functools import cached_property

# Third party imports (anything installed into the local Python environment)
# (none)

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from connections import gitlab
from tools.git import get_git_hosting_platform, GITHUB, GITLAB


class BaseEventInfo():
    """
    Base class to use for handling event info, which works differently
    for GitHub vs. GitLab. Subscripting is implemented for compatibility.
    If a new field needs to be accessed, add a new property to
    retrieve it instead of subscripting/using the event_info dict.
    """
    def __init__(self, event_info):
        if self.__class__ is BaseEventInfo:
            err_msg = "Do not use this base class directly. "
            err_msg += "Please use one of its subclasses instead."
            raise NotImplementedError(err_msg)
        self.event_info = event_info

    # Prevents subclasses from overriding __getitem__
    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        if "__getitem__" in cls.__dict__:
            raise Exception(f"{cls.__name__} must not override __getitem__")

    # Do not override - implements subscripting for compatibility
    def __getitem__(self, key):
        return self.event_info[key]

    @cached_property
    def action(self):
        raise NotImplementedError()

    @cached_property
    def comment_id(self):
        raise NotImplementedError()

    @cached_property
    def comment_body(self):
        raise NotImplementedError()

    @cached_property
    def comment_created_by(self):
        raise NotImplementedError()

    @cached_property
    def comment_updated_by(self):
        raise NotImplementedError()

    @cached_property
    def discussion_id(self):
        raise NotImplementedError()

    @cached_property
    def event_id(self):
        raise NotImplementedError()

    @cached_property
    def event_type(self):
        raise NotImplementedError()

    @cached_property
    def label_name(self):
        raise NotImplementedError()

    @cached_property
    def pr_number(self):
        raise NotImplementedError()

    @cached_property
    def pr_merged_status(self):
        raise NotImplementedError()

    @cached_property
    def pr_url(self):
        raise NotImplementedError()

    @cached_property
    def repo_name(self):
        raise NotImplementedError()


class GitHubEventInfo(BaseEventInfo):
    """
    EventInfo class for use with GitHub webhooks.
    """
    def __init__(self, event_info):
        super().__init__(event_info)
        self._request_body = event_info["raw_request_body"]

    @cached_property
    def action(self):
        return self.event_info["action"]

    @cached_property
    def comment_id(self):
        return self._request_body["comment"]["id"]

    @cached_property
    def comment_body(self):
        return self._request_body["comment"]["body"]

    @cached_property
    def comment_created_by(self):
        return self._request_body["comment"]["user"]["login"]

    @cached_property
    def comment_updated_by(self):
        return self._request_body["sender"]["login"]

    @cached_property
    def discussion_id(self):
        # Not applicable for GitHub
        return None

    @cached_property
    def event_id(self):
        return self.event_info["id"]

    @cached_property
    def event_type(self):
        return self.event_info["type"]

    @cached_property
    def label_name(self):
        return self._request_body["label"]["name"]

    @cached_property
    def pr_number(self):
        if self.event_type == "pull_request":
            pr_num = self._request_body["pull_request"]["number"]
        else:
            pr_num = self._request_body["issue"]["number"]
        return pr_num

    @cached_property
    def pr_merged_status(self):
        return self._request_body["pull_request"]["merged"]

    @cached_property
    def pr_url(self):
        if self.event_type == "pull_request":
            url = self._request_body["pull_request"]["html_url"]
        else:
            url = self._request_body["issue"]["html_url"]
        return url

    @cached_property
    def repo_name(self):
        return self._request_body["repository"]["full_name"]


class GitLabEventInfo(BaseEventInfo):
    """
    EventInfo class for use with GitLab webhooks. Converts GL terminology to
    GH equivalents where needed, e.g. event type 'note' becomes 'issue_comment'.
    """
    def __init__(self, event_info):
        super().__init__(event_info)
        self._request_body = event_info["raw_request_body"]
        self._object_attributes = self._request_body.get("object_attributes", {})

    # Map GitLab actions to GitHub actions
    _ACTION_MAP = {
        # Note -> comment actions
        "create": "created",
        "update": "edited",
        "delete": "deleted",

        # MR -> PR actions
        # MR 'update' handled separately
        "open": "opened",
        "merge": "closed",
        "close": "closed",
    }
    _UNKNOWN = "UNKNOWN"

    @cached_property
    def action(self):
        gl_action = self._object_attributes["action"]
        # GL uses a single 'update' action for MRs
        # Need to check changes to find exact action, e.g. 'labeled'
        if self.event_type == "pull_request" and gl_action == "update":
            changes = self._request_body["changes"]
            if "labels" in changes:
                action = "labeled"
            else:
                action = self._UNKNOWN
        else:
            action = self._ACTION_MAP.get(gl_action, self._UNKNOWN)
        return action

    @cached_property
    def comment_id(self):
        return self._object_attributes["id"]

    @cached_property
    def comment_body(self):
        return self._object_attributes["note"]

    @cached_property
    def comment_created_by(self):
        created_by_id = self._object_attributes["author_id"]
        triggered_by_id = self._request_body["user"]["id"]
        # GL events only include the username of the user who triggered the event
        if triggered_by_id == created_by_id:
            created_by = self._request_body["user"]["username"]
        else:
            gl = gitlab.get_instance()
            user = gl.users.get(created_by_id)
            created_by = user.username
        return created_by

    @cached_property
    def comment_updated_by(self):
        return self._request_body["user"]["username"]

    @cached_property
    def discussion_id(self):
        return self._object_attributes["discussion_id"]

    @cached_property
    def event_id(self):
        return self.event_info["id"]

    # Map (relevant) GitLab events to GitHub events
    _EVENT_TYPE_MAP = {
        "note": "issue_comment",
        "merge_request": "pull_request",
    }

    @cached_property
    def event_type(self):
        gl_event_type = self.event_info["type"]
        return self._EVENT_TYPE_MAP.get(gl_event_type, self._UNKNOWN)

    @cached_property
    def label_name(self):
        # GH sends one event per label while GL sends one event with all label changes
        # Set manually and call handle_pull_request_labeled_event once per label?
        raise NotImplementedError()

    @cached_property
    def pr_number(self):
        if self.event_type == "pull_request":
            pr_iid = self._object_attributes["iid"]
        else:
            pr_iid = self._request_body["merge_request"]["iid"]
        return pr_iid

    @cached_property
    def pr_merged_status(self):
        if self.event_type == "pull_request":
            state = self._object_attributes["state"]
        else:
            state = self._request_body["merge_request"]["state"]
        return state == "merged"

    @cached_property
    def pr_url(self):
        if self.event_type == "pull_request":
            url = self._object_attributes["url"]
        else:
            url = self._request_body["merge_request"]["url"]
        return url

    @cached_property
    def repo_name(self):
        return self._request_body["project"]["path_with_namespace"]


def create_event_info_instance(event_info):
    """
    Creates an EventInfo instance for the configured Git hosting platform.

    Args:
        event_info (dict): The event info dictionary created by PyGHee

    Returns:
        Instance of BaseEventInfo subclass
    """
    git_host = get_git_hosting_platform()
    if git_host == GITHUB:
        new_event_info = GitHubEventInfo(event_info)
    elif git_host == GITLAB:
        new_event_info = GitLabEventInfo(event_info)
    return new_event_info
