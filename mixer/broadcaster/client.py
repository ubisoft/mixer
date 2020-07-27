import queue
import socket
import logging
import time
from typing import Dict, Any

import mixer.broadcaster.common as common
from mixer.broadcaster.common import MessageType
from mixer.broadcaster.common import update_dict_and_get_diff

logger = logging.getLogger() if __name__ == "__main__" else logging.getLogger(__name__)


class Client:
    """
    The client class is responsible for:
    - handling the connection with the server
    - receiving packet of bytes to convert them to commands
    - send commands
    """

    def __init__(self, host=common.DEFAULT_HOST, port=common.DEFAULT_PORT):
        self.host = host
        self.port = port
        self.received_commands = queue.Queue()
        self.pending_commands = queue.Queue()  # todo: does not need to be a queue anymore, at least for Blender client
        self.socket = None
        self.current_metadata: Dict[str, Any] = {}

    def __del__(self):
        if self.socket is not None:
            self.disconnect()

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, *args):
        if self.is_connected():
            self.disconnect()

    def connect(self):
        if self.is_connected():
            raise RuntimeError("Client.connect : already connected")

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            local_address = self.socket.getsockname()
            logger.info(
                "Connecting from local %s:%s to %s:%s", local_address[0], local_address[1], self.host, self.port,
            )
            self.safe_write_message(common.Command(common.MessageType.CLIENT_ID))
            self.safe_write_message(common.Command(common.MessageType.LIST_ALL_CLIENTS))
            self.safe_write_message(common.Command(common.MessageType.LIST_ROOMS))
        except ConnectionRefusedError:
            self.socket = None
        except common.ClientDisconnectedException:
            self.handle_connection_lost()
        except Exception as e:
            logger.error("Connection error %s", e, exc_info=True)
            self.socket = None
            raise

    def disconnect(self):
        if self.socket:
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()
            self.socket = None

    def is_connected(self):
        return self.socket is not None

    def add_command(self, command):
        self.pending_commands.put(command)

    def handle_connection_lost(self):
        logger.info("Connection lost for %s:%s", self.host, self.port)
        # Set socket to None before putting CONNECTION_LIST message to avoid sending/reading new messages
        self.socket = None
        command = common.Command(common.MessageType.CONNECTION_LOST)
        self.received_commands.put(command)

    def safe_write_message(self, command: common.Command):
        try:
            common.write_message(self.socket, command)
            return True
        except common.ClientDisconnectedException:
            self.handle_connection_lost()
            return False

    def join_room(self, room_name):
        return self.safe_write_message(common.Command(common.MessageType.JOIN_ROOM, room_name.encode("utf8"), 0))

    def leave_room(self, room_name):
        return self.safe_write_message(common.Command(common.MessageType.LEAVE_ROOM, room_name.encode("utf8"), 0))

    def wait_for(self, message_type: MessageType):
        while self.is_connected():
            self.fetch_commands()
            while self.is_connected():
                command = self.get_next_received_command()
                if command is None:
                    break
                if command.type == message_type:
                    return True
        # was disconnected before getting the message
        return False

    def delete_room(self, room_name):
        return self.safe_write_message(common.Command(common.MessageType.DELETE_ROOM, room_name.encode("utf8"), 0))

    def set_client_metadata(self, metadata: dict):
        diff = update_dict_and_get_diff(self.current_metadata, metadata)
        if diff == {}:
            return True

        return self.safe_write_message(
            common.Command(common.MessageType.SET_CLIENT_METADATA, common.encode_json(diff), 0)
        )

    def set_room_metadata(self, room_name: str, metadata: dict):
        return self.safe_write_message(common.make_set_room_metadata_command(room_name, metadata))

    def send_list_rooms(self):
        return self.safe_write_message(common.Command(common.MessageType.LIST_ROOMS))

    def set_room_keep_open(self, room_name: str, value: bool):
        return self.safe_write_message(
            common.Command(
                common.MessageType.SET_ROOM_KEEP_OPEN, common.encode_string(room_name) + common.encode_bool(value), 0
            )
        )

    def fetch_incoming_commands(self):
        """
        Gather incoming commands in received_commands queue.
        """
        while True:
            try:
                command = common.read_message(self.socket)
            except common.ClientDisconnectedException:
                self.handle_connection_lost()
                break

            if command is None:
                break

            self.received_commands.put(command)

    def fetch_outgoing_commands(self, commands_send_interval=0):
        """
        Send commands in pending_commands queue to the server.
        """
        while True:
            try:
                command = self.pending_commands.get_nowait()
            except queue.Empty:
                break

            logger.debug("Send %s (queue size = %d)", command.type, self.pending_commands.qsize())

            if not self.safe_write_message(command):
                break

            self.pending_commands.task_done()
            if commands_send_interval > 0:
                time.sleep(commands_send_interval)

    def fetch_commands(self, commands_send_interval=0):
        """
        commands_send_interval is used for debug, to test stability
        """
        self.fetch_incoming_commands()
        self.fetch_outgoing_commands(commands_send_interval)

    def get_next_received_command(self):
        try:
            command = self.received_commands.get_nowait()
            self.received_commands.task_done()
            logger.debug("Receive %s (queue size = %d)", command.type, self.received_commands.qsize())
            return command
        except queue.Empty:
            return None


# For tests
if __name__ == "__main__":
    client = Client()

    while True:
        msg = input("> ")
        # Peut planter si vous tapez des caractères spéciaux
        if msg == "end":
            break

        encoded_msg = msg.encode()

        if msg.startswith("Transform"):
            client.add_command(common.Command(common.MessageType.TRANSFORM, encoded_msg[9:]))
        if msg.startswith("Delete"):
            client.add_command(common.Command(common.MessageType.DELETE, encoded_msg[6:]))
        elif msg.startswith("Room"):
            client.join_room(msg[4:])

    client.disconnect()
