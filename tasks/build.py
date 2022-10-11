import configparser
import json
import os
import subprocess
import time
import glob
import re

from connections import github
from tools import config
from pyghee.utils import log, error
from datetime import datetime, timezone


def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)


def build_easystack_from_pr(pr, event_info):
    # retrieving some settings from 'app.cfg' in bot directory
    # [github]
    app_name = config.get_section('github').get('app_name')

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
    slurm_params = buildenv.get('slurm_params')
    log("slurm_params '%s'" % slurm_params)
    cvmfs_customizations = {}
    try:
        cvmfs_customizations_str = buildenv.get('cvmfs_customizations')
        log("cvmfs_customizations '%s'" % cvmfs_customizations_str)

        if cvmfs_customizations_str != None:
            cvmfs_customizations = json.loads(cvmfs_customizations_str)

        log("cvmfs_customizations '%s'" % json.dumps(cvmfs_customizations))
    except json.decoder.JSONDecodeError as e:
        print(e)
        error(f'Value for cvmfs_customizations ({cvmfs_customizations_str}) could not be decoded.')
    http_proxy = buildenv.get('http_proxy') or ''
    log("http_proxy '%s'" % http_proxy)
    https_proxy = buildenv.get('https_proxy') or ''
    log("https_proxy '%s'" % https_proxy)
    load_modules = buildenv.get('load_modules') or ''
    log("load_modules '%s'" % load_modules)


    # [architecturetargets]
    architecturetargets = config.get_section('architecturetargets')
    arch_target_map = json.loads(architecturetargets.get('arch_target_map'))
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
    # TODO rename to base_repo_name?
    repo_name = pr.base.repo.full_name
    log("build_easystack_from_pr: pr.base.repo.full_name '%s'" % pr.base.repo.full_name)
    branch_name = pr.base.ref
    log("build_easystack_from_pr: pr.base.repo.ref '%s'" % pr.base.ref)

    jobs = []
    for arch_target,slurm_opt in arch_target_map.items():
        arch_job_dir = os.path.join(run_dir, arch_target.replace('/', '_'))
        mkdir(arch_job_dir)
        log("arch_job_dir '%s'" % arch_job_dir)

        # download pull request to arch_job_dir
        #  - PyGitHub doesn't seem capable of doing that (easily);
        #  - for now, keep it simple and just execute the commands (anywhere) (note 'git clone' requires that destination is an empty directory)
        #    * patching method
        #      git clone https://github.com/REPO_NAME arch_job_dir
        #      git checkout BRANCH (is stored as ref for base record in PR)
        #      curl -L https://github.com/REPO_NAME/pull/PR_NUMBER.patch > arch_job_dir/PR_NUMBER.patch
        #    (execute the next one in arch_job_dir)
        #      git am PR_NUMBER.patch
        #
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

        git_checkout_cmd = ' '.join([
            'git checkout',
            branch_name,
        ])
        log("Checkout branch '%s' by running '%s' in directory '%s'" % (branch_name,git_checkout_cmd,arch_job_dir))
        checkout_repo = subprocess.run(git_checkout_cmd,
                                     cwd=arch_job_dir,
                                     shell=True,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE)
        log("Checked out branch!\nStdout %s\nStderr: %s" % (checkout_repo.stdout,checkout_repo.stderr))

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

        # check if we need to apply local customizations:
        #   is cvmfs_customizations defined? yes, apply it
        if len(cvmfs_customizations) > 0:
            # for each entry/key, append value to file
            for key in cvmfs_customizations.keys():
                basename = os.path.basename(key)
                jobcfgfile = os.path.join(arch_job_dir, basename)
                with open(jobcfgfile, "a") as file_object:
                    file_object.write(cvmfs_customizations[key]+'\n')

                # TODO (maybe) create mappings_file to be used by
                #      eessi-bot-build.slurm to init SINGULARITY_BIND;
                #      for now, only existing mappings may be customized


        # enlist jobs to proceed
        jobs.append([arch_job_dir,arch_target,slurm_opt])


    log("  %d jobs to proceed after applying white list" % len(jobs))
    if len(jobs) > 0:
        log(json.dumps(jobs, indent=4))

    # Run jobs with the build job submission script
    submitted_jobs = []
    job_comment = ''
    for job in jobs:
        # TODO make local_tmp specific to job? to isolate jobs if multiple ones can run on a single node
        command_line = ' '.join([
            submit_command,
            slurm_params,
            job[2],
            build_job_script,
            '--tmpdir', local_tmp,
        ])
        if http_proxy:
            command_line += ' --http-proxy ' + http_proxy
        if https_proxy:
            command_line += ' --https-proxy ' + https_proxy
        if load_modules:
            command_line += ' --load-modules ' + load_modules

        # TODO the handling of generic targets requires a bit knowledge about
        #      the internals of building the software layer, maybe ok for now,
        #      but it might be good to think about an alternative
        # if target contains generic, add ' --generic' to command line
        if "generic" in job[1]:
            command_line += ' --generic'

        log("Submit job for target '%s' with '%s' from directory '%s'" % (job[1], command_line, job[0]))

        submitted = subprocess.run(
                command_line,
                shell=True,
                cwd=job[0],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)

        # sbatch output is 'Submitted batch job JOBID'
        #   parse job id & add it to array of submitted jobs PLUS create a symlink from main pr_<ID> dir to job dir (job[0])
        log("build_easystack_from_pr(): sbatch out: %s" % submitted.stdout.decode("UTF-8"))
        log("build_easystack_from_pr(): sbatch err: %s" % submitted.stderr.decode("UTF-8"))
        job_id = submitted.stdout.split()[3].decode("UTF-8")
        submitted_jobs.append(job_id)
        symlink = os.path.join(jobs_base_dir, ym, pr_id, job_id)
        log("jobs_base_dir: %s, ym: %s, pr_id: %s, job_id: %s" % (jobs_base_dir,ym,pr_id,job_id))
        os.symlink(job[0], symlink)
        log("Submit command executed!\nStdout: %s\nStderr: %s" % (submitted.stdout, submitted.stderr))

        # create _bot_job<jobid>.metadata file in submission directory
        bot_jobfile = configparser.ConfigParser()
        bot_jobfile['PR'] = { 'repo' : repo_name, 'pr_number' : pr.number }
        # obtain arch from job[1] which has the format OS/ARCH
        arch_name = '-'.join(job[1].split('/')[1:])
        bot_jobfile['ARCH'] = { 'architecture' : arch_name, 'os' : job[1].split('/')[0], 'slurm_opt' : job[2] }
        bot_jobfile_path = os.path.join(job[0], '_bot_job%s.metadata' % job_id)
        with open(bot_jobfile_path, 'w') as bjf:
            bot_jobfile.write(bjf)

        # report submitted jobs (incl architecture, ...)
        job_comment = 'New job on instance `%s`' % app_name
        job_comment += ' for architecture `%s`' % arch_name
        job_comment += ' in job dir `%s`\n' % symlink
        job_comment += '|date|job status|comment|\n'
        job_comment += '|----------|----------|------------------------|\n'

        dt = datetime.now(timezone.utc)
        job_comment += '|%s|submitted|job id `%s` awaits release by job manager|' % (dt.strftime("%b %d %X %Z %Y"), job_id)

        repo = gh.get_repo(repo_name)
        pull_request = repo.get_pull(pr.number)
        pull_request.create_issue_comment(job_comment)

