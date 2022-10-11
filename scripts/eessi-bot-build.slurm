#!/usr/bin/env bash
#
# Slurm job script to install additional software into EESSI via build container
#
# This is part of the GitHub App for the EESSI project:
# A bot to help with requests to add software installations to the EESSI software layer,
# see https://github.com/EESSI/software-layer
#
# author: Kenneth Hoste (@boegel)
# author: Thomas Roeblitz (@trz42)
#
# license: GPLv2
#
#

# ASSUMPTIONs:
#  - running from a job environment on shared disc
#  - the job environment contains a checkout of the branch of the pull
#    request
#  - arguments: 
#    - eessi_tmpdir: hand over as argument to script

display_help() {
  echo "usage: $0 [OPTIONS]"
  echo "  -g | --generic               -  instructs script to build for generic architecture target"
  echo "  -h | --help                  -  display this usage information"
  echo "  -m | --load-modules MODULES  -  load modules before launching build container"
  echo "  -t | --tmpdir TMPDIR         -  path to tmp directory used by build container"
  echo "  -x | --http-proxy URL        -  provides URL for the environment variable http_proxy"
  echo "  -y | --https-proxy URL       -  provides URL for the environment variable https_proxy"
}

POSITIONAL_ARGS=()

load_modules=${load_modules:=}
tmpdir=${tmpdir:=}
http_proxy=${http_proxy:=}
https_proxy=${https_proxy:=}
common_opts=
install_software_opts=
create_tarball_opts=

while [[ $# -gt 0 ]]; do
  case $1 in
    -g|--generic)
      common_opts="${common_opts} --generic"
      generic_opt=" --generic"
      shift
      ;;
    -h|--help)
      display_help  # Call your function
      # no shifting needed here, we're done.
      exit 0
      ;;
    -m|--load-modules)
      load_modules="$2"
      shift 2
      ;;
    -t|--tmpdir)
      tmpdir="$2"
      eessi_tmpdir=$tmpdir
      shift 2
      ;;
    -x|--http-proxy)
      http_proxy="$2"
      install_software_opts="$install_software_opts --http-proxy $http_proxy"
      shift 2
      ;;
    -y|--https-proxy)
      https_proxy="$2"
      install_software_opts="$install_software_opts --https-proxy $https_proxy"
      shift 2
      ;;
    -*|--*)
      echo "Error: Unknown option: $1" >&2
      exit 1
      ;;
    *)  # No more options
      POSITIONAL_ARGS+=("$1") # save positional arg
      shift
      ;;
  esac
done

echo "Starting eessi-bot-build-slurm.sh"

echo -n "updating \$eessi_tmpdir: '$eessi_tmpdir' -> "
# replace any env variable in $eessi_tmpdir with its
#   current value (e.g., a value that is local to the job)
eessi_tmpdir=$(envsubst <<< $eessi_tmpdir)
echo "'$eessi_tmpdir'"

# bind current working directory to /eessi_bot_job in build container,
# and also use it as home directory in build container
export SINGULARITY_HOME="$(pwd):/eessi_bot_job"

# set tmp directory to deal with possibly too small /tmp
export SINGULARITY_TMPDIR=$eessi_tmpdir/singularity_tmpdir
mkdir -p $SINGULARITY_TMPDIR

# if eessi_tmpdir is not starting with '/tmp' map it to '/tmp'
# rationale: something else than /tmp is used for eessi_tmpdir
#            if /tmp has some limitations (e.g., size);
#            the bot job is then provided with a (job-specific)
#            alternative via the bot's config key local_tmp;
#            because many downstream scripts assume temporary
#            storage under /tmp, the alternative is mapped to
#            /tmp inside the container;
#            the mapping is only needed if $eessi_tmpdir not
#            already points to /tmp
if [[ $eessi_tmpdir != /tmp* ]] ;
then
    export SINGULARITY_BIND="$eessi_tmpdir:/tmp"
fi

echo "SINGULARITY_BIND=${SINGULARITY_BIND}"

# load modules if parameter --load-modules (or environment
#   variable load_modules) was given
if [[ ! -z $load_modules ]]; then
  for m in $(echo $load_modules | tr ',' '\n')
  do
    echo "eessi-bot-build.slurm: module load '$m'"
    module load $m
  done
else
  echo "eessi-bot-build.slurm: no modules to be loaded"
fi

source init/minimal_eessi_env  # for $EESSI_PILOT_VERSION and $EESSI_OS_TYPE

software_subdir=
for i in {1..9};
do
  echo "attempt $i to determine software_subdir"
  raw_output=$(./build_container.sh run ${eessi_tmpdir} python3 /eessi_bot_job/eessi_software_subdir.py ${generic_opt} 2>&1)
  echo "raw output of eessi_software_subdir.py: '$raw_output'"
  software_subdir=$(echo $raw_output | tail -1 | sed 's/.* //g')
  echo "software_subdir: '$software_subdir'"
  # check if software_subdir has the format:
  #   CPU_FAMILY/ARCH_IDENTIFIER
  if [[ $software_subdir == *"/"* ]]; then
    echo "software_subdir seems well formatted"
    break
  else
    n=$((1<<$i))
    echo "sleep $n secs (using exponential backoff)"
    sleep $n
  fi
done

# run standard EESSI software-layer install script
#   in compat layer environment inside build container
./build_container.sh run ${eessi_tmpdir} \
    ./install_software_layer.sh $install_software_opts $common_opts "$@"

# create tarball for the above build and place it in some specific
#   directory on shared disk (just in main directory of job)
#   see https://github.com/EESSI/eessi-bot-software-layer/issues/7

timestamp=$(date +%s)

export TGZ=$(printf "eessi-%s-software-%s-%s-%d.tar.gz" ${EESSI_PILOT_VERSION} ${EESSI_OS_TYPE} ${software_subdir//\//-} ${timestamp})

./build_container.sh run ${eessi_tmpdir} \
    ./create_tarball.sh ${eessi_tmpdir} ${EESSI_PILOT_VERSION} ${software_subdir} /eessi_bot_job/${TGZ}

# clean up eessi_tmpdir
# TODO add option to keep it for inspection
cd ${eessi_tmpdir} && rm -rf .
