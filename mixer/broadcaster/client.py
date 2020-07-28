import socket
import logging
import time
from typing import Dict, Any, Mapping, Optional, List

import mixer.broadcaster.common as common
from mixer.broadcaster.common import MessageType
from mixer.broadcaster.common import update_attributes_and_get_diff, update_named_attributes

logger = logging.getLogger() if __name__ == "__main__" else logging.getLogger(__name__)


class Client:
    """
    The client class is responsible for:
    - handling the connection with the server
    - receiving packet of bytes to convert them to commands
    - send commands
    - maintain an updated view of clients and room states from server's inputs
    """

    def __init__(self, host=common.DEFAULT_HOST, port=common.DEFAULT_PORT):
        self.host = host
        self.port = port
        self.pending_commands: List[common.Command] = []
        self.socket = None

        self.client_id: Optional[str] = None  # Will be filled with a unique string identifying this client
        self.current_custom_attributes: Dict[str, Any] = {}
        self.clients_attributes: Dict[str, Dict[str, Any]] = {}
        self.rooms_attributes: Dict[str, Dict[str, Any]] = {}
        self.current_room: Optional[str] = None

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
            self.safe_write_message(common.Command(common.MessageType.LIST_CLIENTS))
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

    def add_command(self, command: common.Command):
        self.pending_commands.append(command)

    def handle_connection_lost(self):
        logger.info("Connection lost for %s:%s", self.host, self.port)
        # Set socket to None before putting CONNECTION_LIST message to avoid sending/reading new messages
        self.socket = None

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
        self.current_room = None
        return self.safe_write_message(common.Command(common.MessageType.LEAVE_ROOM, room_name.encode("utf8"), 0))

    def wait_for(self, message_type: MessageType) -> Optional[List[common.Command]]:
        """
        Wait for a specific message type to be received and returns the list of all commands received during that time.
        Returns None if the client was disconnected before.
        """
        all_received_commands: List[common.Command] = []
        while self.is_connected():
            self.fetch_outgoing_commands()
            received_commands = self.fetch_incoming_commands()
            if received_commands is None:
                break
            all_received_commands += received_commands
            for command in received_commands:
                if command.type == message_type:
                    return all_received_commands

        return None

    def delete_room(self, room_name):
        return self.safe_write_message(common.Command(common.MessageType.DELETE_ROOM, room_name.encode("utf8"), 0))

    def set_client_attributes(self, attributes: dict):
        diff = update_attributes_and_get_diff(self.current_custom_attributes, attributes)
        if diff == {}:
            return True

        return self.safe_write_message(
            common.Command(common.MessageType.SET_CLIENT_CUSTOM_ATTRIBUTES, common.encode_json(diff), 0)
        )

    def set_room_attributes(self, room_name: str, attributes: dict):
        return self.safe_write_message(common.make_set_room_attributes_command(room_name, attributes))

    def send_list_rooms(self):
        return self.safe_write_message(common.Command(common.MessageType.LIST_ROOMS))

    def set_room_keep_open(self, room_name: str, value: bool):
        return self.safe_write_message(
            common.Command(
                common.MessageType.SET_ROOM_KEEP_OPEN, common.encode_string(room_name) + common.encode_bool(value), 0
            )
        )

    def fetch_incoming_commands(self) -> Optional[List[common.Command]]:
        """
        Gather incoming commands from the socket and return them as a list.
        """
        received_commands: List[common.Command] = []
        while True:
            try:
                command = common.read_message(self.socket)
            except common.ClientDisconnectedException:
                self.handle_connection_lost()
                return None

            if command is None:
                break

            logger.debug("Receive %s", command.type)
            received_commands.append(command)

        logger.debug("Received %d commands", len(received_commands))
        return received_commands

    def fetch_outgoing_commands(self, commands_send_interval=0):
        """
        Send commands in pending_commands queue to the server.
        """
        for idx, command in enumerate(self.pending_commands):
            logger.debug("Send %s (%d / %d)", command.type, idx + 1, len(self.pending_commands))

            if not self.safe_write_message(command):
                break

            if commands_send_interval > 0:
                time.sleep(commands_send_interval)

        self.pending_commands = []

    def update_clients_attributes(self, clients_attributes_update: Mapping[str, Mapping[str, Any]]):
        update_named_attributes(self.clients_attributes, clients_attributes_update)

    def handle_client_disconnected(self, client_id: str):
        if client_id not in self.clients_attributes:
            logger.warning("Client %s disconnected but no attributes in internal view.", client_id)
            return
        del self.clients_attributes[client_id]

    def update_rooms_attributes(self, rooms_attributes_update: Mapping[str, Mapping[str, Any]]):
        update_named_attributes(self.rooms_attributes, rooms_attributes_update)

    def handle_room_deleted(self, room_name: str):
        if room_name not in self.rooms_attributes:
            logger.warning("Room %s deleted but no attributes in internal view.", room_name)
            return
        del self.rooms_attributes[room_name]
