A bot to help with requests to add software installations to the [EESSI software layer](https://github.com/EESSI/software-layer)

GitHub App implemented in ``eessi_bot_software_layer.py``

Script to start app: ``run.sh``

Requires:

* Python 3
* **PyGitHub**: Python library to use GitHub API v3
  * https://github.com/PyGithub/PyGithub
  * API: https://pygithub.readthedocs.io/en/latest/reference.html
* **Waitress**: production-quality pure-Python WSGI server
  * https://docs.pylonsproject.org/projects/waitress/en/stable/
* **PyGHee**: Python library to facilitate creating a GitHub App implemented in Python
  * https://github.com/boegel/PyGHee

```
pip3 install --user -r requirements.txt
```

# Instructions to set up the EESSI bot components

The following sections describe and illustrate the steps necessary
to set up the EESSI bot for the software layer. The bot consists of
two main components provided in this repository:

- An event handler `eessi_bot_software_layer.py` which receives events from a GitHub repository and acts on them.
- A job manager `eessi_bot_job_manager.py` which monitors a Slurm job queue and acts on state changes of jobs submitted by the event handler.

## <a name="prerequisites"></a>Prerequisites

- GitHub account(s) (two needed for a development scenario), referring to them as `YOU_1` and `YOU_2` below
- A fork, say `YOU_1/software-layer`, of [EESSI/software-layer](https://github.com/EESSI/software-layer) and a fork, say `YOU_2/software-layer` of your first fork if you want to emulate the bot's behaviour but not change EESSI's repository. The EESSI bot will act on events triggered for the first fork (`YOU_1/software-layer`).
- Access to a frontend/login node/service node of a Slurm cluster where the EESSI bot components shall run. For the sake of brevity, we call this node simply `bot machine`.
- `singularity` with version 3.6 or newer on the compute nodes of the Slurm cluster.
- The EESSI bot components and the (build) jobs will frequently access the Internet. Hence, worker nodes and `bot machine` of the Slurm cluster need access to the Internet.

## <a name="step1"></a>Step 1: Smee.io channel and smee client

We use smee.io as a service to relay events from GitHub to the EESSI bot. To do so, create a new channel on the page https://smee.io and note the URL, e.g., https://smee.io/CHANNEL-ID

On the `bot machine` we need a tool which receives events relayed from https://smee.io/CHANNEL-ID and forwards it to the EESSI bot. We use the Smee client for this. The Smee client can be installed globally with

```
npm install -g smee-client
```

or per user

```
npm install smee-client
```

If you don't have `npm` on your system and don't have sudo access to easily install it, you may use a container as follows

```
mkdir smee
cd smee
singularity pull docker://node
singularity exec node_latest.sif npm install smee-client
cat << 'EOF' > smee
#!/usr/bin/env bash

BASEDIR=$(dirname "$0")

singularity exec $BASEDIR/node_latest.sif $BASEDIR/node_modules/smee-client/bin/smee.js "$@"
EOF

chmod 700 smee
export PATH=$PATH:$PWD
```

Finally, run the Smee client as follows

```
smee --url https://smee.io/CHANNEL-ID
```

If the event handler (see [Step 6.1](#step6.1)) receives events on a port different than the default (3000), you need to specify the port via the parameter `--port PORTNUMBER`, for example,

```
smee --url https://smee.io/CHANNEL-ID --port 3030
```

Alternatively, you may use a container providing the smee client. For example,

```
singularity pull docker://deltaprojects/smee-client
singularity run smee-client_latest.sif --url https://smee.io/CHANNEL-ID
```

or

```
singularity pull docker://deltaprojects/smee-client
singularity run smee-client_latest.sif --url https://smee.io/CHANNEL-ID --port 3030
```

for specifying a different port than the default (3000).

## <a name="step2"></a>Step 2: Registering GitHub App

We need to register a GitHub App, link it to the Smee.io channel, set a secret token to verify the webhook sender, set some permissions for the app, subscribe it to selected events and define that this app should only be installed in your account.

At the [app settings page](https://github.com/settings/apps) click "New GitHub App" and fill in the page, particular the following fields
- GitHub App name: give the app a name of you choice
- Homepage URL: use the Smee.io channel (https://smee.io/CHANNEL-ID) created in [Step 1](#step1)
- Webhook URL: use the Smee.io channel (https://smee.io/CHANNEL-ID) created in [Step 1](#step1)
- Webhook secret: create a secret token which is used to verify the webhook sender. For example:
  ```shell
  python3 -c 'import secrets; print(secrets.token_hex(64))'
  ```
- Permissions: assign permissions to the app it needs (e.g., read access to commits, issues, pull requests);
  -  Make sure to assign read and write access to the Pull request in Repository permissions section; These  permisions can be changed later on; 
  -  Make sure to accept the new permissions  from the install app section. Select Install App option from the menu on the left hand side. 
  -  Then select the wheel right next to your installed app or use the link https://github.com/settings/installations/INSTALLATION_ID 
  -  Once the page open you’ll be able to accept the new permissions there. 
  -  Some permissions (e.g., metadata) will be selected automatically because of others you have chosen.

- Events: subscribe the app to events it shall react on (e.g., related to pull requests)
- Select that the app can only be installed by this (your) GitHub account

Click on "Create GitHub App"

## <a name="step3"></a>Step 3: Installing GitHub App

_Note, this will trigger the first event (`installation`). While the EESSI bot is not running yet, you can inspect this via the webpage for your Smee channel. Just open https://smee.io/CHANNEL-ID in a browser and browse through the information included in the event. Naturally, some of the information will be different for other types of events._

You need to install the GitHub App -- essentially telling GitHub to link the app to an account and one, several or all repositories on whose events the app then should act upon.
  
Go to the page https://github.com/settings/apps and select the app you want to install by clicking on the icon left to the app's name or on the "Edit" button right to the name of the app. On the next page you should see the menu item "Install App" on the left-hand side. When you click on this you should see a page with a list of accounts you can install the app on. Choose one and click on the "Install" button next to it. This leads to a page where you can select the repositories on whose the app should react to. Here, for the sake of simplicity, choose just `YOU_1/software-layer` as described in [Prerequisites](#prerequisites). Select one, multiple or all and click on the "Install" button.

## <a name="step4"></a>Step 4: Installing the EESSI bot on a `bot machine`

The EESSI bot for the software layer is available from [EESSI/eessi-bot-software-layer](https://github.com/EESSI/eessi-bot-software-layer). This repository (or your fork of it) provides scripts and an example configuration file.

Get the EESSI bot _installed_ onto the `bot machine` by running something like

```
git clone https://github.com/EESSI/eessi-bot-software-layer.git
```
Determine full path to bot directory
```
cd eessi-bot-software-layer
pwd
```
Note the output of `pwd`. This will be used to replace `PATH_TO_EESSI_BOT` in the configuration file `app.cfg` (see [Step 5.4](#step5.4)).

If you want to develop the EESSI bot, it is recommended that you fork the repository and use the fork on the `bot machine`.

If you want to work with a specific pull request, say number 24, you obtain its contents with the following commands:
```
git clone https://github.com/EESSI/eessi-bot-software-layer.git
cd eessi-bot-software-layer
pwd
git fetch origin pull/24/head:PR24
git checkout PR24
```

The EESSI bot requires some Python packages to be installed. It is recommended to install these in a virtual environment based on Python 3.7 or newer. See the below sequence for an example on how to set up the environment, to activate it and to install the requirements for the EESSI bot. The sequence assumes that you are in the directory containing the bot's script:
```
cd ..
python3.7 -m venv venv_bot_p37
source venv_bot_p37/bin/activate
python --version                     # output should match 'Python 3.7.*$'
which python                         # output should match '*/venv_bot_p37/bin/python$'
python -m pip install --upgrade pip
cd eessi-bot-software-layer
pip install -r requirements.txt
```

Note, before you can start the bot components (see below), you have to activate the virtual environment with `source venv_bot_p37/bin/activate`. You can deactivate it simply by running `deactivate`.

**Troubles installing some of the requirements or their dependencies?**
You may try to upgrade `pip` first with
```
python3 -m pip install --user --upgrade pip
```
Then try to install the requirements with
```
pip3 install --user -r requirements.txt
```

Alternatively, you may try to install some of the dependencies by fixing their version. For example, on the [EESSI CitC cluster](https://github.com/EESSI/hackathons/tree/main/2021-12/citc) installing PyGithub failed due to some problem installing its dependency PyNaCl. Apparently, PyGithub only required version 1.4.0 of PyNaCl but the most recent version 1.5.0 failed to install. Hence, when installing PyNaCl version 1.4.0 first, then PyGithub could be installed. Example commands

```
pip3 install --user PyNaCl==1.4.0
pip3 install --user -r requirements.txt
```

### <a name="step4.1"></a>Step 4.1 Using a development version/branch of PyGHee

The above command `pip3 install --user -r requirements.txt` installs the latest release of the PyGHee library. If you want to use a development version/branch, i.e., what is available from GitHub or your own local copy, you have to set `$PYTHONPATH` correctly. Assuming the library's main directory is `SOME_PATH/PyGHee` do the following in the terminal/shell/script where you run the bot:
  
```
export PYTHONPATH=SOME_PATH/PyGHee:$PYTHONPATH
```

## <a name="step5"></a>Step 5: Configuring the EESSI bot on the `bot machine`

For the event handler, you need to set up two environment variables: `GITHUB_TOKEN` ([Step 5.1](#step5.1)) and `GITHUB_APP_SECRET_TOKEN` ([Step 5.2](#step5.2)). For both the event handler and the job manager you need a private key ([Step 5.3](#step5.3)).

### <a name="step5.1"></a>Step 5.1: GitHub Personal Access Token (PAT)
Create a Personal Access Token (PAT) for your GitHub account via the page https://github.com/settings/tokens where you find a button "Generate new token".
Give it meaningful name (field titled "Note") and set the expiration date. Then select the scopes this PAT will be used for. Then click "Generate token". On the result page, take note/copy the resulting token string -- it will only be shown once.

On the `bot machine` set the environment variable `GITHUB_TOKEN`, e.g.
```
export GITHUB_TOKEN='THE_TOKEN_STRING'
```

### <a name="step5.2"></a>Step 5.2: GitHub App Secret Token
The GitHub App Secret Token is used to verify the webhook sender. You should have created one already when registering a new GitHub App in [Step 2](#step2).

On the `bot machine` set the environment variable `GITHUB_APP_SECTRET_TOKEN`, e.g.
```
export GITHUB_APP_SECRET_TOKEN='THE_SECRET_TOKEN_STRING'
```
Note, depending on the characters used in the string you will likely have to use single quotes when setting the value of the environment variable.

### <a name="step5.3"></a>Step 5.3: Create a private key and store it on the `bot machine`
The private key is needed to let the app authenticate when updating information at the repository such as commenting on PRs, adding labels, etc. You can create the key at the page of the GitHub App you have registered in [Step 2](#step2).

Open the page https://github.com/settings/apps and then click on the icon left to the name of the GitHub App for the EESSI bot or the "Edit" button for the app. Near the end of the page you will find a section "Private keys" where you can create a private key by clicking on the button "Generate a private key". The private key should be automatically downloaded to your local computer. Copy it to the `bot machine` and note the full path to it (`PATH_TO_PRIVATE_KEY`).

For example: the private key is in the LOCAL computer. To copy it to the bot machine 
```
scp PATH_TO_PRIVATE_KEY_FILE_LOCAL_COMPUTER REMOTE_USERNAME@TARGET_HOST:TARGET/PATH
```
the `TARGET/PATH` of the bot machine should be noted for PATH_TO_PRIVATE_KEY.

### <a name="step5.4"></a>Step 5.4: Create the configuration file `app.cfg`

If there is no `app.cfg` in the directory `PATH_TO_EESSI_BOT` yet, create an initial version from `app.cfg.example`.

```
cp -i app.cfg.example app.cfg
```

The example file (`app.cfg.example`) includes notes on what you have to adjust to run the bot in your environment.

### Section `[github]`
The section `[github]` contains information for connecting to GitHub:
```
app_id = 123456
```
Replace '123456' with the id of your GitHub App. You find the id of your GitHub App via the page [GitHub Apps](https://github.com/settings/apps). On this page, select the app you have registered in [Step 2](#step2). On the opened page you will find the `app_id` in the section headed "About" listed as 'App ID'.
```
app_name = 'MY-bot'
```
Is a short name representing your bot. It will appear in comments to a pull request. For example, it could include the name of the cluster where the bot runs and a label representing the user that runs the bot: `CitC-TR`. *NOTE avoid putting an actual username here as it will be visible on potentially publicly accessible GitHub pages.*
```
installation_id = 12345678
```
Replace '12345678' with the id of the installation of your GitHub App (installed in [Step 3](#step3)). You find the id of your GitHub App via the page [GitHub Apps](https://github.com/settings/apps). On this page, select the app you have registered in [Step 2](#step2). For determining the `installation_id` select "Install App" in the menu on the left-hand side. Then click on the gearwheel button of the installation (to the right of the "Installed" label). The URL of the resulting page contains the `installation_id` -- the number after the last "/". The `installation_id` is also provided in the payload of every event within the top-level record named "installation". You can see the events and their payload on the webpage of your Smee.io channel (https://smee.io/CHANNEL-ID). Alternatively, you can see the events in the "Advanced" section of your GitHub App: Open the page [GitHub Apps](https://github.com/settings/apps), then select the app you have registered in [Step 2](#step2), and choose "Advanced" in the menu on the left-hand side.
```
private_key = PATH_TO_PRIVATE_KEY
```
Replace `PATH_TO_PRIVATE_KEY` with the path you have noted in [Step 5.3](#step5.3).

### Section `[buildenv]`
The section `[buildenv]` contains information about the build environment.
```
build_job_script = PATH_TO_EESSI_BOT/scripts/eessi-bot-build.slurm
```
This points to the job script which will be submitted by the event handler.
The CVMFS configuration could be commented out unless there’s a need to customize the CVMFS configuration.
```
cvmfs_customizations = { "/etc/cvmfs/default.local": "CVMFS_HTTP_PROXY=\"http://PROXY_DNS_NAME:3128|http://PROXY_IP_ADDRESS:3128\"" }
```
It may happen that we need to customize the CVMFS configuration for the build
job. The value of cvmfs_customizations is a dictionary which maps a file name
to an entry that needs to be appended to that file. In the example line above, the
configuration of `CVMFS_HTTP_PROXY` is appended to the file `/etc/cvmfs/default.local`.
```
http_proxy = http://PROXY_DNS:3128/
https_proxy = http://PROXY_DNS:3128/
```
If compute nodes have no internet connection, we need to set `http(s)_proxy`
or commands such as `pip3` and `eb` (EasyBuild) cannot download software from
package repositories. Typically these settings are set in the prologue of a
Slurm job. However, when entering the Gentoo Prefix, most environment settings
are cleared. Hence, they need to be set again at a late stage (done in the
script `EESSI-pilot-install-software.sh`).
```
jobs_base_dir = $HOME/jobs
```
Replace `$HOME/jobs` with absolute filepath `/home/USER/jobs`. Per job the directory structure under `jobs_base_dir` is `YYYY.MM/pr_PR_NUMBER/event_EVENT_ID/run_RUN_NUMBER/OS+SUBDIR`. The base directory will contain symlinks using the job ids pointing to the job's working directory `YYYY.MM/...`.
```
load_modules = MODULE1/VERSION1,MODULE2/VERSION2,...
```
This setting provides a means to load modules in the `build_job_script`.
None to several modules can be provided in a comma-separated list. It is
read by the bot and handed over to `build_job_script` via the parameter
`--load-modules`.
```
local_tmp = /tmp/$USER/EESSI
```
This is the path to a temporary directory on the node building the stack, i.e., on a compute/worker node. You may have to change this if temporary storage under '/tmp' does not exist or is too small. This setting will be used for the environment variable `EESSI_TMPDIR`. Variables in the value may be esaped with '\' to delay their expansion to the start of the build_job_script. This can be used for referencing environment variables that are only set inside a Slurm job.
```
slurm_params = "--hold"
```
This defines additional parameters for submitting batch jobs. "--hold" should be kept or the bot might not work as intended (the release step would be circumvented). Additional parameters, for example, to specify an account, a partition or any other parameters supported by `sbatch`, may be added to customize the submission to your environment.
```
submit_command = /usr/bin/sbatch
```
This is the full path to the Slurm command used for submitting batch jobs. You may want to verify if `sbatch` is provided at that path or determine its actual location (`which sbatch`).

### Section `[architecturetargets]`
The section `[architecturetargets]` defines for which targets (OS/SUBDIR), e.g., `linux/amd/zen2` the EESSI bot should submit jobs and what additional `sbatch` parameters will be used for requesting a compute node with the CPU microarchitecture needed to build the software stack.
```
arch_target_map = { "linux/x86_64/generic" : "--constraint shape=c4.2xlarge", "linux/x86_64/amd/zen2" : "--constraint shape=c5a.2xlarge" }
```
The map has one to many entries of the format `OS/SUBDIR : ADDITIONAL_SBATCH_PARAMETERS`. For your cluster, you will have to figure out which microarchitectures (`SUBDIR`) are available (as `OS` only `linux` is currently supported) and how to instruct Slurm to request them (`ADDITIONAL_SBATCH_PARAMETERS`).

Note, if you do not have to specify additional parameters to `sbatch` to request a compute node with a specific microarchitecture, you can just write something like
```
arch_target_map = { "linux/x86_64/generic" : "" }
```

### Section `[job_manager]`
The section `[job_manager]` contains information needed by the job manager.
```
job_ids_dir = /home/USER/jobs/ids
```
Path to where the job manager stores information about jobs to be tracked. Under this directory it will store information about submitted/running jobs under `submitted` and about finished jobs under `finished`.
```
poll_command = /usr/bin/squeue
```
This is the full path to the Slurm command used for checking which jobs exist. You may want to verify if `squeue` is provided at that path or determine its actual location (`which squeue`).
```
poll_interval = 60
```
This defines how often the job manager checks the status of the jobs. The unit of the value is seconds.
```
scontrol_command = /usr/bin/scontrol
```
This is the full path to the Slurm command used for manipulating existing jobs. You may want to verify if `scontrol` is provided at that path or determine its actual location (`which scontrol`).

# Instructions to run the bot components

The bot consists of three components, the Smee client, the event handler and the job manager. Running the Smee client was explained in [Step 1](#step1).

## <a name="step6.1"></a>Step 6.1: Running the event handler
As the event handler may run for a long time, it is advised to run it in a `screen` or `tmux` session.

The event handler is provided by the Python script `eessi_bot_software_layer.py`.
Change directory to `eessi-bot-software-layer` (which was created by cloning the
repository in [Step 4](#step4) - either the original one from EESSI or your fork).
Then, simply run the event handler by executing
```
./run.sh
```
If multiple instances on the `bot machine` are being executed, you may need to run the event handler and the Smee client with a different port (default is 3000). The event handler can receive events on a different port by adding the parameter `--port PORTNUMBER`, for example,
```
./run.sh --port 3030
```
See [Step 1](#step1) for telling the Smee client on which port the event handler receives events.

The event handler writes log information to the file `pyghee.log`.

Note, if you run the bot on a frontend of a cluster with multiple frontends make sure that both the Smee client and the event handler run on the same machine.

## <a name="step6.2"></a>Step 6.2: Running the job manager
As the job manager may run for a long time, it is advised to run it in a `screen` or `tmux` session.

The job manager is provided by the Python script `eessi_bot_job_manager_layer.py`. You can run the job manager from the directory `eessi-bot-software-layer` simply by

```
./job_manager.sh
```

It will run in an infinite loop monitoring jobs and acting on their state changes.

If you want to control how the job manager works, you can add two parameters:
|Option|Argument|
|------|--------|
|`-i` / `--max-manager-iterations`|Any number _z_: _z_ < 0 - run the main loop indefinitely, _z_ == 0 - don't run the main loop, _z_ > 0 - run the main loop _z_ times|
|`-j` / `--jobs`|Comma-separated list of job ids the job manager shall process. All other jobs will be ignored.|

An example command would be

```
./job_manager.sh -i 1 -j 2222
```
to run the main loop exactly once for job `2222`.

The job manager writes log information to the file `eessi_bot_job_manager.log`.

The job manager can run on a different machine than the event handler as long as both have access to the same shared filesystem.

# Example pull request on software-layer

Now that the bot is running on your cluster, we want to provide a little demo about how to use it to add a new package to the software layer. We assume that you have forked [EESSI/software-layer](https://github.com/EESSI/software-layer) to `YOUR_GITHUB_ACCOUNT/software-layer` Following methods can be used to test the bot.
Method 1:
   - open the link https://github.com/YOUR_GITHUB_ACCOUNT/software-layer/compare/main...EESSI:software-layer:add-CaDiCaL-9.3.0?expand=1
   - create the label bot:build if it's not there.
   - Create the pull request.
   - Don’t merge the Pull request. It is important to close the pull request or delete the bot:build label after testing it. It can be added again for the other test. 
If the above method is followed then there will be no need to create another Github account for the test which is shown in the following Method 2.

Method 2:
Forked `YOU_1/software-layer` to `YOU_2/software-layer`.

Clone into the second fork and create a new branch:

```
git clone https://github.com/YOU_2/software-layer
cd software-layer
git branch add-CaDiCaL-9.3.0
git checkout add-CaDiCaL-9.3.0
```

Open `EESSI-pilot-install-software.sh` and add the section

```
export CaDiCaL_EC="CaDiCaL-1.3.0-GCC-9.3.0.eb"
echo ">> Installing ${CaDiCaL_EC}..."
ok_msg="${CaDiCaL_EC} installed, let's solve some problems!"
fail_msg="Installation of ${CaDiCaL_EC} failed, that's a pity..."
$EB ${CaDiCaL_EC} --robot
check_exit_code $? "${ok_msg}" "${fail_msg}"
```

just before the line
```
echo ">> Creating/updating Lmod cache..."
```

Open `eessi-2021.12.yml` and append the section

```
  CaDiCaL:
     toolchains:
       GCC-9.3.0:
         versions: ['1.3.0']
```

Commit the changes and push them to `YOU_1/software-layer`. Create the pull request by opening the link shown by `git push`. Make sure that you request to merge into `YOU_1/software-layer` - your bot receives events for this repository only (and while you experiment you may not wish to create too much noise on EESSI's software-layer repository).

At first, the page for the pull request will look like normal pull request. The event handler will already have received an event, but it will wait until the label `bot:build` is set for the pull request.

Add the label `bot:build`. Now, the event handler will submit jobs - one for each target architecture. For each submitted job it will add a comment such as

IMAGE-SCREENSHOT

The jobs are submitted with the parameter `--hold`. They will not start immediately, but rather are required to be released explicitly by the job manager. This can be very useful to control the processing of jobs, for example, when developing the EESSI bot components. If you want to control the execution, the job manager shall not run in an endless loop.

Next the job manager notes the submitted job(s), releases them and updates the comments corresponding to the released jobs. An example update could look like this

IMAGE-SCREENSHOT

When the job has finished, the job manager analyses the result of job (checking if no missing modules were found and if a tarball was generated) and updates the job's comment in the PR. An example update could look like (in case of success)

IMAGE-SCREENSHOT

or in case of failure

IMAGE-SCREENSHOT

