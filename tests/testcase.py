import unittest
import time
import blender_lib as bl
import dccsync_lib as dccsync
from process import BlenderServer
from typing import List
import time


class Blender:
    def __init__(self, port: int, ptvsd_port: int):
        self._port = port
        self._ptvsd_port = ptvsd_port
        self.__blender: BlenderServer = None

    def setup(self, blender_args: List = None):
        self._blender = BlenderServer(self._port, self._ptvsd_port)
        self._blender.start(blender_args)
        self._blender.connect()
        self._blender.send_function(dccsync.connect)
        self._blender.send_function(dccsync.join_room)

    def teardown(self):
        self._blender.wait()
        # time.sleep(60)
        # self._blender.send_function(bl.quit)

    def send_function(self, f, *args, **kwargs):
        self._blender.send_function(f, *args, **kwargs)

        time.sleep(1)


class BlenderTestCase(unittest.TestCase):
    def setUp(self):
        python_port = 8081
        # do not the the default ptvsd posrt as it will be in use when debugging the TestCase
        ptvsd_port = 5688
        self._sender = Blender(python_port + 0, ptvsd_port + 0)
        self._sender.setup(["--window-geometry", "0", "0", "960", "1080"])

        time.sleep(1)

        self._receiver = Blender(python_port + 1, ptvsd_port + 1)
        self._receiver.setup(["--window-geometry", "960", "0", "960", "1080"])

    def tearDown(self):
        self._sender.teardown()
        self._receiver.teardown()
