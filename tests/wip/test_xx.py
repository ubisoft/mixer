import subprocess
from pathlib import Path
import time

"""
The idea is to automate Blender / Blender tests

Sender Blender executes the test script
- join a room
- load a file
- perform changes (core of the tests)
- save the file
- do not leave the room

Receiver Blender
- join the room after Sender
- "wait" for the changes
- save the file

Diff the scenes
"""


class Process:
    def __init__(self):
        self._process = None

    def stop(self):
        if self._process is not None:
            subprocess.Popen.kill(self._process)
            self._process = None


class Server(Process):
    def __init__(self):
        super().__init__()
        self._exe = r'D:\blenders\blender-2.82-windows64\2.82\python\bin\python.exe'

    def start(self):
        dir_path = Path(__file__).parent.parent
        serverPath = dir_path / 'broadcaster' / 'dccBroadcaster.py'
        popen_args = {'creationflags': subprocess.CREATE_NEW_CONSOLE}
        # https://blender.stackexchange.com/questions/1365/how-can-i-run-blender-from-command-line-or-a-python-script-without-opening-a-gui
        self._process = subprocess.Popen([self._exe, str(serverPath)], shell=False, **popen_args)
        return self


class Blender(Process):
    def __init__(self):
        super().__init__()
        self._exe = r'D:\blenders\blender-2.82-windows64\blender.exe'
        self._cmd_args = [
            '--python-exit-code 255',
        ]

    def start(self, python_script_path: None):
        args = [self._exe]
        if python_script_path is not None:
            args.extend(['--python', str(python_script_path)])
            args.extend(self._cmd_args)

        popen_args = {'creationflags': subprocess.CREATE_NEW_CONSOLE}
        self._process = subprocess.Popen(args, shell=False, **popen_args)
        return self


current_dir = Path(__file__).parent
s = Server().start()
time.sleep(2)
b1 = Blender().start(current_dir / 'file1.py')

# TOTRY send code snippets to blender throuigh a pipe or shared fd
# https://docs.python.org/3/library/asyncio-subprocess.html#asyncio-subprocess


b2 = Blender().start(current_dir / 'file2.py')
time.sleep(1000)
