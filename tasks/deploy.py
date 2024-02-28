# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Thomas Roeblitz (@trz42)
# author: Jonas Qvigstad (@jonas-lq)
#
# license: GPLv2
#

# Standard library imports
from datetime import datetime, timezone
import glob
import json
import os
import re
import sys

# Third party imports (anything installed into the local Python environment)
from pyghee.utils import log

# Local application imports (anything from EESSI/eessi-bot-software-layer)
from connections import github
from tasks.build import CFG_DIRNAME, JOB_CFG_FILENAME, JOB_REPO_ID, JOB_REPOSITORY
from tasks.build import get_build_env_cfg
from tools import config, pr_comments, run_cmd
from tools.job_metadata import read_job_metadata_from_file


BUCKET_NAME = "bucket_name"
DEPLOYCFG = "deploycfg"
DEPLOY_PERMISSION = "deploy_permission"
ENDPOINT_URL = "endpoint_url"
JOBS_BASE_DIR = "jobs_base_dir"
METADATA_PREFIX = "metadata_prefix"
NO_DEPLOY_PERMISSION_COMMENT = "no_deploy_permission_comment"
TARBALL_PREFIX = "tarball_prefix"
TARBALL_UPLOAD_SCRIPT = "tarball_upload_script"
UPLOAD_POLICY = "upload_policy"


def determine_job_dirs(pr_number):
    """
    Determine working directories of jobs run for a pull request.

    Args:
        pr_number (int): number of the pull request

    Returns:
        job_directories (list): list of directory names
    """
    funcname = sys._getframe().f_code.co_name

    job_directories = []

    # a job directory's name has the format cfg[JOBS_BASE_DIR]/YYYY.MM/pr_<id>/JOBID
    #  - we may have to scan multiple YYYY.MM directories if the pull request was
    #    processed over more than one month (that is jobs were run in two or more
    #    months)
    #  - we assume that a JOBID is a positive integer
    cfg = config.read_config()
    build_env_cfg = get_build_env_cfg(cfg)
    jobs_base_dir = build_env_cfg[JOBS_BASE_DIR]
    log(f"{funcname}(): jobs_base_dir = {jobs_base_dir}")

    date_pr_job_pattern = (f"[0-9][0-9][0-9][0-9].[0-9][0-9]/"
                           f"pr_{pr_number}/[0-9]*")
    log(f"{funcname}(): date_pr_job_pattern = {date_pr_job_pattern}")

    glob_str = os.path.join(jobs_base_dir, date_pr_job_pattern)
    log(f"{funcname}(): glob_str = {glob_str}")

    job_directories = glob.glob(glob_str)

    return job_directories


def determine_pr_comment_id(job_dir):
    """
    Determine pr_comment_id by reading _bot_job{JOBID}.metadata in job_dir.

    Args:
        job_dir (string): working directory of the job

    Returns:
        (int): id of comment corresponding to job in pull request or -1
    """
    # assumes that last part of job_dir encodes the job's id
    job_id = os.path.basename(os.path.normpath(job_dir))
    job_metadata_file = os.path.join(job_dir, f"_bot_job{job_id}.metadata")
    job_metadata = read_job_metadata_from_file(job_metadata_file)
    if job_metadata and "pr_comment_id" in job_metadata:
        return int(job_metadata["pr_comment_id"])
    else:
        return -1


def determine_slurm_out(job_dir):
    """
    Determine path to job stdout/err output file for a given job directory.
    We assume that the file is named 'slurm-SLURM_JOBID.out' and the last element
    of job_dir is the SLURM_JOBID.

    Args:
        job_dir (string): working directory of the job

    Returns:
        slurm_out (string): path to job stdout/err output file
    """
    funcname = sys._getframe().f_code.co_name

    # we assume that the last element (basename) of a job directory is the job ID
    slurm_out = os.path.join(job_dir, f"slurm-{os.path.basename(job_dir)}.out")
    log(f"{funcname}(): slurm out path = '{slurm_out}'")

    return slurm_out


def determine_eessi_tarballs(job_dir):
    """
    Determine paths to EESSI software tarballs in a given job directory.

    Args:
        job_dir (string): working directory of the job

    Returns:
        eessi_tarballs (list): list of paths to all tarballs in job_dir
    """
    # determine all tarballs that are stored in the directory job_dir
    #   and whose name matches a certain pattern
    tarball_pattern = "eessi-*software-*.tar.gz"
    glob_str = os.path.join(job_dir, tarball_pattern)
    eessi_tarballs = glob.glob(glob_str)

    return eessi_tarballs


def check_build_status(slurm_out, eessi_tarballs):
    """
    Check status of the job in a given directory.

    Args:
        slurm_out (string): path to job output file
        eessi_tarballs (list): list of eessi tarballs found for job

    Returns:
        (bool): True -> job succeeded, False -> job failed
    """
    fn = sys._getframe().f_code.co_name

    # TODO use _bot_job<SLURM_JOBID>.result file to determine result status
    # cases:
    # (1) no result file --> add line with unknown status, found tarball xyz but no result file
    # (2) result file && status = SUCCESS --> return True
    # (3) result file && status = FAILURE --> return False

    # Function checks if all modules have been built and if a tarball has
    # been created.

    # set some initial values
    no_missing_modules = False
    targz_created = False

    # check slurm out for the below strings
    #   ^No missing modules!$ --> all software successfully installed
    #   ^/eessi_bot_job/eessi-.*-software-.*.tar.gz created!$ -->
    #     tarball successfully created
    if os.path.exists(slurm_out):
        re_missing_modules = re.compile(".*No missing installations, party time!.*")
        re_targz_created = re.compile("^/eessi_bot_job/eessi-.*-software-.*.tar.gz created!$")
        outfile = open(slurm_out, "r")
        for line in outfile:
            if re_missing_modules.match(line):
                # no missing modules
                no_missing_modules = True
                log(f"{fn}(): line '{line}' matches '.*No missing installations, party time!.*'")
            if re_targz_created.match(line):
                # tarball created
                targz_created = True
                log(f"{fn}(): line '{line}' matches '^/eessi_bot_job/eessi-.*-software-.*.tar.gz created!$'")

    log(f"{fn}(): found {len(eessi_tarballs)} tarballs for '{slurm_out}'")

    # we test results from the above check and if there is one tarball only
    if no_missing_modules and targz_created and len(eessi_tarballs) == 1:
        return True

    return False


def update_pr_comment(tarball, repo_name, pr_number, pr_comment_id, state, msg):
    """
    Update pull request comment for the given comment id or tarball name

    Args:
        tarball (string): name of tarball that is looked for in a PR comment
        repo_name (string): name of the repository (USER_ORG/REPOSITORY)
        pr_number (int): pull request number
        state (string): value for state column to be used in update
        msg (string): msg (succeeded or failed) describing upload result

    Returns:
        None (implicitly)
    """
    gh = github.get_instance()
    repo = gh.get_repo(repo_name)
    pull_request = repo.get_pull(pr_number)

    issue_comment = pr_comments.determine_issue_comment(pull_request, pr_comment_id, tarball)
    if issue_comment:
        dt = datetime.now(timezone.utc)
        comment_update = (f"\n|{dt.strftime('%b %d %X %Z %Y')}|{state}|"
                          f"transfer of `{tarball}` to S3 bucket {msg}|")

        # append update to existing comment
        issue_comment.edit(issue_comment.body + comment_update)


def append_tarball_to_upload_log(tarball, job_dir):
    """
    Append tarball to upload log.

    Args:
        tarball (string): name of tarball that has been uploaded
        job_dir (string): directory of the job that built the tarball

    Returns:
        None (implicitly)
    """
    # upload log file is 'job_dir/../uploaded.txt'
    pr_base_dir = os.path.dirname(job_dir)
    uploaded_txt = os.path.join(pr_base_dir, 'uploaded.txt')
    with open(uploaded_txt, "a") as upload_log:
        job_plus_tarball = os.path.join(os.path.basename(job_dir), tarball)
        upload_log.write(f"{job_plus_tarball}\n")


def upload_tarball(job_dir, build_target, timestamp, repo_name, pr_number, pr_comment_id):
    """
    Upload built tarball to an S3 bucket.

    Args:
        job_dir (string): path to the job directory
        build_target (string): eessi-VERSION-COMPONENT-OS-ARCH
        timestamp (int): timestamp of the tarball
        repo_name (string): repository of the pull request
        pr_number (int): number of the pull request
        pr_comment_id (int): id of the pull request comment

    Returns:
        None (implicitly)
    """
    funcname = sys._getframe().f_code.co_name

    tarball = f"{build_target}-{timestamp}.tar.gz"
    abs_path = os.path.join(job_dir, tarball)
    log(f"{funcname}(): deploying build '{abs_path}'")

    # obtain config settings
    cfg = config.read_config()
    deploycfg = cfg[DEPLOYCFG]
    tarball_upload_script = deploycfg.get(TARBALL_UPLOAD_SCRIPT)
    endpoint_url = deploycfg.get(ENDPOINT_URL) or ''
    bucket_spec = deploycfg.get(BUCKET_NAME)
    metadata_prefix = deploycfg.get(METADATA_PREFIX)
    tarball_prefix = deploycfg.get(TARBALL_PREFIX)

    # if bucket_spec value looks like a dict, try parsing it as such
    if bucket_spec.lstrip().startswith('{'):
        bucket_spec = json.loads(bucket_spec)

    # if metadata_prefix value looks like a dict, try parsing it as such
    if metadata_prefix.lstrip().startswith('{'):
        metadata_prefix = json.loads(metadata_prefix)

    # if tarball_prefix value looks like a dict, try parsing it as such
    if tarball_prefix.lstrip().startswith('{'):
        tarball_prefix = json.loads(tarball_prefix)

    jobcfg_path = os.path.join(job_dir, CFG_DIRNAME, JOB_CFG_FILENAME)
    jobcfg = config.read_config(jobcfg_path)
    target_repo_id = jobcfg[JOB_REPOSITORY][JOB_REPO_ID]

    if isinstance(bucket_spec, str):
        bucket_name = bucket_spec
        log(f"Using specified bucket: {bucket_name}")
    elif isinstance(bucket_spec, dict):
        # bucket spec may be a mapping of target repo id to bucket name
        bucket_name = bucket_spec.get(target_repo_id)
        if bucket_name is None:
            update_pr_comment(tarball, repo_name, pr_number, pr_comment_id, "not uploaded",
                              f"failed (no bucket specified for {target_repo_id})")
            return
        else:
            log(f"Using bucket for {target_repo_id}: {bucket_name}")
    else:
        update_pr_comment(tarball, repo_name, pr_number, pr_comment_id, "not uploaded",
                          f"failed (incorrect bucket spec: {bucket_spec})")
        return

    if isinstance(metadata_prefix, str):
        metadata_prefix_arg = metadata_prefix
        log(f"Using specified metadata prefix: {metadata_prefix_arg}")
    elif isinstance(metadata_prefix, dict):
        # metadata prefix spec may be a mapping of target repo id to metadata prefix
        metadata_prefix_arg = metadata_prefix.get(target_repo_id)
        if metadata_prefix_arg is None:
            update_pr_comment(tarball, repo_name, pr_number, pr_comment_id, "not uploaded",
                              f"failed (no metadata prefix specified for {target_repo_id})")
            return
        else:
            log(f"Using metadata prefix for {target_repo_id}: {metadata_prefix_arg}")
    else:
        update_pr_comment(tarball, repo_name, pr_number, pr_comment_id, "not uploaded",
                          f"failed (incorrect metadata prefix spec: {metadata_prefix_arg})")
        return

    if isinstance(tarball_prefix, str):
        tarball_prefix_arg = tarball_prefix
        log(f"Using specified tarball prefix: {tarball_prefix_arg}")
    elif isinstance(tarball_prefix, dict):
        # tarball prefix spec may be a mapping of target repo id to tarball prefix
        tarball_prefix_arg = tarball_prefix.get(target_repo_id)
        if tarball_prefix_arg is None:
            update_pr_comment(tarball, repo_name, pr_number, pr_comment_id, "not uploaded",
                              f"failed (no tarball prefix specified for {target_repo_id})")
            return
        else:
            log(f"Using tarball prefix for {target_repo_id}: {tarball_prefix_arg}")
    else:
        update_pr_comment(tarball, repo_name, pr_number, pr_comment_id, "not uploaded",
                          f"failed (incorrect tarball prefix spec: {tarball_prefix_arg})")
        return

    # run 'eessi-upload-to-staging {abs_path}'
    # (1) construct command line
    #   script assumes a few defaults:
    #     bucket_name = 'eessi-staging'
    #     if endpoint_url not set use EESSI S3 bucket
    # (2) run command
    cmd_args = [tarball_upload_script, ]
    if len(bucket_name) > 0:
        cmd_args.extend(['--bucket-name', bucket_name])
    if len(endpoint_url) > 0:
        cmd_args.extend(['--endpoint-url', endpoint_url])
    if len(metadata_prefix_arg) > 0:
        cmd_args.extend(['--metadata-prefix', metadata_prefix_arg])
    cmd_args.extend(['--repository', repo_name])
    cmd_args.extend(['--pull-request-number', str(pr_number)])
    cmd_args.extend(['--pr-comment-id', str(pr_comment_id)])
    if len(tarball_prefix_arg) > 0:
        cmd_args.extend(['--tarball-prefix', tarball_prefix_arg])
    cmd_args.append(abs_path)
    upload_cmd = ' '.join(cmd_args)

    # run_cmd does all the logging we might need
    out, err, ec = run_cmd(upload_cmd, 'Upload tarball to S3 bucket', raise_on_error=False)

    if ec == 0:
        # add file to 'job_dir/../uploaded.txt'
        append_tarball_to_upload_log(tarball, job_dir)
        # update pull request comment
        update_pr_comment(tarball, repo_name, pr_number, pr_comment_id, "uploaded",
                          "succeeded")
    else:
        # update pull request comment
        update_pr_comment(tarball, repo_name, pr_number, pr_comment_id, "not uploaded",
                          "failed")


def uploaded_before(build_target, job_dir):
    """
    Determines if a tarball for a job has been uploaded before. Function
    scans the log file named 'job_dir/../uploaded.txt' for the string
    '.*build_target-.*.tar.gz'.

    Args:
        build_target (string): eessi-VERSION-COMPONENT-OS-ARCH
        job_dir (string): working directory of the job

    Returns:
        (string): name of the first tarball found if any or None.
    """
    funcname = sys._getframe().f_code.co_name

    log(f"{funcname}(): any previous uploads for {build_target}?")

    pr_base_dir = os.path.dirname(job_dir)
    uploaded_txt = os.path.join(pr_base_dir, "uploaded.txt")

    if os.path.exists(uploaded_txt):
        log(f"{funcname}(): upload log '{uploaded_txt}' exists")

        re_string = f".*{build_target}-.*.tar.gz.*"
        re_build_target = re.compile(re_string)

        with open(uploaded_txt, "r") as uploaded_log:
            log(f"{funcname}(): scan log for pattern '{re_string}'")
            for line in uploaded_log:
                if re_build_target.match(line):
                    log(f"{funcname}(): found earlier upload {line.strip()}")
                    return line.strip()
                else:
                    log(f"{funcname}(): upload '{line.strip()}' did NOT match")
            return None
    else:
        log(f"{funcname}(): upload log '{uploaded_txt}' does not exist")
        return None


def determine_successful_jobs(job_dirs):
    """
    Determine all successful jobs provided a list of job_dirs.

    Args:
        job_dirs (list): list of job directories

    Returns:
        (list): list of dictionaries representing successful jobs
    """
    funcname = sys._getframe().f_code.co_name

    successes = []
    for job_dir in job_dirs:
        slurm_out = determine_slurm_out(job_dir)
        eessi_tarballs = determine_eessi_tarballs(job_dir)
        pr_comment_id = determine_pr_comment_id(job_dir)

        if check_build_status(slurm_out, eessi_tarballs):
            log(f"{funcname}(): SUCCESSFUL build in '{job_dir}'")
            successes.append({'job_dir': job_dir,
                              'slurm_out': slurm_out,
                              'pr_comment_id': pr_comment_id,
                              'eessi_tarballs': eessi_tarballs})
        else:
            log(f"{funcname}(): FAILED build in '{job_dir}'")

    return successes


def determine_tarballs_to_deploy(successes, upload_policy):
    """
    Determine tarballs to deploy depending on upload policy

    Args:
        successes (list): list of dictionaries
            {'job_dir':job_dir, 'slurm_out':slurm_out, 'eessi_tarballs':eessi_tarballs}
        upload_policy (string): one of 'all', 'latest' or 'once'
            'all': deploy all
            'latest': deploy only the last for each build target
            'once': deploy only latest if none for this build target has
                    been deployed before
    Returns:
        (dictionary): dictionary of dictionaries representing built tarballs to
            be deployed
    """
    funcname = sys._getframe().f_code.co_name

    log(f"{funcname}(): num successful jobs {len(successes)}")

    to_be_deployed = {}
    for job in successes:
        # all tarballs for successful job
        tarballs = job["eessi_tarballs"]
        log(f"{funcname}(): num tarballs {len(tarballs)}")

        # full path to first tarball for successful job
        # Note, only one tarball per job is expected.
        tb0 = tarballs[0]
        log(f"{funcname}(): path to 1st tarball: '{tb0}'")

        # name of tarball file only
        tb0_base = os.path.basename(tb0)
        log(f"{funcname}(): tarball filename: '{tb0_base}'")

        # tarball name format: eessi-VERSION-COMPONENT-OS-ARCH-TIMESTAMP.tar.gz
        # remove "-TIMESTAMP.tar.gz"
        # build_target format: eessi-VERSION-COMPONENT-OS-ARCH
        build_target = "-".join(tb0_base.split("-")[:-1])
        log(f"{funcname}(): tarball build target '{build_target}'")

        # timestamp in the filename
        timestamp = int(tb0_base.split("-")[-1][:-7])
        log(f"{funcname}(): tarball timestamp {timestamp}")

        deploy = False
        if upload_policy == "all":
            deploy = True
        elif upload_policy == "latest":
            if build_target in to_be_deployed:
                if to_be_deployed[build_target]["timestamp"] < timestamp:
                    # current one will be replaced
                    deploy = True
            else:
                deploy = True
        elif upload_policy == "once":
            uploaded = uploaded_before(build_target, job["job_dir"])
            if uploaded is None:
                deploy = True
            else:
                indent_fname = f"{' '*len(funcname + '(): ')}"
                log(f"{funcname}(): tarball for build target '{build_target}'\n"
                    f"{indent_fname}has been uploaded through '{uploaded}'")

        if deploy:
            to_be_deployed[build_target] = {"job_dir": job["job_dir"],
                                            "pr_comment_id": job["pr_comment_id"],
                                            "timestamp": timestamp}

    return to_be_deployed


def deploy_built_artefacts(pr, event_info):
    """
    Deploy built artefacts.

    Args:
        pr (github.PullRequest.PullRequest): PyGithub instance for the pull request
        event_info (dict): dictionary containing event information

    Returns:
        None (implicitly)
    """
    funcname = sys._getframe().f_code.co_name

    log(f"{funcname}(): deploy for PR {pr.number}")

    cfg = config.read_config()
    deploy_cfg = cfg[DEPLOYCFG]
    deploy_permission = deploy_cfg.get(DEPLOY_PERMISSION, '')
    log(f"{funcname}(): deploy permission '{deploy_permission}'")

    labeler = event_info['raw_request_body']['sender']['login']

    # verify that the GitHub account that set label bot:deploy has the
    # permission to trigger the deployment
    if labeler not in deploy_permission.split():
        log(f"{funcname}(): GH account '{labeler}' is not authorized to deploy")
        no_deploy_permission_comment = deploy_cfg.get(NO_DEPLOY_PERMISSION_COMMENT)
        repo_name = event_info["raw_request_body"]["repository"]["full_name"]
        pr_comments.create_comment(repo_name,
                                   pr.number,
                                   no_deploy_permission_comment.format(deploy_labeler=labeler))
        return
    else:
        log(f"{funcname}(): GH account '{labeler}' is authorized to deploy")

    # get upload policy from config
    upload_policy = deploy_cfg.get(UPLOAD_POLICY)
    log(f"{funcname}(): upload policy '{upload_policy}'")

    if upload_policy == "none":
        return

    # 1) determine the jobs that have been run for the PR
    # 2) for each job, check its status (SUCCESS or FAILURE)
    # 3) for the successful ones, determine which to deploy depending on policy
    # 4) call function to deploy a single artefact per software subdir

    # 1) determine the jobs that have been run for the PR
    job_dirs = determine_job_dirs(pr.number)
    log(f"{funcname}(): job_dirs = {','.join(job_dirs)}")

    # 2) for each job, check its status (SUCCESS or FAILURE)
    successes = determine_successful_jobs(job_dirs)

    # 3) for the successful ones, determine which to deploy depending on
    #    the upload policy
    to_be_deployed = determine_tarballs_to_deploy(successes, upload_policy)

    # 4) call function to deploy a single artefact per software subdir
    #    - update PR comments (look for comments with build-ts.tar.gz)
    repo_name = pr.base.repo.full_name

    for target, job in to_be_deployed.items():
        job_dir = job['job_dir']
        timestamp = job['timestamp']
        pr_comment_id = job['pr_comment_id']
        upload_tarball(job_dir, target, timestamp, repo_name, pr.number, pr_comment_id)
