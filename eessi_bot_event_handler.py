#!/usr/bin/env python3
#
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
# author: Lara Ramona Peeters (@laraPPr)
# author: Thomas Roeblitz (@trz42)
# author: Pedro Santos Neves (@Neves-P)
# author: Sam Moors (@smoors)
#
# license: GPLv2
#

# Standard library imports
import sys
from datetime import datetime, timezone

# Third party imports (anything installed into the local Python environment)
from pyghee.lib import create_app, get_event_info, PyGHee, read_event_from_json
from pyghee.utils import log
import waitress

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from connections import github
from tasks.build import check_build_permission, get_node_types, request_bot_build_issue_comments, \
    submit_build_jobs
from tasks.deploy import deploy_built_artefacts, determine_job_dirs
from tasks.clean_up import move_to_trash_bin
from tools import config
from tools.args import event_handler_parse
from tools.commands import EESSIBotCommand, EESSIBotCommandError, \
    contains_any_bot_command, get_bot_command
from tools.permissions import check_command_permission
from tools.pr_comments import ChatLevels, create_comment


REQUIRED_CONFIG = {
    config.SECTION_ARCHITECTURETARGETS: [
        config.NODE_TYPE_MAP],       # required
    config.SECTION_BOT_CONTROL: [
        # config.BOT_CONTROL_SETTING_CHATLEVEL,                      # optional
        config.BOT_CONTROL_SETTING_COMMAND_PERMISSION,             # required
        config.BOT_CONTROL_SETTING_COMMAND_RESPONSE_FMT],          # required
    config.SECTION_BUILDENV: [
        # config.BUILDENV_SETTING_ALLOW_UPDATE_SUBMIT_OPTS           # optional
        config.BUILDENV_SETTING_BUILD_JOB_SCRIPT,                  # required
        config.BUILDENV_SETTING_BUILD_LOGS_DIR,                    # optional+recommended
        config.BUILDENV_SETTING_BUILD_PERMISSION,                  # optional+recommended
        config.BUILDENV_SETTING_CONTAINER_CACHEDIR,                # optional+recommended
        # config.BUILDENV_SETTING_CLONE_GIT_REPO_VIA,                # optional
        # config.BUILDENV_SETTING_CVMFS_CUSTOMIZATIONS,              # optional
        # config.BUILDENV_SETTING_HTTPS_PROXY,                       # optional
        # config.BUILDENV_SETTING_HTTP_PROXY,                        # optional
        # config.BUILDENV_SETTING_JOB_DELAY_BEGIN_FACTOR,            # optional (default: 2)
        config.BUILDENV_SETTING_JOB_HANDOVER_PROTOCOL,             # required
        config.BUILDENV_SETTING_JOB_NAME,                          # required
        config.BUILDENV_SETTING_JOBS_BASE_DIR,                     # required
        # config.BUILDENV_SETTING_LOAD_MODULES,                      # optional
        config.BUILDENV_SETTING_LOCAL_TMP,                         # required
        config.BUILDENV_SETTING_NO_BUILD_PERMISSION_COMMENT,       # required
        config.BUILDENV_SETTING_SHARED_FS_PATH,                    # optional+recommended
        # config.BUILDENV_SETTING_SLURM_PARAMS,                      # optional
        config.BUILDENV_SETTING_SUBMIT_COMMAND],                   # required
    config.SECTION_CLEAN_UP: [
        config.CLEAN_UP_SETTING_TRASH_BIN_ROOT_DIR,                # required
        config.CLEAN_UP_SETTING_MOVED_JOB_DIRS_COMMENT],           # required
    config.SECTION_DEPLOYCFG: [
        config.DEPLOYCFG_SETTING_ARTEFACT_PREFIX,                  # (required)
        config.DEPLOYCFG_SETTING_ARTEFACT_UPLOAD_SCRIPT,           # required
        config.DEPLOYCFG_SETTING_BUCKET_NAME,                      # required
        config.DEPLOYCFG_SETTING_DEPLOY_PERMISSION,                # optional+recommended
        # config.DEPLOYCFG_SETTING_ENDPOINT_URL,                     # optional
        config.DEPLOYCFG_SETTING_METADATA_PREFIX,                  # (required)
        config.DEPLOYCFG_SETTING_NO_DEPLOY_PERMISSION_COMMENT,     # required
        # config.DEPLOYCFG_SETTING_SIGNING,                          # optional
        config.DEPLOYCFG_SETTING_UPLOAD_POLICY],                   # required
    config.SECTION_DOWNLOAD_PR_COMMENTS: [
        config.DOWNLOAD_PR_COMMENTS_SETTING_CURL_FAILURE,          # required
        config.DOWNLOAD_PR_COMMENTS_SETTING_CURL_TIP,              # required
        config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_APPLY_FAILURE,     # required
        config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_APPLY_TIP,         # required
        config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_CHECKOUT_FAILURE,  # required
        config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_CHECKOUT_TIP,      # required
        config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_CLONE_FAILURE,     # required
        config.DOWNLOAD_PR_COMMENTS_SETTING_GIT_CLONE_TIP,         # required
        config.DOWNLOAD_PR_COMMENTS_SETTING_PR_DIFF_FAILURE,       # required
        config.DOWNLOAD_PR_COMMENTS_SETTING_PR_DIFF_TIP],          # required
    config.SECTION_EVENT_HANDLER: [
        config.EVENT_HANDLER_SETTING_LOG_PATH],                    # required
    config.SECTION_GITHUB: [
        config.GITHUB_SETTING_APP_ID,                              # required
        config.GITHUB_SETTING_APP_NAME,                            # required
        config.GITHUB_SETTING_INSTALLATION_ID,                     # required
        config.GITHUB_SETTING_PRIVATE_KEY],                        # required
    # the poll interval setting is required for the alternative job handover
    # protocol (delayed_begin)
    config.SECTION_JOB_MANAGER: [
        config.JOB_MANAGER_SETTING_POLL_INTERVAL],                 # required
    config.SECTION_REPO_TARGETS: [
        config.REPO_TARGETS_SETTING_REPOS_CFG_DIR],                # required
    config.SECTION_SUBMITTED_JOB_COMMENTS: [
        config.SUBMITTED_JOB_COMMENTS_SETTING_INSTANCE_REPO,       # required
        config.SUBMITTED_JOB_COMMENTS_SETTING_BUILD_ON_ARCH,       # required
        config.SUBMITTED_JOB_COMMENTS_SETTING_BUILD_FOR_ARCH,      # required
        config.SUBMITTED_JOB_COMMENTS_SETTING_JOBDIR,              # required
        # config.SUBMITTED_JOB_COMMENTS_SETTING_AWAITS_RELEASE,      # optional
        config.SUBMITTED_JOB_COMMENTS_SETTING_AWAITS_RELEASE_DELAYED_BEGIN_MSG,  # required
        config.SUBMITTED_JOB_COMMENTS_SETTING_AWAITS_RELEASE_HOLD_RELEASE_MSG,   # required
        config.SUBMITTED_JOB_COMMENTS_SETTING_WITH_ACCELERATOR],   # required
    }


class EESSIBotSoftwareLayer(PyGHee):
    """
    Class for representing the event handler of the build-and-deploy bot. It
    receives events from GitHub via PyGHee and processes them. It is
    multi-threaded (via waitress) to ensure that it can respond to concurrent
    events. It also avoids keeping any event related information in memory.
    """

    def __init__(self, *args, **kwargs):
        """
        EESSIBotSoftwareLayer constructor. Calls constructor of PyGHee and
        initializes some configuration settings.
        """
        super(EESSIBotSoftwareLayer, self).__init__(*args, **kwargs)

        self.cfg = config.read_config()
        event_handler_cfg = self.cfg[config.SECTION_EVENT_HANDLER]
        self.logfile = event_handler_cfg.get(config.EVENT_HANDLER_SETTING_LOG_PATH)

    def log(self, msg, *args):
        """
        Logs a message incl the caller's function name by passing msg and
        *args to PyGHee's log method.

        Args:
            msg (string): message to log to event handler log
            *args (any): any values to be substituted into msg

        Returns:
            None (implicitly)
        """
        funcname = sys._getframe().f_back.f_code.co_name
        if args:
            msg = msg % args
        msg = "[%s]: %s" % (funcname, msg)
        log(msg, log_file=self.logfile)

    def handle_issue_comment_event(self, event_info, log_file=None):
        """
        Handle events of type issue_comment. Main action is to parse new issue
        comments for any bot command and execute it if one is found.

        Args:
            event_info (dict): event received by event_handler
            log_file (string): path to log messages to

        Returns:
            None (implicitly)

        Raises:
            Exception: raises any exception that is not of type EESSIBotCommandError
        """
        request_body = event_info['raw_request_body']
        issue_url = request_body['issue']['url']
        action = request_body['action']
        sender = request_body['sender']['login']
        owner = request_body['comment']['user']['login']
        repo_name = request_body['repository']['full_name']
        pr_number = request_body['issue']['number']

        # TODO add request body text (['comment']['body']) to log message when
        #      log level is set to debug
        self.log(f"Comment in {issue_url} (owned by @{owner}) {action} by @{sender}")

        app_name = self.cfg[config.SECTION_GITHUB][config.GITHUB_SETTING_APP_NAME]
        command_response_fmt = self.cfg[config.SECTION_BOT_CONTROL][config.BOT_CONTROL_SETTING_COMMAND_RESPONSE_FMT]

        # currently, only commands in new comments are supported
        #  - commands have the syntax 'bot: COMMAND [ARGS*]'

        # only scan for commands in newly created comments
        if action == 'created':
            comment_received = request_body['comment']['body']
            self.log(f"comment action '{action}' is handled")
        else:
            # NOTE we do not respond to an updated PR comment with yet another
            #      new PR comment, because it would make the bot very noisy or
            #      worse could result in letting the bot enter an endless loop
            self.log(f"comment action '{action}' not handled")
            return
        # at this point we know that we are handling a new comment

        issue_comment = None

        # check if comment does not contain a bot command
        if not contains_any_bot_command(comment_received):
            self.log("comment does not contain a bot comment; not processing it further")
            return
        # at this point we know that the comment contains a bot command

        # check if sender is authorized to send any command
        # - this serves a double purpose:
        #   1. check permission
        #   2. skip any comment updates that were done by the bot itself
        #      - thus we prevent the bot from entering an endless loop
        #        where it reacts on updates to comments it made itself
        #      - this assumes that the sender of an event is corresponding
        #        to the bot if the bot updates or creates comments itself
        #        and that the bot is not given permission in the
        #        configuration setting 'command_permission'
        #      - in order to prevent surprises we should be very careful
        #        about what the bot adds to comments, for example, before
        #        updating a comment it could run the update through the
        #        function get_bot_command to determine if the comment
        #        includes a bot command
        if check_command_permission(sender) is False:
            self.log(f"account `{sender}` has NO permission to send commands to bot")
            # need to ensure that the bot is not responding on its own comments
            # as a quick implementation we check if the sender name contains '[bot]'
            # TODO improve this by querying (and caching) information about the sender of
            #      an event
            #      ALTERNATIVELY we could postpone this test a bit until we
            #      have parsed the comment and know if it contains any bot command
            if not sender.endswith('[bot]'):
                comment_response = f"\n- account `{sender}` has NO permission to send commands to the bot"
                comment_body = command_response_fmt.format(
                    app_name=app_name,
                    comment_response=comment_response,
                    comment_result=''
                )
                issue_comment = create_comment(repo_name, pr_number, comment_body, ChatLevels.CHATTY)
            else:
                self.log(f"account `{sender}` seems to be a bot instance itself, hence not creating a new PR comment")
            return
        else:
            self.log(f"account `{sender}` has permission to send commands to bot")

        # search for commands in comment
        comment_response = ''
        commands = []
        # process any non-empty lines in comment (inner comprehension splits
        # comment into lines, outer comprehension ensures only non-empty lines
        # are processed further)
        for line in [x for x in [y.strip() for y in comment_received.split('\n')] if x]:
            # TODO add processed line(s) to log when log level is set to debug
            bot_command = get_bot_command(line)
            if bot_command:
                try:
                    ebc = EESSIBotCommand(bot_command)
                except EESSIBotCommandError as bce:
                    self.log(f"ERROR: parsing bot command '{bot_command}' failed with {bce.args}")
                    # TODO possibly add more information to log when log level is set to debug
                    comment_response += f"\n- parsing the bot command `{bot_command}`, received"
                    comment_response += f" from sender `{sender}`, failed"
                    continue
                commands.append(ebc)
                self.log(f"found bot command: '{bot_command}'")
                comment_response += f"\n- received bot command `{bot_command}`"
                comment_response += f" from `{sender}`"
                comment_response += f"\n  - expanded format: `{ebc.to_string()}`"
            # TODO add an else branch that logs information for comments not
            # including a bot command; the logging should only be done when log
            # level is set to debug

        if 'help' in (x.command for x in commands):
            req_chatlevel = ChatLevels.MINIMAL
        else:
            req_chatlevel = ChatLevels.CHATTY

        if comment_response == '':
            # no update to be added, just log and return
            self.log("comment response is empty")
            return
        else:
            self.log(f"comment response: '{comment_response}'")

        if not any(map(get_bot_command, comment_response.split('\n'))):
            # the 'not any()' ensures that the response would not be considered
            # a bot command itself
            # this, together with checking the sender of a comment update, aims
            # at preventing the bot to enter an endless loop in commenting on
            # its own comments
            comment_body = command_response_fmt.format(
                app_name=app_name,
                comment_response=comment_response,
                comment_result=''
            )
            issue_comment = create_comment(repo_name, pr_number, comment_body, req_chatlevel)
        else:
            self.log(f"update '{comment_response}' is considered to contain bot command ... not creating PR comment")
            # TODO we may want to report this back to the PR on GitHub, e.g.,
            # "Oops response message seems to contain a bot command. It is not
            # displayed here to prevent the bot from entering an endless loop
            # of commands. Please, check the logs at the bot instance for more
            # information."

        # process commands
        comment_result = ''
        for cmd in commands:
            try:
                update = self.handle_bot_command(event_info, cmd)
                comment_result += f"\n- handling command `{cmd.to_string()}` resulted in: "
                comment_result += update
                self.log(f"handling command '{cmd.to_string()}' resulted in '{update}'")

            except EESSIBotCommandError as err:
                self.log(f"ERROR: handling command {cmd.command} failed with {err.args[0]}")
                comment_result += f"\n- handling command `{cmd.command}` failed with message"
                comment_result += f"\n  _{err.args[0]}_"
                continue
            except Exception as err:
                log(f"Unexpected err={err}, type(err)={type(err)}")
                if comment_result and issue_comment:
                    comment_body = command_response_fmt.format(
                        app_name=app_name,
                        comment_response=comment_response,
                        comment_result=comment_result
                    )
                    issue_comment.edit(comment_body)
                raise

        if issue_comment:
            # only update PR comment once, that is, a single call to
            # issue_comment.edit is made in the entire function
            comment_body = command_response_fmt.format(
                app_name=app_name,
                comment_response=comment_response,
                comment_result=comment_result
            )
            issue_comment.edit(comment_body)

            self.log(f"issue_comment event (url {issue_url}) handled!")

    def handle_installation_event(self, event_info, log_file=None):
        """
        Handle events of type installation. Main action is to log the event.

        Args:
            event_info (dict): event received by event_handler
            log_file (string): path to log messages to

        Returns:
            None (implicitly)
        """
        request_body = event_info['raw_request_body']
        user = request_body['sender']['login']
        action = request_body['action']
        self.log("App installation event by user %s with action '%s'", user, action)
        self.log("installation event handled!")

    def handle_pull_request_labeled_event(self, event_info, pr):
        """
        Handle events of type pull_request with the action labeled. Main action
        is to process the label 'bot:deploy'.

        Args:
            event_info (dict): event received by event_handler
            pr (github.PullRequest.PullRequest): instance representing the pull request

        Returns:
            None (implicitly)
        """

        # determine label
        label = event_info['raw_request_body']['label']['name']
        self.log("Process PR labeled event: PR#%s, label '%s'", pr.number, label)

        if label == "bot:build":
            msg = "Handling the label 'bot:build' is disabled. Use the command `bot: build [FILTER]*` instead."
            self.log(msg)

            request_body = event_info['raw_request_body']
            repo_name = request_body['repository']['full_name']
            pr_number = request_body['pull_request']['number']
            app_name = self.cfg[config.SECTION_GITHUB][config.GITHUB_SETTING_APP_NAME]
            command_response_fmt = self.cfg[config.SECTION_BOT_CONTROL][config.BOT_CONTROL_SETTING_COMMAND_RESPONSE_FMT]
            comment_body = command_response_fmt.format(
                app_name=app_name,
                comment_response=msg,
                comment_result=''
            )
            create_comment(repo_name, pr_number, comment_body, ChatLevels.BASIC)
        elif label == "bot:deploy":
            # run function to deploy built artefacts
            deploy_built_artefacts(pr, event_info)
        else:
            self.log("handle_pull_request_labeled_event: no handler for label '%s'", label)

    def handle_pull_request_opened_event(self, event_info, pr, req_chatlevel=ChatLevels.CHATTY):
        """
        Handle events of type pull_request with the action opened. Main action
        is to report for which architectures and repositories a bot instance is
        configured to build for.

        Args:
            event_info (dict): event received by event_handler
            pr (github.PullRequest.PullRequest): instance representing the pull request

        Returns:
            github.IssueComment.IssueComment instance or None (note, github refers to
                PyGithub, not the github from the internal connections module)
        """
        self.log("PR opened: waiting for label bot:build")
        app_name = self.cfg[config.SECTION_GITHUB][config.GITHUB_SETTING_APP_NAME]
        # TODO check if PR already has a comment with arch targets and
        # repositories
        node_map = get_node_types(self.cfg)

        comment = f"Instance `{app_name}` is configured to build on:"
        for node in node_map:
            comment += f"\n- Node type `{node}`:"
            current_node_type = node_map[node]
            if "os" in current_node_type:
                comment += f"\n  - OS: `{current_node_type['os']}`"
            if "cpu_subdir" in current_node_type:
                comment += f"\n  - CPU architecture: `{current_node_type['cpu_subdir']}`"
            if "repo_targets" in current_node_type:
                comment += f"\n  - Repositories: `{current_node_type['repo_targets']}`"
            if "accel" in current_node_type:
                comment += f"\n  - Accelerators: `{current_node_type['accel']}`"
            comment += "\n"

        self.log(f"PR opened: comment '{comment}'")

        # create comment to pull request
        repo_name = pr.base.repo.full_name
        issue_comment = create_comment(repo_name, pr.number, comment, req_chatlevel)
        return issue_comment

    def handle_pull_request_event(self, event_info, log_file=None):
        """
        Handle events of type pull_request for all kinds of actions by
        determining a handler for it.

        Args:
            event_info (dict): event received by event_handler
            log_file (string): path to log messages to

        Returns:
            None (implicitly)
        """
        action = event_info['action']
        gh = github.get_instance()
        self.log("repository: '%s'", event_info['raw_request_body']['repository']['full_name'])
        pr = gh.get_repo(event_info['raw_request_body']['repository']
                         ['full_name']).get_pull(event_info['raw_request_body']['pull_request']['number'])
        self.log("PR data: %s", pr)

        handler_name = 'handle_pull_request_%s_event' % action
        if hasattr(self, handler_name):
            handler = getattr(self, handler_name)
            self.log("Handling PR action '%s' for PR #%d...", action, pr.number)
            handler(event_info, pr)
        else:
            self.log("No handler for PR action '%s'", action)

    def handle_bot_command(self, event_info, bot_command, log_file=None):
        """
        Handle a bot command. Main purpose is to determine a handler for the
        specific bot_command given.

        Args:
            event_info (dict): event received by event_handler
            bot_command (EESSIBotCommand): command to be handled
            log_file (string): path to log messages to

        Returns:
            (string): update to be reported back to GitHub as the (immediate)
                result of the bot command

        Raises:
            EESSIBotCommandError: if no handler for the specific command is
                defined
        """
        cmd = bot_command.command
        handler_name = f"handle_bot_command_{cmd}"
        if hasattr(self, handler_name):
            handler = getattr(self, handler_name)
            self.log(f"Handling bot command {cmd}")
            return handler(event_info, bot_command)
        else:
            self.log(f"No handler for command '{cmd}'")
            raise EESSIBotCommandError(f"unknown command `{cmd}`; use `bot: help` for usage information")

    def handle_bot_command_help(self, event_info, bot_command):
        """
        Handles bot command 'help' providing basic information about bot
        commands.

        Args:
            event_info (dict): event received by event_handler
            bot_command (EESSIBotCommand): command to be handled

        Returns:
            (string): basic information about sending commands to the bot
        """
        help_msg = "\n  **How to send commands to bot instances**"
        help_msg += "\n  - Commands must be sent with a **new** comment (edits of existing comments are ignored)."
        help_msg += "\n  - A comment may contain multiple commands, one per line."
        help_msg += "\n  - Every command begins at the start of a line and has the syntax `bot: COMMAND [ARGUMENTS]*`"
        help_msg += "\n  - Currently supported COMMANDs are: `help`, `build`, `show_config`, `status`"
        help_msg += "\n"
        help_msg += "\n  For more information, see https://www.eessi.io/docs/bot"
        return help_msg

    def handle_bot_command_build(self, event_info, bot_command):
        """
        Handles bot command 'build [ARGS*]' by parsing arguments and submitting jobs

        Args:
            event_info (dict): event received by event_handler
            bot_command (EESSIBotCommand): command to be handled

        Returns:
            (string): immediate result of command (any jobs or no jobs being
                submitted) and a link to the issue comment for submitted jobs
        """
        gh = github.get_instance()
        self.log("repository: '%s'", event_info['raw_request_body']['repository']['full_name'])
        repo_name = event_info['raw_request_body']['repository']['full_name']
        pr_number = event_info['raw_request_body']['issue']['number']
        pr = gh.get_repo(repo_name).get_pull(pr_number)
        build_msg = ''
        # Require that build_params is defined, it is required. Otherwise, return early
        if bot_command.build_params is None:
            build_msg = "No 'for:' argument was passed to the bot:build command. This argument is required, so "
            build_msg += "not submitting build jobs"
            return build_msg

        if check_build_permission(pr, event_info):
            # use filter from command
            submitted_jobs = submit_build_jobs(pr, event_info, bot_command.action_filters, bot_command.build_params)
            if submitted_jobs is None or len(submitted_jobs) == 0:
                build_msg = "\n  - no jobs were submitted"
            else:
                for job_id, issue_comment in submitted_jobs.items():
                    build_msg += f"\n  - submitted job `{job_id}`"
                    if issue_comment:
                        build_msg += f", for details & status see {issue_comment.html_url}"
        else:
            request_body = event_info['raw_request_body']
            sender = request_body['sender']['login']
            build_msg = f"\n  - account `{sender}` has NO permission to submit build jobs"
        return build_msg

    def handle_bot_command_show_config(self, event_info, bot_command):
        """
        Handles bot command 'show_config' by running the handler for events of
        type pull_request with the action opened.

        Args:
            event_info (dict): event received by event_handler
            bot_command (EESSIBotCommand): command to be handled

        Returns:
            (string): list item with a link to the issue comment that was created
                by the handler for events of type pull_request with the action opened
        """
        self.log("processing bot command 'show_config'")
        gh = github.get_instance()
        repo_name = event_info['raw_request_body']['repository']['full_name']
        pr_number = event_info['raw_request_body']['issue']['number']
        pr = gh.get_repo(repo_name).get_pull(pr_number)
        issue_comment = self.handle_pull_request_opened_event(event_info, pr, req_chatlevel=ChatLevels.MINIMAL)
        if issue_comment:
            return f"\n  - added comment {issue_comment.html_url} to show configuration"

    def handle_bot_command_status(self, event_info, bot_command):
        """
        Handles bot command 'status' by querying the github API
        for the comments in a pr.

        Args:
            event_info (dict): event received by event_handler
            bot_command (EESSIBotCommand): command to be handled

        Returns:
            (string): list item with a link to the issue comment that was created
                containing the status overview
        """
        self.log("processing bot command 'status'")
        repo_name = event_info['raw_request_body']['repository']['full_name']
        pr_number = event_info['raw_request_body']['issue']['number']
        status_table = request_bot_build_issue_comments(repo_name, pr_number)

        if 'last_build' in bot_command.general_args:
            # If the bot command is something like 'bot:status =last_build', then only retain the last build for each
            # architecture in the status_table
            # To do this, we first insert a timestamp to facilitate sorting by time
            # Then, we obtain sorting indices that first sort by architecture, then by build time
            # Then, we reverse the sorting, so that the last build (highest timestamp) for each archictecture occurs
            # first.
            # Finally, we copy the table, but each time we encounter an entry for an architecture that we've already
            # copied, we ignore it, since - as a result of the sorting - the second entry is always older than the
            # first
            dates = status_table['date']
            status = status_table['status']
            timestamps = []
            for date, state in zip(dates, status):
                if state == 'finished':
                    date_object = datetime.strptime(date, "%b %d %X %Z %Y")
                    timestamps.append(int(date_object.timestamp()))
                else:
                    # Add the oldest date possible, so that ongoing builds only show up if there was no other
                    # completed build yet
                    timestamps.append(0)

            status_table['timestamp'] = timestamps

            # Figure out the sorting indices, so that things are sorted first by the 'for arch', and then by 'date'
            sorted_indices = sorted(
                range(len(status_table['for arch'])),
                key=lambda x: (status_table['for arch'][x], status_table['timestamp'][x])
            )
            # Reverse, so that the newest builds are first
            sorted_indices.reverse()
            # Apply the sorted indices to get a sorted table
            sorted_table = {key: [status_table[key][i] for i in sorted_indices] for key in status_table}
            self.log(f"Sorted status table: {sorted_table}")

            # Keep only the first entry for each 'for arch', as that is now the newest
            status_table_last = {
                'on arch': [], 'for arch': [], 'for repo': [], 'date': [], 'status': [], 'url': [], 'result': []
            }
            for x in range(0, len(sorted_table['date'])):
                if sorted_table['for arch'][x] not in status_table_last['for arch']:
                    self.log(f"arch: {sorted_table['for arch'][x]} not yet in status_table_last")
                    for key in status_table_last:
                        self.log(f"Adding to '{key}' and the value {sorted_table[key][x]}")
                        status_table_last[key].append(sorted_table[key][x])

            # Re-sort, now only on 'for arch', for nicer viewing
            sorted_indices = sorted(
                range(len(status_table_last['for arch'])),
                key=lambda x: status_table_last['for arch'][x]
            )
            sorted_table_last = {key: [status_table_last[key][i] for i in sorted_indices] for key in status_table_last}

            # overwrite the original status_table
            status_table = sorted_table_last

        comment_status = ''
        comment_status += "\nThis is the status of all the `bot: build` commands:"
        comment_status += "\n|on|for|repo|result|date|status|url|"
        comment_status += "\n|----|----|----|------|----|------|---|"
        for x in range(0, len(status_table['date'])):
            comment_status += f"\n|{status_table['on arch'][x]}|"
            comment_status += f"{status_table['for arch'][x]}|"
            comment_status += f"{status_table['for repo'][x]}|"
            comment_status += f"{status_table['result'][x]}|"
            comment_status += f"{status_table['date'][x]}|"
            comment_status += f"{status_table['status'][x]}|"
            comment_status += f"{status_table['url'][x]}|"

        self.log(f"Overview of finished builds: comment '{comment_status}'")
        issue_comment = create_comment(repo_name, pr_number, comment_status, ChatLevels.MINIMAL)
        if issue_comment:
            return f"\n  - added status comment {issue_comment.html_url}"
        else:
            return "\n  - failed to create status comment"

    def start(self, app, port=3000):
        """
        Logs startup information to shell and log file and starts the app using
        waitress.

        Args:
            app (EESSIBotSoftwareLayer): instance of class EESSIBotSoftwareLayer
            port (int, optional): defaults to 3000

        Returns:
            None (implictly), Note it only returns once the call to waitress has
                terminated.
        """
        start_msg = "EESSI bot for software layer started!"
        print(start_msg)
        self.log(start_msg)
        port_info = "app is listening on port %s" % port
        print(port_info)
        self.log(port_info)

        log_file_info = "logging in to %s" % self.logfile
        print(log_file_info)
        self.log(log_file_info)
        waitress.serve(app, listen='*:%s' % port)

    def handle_pull_request_closed_event(self, event_info, pr):
        """
        Handle events of type pull_request with the action 'closed'. It
        determines used by the PR and moves them to the trash_bin. It also adds
        information to the logs and a comment to the PR.

        Args:
        event_info (dict): event received by event_handler
        pr (github.PullRequest.PullRequest): instance representing the pull request

        Returns:
        github.IssueComment.IssueComment instance or None (note, github refers to
        PyGithub, not the github from the internal connections module)
        """

        # Detect event and report if PR was merged or closed
        request_body = event_info['raw_request_body']
        # next value: True -> PR merged, False -> PR closed
        mergedOrClosed = request_body['pull_request']['merged']
        status = "merged" if mergedOrClosed else "closed"

        self.log(f"PR {pr.number}: PR got {status} (json value: {mergedOrClosed})")

        # 1) determine the jobs that have been run for the PR
        self.log(f"PR {pr.number}: determining directories to be moved to trash bin")
        job_dirs = determine_job_dirs(pr.number)

        if job_dirs == []:
            self.log(f"PR {pr.number}: No job directories found; nothing to move.")
        else:
            # 2) Get trash_bin_dir from configs
            trash_bin_root_dir = self.cfg[config.SECTION_CLEAN_UP][config.CLEAN_UP_SETTING_TRASH_BIN_ROOT_DIR]

            repo_name = request_body['repository']['full_name']
            dt_start = datetime.now(timezone.utc)
            trash_bin_dir = "/".join([trash_bin_root_dir, repo_name, dt_start.strftime('%Y.%m.%d')])

            # Subdirectory with date of move. Also with repository name. Handle symbolic links (later?)
            # cron job deletes symlinks?

            # 3) move the directories to the trash_bin
            self.log(f"PR {pr.number}: moving directories to trash bin {trash_bin_dir}")
            move_to_trash_bin(trash_bin_dir, job_dirs)
            dt_end = datetime.now(timezone.utc)
            dt_delta = dt_end - dt_start
            seconds_elapsed = dt_delta.days * 24 * 3600 + dt_delta.seconds
            self.log(f"PR {pr.number}: moved directories to trash bin {trash_bin_dir} (took {seconds_elapsed} seconds)")

            # 4) report move to pull request

            repo_name = pr.base.repo.full_name
            clean_up_comment = self.cfg[config.SECTION_CLEAN_UP][config.CLEAN_UP_SETTING_MOVED_JOB_DIRS_COMMENT]
            moved_comment = clean_up_comment.format(job_dirs=job_dirs, trash_bin_dir=trash_bin_dir)
            issue_comment = create_comment(repo_name, pr.number, moved_comment, ChatLevels.CHATTY)
            return issue_comment


def main():
    """
    Main function which parses command line arguments, verifies if required
    configuration settings are defined, creates an instance of EESSIBotSoftwareLayer
    and starts it.
    """
    opts = event_handler_parse()

    # config is read and checked for settings to raise an exception early when the event_handler starts.
    if config.check_cfg_settings(REQUIRED_CONFIG):
        print("Configuration check: PASSED")
    else:
        print("Configuration check: FAILED")
        sys.exit(1)
    github.connect()

    if opts.file:
        app = create_app(klass=EESSIBotSoftwareLayer)
        event = read_event_from_json(opts.file)
        event_info = get_event_info(event)
        app.handle_event(event_info)
    elif opts.cron:
        app.log("Running in cron mode")
    else:
        # Run as web app
        app = create_app(klass=EESSIBotSoftwareLayer)
        app.start(app, port=opts.port)


if __name__ == '__main__':
    main()
