#!/usr/bin/env bash
#
# Slurm job script to call bot/build.sh in target pull request.
#
# This file is part of the EESSI build-and-deploy bot,
# see https://github.com/EESSI/eessi-bot-software-layer
#
# The bot helps with requests to add software installations to the
# EESSI software layer, see https://github.com/EESSI/software-layer
#
# author: Kenneth Hoste (@boegel)
# author: Thomas Roeblitz (@trz42)
# author: Sam Moors (@smoors)
#
# license: GPLv2
#

# ASSUMPTIONs:
#  - working directory has been prepared by the bot with a checkout of a
#    pull request (OR by some other means)
#  - the working directory contains a directory 'cfg' where the main config
#    file 'job.cfg' has been deposited
#  - the directory may contain any additional files references in job.cfg,
#    for example, repos.cfg and configuration file bundles for repositories

echo "Starting bot-build.slurm"
EXPORT_VARS_SCRIPT=cfg/export_vars.sh
if [ -f ${EXPORT_VARS_SCRIPT} ]; then
    echo "${EXPORT_VARS_SCRIPT} script found in '${PWD}', so sourcing it!"
    source ${EXPORT_VARS_SCRIPT}
    echo "$EXPORT_VARS_SCRIPT finished"
else
    echo "could not find ${EXPORT_VARS_SCRIPT} script in '${PWD}', skipping" >&2
fi

# First, read if there is a local_tmp or a site_config_script defined in
# the site_config section of cfg/job.cfg
# - local_tmp is used to define what location/storage folder is used as a base
#   for creating temporary directories
# - site_config_script points to a script that is used to customize local
#   settings for build jobs; if the script exists, it is sourced
JOB_CFG=cfg/job.cfg
inside_site_config=false
local_tmp_value=""
site_config_script_value=""
while IFS= read -r line; do
    # Check if we've reached [site_config]
    if [[ $line =~ ^\[site_config\]$ ]]; then
        inside_site_config=true
        continue
    fi

    # If another section starts and we haven't found local_tmp or
    # site_config_script, don't try to match
    if [[ $line =~ ^\[.*\]$ && $inside_site_config == true ]]; then
        inside_site_config=false
    fi

    # Extract 'local_tmp' or 'site_config_script' when inside [site_config]
    # and leave while loop when both are found
    if $inside_site_config && [[ $line =~ ^local_tmp\ *=\ *([^[:space:]]+) ]]; then
        local_tmp_value="${BASH_REMATCH[1]}"
    fi
    if $inside_site_config && [[ $line =~ ^site_config_script\ *=\ *([^[:space:]]+) ]]; then
        site_config_script_value="${BASH_REMATCH[1]}"
    fi
    if [[ -n "$local_tmp_value" ]] && [[ -n "$site_config_script_value" ]]; then
        break
    fi
done < "$JOB_CFG"
if [[ -n "${local_tmp_value}" ]]; then
    local_tmp_value=$(envsubst <<< ${local_tmp_value})
    # Ensure dir exists before calling mktemp
    mkdir -p ${local_tmp_value}
    local_tmp_value=$(mktemp -d --tmpdir=${local_tmp_value} eessi_job.XXXXXXXXXX)
    echo "Overwriting current TMPDIR '$TMPDIR' with the value '${local_tmp_value}', as configured in cfg/job.cfg"
    export TMPDIR="${local_tmp_value}"
fi

if [[ -n "${site_config_script_value}" ]] && [[ -r ${site_config_script_value} ]]; then
    echo "Sourcing site config script '${site_config_script_value}'"
    source "${site_config_script_value}"
else
    echo "Site config script defined as '${site_config_script_value}' does not exist; ignoring it"
fi

BOT_BUILD_SCRIPT=bot/build.sh
if [ -f ${BOT_BUILD_SCRIPT} ]; then
    echo "${BOT_BUILD_SCRIPT} script found in '${PWD}', so running it!"
    ${BOT_BUILD_SCRIPT}
else
    echo "could not find ${BOT_BUILD_SCRIPT} script in '${PWD}'" >&2
    exit 1
fi
echo "bot/build.sh finished"
CHECK_BUILD_SCRIPT=bot/check-build.sh
if [ -f ${CHECK_BUILD_SCRIPT} ]; then
    echo "${CHECK_BUILD_SCRIPT} script found in '${PWD}', so running it!"
    ${CHECK_BUILD_SCRIPT}
else
    echo "could not find ${CHECK_BUILD_SCRIPT} script in '${PWD}' ..."
    echo "... depositing default _bot_job${SLURM_JOB_ID}.result file in '${PWD}'"
    cat << 'EOF' > _bot_job${SLURM_JOB_ID}.result
[RESULT]
comment_description = <details><summary>:shrug: UNKNOWN _(click triangle for detailed information)_<summary/><ul><li>Did not find `bot/check-result.sh` script in job's work directory.</li><li>*Check job manually or ask an admin of the bot instance to assist you.*</li></ul></details>
status = UNKNOWN
artefacts =
EOF
fi
echo "check build step finished"

# SKIP_TESTS can be defined as export variable in the bot's config and then added to bot commands (export:SKIP_TESTS=yes)
if [[ "${SKIP_TESTS}" != "yes" ]]; then
    TEST_SCRIPT=bot/test.sh
    if [ -f ${TEST_SCRIPT} ]; then
        echo "${TEST_SCRIPT} script found in '${PWD}', so running it!"
        ${TEST_SCRIPT}
        echo "${TEST_SCRIPT} finished"
    else
        echo "could not find ${TEST_SCRIPT} script in '${PWD}'" >&2
    fi
fi

CHECK_TEST_SCRIPT=bot/check-test.sh
if [ -f ${CHECK_TEST_SCRIPT} ]; then
    echo "${CHECK_TEST_SCRIPT} script found in '${PWD}', so running it!"
    ${CHECK_TEST_SCRIPT}
else
    echo "could not find ${CHECK_TEST_SCRIPT} script in '${PWD}' ..."
    echo "... depositing default _bot_job${SLURM_JOB_ID}.test file in '${PWD}'"
    cat << 'EOF' > _bot_job${SLURM_JOB_ID}.test
[RESULT]
comment_description = <details><summary>:shrug: UNKNOWN _(click triangle for detailed information)_<summary/><ul><li>Did not find `bot/check-test.sh` script in job's work directory.</li><li>*Check job manually or ask an admin of the bot instance to assist you.*</li></ul></details>
status = UNKNOWN
artefacts =
EOF
fi
echo "check test step finished"
