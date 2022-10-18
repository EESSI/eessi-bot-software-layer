import glob
import os
import re
import subprocess

from connections import github
from datetime import datetime, timezone
from tools import config

from pyghee.utils import log

def determine_pr_dirs(pr_number):
    """
    Determine directories of the PR.
    """
    directories = []

    # PRs are under jobs_base_dir/YYYY.MM/pr_<id>
    #   ---> we may have to scan multiple YYYY.MM directories
    buildenv = config.get_section('buildenv')
    jobs_base_dir = buildenv.get('jobs_base_dir')
    print("jobs_base_dir = %s" % jobs_base_dir)
    date_pr_pattern = '[0-9][0-9][0-9][0-9].[0-9][0-9]/pr_%s/[0-9]*' % pr_number
    print("date_pr_pattern = %s" % date_pr_pattern)
    glob_str = os.path.join(jobs_base_dir,date_pr_pattern)
    print("glob_str = %s" % glob_str)
    pr_directories = glob.glob(glob_str)

    return pr_directories

def determine_slurm_out(pr_dir):
    """
    Determine path to slurm*out file for a job given a job directory.
    """
    slurm_out = os.path.join(pr_dir,'slurm-%s.out' % os.path.basename(pr_dir))
    print("slurm out path = '%s'" % slurm_out)
    return slurm_out


def determine_eessi_tarballs(pr_dir):
    """
    Determine EESSI tarballs.
    """
    # determine all tarballs that are stored in the job directory
    #   (only expecting 1)
    tarball_pattern = 'eessi-*software-*.tar.gz'
    glob_str = os.path.join(pr_dir,tarball_pattern)
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
            print("update_pr_comment(): found comment with id %s" % comment.id)
            issue_comment = pull_request.get_issue_comment(int(comment.id))
            original_body = issue_comment.body
            issue_comment.edit(original_body + comment_update)
            break


def deploy_build(pd, build, ts, repo_name, pr_number):
    """
    Deploy build.
    """
    tarball = '%s-%d.tar.gz' % (build, ts)
    abs_path = '%s/%s' % (pd, tarball)
    print("found build: %s" % abs_path)
    # TODO run script eessi-upload-to-staging pd/build-ts.tar.gz
    deploycfg = config.get_section('deploycfg')
    upload_to_s3_script = deploycfg.get('upload_to_s3_script')
    options = deploycfg.get('options')
    bucket = deploycfg.get('bucket')

    upload_cmd = ' '.join([
            upload_to_s3_script,
            abs_path,
        ])
    d = dict(os.environ)
    d["OPTIONS"] = options
    d["bucket"] = bucket
    print("Upload %s to bucket '%s' by running '%s' with options '%s'" % (abs_path, bucket, upload_cmd, options))
    upload_to_s3 = subprocess.run(upload_cmd,
                                  env=d,
                                  shell=True,
                                  stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE)
    print("Uploaded to S3 bucket!\nStdout %s\nStderr: %s" % (upload_to_s3.stdout,upload_to_s3.stderr))
    update_pr_comment(tarball, repo_name, pr_number)

def deploy_built_artefacts(pr, event_info):
    """
    Deploy built artefacts.
    """
    log("Deploy built artefacts: PR#%s" % pr.number)
    # 1) determine what has been built for the PR
    #    - PRs are under jobs_base_dir/YYYY.MM/pr_<id> ---> we may have
    #      to scan multiple YYYY.MM directories
    # 2) for each build check the status of jobs (SUCCESS or FAILURE)
    #    - scan slurm*out file for: No modules missing! & created messages
    # 3) for the successful ones, only use the last (use timestamp in
    #    filename) for each software subdir
    # 4) call function to deploy a single artefact per software subdir

    # 1) determine what has been built for the PR
    #    - PRs are under jobs_base_dir/YYYY.MM/pr_<id> ---> we may have
    #      to scan multiple YYYY.MM directories
    pr_dirs = determine_pr_dirs(pr.number)
    print("pr_dirs = '%s'" % ','.join(pr_dirs))

    # 2) for each build check the status of jobs (SUCCESS or FAILURE)
    #    - scan slurm*out file for: No modules missing! & created messages
    successes = []
    for pr_dir in pr_dirs:
        slurm_out = determine_slurm_out(pr_dir)
        eessi_tarballs = determine_eessi_tarballs(pr_dir)
        if check_build_status(slurm_out, eessi_tarballs):
            print("SUCCESS: build in '%s' was successful" % pr_dir)
            successes.append({ 'pr_dir': pr_dir, 'slurm_out': slurm_out, 'eessi_tarballs': eessi_tarballs })
        else:
            print("FAILURE: build in '%s' was NOT successful" % pr_dir)

    # 3) for the successful ones, only use the last (use timestamp in
    #    filename) for each software subdir
    last_successful = {}
    for sb in successes:
        tbs = sb['eessi_tarballs']
        print("num tarballs: %d" % len(tbs))
        tb0 = tbs[0]
        print("1st tarball: %s" % tb0)
        tb0_base = os.path.basename(tb0)
        print("tarball base: %s" % tb0_base)
        build_pre = '-'.join(tb0_base.split('-')[:-1])
        print("build_pre: %s" % build_pre)
        timestamp = int(tb0_base.split('-')[-1][:-7])
        print("timestamp: %d" % timestamp)
        if build_pre in last_successful:
            if last_successful[build_pre]['timestamp'] < timestamp:
                last_successful[build_pre] = { 'pr_dir': sb['pr_dir'], 'timestamp': timestamp }
        else:
            last_successful[build_pre] = { 'pr_dir': sb['pr_dir'], 'timestamp': timestamp }

    # 4) call function to deploy a single artefact per software subdir
    #    - update PR comments (look for comments with build-ts.tar.gz)
    repo_name = pr.base.repo.full_name

    for build in last_successful.keys():
        pd = last_successful[build]['pr_dir']
        ts = last_successful[build]['timestamp']
        deploy_build(pd, build, ts, repo_name, pr.number)

