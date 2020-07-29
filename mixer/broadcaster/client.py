import socket
import logging
import time
from typing import Dict, Any, Mapping, Optional, List, Callable

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
            self.send_command(common.Command(common.MessageType.CLIENT_ID))
            self.send_command(common.Command(common.MessageType.LIST_CLIENTS))
            self.send_command(common.Command(common.MessageType.LIST_ROOMS))
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

    def wait(self, message_type: MessageType) -> bool:
        """
        Wait for a command of a given message type, the remaining commands are ignored.
        Usually message_type is LEAVING_ROOM.
        """
        while self.is_connected():
            received_commands = self.fetch_incoming_commands()
            if received_commands is None:
                break
            for command in received_commands:
                if command.type == message_type:
                    return True
        return False

    def send_command(self, command: common.Command):
        try:
            common.write_message(self.socket, command)
            return True
        except common.ClientDisconnectedException:
            self.handle_connection_lost()
            return False

    def join_room(self, room_name: str):
        return self.send_command(common.Command(common.MessageType.JOIN_ROOM, room_name.encode("utf8"), 0))

    def leave_room(self, room_name: str):
        self.current_room = None
        return self.send_command(common.Command(common.MessageType.LEAVE_ROOM, room_name.encode("utf8"), 0))

    def delete_room(self, room_name: str):
        return self.send_command(common.Command(common.MessageType.DELETE_ROOM, room_name.encode("utf8"), 0))

    def set_client_attributes(self, attributes: dict):
        diff = update_attributes_and_get_diff(self.current_custom_attributes, attributes)
        if diff == {}:
            return True

        return self.send_command(
            common.Command(common.MessageType.SET_CLIENT_CUSTOM_ATTRIBUTES, common.encode_json(diff), 0)
        )

    def set_room_attributes(self, room_name: str, attributes: dict):
        return self.send_command(common.make_set_room_attributes_command(room_name, attributes))

    def send_list_rooms(self):
        return self.send_command(common.Command(common.MessageType.LIST_ROOMS))

    def set_room_keep_open(self, room_name: str, value: bool):
        return self.send_command(
            common.Command(
                common.MessageType.SET_ROOM_KEEP_OPEN, common.encode_string(room_name) + common.encode_bool(value), 0
            )
        )

    def _handle_list_client(self, command: common.Command):
        clients_attributes, _ = common.decode_json(command.data, 0)
        update_named_attributes(self.clients_attributes, clients_attributes)

    def _handle_list_rooms(self, command: common.Command):
        rooms_attributes, _ = common.decode_json(command.data, 0)
        update_named_attributes(self.rooms_attributes, rooms_attributes)

    def _handle_client_id(self, command: common.Command):
        self.client_id = command.data.decode()

    def _handle_room_update(self, command: common.Command):
        rooms_attributes_update, _ = common.decode_json(command.data, 0)
        update_named_attributes(self.rooms_attributes, rooms_attributes_update)

    def _handle_room_deleted(self, command: common.Command):
        room_name, _ = common.decode_string(command.data, 0)

        if room_name not in self.rooms_attributes:
            logger.warning("Room %s deleted but no attributes in internal view.", room_name)
            return
        del self.rooms_attributes[room_name]

    def _handle_client_update(self, command: common.Command):
        clients_attributes_update, _ = common.decode_json(command.data, 0)
        update_named_attributes(self.clients_attributes, clients_attributes_update)

    def _handle_client_disconnected(self, command: common.Command):
        client_id, _ = common.decode_string(command.data, 0)

        if client_id not in self.clients_attributes:
            logger.warning("Client %s disconnected but no attributes in internal view.", client_id)
            return
        del self.clients_attributes[client_id]

    _default_command_handlers: Mapping[MessageType, Callable[[common.Command], None]] = {
        MessageType.LIST_CLIENTS: _handle_list_client,
        MessageType.LIST_ROOMS: _handle_list_rooms,
        MessageType.CLIENT_ID: _handle_client_id,
        MessageType.ROOM_UPDATE: _handle_room_update,
        MessageType.ROOM_DELETED: _handle_room_deleted,
        MessageType.CLIENT_UPDATE: _handle_client_update,
        MessageType.CLIENT_DISCONNECTED: _handle_client_disconnected,
    }

    def has_default_handler(self, message_type: MessageType):
        return message_type in self._default_command_handlers

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

            if command.type in self._default_command_handlers:
                self._default_command_handlers[command.type](self, command)

        logger.debug("Received %d commands", len(received_commands))
        return received_commands

    def fetch_outgoing_commands(self, commands_send_interval=0):
        """
        Send commands in pending_commands queue to the server.
        """
        for idx, command in enumerate(self.pending_commands):
            logger.debug("Send %s (%d / %d)", command.type, idx + 1, len(self.pending_commands))

            if not self.send_command(command):
                break

            if commands_send_interval > 0:
                time.sleep(commands_send_interval)

        self.pending_commands = []

    def fetch_commands(self, commands_send_interval=0) -> Optional[List[common.Command]]:
        self.fetch_outgoing_commands(commands_send_interval)
        return self.fetch_incoming_commands()
