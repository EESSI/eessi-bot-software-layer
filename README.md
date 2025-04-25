> [!NOTE]
> In the future the installation and configuration of the bot will be moved
> to the EESSI docs, likely under [Build-test-deploy bot](https://www.eessi.io/docs/bot/).

The bot helps automating tasks to build, to test and to deploy components of the
EESSI layers ([compatibility](https://github.com/EESSI/compatibility-layer) and
[software](https://github.com/EESSI/software-layer)). In the future, the bot may
be used with any repository that provides some scripts for building, testing and
deployment.

# Instructions to set up the EESSI bot components

The following sections describe and illustrate the steps necessary to set up the EESSI bot.
The bot consists of two main components provided in this repository:

- An event handler [`eessi_bot_event_handler.py`](eessi_bot_event_handler.py) which receives events from a GitHub repository and acts on them.
- A job manager [`eessi_bot_job_manager.py`](eessi_bot_job_manager.py) which monitors the Slurm job queue and acts on state changes of jobs submitted by the event handler.

## <a name="prerequisites"></a>Prerequisites

- GitHub account(s) (two needed for a development scenario), referring to them
  as `YOU_1` and `YOU_2` below
- A fork, say `YOU_1/software-layer`, of
  [EESSI/software-layer](https://github.com/EESSI/software-layer) and a fork,
  say `YOU_2/software-layer` of your first fork if you want to emulate the
  bot's behaviour but not change EESSI's repository. The EESSI bot will act on
  events triggered for the target repository (in this context, either
  `EESSI/software-layer` or `YOU_1/software-layer`).
- Access to a frontend/login node/service node of a Slurm cluster where the
  EESSI bot components will run. For the sake of brevity, we call this node
  simply `bot machine`.
- `singularity` with version 3.6 or newer _OR_ `apptainer` with version 1.0 or
  newer on the compute nodes of the Slurm cluster.
- On the cluster frontend (or where the bot components run), different tools
  may be needed to run the Smee client. For `x86_64`, `singularity` or
  `apptainer` are sufficient. For `aarch64`, the package manager `npm` is
  needed.
- The EESSI bot components and the (build) jobs will frequently access the
  Internet. Hence, worker nodes and the `bot machine` of the Slurm cluster
  need access to the Internet (either directly or via an HTTP proxy).

## <a name="step1"></a>Step 1: Smee.io channel and smee client

We use [smee.io](https://smee.io) as a service to relay events from GitHub
to the EESSI bot. To do so, create a new channel via https://smee.io and note
the URL, e.g., `https://smee.io/CHANNEL-ID`.

On the `bot machine` we need a tool which receives events relayed from
`https://smee.io/CHANNEL-ID` and forwards it to the EESSI bot. We use the Smee
client for this.

On machines with `x86_64` architecture, the Smee client can be run via a
container as follows

```
singularity pull docker://deltaprojects/smee-client
singularity run smee-client_latest.sif --url https://smee.io/CHANNEL-ID
```

or

```
singularity pull docker://deltaprojects/smee-client
singularity run smee-client_latest.sif --port 3030 --url https://smee.io/CHANNEL-ID
```

for specifying a different port than the default (3000).

On machines with `aarch64` architecture, we can install the the smee client via
the `npm` package manager as follows

```
npm install smee-client
```

and then running it with the default port (3000)

```
node_modules/smee-client/bin/smee.js --url https://smee.io/CHANNEL-ID
```

Another port can be used by adding the `--port PORT` argument, for example,

```
node_modules/smee-client/bin/smee.js --port 3030 --url https://smee.io/CHANNEL-ID
```

## <a name="step2"></a>Step 2: Registering GitHub App

We need to:
* register a GitHub App;
* link it to the `smee.io` channel;
* set a secret token to verify the webhook sender;
* set some permissions for the GitHub app;
* subscribe the GitHub app to selected events;
* define that this GitHub app should only be installed in your GitHub account (or organisation).

At the [app settings page](https://github.com/settings/apps) click "`New GitHub App`" and fill in the page, in particular the following fields:
- GitHub App name: give the app a name of you choice
- Homepage URL: use the Smee.io channel (`https://smee.io/CHANNEL-ID`) created in [Step 1](#step1)
- Webhook URL: use the Smee.io channel (`https://smee.io/CHANNEL-ID`) created in [Step 1](#step1)
- Webhook secret: create a secret token which is used to verify the webhook sender, for example using:
  ```shell
  python3 -c 'import secrets; print(secrets.token_hex(64))'
  ```
- Permissions: assign the required permissions to the app (e.g., read access to commits, issues, pull requests);
  - Make sure to assign read and write access to the Pull requests and Issues in "Repository permissions" section; these permisions can be changed later on;
  - Make sure to accept the new permissions from the "Install App" section that you can reach via the menu on the left hand side.
  - Then select the wheel right next to your installed app, or use the link `https://github.com/settings/installations/INSTALLATION_ID`
  - Once the page is open you will be able to accept the new permissions there.
  - Some permissions (e.g., metadata) will be selected automatically because of others you have chosen.

- Events: subscribe the app to events it shall react on (e.g., related to pull requests and comments)
- Select that the app can only be installed by this (your) GitHub account or organisation.

Click on "`Create GitHub App`" to complete this step.

## <a name="step3"></a>Step 3: Installing GitHub App

_Note, this will trigger the first event (`installation`). While the EESSI bot is not running yet, you can inspect this via the webpage for your Smee channel. Just open `https://smee.io/CHANNEL-ID` in a browser, and browse through the information included in the event. Naturally, some of the information will be different for other types of events._

You also need to *install* the GitHub App -- essentially telling GitHub to link the app to an account and one, several, or all repositories on whose events the app then should act upon.
  
Go to https://github.com/settings/apps and select the app you want to install by clicking on the icon left to the app's name or on the "`Edit`" button right next to the name of the app.

On the next page you should see the menu item "`Install App`" on the left-hand side. When you click on this you should see a page with a list of accounts and organisations you can install the app on. Choose one and click on the "`Install`" button next to it.

This leads to a page where you can select the repositories on whose the app should react to. Here, for the sake of simplicity, choose just `YOU_1/software-layer` as described in the [prerequisites](#prerequisites). Select one, multiple, or all and click on the "`Install`" button.

## <a name="step4"></a>Step 4: Installing the EESSI bot on a `bot machine`

The EESSI bot for the software layer is available from [EESSI/eessi-bot-software-layer](https://github.com/EESSI/eessi-bot-software-layer). This repository (or your fork of it) provides scripts and an example configuration file.

Get the EESSI bot _installed_ onto the `bot machine` by running something like

```
git clone https://github.com/EESSI/eessi-bot-software-layer.git
```
Determine the full path to bot directory:
```
cd eessi-bot-software-layer
pwd
```
Note the output of `pwd`. This will be used to replace `PATH_TO_EESSI_BOT` in the
configuration file `app.cfg` (see [Step 5.4](#step5.4)). In the remainder of this
page we will refer to this directory as `PATH_TO_EESSI_BOT`.

If you want to develop the EESSI bot, it is recommended that you fork the [EESSI/eessi-bot-software-layer](https://github.com/EESSI/eessi-bot-software-layer) repository and use the fork on the `bot machine`.

If you want to work with a specific pull request for the bot, say number 42, you can obtain the corresponding code with the following commands:
```
git clone https://github.com/EESSI/eessi-bot-software-layer.git
cd eessi-bot-software-layer
pwd
git fetch origin pull/42/head:PR42
git checkout PR42
```

The EESSI bot requires some Python packages to be installed, which are specified in the [`requirements.txt`](https://github.com/EESSI/eessi-bot-software-layer/tree/main/requirements.txt) file. It is recommended to install these in a virtual environment based on Python 3.7 or newer. See the commands below for an example on how to set up the virtual environment, activate it, and install the requirements for the EESSI bot. These commands assume that you are in the `eessi-bot-software-layer` directory:
```
# assumption here is that you start from *within* the eessi-bot-software-layer directory
cd ..
python3.7 -m venv venv_eessi_bot_p37
source venv_eessi_bot_p37/bin/activate
python --version                     # output should match 'Python 3.7.*'
which python                         # output should match '*/venv_eessi_bot_p37/bin/python'
python -m pip install --upgrade pip
cd eessi-bot-software-layer
pip install -r requirements.txt
```

Note, before you can start the bot components (see below), you have to activate the virtual environment with `source venv_eessi_bot_p37/bin/activate`.

You can exit the virtual environment simply by running `deactivate`.

### <a name="step4.1"></a>Step 4.1: Installing tools to access S3 bucket

The
[`scripts/eessi-upload-to-staging`](https://github.com/EESSI/eessi-bot-software-layer/blob/main/scripts/eessi-upload-to-staging)
script uploads an artefact and an associated metadata file to an S3 bucket.

It needs two tools for this:
* the `aws` command to actually upload the files;
* the `jq` command to create the metadata file.

This section describes how these tools are installed and configured on the `bot machine`.

#### Create a home for the `aws` and `jq` commands

Create a new directory, say `PATH_TO_EESSI_BOT/tools` and change into it.

```
mkdir PATH_TO_EESSI_BOT/tools
cd PATH_TO_EESSI_BOT/tools
```

#### Install `aws` command

For installing the AWS Command Line Interface, which provides the `aws` command,
follow the instructions at the
[AWS Command Line Interface guide](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html).

Add the directory that contains `aws` to the `$PATH` environment variable.
Make sure that `$PATH` is set correctly for newly spawned shells, e.g.,
it should be exported in a startup file such as `$HOME/.bash_profile`.

Verify that `aws` executes by running `aws --version`. Then, run
`aws configure` to set credentials for accessing the S3 bucket.
See [New configuration quick setup](https://docs.aws.amazon.com/cli/latest/userguide/getting-started-quickstart.html)
for detailed setup instructions. If you are using a non AWS S3 bucket
you will likely only have to provide the `Access Key ID` and the
`Secret Access Key`.

#### Install `jq` command

Next, install the tool `jq` into the same directory into which
`aws` was installed in (for example `PATH_TO_EESSI_BOT/tools`).
Download `jq` from `https://github.com/stedolan/jq/releases`
into that directory by running, for example,
```
cd PATH_TO_EESSI_BOT/tools
curl https://github.com/stedolan/jq/releases/download/jq-1.6/jq-linux64 -o jq-linux64
```
You may check if there are newer releases and choose a different
package depending on your operating system. Update the permissions
of the downloaded tool (`jq-linux64` for the above `curl` example)
with
```
chmod +x jq-linux64
```
Finally, create a symbolic link for `jq` by running
```
ln -s jq-linux64 jq
```

Check that the `jq` command works by running `jq --version`.

## <a name="step5"></a>Step 5: Configuring the EESSI bot on the `bot machine`

For the event handler, you need to set up two environment variables:
* `$GITHUB_TOKEN` (see [Step 5.1](#step5.1))
* `$GITHUB_APP_SECRET_TOKEN` (see [Step 5.2](#step5.2)).

For both the event handler and the job manager you need a private key (see [Step 5.3](#step5.3)).

### <a name="step5.1"></a>Step 5.1: GitHub Personal Access Token (PAT)

Create a Personal Access Token (PAT) for your GitHub account via the page https://github.com/settings/tokens where you find a button "`Generate new token`".

Give it meaningful name (field titled "`Note`"), and set the expiration date. Then select the scopes this PAT will be used for. Then click "`Generate token`".

On the result page, take note/copy the resulting token string -- it will only be shown once.

On the `bot machine` set the environment variable `$GITHUB_TOKEN`:
```
export GITHUB_TOKEN='THE_TOKEN_STRING'
```

in which you replace `THE_TOKEN_STRING` with the actual token.

### <a name="step5.2"></a>Step 5.2: GitHub App Secret Token

The GitHub App Secret Token is used to verify the webhook sender. You should have created one already when registering a new GitHub App in [Step 2](#step2).

On the `bot machine` set the environment variable `$GITHUB_APP_SECTRET_TOKEN`:
```
export GITHUB_APP_SECRET_TOKEN='THE_SECRET_TOKEN_STRING'
```

in which you replace `THE_SECRET_TOKEN_STRING` with the actual token.

Note that depending on the characters used in the string you will likely have to use *single quotes* (`'...'`) when setting the value of the environment variable.

### <a name="step5.3"></a>Step 5.3: Create a private key and store it on the `bot machine`

The private key is needed to let the app authenticate when updating information at the repository such as commenting on PRs, adding labels, etc. You can create the key at the page of the GitHub App you have registered in [Step 2](#step2).

Open the page https://github.com/settings/apps and then click on the icon left to the name of the GitHub App for the EESSI bot or the "`Edit`" button for the app.

Near the end of the page you will find a section "`Private keys`" where you can create a private key by clicking on the button "`Generate a private key`".

The private key should be automatically downloaded to your system. Copy it to the `bot machine` and note the full path to it (`PATH_TO_PRIVATE_KEY`).

For example: the private key is on your LOCAL computer. To transfer it to the
`bot machine` use the `scp` command for example: 
```
scp PATH_TO_PRIVATE_KEY_FILE_LOCAL_COMPUTER REMOTE_USERNAME@TARGET_HOST:TARGET/PATH
```
The location to where the private key is copied on the bot machine (`TARGET/PATH`) should be noted for `PATH_TO_PRIVATE_KEY`.

### <a name="step5.4"></a>Step 5.4: Create the configuration file `app.cfg`

If there is no `app.cfg` in the directory `PATH_TO_EESSI_BOT` yet, create an initial version from `app.cfg.example`.

```
cp -i app.cfg.example app.cfg
```

The example file (`app.cfg.example`) includes notes on what you have to adjust to run the bot in your environment.


#### `[github]` section

The section `[github]` contains information for connecting to GitHub:
```
app_id = 123456
```
Replace '`123456`' with the id of your GitHub App. You can find the id of your GitHub App via the page [GitHub Apps](https://github.com/settings/apps). On this page, select the app you have registered in [Step 2](#step2). On the opened page you will find the `app_id` in the section headed "`About`" listed as "`App ID`".
```
app_name = 'MY-bot'
```
The `app_name` specifies a short name for your bot. It will appear in comments to a pull request. For example, it could include the name of the cluster where the bot runs and a label representing the user that runs the bot, like `hal9000-bot`.

*Note: avoid putting an actual username here as it will be visible on potentially publicly accessible GitHub pages.*

```
installation_id = 12345678
```
Replace '`12345678`' with the id of the *installation* of your GitHub App (see [Step 3](#step3)).

You find the installation id of your GitHub App via the page [GitHub Apps](https://github.com/settings/apps). On this page, select the app you have registered in [Step 2](#step2). For determining the `installation_id` select "`Install App`" in the menu on the left-hand side. Then click on the gearwheel button of the installation (to the right of the "`Installed`" label). The URL of the resulting page contains the `installation_id` -- the number after the last "/".

The `installation_id` is also provided in the payload of every event within the top-level record named "`installation`". You can see the events and their payload on the webpage of your Smee.io channel (`https://smee.io/CHANNEL-ID`). Alternatively, you can see the events in the "`Advanced`" section of your GitHub App: open the [GitHub Apps](https://github.com/settings/apps) page, select the app you have registered in [Step 2](#step2), and choose "`Advanced`" in the menu on the left-hand side.
```
private_key = PATH_TO_PRIVATE_KEY
```
Replace `PATH_TO_PRIVATE_KEY` with the path you have noted in [Step 5.3](#step5.3).


#### `[buildenv]` section

The `[buildenv]` section contains information about the build environment.
```
build_job_script = PATH_TO_EESSI_BOT/scripts/bot-build.slurm
```
`build_job_script` points to the job script which will be submitted by the bot event handler.

```
shared_fs_path = PATH_TO_SHARED_DIRECTORY
```

Via `shared_fs_path` the path to a directory on a shared filesystem (NFS, etc.) can be provided,
which can be leveraged by the `bot/build.sh` script to store files that should be available across build jobs
(software source tarballs, for example).

```
build_logs_dir = PATH_TO_BUILD_LOGS_DIR
```

If build logs should be copied to a particular (shared) directory under certain conditions,
for example when a build failed, the `build_logs_dir` can be set to the path to which logs
should be copied by the `bot/build.sh` script.

```
container_cachedir = PATH_TO_SHARED_DIRECTORY
```
`container_cachedir` may be used to reuse downloaded container image files across jobs, so jobs can launch containers more quickly.

```
cvmfs_customizations = { "/etc/cvmfs/default.local": "CVMFS_HTTP_PROXY=\"http://PROXY_DNS_NAME:3128|http://PROXY_IP_ADDRESS:3128\"" }
```
It may happen that we need to customize the [CernVM-FS](https://cernvm.cern.ch/fs/) configuration for the build
job. The value of `cvmfs_customizations` is a dictionary which maps a file name
to an entry that needs to be appended to that file. In the example line above, the
configuration of `CVMFS_HTTP_PROXY` is appended to the file `/etc/cvmfs/default.local`.
The CernVM-FS configuration can be commented out, unless there is a need to customize the CernVM-FS configuration.

```
http_proxy = http://PROXY_DNS:3128/
https_proxy = http://PROXY_DNS:3128/
```
If compute nodes have no direct internet connection, we need to set `http(s)_proxy`
or commands such as `pip3` and `eb` (EasyBuild) cannot download software from
package repositories. Typically these settings are set in the prologue of a
Slurm job. However, when entering the [EESSI compatibility layer](https://www.eessi.io/docs/compatibility_layer),
most environment settings are cleared. Hence, they need to be set again at a later stage.

```
job_delay_begin_factor = 2
```
The `job_delay_begin_factor` setting defines how many times the `poll_interval` a
job's begin (EligibleTime) from now should be delayed if the handover protocol
is set to `delayed_begin` (see setting `job_handover_protocol`). That is, if
the `job_delay_begin_factor` is set to five (5) the delay time is calculated as
5 * `poll_interval`. The event manager would use 2 as default value when
submitting jobs.

```
job_handover_protocol = hold_release
```
The `job_handover_protocol` setting defines which method is used to handover a
job from the event handler to the job manager. Values are
 - `hold_release` (job is submitted with `--hold`, job manager removes the hold
   with `scontrol release`)
 - `delayed_begin` (job is submitted with `--begin=now+(5 * poll_interval)` and
    any `--hold` is removed from the submission parameters); see setting
    `poll_interval` further below; this is useful if the
    bot account cannot run `scontrol release` to remove the hold of the job;
    also, the status update in the PR comment of the job is extended by noting
    the `EligibleTime`

```
job_name = JOB_NAME
```
Replace `JOB_NAME` with a string of at least 3 characters that is used as job
name when a job is submitted. This is used to filter jobs, e.g., should be used
to make sure that multiple bot instances can run in the same Slurm environment.

```
jobs_base_dir = PATH_TO_JOBS_BASE_DIR
```
Replace `PATH_TO_JOBS_BASE_DIR` with an absolute filepath like `/home/YOUR_USER_NAME/jobs` (or another path of your choice). Per job the directory structure under `jobs_base_dir` is `YYYY.MM/pr_PR_NUMBER/event_EVENT_ID/run_RUN_NUMBER/OS+SUBDIR`. The base directory will contain symlinks using the job ids pointing to the job's working directory `YYYY.MM/...`.

```
load_modules = MODULE1/VERSION1,MODULE2/VERSION2,...
```
`load_modules` provides a means to load modules in the `build_job_script`.
None to several modules can be provided in a comma-separated list. It is
read by the bot and handed over to `build_job_script` via the `--load-modules` option.

```
local_tmp = /tmp/$USER/EESSI
```
`local_tmp` specifies the path to a temporary directory on the node building the software, i.e.,
on a compute/worker node. You may have to change this if temporary storage under
`/tmp` does not exist or is too small. This setting will be used for the
environment variable `$EESSI_TMPDIR`. The value is expanded only inside a running
job. Thus, typical job environment variables (like `$USER` or `$SLURM_JOB_ID`) may be used to isolate jobs running
simultaneously on the same compute node.

```
site_config_script = /path/to/script/if/any
```
`site_config_script` specifies the path to a script that - if it exists - is
sourced in the build job before any `bot/*` script is run. This allows to
customize the build environment due to specifics of the build site/cluster.
Note, such customizations could also be performed by putting them into a
module file and use the setting `load_modules` (see above). However, the
setting `site_config_script` provides a low threshold for achieving this, too.

```
slurm_params = "--hold"
```

`slurm_params` defines additional parameters for submitting batch jobs. `"--hold"` should be kept or the bot might not work as intended (the release step done by the job manager component of the bot would be circumvented). Additional parameters, for example, to specify an account, a partition, or any other parameters supported by the [`sbatch` command](https://slurm.schedmd.com/sbatch.html), may be added to customize the job submission.
```
submit_command = /usr/bin/sbatch
```
`submit_command` is the full path to the Slurm job submission command used for submitting batch jobs. You may want to verify if `sbatch` is provided at that path or determine its actual location (using `which sbatch`).

```
build_permission = GH_ACCOUNT_1 GH_ACCOUNT_2 ...
```
`build_permission` defines which GitHub accounts have the permission to trigger
build jobs, i.e., for which accounts the bot acts on `bot: build ...` commands.
If the value is left empty, everyone can trigger build jobs.

```
no_build_permission_comment = The `bot: build ...` command has been used by user `{build_labeler}`, but this person does not have permission to trigger builds.
```
`no_build_permission_comment` defines a comment (template) that is used when
the account trying to trigger build jobs has no permission to do so.

```
allow_update_submit_opts = false
```
`allow_update_submit_opts` determines whether or not to allow updating the submit
options via custom module `det_submit_opts` provided by the pull request being
processed.

```
allowed_exportvars = ["NAME1=value_1a", "NAME1=value_1b", "NAME2=value_2"]
```
`allowed_exportvars` defines a list of name-value pairs (environment
variables) that are allowed to be specified in a PR command with the
`exportvariable` filter. To specify multiple environment variables, multiple
`exportvariable` filters must be used (one per variable). These variables will
be exported into the build environment before running the bot/build.sh script.

The bot build script makes use of the variable `SKIP_TESTS` to determine if
ReFrame tests shall be skipped or not. Default is not to skip them. To allow the
use of the variable the setting could look like
```
allowed_exportvars = ["SKIP_TESTS=yes", "SKIP_TESTS=no"]
```


```
clone_git_repo_via = https
```

The `clone_git_repo_via` setting specifies via which mechanism the Git repository
should be cloned. This can be either:
* `https` (default): clone repository via HTTPS with `git clone https://github.com/<owner>/<repo>`
* `ssh`: clone repository via SSH with `git clone git@github.com:<owner>/<repo>.git`
In case of using 'ssh', one may need additional steps to ensure that the bot uses the right ssh key and does not ask for a passphrase (if the key used is protected with one). Here are a few things to consider:
- if the ssh key to be used does not have a standard name (e.g., `id_rsa`), add the following entry to `~/.ssh/config` in the bot's account
  ```
  Host github.com
    User git
    IdentityFile ~/.ssh/NAME_OF_PRIVATE_KEY_FILE
  ```
- if the key is protected by a passphrase (**highly recommended**), run an SSH agent and add the key to it
  ```
  eval $(ssh-agent -s)
  ssh-add ~/.ssh/NAME_OF_PRIVATE_KEY_FILE
  ```

#### `[bot_control]` section

The `[bot_control]` section contains settings for configuring the feature to
send commands to the bot.
```
command_permission = GH_ACCOUNT_1 GH_ACCOUNT_2 ...
```
The `command_permission` setting defines which GitHub accounts can send commands
to the bot (via new PR comments). If the value is empty *no* GitHub account can send
commands.

```
command_response_fmt = FORMAT_MARKDOWN_AND_HTML
```
`command_response_fmt` allows to customize the format of the comments about the handling of bot
commands. The format needs to include `{app_name}`, `{comment_response}` and
`{comment_result}`. `{app_name}` is replaced with the name of the bot instance.
`{comment_response}` is replaced with information about parsing the comment
for commands before any command is run. `{comment_result}` is replaced with
information about the result of the command that was run (can be empty).


#### `[deploycfg]` section

The `[deploycfg]` section defines settings for uploading built artefacts (tarballs).
```
artefact_upload_script = PATH_TO_EESSI_BOT/scripts/eessi-upload-to-staging
```
`artefact_upload_script` provides the location for the script used for uploading built software packages to an S3 bucket.

```
signing =
    {
        REPO_ID: {
            "script": PATH_TO_SIGN_SCRIPT,
            "key": PATH_TO_KEY_FILE,
            "container_runtime": PATH_TO_CONTAINER_RUNTIME
        }, ...
    }
```
`signing` provides a setting for signing artefacts. The value uses a JSON-like format
with `REPO_ID` being the repository ID. Repository IDs are defined in a file
`repos.cfg` (see setting `repos_cfg_dir`), `script` provides the location of the
script that is used to sign a file. If the location is a relative path, the script
must reside in the checked out pull request of the target repository (e.g.,
EESSI/software-layer). `key` points to the file of the key being used
for signing. The bot calls the script with the two arguments:
 1. private key (as provided by the attribute 'key')
 2. path to the file to be signed (the upload script will determine that)
NOTE (on `container_runtime`), signing requires a recent installation of OpenSSH
(8.2 or newer). If the frontend where the event handler runs does not have that
version installed, you can specify a container runtime via the `container_runtime`
attribute below. Currently, only Singularity or Apptainer are supported.
Note (on the key), make sure the file permissions are restricted to `0600` (only
readable+writable by the file owner, or the signing will likely fail.
Note (on json format), make sure no trailing commas are used after any elements
or parsing/loading the json will likely fail. Also, the whole value should start
at a new line and be indented as shown above.

```
endpoint_url = URL_TO_S3_SERVER
```
`endpoint_url` provides an endpoint (URL) to a server hosting an S3 bucket. The
server could be hosted by a commercial cloud provider like AWS or Azure, or
running in a private environment, for example, using Minio. The bot uploads
artefacts to the bucket which will be periodically scanned by the ingestion procedure at the Stratum 0 server.


```ini
# example: same bucket for all target repos
bucket_name = "eessi-staging"
```
```ini
# example: bucket to use depends on target repo
bucket_name = {
    "eessi-pilot-2023.06": "eessi-staging-2023.06",
    "eessi.io-2023.06": "software.eessi.io-2023.06",
}
```

`bucket_name` is the name of the bucket used for uploading of artefacts.
The bucket must be available on the default server (`https://${bucket_name}.s3.amazonaws.com`), or the one provided via `endpoint_url`.

`bucket_name` can be specified as a string value to use the same bucket for all target repos, or it can be mapping from target repo id to bucket name.


```
upload_policy = once
```

The `upload_policy` defines what policy is used for uploading built artefacts to an S3 bucket.

|`upload_policy` value|Policy|
|:--------|:--------------------------------|
|`all`|Upload all artefacts (mulitple uploads of the same artefact possible).|
|`latest`|For each build target (prefix in artefact name `eessi-VERSION-{software,init,compat}-OS-ARCH)` only upload the latest built artefact.|
|`once`|Only once upload any built artefact for the build target.|
|`none`|Do not upload any built artefacts.|

```
deploy_permission = GH_ACCOUNT_1 GH_ACCOUNT_2 ...
```
The `deploy_permission` setting defines which GitHub accounts can trigger the
deployment procedure. The value can be empty (*no* GitHub account can trigger the
deployment), or a space delimited list of GitHub accounts.

```
no_deploy_permission_comment = Label `bot:deploy` has been set by user `{deploy_labeler}`, but this person does not have permission to trigger deployments
```
This defines a message that is added to the status table in a PR comment
corresponding to a job whose artefact should have been uploaded (e.g., after
setting the `bot:deploy` label).


```
metadata_prefix = LOCATION_WHERE_METADATA_FILE_GETS_DEPOSITED
artefact_prefix = LOCATION_WHERE_TARBALL_GETS_DEPOSITED
```

These two settings are used to define where (which directory) in the S3 bucket
(see `bucket_name` above) the metadata file and the artefact will be stored. The
value `LOCATION...` can be a string value to always use the same 'prefix'
regardless of the target CVMFS repository, or can be a mapping of a target
repository id (see also `repo_target_map` below) to a prefix.

The prefix itself can use some (environment) variables that are set within
the upload script (see `artefact_upload_script` above). Currently those are:
 * `'${github_repository}'` (which would be expanded to the full name of the GitHub
   repository, e.g., `EESSI/software-layer`),
 * `'${legacy_aws_path}'` (which expands to the legacy/old prefix being used for
   storing artefacts/metadata files, the old prefix is
   `EESSI_VERSION/TARBALL_TYPE/OS_TYPE/CPU_ARCHITECTURE/TIMESTAMP/`), _and_
 * `'${pull_request_number}'` (which would be expanded to the number of the pull
   request from which the artefact originates).
Note, it's important to single-quote (`'`) the variables as shown above, because
they may likely not be defined when the bot calls the upload script.

The list of supported variables can be shown by running
`scripts/eessi-upload-to-staging --list-variables`.

**Examples:**
```
metadata_prefix = {"eessi.io-2023.06": "new/${github_repository}/${pull_request_number}"}
artefact_prefix = {
    "eessi-pilot-2023.06": "",
    "eessi.io-2023.06": "new/${github_repository}/${pull_request_number}"
    }
```
If left empty, the old/legacy prefix is being used.

#### `[architecturetargets]` section

The section `[architecturetargets]` defines for which targets (OS/SUBDIR), (for example `linux/x86_64/amd/zen2`) the EESSI bot should submit jobs, and which additional `sbatch` parameters will be used for requesting a compute node with the CPU microarchitecture needed to build the software stack.
```
arch_target_map = { "linux/x86_64/generic" : "--constraint shape=c4.2xlarge", "linux/x86_64/amd/zen2" : "--constraint shape=c5a.2xlarge" }
```
The map has one-to-many entries of the format `OS/SUBDIR :
ADDITIONAL_SBATCH_PARAMETERS`. For your cluster, you will have to figure out
which microarchitectures (`SUBDIR`) are available (as `OS` only `linux` is
currently supported) and how to instruct Slurm to allocate nodes with that
architecture to a job (`ADDITIONAL_SBATCH_PARAMETERS`).

Note, if you do not have to specify additional parameters to `sbatch` to request a compute node with a specific microarchitecture, you can just write something like:
```
arch_target_map = { "linux/x86_64/generic" : "" }
```

#### `[repo_targets]` section

The `[repo_targets]` section defines for which repositories and architectures the bot can run a job.
Repositories are referenced by IDs (or `repo_id`). Architectures are identified
by `OS/SUBDIR` which correspond to settings in the `arch_target_map`.

```
repo_target_map = {
    "OS_SUBDIR_1" : ["REPO_ID_1_1","REPO_ID_1_2"],
    "OS_SUBDIR_2" : ["REPO_ID_2_1","REPO_ID_2_2"] }
```
For each `OS/SUBDIR` combination a list of available repository IDs can be
provided.

The repository IDs are defined in a separate file, say `repos.cfg` which is
stored in the directory defined via `repos_cfg_dir`:
```
repos_cfg_dir = PATH_TO_SHARED_DIRECTORY/cfg_bundles
```
The `repos.cfg` file also uses the `ini` format as follows
```ini
[eessi-2023.06]
repo_name = software.eessi.io
repo_version = 2023.06
config_bundle = eessi.io-cfg_files.tgz
config_map = {"eessi.io/eessi.io.pub":"/etc/cvmfs/keys/eessi.io/eessi.io.pub", "default.local":"/etc/cvmfs/default.local", "eessi.io.conf":"/etc/cvmfs/domain.d/eessi.io.conf"}
container = docker://ghcr.io/eessi/build-node:debian11
```
The repository id is given in brackets (`[eessi-2023.06]`). Then the name of the repository (`repo_name`) and the
version (`repo_version`) are defined. Next, a tarball containing configuration files for CernVM-FS
is specified (`config_bundle`). The `config_map` setting maps entries of that tarball to locations inside
the file system of the container which is used when running the job. Finally, the
container to be used is given (`container`).

The `repos.cfg` file may contain multiple definitions of repositories.

#### `[event_handler]` section

The `[event_handler]` section contains information required by the bot event handler component.
```
log_path = /path/to/eessi_bot_event_handler.log
```
`log_path` specifies the path to the event handler log. 

#### `[job_manager]` section

The `[job_manager]` section contains information needed by the job manager.
```

log_path = /path/to/eessi_bot_job_manager.log
```
`log_path` specifies the path to the job manager log. 

```
job_ids_dir = /home/USER/jobs/ids
```
`job_ids_dir` specifies where the job manager should store information about jobs being tracked. Under this directory it will store information about submitted/running jobs under a subdirectory named '`submitted`', and about finished jobs under a subdirectory named '`finished`'.
```
poll_command = /usr/bin/squeue
```
`poll_command` is the full path to the Slurm command that can be used for checking which jobs exist. You may want to verify if `squeue` is provided at that path or determine its actual location (via `which squeue`).
```
poll_interval = 60
```
`poll_interval` defines how often the job manager checks the status of the jobs. The unit of the value is seconds.
```
scontrol_command = /usr/bin/scontrol
```
`scontrol_command` is the full path to the Slurm command used for manipulating existing jobs. You may want to verify if `scontrol` is provided at that path or determine its actual location (via `which scontrol`).

#### `[submitted_job_comments]` section

The `[submitted_job_comments]` section specifies templates for messages about newly submitted jobs.

DEPRECATED setting (use `awaits_release_delayed_begin_msg` and/or `awaits_release_hold_release_msg`)
```
awaits_release = job id `{job_id}` awaits release by job manager
```
`awaits_release` is used to provide a status update of a job (shown as a row in the job's status
table).

```
awaits_release_delayed_begin_msg = job id `{job_id}` will be eligible to start in about {delay_seconds} seconds
```
`awaits_release_delayed_begin_msg` is used when the `job_handover_protocol` is
set to `delayed_begin`. Note, both `{job_id}` and `{delay_seconds}` need to be
present in the value or the event handler will throw an exception when formatting
the update of the PR comment corresponding to the job.

```
awaits_release_hold_release_msg = job id `{job_id}` awaits release by job manager
```
`awaits_release_hold_release_msg` is used when the `job_handover_protocol` is
set to `hold_release`. Note, `{job_id}` needs to be present in the value or the
event handler will throw an exception when formatting the update of the PR
comment corresponding to the job.

```
initial_comment = New job on instance `{app_name}` for architecture `{arch_name}`{accelerator_spec} for repository `{repo_id}` in job dir `{symlink}`
```
`initial_comment` is used to create a comment to a PR when a new job has been
created. Note, the part '{accelerator_spec}' is only filled-in by the bot if the
argument 'accelerator' to the `bot: build` command has been used.
```
with_accelerator = &nbsp;and accelerator `{accelerator}`
```
`with_accelerator` is used to provide information about the accelerator the job
should build for if and only if the argument `accelerator:X/Y` has been provided.

#### `[new_job_comments]` section

The `[new_job_comments]` section sets templates for messages about jobs whose `hold` flag was released.
```
awaits_launch = job awaits launch by Slurm scheduler
```
`awaits_launch` specifies the status update that is used when the `hold` flag of a job has been removed.

#### `[running_job_comments]` section

The `[running_job_comments]` section sets templates for messages about jobs that are running.
```
running_job = job `{job_id}` is running
```
`running_job` specifies the status update for a job that started running.

#### `[finished_job_comments]` section

The `[finished_job_comments]` section sets templates for messages about finished jobs.
```
job_result_unknown_fmt = <details><summary>:shrug: UNKNOWN _(click triangle for details)_</summary><ul><li>Job results file `{filename}` does not exist in job directory, or parsing it failed.</li><li>No artefacts were found/reported.</li></ul></details>
```
`job_result_unknown_fmt` is used in case no result file (produced by `bot/check-build.sh`
provided by target repository) was found.

```
job_test_unknown_fmt = <details><summary>:shrug: UNKNOWN _(click triangle for details)_</summary><ul><li>Job test file `{filename}` does not exist in job directory, or parsing it failed.</li></ul></details>
```
`job_test_unknown_fmt` is used in case no test file (produced by `bot/check-test.sh`
provided by target repository) was found.


#### `[download_pr_comments]` section

The `[download_pr_comments]` section sets templates for messages related to
downloading the contents of a pull request.
```
git_clone_failure = Unable to clone the target repository.
```
`git_clone_failure` is shown when `git clone` failed.

```
git_clone_tip = _Tip: This could be a connection failure. Try again and if the issue remains check if the address is correct_.
```
`git_clone_tip` should contain some hint on how to deal with the issue. It is shown when `git clone` failed.

```
git_checkout_failure = Unable to checkout to the correct branch.
```
`git_checkout_failure` is shown when `git checkout` failed.

```
git_checkout_tip = _Tip: Ensure that the branch name is correct and the target branch is available._
```
`git_checkout_tip` should contain some hint on how to deal with the failure. It
is shown when `git checkout` failed.

```
curl_failure = Unable to download the `.diff` file.
```
`curl_failure` is shown when downloading the `PR_NUMBER.diff`
```
curl_tip = _Tip: This could be a connection failure. Try again and if the issue remains check if the address is correct_
```
`curl_tip` should help in how to deal with failing downloads of the `.diff` file.

```
git_apply_failure = Unable to download or merge changes between the source branch and the destination branch.
```
`git_apply_failure` is shown when applying the `.diff` file with `git apply`
failed.

```
git_apply_tip = _Tip: This can usually be resolved by syncing your branch and resolving any merge conflicts._
```
`git_apply_tip` should guide the contributor/maintainer about resolving the cause
of `git apply` failing.

#### `[clean_up]` section

The `[clean_up]` section includes settings related to cleaning up disk used by merged (and closed) PRs.
```
trash_bin_dir = PATH/TO/TRASH_BIN_DIRECTORY
```
Ideally this is on the same filesystem used by `jobs_base_dir` and `job_ids_dir` to efficiently move data
into the trash bin. If it resides on a different filesystem, the data will be copied.

```
moved_job_dirs_comment = PR merged! Moved `{job_dirs}` to `{trash_bin_dir}`
```
Template that is used by the bot to add a comment to a PR noting down which directories have been
moved and where.

# Step 6: Creating a ReFrame configuration file for the test step (only needed when building for the [EESSI software layer](https://github.com/EESSI/software-layer))
Part of the test step of the EESSI software layer is running the EESSI test suite. This requires putting a ReFrame configuration file in place that describes the partitions in the `arch_target_map` of the bot config.

You can find general documentation on how to write a ReFrame config file in the [EESSI documentation](https://www.eessi.io/docs/test-suite/ReFrame-configuration-file/). However, some specifics apply when setting things up for the test step:

- The configuration file has to be in `{shared_fs_path}/reframe_config.py` (recommended) or you have to set `RFM_CONFIG_FILES` to point to the configuration file and you have to make sure that is a location that is available (mounted) in the build container.
- The system name _has_ to be `BotBuildTests`
- Partition names should be ${EESSI_SOFTWARE_SUBDIR//\//_} for non-accelerator partitions and ${EESSI_SOFTWARE_SUBDIR//\//_}_${EESSI_ACCELERATOR_TARGET//\//_} for accelerator partitions. In words: the partition name should be the software subdir, replacing slashes with underscores, and for accelerators appending the accelerator target (again replacing slashes with underscores). E.g. x86_64_intel_skylake_avx512_nvidia_cc80 would be a valid partition name for a partition with Intel skylake's + Nvidia A100s.\
- The `scheduler` should be `local`, as the bot already schedules the job (ReFrame should just locally spawn the tests in the allocation created by the bot).
- The `access` field should not be used by ReFrame if the local scheduler is defined, you can simply omit this keyword.

To configure the number of GPUs and CPUs, we have two options: 
1. We describe the physical node in the ReFrame configuration file and set the `REFRAME_SCALE_TAG` environment variable to match the size of the allocation that you specify in your bot config. E.g. if your bot config allocates 1/4th of a node, one would set `REFRAME_SCALE_TAG=1_4_node` in the environment of the job submitted by the bot.
2. We describe a virtual node configuration that matches the size of the allcation created by the bot (and we use the default `REFRAME_SCALE_TAG=1_node`, you don't have to set this explicitely).

The first approach is the easiest, and thus recommended, since you can use CPU autodetection by ReFrame. The second approach allows for more flexibility.

## Approach 1 (recommended): describing the physical node and setting the `REFRAME_SCALE_TAG` to match the bot config's allocation size
In this approach, we describe the physical node configuration. That means: the amount of physical CPUs and GPUs present in the node.

For the CPU part, we can rely on ReFrame's CPU autodetection: if `remote_detect` is set to `True` in the general section of the config, and no CPU topology information is provided in the ReFrame configuration file, ReFrame will automatically detect the [CPU topology](https://reframe-hpc.readthedocs.io/en/stable/config_reference.html#config.systems.partitions.processor).

For the GPU part, we need to configure the vendor and the amount of GPUs. E.g. for a partition with 4 Nvidia GPUs per node:
```
'partition': {
...
    'extras': {
        GPU_VENDOR: GPU_VENDORS[NVIDIA],
    },
    'devices': [
        {
            'type': DEVICE_TYPES[GPU],
            'num_devices': 4,
        }
    ]
}
```

Now, we need to make sure ReFrame only starts tests that have scales that fit within the allocation created by the bot. E.g. on a GPU node, it would be quite common to only allocate a single GPU for building GPU software. In the above example, that means only a quarter node. We can make sure the EESSI test suite only runs tests that fit within a 25% of the physical node described above by making sure the `REFRAM_SCALE_TAG` environment variable is set to `1_4_node`. You can find a list of all valid values for the `REFRAME_SCALE_TAG` by checking the `SCALES` constant in the [EESSI test suite](https://github.com/EESSI/test-suite/blob/main/eessi/testsuite/constants.py).

Note that if you had e.g. a node with 6 GPUs per node, and you were building on 1 GPU, you probably want to go for Approach 2, since `1_6_node` is not a known scale in the EESSI test suite. Although you could set `REFRAME_SCALE_TAG=1_8_node`, this would lead to undefined behavior for the amount of GPUs allocated (may be 1, may be 0). For CPU-based nodes, this could however be a reasonable approach.

Note that if for _some_ partitions you use e.g. quarter nodes, and for some full nodes, you'll have to set the `REFRAME_SCALE_TAG` conditionally based on the node architecture. You could e.g. do this in a `.bashrc` that has some conditional logic to determine the node type and set the corresponding scale. Alternatively, you could use Approach 2.

### Complete example config
In this example, we assume a node with 4 A100 GPUs (compute capability `cc80`) and 72 CPU cores (Intel Skylake) and 512 GB of memory (of which 491520 MiB is useable by SLURM jobs; on this system the rest is reserved for the OS):
```
from eessi.testsuite.common_config import common_logging_config
from eessi.testsuite.constants import *  # noqa: F403


site_configuration = {
    'systems': [
        {
            'name': 'BotBuildTests',  # The system HAS to have this name, do NOT change it
            'descr': 'Software-layer bot',
            'hostnames': ['.*'],
            'modules_system': 'lmod',
            'partitions': [
                {
                    'name': 'x86_64_intel_skylake_avx512_nvidia_cc80',
                    'scheduler': 'local',
                    'launcher': 'mpirun',
                    'environs': ['default'],
                    'features': [
                        FEATURES[GPU]  # We want this to run GPU-based tests from the EESSI test suite
                    ] + list(SCALES.keys()),
                    'resources': [
                        {
                            'name': 'memory',
                            'options': ['--mem={size}'],
                        }
                    ],
                    'extras': {
                        # Make sure to round down, otherwise a job might ask for more mem than is available
                        # per node
                        'mem_per_node': 491520,  # in MiB (512 GB minus some reserved for the OS)
                        GPU_VENDOR: GPU_VENDORS[NVIDIA],
                    },
                    'devices': [
                        {
                            'type': DEVICE_TYPES[GPU],
                            'num_devices': 4,
                        }
                    ],
                    'max_jobs': 1
                },
            ]
        }
    ],
    'environments': [
        {
            'name': 'default',
            'cc': 'cc',
            'cxx': '',
            'ftn': ''
            }
        ],
    'general': [
        {
            'purge_environment': True,
            'resolve_module_conflicts': False,  # avoid loading the module before submitting the job
            'remote_detect': True,  # Make sure to automatically detect the CPU topology
        }
    ],
    'logging': common_logging_config(),
}
```

## Approach 2: describing a virtual node
In this approach, we describe a virtual node configuration for which the size matches exactly what is allocated by the bot (through the `slurm_params` and `arch_target_map`). In this example, we'll assume that this node has 4 GPUs and 72 cores, distributed over 2 sockets each consisting of 1 NUMA domain. We also assume our bot is configured with `slurm_params = --hold --nodes=1 --export=None --time=0:30:0` and `arch_target_map = {"linux/x86_64/intel/skylake_avx512" : "--partition=gpu --cpus-per-task=18 --gpus-per-node 1"}`, i.e. it effectively allocates a quarter node. We describe a virtual partition for ReFrame as if this quarter node is a full node, i.e. we pretend it is a partition with 18 cores and 1 GPU per node, with 1 socket. 

We would first have to hardcode the CPU configuration.
```
'partition': {
...
    'processor': {
          "num_cpus": 18,
          "num_cpus_per_core": 1,
          "num_cpus_per_socket": 18,
          "num_sockets": 1,
          "topology": {
              "numa_nodes": [
                # As stated, the 18 cores are on a single NUMA domain. Thus, the bitmask should be a sequence of 18 1's, which is 3ffff in hexadecimal representation
                "0x3ffff",  # a bit mask of 111111111111111111, i.e. cores 0-17 are on this NUMA domain
              ],
          },
    }
}
```

Note that if instead, this node would have had 8 NUMA domains (4 per socket), the 18 cores would correspond to 2 NUMA domains and we would have had to define:
```
"numa_nodes": [
    "0x001ff",  # a bit mask of 000000000111111111, i.e. cores 0-8 are on this NUMA domain
    "0x3fe00",  # a bit mask of 111111111000000000, i.e. cores 9-17 are on this NUMA domain
]
```

Note that the `topology` dictionary in a ReFrame configuration file can contain more information, such as the bitmasks for the CPU sockets and cores, as well as information on the caches (see [here](https://reframe-hpc.readthedocs.io/en/stable/config_reference.html#config.systems.partitions.processor.topology)). Currently, that information is not needed by the EESSI test suite, but that may change if tests are added that utilize such information to execute efficiently.

For the GPU configuration, we simply put:
```
'partition': {
...
    'extras': {
        GPU_VENDOR: GPU_VENDORS[NVIDIA],
    },
    'devices': [
        {
            'type': DEVICE_TYPES[GPU],
            'num_devices': 1,
        }
    ]
}
```
To match the fact that we allocate 1 GPU in the `arch_target_map`.

### Complete example config
In this example, we assume a node with 4 A100 GPUs (compute capability `cc80`) and 72 CPU cores (Intel Skylake) and 512 GB of memory (of which 491520 MiB is useable by SLURM jobs; on this system the rest is reserved for the OS). We also assume the bot configuration is such for this partition that 1/4th of these nodes gets allocated for a build job:
```
site_configuration = {
    'systems': [
        {
            'name': 'BotBuildTests',  # The system HAS to have this name, do NOT change it
            'descr': 'Software-layer bot',
            'hostnames': ['.*'],
            'modules_system': 'lmod',
            'partitions': [
                {
                    'name': 'x86_64_intel_skylake_avx512_nvidia_cc80',
                    'scheduler': 'local',
                    'launcher': 'mpirun',
                    'environs': ['default'],
                    'features': [
                        FEATURES[GPU]  # We want this to run GPU-based tests from the EESSI test suite
                    ] + list(SCALES.keys()),
                    'resources': [
                        {
                            'name': 'memory',
                            'options': ['--mem={size}'],
                        }
                    ],
                    'extras': {
                        # Make sure to round down, otherwise a job might ask for more mem than is available
                        # per node
                        'mem_per_node': 122880,  # in MiB (1/4th of 491520 MiB)
                        GPU_VENDOR: GPU_VENDORS[NVIDIA],
                    },
                    'devices': [
                        {
                            'type': DEVICE_TYPES[GPU],
                            'num_devices': 1,
                        }
                    ],
                    'processor': {
                          "num_cpus": 18,
                          "num_cpus_per_core": 1,
                          "num_cpus_per_socket": 18,
                          "num_sockets": 1,
                          "topology": {
                              "numa_nodes": [
                                # As stated, the 18 cores are on a single NUMA domain. Thus, the bitmask should be a sequence of 18 1's, which is 3ffff in hexadecimal representation
                                "0x3ffff",
                              ],
                          },
                    },
                    'max_jobs': 1
                },
            ]
        }
    ],
    'environments': [
        {
            'name': 'default',
            'cc': 'cc',
            'cxx': '',
            'ftn': ''
            }
        ],
    'general': [
        {
            'purge_environment': True,
            'resolve_module_conflicts': False,  # avoid loading the module before submitting the job
        }
    ],
    'logging': common_logging_config(),
}
```

# Step 7: Instructions to run the bot components

The bot consists of three components:
* the Smee client;
* the event handler;
* the job manager.

Running the Smee client was explained in [Step 1](#step1).

## <a name="step7.1"></a>Step 7.1: Running the event handler
As the event handler may run for a long time, it is advised to run it in a `screen` or `tmux` session.

The event handler is provided by the [`eessi_bot_event_handler.py`](https://github.com/EESSI/eessi-bot-software-layer/blob/main/eessi_bot_event_handler.py) Python script.

Change directory to `eessi-bot-software-layer` (which was created by cloning the
repository in [Step 4](#step4) - either the original one from EESSI, or your fork).

Then, simply run the event handler script:
```
./event_handler.sh
```
If multiple instances on the `bot machine` are being executed, you may need to run the event handler and the Smee client with a different port (default is 3000). The event handler can receive events on a different port by adding the parameter `--port PORTNUMBER`, for example,
```
./event_handler.sh --port 3030
```
See [Step 1](#step1) for telling the Smee client on which port the event handler receives events.

The event handler writes log information to the files `pyghee.log` and
`eessi_bot_event_handler.log`.

Note, if you run the bot on a frontend of a cluster with multiple frontends make sure that both the Smee client and the event handler run on the same system!

## <a name="step7.2"></a>Step 7.2: Running the job manager
As the job manager may run for a long time, it is advised to run it in a `screen` or `tmux` session.

The job manager is provided by the [`eessi_bot_job_manager_layer.py`](https://github.com/EESSI/eessi-bot-software-layer/blob/main/eessi_bot_job_manager.py) Python script. You can run the job manager from the directory `eessi-bot-software-layer` simply by:

```
./job_manager.sh
```

It will run in an infinite loop monitoring jobs and acting on their state changes.

If you want to limit the execution of the job manager, you can use thes options:
|Option|Argument|
|------|--------|
|`-i` / `--max-manager-iterations`|Any number _z_: _z_ < 0 - run the main loop indefinitely, _z_ == 0 - don't run the main loop, _z_ > 0 - run the main loop _z_ times|
|`-j` / `--jobs`|Comma-separated list of job ids the job manager shall process. All other jobs will be ignored.|

An example command would be

```
./job_manager.sh -i 1 -j 1234
```
to run the main loop exactly once for the job with ID `1234`.

The job manager writes log information to the file `eessi_bot_job_manager.log`.

The job manager can run on a different machine than the event handler, as long as both have access to the same shared filesystem.

# Example pull request on software-layer

For information on how to make pull requests and let the bot build software, see
[the bot section of the EESSI documentation](https://www.eessi.io/docs/bot/).

# Private target repos

Both Git and Curl need to have access to the target repo. A convenient way to
access a private repo via a Github token is by adding the following lines to
your `~/.netrc` and `~/.curlrc` files:

```
# ~/.netrc
machine github.com
login oauth
password <Github token>

machine api.github.com
login oauth
password <Github token>
```

```
# ~/.curlrc
--netrc
```

