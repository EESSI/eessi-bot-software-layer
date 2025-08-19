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

- GitHub account, say `GH_ACCOUNT`
- A fork, say `GH_ACCOUNT/software-layer`, of
  [EESSI/software-layer](https://github.com/EESSI/software-layer). The EESSI bot will act on
  events triggered for a repository its corresponding GitHub App was installed into.
  To install the GitHub App into a repository, the GitHub App needs to be
  configured such that it can be installed into any repository or all
  repositories belonging to an account/organisation and the installer
  (account/person who performs the "installation") has permissions to perform the
  installation.
- Access to a frontend/login node/service node of a Slurm cluster where the
  EESSI bot components will run. For the sake of brevity, we call this node
  simply `bot machine`.
- `singularity` with version 3.6 or newer _OR_ `apptainer` with version 1.0 or
  newer on the compute nodes of the Slurm cluster.
- On the `bot machine`, different tools may be needed to run the Smee client.
  The Smee client is available via a docker container and can be run with
  `singularity` or `apptainer`. Alternatively, the package manager `npm` may be
  used to install the Smee client. Running via the EESSI-built container is
  preferred.
- The EESSI bot components and the (build) jobs will frequently access the
  Internet. Hence, worker nodes and the `bot machine` of the Slurm cluster
  need access to the Internet (either directly or via an HTTP proxy).

## <a name="step1"></a>Step 1: Relaying events via Smee

### Step 1a: Create a Smee channel for your own/test scenario

_EESSI uses specific Smee channels. Access to them is restricted for
EESSI-internal use._
For development and testing purposes, one can use [smee.io](https://smee.io) as a service to relay events from GitHub
to the EESSI bot. To do so, create a new channel via [smee.io](https://smee.io) and note
the URL, e.g., `https://smee.io/CHANNEL-ID`.

### Step 1b: Install Smee client on `bot machine`

On the `bot machine` we need a tool (the Smee client) which receives events relayed from
`https://smee.io/CHANNEL-ID` and forwards it to the EESSI bot event handler.

NOTE, both options below rely on software (the Smee client) that is provided by
3rd parties. Use any of these options at your own risk!

#### EESSI-built container for Smee client (PREFERRED OPTION)

The Smee client can be run via a container as follows

```bash
apptainer run docker://ghcr.io/eessi/smee-client:latest --url https://smee.io/CHANNEL-ID
```

or

```bash
apptainer run docker://ghcr.io/eessi/smee-client:latest --url https://smee.io/CHANNEL-ID --port 3030
```

for specifying a different port than the default (3000).

#### Use Node.js-based Smee client (alternative option)

The Smee client can be installed via the package manager `npm` as follows

```bash
npm install smee-client
```

and then running it with

```bash
node_modules/smee-client/bin/smee.js --url https://smee.io/CHANNEL-ID
```

Another port can be used by adding the `--port PORT` argument. This can be particularly useful if you have multiple bot instances running on the same cluster, in which case you'd want a different port for each. As an example, one could use the non-default port 3030 in this way:

```bash
node_modules/smee-client/bin/smee.js --url https://smee.io/CHANNEL-ID --port 3030
```

## <a name="step2"></a>Step 2: Registering a GitHub App

We need to:

- register a GitHub App
- link it to the `smee.io` channel
- set a secret token used by GitHub to sign webhooks and used by the EESSI bot to
  verify that a received event originates from GitHub
- set some permissions for the GitHub app
- subscribe the GitHub app to selected events
- generate a private key (via GitHub GUI)

At the [app settings page](https://github.com/settings/apps) click <kbd style="background-color: #28a745; color: white;">New GitHub App</kbd> and fill in the page, in particular the following fields:

- **GitHub App name**: give the app a name of your choice
- **Homepage URL**: can use the Smee.io channel (`https://smee.io/CHANNEL-ID`) created in [Step 1](#step1)
- **Webhook URL**: MUST use the Smee.io channel (`https://smee.io/CHANNEL-ID`) created in [Step 1](#step1)
- **Secret**: create a secret token which is used to verify the webhook sender, for example using:

  ```shell
  python3 -c 'import secrets; print(secrets.token_hex(64))'
  ```

- **Permissions**: assign the required permissions to the app
  - Under "Repository permissions" assign "Read and write" for both "Issues" and
    "Pull requests"

    > [!NOTE]
    > "Read and write" permissions to "Pull requests" gives the bot powerful
    > means to _mess_ with your pull requests. Unfortunately, there is currently no way
    > around this or the bot could not create comments in pull requests.

- **Subscribe to events**: subscribe the app to events it shall react on
  - Select "Issue comment" and "Pull request" (Note, they may only be selectable
    after the required _Permissions_ have been chosen above.)
- **Where can this GitHub App be installed?**
  - Select "Only on this account"

Click on <kbd style="background-color: #28a745; color: white;">Create GitHub App</kbd> to create the app, then generate a private key
(see below).

### Generate private key

After clicking <kbd style="background-color: #28a745; color: white;">Create GitHub App</kbd> you will be informed with a banner
to generate a private key. You can follow the link in the banner or simply
scroll down to the section "Private keys"

Generate the private key, which downloads it and note the SHA256 string (to
more easily identify the key later on).

## <a name="step3"></a>Step 3: Installing the GitHub App into a repository

> [!NOTE]
> This will trigger the first event (`installation`). While the EESSI bot is not running yet, you can inspect this via the webpage for your Smee channel. Just open `https://smee.io/CHANNEL-ID` in a browser, and browse through the information included in the event. Naturally, some of the information will be different for other types of events.

You also need to _install_ the GitHub App -- essentially telling GitHub for which
repositories it should send events.
  
Go to [https://github.com/settings/apps/**APP_NAME**](https://github.com/settings/apps/**APP_NAME**) and select the menu item
**Install App** on the left-hand side.

On the next page you should see a list of accounts and organisations you can install the app on. Choose one and click on the <kbd style="background-color: #28a745; color: white;">Install</kdb> button next to it.

This leads to a page where you can select the repositories where the app should react to. Here, for the sake of simplicity, choose "Only select repositories", then open the pull-down menu named "Select repositories" and in there select `GH_ACCOUNT/software-layer` (`GH_ACCOUNT` is the GitHub account mentioned in section [prerequisites](#prerequisites)). Finally, click on the <kbd style="background-color: #28a745; color: white;">Install</kbd> button.

## <a name="step4"></a>Step 4: Installing the EESSI bot on a `bot machine`

The EESSI bot for the software layer is available from [EESSI/eessi-bot-software-layer](https://github.com/EESSI/eessi-bot-software-layer). This repository (or your fork of it) provides scripts and an example configuration file.

Get the EESSI bot _installed_ onto the `bot machine` by running something like

```bash
git clone https://github.com/EESSI/eessi-bot-software-layer.git
```

Determine the full path to bot directory:

```bash
cd eessi-bot-software-layer
pwd
```

Take note of the output of `pwd`. This will be used to replace `PATH_TO_EESSI_BOT` in the
configuration file `app.cfg` (see [Step 5.4](#step5.4)). In the remainder of this
page we will refer to this directory as `PATH_TO_EESSI_BOT`.

If you want to develop the EESSI bot, it is recommended that you fork the [EESSI/eessi-bot-software-layer](https://github.com/EESSI/eessi-bot-software-layer) repository and use the fork on the `bot machine`.

If you want to work with a specific pull request for the bot, say number 42, you can obtain the corresponding code with the following commands:

```bash
git clone https://github.com/EESSI/eessi-bot-software-layer.git
cd eessi-bot-software-layer
pwd
git fetch origin pull/42/head:PR42
git checkout PR42
```

The EESSI bot requires some Python packages to be installed, which are specified in the [`requirements.txt`](https://github.com/EESSI/eessi-bot-software-layer/tree/main/requirements.txt) file. It is recommended to install these in a virtual environment based on Python 3.7 or newer. See the commands below for an example on how to set up the virtual environment, activate it, and install the requirements for the EESSI bot. These commands assume that you are in the `eessi-bot-software-layer` directory:

```bash
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

You can exit the virtual environment by running `deactivate`.

### <a name="step4.1"></a>Step 4.1: Installing tools to access S3 bucket

The
[`scripts/eessi-upload-to-staging`](https://github.com/EESSI/eessi-bot-software-layer/blob/main/scripts/eessi-upload-to-staging)
script uploads an artefact and an associated metadata file to an S3 bucket.

It needs two tools for this:

- the `aws` command to actually upload the files;
- the `jq` command to create the metadata file.

This section describes how these tools are installed and configured on the `bot machine`.

#### Create a home for the `aws` and `jq` commands

Create a new directory, say `PATH_TO_EESSI_BOT/tools` and change into it.

```bash
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

```bash
cd PATH_TO_EESSI_BOT/tools
curl https://github.com/stedolan/jq/releases/download/jq-1.6/jq-linux64 -o jq-linux64
```

You may check if there are newer releases and choose a different
package depending on your operating system. Update the permissions
of the downloaded tool (`jq-linux64` for the above `curl` example)
with

```bash
chmod +x jq-linux64
```

Finally, create a symbolic link for `jq` by running

```bash
ln -s jq-linux64 jq
```

Check that the `jq` command works by running `jq --version`.

## <a name="step5"></a>Step 5: Configuring the EESSI bot on the `bot machine`

For the event handler, you need to set up two environment variables:

- `$GITHUB_TOKEN` (see [Step 5.1](#step5.1))
- `$GITHUB_APP_SECRET_TOKEN` (see [Step 5.2](#step5.2)).

For both the event handler and the job manager you need a private key (see [Step 5.3](#step5.3)).

### <a name="step5.1"></a>Step 5.1: GitHub Personal Access Token (PAT)

Create a Personal Access Token (PAT) for your GitHub account via the page [https://github.com/settings/tokens](https://github.com/settings/tokens) where you find a button <kbd style="background-color: #28a745; color: white;">Generate new token</kbd>.

Give it meaningful name in the field titled **Note**, and set the expiration date. Then select the scopes this PAT will be used for. Finally, click <kbd style="background-color: #28a745; color: white;">Generate token</kbd>.

On the result page, take note/copy the resulting token string -- it will only be shown once.

On the `bot machine` set the environment variable `$GITHUB_TOKEN`:

```bash
export GITHUB_TOKEN='THE_TOKEN_STRING'
```

in which you replace `THE_TOKEN_STRING` with the actual token.

### <a name="step5.2"></a>Step 5.2: GitHub App Secret Token

The GitHub App Secret Token is used to verify the webhook sender. You should have created one already when registering a new GitHub App in [Step 2](#step2).

On the `bot machine` set the environment variable `$GITHUB_APP_SECTRET_TOKEN`:

```bash
export GITHUB_APP_SECRET_TOKEN='THE_SECRET_TOKEN_STRING'
```

in which you replace `THE_SECRET_TOKEN_STRING` with the secret token you have created in [Step 2](#step2).

Note that depending on the characters used in the string you will likely have to use _single quotes_ (`'...'`) when setting the value of the environment variable.

### <a name="step5.3"></a>Step 5.3: Create a private key and store it on the `bot machine`

The private key is needed to let the app authenticate when updating information at the repository such as commenting on pull requests, adding labels, etc. You can create the key at the page of the GitHub App you have registered in [Step 2](#step2).

Open the page [https://github.com/settings/apps](https://github.com/settings/apps) and then click on the icon left to the name of the GitHub App for the EESSI bot or the <kbd style="background-color: #f6f8fa; color: #24292f; border: 1px solid #d0d7de; padding: 4px 8px; border-radius: 3px;">Edit</kbd> button for the app.

Near the end of the page you will find a section **Private keys** where you can create a private key by clicking on the button <kbd style="background-color: #f6f8fa; color: #24292f; border: 1px solid #d0d7de; padding: 4px 8px; border-radius: 3px;">Generate a private key</kbd>.

The private key should be automatically downloaded to your system. Copy it to the `bot machine` and note the full path to it (`PATH_TO_PRIVATE_KEY`). Also note down the day when the key was generated. The keys should be rotated every 6 months.

### <a name="step5.4"></a>Step 5.4: Create the configuration file `app.cfg`

If there is no `app.cfg` in the directory `PATH_TO_EESSI_BOT` yet, create an initial version from `app.cfg.example`.

```bash
cp -i app.cfg.example app.cfg
```

The example file (`app.cfg.example`) includes notes on what you have to adjust to run the bot in your environment.

#### `[github]` section

The section `[github]` contains information for connecting to GitHub:

```ini
app_id = 123456
```

Replace '`123456`' with the id of your GitHub App. You can find the id of your GitHub App via the page [GitHub Apps](https://github.com/settings/apps). On this page, select the app you have registered in [Step 2](#step2). On the opened page you will find the `app_id` in the section headed "`About`" listed as "`App ID`".

```ini
app_name = 'MY-bot'
```

The `app_name` specifies a short name for your bot. It will appear in comments to
a pull request. For example, it could include the name of the cluster where the
bot runs and a label representing the user that runs the bot, like `hal9000-bot`.
The name will be used when signing files uploaded to an S3 bucket. Thus, the name
has to be the same that is used as value for `namespaces` in the
`allowed_signers` file used during the ingestion procedure (see
[https://github.com/EESSI/filesystem-layer](https://github.com/EESSI/filesystem-layer)).
The file `allowed_signers` is provided by another (private) repository. More
information on its content can be obtained from the manual page for `ssh-keygen`
or from the sign script which is available as `scripts/sign_verify_file_ssh.sh`.

_Note: avoid putting an actual username here as it will be visible on potentially publicly accessible GitHub pages._

```ini
installation_id = 12345678
```

Replace '`12345678`' with the id of the _installation_ of your GitHub App (see [Step 3](#step3)).

You find the installation id of your GitHub App via the page [Applications](https://github.com/settings/installations). On this page, select the app you have registered in [Step 2](#step2) by clicking on the <kbd style="background-color: #f6f8fa; color: #24292f; border: 1px solid #d0d7de; padding: 4px 8px; border-radius: 3px;">Configure</kbd> button. The installation id is shown as the number after the last `/` of the page's URL.

The `installation_id` is also provided in the payload of every event within the top-level record named "`installation`". You can see the events and their payload on the webpage of your Smee.io channel (`https://smee.io/CHANNEL-ID`). Alternatively, you can see the events in the **Advanced** section of your GitHub App: open the [GitHub Apps](https://github.com/settings/apps) page, select the app you have registered in [Step 2](#step2), and choose **Advanced** in the menu on the left-hand side.

```ini
private_key = PATH_TO_PRIVATE_KEY
```

Replace `PATH_TO_PRIVATE_KEY` with the path you have noted in [Step 5.3](#step5.3).

#### `[bot_control]` section

The `[bot_control]` section contains settings for configuring the feature to
send commands to the bot.

```ini
command_permission = GH_ACCOUNT_1 GH_ACCOUNT_2 ...
```

The `command_permission` setting defines which GitHub accounts can send commands
to the bot (via new PR comments). If the value is empty _no_ GitHub account can send
commands.

```ini
command_response_fmt = FORMAT_MARKDOWN_AND_HTML
```

`command_response_fmt` allows to customize the format of the comments about the handling of bot
commands. The format needs to include `{app_name}`, `{comment_response}` and
`{comment_result}`. `{app_name}` is replaced with the name of the bot instance.
`{comment_response}` is replaced with information about parsing the comment
for commands before any command is run. `{comment_result}` is replaced with
information about the result of the command that was run (can be empty).

```ini
chatlevel = basic
```

`chatlevel` defines the amount of comments the bot writes into PRs (incognito - no comments, minimal - respond with single comment on bot commands `help`, `show_config`, `status` and `build` and update job progress, basic - minimal + report failures, or chatty - comments on any event being processed)
chatlevel = basic

#### `[buildenv]` section

The `[buildenv]` section contains information about the build environment.

```ini
build_job_script = PATH_TO_EESSI_BOT/scripts/bot-build.slurm
```

`build_job_script` points to the job script which will be submitted by the bot event handler.

```ini
shared_fs_path = PATH_TO_SHARED_DIRECTORY
```

Via `shared_fs_path` the path to a directory on a shared filesystem (NFS, etc.) can be provided,
which can be leveraged by the `bot/build.sh` script to store files that should be available across build jobs
(software source tarballs, for example).

```ini
build_logs_dir = PATH_TO_BUILD_LOGS_DIR
```

If build logs should be copied to a particular (shared) directory under certain conditions,
for example when a build failed, the `build_logs_dir` can be set to the path to which logs
should be copied by the `bot/build.sh` script.

```ini
container_cachedir = PATH_TO_SHARED_DIRECTORY
```

`container_cachedir` may be used to reuse downloaded container image files across jobs, so jobs can launch containers more quickly.

```ini
cvmfs_customizations = { "/etc/cvmfs/default.local": "CVMFS_HTTP_PROXY=\"http://PROXY_DNS_NAME:3128|http://PROXY_IP_ADDRESS:3128\"" }
```

It may happen that we need to customize the [CernVM-FS](https://cernvm.cern.ch/fs/) configuration for the build
job. The value of `cvmfs_customizations` is a dictionary which maps a file name
to an entry that needs to be appended to that file. In the example line above, the
configuration of `CVMFS_HTTP_PROXY` is appended to the file `/etc/cvmfs/default.local`.
The CernVM-FS configuration can be commented out, unless there is a need to customize the CernVM-FS configuration.

```ini
http_proxy = http://PROXY_DNS:3128/
https_proxy = http://PROXY_DNS:3128/
```

If compute nodes have no direct internet connection, we need to set `http(s)_proxy`
or commands such as `pip3` and `eb` (EasyBuild) cannot download software from
package repositories. Typically these settings are set in the prologue of a
Slurm job. However, when entering the [EESSI compatibility layer](https://www.eessi.io/docs/compatibility_layer),
most environment settings are cleared. Hence, they need to be set again at a later stage.

```ini
job_name = JOB_NAME
```

Replace `JOB_NAME` with a string of at least 3 characters that is used as job
name when a job is submitted. This is used to filter jobs, e.g., should be used
to make sure that multiple bot instances can run in the same Slurm environment.

```ini
job_delay_begin_factor = 2
```

The `job_delay_begin_factor` setting defines how many times the `poll_interval` a
job's begin (EligibleTime) from now should be delayed if the handover protocol
is set to `delayed_begin` (see setting `job_handover_protocol`). That is, if
the `job_delay_begin_factor` is set to five (5) the delay time is calculated as
5 * `poll_interval`. The event manager would use 2 as default value when
submitting jobs.

```ini
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

```ini
jobs_base_dir = PATH_TO_JOBS_BASE_DIR
```

Replace `PATH_TO_JOBS_BASE_DIR` with an absolute filepath like `/home/YOUR_USER_NAME/jobs` (or another path of your choice). Per job the directory structure under `jobs_base_dir` is `YYYY.MM/pr_PR_NUMBER/event_EVENT_ID/run_RUN_NUMBER/OS+SUBDIR`. The base directory will contain symlinks using the job ids pointing to the job's working directory `YYYY.MM/...`.

```ini
load_modules = MODULE1/VERSION1,MODULE2/VERSION2,...
```

`load_modules` provides a means to load modules in the `build_job_script`.
None to several modules can be provided in a comma-separated list. It is
read by the bot and handed over to `build_job_script` via the `--load-modules` option.

```ini
local_tmp = /tmp/$USER/EESSI
```

`local_tmp` specifies the path to a temporary directory on the node building the software, i.e.,
on a compute/worker node. You may have to change this if temporary storage under
`/tmp` does not exist or is too small. This setting will be used for the
environment variable `$EESSI_TMPDIR`. The value is expanded only inside a running
job. Thus, typical job environment variables (like `$USER` or `$SLURM_JOB_ID`) may be used to isolate jobs running
simultaneously on the same compute node.

```ini
site_config_script = /path/to/script/if/any
```

`site_config_script` specifies the path to a script that - if it exists - is
sourced in the build job before any `bot/*` script is run. This allows to
customize the build environment due to specifics of the build site/cluster.
Note, such customizations could also be performed by putting them into a
module file and use the setting `load_modules` (see above). However, the
setting `site_config_script` provides a low threshold for achieving this, too.

```ini
slurm_params = "--hold"
```

`slurm_params` defines additional parameters for submitting batch jobs. `"--hold"` should be kept or the bot might not work as intended (the release step done by the job manager component of the bot would be circumvented). Additional parameters, for example, to specify an account, a partition, or any other parameters supported by the [`sbatch` command](https://slurm.schedmd.com/sbatch.html), may be added to customize the job submission.

```ini
submit_command = /usr/bin/sbatch
```

`submit_command` is the full path to the Slurm job submission command used for submitting batch jobs. You may want to verify if `sbatch` is provided at that path or determine its actual location (using `which sbatch`).

```ini
build_permission = -NOT_ALLOWED_GH_ACCOUNT_NAME- [...]
```

`build_permission` defines which GitHub accounts have the permission to trigger
build jobs, i.e., for which accounts the bot acts on `bot: build ...` commands.
If the value is left empty, everyone can trigger build jobs. The string
`-NOT_ALLOWED_GH_ACCOUNT_NAME-` in the example above is not an allowed account
name on GitHub. Thus, one could not - by accident - give build permissions to an
unknown account.

```ini
no_build_permission_comment = The `bot: build ...` command has been used by user `{build_labeler}`, but this person does not have permission to trigger builds.
```

`no_build_permission_comment` defines a comment (template) that is used when
the account trying to trigger build jobs has no permission to do so.

```ini
allow_update_submit_opts = false
```

`allow_update_submit_opts` determines whether or not to allow updating the submit
options via custom module `det_submit_opts` provided by the pull request being
processed.
Should only be enabled (true) with care because this will result in code from the target
repository being executed by the event handler process, that is, not in a compute job.

```ini
allowed_exportvars = ["NAME1=value_1a", "NAME1=value_1b", "NAME2=value_2"]
```

`allowed_exportvars` defines a list of name-value pairs (environment
variables) that are allowed to be specified in a PR command with the
`exportvariable` filter. To specify multiple environment variables, multiple
`exportvariable` filters must be used (one per variable). These variables will
be exported into the build environment before running the `bot/build.sh` script.

The bot build script makes use of the variable `SKIP_TESTS` to determine if
ReFrame tests shall be skipped or not. Default is not to skip them. To allow the
use of the variable the setting could look like

```ini
allowed_exportvars = ["SKIP_TESTS=yes", "SKIP_TESTS=no"]
```

A resonable default setting is

```ini
allowed_exportvars = []
```

```ini
clone_git_repo_via = https
```

The `clone_git_repo_via` setting specifies via which mechanism the Git repository
should be cloned. This can be either:

- `https` (default): clone repository via HTTPS with `git clone https://github.com/<owner>/<repo>`
- `ssh`: clone repository via SSH with `git clone git@github.com:<owner>/<repo>.git`
  In case of using 'ssh', one may need additional steps to ensure that the bot uses the right SSH key and does not ask for a passphrase (if the key used is protected with one). Here are a few things to consider:
- if the ssh key to be used does not have a standard name (e.g., `id_rsa`), add the following entry to `~/.ssh/config` in the bot's account

  ```bash
  Host github.com
    User git
    IdentityFile ~/.ssh/NAME_OF_PRIVATE_KEY_FILE
  ```

- if the key is protected by a passphrase (**highly recommended**), run an SSH agent and add the key to it

  ```bash
  eval $(ssh-agent -s)
  ssh-add ~/.ssh/NAME_OF_PRIVATE_KEY_FILE
  ```

Note that the `bot: status` command doesn't work with SSH keys; you'll still need a Github token for that to work.

#### `[deploycfg]` section

The `[deploycfg]` section defines settings for uploading built artefacts (tarballs).

```ini
artefact_upload_script = PATH_TO_EESSI_BOT/scripts/eessi-upload-to-staging
```

`artefact_upload_script` provides the location for the script used for uploading built software packages to an S3 bucket.

```ini
endpoint_url = URL_TO_S3_SERVER
```

`endpoint_url` provides an endpoint (URL) to a server hosting an S3 bucket. The
server could be hosted by a commercial cloud provider like AWS or Azure, or
running in a private environment, for example, using Minio. In EESSI, the bot uploads
artefacts to the bucket which will be periodically scanned by the ingestion procedure at the Stratum 0 server.

```ini
# example: same bucket for all target repos
bucket_name = "eessi-staging"
```

```ini
# example: bucket to use depends on target repo identifier (see setting
#   `repo_target_map`)
#   the key is the identifier of a repo, while the value is the name of the bucket
bucket_name = {
    "eessi.io-2023.06-software": "eessi.io-staging-2023.06",
    "eessi.io-2025.06-software": "eessi.io-2025.06"
}
```

`bucket_name` is the name of the bucket used for uploading of artefacts.
The bucket must be available on the default server (`https://${bucket_name}.s3.amazonaws.com`), or the one provided via `endpoint_url`.

`bucket_name` can be specified as a string value to use the same bucket for all target repos, or it can be mapping from target repo id to bucket name.

```ini
upload_policy = once
```

The `upload_policy` defines what policy is used for uploading built artefacts to an S3 bucket.

|`upload_policy` value|Policy|
|:--------|:--------------------------------|
|`all`|Upload all artefacts (mulitple uploads of the same artefact possible).|
|`latest`|For each build target (prefix in artefact name `eessi-VERSION-{software,init,compat}-OS-ARCH)` only upload the latest built artefact.|
|`once`|Only once upload any built artefact for the build target.|
|`none`|Do not upload any built artefacts.|

```ini
deploy_permission = GH_ACCOUNT_1 GH_ACCOUNT_2 ...
```

The `deploy_permission` setting defines which GitHub accounts can trigger the
deployment procedure. The value can be empty (_no_ GitHub account can trigger the
deployment), or a space delimited list of GitHub accounts.

```ini
no_deploy_permission_comment = Label `bot:deploy` has been set by user `{deploy_labeler}`, but this person does not have permission to trigger deployments
```

This defines a message that is added to the status table in a PR comment
corresponding to a job whose artefact should have been uploaded (e.g., after
setting the `bot:deploy` label).

```ini
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

- `'${github_repository}'` (which would be expanded to the full name of the GitHub
  repository, e.g., `EESSI/software-layer`),
- `'${legacy_aws_path}'` (which expands to the legacy/old prefix being used for
  storing artefacts/metadata files, the old prefix is
  `EESSI_VERSION/TARBALL_TYPE/OS_TYPE/CPU_ARCHITECTURE/TIMESTAMP/`), _and_
- `'${pull_request_number}'` (which would be expanded to the number of the pull
  request from which the artefact originates).
Note, it's important to single-quote (`'`) the variables as shown above, because
they may likely not be defined when the bot calls the upload script.

The list of supported variables can be shown by running
`scripts/eessi-upload-to-staging --list-variables`.

**Examples:**

```ini
metadata_prefix = {"eessi.io-2023.06": "new/${github_repository}/${pull_request_number}"}
artefact_prefix = {
    "eessi-pilot-2023.06": "",
    "eessi.io-2023.06": "new/${github_repository}/${pull_request_number}"
    }
```

If left empty, the old/legacy prefix is being used.

```ini
signing =
    {
        "REPO_ID": {
            "script": "PATH_TO_SIGN_SCRIPT",
            "key": "PATH_TO_KEY_FILE",
            "container_runtime": "PATH_TO_CONTAINER_RUNTIME"
        }
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

> [!NOTE]
> Wrt `container_runtime`, signing requires a recent installation of OpenSSH
> (8.2 or newer). If the frontend where the event handler runs does not have that
> version installed, you can specify a container runtime via the `container_runtime`
> attribute below. Currently, only Singularity or Apptainer are supported.
> [!NOTE]
> Wrt to the private key file, make sure the file permissions are restricted to `0600`
> (only readable+writable by the file owner) or the signing will likely fail.
> [!NOTE]
> Wrt to the JSON-like format, make sure commas are only used for separating elements
> and that there is no trailing comma on the last element, or parsing/loading the json
> will likely fail. Also, the whole value should start a new line and be indented as shown
> above.
> [!NOTE]
> As shown in the example, use double quotes for all keys and values.

#### `[architecturetargets]` section

The section `[architecturetargets]` defines for which targets (OS/SUBDIR), (for example `linux/x86_64/amd/zen2`) the EESSI bot should submit jobs, and which additional `sbatch` parameters will be used for requesting a compute node with the CPU microarchitecture needed to build the software stack.

```ini
node_type_map = {
    "cpu_zen2": {
        "os": "linux",
        "cpu_subdir": "x86_64/amd/zen2",
        "slurm_params": "-p rome --nodes 1 --ntasks-per-node 16 --cpus-per-task 1",
        "repo_targets": ["eessi.io-2023.06-compat","eessi.io-2023.06-software"]
    },
    "gpu_h100": {
        "os": "linux",
        "cpu_subdir": "x86_64/amd/zen4",
        "accel": "nvidia/cc90",
        "slurm_params": "-p gpu_h100 --nodes 1 --tasks-per-node 16 --cpus-per-task 1 --gpus-per-node 1",
        "repo_targets": ["eessi.io-2023.06-compat","eessi.io-2023.06-software"]
    }}
```

Each entry in the `node_type_map` dictionary describes a build node type. The key is a (descriptive) name for this build node, and its value is a dictionary containing the following build node properties as key-value pairs:

- `os`: its operating system (os)
- `cpu_subdir`: its CPU architecture
- `slurm_params`: the SLURM parameters that need to be passed to submit jobs to it
- `repo_targets`: supported repository targets for this node type
- `accel` (optional): which accelerators this node has

All values are strings, except repo_targets, which is a list of strings. Repository targets listed in `repo_target` should correspond to the repository IDs as defined in the `repos.cfg` file in the `repos_cfg_dir` (see below).

Note that the Slurm parameters should typically be chosen such that a single type of node (with one specific type of CPU and one specific type of GPU) should be allocated.

To command the bot to build on the `cpu_zen2` node type above, one would give the command `bot:build on:arch=zen2 for:...`. To command the bot to build on the `gpu_h100` node type, one would give the command `bot:build on:arch=zen4,accel=nvidia/cc90 for:...`.

For a native build (i.e. building for `zen2` on a `zen2` node), one can pass `bot:build on:arch=zen2 for:arch=x86_64/amd/zen2`, or use the short-hand `bot:build for:arch=x86_64/amd/zen2` (i.e. omitting the `on` argument implies a native build; note that the reverse, omitting the `for` argument, does not work). This will trigger a build on the `cpu_zen2` node type (as configured above) and prepare a configuration file in the job directory that instructs to build for a `zen2` CPU architecture.

For cross-compiling GPU code for NVIDIA Compute Capabiltiy 8.0 (and a `zen2` CPU architecture), one would instruct the bot with `bot:build on:arch=zen2 for:arch=x86_64/amd/zen2,accel=nvidia/cc80`. This will trigger a build on the `cpu_zen2` node type (as configured above) and prepare a configuration file in the job directory that instructs to build for a `zen2` CPU architecture with an `nvidia/cc80` GPU architecture.

Note that the `arch_target_map` and `repo_target_map` (used in version <=0.8.0) configuration options were replaced by `node_type_map`. The `arch_target_map` and `repo_target_map` that would be equivalent to the `node_type_map` above are:

```ini
arch_target_map = { "linux/x86_64/amd/zen2": "-p rome --nodes 1 --ntasks-per-node 16 --cpus-per-task 1", "linux/x86_64/amd/zen4": "-p gpu_h100 --nodes 1 --tasks-per-node 16 --cpus-per-task 1 --gpus-per-node 1" }
repo_target_map = { "linux/x86_64/amd/zen2": ["eessi.io-2023.06-compat","eessi.io-2023.06-software"], "linux/x86_64/amd/zen4": ["eessi.io-2023.06-compat","eessi.io-2023.06-software"] }
```

#### `[repo_targets]` section

The `[repo_targets]` section defines where the configuration for the repository targets defined in the `node_type_map` can be found.

The repository IDs are defined in a separate file, say `repos.cfg` which is
stored in the directory defined via `repos_cfg_dir`:

```ini
repos_cfg_dir = PATH_TO_SHARED_DIRECTORY/repos
```

The `repos.cfg` file also uses the `ini` format as follows

```ini
[eessi.io-2023.06-software]
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

```ini
log_path = /path/to/eessi_bot_event_handler.log
```

`log_path` specifies the path to the event handler log.

#### `[job_manager]` section

The `[job_manager]` section contains information needed by the job manager.

```ini
log_path = /path/to/eessi_bot_job_manager.log
```

`log_path` specifies the path to the job manager log.

```ini
job_ids_dir = /home/USER/jobs/ids
```

`job_ids_dir` specifies where the job manager should store information about jobs being tracked. Under this directory it will store information about submitted/running jobs under a subdirectory named '`submitted`', and about finished jobs under a subdirectory named '`finished`'.

```ini
poll_command = /usr/bin/squeue
```

`poll_command` is the full path to the Slurm command that can be used for checking which jobs exist. You may want to verify if `squeue` is provided at that path or determine its actual location (via `which squeue`).

```ini
poll_interval = 60
```

`poll_interval` defines how often the job manager checks the status of the jobs. The unit of the value is seconds.

```ini
scontrol_command = /usr/bin/scontrol
```

`scontrol_command` is the full path to the Slurm command used for manipulating existing jobs. You may want to verify if `scontrol` is provided at that path or determine its actual location (via `which scontrol`).
It is also possible to add placeholder values to the scontrol_command. These placeholders can capture output from the `squeue` command that the bot runs internally, and pass it back to the `scontrol_command`. An example where this may be useful is in a setup where multiple clusters are managed by the same SLURM instance, and the `scontrol_command` for that instance needs to get the correct cluster name passed. This can be achieved by defining `scontrol_command = /usr/bin/scontrol --clusters=%%(cluster)s`. Valid placeholder names are currently: `jobid`, `cluster`, `partition`, `state`, and `reason`.

#### `[submitted_job_comments]` section

The `[submitted_job_comments]` section specifies templates for messages about newly submitted jobs.

The following setting is no longer used since bot release v0.7.0. Instead, use the replacement settings `awaits_release_delayed_begin_msg` and/or `awaits_release_hold_release_msg`.

```ini
awaits_release = job id `{job_id}` awaits release by job manager
```

`awaits_release` is used to provide a status update of a job (shown as a row in the job's status
table).

```ini
awaits_release_delayed_begin_msg = job id `{job_id}` will be eligible to start in about {delay_seconds} seconds
```

`awaits_release_delayed_begin_msg` is used when the `job_handover_protocol` is
set to `delayed_begin`. Note, both `{job_id}` and `{delay_seconds}` need to be
present in the value or the event handler will throw an exception when formatting
the update of the PR comment corresponding to the job.

```ini
awaits_release_hold_release_msg = job id `{job_id}` awaits release by job manager
```

`awaits_release_hold_release_msg` is used when the `job_handover_protocol` is
set to `hold_release`. Note, `{job_id}` needs to be present in the value or the
event handler will throw an exception when formatting the update of the PR
comment corresponding to the job.

```ini
new_job_instance_repo = New job on instance `{app_name}` for repository `{repo_id}`
```

`new_job_instance_repo` is used as the first line in a comment to a PR when a new job has been created.

```ini
build_on_arch = Building on: `{on_arch}`{on_accelerator}
```

`build_on_arch` is used as the second line in a comment to a PR when a new job has been created. Note that the `on_accelerator` spec is only filled-in by the bot if the `on:...,accel=...` has been passed to the bot.

```ini
build_for_arch = Building for: `{for_arch}`{for_accelerator}
```

`build_for_arch` is used as the third line in a comment to a PR when a new job has been created. Note that the `for_accelerator` spec is only filled-in by the bot if the `for:...,accel=...` has been passed to the bot.

```ini
jobdir = Job dir: `{symlink}`
```

`jobdir` is used as the fourth line in a comment to a PR when a new job has been created.

```ini
with_accelerator = &nbsp;and accelerator `{accelerator}`
```

`with_accelerator` is used to provide information about the accelerator the job
should build for if and only if the argument `on:...,accel=...` or `for:...,accel=...` has been provided.

#### `[new_job_comments]` section

The `[new_job_comments]` section sets templates for messages about jobs whose `hold` flag was released.

```ini
awaits_launch = job awaits launch by Slurm scheduler
```

`awaits_launch` specifies the status update that is used when the `hold` flag of a job has been removed.

#### `[running_job_comments]` section

The `[running_job_comments]` section sets templates for messages about jobs that are running.

```ini
running_job = job `{job_id}` is running
```

`running_job` specifies the status update for a job that started running.

#### `[finished_job_comments]` section

The `[finished_job_comments]` section sets templates for messages about finished jobs.

```ini
job_result_unknown_fmt = <details><summary>:shrug: UNKNOWN _(click triangle for details)_</summary><ul><li>Job results file `{filename}` does not exist in job directory, or parsing it failed.</li><li>No artefacts were found/reported.</li></ul></details>
```

`job_result_unknown_fmt` is used in case no result file (produced by `bot/check-build.sh`
provided by target repository) was found.

```ini
job_test_unknown_fmt = <details><summary>:shrug: UNKNOWN _(click triangle for details)_</summary><ul><li>Job test file `{filename}` does not exist in job directory, or parsing it failed.</li></ul></details>
```

`job_test_unknown_fmt` is used in case no test file (produced by `bot/check-test.sh`
provided by target repository) was found.

#### `[download_pr_comments]` section

The `[download_pr_comments]` section sets templates for messages related to
downloading the contents of a pull request.

```ini
git_clone_failure = Unable to clone the target repository.
```

`git_clone_failure` is shown when `git clone` failed.

```ini
git_clone_tip = _Tip: This could be a connection failure. Try again and if the issue remains check if the address is correct_.
```

`git_clone_tip` should contain some hint on how to deal with the issue. It is shown when `git clone` failed.

```ini
git_checkout_failure = Unable to checkout to the correct branch.
```

`git_checkout_failure` is shown when `git checkout` failed.

```ini
git_checkout_tip = _Tip: Ensure that the branch name is correct and the target branch is available._
```

`git_checkout_tip` should contain some hint on how to deal with the failure. It
is shown when `git checkout` failed.

```ini
curl_failure = Unable to download the `.diff` file.
```

`curl_failure` is shown when downloading the `PR_NUMBER.diff`

```ini
curl_tip = _Tip: This could be a connection failure. Try again and if the issue remains check if the address is correct_
```

`curl_tip` should help in how to deal with failing downloads of the `.diff` file.

```ini
git_apply_failure = Unable to download or merge changes between the source branch and the destination branch.
```

`git_apply_failure` is shown when applying the `.diff` file with `git apply`
failed.

```ini
git_apply_tip = _Tip: This can usually be resolved by syncing your branch and resolving any merge conflicts._
```

`git_apply_tip` should guide the contributor/maintainer about resolving the cause
of `git apply` failing.

```ini
pr_diff_failure = Unable to obtain PR diff.
```

The value of `pr_diff_failure` is shown when the `.diff` file could not be obtained.

```ini
pr_diff_tip = _Tip: This could be a problem with SSH access to the repository._
```

The value of `pr_diff_tip` should guide the maintainer / bot administrator about resolving the cause for the failing procedure to obtain the `.diff` file.

#### `[clean_up]` section

The `[clean_up]` section includes settings related to cleaning up disk used by merged (and closed) PRs.

```ini
trash_bin_dir = PATH/TO/TRASH_BIN_DIRECTORY
```

Ideally this is on the same filesystem used by `jobs_base_dir` and `job_ids_dir` to efficiently move data
into the trash bin. If it resides on a different filesystem, the data will be copied.

```ini
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

```json
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

```python
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

```json
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

```json
"numa_nodes": [
    "0x001ff",  # a bit mask of 000000000111111111, i.e. cores 0-8 are on this NUMA domain
    "0x3fe00",  # a bit mask of 111111111000000000, i.e. cores 9-17 are on this NUMA domain
]
```

Note that the `topology` dictionary in a ReFrame configuration file can contain more information, such as the bitmasks for the CPU sockets and cores, as well as information on the caches (see [ReFrame docs](https://reframe-hpc.readthedocs.io/en/stable/config_reference.html#config.systems.partitions.processor.topology)). Currently, that information is not needed by the EESSI test suite, but that may change if tests are added that utilize such information to execute efficiently.

For the GPU configuration, we simply put:

```json
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

```python
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

- the Smee client;
- the event handler;
- the job manager.

Running the Smee client was explained in [Step 1](#step1).

## <a name="step7.1"></a>Step 7.1: Running the event handler

As the event handler may run for a long time, it is advised to run it in a `screen` or `tmux` session.

The event handler is provided by the [`eessi_bot_event_handler.py`](https://github.com/EESSI/eessi-bot-software-layer/blob/main/eessi_bot_event_handler.py) Python script.

Change directory to `eessi-bot-software-layer` (which was created by cloning the
repository in [Step 4](#step4) - either the original one from EESSI, or your fork).

Then, simply run the event handler script:

```bash
./event_handler.sh
```

If multiple instances on the `bot machine` are being executed, you may need to run the event handler and the Smee client with a different port (default is 3000). The event handler can receive events on a different port by adding the parameter `--port PORTNUMBER`, for example,

```bash
./event_handler.sh --port 3030
```

See [Step 1](#step1) for telling the Smee client on which port the event handler receives events.

The event handler writes log information to the files `pyghee.log` and
`eessi_bot_event_handler.log`.

Note, if you run the bot on a frontend of a cluster with multiple frontends make sure that both the Smee client and the event handler run on the same system!

## <a name="step7.2"></a>Step 7.2: Running the job manager

As the job manager may run for a long time, it is advised to run it in a `screen` or `tmux` session.

The job manager is provided by the [`eessi_bot_job_manager_layer.py`](https://github.com/EESSI/eessi-bot-software-layer/blob/main/eessi_bot_job_manager.py) Python script. You can run the job manager from the directory `eessi-bot-software-layer` simply by:

```bash
./job_manager.sh
```

It will run in an infinite loop monitoring jobs and acting on their state changes.

If you want to limit the execution of the job manager, you can use thes options:

|Option|Argument|
|------|--------|
|`-i` / `--max-manager-iterations`|Any number _z_: _z_ < 0 - run the main loop indefinitely, _z_ == 0 - don't run the main loop, _z_ > 0 - run the main loop _z_ times|
|`-j` / `--jobs`|Comma-separated list of job ids the job manager shall process. All other jobs will be ignored.|

An example command would be

```bash
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

```bash
# ~/.netrc
machine github.com
login oauth
password <Github token>

machine api.github.com
login oauth
password <Github token>
```

```bash
# ~/.curlrc
--netrc
```
