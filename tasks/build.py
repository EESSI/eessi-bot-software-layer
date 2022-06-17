import json
import os
import subprocess
import time
import glob
import re

import pandas as pd

from io import StringIO
from connections import github
from tools import config
from pyghee.utils import log
from datetime import datetime


def process_job_result(pr, event_info, jobid, pr_dir):
    # structure of directory tree
    #   jobs_base_dir/YYYY.MM/pr_<id>/event_<id>/run_<id>/target_<cpuarch>
    #   jobs_base_dir/YYYY.MM/pr_<id>/<jobid> - being a symlink to the job dir
    #   jobs_base_dir/YYYY.MM/pr_<id>/<jobid>/slurm-<jobid>.out

    gh = github.get_instance()

    # seems we have to use `base` here (instead of `head`)
    repo_name = pr.base.repo.full_name
    log("process_job_result: repo_name %s" % repo_name)
    repo = gh.get_repo(repo_name)
    log("process_job_result: pr.number %s" % pr.number)
    pull_request = repo.get_pull(pr.number)

    job_dir = os.path.join(pr_dir,jobid)
    sym_dst = os.readlink(job_dir)
    slurm_out = os.path.join(sym_dst,'slurm-%s.out' % jobid)

    # determine all tarballs that are stored in the job directory (only expecting 1)
    tarball_pattern = 'eessi-*software-*.tar.gz'
    eessi_tarballs = glob.glob(os.path.join(sym_dst,tarball_pattern))

    # set some initial values
    no_missing_modules = False
    targz_created = False

    # check slurm out for the below strings
    #     ^No missing modules!$ --> software successfully installed
    #     ^eessi-2021.12-software-linux-x86_64-intel-haswell-1654294643.tar.gz created!$ --> tarball successfully created
    if os.path.exists(slurm_out):
        re_missing_modules = re.compile('^No missing modules!$')
        re_targz_created = re.compile('^/eessi_bot_job/eessi-.*-software-.*.tar.gz created!$')
        outfile = open(slurm_out, "r")
        for line in outfile:
            if re_missing_modules.match(line):
                # no missing modules
                no_missing_modules = True
            if re_targz_created.match(line):
                # tarball created
                targz_created = True

    if no_missing_modules and targz_created and len(eessi_tarballs) == 1:
        # We've got one tarball and slurm out messages are ok
        # Prepare a message with information such as (installation status, tarball name, tarball size)
        comment = 'SUCCESS The build job (directory %s -> %s) went fine:\n' % (job_dir,sym_dst)
        comment += ' - No missing modules!\n'
        comment += ' - Tarball with size %.3f GiB available at %s.\n' % (os.path.getsize(eessi_tarballs[0])/2**30,eessi_tarballs[0])
        comment += '\nAwaiting approval to ingest this into the repository.\n'
        # report back to PR (just the comment + maybe add a label? (require manual check))
        pull_request.create_issue_comment(comment)
    else:
        # something is not allright:
        #  - no slurm out or
        #  - did not find the messages we expect or
        #  - no tarball or
        #  - more than one tarball
        # prepare a message with details about the above conditions and update PR with a comment
        comment = 'FAILURE The build job (directory %s -> %s) encountered some issues:\n' % (job_dir,sym_dst)
        if not os.path.exists(slurm_out):
            # no slurm out ... something went wrong with the job
            comment += ' - Did not find slurm output file (%s).\n' % slurm_out
        if not no_missing_modules:
            # Found slurm out, but doesn't contain message 'No missing modules!'
            comment += ' - Slurm output file (%s) does not contain pattern: %s.\n' % (slurm_out,re_missing_modules.pattern)
        if not targz_created:
            # Found slurm out, but doesn't contain message 'eessi-.*-software-.*.tar.gz created!'
            comment += ' - Slurm output file (%s) does not contain pattern: %s.\n' % (slurm_out,re_targz_created.pattern)
        if len(eessi_tarballs) == 0:
            # no luck, job just seemed to have failed ...
            comment += ' - No tarball found in %s. (search pattern %s)\n' % (sym_dst,tarball_pattern)
        if len(eessi_tarballs) > 1:
            # something's fishy, we only expected a single tar.gz file
            comment += ' - Found %d tarballs in %s - only 1 expected.\n' % (len(eessi_tarballs),sym_dst)
        comment += '\nIf a tarball has been created, it might still be ok to approve the pull request (e.g., after receiving additional information from the build host).'
        # report back to PR (just the comment + maybe add a label? (require manual check))
        pull_request.create_issue_comment(comment)


def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def build_easystack_from_pr(pr, event_info):
    # retrieving some settings from 'app.cfg' in bot directory
    # [buildenv]
    buildenv = config.get_section('buildenv')
    jobs_base_dir = buildenv.get('jobs_base_dir')
    log("jobs_base_dir '%s'" % jobs_base_dir)
    local_tmp = buildenv.get('local_tmp')
    log("local_tmp '%s'" % local_tmp)
    build_job_script = buildenv.get('build_job_script')
    log("build_job_script '%s'" % build_job_script)
    submit_command = buildenv.get('submit_command')
    log("submit_command '%s'" % submit_command)

    # [architecturetargets]
    arch_target_map = json.loads(config.get_section('architecturetargets').get('arch_target_map'))
    log("arch target map '%s'" % json.dumps(arch_target_map))

    # create directory structure according to alternative described in
    #   https://github.com/EESSI/eessi-bot-software-layer/issues/7
    #   jobs_base_dir/YYYY.MM/pr<id>/event_<id>/run_<id>/target_<cpuarch>
    ym = datetime.today().strftime('%Y.%m')
    pr_id = 'pr_%s' % pr.number
    event_id = 'event_%s' % event_info['id']
    event_dir = os.path.join(jobs_base_dir, ym, pr_id, event_id)
    mkdir(event_dir)

    run = 0
    while os.path.exists(os.path.join(event_dir, 'run_%03d' % run)):
        run += 1
    run_dir = os.path.join(event_dir, 'run_%03d' % run)
    mkdir(run_dir)

    gh = github.get_instance()
    # adopting approach outlined in https://github.com/EESSI/eessi-bot-software-layer/issues/17
    # need to use `base` instead of `head` ... don't need to know the branch name
    repo_name = pr.base.repo.full_name
    log("build_easystack_from_pr: pr.base.repo.full_name '%s'" % pr.base.repo.full_name)

    jobs = []
    for arch_target,slurm_opt in arch_target_map.items():
        arch_job_dir = os.path.join(run_dir, arch_target.replace('/', '_'))
        mkdir(arch_job_dir)
        log("arch_job_dir '%s'" % arch_job_dir)

        # download pull request to arch_job_dir
        #  - PyGitHub doesn't seem capable of doing that (easily);
        #  - for now, keep it simple and just execute the commands (anywhere) (note 'git clone' requires that destination is an empty directory)
        #      git clone https://github.com/REPO_NAME arch_job_dir
        #      curl -L https://github.com/REPO_NAME/pull/PR_NUMBER.patch > arch_job_dir/PR_NUMBER.patch
        #    (execute the next one in arch_job_dir)
        #      git am PR_NUMBER.patch
        #  - REPO_NAME is repo_name
        #  - PR_NUMBER is pr.number
        git_clone_cmd = ' '.join([
            'git clone',
            'https://github.com/' + repo_name,
            arch_job_dir,
        ])
        log("Clone repo by running '%s' in directory '%s'" % (git_clone_cmd,arch_job_dir))
        cloned_repo = subprocess.run(git_clone_cmd,
                                     cwd=arch_job_dir,
                                     shell=True,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
        log("Cloned repo!\nStdout %s\nStderr: %s" % (cloned_repo.stdout,cloned_repo.stderr))

        curl_cmd = 'curl -L https://github.com/%s/pull/%s.patch > %s.patch' % (repo_name,pr.number,pr.number)
        log("Obtain patch by running '%s' in directory '%s'" % (curl_cmd,arch_job_dir))
        got_patch = subprocess.run(curl_cmd,
                                   cwd=arch_job_dir,
                                   shell=True,
                                   stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        log("Got patch!\nStdout %s\nStderr: %s" % (got_patch.stdout,got_patch.stderr))

        git_am_cmd = 'git am %s.patch' % pr.number
        log("Apply patch by running '%s' in directory '%s'" % (git_am_cmd,arch_job_dir))
        patched = subprocess.run(git_am_cmd,
                                 cwd=arch_job_dir,
                                 shell=True,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
        log("Applied patch!\nStdout %s\nStderr: %s" % (patched.stdout,patched.stderr))

        # enlist jobs to proceed
        jobs.append([arch_job_dir,arch_target,slurm_opt])


    log("  %d jobs to proceed after applying white list" % len(jobs))
    if len(jobs) > 0:
        log(json.dumps(jobs, indent=4))

    # Run jobs with the build job submission script
    submitted_jobs = []
    for job in jobs:
        log("Submit job with '%s %s %s %s' from directory '%s'" % (submit_command, job[2], build_job_script, local_tmp, job[0]))
        # TODO make local_tmp specific to job? to isolate jobs if multiple ones can run on a single node
        command_line = ' '.join([
            submit_command,
            job[2],
            build_job_script,
            local_tmp,
        ])
        submitted = subprocess.run(command_line, shell=True, cwd=job[0], stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # sbatch output is 'Submitted batch job JOBID'
        #   parse job id & add it to array of submitted jobs PLUS create a symlink from main pr_<ID> dir to job dir (job[0])
        job_id = submitted.stdout.split()[3].decode("UTF-8")
        submitted_jobs.append(job_id)
        log("jobs_base_dir: %s, ym: %s, pr_id: %s, job_id: %s" % (jobs_base_dir,ym,pr_id,job_id))
        os.symlink(job[0], os.path.join(jobs_base_dir, ym, pr_id, job_id))
        log("Submit command executed!\nStdout: %s\nStderr: %s" % (submitted.stdout, submitted.stderr))

    # check status for submitted_jobs every N seconds
    poll_interval = int(config.get_section('buildenv').get('poll_interval') or 0)
    if poll_interval <= 0:
        poll_interval = 60
    poll_command = config.get_section('buildenv').get('poll_command')
    # the below method works if the poll command is 'squeue'
    jobs_to_be_checked = submitted_jobs.copy()
    while len(jobs_to_be_checked) > 0:
        # initial pause/sleep
        time.sleep(poll_interval)
        # check status of all jobs_to_be_checked
        #   - handle finished jobs
        #   - update jobs_to_be_checked if any job finished
        job_list_str = ','.join(jobs_to_be_checked)
        # TODO instead of '--long' specify explicitly which columns shall be shown
        squeue_cmd = '%s --long --jobs=%s' % (poll_command,job_list_str)
        log("run squeue command: %s" % squeue_cmd)
        squeue = subprocess.run(squeue_cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # cases
        # (1) no job returned -> all finished -> check result for each, update jobs_to_be_checked
        # (2) some/not all jobs returned -> may check status (to detect potential issues), check result for jobs not returned & update jobs_to_be_checked for them
        # (3) all jobs returned -> may check status (to detect potential issues)
        log("squeue output: +++%s+++" % squeue.stdout)
        # TODO add sanity check if any output from command
        job_table = pd.read_csv(StringIO(squeue.stdout.decode("UTF-8")),delim_whitespace=True,skiprows=1)
        if len(job_table) == 0:
            # case (1)
            log("All jobs seem finished.")
            for cj in jobs_to_be_checked:
                log("Processing result of job '%s'." % (cj))
                process_job_result(pr, event_info, cj, os.path.join(jobs_base_dir, ym, pr_id))
            jobs_to_be_checked = []
        elif len(job_table) < len(jobs_to_be_checked):
            # case (2)
            #   set A: finished jobs -> check job result, remove from jobs_to_be_checked
            #   set B: not yet finished jobs -> may check status (to detect potential issues)
            # set A
            jtbc_df = pd.DataFrame(jobs_to_be_checked, columns = ["JOBID"], dtype = int)
            # set A: finished
            finished = jtbc_df[~jtbc_df["JOBID"].isin(job_table["JOBID"])]
            log("Some jobs seem finished: '%s'" % (','.join(finished["JOBID"]).tolist()))
            for fj in finished["JOBID"].tolist():
                log("Processing result of job '%s'." % fj)
                process_job_result(pr, event_info, fj, os.path.join(jobs_base_dir, ym, pr_id))
                jobs_to_be_checked.remove(fj)
            # set B: not yet finished
            not_finished = jtbc_df[jtbc_df["JOBID"].isin(job_table["JOBID"])]
        else:
            # case (3)
            #   not yet finished jobs -> may check status (to detect potential issues)
            log("No job finished yet.")
