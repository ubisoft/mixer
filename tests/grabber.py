from mixer.broadcaster.common import MessageType
from mixer.broadcaster.common import Command
from mixer.broadcaster.common import ClientDisconnectedException
from mixer.broadcaster.common import encode_string, encode_bool
from mixer.broadcaster.client import Client
from typing import Mapping, List
import time
import sys


class CommandStream:
    """
    Command stream split by command type
    """

    def __init__(self):
        self.data: Mapping[int, List[Command]] = {m: [] for m in MessageType if m > MessageType.COMMAND}

    def sort(self):
        # For each command type, the comand ordering is not significant for deciding the test success
        # and the order may be different for the server and the receiver
        for commands in self.data.values():
            commands.sort()


class Grabber:
    """
    Grab the command stream from a server for the purpose of unit testing. Ignores protocol messages (JOIN, ...)
    and messagae order
    """

    def __init__(self):
        self.streams = CommandStream()

    def grab(self, host, port, room_name: str):
        with Client(host, port) as client:
            client.join_room(room_name)

            attempts_max = 20
            attempts = 0
            try:
                while attempts < attempts_max:
                    received_commands = client.fetch_incoming_commands()
                    if received_commands is None:
                        raise ClientDisconnectedException()

                    attempts += 1
                    time.sleep(0.01)

                    for command in received_commands:
                        attempts = 0
                        if command.type <= MessageType.COMMAND:
                            continue
                        # Ignore command serial Id, that may not match
                        command.id = 0
                        self.streams.data[command.type].append(command.data)
            except ClientDisconnectedException:
                print("Grabber: disconnected before received command stream.", file=sys.stderr)

            client.send_command(Command(MessageType.SET_ROOM_KEEP_OPEN, encode_string(room_name) + encode_bool(False)))
            client.send_command(Command(MessageType.LEAVE_ROOM, room_name.encode("utf8")))

            if not client.wait(MessageType.LEAVE_ROOM):
                print("Grabber: disconnected before receiving LEAVE_ROOM.", file=sys.stderr)

    def sort(self):
        self.streams.sort()
