#!/usr/bin/env python3
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

# parse command-line args
opts = args.parse()

repo_name = None
if opts.repository_name is not None:
    repo_name = opts.repository_name
else:
    print("need a full repository name")
    quit()

print("repository name: %s" % repo_name)

pr_number = None
if opts.pr_number is not None:
    pr_number = opts.pr_number
else:
    print("need a pull request number")
    quit()

print("pull request number: %s" % pr_number)

config.read_file("app.cfg")
github.connect()
gh = github.get_instance()
repo = gh.get_repo(repo_name)
pr   = repo.get_pull(int(pr_number))
base_ref = pr.base.ref

print("base_ref = '%s'" % base_ref)
