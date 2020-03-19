import subprocess
from pathlib import Path
from typing import List, Callable
import inspect
import socket
import time
import blender_lib
import os
import logging

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

BLENDER_EXE = os.environ.get('DCCSYNC_BLENDER_EXE_PATH', 'blender.exe')
current_dir = Path(__file__).parent


class Process:
    def __init__(self):
        self._process = None

    def stop(self):
        if self._process is not None:
            subprocess.Popen.kill(self._process)
            self._process = None


class Blender(Process):
    """
    Start a Blender process
    """

    def __init__(self):
        super().__init__()
        self._cmd_args = [
            '--python-exit-code', '255',
            '--log-level', '-1',
            '--start-console'
        ]
        self._process: subprocess.Popen = None

    def start(self, python_script_path: str = None, script_args: List = None, blender_args: List = None):
        popen_args = [BLENDER_EXE]
        popen_args.extend(self._cmd_args)
        if blender_args is not None:
            popen_args.extend(blender_args)
        if python_script_path is not None:
            popen_args.extend(['--python', str(python_script_path)])
        if script_args is not None:
            popen_args.append('--')
            popen_args.extend([str(arg) for arg in script_args])

        print(' ' + ' '.join(popen_args))

        other_args = {'creationflags': subprocess.CREATE_NEW_CONSOLE}
        try:
            self._process = subprocess.Popen(popen_args, shell=False, **other_args)
        except FileNotFoundError:
            logging.error(
                f'Cannot start "{BLENDER_EXE}". Define DCCSYNC_BLENDER_EXE_PATH environment variable or add to PATH')

    def wait(self, timeout: float = None):
        try:
            return self._process.wait(timeout)
        except subprocess.TimeoutExpired:
            return None

    def kill(self):
        self._process.kill()


class BlenderServer(Blender):
    """
    Starts a Blender process that runs a python server. The Blender can be controlled
    by sending python source code.
    """

    def __init__(self, port: int, ptvsd_port: int = None, wait_for_debugger=False):
        super().__init__()
        self._port = port
        self._ptvsd_port = ptvsd_port
        self._wait_for_debugger = wait_for_debugger
        self._path = str(current_dir / 'python_server.py')
        self._sock: socket.socket = None

    def start(self, blender_args: List = None):
        args = [f'--port={self._port}']
        if self._ptvsd_port is not None:
            args.append(f'--ptvsd={self._ptvsd_port}')
        if self._wait_for_debugger:
            args.append('--wait_for_debugger')
        super().start(self._path, args, blender_args)

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connected = False
        max_attempts = 200
        attempts = 0
        while not connected and attempts < max_attempts:
            try:
                self._sock.connect(('127.0.0.1', self._port))
                connected = True
            except ConnectionRefusedError:
                time.sleep(0.1)
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
        self.send_string(source)

    def quit(self):
        self.send_function(blender_lib.quit)
