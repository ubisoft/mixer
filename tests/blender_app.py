import logging
import time
from typing import List
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

    def setup(self, blender_args: List = None):
        self._blender = BlenderServer(self._port, self._ptvsd_port, self._wait_for_debugger)
        self._blender.start(blender_args)
        self._blender.connect()
        self.connect_and_join_mixer()

    def connect_and_join_mixer(self, room_name="mixer_unittest"):
        if self._log_level is not None:
            self._blender.send_function(mixer_lib.set_log_level, self._log_level)
        self._blender.send_function(mixer_lib.connect)
        self._blender.send_function(mixer_lib.join_room, room_name)

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

    def quit(self):
        self._blender.send_function(bl.quit)

    def close(self):
        self._blender.close()
