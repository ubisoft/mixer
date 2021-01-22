"""
Base class for test cases
"""
import array
from dataclasses import dataclass
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any, Iterable, List, Optional, Tuple
import unittest

from tests.blender_app import BlenderApp
from tests.grabber import Grabber, CommandStream
from tests.process import ServerProcess

import mixer.codec
from mixer.broadcaster.common import Command, MessageType
from mixer.blender_data.types import Soa

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
        self.latency = 0
        self.expected_counts = {}
        super().__init__(*args, **kwargs)
        self._log_level = logging.WARNING
        self._server_process: ServerProcess = ServerProcess()
        self._blenders: List[BlenderApp] = []
        self.ignored_messages = set()
        self.experimental_sync = True
        self.shared_folders: List[List[str]] = []
        """One list of shared_folder folders per Blender"""

    @property
    def log_level(self):
        return self._log_level

    @log_level.setter
    def log_level(self, log_level):
        self._log_level = log_level

    @classmethod
    def get_class_name(cls, test_class, num, params_dict):
        """
        Tweak test case name for parameterized (from parameterized doc)
        """
        if params_dict["vrtist_protocol"]:
            suffix = "_VRtist"
        else:
            suffix = "_Generic"

        return test_class.__name__ + suffix

    @property
    def _sender(self):
        return self._blenders[0]

    @property
    def _receiver(self):
        return self._blenders[1]

    def setUp(
        self,
        blenderdescs: Tuple[BlenderDesc, BlenderDesc] = (BlenderDesc(), BlenderDesc()),
        server_args: Optional[List[str]] = None,
        join=True,
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
                shared_folders = self.shared_folders[i] if i < len(self.shared_folders) else []
                if not isinstance(shared_folders, (list, tuple)):
                    self.fail(f"shared_folder must be a list or tuple, not a {type(shared_folders)}")

                window_x = str(i * window_width)
                args = ["--window-geometry", window_x, "0", "960", "1080"]
                if blenderdesc.load_file is not None:
                    args.append(str(blenderdesc.load_file))
                blender = BlenderApp(python_port + i, ptvsd_port + i, blenderdesc.wait_for_debugger)
                blender.set_log_level(self._log_level)
                blender.setup(args)
                if join:
                    blender.connect_mixer()
                    if i == 0:
                        blender.create_room(vrtist_protocol=self.vrtist_protocol, shared_folders=shared_folders)
                    else:
                        blender.join_room(vrtist_protocol=self.vrtist_protocol, shared_folders=shared_folders)

                self._blenders.append(blender)

            # join_room waits for the room to be joinable before issuing join room, but it
            # cannot wait for the reception of the room contents
            time.sleep(10 * self.latency)

            mixer.codec.register()
        except Exception:
            self.shutdown()
            raise

    def tearDown(self):
        self.shutdown()
        super().tearDown()

    def shutdown(self):
        # quit and wait
        for blender in self._blenders:
            try:
                blender.quit()
                blender.wait()
                blender.close()
            except Exception:
                # always close server
                pass

        self._server_process.kill()
        mixer.codec.unregister()

    def end_test(self):
        self.assert_matches()

    def assert_matches(self, ignore: Iterable[str] = ()):
        # TODO add message count dict as param
        try:
            self._sender.disconnect_mixer()
            # time.sleep(1)
            self._receiver.disconnect_mixer()
        except Exception as e:
            raise self.failureException(f"Exception during disconnect():\n{e!r}\nPossible Blender crash") from None

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

            grabbers = []
            for i, blender in enumerate(self._blenders):
                # blender upload room
                blender.connect_mixer()
                shared_folders = self.shared_folders[i] if i < len(self.shared_folders) else []
                blender.create_room(
                    f"mixer_grab_{i}",
                    keep_room_open=True,
                    vrtist_protocol=self.vrtist_protocol,
                    shared_folders=shared_folders,
                )
                time.sleep(scene_upload_delay)
                blender.disconnect_mixer()

                # download the room
                grabber = Grabber()
                grabbers.append(grabber)
                try:
                    grabber.grab(host, port, f"mixer_grab_{i}")
                except Exception as e:
                    raise self.failureException(f"Grab {i}: ", *e.args) from None

        finally:
            server_process.kill()

        s = grabbers[0].streams
        r = grabbers[1].streams
        self.assert_stream_equals(s, r, ignore=ignore)

    def assert_any_almost_equal(self, a: Any, b: Any, msg: str = "", ignore: Iterable[str] = ()):
        """Recursive comparison with float tolerance"""
        # Use Assertion error.
        # The all but last args in the resulting exception is the path into the structure to the faulting element
        # Not that obvious to do something smarter to have a nicer display :
        # https://stackoverflow.com/questions/1319615/proper-way-to-declare-custom-exceptions-in-modern-python

        type_a = type(a)
        type_b = type(b)
        self.assertEqual(type_a, type_b, msg=msg)

        if isinstance(a, (bool, int, str, bytes, type(None))):
            self.assertEqual(a, b, msg=msg)
        elif isinstance(a, float):
            self.assertAlmostEqual(a, b, places=4, msg=msg)
        elif isinstance(a, array.array):
            self.assert_any_almost_equal(a.tolist(), b.tolist(), msg=msg)
        elif isinstance(a, (list, tuple)):
            self.assertEqual(len(a), len(b), msg=msg)
            for i, (item_a, item_b) in enumerate(zip(a, b)):
                try:
                    self.assert_any_almost_equal(item_a, item_b, msg=msg, ignore=ignore)
                except AssertionError as e:
                    raise AssertionError(i, *e.args) from None
        else:
            if isinstance(a, dict):
                dict_a, dict_b = a, b
            else:
                if isinstance(a, Soa):
                    # soa members are not delivered in deterministic order, sort by name
                    def first_item_pred(x):
                        return x[0]

                    a.members.sort(key=first_item_pred)
                    b.members.sort(key=first_item_pred)
                dict_a, dict_b = vars(a), vars(b)

            keys_a, keys_b = sorted(dict_a.keys()), sorted(dict_b.keys())
            self.assertListEqual(keys_a, keys_b, msg=msg)
            for k in keys_a:
                if k in ignore:
                    continue
                try:
                    self.assert_any_almost_equal(dict_a[k], dict_b[k], msg=msg, ignore=ignore)
                except AssertionError as e:
                    raise AssertionError(k, *e.args) from None

    def assert_stream_equals(
        self, streams_a: CommandStream, streams_b: CommandStream, msg: str = None, ignore: Iterable[str] = ()
    ):
        self.assertEqual(streams_a.commands.keys(), streams_b.commands.keys())

        for k in streams_a.commands.keys():
            len_a = len(streams_a.commands[k])
            len_b = len(streams_b.commands[k])
            self.assertEqual(len_a, len_b, f"Command count mismatch for {MessageType(k)!r}: {len_a} vs {len_b}")

        def decode_and_sort_messages(commands: List[Command]) -> List[mixer.codec.Message]:
            stream = [mixer.codec.decode(c) for c in commands]
            stream.sort()
            return stream

        def sort_buffers(commands: List[Command]) -> List[bytes]:
            stream = [c.data for c in commands]
            stream.sort()
            return stream

        message_types = streams_a.commands.keys() - self.ignored_messages
        for message_type in message_types:
            commands_a, commands_b = streams_a.commands[message_type], streams_b.commands[message_type]
            len_a = len(commands_a)
            if len_a == 0:
                continue

            message_name = str(MessageType(message_type))
            logger.info(f"Message count for {message_name:16} : {len_a}")

            # Equality tests required to handle float comparison.
            # This prevents us from using raw buffer comparison if they contain floats,
            # so decode the messages that contain floats.
            # Due to a lack of time not all decodable message classes are implemented.
            if mixer.codec.is_registered(message_type):
                decoded_stream_a = decode_and_sort_messages(commands_a)
                decoded_stream_b = decode_and_sort_messages(commands_b)
                if message_type in {MessageType.BLENDER_DATA_CREATE, MessageType.BLENDER_DATA_UPDATE}:
                    string_a = "\n".join([message.proxy_string for message in decoded_stream_a])
                    string_b = "\n".join([message.proxy_string for message in decoded_stream_b])
                else:
                    string_a = "\n".join([str(message) for message in decoded_stream_a])
                    string_b = "\n".join([str(message) for message in decoded_stream_b])
                detail_message = f"Stream_a\n{string_a}\nStream_b\n{string_b}\n"

                if len(decoded_stream_a) != len(decoded_stream_b):
                    self.failureException(f"{message_type} : sequence length mismatch:\n{detail_message}")

                expected_count = self.expected_counts.get(message_type)
                if expected_count is not None:
                    self.assertEqual(
                        expected_count,
                        len_a,
                        f"Unexpected message count for message {message_name}. Expected {expected_count}: found {len_a}\n{detail_message}",
                    )

                def decode_proxy_strings(stream):
                    for decoded in stream:
                        # HACK do not hardcode
                        proxy_string = getattr(decoded, "proxy_string", None)
                        if proxy_string is not None:
                            decoded.proxy_string = json.loads(proxy_string)

                decode_proxy_strings(decoded_stream_a)
                decode_proxy_strings(decoded_stream_b)

                for i, (decoded_a, decoded_b) in enumerate(zip(decoded_stream_a, decoded_stream_b)):
                    # TODO there another failure case with floats as they will cause sort differences for proxies
                    # we actually need to sort on something else, that the encoded json of the proxy, maybe the uuid
                    self.assertIs(
                        type(decoded_a),
                        type(decoded_b),
                        f"{message_name}: Type mismatch at decoded message mismatch at index {i}",
                    )

                if message_type == MessageType.BLENDER_DATA_CREATE:

                    def identifier(message):
                        return (
                            message.proxy_string["_datablock_uuid"],
                            message.proxy_string["_bpy_data_collection"],
                            message.proxy_string["_data"].get("name"),
                        )

                    def patch(message):
                        # remove folder part, that differs when workspace folders differ
                        # process only create since room grabbing only generates CREATE messages
                        proxy = message.proxy_string
                        if "_filepath_raw" in proxy:
                            filename = Path(proxy["_filepath_raw"]).name
                            proxy["_filepath_raw"] = filename
                            proxy["_data"]["filepath"] = filename
                            proxy["_data"]["filepath_raw"] = filename

                    short_a, short_b = [], []
                    for a, b in zip(decoded_stream_a, decoded_stream_b):
                        short_a.append(identifier(a))
                        short_b.append(identifier(b))
                        patch(a)
                        patch(b)

                    self.assertListEqual(short_a, short_b, f"Mismatch for {message_name} at index {i}")
                elif message_type == MessageType.BLENDER_DATA_MEDIA:
                    # workspaces are not set for room grabbing and BLENDER_DATA_MEDIA are always received
                    # although they were not part of the test operation with workspaces
                    for a, b in zip(decoded_stream_a, decoded_stream_b):
                        # remove folder part, that differs when workspace folders differ
                        a.path = Path(a.path).name
                        b.path = Path(b.path).name

                for i, (decoded_a, decoded_b) in enumerate(zip(decoded_stream_a, decoded_stream_b)):
                    self.assert_any_almost_equal(
                        decoded_a, decoded_b, f"{message_name}: decoded message mismatch at index {i}", ignore=ignore
                    )
            else:
                buffer_stream_a = sort_buffers(commands_a)
                buffer_stream_b = sort_buffers(commands_b)
                len_a = len(buffer_stream_a)
                len_b = len(buffer_stream_b)
                if len_a != len_b:

                    def dump(buffers):
                        strings = [str(b) for b in buffers]
                        return "\n".join(strings)

                    string_a = dump(buffer_stream_a)
                    string_b = dump(buffer_stream_b)
                    message = f"Stream_a ({len_a} elements)\n{string_a}\n\nStream_b ({len_b} elements)\n{string_b}\n"
                    raise self.failureException(f"\n{message_name} : sequence length mismatch:\n{message}")

                for i, (buffer_a, buffer_b) in enumerate(zip(buffer_stream_a, buffer_stream_b)):
                    self.assertIs(type(buffer_a), type(buffer_b))
                    self.assert_any_almost_equal(
                        buffer_a, buffer_b, f"{message_name}: encoded buffer mismatch at index {i}", ignore=ignore
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
            blender.connect_mixer()
            if i == 0:
                blender.create_room(vrtist_protocol=self.vrtist_protocol)
            else:
                blender.join_room(vrtist_protocol=self.vrtist_protocol)

    def disconnect(self):
        try:
            for blender in self._blenders:
                blender.disconnect_mixer()
        except Exception as e:
            raise self.failureException(f"Exception {e!r} during disconnect_mixer(). Possible Blender crash")

    def send_string(self, s: str, to: int = 0, sleep: float = 0.5):
        try:
            self._blenders[to].send_string(s, sleep)
        except Exception as e:
            raise self.failureException(
                f"Exception {e!r}\n" "during send command :\n" "{s}\n" "to Blender {to}.\n" "Possible Blender crash"
            )

    def send_strings(self, strings: List[str], to: int = 0, sleep: float = 0.5):
        self.send_string("\n".join(strings), to, sleep)
