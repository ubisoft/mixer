import unittest
import time
import blender_lib
import dccsync_lib as dccsync
from process import BlenderServer
from typing import List
import hashlib
import tempfile
from pathlib import Path


class Blender:
    def __init__(self, port: int, ptvsd_port: int = None, wait_for_debugger=False):
        self._port = port
        self._ptvsd_port = ptvsd_port
        self._wait_for_debugger = wait_for_debugger
        self.__blender: BlenderServer = None

    def setup(self, blender_args: List = None):
        self._blender = BlenderServer(self._port, self._ptvsd_port, self._wait_for_debugger)
        self._blender.start(blender_args)
        self._blender.connect()
        self._blender.send_function(dccsync.connect)
        self._blender.send_function(dccsync.join_room)

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
        self._blender.send_function(blender_lib.quit)


class BlenderTestCase(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        self._sender_wait_for_debugger = False
        self._receiver_wait_for_debugger = False
        super().__init__(*args, **kwargs)

    def sender_wait_for_debugger(self):
        self._sender_wait_for_debugger = True

    def receiver_wait_for_debugger(self):
        self._receiver_wait_for_debugger = True

    def setUp(self):
        python_port = 8081
        # do not the the default ptvsd port as it will be in use when debugging the TestCase
        ptvsd_port = 5688
        self._sender = Blender(python_port + 0, ptvsd_port + 0, self._sender_wait_for_debugger)
        self._sender.setup(["--window-geometry", "0", "0", "960", "1080"])

        self._receiver = Blender(python_port + 1, ptvsd_port + 1, self._receiver_wait_for_debugger)
        self._receiver.setup(["--window-geometry", "960", "0", "960", "1080"])

    def tearDown(self):
        self._wait_for_debugger = False
        self._sender.wait()
        self._receiver.wait()

    def assertUserSuccess(self):
        """
        Test the processes return codes, that can be set from the TestPanel UI
        """
        timeout = 0.2
        rc = None
        while True:
            rc = self._sender.wait(timeout)
            if rc is not None:
                self._receiver.kill()
                if rc != 0:
                    self.fail(f'sender return code {rc}')
                else:
                    return

            rc = self._receiver.wait(timeout)
            if rc is not None:
                self._sender.kill()
                if rc != 0:
                    self.fail(f'receiver return code {rc}')
                else:
                    return

    def assertSameFiles(self):
        """
        Save and quit, then compare files

        This currently fails :
        - files are different for no apparent reason one file contains an extra Image block name Viewer Node

        """
        with Path(tempfile.mkdtemp()) as tmp_dir:
            sender_file = tmp_dir / 'sender'
            receiver_file = tmp_dir / 'receiver'
            self._sender.send_function(blender_lib.save, str(sender_file))
            self._receiver.send_function(blender_lib.save, str(receiver_file))
            self._sender.quit()
            self._receiver.quit()
            self.assertUserSuccess()
            self.assertFilesIdentical(sender_file, receiver_file)

    def assertFileExists(self, path):
        self.assertTrue(Path(path).is_file(), f'File does not exist or is not a file : {path}')

    def assertFilesIdentical(self, *files):
        """

        """
        if len(files) == 0:
            return

        paths = [Path(f) for f in files]
        for path in paths:
            self.assertFileExists(path)

        attrs = [(path, path.stat().st_size) for path in files]
        p0, s0 = attrs[0]
        for (p,  s) in attrs:
            self.assertEqual(s0, s, f'File size differ for {p0} ({s0}) and {p} ({s})')

        hashes = []
        for path in paths:
            hash = hashlib.md5()
            with open(path, 'rb') as f:
                hash.update(f.read())
            hashes.append((path, hash))

        p0, h0 = hashes[0]
        for (p,  h) in attrs:
            self.assertEqual(h0, h, f'Hashes differ for {p0} ({h0.hex()}) and {p} ({h.hex()})')
