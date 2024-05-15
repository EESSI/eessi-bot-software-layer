# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#

# Standard library imports
# (none yet)

# Third party imports (anything installed into the local Python environment)
# (none yet)

# Local application imports (anything from EESSI/eessi-bot-software-layer)
# (none yet)


# Constants for settings in JOB_WORKING_DIRECTORY/cfg/repos.cfg
#
# Access to a CernVM-FS repository is defined via a repos.cfg file and associated
# tarballs containing configuration settings per repository.
#
# Below, we define constants for the settings of each repository.
#
# Note, we do not define a constant for the section name, because for every
# repository we will use a different section name. For example, '[eessi-2023.06]'
# would define a section with name 'eessi-2023.06'.
#
REPOS_CFG_CONFIG_BUNDLE = "config_bundle"
REPOS_CFG_CONFIG_MAP = "config_map"
REPOS_CFG_CONTAINER = "container"
REPOS_CFG_REPO_NAME = "repo_name"
REPOS_CFG_REPO_VERSION = "repo_version"
