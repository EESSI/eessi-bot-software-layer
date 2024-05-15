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
from tasks.build import get_build_env_cfg
from tools import config, job_metadata, pr_comments, run_cmd


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

    # a job directory's name has the format cfg[config.BUILDENV_SETTING_JOBS_BASE_DIR]/YYYY.MM/pr_<id>/JOBID
    #  - we may have to scan multiple YYYY.MM directories if the pull request was
    #    processed over more than one month (that is jobs were run in two or more
    #    months)
    #  - we assume that a JOBID is a positive integer
    cfg = config.read_config()
    build_env_cfg = get_build_env_cfg(cfg)
    jobs_base_dir = build_env_cfg[config.BUILDENV_SETTING_JOBS_BASE_DIR]
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
    metadata_file = os.path.join(job_dir, f"_bot_job{job_id}.metadata")
    metadata = job_metadata.get_section_from_file(metadata_file, job_metadata.JOB_PR_SECTION)
    if metadata and "pr_comment_id" in metadata:
        return int(metadata["pr_comment_id"])
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


def determine_artefacts(job_dir):
    """
    Determine paths to artefacts created by a job in a given job directory.

    Args:
        job_dir (string): working directory of the job

    Returns:
        (list): list of paths to all artefacts in job_dir
    """
    # determine all artefacts that are stored in the directory job_dir
    # by using the _bot_jobSLURM_JOBID.result file in that job directory
    job_id = job_metadata.determine_job_id_from_job_directory(job_dir)
    if job_id == 0:
        # could not determine job id, returning empty list of artefacts
        return None

    job_result_file = f"_bot_job{job_id}.result"
    job_result_file_path = os.path.join(job_dir, job_result_file)
    job_result = job_metadata.get_section_from_file(job_result_file_path, job_metadata.JOB_RESULT_SECTION)

    if job_result and job_metadata.JOB_RESULT_ARTEFACTS in job_result:
        # transform multiline value into a list
        artefacts_list = job_result[job_metadata.JOB_RESULT_ARTEFACTS].split('\n')
        # drop elements of length zero
        artefacts = [af for af in artefacts_list if len(af) > 0]
        return artefacts
    else:
        return None


def check_job_status(job_dir):
    """
    Check status of the job in a given directory.

    Args:
        job_dir (string): path to job directory

    Returns:
        (bool): True -> job succeeded, False -> job failed
    """
    fn = sys._getframe().f_code.co_name

    # use _bot_job<SLURM_JOBID>.result file to determine result status
    #   cases:
    #   (0) no job id --> return False
    #   (1) no result file --> return False
    #   (2) result file && status = SUCCESS --> return True
    #   (3) result file && status = FAILURE --> return False

    # case (0): no job id --> return False
    job_id = job_metadata.determine_job_id_from_job_directory(job_dir)
    if job_id == 0:
        # could not determine job id, return False
        log(f"{fn}(): could not determine job id from directory '{job_dir}'\n")
        return False

    job_result_file = f"_bot_job{job_id}.result"
    job_result_file_path = os.path.join(job_dir, job_result_file)
    job_result = job_metadata.get_section_from_file(job_result_file_path, job_metadata.JOB_RESULT_SECTION)

    job_status = job_metadata.JOB_RESULT_FAILURE
    if job_result and job_metadata.JOB_RESULT_STATUS in job_result:
        job_status = job_result[job_metadata.JOB_RESULT_STATUS]
    else:
        # case (1): no result file or no status --> return False
        log(f"{fn}(): no result file '{job_result_file_path}' or reading it failed\n")
        return False

    log(f"{fn}(): job status is {job_status} (compare against {job_metadata.JOB_RESULT_SUCCESS})\n")

    if job_status == job_metadata.JOB_RESULT_SUCCESS:
        # case (2): result file && status = SUCCESS --> return True
        log(f"{fn}(): found status 'SUCCESS' from '{job_result_file_path}'\n")
        return True
    else:
        # case (3): result file && status = FAILURE --> return False
        log(f"{fn}(): found status 'FAILURE' from '{job_result_file_path}'\n")
        return False


def update_pr_comment(artefact, repo_name, pr_number, pr_comment_id, state, msg):
    """
    Update pull request comment for the given comment id or artefact name

    Args:
        artefact (string): name of artefact that is looked for in a PR comment
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

    issue_comment = pr_comments.determine_issue_comment(pull_request, pr_comment_id, artefact)
    if issue_comment:
        dt = datetime.now(timezone.utc)
        comment_update = (f"\n|{dt.strftime('%b %d %X %Z %Y')}|{state}|"
                          f"transfer of `{artefact}` to S3 bucket {msg}|")

        # append update to existing comment
        issue_comment.edit(issue_comment.body + comment_update)


def append_artefact_to_upload_log(artefact, job_dir):
    """
    Append artefact to upload log.

    Args:
        artefact (string): name of artefact that has been uploaded
        job_dir (string): directory of the job that built the artefact

    Returns:
        None (implicitly)
    """
    # upload log file is 'job_dir/../uploaded.txt'
    pr_base_dir = os.path.dirname(job_dir)
    uploaded_txt = os.path.join(pr_base_dir, 'uploaded.txt')
    with open(uploaded_txt, "a") as upload_log:
        job_plus_artefact = os.path.join(os.path.basename(job_dir), artefact)
        upload_log.write(f"{job_plus_artefact}\n")


def upload_artefact(job_dir, payload, timestamp, repo_name, pr_number, pr_comment_id):
    """
    Upload artefact to an S3 bucket.

    Args:
        job_dir (string): path to the job directory
        payload (string): can be any name describing the payload, e.g., for
            EESSI it could have the format eessi-VERSION-COMPONENT-OS-ARCH
        timestamp (int): timestamp of the artefact
        repo_name (string): repository of the pull request
        pr_number (int): number of the pull request
        pr_comment_id (int): id of the pull request comment

    Returns:
        None (implicitly)
    """
    funcname = sys._getframe().f_code.co_name

    artefact = f"{payload}-{timestamp}.tar.gz"
    abs_path = os.path.join(job_dir, artefact)
    log(f"{funcname}(): uploading '{abs_path}'")

    # obtain config settings
    cfg = config.read_config()
    deploycfg = cfg[config.SECTION_DEPLOYCFG]
    artefact_upload_script = deploycfg.get(config.DEPLOYCFG_SETTING_ARTEFACT_UPLOAD_SCRIPT)
    endpoint_url = deploycfg.get(config.DEPLOYCFG_SETTING_ENDPOINT_URL) or ''
    bucket_spec = deploycfg.get(config.DEPLOYCFG_SETTING_BUCKET_NAME)
    metadata_prefix = deploycfg.get(config.DEPLOYCFG_SETTING_METADATA_PREFIX)
    artefact_prefix = deploycfg.get(config.DEPLOYCFG_SETTING_ARTEFACT_PREFIX)

    # if bucket_spec value looks like a dict, try parsing it as such
    if bucket_spec.lstrip().startswith('{'):
        bucket_spec = json.loads(bucket_spec)

    # if metadata_prefix value looks like a dict, try parsing it as such
    if metadata_prefix.lstrip().startswith('{'):
        metadata_prefix = json.loads(metadata_prefix)

    # if artefact_prefix value looks like a dict, try parsing it as such
    if artefact_prefix.lstrip().startswith('{'):
        artefact_prefix = json.loads(artefact_prefix)

    jobcfg_path = os.path.join(job_dir, job_metadata.JOB_CFG_DIRECTORY_NAME, job_metadata.JOB_CFG_FILENAME)
    jobcfg = config.read_config(jobcfg_path)
    target_repo_id = jobcfg[job_metadata.JOB_CFG_REPOSITORY_SECTION][job_metadata.JOB_CFG_REPOSITORY_REPO_ID]

    if isinstance(bucket_spec, str):
        bucket_name = bucket_spec
        log(f"Using specified bucket: {bucket_name}")
    elif isinstance(bucket_spec, dict):
        # bucket spec may be a mapping of target repo id to bucket name
        bucket_name = bucket_spec.get(target_repo_id)
        if bucket_name is None:
            update_pr_comment(artefact, repo_name, pr_number, pr_comment_id, "not uploaded",
                              f"failed (no bucket specified for {target_repo_id})")
            return
        else:
            log(f"Using bucket for {target_repo_id}: {bucket_name}")
    else:
        update_pr_comment(artefact, repo_name, pr_number, pr_comment_id, "not uploaded",
                          f"failed (incorrect bucket spec: {bucket_spec})")
        return

    if isinstance(metadata_prefix, str):
        metadata_prefix_arg = metadata_prefix
        log(f"Using specified metadata prefix: {metadata_prefix_arg}")
    elif isinstance(metadata_prefix, dict):
        # metadata prefix spec may be a mapping of target repo id to metadata prefix
        metadata_prefix_arg = metadata_prefix.get(target_repo_id)
        if metadata_prefix_arg is None:
            update_pr_comment(artefact, repo_name, pr_number, pr_comment_id, "not uploaded",
                              f"failed (no metadata prefix specified for {target_repo_id})")
            return
        else:
            log(f"Using metadata prefix for {target_repo_id}: {metadata_prefix_arg}")
    else:
        update_pr_comment(artefact, repo_name, pr_number, pr_comment_id, "not uploaded",
                          f"failed (incorrect metadata prefix spec: {metadata_prefix_arg})")
        return

    if isinstance(artefact_prefix, str):
        artefact_prefix_arg = artefact_prefix
        log(f"Using specified artefact prefix: {artefact_prefix_arg}")
    elif isinstance(artefact_prefix, dict):
        # artefact prefix spec may be a mapping of target repo id to artefact prefix
        artefact_prefix_arg = artefact_prefix.get(target_repo_id)
        if artefact_prefix_arg is None:
            update_pr_comment(artefact, repo_name, pr_number, pr_comment_id, "not uploaded",
                              f"failed (no artefact prefix specified for {target_repo_id})")
            return
        else:
            log(f"Using artefact prefix for {target_repo_id}: {artefact_prefix_arg}")
    else:
        update_pr_comment(artefact, repo_name, pr_number, pr_comment_id, "not uploaded",
                          f"failed (incorrect artefact prefix spec: {artefact_prefix_arg})")
        return

    # run 'eessi-upload-to-staging {abs_path}'
    # (1) construct command line
    #   script assumes a few defaults:
    #     bucket_name = 'eessi-staging'
    #     if endpoint_url not set use EESSI S3 bucket
    # (2) run command
    cmd_args = [artefact_upload_script, ]
    if len(artefact_prefix_arg) > 0:
        cmd_args.extend(['--artefact-prefix', artefact_prefix_arg])
    if len(bucket_name) > 0:
        cmd_args.extend(['--bucket-name', bucket_name])
    if len(endpoint_url) > 0:
        cmd_args.extend(['--endpoint-url', endpoint_url])
    if len(metadata_prefix_arg) > 0:
        cmd_args.extend(['--metadata-prefix', metadata_prefix_arg])
    cmd_args.extend(['--pr-comment-id', str(pr_comment_id)])
    cmd_args.extend(['--pull-request-number', str(pr_number)])
    cmd_args.extend(['--repository', repo_name])
    cmd_args.append(abs_path)
    upload_cmd = ' '.join(cmd_args)

    # run_cmd does all the logging we might need
    out, err, ec = run_cmd(upload_cmd, 'Upload artefact to S3 bucket', raise_on_error=False)

    if ec == 0:
        # add file to 'job_dir/../uploaded.txt'
        append_artefact_to_upload_log(artefact, job_dir)
        # update pull request comment
        update_pr_comment(artefact, repo_name, pr_number, pr_comment_id, "uploaded",
                          "succeeded")
    else:
        # update pull request comment
        update_pr_comment(artefact, repo_name, pr_number, pr_comment_id, "not uploaded",
                          "failed")


def uploaded_before(payload, job_dir):
    """
    Determines if an artefact for a job has been uploaded before. Function
    scans the log file named 'job_dir/../uploaded.txt' for the string
    '.*{payload}-.*.tar.gz'.

    Args:
        payload (string): can be any name describing the payload, e.g., for
            EESSI it could have the format eessi-VERSION-COMPONENT-OS-ARCH
        job_dir (string): working directory of the job

    Returns:
        (string): name of the first artefact found if any or None.
    """
    funcname = sys._getframe().f_code.co_name

    log(f"{funcname}(): any previous uploads for {payload}?")

    pr_base_dir = os.path.dirname(job_dir)
    uploaded_txt = os.path.join(pr_base_dir, "uploaded.txt")

    if os.path.exists(uploaded_txt):
        log(f"{funcname}(): upload log '{uploaded_txt}' exists")

        re_string = f".*{payload}-.*.tar.gz.*"
        re_payload = re.compile(re_string)

        with open(uploaded_txt, "r") as uploaded_log:
            log(f"{funcname}(): scan log for pattern '{re_string}'")
            for line in uploaded_log:
                if re_payload.match(line):
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
        artefacts = determine_artefacts(job_dir)
        pr_comment_id = determine_pr_comment_id(job_dir)

        if check_job_status(job_dir):
            log(f"{funcname}(): SUCCESSFUL job in '{job_dir}'")
            successes.append({'job_dir': job_dir,
                              'pr_comment_id': pr_comment_id,
                              'artefacts': artefacts})
        else:
            log(f"{funcname}(): FAILED job in '{job_dir}'")

    return successes


def determine_artefacts_to_deploy(successes, upload_policy):
    """
    Determine artefacts to deploy depending on upload policy

    Args:
        successes (list): list of dictionaries
            {'job_dir':job_dir, 'pr_comment_id':pr_comment_id, 'artefacts':artefacts}
        upload_policy (string): one of 'all', 'latest' or 'once'
            'all': deploy all
            'latest': deploy only the last for each payload
            'once': deploy only latest if none for this payload has
                    been deployed before
    Returns:
        (dictionary): dictionary of dictionaries representing artefacts to be deployed
    """
    funcname = sys._getframe().f_code.co_name

    log(f"{funcname}(): num successful jobs {len(successes)}")

    to_be_deployed = {}
    for job in successes:
        # all artefacts for successful job
        artefacts = job["artefacts"]
        log(f"{funcname}(): num artefacts {len(artefacts)}")

        # full path to first artefact for successful job
        # Note, only one artefact per job is expected.
        artefact = artefacts[0]
        log(f"{funcname}(): path to 1st artefact: '{artefact}'")

        # name of artefact file only
        artefact_base = os.path.basename(artefact)
        log(f"{funcname}(): artefact filename: '{artefact_base}'")

        # artefact name format: PAYLOAD-TIMESTAMP.tar.gz
        # remove "-TIMESTAMP.tar.gz" (last element when splitting along '-')
        payload = "-".join(artefact_base.split("-")[:-1])
        log(f"{funcname}(): artefact payload '{payload}'")

        # timestamp in the filename
        timestamp = int(artefact_base.split("-")[-1][:-7])
        log(f"{funcname}(): artefact timestamp {timestamp}")

        deploy = False
        if upload_policy == "all":
            deploy = True
        elif upload_policy == "latest":
            if payload in to_be_deployed:
                if to_be_deployed[payload]["timestamp"] < timestamp:
                    # current one will be replaced
                    deploy = True
            else:
                deploy = True
        elif upload_policy == "once":
            uploaded = uploaded_before(payload, job["job_dir"])
            if uploaded is None:
                deploy = True
            else:
                indent_fname = f"{' '*len(funcname + '(): ')}"
                log(f"{funcname}(): artefact for payload '{payload}'\n"
                    f"{indent_fname}has been uploaded through '{uploaded}'")

        if deploy:
            to_be_deployed[payload] = {"job_dir": job["job_dir"],
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
    deploy_cfg = cfg[config.SECTION_DEPLOYCFG]
    deploy_permission = deploy_cfg.get(config.DEPLOYCFG_SETTING_DEPLOY_PERMISSION, '')
    log(f"{funcname}(): deploy permission '{deploy_permission}'")

    labeler = event_info['raw_request_body']['sender']['login']

    # verify that the GitHub account that set label bot:deploy has the
    # permission to trigger the deployment
    if labeler not in deploy_permission.split():
        log(f"{funcname}(): GH account '{labeler}' is not authorized to deploy")
        no_deploy_permission_comment = deploy_cfg.get(config.DEPLOYCFG_SETTING_NO_DEPLOY_PERMISSION_COMMENT)
        repo_name = event_info["raw_request_body"]["repository"]["full_name"]
        pr_comments.create_comment(repo_name,
                                   pr.number,
                                   no_deploy_permission_comment.format(deploy_labeler=labeler))
        return
    else:
        log(f"{funcname}(): GH account '{labeler}' is authorized to deploy")

    # get upload policy from config
    upload_policy = deploy_cfg.get(config.DEPLOYCFG_SETTING_UPLOAD_POLICY)
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
    to_be_deployed = determine_artefacts_to_deploy(successes, upload_policy)

    # 4) call function to deploy a single artefact per software subdir
    repo_name = pr.base.repo.full_name

    for payload, job in to_be_deployed.items():
        job_dir = job['job_dir']
        timestamp = job['timestamp']
        pr_comment_id = job['pr_comment_id']
        upload_artefact(job_dir, payload, timestamp, repo_name, pr.number, pr_comment_id)
