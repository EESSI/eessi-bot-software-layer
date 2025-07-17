#!/usr/bin/env python3
#
# (Slurm) job manager for the GitHub App for the EESSI project
#
# This tool monitors EESSI build jobs and acts on state changes of
# these jobs. It releases jobs initially held, it processes running and
# finished jobs and reports status changes/results back to the
# corresponding GitHub pull request to a target software-layer repository.
#
# EESSI build jobs are recognised by
#  - being submitted in JobUserHeld status (sbatch parameter --hold)
#  - job ids listed in a specific directory (ids being symlinks to job
#    directories created by EESSI bot)
#  - a metadata file in the job's working directory
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
# author: Jacob Ziemke (@jacobz137)
# author: Jonas Qvigstad (@jonas-lq)
# author: Lara Ramona Peeters (@laraPPr)
# author: Richard Topouchian (@TopRichard)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
from datetime import datetime, timezone
import os
import re
import sys
import time

# Third party imports (anything installed into the local Python environment)
from pyghee.utils import log

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from connections import github
from tools import config, job_metadata, run_cmd
from tools.args import job_manager_parse
from tools.pr_comments import get_submitted_job_comment, update_comment


# settings that are required in 'app.cfg'
REQUIRED_CONFIG = {
    config.SECTION_BUILDENV: [
        config.BUILDENV_SETTING_JOB_HANDOVER_PROTOCOL,                # required
        config.BUILDENV_SETTING_JOB_NAME],                            # required
    config.SECTION_FINISHED_JOB_COMMENTS: [
        config.FINISHED_JOB_COMMENTS_SETTING_JOB_RESULT_UNKNOWN_FMT,  # required
        config.FINISHED_JOB_COMMENTS_SETTING_JOB_TEST_UNKNOWN_FMT],   # required
    config.SECTION_GITHUB: [
        config.GITHUB_SETTING_APP_ID,                                 # required
        # config.GITHUB_SETTING_APP_NAME,                               # unused
        config.GITHUB_SETTING_INSTALLATION_ID,                        # required
        config.GITHUB_SETTING_PRIVATE_KEY],                           # required
    config.SECTION_JOB_MANAGER: [
        config.JOB_MANAGER_SETTING_LOG_PATH,                          # required
        config.JOB_MANAGER_SETTING_JOB_IDS_DIR,                       # required
        config.JOB_MANAGER_SETTING_POLL_COMMAND,                      # required
        config.JOB_MANAGER_SETTING_POLL_INTERVAL,                     # optional+recommended
        config.JOB_MANAGER_SETTING_SCONTROL_COMMAND],                 # required
    config.SECTION_NEW_JOB_COMMENTS: [
        config.NEW_JOB_COMMENTS_SETTING_AWAITS_LAUNCH],               # required
    config.SECTION_RUNNING_JOB_COMMENTS: [
        config.RUNNING_JOB_COMMENTS_SETTING_RUNNING_JOB]              # required
    }


class EESSIBotSoftwareLayerJobManager:
    """
    Class for representing the job manager of the build-and-deploy bot. It
    monitors the job queue and processes job state changes.
    """

    def __init__(self):
        """
        EESSIBotSoftwareLayerJobManager constructor. Just reads the
        configuration to set the path to the logfile.
        """
        cfg = config.read_config()
        job_manager_cfg = cfg[config.SECTION_JOB_MANAGER]
        self.logfile = job_manager_cfg.get(config.JOB_MANAGER_SETTING_LOG_PATH)
        buildenv_cfg = cfg[config.SECTION_BUILDENV]
        self.job_name = buildenv_cfg.get(config.BUILDENV_SETTING_JOB_NAME)
        if self.job_name and len(self.job_name) < 3:
            raise Exception(f"job name ({self.job_name}) is shorter than 3 characters")
        self.job_handover_protocol = buildenv_cfg.get(config.BUILDENV_SETTING_JOB_HANDOVER_PROTOCOL)
        if self.job_handover_protocol not in config.JOB_HANDOVER_PROTOCOLS_SET:
            raise Exception(f"job handover protocol ({self.job_handover_protocol}) is unknown")

    def get_current_jobs(self):
        """
        Obtains a list of jobs currently managed by the batch system.
        Retains key information about each job such as its id and its state.

        Args:
            No arguments

        Returns:
            (dict): maps a job id to a dictionary containing key information
                about a job (currently: 'jobid', 'state' and 'reason')

        Raises:
            Exception: if the environment variable USER is not set
        """
        username = os.getenv('USER', None)
        if username is None:
            raise Exception("Unable to find username")

        squeue_cmd = "%s --long --noheader --user=%s" % (self.poll_command, username)
        if self.job_name:
            squeue_cmd += " --name='%s'" % self.job_name
        # Format the output of SLURM
        squeue_cmd += " --Format JobId:100@,Cluster:100@,Partition:100@,State:100@,Reason:100"
        squeue_output, squeue_err, squeue_exitcode = run_cmd(
            squeue_cmd,
            "get_current_jobs(): squeue command",
            log_file=self.logfile,
        )

        # create dictionary of jobs from output of 'squeue_cmd'
        # with the following information per job: jobid, state,
        # nodelist_reason
        current_jobs = {}
        lines = str(squeue_output).rstrip().split("\n")
        bad_state_messages = {
            "F": "Failure",
            "OOM": "Out of Memory",
            "TO": "Time Out",
        }

        # get job info, logging any Slurm issues
        # Note, all output lines of squeue are processed because we run it with
        # --noheader.
        for line in lines:
            job = line.rstrip().split('@')
            if len(job) == 5:
                job_id = job[0].rstrip()
                state = job[3].rstrip()
                current_jobs[job_id] = {
                    "jobid": job_id,
                    "cluster": job[1].rstrip(),
                    "partition": job[2].rstrip(),
                    "state": state,
                    "reason": job[4].rstrip(),
                }
                if state in bad_state_messages:
                    log("Job {} in state {}: {}".format(job_id, state, bad_state_messages[state]))

        return current_jobs

    def determine_running_jobs(self, current_jobs):
        """
        Determine currently running jobs.

        Args:
            current_jobs (dict): dictionary containing data of current jobs

        Returns:
            (list): list of ids of currently running jobs
        """
        running_jobs = []
        for job in current_jobs.values():
            if job["state"] == "RUNNING":
                running_jobs.append(job["jobid"])
        return running_jobs

    def get_known_jobs(self):
        """
        Obtain information about jobs that should be known to the job manager
        (e.g., before it stopped or when it is resumed after a crash). This
        method obtains the information from a local store (database or
        filesystem). When comparing its results to the list of jobs currently
        registered with the job management system (see method
        get_current_jobs()), new jobs and finished jobs can be derived.

        Args:
            No arguments

        Returns:
            (dict): maps a job id to a dictionary containing key information
                about a job (currently: 'jobid')
        """
        # find all symlinks resembling job ids (digits only) in
        # self.submitted_jobs_dir (the symlink is created by method
        # process_new_job)
        known_jobs = {}
        if os.path.isdir(self.submitted_jobs_dir):
            regex = re.compile(r"(\d)+")
            for fname in os.listdir(self.submitted_jobs_dir):
                if regex.match(fname):
                    full_path = os.path.join(self.submitted_jobs_dir, fname)
                    if os.path.islink(full_path):
                        known_jobs[fname] = {"jobid": fname}
                    else:
                        log(
                            "get_known_jobs(): entry %s in %s"
                            " is not recognised as a symlink"
                            % (full_path, self.submitted_jobs_dir),
                            self.logfile,
                        )
                else:
                    log(
                        "get_known_jobs(): entry %s in %s "
                        "doesn't match regex" %
                        (fname, self.submitted_jobs_dir),
                        self.logfile,
                    )
        else:
            log(
                "get_known_jobs(): directory '%s' "
                "does not exist -> assuming no jobs known previously"
                % self.submitted_jobs_dir,
                self.logfile,
            )

        return known_jobs

    def determine_new_jobs(self, known_jobs, current_jobs):
        """
        Determine which jobs are new.

        Args:
            known_jobs (dict): dictionary with information about jobs that are
                already known/seen from before
            current_jobs (dict): dictionary with information about jobs that are
                currently registered with the job management system

        Returns:
            (list): list of ids of new jobs
        """
        new_jobs = []
        for ckey in current_jobs:
            if ckey not in known_jobs:
                new_jobs.append(ckey)

        return new_jobs

    def determine_finished_jobs(self, known_jobs, current_jobs):
        """
        Determine which jobs have finished.

        Args:
            known_jobs (dict): dictionary with information about jobs that are
                already known/seen from before
            current_jobs (dict): dictionary with information about jobs that are
                currently registered with the job management system

        Returns:
            (list): list of ids of finished jobs
        """
        finished_jobs = []
        for kkey in known_jobs:
            if kkey not in current_jobs:
                finished_jobs.append(kkey)

        return finished_jobs

    def parse_scontrol_show_job_output(self, output):
        """
        The output of 'scontrol --oneliner show job' is a list of key=value pairs
        separated by whitespaces.

        Args:
            output (string): the output of the scontrol command

        Returns:
            (dict): Returns a dictionary of the key-value pairs
        """
        job_info = {}
        stripped_output = output.strip()
        for pair in stripped_output.split():
            key, value = pair.split('=', 1)
            job_info[key] = value

        return job_info

    def process_new_job(self, new_job):
        """
        Process a new job by verifying that it is a bot job and if so
        - create symlink in submitted_jobs_dir (destination is the working
            dir of the job derived via scontrol)
        - release the job (so it may be started by the scheduler)
        - update the PR comment by adding its new status (released)

        Args:
            new_job (dict): dictionary storing key information about the job

        Returns:
            (bool): True if method completed the tasks described, False if job
                is not a bot job
        """
        job_id = new_job["jobid"]

        # check if their is a placeholder value in the scontrol_command
        if bool(re.search(r'%\([^)]+\)s', self.scontrol_command)):
            placeholders = re.findall(r'%\(([^)]+)\)s', self.scontrol_command)
            for placeholder in placeholders:
                if placeholder == 'new_job["cluster"]':
                    self.scontrol_command = self.scontrol_command % {placeholder: new_job["cluster"]}
        scontrol_cmd = "%s --oneliner show jobid %s" % (
            self.scontrol_command,
            job_id,
        )
        scontrol_output, scontrol_err, scontrol_exitcode = run_cmd(
            scontrol_cmd,
            "process_new_job(): scontrol command",
            log_file=self.logfile,
        )

        # parse output of 'scontrol_cmd'
        job_info = self.parse_scontrol_show_job_output(str(scontrol_output))

        # check if job_info contains 'WorkDir', if not we cannot process the job
        # further
        if 'WorkDir' in job_info:
            log(
                "process_new_job(): work dir of job %s: '%s'"
                % (job_id, job_info['WorkDir']),
                self.logfile,
            )

            job_metadata_path = "%s/_bot_job%s.metadata" % (
                job_info['WorkDir'],
                job_id,
            )

            # assuming that a bot job's working directory contains a metadata
            # file, its existence is used to check if the job belongs to the bot
            metadata_pr = job_metadata.get_section_from_file(job_metadata_path,
                                                             job_metadata.JOB_PR_SECTION,
                                                             self.logfile)

            if metadata_pr is None:
                log(f"No metadata file found at {job_metadata_path} for job {job_id}, so skipping it",
                    self.logfile)
                return False

            symlink_source = os.path.join(self.submitted_jobs_dir, job_id)
            log(
                "process_new_job(): create a symlink: %s -> %s"
                % (symlink_source, job_info['WorkDir']),
                self.logfile,
            )
            os.symlink(job_info['WorkDir'], symlink_source)

            # handle different job handover protocols
            #   *_HOLD_RELEASE: job was submitted with '--hold' and shall be
            #                   released with 'scontrol release JOB_ID'
            #   *_DELAYED_BEGIN: job was submitted with '--begin=now+SOMEDELAY',
            #                   no extra action is needed
            job_status = ''
            extra_info = ''
            if self.job_handover_protocol == config.JOB_HANDOVER_PROTOCOL_HOLD_RELEASE:
                release_cmd = "%s release %s" % (
                    self.scontrol_command,
                    job_id,
                )

                release_output, release_err, release_exitcode = run_cmd(
                    release_cmd,
                    "process_new_job(): scontrol command",
                    log_file=self.logfile,
                )
                job_status = 'released'
                extra_info = ''
            elif self.job_handover_protocol == config.JOB_HANDOVER_PROTOCOL_DELAYED_BEGIN:
                job_status = 'received'
                extra_info = " (eligible to start from {job_info['EligibleTime'})"

            # update PR defined by repo and pr_number stored in the job's
            # metadata file
            repo_name = metadata_pr.get("repo", "")
            pr_number = metadata_pr.get("pr_number", None)

            gh = github.get_instance()

            repo = gh.get_repo(repo_name)
            pr = repo.get_pull(int(pr_number))

            # find & get comment for this job
            # only get comment if we don't know its id yet
            if "comment_id" not in new_job:
                new_job_cmnt = get_submitted_job_comment(pr, new_job['jobid'])

                if new_job_cmnt:
                    log(
                        "process_new_job(): found comment with id %s"
                        % new_job_cmnt.id,
                        self.logfile,
                    )
                    new_job["comment_id"] = new_job_cmnt.id

            # update status table if we found a comment
            if "comment_id" in new_job:
                new_job_comments_cfg = config.read_config()[config.SECTION_NEW_JOB_COMMENTS]
                dt = datetime.now(timezone.utc)
                update = "\n|%s|%s|" % (dt.strftime("%b %d %X %Z %Y"), job_status)
                description_col_fmt = new_job_comments_cfg[config.NEW_JOB_COMMENTS_SETTING_AWAITS_LAUNCH]
                update += f"{description_col_fmt.format(extra_info=extra_info)}|"
                update_comment(new_job["comment_id"], pr, update)
            else:
                log(
                    "process_new_job(): did not obtain/find a comment"
                    " for job '%s'" % job_id,
                    self.logfile,
                )
        else:
            log(
                "process_new_job(): did not find work dir for job '%s'"
                % job_id,
                self.logfile,
            )

        return True

    def process_running_jobs(self, running_job):
        """
        Process a running job by verifying that it is a bot job and if so
        - determines the PR comment body and id corresponding to the job,
        - updates the PR comment (if found)

        Args:
            running_job (dict): dictionary containing data of the running jobs

        Returns:
            None (implicitly)

        Raises:
            Exception: if there is no metadata file or reading it failed
        """

        gh = github.get_instance()

        # set variable for accessing the working directory of the job
        job_dir = os.path.join(self.submitted_jobs_dir, running_job["jobid"])

        metadata_file = "_bot_job%s.metadata" % running_job["jobid"]
        job_metadata_path = os.path.join(job_dir, metadata_file)

        # check if metadata file exist
        metadata_pr = job_metadata.get_section_from_file(job_metadata_path,
                                                         job_metadata.JOB_PR_SECTION,
                                                         self.logfile)
        if metadata_pr is None:
            raise Exception("Unable to find metadata file")

        repo_name = metadata_pr.get("repo", "")
        pr_number = metadata_pr.get("pr_number", None)

        repo = gh.get_repo(repo_name)
        pullrequest = repo.get_pull(int(pr_number))

        # determine comment to be updated
        if "comment_id" not in running_job:
            running_job_cmnt = get_submitted_job_comment(pullrequest, running_job['jobid'])

            if running_job_cmnt:
                log(
                    "process_running_job(): found comment with id %s"
                    % running_job_cmnt.id,
                    self.logfile,
                )
                running_job["comment_id"] = running_job_cmnt.id
                running_job["comment_body"] = running_job_cmnt.body

        if "comment_id" in running_job:
            dt = datetime.now(timezone.utc)
            running_job_comments_cfg = config.read_config()[config.SECTION_RUNNING_JOB_COMMENTS]
            running_msg_fmt = running_job_comments_cfg[config.RUNNING_JOB_COMMENTS_SETTING_RUNNING_JOB]
            running_msg = running_msg_fmt.format(job_id=running_job['jobid'])
            if "comment_body" in running_job and running_msg in running_job["comment_body"]:
                log("Not updating comment, '%s' already found" % running_msg)
            else:
                update = f"\n|{dt.strftime('%b %d %X %Z %Y')}|running|"
                update += f"{running_msg}|"
                update_comment(running_job["comment_id"], pullrequest, update)
        else:
            log(
                "process_running_job(): did not obtain/find a comment"
                " for job '%s'" % running_job['jobid'],
                self.logfile,
            )

    def process_finished_job(self, finished_job):
        """
        Process a finished job by
        - moving the symlink to the directory storing finished jobs,
        - updating the PR comment with information from '*.result' and '*.test'
          files

        Args:
            finished_job (dict): dictionary with information about the job

        Returns:
            None (implicitly)

        Raises:
            Exception: if there is no metadata file or reading it failed
        """
        fn = sys._getframe().f_code.co_name

        job_id = finished_job['jobid']

        # move symlink from job_ids_dir/submitted to jobs_ids_dir/finished
        old_symlink = os.path.join(self.submitted_jobs_dir, job_id)

        finished_jobs_dir = os.path.join(self.job_ids_dir, "finished")
        os.makedirs(finished_jobs_dir, exist_ok=True)

        new_symlink = os.path.join(finished_jobs_dir, job_id)

        log(f"{fn}(): os.rename({old_symlink},{new_symlink})", self.logfile)
        os.rename(old_symlink, new_symlink)

        # REPORT status (to logfile in any case, to PR comment if accessible)
        #  - rely fully on what bot/check-build.sh and bot/check-test.sh have
        #    returned
        #  - check if file _bot_jobJOBID.result exists --> if so read it and
        #    update PR comment
        #    . contents of *.result file (here we only use section [RESULT])
        #      [RESULT]
        #      comment_description = _FULLY_DEFINED_UPDATE_TO_PR_COMMENT_
        #      status = {SUCCESS,FAILURE,UNKNOWN}
        #      artefacts = _LIST_OF_ARTEFACTS_TO_BE_DEPLOYED_
        #  - check if file _bot_jobJOBID.test exists --> if so read it and
        #    update PR comment
        #    . contents of *.test file (here we only use section [TEST])
        #      [TEST]
        #      comment_description = _FULLY_DEFINED_UPDATE_TO_PR_COMMENT_
        #      status = {SUCCESS,FAILURE,UNKNOWN}

        # obtain format templates from app.cfg
        finished_job_comments_cfg = config.read_config()[config.SECTION_FINISHED_JOB_COMMENTS]

        # check if _bot_jobJOBID.result exits
        job_result_file = f"_bot_job{job_id}.result"
        job_result_file_path = os.path.join(new_symlink, job_result_file)
        job_results = job_metadata.get_section_from_file(job_result_file_path,
                                                         job_metadata.JOB_RESULT_SECTION,
                                                         self.logfile)

        job_result_unknown_fmt = finished_job_comments_cfg[config.FINISHED_JOB_COMMENTS_SETTING_JOB_RESULT_UNKNOWN_FMT]
        # set fallback comment_description in case no result file was found
        # (job_metadata.get_section_from_file returned None)
        comment_description = job_result_unknown_fmt.format(filename=job_result_file)
        if job_results:
            # get preformatted comment_description or use previously set default for unknown
            comment_description = job_results.get(job_metadata.JOB_RESULT_COMMENT_DESCRIPTION, comment_description)

        # report to log
        log(f"{fn}(): finished job {job_id}\n"
            f"########\n"
            f"comment_description: {comment_description}\n"
            f"########\n", self.logfile)

        dt = datetime.now(timezone.utc)

        comment_update = f"\n|{dt.strftime('%b %d %X %Z %Y')}|finished|"
        comment_update += f"{comment_description}|"

        # check if _bot_jobJOBID.test exits
        # TODO if not found, assume test was not run (or failed, or ...) and add
        # a message noting that ('not tested' + 'test suite not run or failed')
        # --> bot/test.sh and bot/check-test.sh scripts are run in job script used by bot for 'build' action
        job_test_file = f"_bot_job{job_id}.test"
        job_test_file_path = os.path.join(new_symlink, job_test_file)
        job_tests = job_metadata.get_section_from_file(job_test_file_path,
                                                       job_metadata.JOB_TEST_SECTION,
                                                       self.logfile)

        job_test_unknown_fmt = finished_job_comments_cfg[config.FINISHED_JOB_COMMENTS_SETTING_JOB_TEST_UNKNOWN_FMT]
        # set fallback comment_description in case no test file was found
        # (job_metadata.get_section_from_file returned None)
        comment_description = job_test_unknown_fmt.format(filename=job_test_file)
        if job_tests:
            # get preformatted comment_description or use previously set default for unknown
            comment_description = job_tests.get(job_metadata.JOB_TEST_COMMENT_DESCRIPTION, comment_description)

        # report to log
        log(f"{fn}(): finished job {job_id}, test suite result\n"
            f"########\n"
            f"comment_description: {comment_description}\n"
            f"########\n", self.logfile)

        dt = datetime.now(timezone.utc)

        comment_update += f"\n|{dt.strftime('%b %d %X %Z %Y')}|test result|"
        comment_update += f"{comment_description}|"

        # obtain id of PR comment to be updated (from file '_bot_jobID.metadata')
        metadata_file = f"_bot_job{job_id}.metadata"
        job_metadata_path = os.path.join(new_symlink, metadata_file)
        metadata_pr = job_metadata.get_section_from_file(job_metadata_path,
                                                         job_metadata.JOB_PR_SECTION,
                                                         self.logfile)
        if metadata_pr is None:
            raise Exception("Unable to find metadata file ... skip updating PR comment")

        repo_name = metadata_pr.get("repo", None)
        pr_number = metadata_pr.get("pr_number", -1)
        pr_comment_id = metadata_pr.get("pr_comment_id", -1)
        log(f"{fn}(): pr comment id {pr_comment_id}", self.logfile)

        gh = github.get_instance()

        repo = gh.get_repo(repo_name)
        pull_request = repo.get_pull(int(pr_number))

        update_comment(int(pr_comment_id), pull_request, comment_update)

        return


def main():
    """
    Main function which parses command line arguments, verifies if required
    configuration settings are defined, creates an instance of
    EESSIBotSoftwareLayerJobManager, reads the configuration to initialize
    core attributes, determines known jobs and starts the main loop that
    monitors jobs.
    """

    opts = job_manager_parse()

    # config is read and checked for settings to raise an exception early when
    # the job_manager runs
    if config.check_required_cfg_settings(REQUIRED_CONFIG):
        print("Configuration check: PASSED")
    else:
        print("Configuration check: FAILED")
        sys.exit(1)
    github.connect()

    job_manager = EESSIBotSoftwareLayerJobManager()
    job_manager.job_filter = {}
    if opts.jobs is not None:
        job_manager.job_filter = {jobid: None
                                  for jobid in opts.jobs.split(",")}

    log(
        "job manager just started, logging to '%s', processing job ids '%s'"
        % (job_manager.logfile, ",".join(job_manager.job_filter.keys())),
        job_manager.logfile,
    )
    print(
        "job manager just started, logging to '%s', processing job ids '%s'"
        % (job_manager.logfile, ",".join(job_manager.job_filter.keys()))
    )

    # before main loop, get list of known jobs (stored on disk)
    # main loop
    # ---------
    #  get current jobs of the bot user (job id, state, reason)
    #  determine new jobs (comparing known and current jobs)
    #  process new jobs (filtered by optional command line option)
    #  determine running jobs (comparing known and current jobs)
    #  process running jobs (filtered by optional command line option)
    #  determine finished jobs (comparing known and current jobs)
    #  process finished jobs (filtered by optional command line option)
    #  set known jobs to list of current jobs
    #  wait configurable period before next iteration begins

    max_iter = int(opts.max_manager_iterations)
    # retrieve some settings from app.cfg
    job_manager.job_ids_dir = ""
    job_manager.submitted_jobs_dir = ""
    job_manager.poll_command = "false"
    poll_interval = 0
    job_manager.scontrol_command = ""
    if max_iter != 0:
        cfg = config.read_config()
        job_mgr = cfg[config.SECTION_JOB_MANAGER]
        job_manager.job_ids_dir = job_mgr.get(config.JOB_MANAGER_SETTING_JOB_IDS_DIR)
        job_manager.submitted_jobs_dir = os.path.join(
            job_manager.job_ids_dir, "submitted"
        )
        job_manager.poll_command = job_mgr.get(config.JOB_MANAGER_SETTING_POLL_COMMAND) or False
        poll_interval = int(job_mgr.get(config.JOB_MANAGER_SETTING_POLL_INTERVAL) or 0)
        if poll_interval <= 0:
            poll_interval = 60
        job_manager.scontrol_command = job_mgr.get(config.JOB_MANAGER_SETTING_SCONTROL_COMMAND) or False
        os.makedirs(job_manager.submitted_jobs_dir, exist_ok=True)

    # max_iter
    #   < 0: run loop indefinitely
    #  == 0: don't run loop
    #   > 0: run loop max_iter times
    # processing may be limited to a list of job ids (see parameter -j --jobs)
    i = 0
    if max_iter != 0:
        known_jobs = job_manager.get_known_jobs()
    while max_iter < 0 or i < max_iter:
        # sleep poll_interval seconds (not for the first iteration)
        if i != 0:
            log(
                "job manager main loop: sleep %d seconds" % poll_interval,
                job_manager.logfile,
            )
            time.sleep(poll_interval)
        log("job manager main loop: iteration %d" % i, job_manager.logfile)
        log(
            "job manager main loop: known_jobs='%s'" % ",".join(
                known_jobs.keys()),
            job_manager.logfile,
        )

        try:
            current_jobs = job_manager.get_current_jobs()
        except RuntimeError:
            i = i + 1
            continue

        log(
            "job manager main loop: current_jobs='%s'" % ",".join(
                current_jobs.keys()),
            job_manager.logfile,
        )

        new_jobs = job_manager.determine_new_jobs(known_jobs, current_jobs)
        log(
            "job manager main loop: new_jobs='%s'" % ",".join(new_jobs),
            job_manager.logfile,
        )
        # process new jobs
        non_bot_jobs = []
        for nj in new_jobs:
            # assume it is not a bot job
            is_bot_job = False
            # apply filtering of job ids
            if not job_manager.job_filter or nj in job_manager.job_filter:
                is_bot_job = job_manager.process_new_job(current_jobs[nj])
            if not is_bot_job:
                # add job id to non_bot_jobs list
                non_bot_jobs.append(nj)

        # remove non bot jobs from current_jobs
        for job in non_bot_jobs:
            current_jobs.pop(job)

        running_jobs = job_manager.determine_running_jobs(current_jobs)
        log(
            "job manager main loop: running_jobs='%s'" %
            ",".join(running_jobs),
            job_manager.logfile,
        )

        for rj in running_jobs:
            # apply filtering of job ids
            if not job_manager.job_filter or rj in job_manager.job_filter:
                job_manager.process_running_jobs(current_jobs[rj])

        finished_jobs = job_manager.determine_finished_jobs(
                        known_jobs, current_jobs)
        log(
            "job manager main loop: finished_jobs='%s'" %
            ",".join(finished_jobs),
            job_manager.logfile,
        )
        # process finished jobs
        for fj in finished_jobs:
            # apply filtering of job ids
            if not job_manager.job_filter or fj in job_manager.job_filter:
                job_manager.process_finished_job(known_jobs[fj])

        known_jobs = current_jobs

        # add one iteration to the loop
        i = i + 1


if __name__ == "__main__":
    main()
