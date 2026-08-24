# Tests for 'tools/event_info.py' of the EESSI build-and-deploy bot,
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
import json
from unittest.mock import patch

# Third party imports (anything installed into the local Python environment)
from pyghee.lib import CaseInsensitiveDict, get_event_info
import pytest

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from tools import event_info, git


# All properties to be implemented by the EventInfo classes
EVENT_INFO_PROPERTIES = [
    "action", "comment_id", "comment_body", "comment_created_by",
    "event_id", "event_triggered_by", "event_type",
    "issue_number", "issue_url", "label_name",
    "pr_number", "pr_title", "pr_merged_status", "pr_url",
    "repo_name",
]

# Event type + action combinations with sample event files
# Used as keys in *_EVENT_PATHS dicts below
PR_OPENED = "pr_opened"
PR_LABELED = "pr_labeled"
PR_CLOSED = "pr_closed"
COMMENT_CREATED = "comment_created"
COMMENT_EDITED = "comment_edited"
INSTALLATION_CREATED = "installation_created"

# Sample event files for GitHubEventInfo tests
GITHUB_EVENT_PATHS = {
    # Pull request events
    PR_OPENED: "test/events/github/pr-opened.json",
    PR_LABELED: "test/events/github/pr-labeled.json",
    PR_CLOSED: "test/events/github/pr-closed.json",

    # Comment events
    COMMENT_CREATED: "test/events/github/comment-created.json",
    COMMENT_EDITED: "test/events/github/comment-edited.json",

    # Installation event
    INSTALLATION_CREATED: "test/events/github/installation-created.json"
}

# Sample event files for GitLabEventInfo tests
GITLAB_EVENT_PATHS = {
    # Pull request events
    PR_OPENED: "test/events/gitlab/pr-opened.json",
    PR_LABELED: "test/events/gitlab/pr-labeled.json",
    PR_CLOSED: "test/events/gitlab/pr-closed.json",

    # Comment events
    COMMENT_CREATED: "test/events/gitlab/comment-created.json",
    COMMENT_EDITED: "test/events/gitlab/comment-edited.json",
}


class MockRequest():
    """Mock of a flask.Request object as expected by PyGHee's get_event_info().
    Only the attributes used by that function are implemented.
    """

    def __init__(self, event):
        """Set up mock request attributes from a sample event.

        Args:
            event: dict read from one of the sample event files;
                must contain the keys 'json' and 'headers'.
        """
        self.json = event["json"]
        self.data = json.dumps(self.json).encode()
        self.headers = CaseInsensitiveDict(event["headers"])


# Mock class handling individual user information in MockGitlab
class MockGitlabUser():
    def __init__(self, id, username):
        self.id = id
        self.username = username


# Mock class handling collections of users in MockGitlab
class MockGitlabUsers():
    def __init__(self, users):
        # Store ID -> User mappings
        self._users = {id: MockGitlabUser(id, username) for id, username in users.items()}

    def get(self, id, *_args, **_kwargs):
        user = self._users.get(id)
        if user is None:
            raise ValueError("User does not exist!")
        return user


# Mock class imitating python-gitlab's Gitlab class
class MockGitlab():
    def __init__(self, users=None):
        self.users = MockGitlabUsers(users)


# Read event from file, create a MockRequest and return event_info dict from PyGHee's get_event_info()
def get_event_info_from_file(path):
    # Use get_git_hosting_platform() imported by event_info - return value should be patched by tests
    event_source = event_info.get_git_hosting_platform()
    with open(path, "r") as file:
        event = json.load(file)
    request = MockRequest(event)
    event_info_dict = get_event_info(request, event_source)
    return event_info_dict


# Verify EventInfo type definition
def test_EventInfo():
    expected_event_info_types = set((event_info.GitHubEventInfo, event_info.GitLabEventInfo))
    # Need to use __args__ for Python 3.9 compatibility
    actual_event_info_types = set(event_info.EventInfo.__args__)
    assert actual_event_info_types == expected_event_info_types


# Test BaseEventInfo class
def test_BaseEventInfo():
    # Creating a BaseEventInfo instance should fail
    with pytest.raises(NotImplementedError):
        event_info.BaseEventInfo({})

    # Overriding __getitem__ in subclasses should fail
    with pytest.raises(Exception):
        class _(event_info.BaseEventInfo):
            def __getitem__(self, _):
                return None

    with patch("tools.event_info.BaseEventInfo.__init__") as mock_init:
        # Mock __init__ to allow creating an instance
        mock_init.return_value = None
        event_info_obj = event_info.BaseEventInfo()

    # Subscripting should subscript the event_info dict attribute
    event_info_obj.event_info = {"test": 123}
    assert event_info_obj["test"] is event_info_obj.event_info["test"]
    assert event_info_obj["test"] == 123

    # All properties should be cached_property and raise a NotImplementedError
    for prop in EVENT_INFO_PROPERTIES:
        # Test property type
        attr = getattr(event_info.BaseEventInfo, prop)
        assert type(attr) is cached_property

        # Test property getter - should fail with NotImplementedError
        with pytest.raises(NotImplementedError):
            attr.__get__(event_info_obj)


# Test GitHubEventInfo class on each supported event + action
@patch("tools.event_info.get_git_hosting_platform", return_value="github")
def test_GitHubEventInfo(_):
    event_info_dict = get_event_info_from_file(GITHUB_EVENT_PATHS[PR_OPENED])
    event_info_obj = event_info.create_event_info_instance(event_info_dict)

    # Test common properties
    assert event_info_obj.action == "opened"
    assert event_info_obj.event_id == event_info_dict["id"]
    assert event_info_obj.event_triggered_by == event_info_dict["raw_request_body"]["sender"]["login"]
    assert event_info_obj.event_type == "pull_request"
    assert event_info_obj.repo_name == event_info_dict["raw_request_body"]["repository"]["full_name"]

    # Test properties for pull_request events
    assert event_info_obj.pr_number == event_info_dict["raw_request_body"]["pull_request"]["number"]
    assert event_info_obj.pr_title == event_info_dict["raw_request_body"]["pull_request"]["title"]
    assert event_info_obj.pr_url == event_info_dict["raw_request_body"]["pull_request"]["html_url"]

    # Test properties for pull_request opened
    assert event_info_obj.pr_merged_status is False

    # Test pull_request labeled
    event_info_dict = get_event_info_from_file(GITHUB_EVENT_PATHS[PR_LABELED])
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.action == "labeled"
    assert event_info_obj.label_name == event_info_dict["raw_request_body"]["label"]["name"]

    # Test pull_request closed
    # Closed by merging
    event_info_dict = get_event_info_from_file(GITHUB_EVENT_PATHS[PR_CLOSED])
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.action == "closed"
    assert event_info_obj.pr_merged_status is True

    # Closed without merging
    event_info_dict["raw_request_body"]["pull_request"]["merged"] = False
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.action == "closed"
    assert event_info_obj.pr_merged_status is False

    # Test properties for issue_comment events
    event_info_dict = get_event_info_from_file(GITHUB_EVENT_PATHS[COMMENT_CREATED])
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.event_type == "issue_comment"
    assert event_info_obj.comment_id == event_info_dict["raw_request_body"]["comment"]["id"]
    assert event_info_obj.comment_body == event_info_dict["raw_request_body"]["comment"]["body"]
    assert event_info_obj.issue_number == event_info_dict["raw_request_body"]["issue"]["number"]
    assert event_info_obj.issue_url == event_info_dict["raw_request_body"]["issue"]["html_url"]

    # Test issue_comment created
    assert event_info_obj.action == "created"
    assert event_info_obj.comment_created_by == event_info_dict["raw_request_body"]["comment"]["user"]["login"]
    assert event_info_obj.comment_created_by == event_info_obj.event_triggered_by

    # Test issue_comment edited
    event_info_dict = get_event_info_from_file(GITHUB_EVENT_PATHS[COMMENT_EDITED])
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.event_type == "issue_comment"
    assert event_info_obj.action == "edited"

    # Check who created vs. updated the comment - should be different users
    assert event_info_obj.event_triggered_by == event_info_dict["raw_request_body"]["sender"]["login"]
    assert event_info_obj.comment_created_by == event_info_dict["raw_request_body"]["comment"]["user"]["login"]
    assert event_info_obj.event_triggered_by != event_info_obj.comment_created_by

    # Test installation created
    event_info_dict = get_event_info_from_file(GITHUB_EVENT_PATHS[INSTALLATION_CREATED])
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.event_type == "installation"
    assert event_info_obj.action == "created"


# Test GitLabEventInfo class on each supported event + action
@patch("tools.event_info.get_git_hosting_platform", return_value="gitlab")
def test_GitLabEventInfo(_):
    event_info_dict = get_event_info_from_file(GITLAB_EVENT_PATHS[PR_OPENED])
    event_info_obj = event_info.create_event_info_instance(event_info_dict)

    # Test common properties
    assert event_info_obj.action == "opened"
    assert event_info_obj.event_id == event_info_dict["id"]
    assert event_info_obj.event_triggered_by == event_info_dict["raw_request_body"]["user"]["username"]
    assert event_info_obj.event_type == "pull_request"
    assert event_info_obj.repo_name == event_info_dict["raw_request_body"]["project"]["path_with_namespace"]

    # Test properties for pull_request events
    assert event_info_obj.pr_number == event_info_dict["raw_request_body"]["object_attributes"]["iid"]
    assert event_info_obj.pr_title == event_info_dict["raw_request_body"]["object_attributes"]["title"]
    assert event_info_obj.pr_url == event_info_dict["raw_request_body"]["object_attributes"]["url"]

    # Test properties for pull_request opened
    assert event_info_obj.pr_merged_status is False

    # Test properties for pull_request labeled
    event_info_dict = get_event_info_from_file(GITLAB_EVENT_PATHS[PR_LABELED])
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.action == "labeled"

    # 'label_name' should be None if 'bot:deploy' was not added
    # label added in sample event is 'test:label'
    current_labels = event_info_dict["raw_request_body"]["changes"]["labels"]["current"]
    label = current_labels[0]
    assert label["title"] == "test:label"
    assert event_info_obj.label_name is None

    # Append several labels to the list of current labels, including 'bot:deploy'
    # 'label_name' getter should look for 'bot:deploy' among all added labels
    bot_deploy_label = {**label, "title": "bot:deploy"}
    current_labels.append(bot_deploy_label)
    current_labels.append({**label, "title": "test2:label"})
    current_labels.append({**label, "title": "test:label2"})
    event_info_dict["raw_request_body"]["changes"]["labels"]["current"] = current_labels
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    # 'label_name' should now be 'bot:deploy'
    assert event_info_obj.label_name == "bot:deploy"

    # Add 'bot:deploy' label to list of previous labels, meaning it was already present
    # 'label_name' should again be None
    event_info_dict["raw_request_body"]["changes"]["labels"]["previous"].append(bot_deploy_label)
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.label_name is None

    # Test unknown pull_request update action
    event_info_dict["raw_request_body"]["changes"] = {}
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.action == "UNKNOWN"

    # Test properties for pull_request closed
    # Closed by merging
    event_info_dict = get_event_info_from_file(GITLAB_EVENT_PATHS[PR_CLOSED])
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.action == "closed"
    assert event_info_obj.pr_merged_status is True

    # Closed without merging
    event_info_dict["action"] = "close"
    event_info_dict["raw_request_body"]["object_attributes"]["state"] = "closed"
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.action == "closed"
    assert event_info_obj.pr_merged_status is False

    # Test properties for issue_comment events
    event_info_dict = get_event_info_from_file(GITLAB_EVENT_PATHS[COMMENT_CREATED])
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.event_type == "issue_comment"
    assert event_info_obj.comment_id == event_info_dict["raw_request_body"]["object_attributes"]["id"]
    assert event_info_obj.comment_body == event_info_dict["raw_request_body"]["object_attributes"]["note"]
    assert event_info_obj.issue_number == event_info_dict["raw_request_body"]["merge_request"]["iid"]
    assert event_info_obj.issue_url == event_info_dict["raw_request_body"]["merge_request"]["url"]
    assert event_info_obj.pr_number == event_info_dict["raw_request_body"]["merge_request"]["iid"]
    assert event_info_obj.pr_title == event_info_dict["raw_request_body"]["merge_request"]["title"]
    pr_merged_status = (event_info_dict["raw_request_body"]["merge_request"]["state"] == "merged")
    assert event_info_obj.pr_merged_status is pr_merged_status
    assert event_info_obj.pr_url == event_info_dict["raw_request_body"]["merge_request"]["url"]

    # Test properties for issue_comment created
    assert event_info_obj.action == "created"
    assert event_info_obj.comment_created_by == event_info_dict["raw_request_body"]["user"]["username"]
    assert event_info_obj.comment_created_by == event_info_obj.event_triggered_by

    # Store the author of the comment
    user_dict = event_info_dict["raw_request_body"]["user"]
    users = {user_dict["id"]: user_dict["username"]}
    comment_created_by = user_dict["username"]

    # Test properties for issue_comment edited
    event_info_dict = get_event_info_from_file(GITLAB_EVENT_PATHS[COMMENT_EDITED])
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.event_type == "issue_comment"
    assert event_info_obj.action == "edited"

    # Check who created vs. updated the comment - should be different users
    assert event_info_obj.event_triggered_by == event_info_dict["raw_request_body"]["user"]["username"]
    with patch("tools.event_info.gitlab.get_instance") as mock_get_instance:
        mock_get_instance.return_value = MockGitlab(users)
        assert event_info_obj.comment_created_by == comment_created_by
        mock_get_instance.assert_called()
    assert event_info_obj.event_triggered_by != event_info_obj.comment_created_by

    # Test handling of non-PR comments
    # Test Issue comment handling
    event_info_dict["raw_request_body"]["object_attributes"]["noteable_type"] = "Issue"
    mr_dict = event_info_dict["raw_request_body"].pop("merge_request")
    issue_dict = {}
    issue_dict["iid"] = mr_dict["iid"]
    issue_dict["url"] = mr_dict["url"]
    event_info_dict["raw_request_body"]["issue"] = issue_dict
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.issue_number == issue_dict["iid"]
    assert event_info_obj.issue_url == issue_dict["url"]

    # Test Commit comment handling - should return defaults
    event_info_dict["raw_request_body"]["object_attributes"]["noteable_type"] = "Commit"
    event_info_dict["raw_request_body"].pop("issue")
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.issue_number == -1
    assert event_info_obj.issue_url == ""

    # Test unknown event type and action
    event_info_dict["type"] = "invalidtype"
    event_info_dict["action"] = "invalidaction"
    event_info_obj = event_info.create_event_info_instance(event_info_dict)
    assert event_info_obj.event_type == "UNKNOWN"
    assert event_info_obj.action == "UNKNOWN"


# Test create_event_info_instance()
@pytest.mark.parametrize("git_host,expected_type", [
    (git.GITHUB, event_info.GitHubEventInfo),
    (git.GITLAB, event_info.GitLabEventInfo),
    ("doesnotexist", type(None))
])
@patch("tools.event_info.get_git_hosting_platform")
def test_create_event_info_instance(mock_get_git_host, git_host, expected_type):
    mock_get_git_host.return_value = git_host
    event_info_obj = event_info.create_event_info_instance({"raw_request_body": {}})
    assert type(event_info_obj) is expected_type
