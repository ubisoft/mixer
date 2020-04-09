import sys  # nopep8
from pathlib import Path  # nopep8
sys.path.append(str(Path(__package__).parent))  # nopep8

from broadcaster.common import MessageType
from broadcaster.common import Command
from broadcaster.common import readMessage
from broadcaster.common import ClientDisconnectedException
from broadcaster.client import Client
from typing import Mapping, List
import threading
import time


class CommandStream():
    """
    Command stream split by command type
    """

    def __init__(self):
        self.data: Mapping[int, List[Command]] = {
            m: [] for m in MessageType if m > MessageType.COMMAND
        }

    def sort(self):
        # For each command type, the comand ordering is not significant for deciding the test success
        # and the order may be different for the server and the receiver
        for commands in self.data.values():
            commands.sort()


class Grabber():
    """
    Grab the command stream from a server for the purpose of unit testing. Ignores protocol messages (JOIN, ...)
    and messagae order
    """

    def __init__(self):
        self.streams = CommandStream()

    def grab(self, host, port, room_name: str):
        client = Client(host, port)
        client.connect()
        command = Command(MessageType.JOIN_ROOM, room_name.encode('utf8'))
        client.addCommand(command)

        attempts_max = 20
        attempts = 0
        try:
            while attempts < attempts_max:
                command = client.getNextReceivedCommand()
                if command is None:
                    attempts += 1
                    time.sleep(0.01)
                    continue
                attempts = 0
                if command.type <= MessageType.COMMAND:
                    continue
                # Ignore command serial Id, that may not match
                command.id = 0
                self.streams.data[command.type].append(command.data)
        except ClientDisconnectedException:
            pass
        client.threadAlive = False

        self.streams.sort()
