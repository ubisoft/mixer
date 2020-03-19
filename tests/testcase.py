import unittest
import time
import blender_lib
import dccsync_lib
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
        self._blender.send_function(dccsync_lib.connect)
        self._blender.send_function(dccsync_lib.join_room)

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

    def setUp(self, sender_blendfile=None, receiver_blendfile=None,
              sender_wait_for_debugger=False, receiver_wait_for_debugger=False):
        """
        if a blendfile if not specified, blender will start with its default file.
        Not recommended) as it is machine dependent
        """
        super().setUp()
        python_port = 8081
        # do not the the default ptvsd port as it will be in use when debugging the TestCase
        ptvsd_port = 5688
        sender_args = ["--window-geometry", "0", "0", "960", "1080"]
        if sender_blendfile is not None:
            sender_args.append(str(sender_blendfile))
        self._sender = Blender(python_port + 0, ptvsd_port + 0, sender_wait_for_debugger)
        self._sender.setup(sender_args)

        receiver_args = ["--window-geometry", "960", "0", "960", "1080"]
        if receiver_blendfile is not None:
            receiver_args.append(str(receiver_blendfile))
        self._receiver = Blender(python_port + 1, ptvsd_port + 1, receiver_wait_for_debugger)
        self._receiver.setup(receiver_args)

    def tearDown(self):
        self._wait_for_debugger = False
        self._sender.wait()
        self._receiver.wait()
        super().tearDown()

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
