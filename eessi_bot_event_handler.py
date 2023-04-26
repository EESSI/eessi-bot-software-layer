#!/usr/bin/env python3
#
# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Kenneth Hoste (@boegel)
# author: Bob Droege (@bedroge)
# author: Hafsa Naeem (@hafsa-naeem)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#
import json
import os
import waitress
import sys
import tasks.build as build

from connections import github
from tools import config
from tools.args import event_handler_parse
from tasks.build import check_build_permission, submit_build_jobs, get_repo_cfg
from tasks.deploy import deploy_built_artefacts

from pyghee.lib import PyGHee, create_app, get_event_info, read_event_from_json
from pyghee.utils import log

from requests.structures import CaseInsensitiveDict
from collections import namedtuple


class EESSIBotSoftwareLayer(PyGHee):

    def __init__(self, *args, **kwargs):
        """
        EESSIBotSoftwareLayer constructor.
        """
        super(EESSIBotSoftwareLayer, self).__init__(*args, **kwargs)

        self.cfg = config.read_config()
        event_handler_cfg = self.cfg['event_handler']
        self.logfile = event_handler_cfg.get('log_path')

    def log(self, msg, *args):
        """
        Logs a message incl the caller's function name by passing msg and *args to PyGHee's log method.

        Args:
            msg (string): message (format) to log to event handler log
            *args (any): any values to be substituted into msg
        """
        funcname = sys._getframe().f_back.f_code.co_name
        if args:
            msg = msg % args
        msg = "[%s]: %s" % (funcname, msg)
        log(msg, log_file=self.logfile)

    def handle_issue_comment_event(self, event_info, log_file=None):
        """
        Handle adding/removing of comment in issue or PR.
        """
        request_body = event_info['raw_request_body']
        issue_url = request_body['issue']['url']
        comment_author = request_body['comment']['user']['login']
        comment_txt = request_body['comment']['body']
        if comment_txt.lower()[:6] == "replay":
            self.replay_event(comment_txt[7:])
        self.log("Comment posted in %s by @%s: %s", issue_url, comment_author, comment_txt)
        self.log("issue_comment event handled!")

    def handle_installation_event(self, event_info, log_file=None):
        """
        Handle installation of app.
        """
        request_body = event_info['raw_request_body']
        user = request_body['sender']['login']
        action = request_body['action']
        # repo_name = request_body['repositories'][0]['full_name'] # not every action has that attribute
        self.log("App installation event by user %s with action '%s'", user, action)
        self.log("installation event handled!")

    def handle_pull_request_labeled_event(self, event_info, pr):
        """
        Handle adding of a label to a pull request.
        """

        # determine label
        label = event_info['raw_request_body']['label']['name']
        self.log("Process PR labeled event: PR#%s, label '%s'", pr.number, label)

        if label == "bot:build":
            # run function to build software stack
            if check_build_permission(pr, event_info):
                submit_build_jobs(pr, event_info)

        elif label == "bot:deploy":
            # run function to deploy built artefacts
            deploy_built_artefacts(pr, event_info)
        else:
            self.log("handle_pull_request_labeled_event: no handler for label '%s'", label)

    def handle_pull_request_opened_event(self, event_info, pr):
        """
        Handle opening of a pull request.
        """
        self.log("PR opened: waiting for label bot:build")
        app_name = self.cfg['github']['app_name']
        # TODO check if PR already has a comment with arch targets and
        # repositories
        repo_cfg = get_repo_cfg(self.cfg)
        comment = f"Instance `{app_name}` is configured to build:"
        for arch in repo_cfg['repo_target_map'].keys():
            for repo_id in repo_cfg['repo_target_map'][arch]:
                comment += f"\n- arch `{'/'.join(arch.split('/')[1:])}` for repo `{repo_id}`"

        self.log(f"PR opened: comment '{comment}'")

        # create comment to pull request
        repo_name = pr.base.repo.full_name
        gh = github.get_instance()
        repo = gh.get_repo(repo_name)
        pull_request = repo.get_pull(pr.number)
        pull_request.create_issue_comment(comment)

    def handle_pull_request_event(self, event_info, log_file=None):
        """
        Handle 'pull_request' event
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

    def replay_event(self, event_id):
        """Replay an event stored in the file system

        Args:
            event_id (string): The id of the event that should be replayed
        """
        event = namedtuple('Request', ['headers', 'json', 'data'])

        for (dir, _subdirs, files) in os.walk("."):
            if any([event_id in file for file in files]):
                with open(f"{dir}/{event_id}_headers.json", 'r') as jf:
                    headers = json.load(jf)
                    event.headers = CaseInsensitiveDict(headers)
                with open(f"{dir}/{event_id}_body.json", 'r') as jf:
                    body = json.load(jf)
                    event.json = body

        event_info = get_event_info(event)
        self.handle_event(event_info)

    def start(self, app, port=3000):
        """starts the app and log information in the log file

        Args:
            app (object): instance of class EESSIBotSoftwareLayer
            port (int, optional): Defaults to 3000.
        """
        start_msg = "EESSI bot for software layer started!"
        print(start_msg)
        self.log(start_msg)
        port_info = "app is listening on port %s" % port
        print(port_info)
        self.log(port_info)

        event_handler_cfg = self.cfg['event_handler']
        my_logfile = event_handler_cfg.get('log_path')
        log_file_info = "logging in to %s" % my_logfile
        print(log_file_info)
        self.log(log_file_info)
        waitress.serve(app, listen='*:%s' % port)


def main():
    """Main function."""
    opts = event_handler_parse()

    required_config = {
        build.SUBMITTED_JOB_COMMENTS: [build.INITIAL_COMMENT, build.AWAITS_RELEASE]
    }
    # config is read and checked for settings to raise an exception early when the event_handler starts.
    config.check_required_cfg_settings(required_config)
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
