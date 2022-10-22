import glob
import os
import re
import subprocess

from datetime import datetime, timezone

from pyghee.utils import log, error

from connections import github
from tools import config

def determine_job_dirs(pr_number):
    """
    Determine job directories of the PR.
    """
    job_directories = []

    # job directories are any job IDs under jobs_base_dir/YYYY.MM/pr_<id>
    #   ---> we may have to scan multiple YYYY.MM directories
    buildenv = config.get_section('buildenv')
    jobs_base_dir = buildenv.get('jobs_base_dir')
    log("jobs_base_dir = %s" % jobs_base_dir)
    date_pr_job_pattern = '[0-9][0-9][0-9][0-9].[0-9][0-9]/pr_%s/[0-9]*' % pr_number
    log("date_pr_job_pattern = %s" % date_pr_job_pattern)
    glob_str = os.path.join(jobs_base_dir,date_pr_job_pattern)
    log("glob_str = %s" % glob_str)
    job_directories = glob.glob(glob_str)

    return job_directories

def determine_slurm_out(job_dir):
    """
    Determine path to slurm*out file for a job given a job directory.
    """
    slurm_out = os.path.join(job_dir,'slurm-%s.out' % os.path.basename(job_dir))
    log("slurm out path = '%s'" % slurm_out)
    return slurm_out


def determine_eessi_tarballs(job_dir):
    """
    Determine EESSI tarballs.
    """
    # determine all tarballs that are stored in the job directory
    #   (only expecting 1)
    tarball_pattern = 'eessi-*software-*.tar.gz'
    glob_str = os.path.join(job_dir,tarball_pattern)
    eessi_tarballs = glob.glob(glob_str)
    return eessi_tarballs


def check_build_status(slurm_out, eessi_tarballs):
    """
    Check status of job in a given directory.
    """
    # analyse job result

    # set some initial values
    no_missing_modules = False
    targz_created = False

    # check slurm out for the below strings
    #   ^No missing modules!$ --> software successfully installed
    #   ^/eessi_bot_job/eessi-.*-software-.*.tar.gz created!$ -->
    #     tarball successfully created
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
        return True

    return False

def update_pr_comment(tarball, repo_name, pr_number):
    """
    Update PR comment which contains specific tarball name.
    """
    # update PR comments (look for comments with build-ts.tar.gz)
    dt = datetime.now(timezone.utc)
    comment_update = '\n|%s|staged|uploaded `%s` to S3 bucket|' % (dt.strftime("%b %d %X %Z %Y"), tarball)

    gh = github.get_instance()
    repo = gh.get_repo(repo_name)
    pull_request = repo.get_pull(pr_number)
    comments = pull_request.get_issue_comments()
    for comment in comments:
        # NOTE adjust search string if format changed by event
        #        handler (separate process running
        #        eessi_bot_software_layer.py)
        cms = '.*%s.*' % tarball
    
        comment_match = re.search(cms, comment.body)

        if comment_match:
            log("update_pr_comment(): found comment with id %s" % comment.id)
            issue_comment = pull_request.get_issue_comment(int(comment.id))
            original_body = issue_comment.body
            issue_comment.edit(original_body + comment_update)
            break


def deploy_build(job_dir, build_target, timestamp, repo_name, pr_number):
    """
    Deploy built artefact by uploading it to an S3 bucket.
    """
    tarball = '%s-%d.tar.gz' % (build_target, timestamp)
    abs_path = '%s/%s' % (job_dir, tarball)
    log("found build: %s" % abs_path)
    # run 'eessi-upload-to-staging job_dir/build_target-timestamp.tar.gz'
    deploycfg = config.get_section('deploycfg')
    upload_to_s3_script = deploycfg.get('upload_to_s3_script')
    endpoint_url = deploycfg.get('endpoint_url') or ''
    bucket_name = deploycfg.get('bucket_name')

    cmd_args = [ upload_to_s3_script, ]
    if len(bucket_name) > 0:
        cmd_args.extend([ '--bucket-name', bucket_name ])
    if len(endpoint_url) > 0:
        cmd_args.extend([ '--endpoint-url', endpoint_url ])
    cmd_args.extend([ '--repository', repo_name ])
    cmd_args.extend([ '--pull-request', str(pr_number) ])
    cmd_args.append(abs_path)
    upload_cmd = ' '.join(cmd_args)

    log("Upload '%s' to bucket '%s' by running '%s' with endpoint_url '%s'" % (abs_path, bucket_name if len(bucket_name) > 0 else "DEFAULT", upload_cmd, endpoint_url if len(endpoint_url) > 0 else "EMPTY"))

    upload_to_s3 = subprocess.run(upload_cmd,
                                  shell=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
    log("Uploaded to S3 bucket!\nStdout %s\nStderr: %s" % (upload_to_s3.stdout,upload_to_s3.stderr))
    # TODO check for errors
    # add file to 'job_dir/../uploaded.txt'
    pr_base_dir = os.path.dirname(job_dir)
    uploaded_txt = os.path.join(pr_base_dir, 'uploaded.txt')
    uploaded_file = open(uploaded_txt, "a")
    job_plus_tarball = os.path.join(os.path.basename(job_dir), tarball)
    uploaded_file.write('%s\n' % job_plus_tarball)
    uploaded_file.close()

    update_pr_comment(tarball, repo_name, pr_number)

def uploaded_before(build_target, job_dir):
    """
    Determines if a tarball for the given build_target and job_dir
    has been uploaded before. It reads the file 'uploaded.txt' in
    directory 'job_dir/..'.
    Returns the name of the first tarball found if any or None.
    """
    pr_base_dir = os.path.dirname(job_dir)
    uploaded_txt = os.path.join(pr_base_dir, 'uploaded.txt')
    if os.path.exists(uploaded_txt):
        # do stuff
        re_string = '.*%s-.*.tar.gz.*' % build_target
        log("searching for '%s' in '%s'" % (re_string, uploaded_txt))
        re_build_target = re.compile(re_string)
        uploaded_file = open(uploaded_txt, "r")
        for line in uploaded_file:
            if re_build_target.match(line):
                log("found earlier upload: %s" % line.strip())
                uploaded_file.close()
                return line.strip()
            else:
                log("line '%s' did NOT match '%s'" % (line, re_string))
        log("file '%s' exists, no uploads for '%s' though" % (uploaded_txt, build_target))
        uploaded_file.close()
        return None
    else:
        log("file '%s' does not exist, hence no uploads for '%s' yet" % (uploaded_txt, build_target))
        return None


def deploy_built_artefacts(pr, event_info):
    """
    Deploy built artefacts.
    """
    log("Deploy built artefacts: PR#%s" % pr.number)

    deploycfg = config.get_section('deploycfg')
    upload_policy = deploycfg.get('upload_policy')

    if upload_policy == 'none':
        return

    # 1) determine what has been built for the PR
    #    - PRs are under jobs_base_dir/YYYY.MM/pr_<id> ---> we may have
    #      to scan multiple YYYY.MM directories
    # 2) for each build check the status of jobs (SUCCESS or FAILURE)
    #    - scan slurm*out file for: No modules missing! & created messages
    # 3) for the successful ones, only use the last (use timestamp in
    #    filename) for each software subdir
    # 4) call function to deploy a single artefact per software subdir

    # 1) determine what has been built for the PR
    #    - each job is stored in a directory given by its job ID
    #    - these job directories are stored under jobs_base_dir/YYYY.MM/pr_<id> ---> we may have
    #      to scan multiple YYYY.MM directories
    job_dirs = determine_job_dirs(pr.number)
    log("job_dirs = '%s'" % ','.join(job_dirs))

    # 2) for each build check the status of jobs (SUCCESS or FAILURE)
    #    - scan slurm*out file for: No modules missing! & created messages
    successes = []
    for job_dir in job_dirs:
        slurm_out = determine_slurm_out(job_dir)
        eessi_tarballs = determine_eessi_tarballs(job_dir)
        if check_build_status(slurm_out, eessi_tarballs):
            log("SUCCESS: build in '%s' was successful" % job_dir)
            successes.append({ 'job_dir': job_dir, 'slurm_out': slurm_out, 'eessi_tarballs': eessi_tarballs })
        else:
            log("FAILURE: build in '%s' was NOT successful" % job_dir)

    # 3) for the successful ones, determine which to deploy depending on policy
    #      'all': deploy all
    #      'latest': deploy only the last (use timestamp in filename) for each build target
    #      'once': deploy only latest if none for this build target has been deployed before
    # data structures:
    #  - IN: successes: list of dictionaries {job_dir, slurm_out, eessi_tarballs}
    #  - OUT: to_be_deployed: dictionary (key=build_target) of dictionaries {job_dir,timestamp}
    to_be_deployed = {}
    for sb in successes:
        # all tarballs for job
        tarballs = sb['eessi_tarballs']
        log("num tarballs: %d" % len(tarballs))
        # full path to first tarball for job
        tb0 = tarballs[0]
        log("1st tarball: %s" % tb0)
        # name of tarball file only
        tb0_base = os.path.basename(tb0)
        log("tarball base: %s" % tb0_base)
        # filename without '-TIMESTAMP.tar.gz' --> eessi-VERSION-{software,init,compat}-OS-ARCH
        build_target = '-'.join(tb0_base.split('-')[:-1])
        log("build_target: %s" % build_target)
        # timestamp in the filename
        timestamp = int(tb0_base.split('-')[-1][:-7])
        log("timestamp: %d" % timestamp)

        deploy = False
        if upload_policy == 'all':
            deploy = True
        elif upload_policy == 'latest':
            if build_target in to_be_deployed:
                if to_be_deployed[build_target]['timestamp'] < timestamp:
                    deploy = True
            else:
                deploy = True
        elif upload_policy == 'once':
            uploaded = uploaded_before(build_target, job_dir)
            if uploaded is None:
                deploy = True
            else:
                log("tarball for '%s' has been uploaded before ('%s')" % (build_target, uploaded))

        if deploy:
            to_be_deployed[build_target] = { 'job_dir': sb['job_dir'], 'timestamp': timestamp }

    # 4) call function to deploy a single artefact per software subdir
    #    - update PR comments (look for comments with build-ts.tar.gz)
    repo_name = pr.base.repo.full_name

    for build in to_be_deployed.keys():
        job_dir = to_be_deployed[build]['job_dir']
        timestamp = to_be_deployed[build]['timestamp']
        deploy_build(job_dir, build, timestamp, repo_name, pr.number)

