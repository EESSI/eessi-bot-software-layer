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
import configparser
import json
import os
import sys

from collections import namedtuple
from connections import github
from datetime import datetime, timezone
from pyghee.utils import log, error
from tools import config, run_cmd

BUILDENV = "buildenv"
BUILD_JOB_SCRIPT = "build_job_script"
DEFAULT_JOB_TIME_LIMIT = "24:00:00"
CVMFS_CUSTOMIZATIONS = "cvmfs_customizations"
HTTP_PROXY = "http_proxy"
HTTPS_PROXY = "https_proxy"
JOBS_BASE_DIR = "jobs_base_dir"
LOAD_MODULES = "load_modules"
LOCAL_TMP = "local_tmp"
SLURM_PARAMS = "slurm_params"
SUBMIT_COMMAND = "submit_command"
BUILD_PERMISSION = "build_permission"
ARCHITECTURE_TARGETS = "architecturetargets"

Job = namedtuple('Job', ('working_dir', 'arch_target', 'slurm_opts'))


def get_build_env_cfg():
    """Gets build environment values

    Returns:
         dict(str, dict): dictionary of configuration data
    """
    cfg = config.read_config()
    buildenv = cfg[BUILDENV]

    jobs_base_dir = buildenv.get(JOBS_BASE_DIR)
    log("jobs_base_dir '%s'" % jobs_base_dir)
    config_data = {JOBS_BASE_DIR: jobs_base_dir}
    local_tmp = buildenv.get(LOCAL_TMP)
    log("local_tmp '%s'" % local_tmp)
    config_data[LOCAL_TMP] = local_tmp

    build_job_script = buildenv.get(BUILD_JOB_SCRIPT)
    log("build_job_script '%s'" % build_job_script)
    config_data[BUILD_JOB_SCRIPT] = build_job_script

    submit_command = buildenv.get(SUBMIT_COMMAND)
    log("submit_command '%s'" % submit_command)
    config_data[SUBMIT_COMMAND] = submit_command

    slurm_params = buildenv.get(SLURM_PARAMS)
    # always submit jobs with hold set, so job manager can release them
    slurm_params += ' --hold'
    log("slurm_params '%s'" % slurm_params)
    config_data[SLURM_PARAMS] = slurm_params

    cvmfs_customizations = {}
    try:
        cvmfs_customizations_str = buildenv.get(CVMFS_CUSTOMIZATIONS)
        log("cvmfs_customizations '%s'" % cvmfs_customizations_str)

        if cvmfs_customizations_str is not None:
            cvmfs_customizations = json.loads(cvmfs_customizations_str)

        log("cvmfs_customizations '%s'" % json.dumps(cvmfs_customizations))
    except json.decoder.JSONDecodeError as e:
        print(e)
        error(f'Value for cvmfs_customizations ({cvmfs_customizations_str}) could not be decoded.')

    config_data[CVMFS_CUSTOMIZATIONS] = cvmfs_customizations

    http_proxy = buildenv.get(HTTP_PROXY) or ''
    log("http_proxy '%s'" % http_proxy)
    config_data[HTTP_PROXY] = http_proxy

    https_proxy = buildenv.get(HTTPS_PROXY) or ''
    log("https_proxy '%s'" % https_proxy)
    config_data[HTTPS_PROXY] = https_proxy

    load_modules = buildenv.get(LOAD_MODULES) or ''
    log("load_modules '%s'" % load_modules)
    config_data[LOAD_MODULES] = load_modules

    return config_data


def get_architecturetargets():
    """get architecturetargets and set arch_target_map

    Returns:
        dict(str, dict): dictionary of arch_target_map which contains entries of the format
                         OS/SUBDIR : ADDITIONAL_SBATCH_PARAMETERS
    """
    cfg = config.read_config()
    architecturetargets = cfg[ARCHITECTURE_TARGETS]

    arch_target_map = json.loads(architecturetargets.get('arch_target_map'))
    log("arch target map '%s'" % json.dumps(arch_target_map))
    return arch_target_map


def create_pr_dir(pr, jobs_base_dir, event_info):
    """Create directory for Pull Request

    Args:
        pr (object): pr details
        jobs_base_dir (string): location where the bot prepares directories per job
        event_info (string): event received by event_handler

    Returns:
        tuple of 3 elements containing

        - ym(string): string with datestamp (<year>.<month>)
        - pr_id(int): pr number
        - run_dir(string): path to run_dir
    """
    # create directory structure according to alternative described in
    #   https://github.com/EESSI/eessi-bot-software-layer/issues/7
    #   jobs_base_dir/YYYY.MM/pr<id>/event_<id>/run_<id>/target_<cpuarch>

    ym = datetime.today().strftime('%Y.%m')
    pr_id = 'pr_%s' % pr.number
    event_id = 'event_%s' % event_info['id']
    event_dir = os.path.join(jobs_base_dir, ym, pr_id, event_id)
    os.makedirs(event_dir, exist_ok=True)

    run = 0
    while os.path.exists(os.path.join(event_dir, 'run_%03d' % run)):
        run += 1
    run_dir = os.path.join(event_dir, 'run_%03d' % run)
    os.makedirs(run_dir, exist_ok=True)
    return ym, pr_id, run_dir


def download_pr(repo_name, branch_name, pr, arch_job_dir):
    """Download pull request to arch_job_dir

    Args:
        repo_name (string): pr base repo name
        branch_name (string): pr branch name
        pr (object): pr details
        arch_job_dir (string): location of arch_job_dir
    """
    # download pull request to arch_job_dir
    #  - PyGitHub doesn't seem capable of doing that (easily);
    #  - for now, keep it simple and just execute the commands (anywhere) (note 'git clone' requires that
    #    destination is an empty directory)
    #    * patching method
    #      git clone https://github.com/REPO_NAME arch_job_dir
    #      git checkout BRANCH (is stored as ref for base record in PR)
    #      curl -L https://github.com/REPO_NAME/pull/PR_NUMBER.patch > arch_job_dir/PR_NUMBER.patch
    #    (execute the next one in arch_job_dir)
    #      git am PR_NUMBER.patch
    #
    #  - REPO_NAME is repo_name
    #  - PR_NUMBER is pr.number
    git_clone_cmd = ' '.join(['git clone', f'https://github.com/{repo_name}', arch_job_dir])
    clone_output, clone_error, clone_exit_code = run_cmd(git_clone_cmd, "Clone repo", arch_job_dir)

    git_checkout_cmd = ' '.join([
        'git checkout',
        branch_name,
    ])
    checkout_output, checkout_err, checkout_exit_code = run_cmd(git_checkout_cmd,
                                                                "checkout branch '%s'" % branch_name, arch_job_dir)

    curl_cmd = f'curl -L https://github.com/{repo_name}/pull/{pr.number}.diff > {pr.number}.diff'
    curl_output, curl_error, curl_exit_code = run_cmd(curl_cmd, "Obtain patch", arch_job_dir)

    git_apply_cmd = f'git apply {pr.number}.diff'
    git_apply_output, git_apply_error, git_apply_exit_code = run_cmd(git_apply_cmd, "Apply patch", arch_job_dir)


def apply_cvmfs_customizations(cvmfs_customizations, arch_job_dir):
    """if cvmfs_customizations are defined then applies it

    Args:
        cvmfs_customizations (dictionary): maps a file name to an entry that needs to be appended to that file.
        arch_job_dir ((string): location of arch_job_dir
    """
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


def setup_pr_in_arch_job_dir(pr, arch_target_map, run_dir, cvmfs_customizations):
    """setup pull request in arch_job_dir and apply cvmfs customizations

    Args:
        pr (object): data of pr
        arch_target_map (dictionary): contains entries of the format
                                      OS/SUBDIR : ADDITIONAL_SBATCH_PARAMETERS where the jobs are submitted
        run_dir (string): path to run directory
        cvmfs_customizations (dictionary): CVMFS configuration for the build job

    Returns:
        tuple of 2 elements containing
            - repo_name(string):  pr base repository name
            - jobs(list): list containing all the jobs
    """
    # adopting approach outlined in https://github.com/EESSI/eessi-bot-software-layer/issues/17
    # need to use `base` instead of `head` ... don't need to know the branch name
    # TODO rename to base_repo_name?
    repo_name = pr.base.repo.full_name
    log("submit_build_jobs: pr.base.repo.full_name '%s'" % pr.base.repo.full_name)
    branch_name = pr.base.ref
    log("submit_build_jobs: pr.base.repo.ref '%s'" % pr.base.ref)
    jobs = []
    for arch_target, slurm_opt in arch_target_map.items():
        arch_job_dir = os.path.join(run_dir, arch_target.replace('/', '_'))

        os.makedirs(arch_job_dir, exist_ok=True)
        log("arch_job_dir '%s'" % arch_job_dir)

        download_pr(repo_name, branch_name, pr, arch_job_dir)

        # check if we need to apply local customizations:
        #   is cvmfs_customizations defined? yes, apply it
        apply_cvmfs_customizations(cvmfs_customizations, arch_job_dir)
        # enlist jobs to proceed
        job = Job(arch_job_dir, arch_target, slurm_opt)
        jobs.append(job)
    log("  %d jobs to proceed after applying white list" % len(jobs))
    if jobs:
        log(json.dumps(jobs, indent=4))

    return repo_name, jobs


def submit_job(job, submitted_jobs, build_env_cfg, ym, pr_id):
    """Parse job id and submit jobs from directory

    Args:
        job (list): jobs to be submitted
        submitted_jobs (list): jobs submitted
        build_env_cfg (dictionary): build environment data
        ym (string): string with datestamp (<year>.<month>)
        pr_id(int): pr number

    Returns:
        tuple of 2 elements containing
            - job_id(string):  job_id of submitted job
            - symlink(string): symlink from main pr_<ID> dir to job dir (job[0])
    """
    # determine CPU target to use: job.arch_target, but without the linux/ part
    cpu_target = '/'.join(job.arch_target.split('/')[1:])

    # Add a default time limit of 24h to the command if nothing else is specified by the user
    all_opts_str = " ".join([build_env_cfg[SLURM_PARAMS], job.slurm_opts])
    all_opts_list = all_opts_str.split(" ")
    if any([(opt.startswith("--time") or opt.startswith("-t")) for opt in all_opts_list]):
        time_limit = ""
    else:
        time_limit = f"--time={DEFAULT_JOB_TIME_LIMIT}"

    command_line = ' '.join([
        build_env_cfg[SUBMIT_COMMAND],
        build_env_cfg[SLURM_PARAMS],
        time_limit,
        job.slurm_opts,
        # set $CPU_TARGET in job environment, which can be picked up by build job script;
        '--export=ALL,CPU_TARGET=%s' % cpu_target,
        build_env_cfg[BUILD_JOB_SCRIPT],
        '--tmpdir', build_env_cfg[LOCAL_TMP],
    ])
    if build_env_cfg[HTTP_PROXY]:
        command_line += f' --http-proxy {build_env_cfg[HTTP_PROXY]}'
    if build_env_cfg[HTTPS_PROXY]:
        command_line += f' --https-proxy {build_env_cfg[HTTPS_PROXY]}'
    if build_env_cfg[LOAD_MODULES]:
        command_line += f' --load-modules {build_env_cfg[LOAD_MODULES]}'

    # TODO the handling of generic targets requires a bit knowledge about
    #      the internals of building the software layer, maybe ok for now,
    #      but it might be good to think about an alternative
    # if target contains generic, add ' --generic' to command line
    if cpu_target.endswith("generic"):
        command_line += ' --generic'

    # to make sure that correct $CPU_TARGET value is passed into job,
    # we need to also set it in the submission environment;
    # cfr. documentation for sbatch --export option, see https://slurm.schedmd.com/sbatch.html
    os.environ['CPU_TARGET'] = cpu_target

    cmdline_output, cmdline_error, cmdline_exit_code = run_cmd(command_line,
                                                               "submit job for target '%s'" % job.arch_target,
                                                               working_dir=job.working_dir)

    # sbatch output is 'Submitted batch job JOBID'
    #   parse job id & add it to array of submitted jobs PLUS create a symlink from main pr_<ID> dir to job dir (job[0])
    log(f'submit_build_jobs(): sbatch out: {cmdline_output}')
    log(f'submit_build_jobs(): sbatch err: {cmdline_error}')

    job_id = cmdline_output.split()[3]
    submitted_jobs.append(job_id)
    symlink = os.path.join(build_env_cfg[JOBS_BASE_DIR], ym, pr_id, job_id)
    log(f"jobs_base_dir: {build_env_cfg[JOBS_BASE_DIR]}, ym: {ym}, pr_id: {pr_id}, job_id: {job_id}")

    os.symlink(job[0], symlink)
    log("Submit command executed!\nStdout: %s\nStderr: %s" % (cmdline_output, cmdline_error))
    return job_id, symlink


def create_metadata(job, repo_name, pr, job_id):
    """Create metadata file in submission dir

    Args:
        job (list):  jobs to be submitted
        repo_name (string): pr base repository name
        pr (object): data of pr
        job_id (string): job id after parsing
    """
    # create _bot_job<jobid>.metadata file in submission directory
    bot_jobfile = configparser.ConfigParser()
    bot_jobfile['PR'] = {'repo': repo_name, 'pr_number': pr.number}
    bot_jobfile_path = os.path.join(job.working_dir, f'_bot_job{job_id}.metadata')
    with open(bot_jobfile_path, 'w') as bjf:
        bot_jobfile.write(bjf)


def create_pr_comments(job, job_id, app_name, job_comment, pr, repo_name, gh, symlink):
    """create comments for pr

    Args:
        job (list): jobs to be submitted
        job_id (string): job id after parsing
        app_name (string): name of the app
        job_comment (string): comments for jobs status and job release
        pr (object): pr data
        repo_name (string): pr base repo name
        gh (object):github instance
        symlink(string): symlink from main pr_<ID> dir to job dir
    """
    # obtain arch from job.arch_target which has the format OS/ARCH
    arch_name = '-'.join(job.arch_target.split('/')[1:])

    # get current data/time
    dt = datetime.now(timezone.utc)

    # construct initial job comment
    job_comment = (f"New job on instance `{app_name}`"
                   f" for architecture `{arch_name}`"
                   f" in job dir `{symlink}`\n"
                   f"|date|job status|comment|\n"
                   f"|----------|----------|------------------------|\n"
                   f"|{dt.strftime('%b %d %X %Z %Y')}|submitted|"
                   f"job id `{job_id}` awaits release by job manager|")

    # create comment to pull request
    repo = gh.get_repo(repo_name)
    pull_request = repo.get_pull(pr.number)
    pull_request.create_issue_comment(job_comment)


def submit_build_jobs(pr, event_info):
    """Build from the pr by fetching data for build environment cofinguration, downloading pr,
       running jobs and adding comments

    Args:
        pr (object): _description_
        event_info (string): event received by event_handler
    """
    # retrieving some settings from 'app.cfg' in bot directory
    # [github]

    cfg = config.read_config()
    app_name = cfg['github'].get('app_name')

    # [buildenv]
    build_env_cfg = get_build_env_cfg()

    # [architecturetargets]
    arch_target_map = get_architecturetargets()

    # [directory structure]
    ym, pr_id, run_dir = create_pr_dir(pr, build_env_cfg[JOBS_BASE_DIR], event_info)
    gh = github.get_instance()

    # [download pull request]
    repo_name, jobs = setup_pr_in_arch_job_dir(pr, arch_target_map, run_dir, build_env_cfg[CVMFS_CUSTOMIZATIONS])

    # Run jobs with the build job submission script
    submitted_jobs = []
    job_comment = ''
    for job in jobs:
        # TODO make local_tmp specific to job? to isolate jobs if multiple ones can run on a single node
        job_id, symlink = submit_job(job, submitted_jobs, build_env_cfg, ym, pr_id)

        # create _bot_job<jobid>.metadata file in submission directory
        create_metadata(job, repo_name, pr, job_id)
        # report submitted jobs (incl architecture, ...)
        create_pr_comments(job, job_id, app_name, job_comment, pr, repo_name, gh, symlink)


def check_build_permission(pr, event_info):
    """check if the GH account is authorized to trigger build

    Args:
        pr (object): pr details
        event_info (string): event received by event_handler

    """
    funcname = sys._getframe().f_code.co_name

    log(f"{funcname}(): build for PR {pr.number}")

    cfg = config.read_config()

    buildenv = cfg[BUILDENV]

    # verify that the GH account that set label bot:build has the
    # permission to trigger the build
    build_permission = buildenv.get(BUILD_PERMISSION, '')

    log(f"{funcname}(): build permission '{build_permission}'")

    build_labeler = event_info['raw_request_body']['sender']['login']
    if build_labeler not in build_permission.split():
        log(f"{funcname}(): GH account '{build_labeler}' is not authorized to build")
        # TODO update PR comments for this bot instance?
        return False
    else:
        log(f"{funcname}(): GH account '{build_labeler}' is authorized to build")
        return True
