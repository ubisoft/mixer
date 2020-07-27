from __future__ import annotations

import logging
import argparse
import select
import threading
import socket
import queue
from typing import List, Mapping, Dict, Optional, Any

from mixer.broadcaster.cli_utils import init_logging, add_logging_cli_args
import mixer.broadcaster.common as common
from mixer.broadcaster.common import update_dict_and_get_diff

SHUTDOWN = False

logger = logging.getLogger() if __name__ == "__main__" else logging.getLogger(__name__)


class Connection:
    """ Represent a connection with a client """

    def __init__(self, server: Server, sock: socket.socket, address):
        self.socket: socket.socket = sock
        self.address = address
        self.room: Optional[Room] = None

        self.unique_id = f"{address[0]}:{address[1]}"

        self.custom_attributes: Dict[str, Any] = {}  # custom attributes are used between clients, but not by the server

        self._command_queue: queue.Queue = queue.Queue()  # Pending commands to send to the client
        self._server = server

        self.thread: threading.Thread = threading.Thread(None, self.run)

    def start(self):
        self.thread.start()

    def has_room(self):
        return self.room is not None

    def join_room(self, room_name: str):
        error = None
        if self.room is not None:
            error = f"Received join_room({room_name}) but room {self.room.name} is already joined"

        if error:
            logger.warning(error)
            self.send_error(error)
            return

        self._server.join_room(self, room_name)

    def leave_room(self):
        error = None
        if self.room is None:
            error = f"Received leave_room but no room is joined"

        if error:
            logger.warning(error)
            self.send_error(error)
            return

        self._server.leave_room(self)

    def client_attributes(self) -> Dict[str, Any]:
        return {
            **self.custom_attributes,
            common.ClientAttributes.ID: f"{self.unique_id}",
            common.ClientAttributes.IP: self.address[0],
            common.ClientAttributes.PORT: self.address[1],
            common.ClientAttributes.ROOM: self.room.name if self.room is not None else None,
        }

    def set_custom_attributes(self, custom_attributes: Mapping[str, Any]):
        diff = update_dict_and_get_diff(self.custom_attributes, custom_attributes)
        self._server.broadcast_client_update(self, diff)

    def send_error(self, s: str):
        logger.warning("Sending error %s", s)
        self.send_command(common.Command(common.MessageType.SEND_ERROR, common.encode_string(s)))

    def set_room_joinable(self):
        if self.room is None:
            self.send_error("Unjoined client trying to set room joinable")
            return
        if self.room.creator_client_id != self.unique_id:
            self.send_error(
                f"Client {self.unique_id} trying to set joinbale room {self.room.name} created by {self.room.creator_client_id}"
            )
            return
        if not self.room.joinable:
            self.room.joinable = True
            self._server.broadcast_room_update(self.room, {common.RoomAttributes.JOINABLE: True})

    def run(self):
        def _join_room(command: common.Command):
            self.join_room(command.data.decode())

        def _leave_room(command: common.Command):
            _ = command.data.decode()  # todo remove room_name from protocol
            self.leave_room()

        def _list_rooms(command: common.Command):
            self.send_command(self._server.get_list_rooms_command())

        def _delete_room(command: common.Command):
            self._server.delete_room(command.data.decode())

        def _set_client_name(command: common.Command):
            self.set_custom_attributes({common.ClientAttributes.USERNAME: command.data.decode()})

        def _list_clients(command: common.Command):
            self.send_command(self._server.get_list_clients_command())

        def _set_client_custom_attributes(command: common.Command):
            self.set_custom_attributes(common.decode_json(command.data, 0)[0])

        def _set_room_custom_attributes(command: common.Command):
            room_name, offset = common.decode_string(command.data, 0)
            custom_attributes, _ = common.decode_json(command.data, offset)
            self._server.set_room_custom_attributes(room_name, custom_attributes)

        def _set_room_keepopen(command: common.Command):
            room_name, offset = common.decode_string(command.data, 0)
            value, _ = common.decode_bool(command.data, offset)
            self._server.set_room_keep_open(room_name, value)

        def _client_id(command: common.Command):
            self.send_command(
                common.Command(common.MessageType.CLIENT_ID, f"{self.address[0]}:{self.address[1]}".encode("utf8"))
            )

        def _content(command: common.Command):
            self.set_room_joinable()

        command_handlers = {
            common.MessageType.JOIN_ROOM: _join_room,
            common.MessageType.LEAVE_ROOM: _leave_room,
            common.MessageType.LIST_ROOMS: _list_rooms,
            common.MessageType.DELETE_ROOM: _delete_room,
            common.MessageType.SET_ROOM_CUSTOM_ATTRIBUTES: _set_room_custom_attributes,
            common.MessageType.SET_ROOM_KEEP_OPEN: _set_room_keepopen,
            common.MessageType.LIST_CLIENTS: _list_clients,
            common.MessageType.SET_CLIENT_NAME: _set_client_name,
            common.MessageType.SET_CLIENT_CUSTOM_ATTRIBUTES: _set_client_custom_attributes,
            common.MessageType.CLIENT_ID: _client_id,
            common.MessageType.CONTENT: _content,
        }

        global SHUTDOWN
        while not SHUTDOWN:
            try:
                command = common.read_message(self.socket)
            except common.ClientDisconnectedException:
                break

            if command is not None:
                logger.debug("Received from %s:%s - %s", self.address[0], self.address[1], command.type)

                if command.type in command_handlers:
                    command_handlers[command.type](command)

                elif command.type.value > common.MessageType.COMMAND.value:
                    if self.room is not None:
                        self.room.add_command(command, self)
                    else:
                        logger.warning(
                            "%s:%s - %s received but no room was joined",
                            self.address[0],
                            self.address[1],
                            command.type.value,
                        )

                else:
                    logger.error("Command %s received but no handler for it on server", command.type)

            try:
                while True:
                    try:
                        command = self._command_queue.get_nowait()
                    except queue.Empty:
                        break

                    logger.debug("Sending to %s:%s - %s", self.address[0], self.address[1], command.type)
                    common.write_message(self.socket, command)

                    self._command_queue.task_done()
            except common.ClientDisconnectedException:
                break

        self._server.handle_client_disconnect(self)

    def add_command(self, command: common.Command):
        """
        Add command to be consumed later. Meant to be used by other threads.
        """
        self._command_queue.put(command)

    def send_command(self, command: common.Command):
        """
        Directly send a command to the socket. Meant to be used by this thread.
        """
        assert threading.current_thread() is self.thread
        common.write_message(self.socket, command)


class Room:
    """
    Room class is responsible for:
    - handling its list of clients (as Connection instances)
    - keep a list of commands, to be dispatched to new clients
    - dispatch added commands to clients already in the room
    """

    def __init__(self, server: Server, room_name: str, creator_client_id: str):
        self.name = room_name
        self.keep_open = False  # Should the room remain open when no more clients are inside ?
        self.byte_size = 0
        self.joinable = False  # A room becomes joinable when its first client has send all the initial content

        self.custom_attributes: Dict[str, Any] = {}  # custom attributes are used between clients, but not by the server

        self._commands: List[common.Command] = []

        self._commands_mutex: threading.RLock = threading.RLock()
        self._connections: List[Connection] = []

        self.creator_client_id = creator_client_id

    def client_count(self):
        return len(self._connections)

    def command_count(self):
        return len(self._commands)

    def add_client(self, connection: Connection):
        logger.info(f"Add Client {connection.address} to Room {self.name}")
        self._connections.append(connection)

    def remove_client(self, connection: Connection):
        logger.info("Remove Client % s from Room % s", connection.address, self.name)
        self._connections.remove(connection)

    def attributes_dict(self):
        return {
            **self.custom_attributes,
            common.RoomAttributes.KEEP_OPEN: self.keep_open,
            common.RoomAttributes.COMMAND_COUNT: self.command_count(),
            common.RoomAttributes.BYTE_SIZE: self.byte_size,
            common.RoomAttributes.JOINABLE: self.joinable,
        }

    def broadcast_commands(self, connection: Connection):
        with self._commands_mutex:
            for command in self._commands:
                connection.add_command(command)

    def add_command(self, command, sender: Connection):
        def merge_command():
            """
            Add the command to the room list, possibly merge with the previous command.
            """
            command_type = command.type
            if command_type.value > common.MessageType.OPTIMIZED_COMMANDS.value:
                command_path = common.decode_string(command.data, 0)[0]
                if self.command_count() > 0:
                    stored_command = self._commands[-1]
                    if (
                        command_type == stored_command.type
                        and command_path == common.decode_string(stored_command.data, 0)[0]
                    ):
                        self._commands.pop()
                        self.byte_size -= stored_command.byte_size()
            self._commands.append(command)
            self.byte_size += command.byte_size()

        with self._commands_mutex:
            current_byte_size = self.byte_size
            current_command_count = self.command_count()
            merge_command()

            room_update = {}
            if self.byte_size != current_byte_size:
                room_update[common.RoomAttributes.BYTE_SIZE] = self.byte_size
            if current_command_count != self.command_count():
                room_update[common.RoomAttributes.COMMAND_COUNT] = self.command_count()

            sender._server.broadcast_room_update(self, room_update)

            for connection in self._connections:
                if connection != sender:
                    connection.add_command(command)


class Server:
    def __init__(self):
        self._rooms: Dict[str, Room] = {}
        self._connections: Dict[str, Connection] = {}
        self._mutex = threading.RLock()

    def delete_room(self, room_name: str):
        with self._mutex:
            if room_name not in self._rooms:
                logger.warning("Room %s does not exist.", room_name)
                return
            if self._rooms[room_name].client_count() > 0:
                logger.warning("Room %s is not empty.", room_name)
                return

            del self._rooms[room_name]
            logger.info(f"Room {room_name} deleted")

            self.broadcast_to_all_clients(
                common.Command(common.MessageType.ROOM_DELETED, common.encode_string(room_name))
            )

    def _create_room(self, connection: Connection, room_name: str):
        logger.info(f"Room {room_name} does not exist. Creating it.")
        room = Room(self, room_name, connection.unique_id)
        room.add_client(connection)
        connection.room = room
        connection.send_command(common.Command(common.MessageType.CONTENT))

        self._rooms[room_name] = room
        logger.info(f"Room {room_name} added")

        self.broadcast_room_update(room, room.attributes_dict())  # Inform new room
        self.broadcast_client_update(connection, {common.ClientAttributes.ROOM: connection.room.name})

    def join_room(self, connection: Connection, room_name: str):
        assert not connection.has_room()

        with self._mutex:
            room = self._rooms.get(room_name)
            if room is None:
                self._create_room(connection, room_name)
                return

            if not room.joinable:
                logging.error("Room %s not joinable yet.", room_name)
                return

            # Do this before releasing the global mutex
            # Ensure the room will not be deleted because it now has at least one client
            room.add_client(connection)
            connection.room = room
            connection.send_command(common.Command(common.MessageType.CLEAR_CONTENT))

        try:
            room.broadcast_commands(connection)
            self.broadcast_client_update(connection, {common.ClientAttributes.ROOM: connection.room.name})
        except Exception as e:
            connection.room = None
            raise e

    def leave_room(self, connection: Connection):
        assert connection.room is not None
        with self._mutex:
            room = self._rooms.get(connection.room.name)
            if room is None:
                raise ValueError(f"Room not found {connection.room.name})")
            room.remove_client(connection)
            connection.room = None
            connection.send_command(common.Command(common.MessageType.LEAVE_ROOM))
            self.broadcast_client_update(connection, {common.ClientAttributes.ROOM: None})

            if room.client_count() == 0 and not room.keep_open:
                logger.info('No more clients in room "%s" and not keep_open', room.name)
                self.delete_room(room.name)
            else:
                logger.info(f"Connections left in room {room.name}: {room.client_count()}.")

    def broadcast_to_all_clients(self, command: common.Command):
        with self._mutex:
            for connection in self._connections.values():
                connection.add_command(command)

    def broadcast_client_update(self, connection: Connection, attributes: Dict[str, Any]):
        if attributes == {}:
            return

        self.broadcast_to_all_clients(
            common.Command(common.MessageType.CLIENT_UPDATE, common.encode_json({connection.unique_id: attributes}))
        )

    def broadcast_room_update(self, room: Room, attributes: Dict[str, Any]):
        if attributes == {}:
            return

        self.broadcast_to_all_clients(
            common.Command(common.MessageType.ROOM_UPDATE, common.encode_json({room.name: attributes}),)
        )

    def set_room_custom_attributes(self, room_name: str, custom_attributes: Mapping[str, Any]):
        with self._mutex:
            if room_name not in self._rooms:
                logger.warning("Room %s does not exist.", room_name)
                return

            diff = update_dict_and_get_diff(self._rooms[room_name].custom_attributes, custom_attributes)
            self.broadcast_room_update(self._rooms[room_name], diff)

    def set_room_keep_open(self, room_name: str, value: bool):
        with self._mutex:
            if room_name not in self._rooms:
                logger.warning("Room %s does not exist.", room_name)
                return
            room = self._rooms[room_name]
            if room.keep_open != value:
                room.keep_open = value
                self.broadcast_room_update(room, {common.RoomAttributes.KEEP_OPEN: room.keep_open})

    def get_list_rooms_command(self) -> common.Command:
        with self._mutex:
            result_dict = {room_name: value.attributes_dict() for room_name, value in self._rooms.items()}
            return common.Command(common.MessageType.LIST_ROOMS, common.encode_json(result_dict))

    def get_list_clients_command(self) -> common.Command:
        with self._mutex:
            result_dict = {cid: c.client_attributes() for cid, c in self._connections.items()}
            return common.Command(common.MessageType.LIST_CLIENTS, common.encode_json(result_dict))

    def handle_client_disconnect(self, connection: Connection):
        if connection.room is not None:
            self.leave_room(connection)

        with self._mutex:
            del self._connections[connection.unique_id]

        try:
            connection.socket.close()
        except Exception as e:
            logger.warning(e)
        logger.info("%s closed", connection.address)

        self.broadcast_to_all_clients(
            common.Command(common.MessageType.CLIENT_DISCONNECTED, common.encode_string(connection.unique_id))
        )

    def run(self, port):
        global SHUTDOWN
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        binding_host = ""
        sock.bind((binding_host, port))
        sock.setblocking(0)
        sock.listen(1000)

        logger.info("Listening on port % s", port)
        while True:
            try:
                timeout = 0.1  # Check for a new client every 10th of a second
                readable, _, _ = select.select([sock], [], [], timeout)
                if len(readable) > 0:
                    client_socket, client_address = sock.accept()
                    connection = Connection(self, client_socket, client_address)
                    with self._mutex:
                        self._connections[connection.unique_id] = connection
                    connection.start()
                    logger.info(f"New connection from {client_address}")
                    self.broadcast_client_update(connection, connection.client_attributes())
            except KeyboardInterrupt:
                break

        logger.info("Shutting down server")
        SHUTDOWN = True
        sock.close()


def main():
    args, args_parser = parse_cli_args()
    init_logging(args)

    server = Server()
    server.run(args.port)


def parse_cli_args():
    parser = argparse.ArgumentParser(description="Start broadcasting server for Mixer")
    add_logging_cli_args(parser)
    parser.add_argument("--port", type=int, default=common.DEFAULT_PORT)
    return parser.parse_args(), parser


if __name__ == "__main__":
    main()
