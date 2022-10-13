#!/usr/bin/env python3
#
# script to resubmit a job with or without changes applied
#   only locally to a PR's content; still updating the
#   original PR comment and enabling the job manager to
#   pick the job up (including releasing it)
#
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#
## resubmit.py [PATH_TO_ORG_JOB [RERUN_DIR]]
## * if PATH_TO_ORG_JOB not given -> run from current directory
## * if RERUN_DIR (relative to PATH_TO_ORG_JOB) not given, create it
## * in RERUN_DIR create symlinks for all files not included in
##   the dir, that is all to all PR files in PATH_TO_ORG_DIR
## * resubmit job with same sbatch parameters as org
##   (/usr/bin/sbatch --hold --get-user-env --account=nn9992k \
##               --time=3-00:00:00 --nodes=1 \
##               --ntasks-per-node=12 --mem=60G \
##               --gres=localscratch:120G --partition normal \
##               --exclude=c1-[1-56],c2-[1-56],c3-[1-28],c5-[1-60] \
##       /cluster/projects/nn9992k/pilot.nessi/eessi-bot-software-layer/scripts/eessi-bot-build.slurm \
##          --tmpdir \$LOCALSCRATCH/EESSI \
##          --http-proxy http://proxy.saga:3128/ \
##          --https-proxy http://proxy.saga:3128/)
## * create _bot_jobID.metadata file
## * ensure symlink structures are maintained such that the job
##   manager can pick up the job as if it was submitted by the
##   event handler
## * update PR comment (need to identify comment): 
##     DATE | resubmitted | comment
##     new job id, directory; possibly changes (diff) as details

import configparser
import json
import glob
import os
import re
import shutil
import subprocess
import sys
import time

from connections import github
from datetime import datetime, timezone
from tools import args, config

from pyghee.utils import create_file

from git import Git, Repo
import requests
from typing import Tuple

# "-o", "--original-job-dir",
# help="original job directory when resubmitting",
# "-r", "--rerun-job-dir",
# help="directory relative to original job directory which contains information to rerun job",

############### BEGIN OF DEFINITIONS #####################################

def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)

# determine last jobid (in most cases there will be just one
#     jobid per directory)
#   - possible sources: _bot_job<JOBID>.metadata file(s),
#                       slurm-<JOBID>.out file(s)
def determine_last_jobid(directory: str = None) -> int:
    if directory is None:
        directory = os.getcwd()
    # TODO make sure that directory exists and is accessible
    # determine list of files (metadata or slurm out)
    glob_metadata = '_bot_job[0-9]*.metadata'
    metadata_files = glob.glob(os.path.join(directory, glob_metadata))
    glob_slurm_out = 'slurm-[0-9]*.out'
    slurm_out_files = glob.glob(os.path.join(directory, glob_slurm_out))
    job_ids = [ int(re.sub("(.*_bot_job)|(.metadata)", "", jobid)) for jobid in metadata_files ] + \
              [ int(re.sub("(.*slurm-)|(.out)", "", jobid)) for jobid in slurm_out_files ]
    # return based on number of jobs
    if len(job_ids) > 0:
        return sorted(job_ids, reverse=True)[0]
    else:
        return None


# get repo name and PR number from file _bot_job<JOBID>.metadata
#     the file should be written by the event handler to the working
#     dir of the job
def get_pull_request_info(jobid: int, directory: str = None) -> Tuple[str, int]:
    if directory is None:
        directory = os.getcwd()
    # TODO make sure that directory exists and is accessible
    job_metadata_file = '_bot_job%d.metadata' % jobid
    job_metadata_path = os.path.join(directory, job_metadata_file)
    metadata = configparser.ConfigParser()
    try:
        metadata.read(job_metadata_path)
    except Exception as e:
        print(e)
        error(f'Unable to read job metadata file {job_metadata_path}!')

    repo_name = None
    pr_number = None
    if 'PR' in metadata:
        metadata_pr = metadata['PR']
        repo_name = metadata_pr['repo'] or None
        pr_number = metadata_pr['pr_number'] or None

    return repo_name, pr_number


# get arch name, operating system and job params from file _bot_job<JOBID>.metadata
#     the file should be written by the event handler to the working
#     dir of the job
def get_arch_info(jobid: int, directory: str = None) -> Tuple[str, str, str]:
    if directory is None:
        directory = os.getcwd()
    # TODO make sure that directory exists and is accessible
    job_metadata_file = '_bot_job%d.metadata' % jobid
    job_metadata_path = os.path.join(directory, job_metadata_file)
    metadata = configparser.ConfigParser()
    try:
        metadata.read(job_metadata_path)
    except Exception as e:
        print(e)
        error(f'Unable to read job metadata file {job_metadata_path}!')

    arch_name = None
    os_name = None
    slurm_opt = None
    if 'ARCH' in metadata:
        metadata_arch = metadata['ARCH']
        arch_name = metadata_arch['architecture'] or None
        os_name   = metadata_arch['os'] or None
        slurm_opt = metadata_arch['slurm_opt'] or None

    return arch_name, os_name, slurm_opt


# download pull request to arch_job_dir
#  - PyGitHub doesn't seem capable of doing that (easily);
#  - for now, keep it simple and just execute the commands (anywhere) (note 'git clone' requires that destination is an empty directory)
#  NOTE, patching method seems to fail sometimes, using a different method
#    * patching method
#      git clone https://github.com/REPO_NAME arch_job_dir
#      git checkout base_ref_of_PR
#      curl -L https://github.com/REPO_NAME/pull/PR_NUMBER.patch > arch_job_dir/PR_NUMBER.patch
#    (execute the next one in arch_job_dir)
#      git am PR_NUMBER.patch
#
#  - REPO_NAME is repo_name
#  - PR_NUMBER is pr.number
def obtain_pull_request(work_directory: str,
                        target_directory: str,
                        repository_name: str,
                        pull_request_number: int,
                        base_ref: str) -> bool:

    # TODO check if target_directory already exists under work_directory
    # (1) clone repo
    repo_url = 'https://github.com/'+repository_name
    target_path = os.path.join(work_directory, target_directory)
    cloned_repo = Repo.clone_from(url=repo_url, to_path=target_path)
    assert cloned_repo.__class__ is Repo
    print("Cloned repo '%s' into '%s'." % (repo_url, target_path))

    git = Git(target_path)

    # (2) checkout base branch
    print("Checking out base branch: '%s'" % base_ref)
    status, co_out, co_err = git.checkout(base_ref, with_extended_output = True)
    print("Checked out branch: status %d, out '%s', err '%s'" % (status, co_out, co_err) )

    # (3) optain patch for pull request
    patch_file = pull_request_number + '.patch'
    patch_url = repo_url + '/pull/' + patch_file
    patch_target = os.path.join(target_path, patch_file)
    r = requests.get(patch_url)
    with open(patch_target, 'w') as p:
        p.write(r.text)
    print("Stored patch under '%s'." % patch_target)

    # (4) apply patch
    status, am_out, am_err = git.am(patch_target, with_extended_output = True)
    print("Applied patch: status %d, out '%s', err '%s'" % (status, am_out, am_err) )

    return (status == 0)


def remove_prefix(path: str, prefix: str) -> str:
    if path.startswith(prefix):
        return path[len(prefix):]
    return path


def copy_contents(source_directory: str, target_directory: str) -> bool:
    #print("source_directory %s" % source_directory)
    #print("target_directory %s" % target_directory)
    for root, dirs, files in os.walk(source_directory):
        path = root.split(os.sep)
        base = os.path.basename(root)
        dirname = os.path.dirname(root)
        #print("SRC: root %s, dir '%s', base '%s'" % (root, dirname, base))
        rel_target = remove_prefix(root, source_directory).strip('/')
        todir = os.path.join(target_directory, rel_target).rstrip('/')
        #print("DST: root %s, dir '%s', todir '%s'" % (target_directory, rel_target, todir))
        if root != source_directory:
            #if os.path.islink(root):
            #    print("%s%s %s (in dir %s)" % ((len(path)-2) * '---', '--L', base, dirname))
            #if os.path.isfile(root):
            #    print("%s%s %s (in dir %s)" % ((len(path)-2) * '---', '--F', base, dirname))
            if os.path.isdir(root):
                #print("%s%s %s (from dir %s to dir %s)" % ((len(path)-2) * '---', '--D', base, dirname, todir))
                mkdir(todir)
            #else:
            #    print("%s%s %s (in dir %s)" % ((len(path)-2) * '---', '--*', base, dirname))
        for f in files:
            src = os.path.join(root,f)
            if os.path.islink(src):
                #print("%s%s %s (from dir %s to dir %s)" % ((len(path)-1) * '---', '--L', f, root, todir))
                linkto = os.readlink(src)
                linkfrom = os.path.join(todir,f)
                #print("    symlink from %s to %s" % (linkfrom, linkto))
                os.symlink(linkto, linkfrom)
            else:
                #print("%s%s %s (from dir %s to dir %s)" % ((len(path)-1) * '---', '--f', f, root, todir))
                shutil.copy(src, todir)
            
    return True

############### END OF DEFINITIONS #######################################

print()

# parse command-line args
opts = args.parse()

# determine location of app config file (app.cfg)
#   IDEA should we have a command line argument for this one?
#   for now assumes that the file is in the directory of this script
app_cfg_dir = os.path.dirname(os.path.realpath(__file__))
app_cfg = os.path.join(app_cfg_dir,'app.cfg')
print('app.cfg ........: %s' % app_cfg)
# read config file
#   -> should make key parameters available:
#         private_key, build_job_script, {cvmfs_customizations},
#         http(s)_proxy, load_modules, {local_tmp}, slurm_params,
#         submit_command, arch_target_map, job_ids_dir
config.read_file(app_cfg)

# commented for now as it seemed to take very long to connect
#github.connect()

# determine directory of original job (current or given as argument)
original_job_dir = None
if opts.original_job_dir is not None:
    original_job_dir = opts.original_job_dir
else:
    original_job_dir = os.getcwd()
print("original job dir: %s" % original_job_dir)

# prepare directory for job to re-run
#   Note 1, it always creates a new directory 'rerun_NUM' under
#           original_job_dir.
#   Note 2, the directory rerun_job_dir is used as input for possible
#           changes to the original job. All contents of rerun_job_dir
#           is simply copied into rerun_NUM.
# (1) determine rerun_NUM under original_job_dir
run = 0
while os.path.exists(os.path.join(original_job_dir, 'rerun_%03d' % run)):
    run += 1
rerun_job_dir = os.path.join(original_job_dir, 'rerun_%03d' % run)
print("rerun job dir ..: %s" % rerun_job_dir)

# (2) prepare contents of rerun directory
#   (2a) get repo name and pr number from metadata file
#   (2b) get original PR, patch and apply patch (same method used by
#        event handler) + do customizations (cvmfs, ...)
#   (2c) copy contents from directory that contains changes
#
# (2a) get repo name and pr number from metadata file
org_job_id = determine_last_jobid(original_job_dir)
print("last job id ....: %d" % org_job_id)

repo_name, pr_number = get_pull_request_info(org_job_id, original_job_dir)

print("repository name.: %s" % repo_name)
print("pr number ......: %s" % pr_number)

arch_name, os_name, slurm_opt = get_arch_info(org_job_id, original_job_dir)

print("archictecture ..: %s" % arch_name)
print("operating system: %s" % os_name)
print("job params .....: %s" % slurm_opt)

gh = github.get_instance()
repo = gh.get_repo(repo_name)
pr   = repo.get_pull(int(pr_number))
base_ref = pr.base.ref

# (2b) get original PR, patch and apply patch (same method used by
#      event handler) + do customizations (cvmfs, ...)
if not obtain_pull_request(original_job_dir,
                           rerun_job_dir,
                           repo_name,
                           pr_number,
                           base_ref):
    print("failed to obtain pull request")
    sys.exit(-2)
# TODO do customizations

# (2c) copy contents from directory that contains changes
if opts.modified_job_dir is not None:
    copy_contents(opts.modified_job_dir, rerun_job_dir)

#sys.exit()

# (3) submit job, create metadata file, create symlink, update PR comment
# prepare metadata file --> after submission, just rename it
# create _bot_job<jobid>.metadata file in submission directory
bot_jobfile = configparser.ConfigParser()
bot_jobfile['PR'] = { 'repo' : repo_name, 'pr_number' : pr_number }
bot_jobfile['ARCH'] = { 'architecture' : arch_name, 'os' : os_name, 'slurm_opt' : slurm_opt }
bot_jobfile_path = os.path.join(rerun_job_dir, '_bot_job%s.metadata' % 'TEMP')
with open(bot_jobfile_path, 'w') as bjf:
    bot_jobfile.write(bjf)

# find PR comment (old job id, appname from app.cfg) and update it
#   'date | resubmitted | jobid + directory'
#     --> update method in job manager to find comment
# next line requires access to app.cfg which provides app_id,
#      installation_id and private_key
# - access to app.cfg requires that config app.cfg is read with
#      'config.read_file("app.cfg")'
#      should be done early in this script
comments = pr.get_issue_comments()
comment_id = ''
for comment in comments:
    # NOTE adjust search string if format changed by event
    #        handler (separate process running
    #        eessi_bot_software_layer.py)
    cms = '.*submitted.*job id `%s`.*' % org_job_id

    comment_match = re.search(cms, comment.body)

    if comment_match:
        print("found comment with id %s" % comment.id)
        comment_id = comment.id
        break

# prepare command for submission
# (first) obtain some config values
# [buildenv]
buildenv = config.get_section('buildenv')
jobs_base_dir = buildenv.get('jobs_base_dir')
print("jobs_base_dir '%s'" % jobs_base_dir)
local_tmp = buildenv.get('local_tmp')
print("local_tmp '%s'" % local_tmp)
build_job_script = buildenv.get('build_job_script')
print("build_job_script '%s'" % build_job_script)
submit_command = buildenv.get('submit_command')
print("submit_command '%s'" % submit_command)
slurm_params = buildenv.get('slurm_params')
print("slurm_params '%s'" % slurm_params)
http_proxy = buildenv.get('http_proxy') or ''
print("http_proxy '%s'" % http_proxy)
https_proxy = buildenv.get('https_proxy') or ''
print("https_proxy '%s'" % https_proxy)
load_modules = buildenv.get('load_modules') or ''
print("load_modules '%s'" % load_modules)

command_line = ' '.join([
    submit_command, # app.cfg
    slurm_params, # app.cfg
    slurm_opt, # read from _bot_jobJOBID.metadata of original job
    build_job_script, # app.cfg
    '--tmpdir', local_tmp, # app.cfg
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
if "generic" in arch_name:
    command_line += ' --generic'

print("Submit job for target '%s' with '%s' from directory '%s'" % (arch_name, command_line, rerun_job_dir))

submitted = subprocess.run(
    command_line,
    shell=True,
    cwd=rerun_job_dir,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE)

# sbatch output is 'Submitted batch job JOBID'
#   parse job id & add it to array of submitted jobs PLUS create a symlink from main pr_<ID> dir to job dir (job[0])
job_id = submitted.stdout.split()[3].decode("UTF-8")

# rename job metadata file
new_metadata_path = bot_jobfile_path.replace('TEMP', job_id, 1)
os.rename(bot_jobfile_path, new_metadata_path)

# print sbatch status
print("sbatch out: %s" % submitted.stdout.decode("UTF-8"))
print("sbatch err: %s" % submitted.stderr.decode("UTF-8"))

# create symlink from jobs_base_dir/YYYY.MM/pr_PR_NUMBER to
#   rerun_job_dir
job_mgr = config.get_section('job_manager')
job_ids_dir = job_mgr.get('job_ids_dir')
ym = datetime.today().strftime('%Y.%m')
pr_id = 'pr_%s' % pr.number
symlink = os.path.join(jobs_base_dir, ym, pr_id, job_id)
os.symlink(rerun_job_dir, symlink)

# update comment
if int(comment_id) > 0:
    print("updating comment with id %s" % comment_id)
    issue_comment = pr.get_issue_comment(int(comment_id))
    original_body = issue_comment.body
    dt = datetime.now(timezone.utc)
    update = '\n|%s|resubmitted|job id `%s`, dir `%s` awaits release by job manager|' % (dt.strftime("%b %d %X %Z %Y"), job_id, symlink)
    issue_comment.edit(original_body + update)
else:
    print("apparently no comment (%s) to update" % comment_id)
