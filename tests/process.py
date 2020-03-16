import subprocess
from pathlib import Path
from typing import List, Callable
import inspect
import socket
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

BLENDER_DIR = Path(r'D:\blenders\blender-2.82-windows64')
# BLENDER_DIR = Path(r'D:\blenders\2.82')
current_dir = Path(__file__).parent


class Process:
    def __init__(self):
        self._process = None

    def stop(self):
        if self._process is not None:
            subprocess.Popen.kill(self._process)
            self._process = None


class DccsyncServer(Process):
    def __init__(self):
        super().__init__()
        self._exe = str(BLENDER_DIR / r'2.82\python\bin\python.exe')

    def start(self):
        dir_path = Path(__file__).parent.parent.parent
        serverPath = dir_path / 'broadcaster' / 'dccBroadcaster.py'
        popen_args = {'creationflags': subprocess.CREATE_NEW_CONSOLE}
        # https://blender.stackexchange.com/questions/1365/how-can-i-run-blender-from-command-line-or-a-python-script-without-opening-a-gui
        self._process = subprocess.Popen([self._exe, str(serverPath)], shell=False, **popen_args)
        return self


class Blender(Process):
    """
    Start a Blender process
    """

    def __init__(self):
        super().__init__()
        self._exe = str(BLENDER_DIR / 'blender.exe')
        self._cmd_args = [
            '--python-exit-code', '255',
            '--log-level', '-1',
            '--start-console'
        ]

    def start(self, python_script_path: str = None, script_args: List = None, blender_args: List = None):
        popen_args = [self._exe]
        popen_args.extend(self._cmd_args)
        if blender_args is not None:
            popen_args.extend(blender_args)
        if python_script_path is not None:
            popen_args.extend(['--python', str(python_script_path)])
        if script_args is not None:
            popen_args.append('--')
            script_args = script_args if isinstance(script_args, list) else [script_args]
            popen_args.extend([str(arg) for arg in script_args])

            display_args = ''

        for arg in popen_args:
            display_args += arg + ' '
        print(display_args)

        other_args = {'creationflags': subprocess.CREATE_NEW_CONSOLE}
        self._process = subprocess.Popen(popen_args, shell=False, **other_args)

    def wait(self):
        self._process.wait()


class BlenderServer(Blender):
    """
    Starts a Blender process that runs a python server. The Blender can be controlled
    by sending python source code.
    """

    def __init__(self, port: int):
        super().__init__()
        self._port = port
        self._path = str(current_dir / 'python_server.py')
        self._sock: socket.socket = None

    def start(self, blender_args: List = None):
        arg = f'--port={self._port}'
        super().start(self._path, arg, blender_args)

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connected = False
        max_attempts = 20
        attempts = 0
        while not connected and attempts < max_attempts:
            try:
                self._sock.connect(('127.0.0.1', self._port))
                connected = True
            except ConnectionRefusedError:
                time.sleep(1)
                attempts += 1

    def send_string(self, script: str):
        self._sock.send(script.encode('utf-8'))

    def send_function(self, f: Callable, *args, **kwargs):
        """
        Remotely execute a function.

        Extracts the source code from the function f. 
        The def statement must not be indented (no local function)
        """
        src = inspect.getsource(f)
        kwargs_ = [f'{key}={repr(value)}' for key, value in kwargs.items()]
        args_ = [f'{repr(arg)}' for arg in args]
        args_.extend(kwargs_)
        arg_string = '' if args_ is None else ','.join(args_)
        source = f'{src}\n{f.__name__}({arg_string})\n'
        print(source)
        self.send_string(source)
