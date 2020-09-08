import logging
import time
from typing import List, Optional, Mapping
import sys

import tests.blender_lib as bl
import tests.mixer_lib as mixer_lib
from tests.process import BlenderServer

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)


class BlenderApp:
    def __init__(self, port: int, ptvsd_port: int = None, wait_for_debugger=False):
        self._port = port
        self._ptvsd_port = ptvsd_port
        self._wait_for_debugger = wait_for_debugger
        self._blender: BlenderServer = None
        self._log_level = None

    def set_log_level(self, log_level: int):
        self._log_level = log_level

    def setup(self, blender_args: List = None, env: Optional[Mapping[str, str]] = None):
        self._blender = BlenderServer(self._port, self._ptvsd_port, self._wait_for_debugger)
        self._blender.start(blender_args, env)
        self._blender.connect()

    def connect_mixer(self,):
        if self._log_level is not None:
            self._blender.send_function(mixer_lib.set_log_level, self._log_level)
        self._blender.send_function(mixer_lib.connect)

    def create_room(self, room_name="mixer_unittest", keep_room_open=False, experimental_sync: bool = False):
        self._blender.send_function(mixer_lib.create_room, room_name, experimental_sync)
        self._blender.send_function(mixer_lib.keep_room_open, room_name, keep_room_open)

    def join_room(self, room_name="mixer_unittest", experimental_sync: bool = False):
        self._blender.send_function(mixer_lib.join_room, room_name, experimental_sync)

    def disconnect_mixer(self):
        self._blender.send_function(mixer_lib.disconnect)

    def wait(self, timeout: float = None):
        return self._blender.wait(timeout)
        # time.sleep(60)
        # self._blender.send_function(bl.quit)

    def kill(self):
        self._blender.kill()

    def send_function(self, f, *args, **kwargs):
        self._blender.send_function(f, *args, **kwargs)
        time.sleep(1)

    def send_string(self, s):
        self._blender.send_string(s)
        time.sleep(0.5)

    def quit(self):
        self._blender.send_function(bl.quit)

    def close(self):
        self._blender.close()
