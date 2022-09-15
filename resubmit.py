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
import subprocess
import time

from connections import github
from datetime import datetime, timezone
from tools import args, config

from pyghee.utils import create_file, log

# "-o", "--original-job-dir",
# help="original job directory when resubmitting",
# "-r", "--rerun-job-dir",
# help="directory relative to original job directory which contains information to rerun job",

def mkdir(path):
    if not os.path.exists(path):
        os.makedirs(path)

opts = args.parse()

app_cfg_dir = os.path.dirname(os.path.realpath(__file__))
app_cfg = os.path.join(app_cfg_dir,'app.cfg')
print('app.cfg: %s\n' % app_cfg)

config.read_file(app_cfg)

#github.connect()

original_job_dir = os.getcwd()
if opts.original_job_dir is not None:
    original_job_dir = opts.original_job_dir
print("original job dir: '%s'" % original_job_dir)

rerun_job_dir = None
if opts.rerun_job_dir is not None:
    rerun_job_dir = os.path.join(original_job_dir,opts.rerun_job_dir)
else:
    # determine next dir for resubmission with scheme 'rerun_NUM' where NUM begins with 000
    run = 0
    while os.path.exists(os.path.join(original_job_dir, 'rerun_%03d' % run)):
        run += 1
    rerun_job_dir = os.path.join(original_job_dir, 'rerun_%03d' % run)
print("rerun job dir: '%s'" % rerun_job_dir)

# mkdir -p rerun_job_dir
mkdir(rerun_job_dir)

# determine files that belong to PR but not in rerun_job_dir
#   and create symlinks to them from rerun_job_dir
#   also need to handle directories in PR an rerun_job_dir
#   ignore .git... entries in PR
#  PR contents: git ls-tree -r HEAD --names-only
#  rerun_job_dir contents: glob.iglob(rerun_dir)

git_ls_tree_cmd = ' '.join( [
                      'git',
                      'ls-tree',
                      '-r', 'HEAD',
                      '--name-only' ])
s = subprocess.Popen([ "git ls-tree -r HEAD --name-only | grep -v '^\.'" ], shell=True, stdout=subprocess.PIPE).stdout
pr_files = s.read().splitlines()
rerun_files = glob.iglob(os.path.join(rerun_job_dir,'**'),recursive=True)
print("FILES IN PR:")
for s in pr_files:
    s_str = s.decode("UTF-8")
    print(s_str)
    for f in rerun_files:
        #print('%s -> abspath %s' % (f, os.path.abspath(f)) )
        if os.path.realpath(rerun_job_dir) != os.path.realpath(os.path.abspath(f)):
            ff
