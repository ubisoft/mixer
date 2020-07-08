# Developer environment

## Python Virtual Environment

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

## Visual Studio Code

We recommand Visual Studio Code, with Python and Blender VSCode extensions.

If you have a python file open in VSCode, it should automatically detect the virtual env, activate it when prompted. Note that VSCode never detect your python unless you open a Python file. When your python is detected, you should see it in your status bar and any new terminal open should have the virtual env activated ("(.venv)" should appear on the prompt line).

The file `.vscode/settings.shared.json` gives an exemple of settings to fill your own `.vscode/settings.json`. The important parts are `editor`, `python` and `blender` settings.

Similarly you can copy `.vscode/launch.shared.json` and `.vscode/tasks.shared.json` for exemples of debug configurations and tasks to run from VSCode.

## VSCode "configuration"

To prevent VSCode from breaking on generator related exceptions, modify your local installation of `pydevd_frame.py` like stated in https://github.com/fabioz/ptvsd/commit/b297bc027f504cf8679090079aebff6028dfec02.

## Running code quality tools manually

With the above setup, all the code you type should be formatted on save and you should have flake8 warning messages.

If you want to format manually the codebase, run `black .` in the terminal.

If you want to check flake warnings, run `flake8` in the terminal. Note that the flake8 plugins `flake8-black` and `pep8-naming` are installed in the virtual env so you will be notified if black would reformat a file and if you violate PEP8 naming conventions.

You need to have the virtual env activated for these commands to work.

## CI/CD

The CI/CD script `.gitlab-ci.yml` has a codequality stage that run flake8 on the codebase. Go to the pipeline pages of the project to check if your commits meet the quality check.
