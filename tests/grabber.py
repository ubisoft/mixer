from mixer.broadcaster.common import MessageType
from mixer.broadcaster.common import Command
from mixer.broadcaster.common import ClientDisconnectedException
from mixer.broadcaster.common import decode_string, encode_string, encode_bool
from mixer.broadcaster.client import Client
from typing import Mapping, List
import time


class CommandStream:
    """
    Command stream split by command type
    """

    def __init__(self):
        self.commands: Mapping[int, List[Command]] = {m: [] for m in MessageType if m > MessageType.COMMAND}


class Grabber:
    """
    Grab the command stream from a server for the purpose of unit testing. Ignores protocol messages (JOIN, ...)
    and message order
    """

    def __init__(self):
        self.streams = CommandStream()

    def grab(self, host, port, room_name: str):
        with Client(host, port) as client:
            client.join_room(room_name, "ignored", "ignored", True, True)

            attempts_max = 20
            attempts = 0
            try:
                while attempts < attempts_max:
                    received_commands = client.fetch_incoming_commands()

                    attempts += 1
                    time.sleep(0.01)

                    for command in received_commands:
                        attempts = 0
                        if command.type == MessageType.SEND_ERROR:
                            message = decode_string(command.data, 0)
                            raise RuntimeError(f"Received error message {message}")
                        if command.type <= MessageType.COMMAND:
                            continue
                        # Ignore command serial Id, that may not match
                        command.id = 0
                        self.streams.commands[command.type].append(command)

            except ClientDisconnectedException:
                raise RuntimeError("Grabber: disconnected before received command stream.")

            client.send_command(Command(MessageType.SET_ROOM_KEEP_OPEN, encode_string(room_name) + encode_bool(False)))
            client.send_command(Command(MessageType.LEAVE_ROOM, room_name.encode("utf8")))

            if not client.wait(MessageType.LEAVE_ROOM):
                raise RuntimeError("Grabber: disconnected before receiving LEAVE_ROOM.")

            count = sum([len(commands) for commands in self.streams.commands.values()])
            assert count > 0, "No message grabbed"
