# Mixer

**Disclaimer**: This project is in alpha state and actively developped. Do not use it to edit your production assets without a backup or you might break them. In the code you might see references to VRtist or Shot Manager, which are other technologies/addons that are developped in our studio. Don't pay too much attention to related code since we plan to extract it in some kind of plugin mechanism.

## Introduction

Mixer is a Blender addon developped at Ubisoft Animation Studio for Real Time Collaboration in 3D edition. It allows multiple Blender users to work on the same scene at the same time. Thanks to a broadcasting server that is independent from Blender, it is also possible to implement a connection for other 3D editing softwares.

## Usage

You can download the addon from the release page and install it into Blender.

We didn't write extensive documentation for the user interface because it is still a work in progress and might be changed often. If will be done when the addon become more stable.

From the Mixer panel in the 3D viewport you can enter an IP address, a port and connect to a server. If you enter `localhost` and no Mixer server is already running on your computer, then the addon will start one in the background when you click `Connect`.

Then you can test locally between two Blender instances, or you can open the port on your router and give you external IP address to someone so he can join your session.

If you are on the Ubisoft network you don't need any router configuration but beware that the VPN apply some rules and you might not be able to reach the IP of someone else behind the VPN. A configuration that should work is to start the server on a workstation from a Ubisoft site, and to have all participants connect to it.

A Mixer broadcaster hosts rooms that are created by users. By default there is no room and someone needs to create one. The creator of the room will upload its current scene to the server, and this scene will be transfered to people that connect to the room. When all users leave a room its content is destroyed, so someone needs to save the scene before everyone leave if you want to keep it.

## Developer environment

### Python Virtual Environment

After cloning the repository, create a Virtual Environment in the code directory:

```bash
python -m venv .venv
```

Use python 3.7 to match Blender's python version.

Activate the virtual env, on Windows the commands are:

With Git bash:

```bash
source .venv/Scripts/activate
```

With cmd.exe:

```bash
.venv\Scripts\activate.bat
```

Then install development packages with pip:

```bash
pip install -r requirements-dev.txt
```

### Visual Studio Code

We recommand Visual Studio Code, with Python and Blender VSCode extensions.

If you have a python file open in VSCode, it should automatically detect the virtual env, activate it when prompted. Note that VSCode never detect your python unless you open a Python file. When your python is detected, you should see it in your status bar and any new terminal open should have the virtual env activated ("(.venv)" should appear on the prompt line).

The file `.vscode/settings.shared.json` gives an exemple of settings to fill your own `.vscode/settings.json`. The important parts are `editor`, `python` and `blender` settings.

Similarly you can copy `.vscode/launch.shared.json` and `.vscode/tasks.shared.json` for exemples of debug configurations and tasks to run from VSCode.

#### VSCode "configuration"

To prevent VSCode from breaking on generator related exceptions, modify your local installation of `pydevd_frame.py` like stated in https://github.com/fabioz/ptvsd/commit/b297bc027f504cf8679090079aebff6028dfec02.

### Running code quality tools manually

With the above setup, all the code you type should be formatted on save and you should have flake8 warning messages.

If you want to format manually the codebase, run `black .` in the terminal.

If you want to check flake warnings, run `flake8` in the terminal. Note that the flake8 plugins `flake8-black` and `pep8-naming` are installed in the virtual env so you will be notified if black would reformat a file and if you violate PEP8 naming conventions.

You need to have the virtual env activated for these commands to work.

### CI/CD

The CI/CD script `.gitlab-ci.yml` has a codequality stage that run flake8 on the codebase. Go to the pipeline pages of the project to check if your commits meet the quality check.

## Unit tests

### CI/CD on unit tests

For a first simple setup, we rely on an interactive gitlab runner setup. Issues related to service-based runners are described below.

The scripts are located in a new `gitlab` folder.

#### Skipping automatic tests

You can skip tests by including the string `[skip-tests]` in the commit message.

#### Interactive runner

Documentation:

- Installation : https://docs.gitlab.com/runner/install/windows.html
- Runner commands : https://docs.gitlab.com/runner/commands/

Installation steps:

1. Install a gitlab runner in a folder of your choice. For this tutorial we'll use `d:\gitlab_runner`.
2. Run a terminal as administrator, create folder `d:\gitlab_runner\working_dir` and place yourself into it in your terminal
3. Register a runner with `gitlab-runner-windows-amd64.exe register`. Use `https://gitlab-ncsa.ubisoft.org/` as URL, `3doSyUPxsy5hL-svi_Qu` as token, `blender` as tags, `shell` as executor. The token can be found in Settings -> CI/CD page of this repository. This step should create a file `config.toml` in `d:\gitlab_runner\working_dir`.
4. Edit `d:\gitlab_runner\working_dir` and add an entry `cache_dir = "D:/gitlab_runner/cache"` in the `[[runners]]` section, after the `shell` entry.

Then run an interactive : `gitlab-runner-windows-amd64.exe run`. It must run as administrator because the `TSCON` command requires administrator rights to disconnect a session from the remote desktop.

As the runner executes jobs, it will display the jobs status :

```
D:\gitlab_runner>gitlab-runner-windows-amd64.exe run
Runtime platform                                    arch=amd64 os=windows pid=19628 revision=4c96e5ad version=12.9.0
Starting multi-runner from D:\gitlab_runner\config.toml...  builds=0
Configuration loaded                                builds=0
listen_address not defined, metrics & debug endpoints disabled  builds=0
[session_server].listen_address not defined, session endpoints disabled  builds=0
Checking for jobs... received                       job=11132741 repo_url=https://gitlab-ncsa.ubisoft.org/animation-studio/blender/mixer.git runner=Q-sQ1rhN
Job succeeded                                       duration=5m3.2796891s job=11132741 project=39094 runner=Q-sQ1rhN
Checking for jobs... received                       job=11132866 repo_url=https://gitlab-ncsa.ubisoft.org/animation-studio/blender/mixer.git runner=Q-sQ1rhN
WARNING: Job failed: exit status 1                  duration=5m8.5314355s job=11132866 project=39094 runner=Q-sQ1rhN
WARNING: Failed to process runner                   builds=0 error=exit status 1 executor=shell runner=Q-sQ1rhN
```

The builds for the runner will be put in the current working directory `d:\gitlab_runner\working_dir` where you started the runner.

#### Runner as a Windows service

Using a system service could be difficult because the user profile may not be easy to access and we also need the service to access to the desktop.

Using a service that logons with a user account requires a user account that can logon as a service as described in https://docs.gitlab.com/runner/faq/README.html#the-service-did-not-start-due-to-a-logon-failure-error-when-starting-service.

## How to release a new version ?

The release process of Mixer is handled with CI/CD and based on git tags. Each tag with a name `v{major}.{minor}.{bugfix}` is considered to be a release tag and should trigger the release job of the CI/CD.

You should not add such tag manually, instead run the script:

```bash
python -m extra.prepare_release <major> <minor> <bugfix>
```

For it to succeed:

- You should have commited all your changes
- You should have added a section describing the release and starting with `# <major>.<minor>.<bugfix>` in `CHANGELOG.md`
- The tag `v{major}.{minor}.{bugfix}` should not already exists

If all these requirements are met, then the script will inject the new version number in the addon `bl_info` dictionnary and tag the commit.

You can then push the tag:

```bash
git push # Push the branch
git push --tags # Push the tag
```

Then watch your pipeline on Gitlab and wait for the release notes to appear on the release page.

### What if I did a mistake ?

It may happen. In that case just go to gitlab and remove the tag. It will also remove the release.

In your local repository manually delete the tag.
