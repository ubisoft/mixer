import inspect
import logging
import os
from pathlib import Path
import socket
import subprocess
import time
from typing import Any, Callable, Iterable, List, Mapping, Optional

import tests.blender_lib as blender_lib

from mixer.broadcaster.common import DEFAULT_PORT

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

logger = logging.getLogger(__name__)

BLENDER_EXE = os.environ.get("MIXER_BLENDER_EXE_PATH", "blender.exe")
current_dir = Path(__file__).parent


class Process:
    """
    Simple wrapper around subprocess.Popen
    """

    def __init__(self):
        self._process: subprocess.Popen = None

    def start(self, args, kwargs):
        logger.info(f"Running subprocess.Popen()")
        logger.info(f"args:   {args}")
        logger.info(f"kwargs: {kwargs}")
        command_line = " ".join(args)
        logger.info(f"command line: {command_line}")
        try:
            self._process = subprocess.Popen(args, **kwargs)
            logger.info(f"subprocess.popen: success")
        except Exception as e:
            logger.error(f"Python.start(): Exception raised during subprocess.Popen(): ")
            logger.error(f"{e}")
            logger.error(f"args:   {args}")
            logger.error(f"kwargs: {kwargs}")
            logger.error(f"command line: {command_line}")

    def wait(self, timeout: float = None):
        try:
            return self._process.wait(timeout)
        except subprocess.TimeoutExpired:
            return None

    def kill(self, timeout: float = None):
        if self._process is None:
            return
        self._process.kill()
        self.wait(timeout)
        self._process = None


class BlenderProcess(Process):
    """
    Start a Blender process that executes a python script
    """

    def __init__(self):
        super().__init__()
        self._cmd_args = ["--python-exit-code", "255", "--log-level", "-1", "--start-console"]

    def start(
        self,
        python_script_path: str = None,
        script_args: Optional[List[Any]] = None,
        blender_args: Optional[List[str]] = None,
        env: Optional[List[str]] = None,
    ):
        popen_args = [BLENDER_EXE]
        popen_args.extend(self._cmd_args)
        if blender_args is not None:
            popen_args.extend(blender_args)
        if python_script_path is not None:
            popen_args.extend(["--python", str(python_script_path)])
        if script_args is not None:
            popen_args.append("--")
            popen_args.extend([str(arg) for arg in script_args])

        popen_kwargs = {"creationflags": subprocess.CREATE_NEW_CONSOLE, "shell": False}
        popen_kwargs.update({"env": env})
        super().start(popen_args, popen_kwargs)


class BlenderServer(BlenderProcess):
    """
    Starts a Blender process that runs a python server. The Blender can be controlled
    by sending python source code.
    """

    def __init__(self, port: int, ptvsd_port: int = None, wait_for_debugger=False):
        super().__init__()
        self._port = port
        self._ptvsd_port = ptvsd_port
        self._wait_for_debugger = wait_for_debugger
        self._path = str(current_dir / "python_server.py")
        self._sock: socket.socket = None

    def start(self, blender_args: List = None, env: Optional[Mapping[str, str]] = None):
        args = [f"--port={self._port}"]
        if self._ptvsd_port is not None:
            args.append(f"--ptvsd={self._ptvsd_port}")
        if self._wait_for_debugger:
            args.append("--wait_for_debugger")

        # The testcase will start its own server and control its configuration.
        # If it fails we want to know and not have Blender silently start a misconfigured one
        env = {} if env is None else env
        env.update(dict(os.environ, MIXER_NO_START_SERVER="1"))
        super().start(self._path, args, blender_args, env=env)

    def connect(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connected = False
        max_attempts = 200
        attempts = 0
        while not connected and attempts < max_attempts:
            try:
                self._sock.connect(("127.0.0.1", self._port))
                connected = True
            except ConnectionRefusedError:
                time.sleep(0.1)
                attempts += 1

    def close(self):
        if self._sock is not None:
            self._sock.close()

    def send_string(self, script: str):
        self._sock.send(script.encode("utf-8"))

    def send_function(self, f: Callable, *args, **kwargs):
        """
        Remotely execute a function.

        Extracts the source code from the function f.
        The def statement must not be indented (no local function)
        """
        src = inspect.getsource(f)
        kwargs_ = [f"{key}={repr(value)}" for key, value in kwargs.items()]
        args_ = [f"{repr(arg)}" for arg in args]
        args_.extend(kwargs_)
        arg_string = "" if args_ is None else ",".join(args_)
        source = f"{src}\n{f.__name__}({arg_string})\n"
        self.send_string(source)

    def quit(self):
        self.send_function(blender_lib.quit)


class PythonProcess(Process):
    """
    Starts a Blender python process that runs a script
    """

    def __init__(self):
        super().__init__()
        blender_exe = os.environ.get("MIXER_BLENDER_EXE_PATH", "blender.exe")
        blender_dir = Path(blender_exe).parent
        python_paths = list(blender_dir.glob("*/python/bin/python.exe"))
        if len(python_paths) != 1:
            raise RuntimeError(f"Expected one python.exe, found {len(python_paths)} : {python_paths}")
        self._python_path = str(python_paths[0])

    def start(self, args: Optional[Iterable[Any]] = ()):
        popen_args = [self._python_path]
        popen_args.extend([str(arg) for arg in args])
        popen_kwargs = {}
        popen_kwargs.update({"creationflags": subprocess.CREATE_NEW_CONSOLE})
        popen_kwargs.update({"shell": False})
        super().start(popen_args, popen_kwargs)


class ServerProcess(PythonProcess):
    """
    Starts a broadcaster process
    """

    def __init__(self):
        super().__init__()
        self.port: int = DEFAULT_PORT
        self.host: str = "127.0.0.1"

    def start(self, server_args: Optional[List[str]] = None):
        # do not use an existing server, since it might not be ours and might not be setup
        # the way we want (throttling)
        try:
            self._test_connect()
        except ConnectionRefusedError:
            pass
        else:
            raise RuntimeError(f"A server listening at {self.host}:{self.port} already exists. Aborting")

        args = ["-m", "mixer.broadcaster.apps.server"]
        args.extend(["--port", str(self.port)])
        args.extend(["--log-level", "INFO"])
        if server_args:
            args.extend(server_args)
        super().start(args)
        self._test_connect(timeout=4)

    def _test_connect(self, timeout: float = 0.0):
        waited = 0.0
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.connect((self.host, self.port))
        except ConnectionRefusedError:
            if waited >= timeout:
                raise
            delay = 0.2
            time.sleep(delay)
            waited += delay
        finally:
            sock.close()
