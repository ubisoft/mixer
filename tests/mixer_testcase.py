from dataclasses import dataclass
import logging
import os
import sys
import time
from typing import Iterable, List, Optional
import unittest

from mixer.broadcaster.common import DEFAULT_PORT

from tests.blender_app import BlenderApp
from tests.grabber import Grabber
from tests.process import ServerProcess

logging.basicConfig(stream=sys.stderr, level=logging.WARNING)
logger = logging.getLogger(__name__)


@dataclass
class BlenderDesc:
    load_file: Optional[str] = None
    wait_for_debugger: bool = False


class MixerTestCase(unittest.TestCase):
    """
    Base test case class for Mixer.

    MixerTestCase :
    - starts several instances of Blender,
    - connects them to a broadcaster server,

    Derived classes
    - "injects" Python commands into one or mode Blender, letting Mixer synchronize them
    - test success/failure
    """

    def __init__(self, *args, **kwargs):
        self.expected_counts = {}
        super().__init__(*args, **kwargs)
        self._log_level = None
        self._server_process: ServerProcess = ServerProcess()
        self._blenders: List[BlenderApp] = []

    def set_log_level(self, log_level):
        self._log_level = log_level

    @property
    def _sender(self):
        return self._blenders[0]

    @property
    def _receiver(self):
        return self._blenders[1]

    def setUp(self, blenderdescs: Iterable[BlenderDesc] = (BlenderDesc(), BlenderDesc()), join=True):
        """
        if a blendfile if not specified, blender will start with its default file.
        Not recommended) as it is machine dependent
        """
        super().setUp()
        python_port = 8081
        # do not the the default ptvsd port as it will be in use when debugging the TestCase
        ptvsd_port = 5688

        # start a broadcaster server
        self._server_process.start()

        # start all the blenders
        window_width = int(1920 / len(blenderdescs))
        for i, blenderdesc in enumerate(blenderdescs):
            window_x = str(i * window_width)
            args = ["--window-geometry", window_x, "0", "960", "1080"]
            if blenderdesc.load_file is not None:
                args.append(str(blenderdesc.load_file))

            blender = BlenderApp(python_port + i, ptvsd_port + i, blenderdesc.wait_for_debugger)
            blender.set_log_level(self._log_level)
            blender.setup(args)
            if join:
                blender.connect_and_join_mixer()
            self._blenders.append(blender)

    def tearDown(self):
        # quit and wait
        for blender in self._blenders:
            blender.quit()
        for blender in self._blenders:
            blender.wait()
        for blender in self._blenders:
            blender.close()

        self._server_process.kill()
        super().tearDown()

    def end_test(self):
        self.assert_matches()

    def assert_matches(self):
        # TODO add message cout dict as param

        self._sender.disconnect_mixer()
        # time.sleep(1)
        self._receiver.disconnect_mixer()

        # wait for disconnect before killing the server. Avoids a disconnect operator context error message
        time.sleep(0.5)

        self._server_process.kill()

        # start a broadcaster server to grab the room
        server_process = ServerProcess()
        server_process.start()

        host = "127.0.0.1"
        port = int(os.environ.get("VRTIST_PORT", DEFAULT_PORT))
        # upload the room
        self._sender.connect_and_join_mixer("mixer_grab_sender", keep_room_open=True)
        time.sleep(1)
        self._sender.disconnect_mixer()

        # download the room
        sender_grabber = Grabber()
        sender_grabber.grab(host, port, "mixer_grab_sender")
        # HACK messages are not delivered in the same order on the receiver and the sender
        # so sort each substream
        sender_grabber.sort()

        self._receiver.connect_and_join_mixer("mixer_grab_receiver", keep_room_open=True)
        time.sleep(1)
        self._receiver.disconnect_mixer()
        receiver_grabber = Grabber()
        receiver_grabber.grab(host, port, "mixer_grab_receiver")
        receiver_grabber.sort()

        server_process.kill()

        # TODO_ timing error : sometimes succeeds
        # TODO_ enhance comparison : check # elements, understandable comparison
        s = sender_grabber.streams
        r = receiver_grabber.streams
        self.assert_stream_equals(s, r)

    def assert_user_success(self):
        """
        Test the processes return codes, that can be set from the TestPanel UI (a manual process)
        """
        timeout = 0.2
        rc = None
        while True:
            rc = self._sender.wait(timeout)
            if rc is not None:
                self._receiver.kill()
                if rc != 0:
                    self.fail(f"sender return code {rc} ({hex(rc)})")
                else:
                    return

            rc = self._receiver.wait(timeout)
            if rc is not None:
                self._sender.kill()
                if rc != 0:
                    self.fail(f"receiver return code {rc} ({hex(rc)})")
                else:
                    return

    def connect(self):
        for i, blender in enumerate(self._blenders):
            if i > 0:
                time.sleep(1)
            blender.connect_and_join_mixer()

    def disconnect(self):
        for blender in self._blenders:
            blender.disconnect_mixer()

    def send_string(self, s: str):
        self._sender.send_string(s)
