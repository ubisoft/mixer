from dataclasses import dataclass
import json
import logging
import sys
import time
from typing import Any, Iterable, List, Optional
import unittest

from tests.blender_app import BlenderApp
from tests.grabber import Grabber, CommandStream
from tests.process import ServerProcess

from mixer.broadcaster.common import MessageType

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
        self._log_level = logging.INFO
        self._server_process: ServerProcess = ServerProcess()
        self._blenders: List[BlenderApp] = []

    def set_log_level(self, log_level):
        self._log_level = log_level

    @classmethod
    def get_class_name(cls, test_class, num, params_dict):
        """
        Tweak test case name for parameterized (from parameterized doc)
        """
        experimental = str(params_dict["experimental_sync"])
        return f"{test_class.__name__}_Experimental_{experimental}"

    @property
    def _sender(self):
        return self._blenders[0]

    @property
    def _receiver(self):
        return self._blenders[1]

    def setUp(
        self,
        blenderdescs: Iterable[BlenderDesc] = (BlenderDesc(), BlenderDesc()),
        server_args: Optional[List[str]] = None,
        join=True,
        join_delay: Optional[float] = None,
    ):
        """
        if a blendfile if not specified, blender will start with its default file.
        Not recommended) as it is machine dependent
        """
        super().setUp()
        try:
            python_port = 8081
            # do not the the default ptvsd port as it will be in use when debugging the TestCase
            ptvsd_port = 5688

            # start a broadcaster server
            self._server_process.start(server_args=server_args)

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
                    blender.connect_and_join_mixer(experimental_sync=self.experimental_sync)
                self._blenders.append(blender)
        except Exception:
            for blender in self._blenders:
                blender.kill()
            self.shutdown()
            raise

    def tearDown(self):
        self.shutdown()
        super().tearDown()

    def shutdown(self):
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
        try:
            host = server_process.host
            port = server_process.port

            scene_upload_delay = 1
            # Bumping the delay is required when running the tests from VScode text explorer
            # in debug on a "slow" machine. Otherwise either Blender disconnects before the room
            # content has been sent or the grabber tries to join the room before it is joinable.
            # It probably helps solving random failures on the Gitlab runner as well.
            vscode_debug_delay = 2
            scene_upload_delay += vscode_debug_delay

            # sender upload the room
            self._sender.connect_and_join_mixer(
                "mixer_grab_sender", keep_room_open=True, experimental_sync=self.experimental_sync
            )
            time.sleep(scene_upload_delay)
            self._sender.disconnect_mixer()

            # download the room from sender
            sender_grabber = Grabber()
            try:
                sender_grabber.grab(host, port, "mixer_grab_sender")
            except Exception as e:
                raise self.failureException("Sender grab: ", *e.args) from None

            # receiver upload the room
            self._receiver.connect_and_join_mixer(
                "mixer_grab_receiver", keep_room_open=True, experimental_sync=self.experimental_sync
            )
            time.sleep(scene_upload_delay)
            self._receiver.disconnect_mixer()

            # download the room from receiver
            receiver_grabber = Grabber()
            try:
                receiver_grabber.grab(host, port, "mixer_grab_receiver")
            except Exception as e:
                raise self.failureException("Receiver grab: ", *e.args) from None

        finally:
            server_process.kill()

        # TODO_ timing error : sometimes succeeds
        # TODO_ enhance comparison : check # elements, understandable comparison
        s = sender_grabber.streams
        r = receiver_grabber.streams
        self.assert_stream_equals(s, r)

    def assert_any_almost_equal(self, a: Any, b: Any, msg: str = None):

        # Use Assertion error.
        # The all but last args in the resulting exception is the path into the structure to the faulting element
        # Not that obvious to do something smarter to have a nicer display :
        # https://stackoverflow.com/questions/1319615/proper-way-to-declare-custom-exceptions-in-modern-python

        type_a = type(a)
        type_b = type(b)
        self.assertEqual(type_a, type_b, msg=msg)

        if isinstance(a, float):
            self.assertAlmostEqual(a, b, places=5, msg=msg)
        elif isinstance(a, (bool, int, str, bytes)):
            self.assertEqual(a, b, msg=msg)
        elif isinstance(a, (list, tuple)):
            for i, (item_a, item_b) in enumerate(zip(a, b)):
                try:
                    self.assert_any_almost_equal(item_a, item_b, msg=msg)
                except AssertionError as e:
                    raise AssertionError(i, *e.args) from None
        else:
            if isinstance(a, dict):
                dict_a, dict_b = a, b
            else:
                dict_a, dict_b = vars(a), vars(b)

            keys_a, keys_b = sorted(dict_a.keys()), sorted(dict_b.keys())
            self.assertListEqual(keys_a, keys_b, msg=msg)
            for k in keys_a:
                try:
                    self.assert_any_almost_equal(dict_a[k], dict_b[k], msg=msg)
                except AssertionError as e:
                    raise AssertionError(k, *e.args) from None

    def assert_stream_equals(self, streams_a: CommandStream, streams_b: CommandStream, msg: str = None):
        self.assertEqual(streams_a.commands.keys(), streams_b.commands.keys())

        for k in streams_a.commands.keys():
            commands_a, commands_b = streams_a.commands[k], streams_b.commands[k]
            message_type = str(MessageType(k))
            len_a, len_b = len(commands_a), len(commands_b)
            self.assertEqual(len_a, len_b, f"command stream length mismatch for {message_type}: {len_a} and {len_b}")

            if len_a != 0:
                logger.info(f"Message count for {message_type:16} : {len_a}")
            expected_count = self.expected_counts.get(k)
            if expected_count is not None:
                self.assertEqual(
                    expected_count,
                    len_a,
                    f"Unexpected message count for message {message_type}. Expected {expected_count}: found {len_a}",
                )

            def decode(c):
                return None

            decoded_stream_a = [(decode(c), c) for c in commands_a]
            decoded_stream_b = [(decode(c), c) for c in commands_b]

            # sort
            def key(a):
                return a[1].data

            decoded_stream_a.sort(key=key)
            decoded_stream_b.sort(key=key)

            for i, ((decoded_a, encoded_a), (decoded_b, encoded_b)) in enumerate(
                zip(decoded_stream_a, decoded_stream_b)
            ):
                self.assertIs(type(decoded_a), type(decoded_b))
                if decoded_a is None:
                    # no decoder, compare the buffers, will have problems will float comparisons
                    self.assert_any_almost_equal(
                        encoded_a, encoded_b, f"content mismatch for {message_type} at index {i}"
                    )
                else:
                    proxy_string_a = getattr(decoded_a, "proxy_string", None)
                    proxy_string_b = getattr(decoded_b, "proxy_string", None)
                    if proxy_string_a is not None and proxy_string_b is not None:
                        decoded_a.proxy_string = json.loads(proxy_string_a)
                        decoded_b.proxy_string = json.loads(proxy_string_b)
                    self.assert_any_almost_equal(
                        decoded_a, decoded_b, f"content mismatch for {message_type} at index {i}"
                    )

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
            blender.connect_and_join_mixer(experimental=self.experimental_sync)

    def disconnect(self):
        for blender in self._blenders:
            blender.disconnect_mixer()

    def send_string(self, s: str, to: Optional[int] = 0):
        self._blenders[to].send_string(s)

    def send_strings(self, strings: List[str], to: Optional[int] = 0):
        self.send_string("\n".join(strings), to)
