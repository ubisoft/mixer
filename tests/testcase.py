import unittest
import time
import blender_lib as bl
import dccsync_lib as dccsync
from process import BlenderServer
from typing import List


class Blender:
    def __init__(self, port: int):
        self._port = port
        self.__blender: BlenderServer = None

    def setup(self, blender_args: List = None):
        self._blender = BlenderServer(self._port)
        self._blender.start(blender_args)
        self._blender.connect()
        self._blender.send_function(dccsync.connect)
        self._blender.send_function(dccsync.join_room)

    def teardown(self):
        time.sleep(60)
        self._blender.send_function(bl.quit)

    def send_function(self, f, *args, **kwargs):
        self._blender.send_function(f, *args, **kwargs)


class BlenderTestCase(unittest.TestCase):
    def setUp(self):
        self._sender = Blender(8081)
        self._sender.setup(["--window-geometry", "0", "0", "960", "1080"])
        self._receiver = Blender(8082)
        self._receiver.setup(["--window-geometry", "960", "0", "960", "1080"])

    def tearDown(self):
        self._sender.teardown()
        self._receiver.teardown()
