import logging
import argparse
import os
import socket
import select
import sys
import threading
import time
from typing import Any, List, Mapping, Union, ValuesView

import cli_utils
import common

sys.path.append(os.getcwd())

BINDING_HOST = ''
SHUTDOWN = False

logger = logging.getLogger() if __name__ == "__main__" else logging.getLogger(__name__)


class Connection:
    """ Represent a connection with a client """

    def __init__(self, server: 'Server', socket: socket.socket, address):
        self.socket = socket
        self.address = address
        self.clientname: str = None
        self.room: 'Room' = None
        # TODO use a Queue and drop the mutex ?
        self.commands = []  # Pending commands to send to the client
        self._server = server

    def start(self):
        self.thread = threading.Thread(None, self.run)
        self.thread.start()

    def joinRoom(self, room_name: str):
        error = None
        if self.room is not None:
            error = f"Received joinRoom({room_name}) but room {self.room.name} is already joined"
        if error:
            logger.warning(error)
            self.send_error(error)
            return

        with common.mutex:
            self._server.join_room(self, room_name)

    def deleteRoom(self, room_name: str):
        error = None
        if self.room is None:
            error = f"Received deleteRoom({room_name}) but no room is joined"
        elif room_name != self.room.name:
            error = f"Received deleteRoom({room_name}) but room {self.room.name} is joined instead"
        if error:
            logger.warning(error)
            self.send_error(error)
            return

        with common.mutex:
            self._server.delete_room(room_name)

    def clearRoom(self, room_name: str):
        error = None
        if self.room is None:
            error = f"Received clearRoom({room_name}) but no room is joined"
        elif room_name != self.room.name:
            error = f"Received clearRoom({room_name}) but room {self.room.name} is joined instead"
        if error:
            logger.warning(error)
            self.send_error(error)
            return

        with common.mutex:
            room = self._server.get_room(room_name)
            if room is not None:
                room.clear()

    def sendListRooms(self):
        data = common.encodeStringArray(self._server.rooms_names())
        command = common.Command(common.MessageType.LIST_ROOMS, data)
        with common.mutex:
            self.commands.append(command)

    def sendListRoomClients(self, room_name: str = None, client_ids: Union[Mapping, List[Mapping]] = None):
        logger.debug("sendListRoomClients")
        with common.mutex:
            # ensure we use only one since each message ovewrites the previous one
            # on the client
            assert bool(room_name is not None) != bool(client_ids is not None)
            command = None

            if client_ids is not None:
                client_ids = client_ids if isinstance(client_ids, list) else [client_ids]
                ids = common.encodeJson(client_ids)
                command = common.Command(common.MessageType.LIST_ROOM_CLIENTS, ids)

            if room_name is not None:
                room = self._server.get_room(room_name)
                if room is not None:
                    ids = common.encodeJson(room.client_ids())
                    command = common.Command(common.MessageType.LIST_ROOM_CLIENTS, ids)
                else:
                    command = common.Command(common.MessageType.SEND_ERROR,
                                             common.encodeString(f'No room named {room_name}.'))
            if command:
                self.commands.append(command)

    def sendListClients(self):
        """
        Joined clients for all rooms
        """
        with common.mutex:
            clients = []
            for room in self._server.rooms():
                clients.extend(room.client_ids())
            command = common.Command(common.MessageType.LIST_CLIENTS, common.encodeJson(clients))
            self.commands.append(command)

    def sendListAllClients(self):
        ids = self._server.client_ids()
        self.send_client_ids(ids)

    def send_client_ids(self, client_ids):
        with common.mutex:
            command = common.Command(common.MessageType.LIST_ALL_CLIENTS, common.encodeJson(client_ids))
            self.commands.append(command)

    def leaveRoom(self, room_name: str):
        error = None
        if self.room is None:
            error = f"Received leaveRoom({room_name}) but no room is joined"
        elif room_name != self.room.name:
            error = f"Received leaveRoom({room_name}) but room {self.room.name} is joined instead"
        if error:
            logger.warning(error)
            self.send_error(error)
            return

        with common.mutex:
            self._server.leave_room(self, room_name)

    def client_id(self) -> Mapping[str, str]:
        return {'ip': self.address[0],
                'port': self.address[1],
                'name': self.clientname,
                'room': self.room.name if self.room is not None else None}

    def setClientName(self, name):
        self.clientname = name
        self._server.broadcast_user_list()

    def send_error(self, s: str):
        command = common.Command(common.MessageType.SEND_ERROR, common.encodeString(s))
        with common.mutex:
            self.commands.append(command)

    def onClientDisconnected(self):
        self._server.broadcast_user_list()

    def run(self):
        global SHUTDOWN
        while not SHUTDOWN:
            try:
                command = common.readMessage(self.socket)
            except common.ClientDisconnectedException:
                break

            if command is not None:
                logger.debug("Received from %s:%s - %s", self.address[0], self.address[1], command.type)

                if command.type == common.MessageType.JOIN_ROOM:
                    self.joinRoom(command.data.decode())

                elif command.type == common.MessageType.LEAVE_ROOM:
                    self.leaveRoom(command.data.decode())

                elif command.type == common.MessageType.LIST_ROOMS:
                    self.sendListRooms()

                elif command.type == common.MessageType.DELETE_ROOM:
                    self.deleteRoom(command.data.decode())

                elif command.type == common.MessageType.CLEAR_ROOM:
                    self.clearRoom(command.data.decode())

                elif command.type == common.MessageType.LIST_ROOM_CLIENTS:
                    self.sendListRoomClients(room_name=command.data.decode())

                elif command.type == common.MessageType.LIST_ALL_CLIENTS:
                    self.sendListAllClients()

                elif command.type == common.MessageType.LIST_CLIENTS:
                    self.sendListClients()

                elif command.type == common.MessageType.SET_CLIENT_NAME:
                    self.setClientName(command.data.decode())

                # Other commands
                elif command.type.value > common.MessageType.COMMAND.value:
                    if self.room is not None:
                        self.room.addCommand(command, self)
                    else:
                        logger.error("COMMAND received but no room was joined")

            try:
                if len(self.commands) > 0:
                    with common.mutex:
                        for command in self.commands:
                            logger.debug("Sending to %s:%s - %s", self.address[0], self.address[1], command.type)
                            common.writeMessage(self.socket, command)
                        self.commands = []
            except common.ClientDisconnectedException:
                break

        self.close()
        self.onClientDisconnected()

    def addCommand(self, command):
        self.commands.append(command)

    def close(self):
        # called on disconnection
        if self.room is not None:
            self.room.removeClient(self)
        else:
            self._server.remove_unjoined_client(self)

        try:
            self.socket.close()
        except Exception:
            pass
        logger.info("%s closed",  self.address)


class Room:
    def __init__(self, server: 'Server', roomName: str):
        self.name = roomName
        self._connections: List['Connection'] = []
        self.commands = []
        self._server: 'Server' = server

    def client_count(self):
        return len(self._connections)

    def addClient(self, connection: Connection):
        logger.info(f"Add Client {connection.address} to Room {self.name}")
        self._connections.append(connection)
        connection.room = self
        if len(self._connections) == 1:
            command = common.Command(common.MessageType.CONTENT)
            connection.addCommand(command)
        else:
            command = common.Command(common.MessageType.CLEAR_CONTENT)
            connection.addCommand(command)

            for command in self.commands:
                connection.addCommand(command)

        self._server.broadcast_user_list()

    def broadcast_user_list(self):
        for connection in self._connections:
            connection.send_client_ids(client_ids=self.client_ids())

    def client_ids(self):
        if not self._connections:
            return None
        return [c.client_id() for c in self._connections]

    def close(self):
        command = common.Command(common.MessageType.LEAVE_ROOM, common.encodeString(self.name))
        self.addCommand(command, None)
        self._connections = []
        self._server.delete_room(self.name)
        self.broadcast_user_list()

    def clear(self):
        self.commands = []

    def removeClient(self, connection: Connection):
        logger.info("Remove Client % s from Room % s", connection.address, self.name)
        self._connections.remove(connection)
        connection.room = None
        if len(self._connections) == 0:
            self._server.delete_room(self.name)
            logger.info("No more clients in room \"%s\". Room deleted", self.name)
        else:
            logger.info(f'Connections left : {len(self._connections)}.')
            self.broadcast_user_list()

    def send_client_ids(self, client_ids):
        for c in self._connections:
            c.send_client_ids(client_ids)

    def mergeCommands(self, command):
        commandType = command.type
        if commandType.value > common.MessageType.OPTIMIZED_COMMANDS.value:
            commandPath = common.decodeString(command.data, 0)[0]
            if len(self.commands) > 0:
                storedCommand = self.commands[-1]
                if commandType == storedCommand.type and commandPath == common.decodeString(storedCommand.data, 0)[0]:
                    self.commands.pop()
        self.commands.append(command)

    def addCommand(self, command, sender):
        with common.mutex:
            self.mergeCommands(command)
            for connection in self._connections:
                if connection != sender:
                    connection.addCommand(command)


class Server:
    def __init__(self):
        Address = (str, str)
        self._rooms: Mapping[str, Room] = {}
        # Connections not joined to any room
        self._unjoined_connections: Mapping[Address, Connection] = {}
        self._shutdown = False

    def shutdown(self):
        # mostly for tests
        self._shutdown = True

    def client_count(self):
        """
        Returns (numver of joined connections, number of unjoined connections)
        """
        joined = 0
        for room in self._rooms.values():
            joined += room.client_count()
        unjoined = len(self._unjoined_connections)
        return (joined, unjoined)

    def remove_unjoined_client(self, connection: Connection):
        with common.mutex:
            logger.debug("Server : removing unjoined client %s", connection.address)
            del self._unjoined_connections[connection.address]

    def get_room(self, room_name: str) -> Room:
        return self._rooms.get(room_name)

    def add_room(self, room_name: str) -> Room:
        with common.mutex:
            if room_name in self._rooms:
                raise ValueError(f"add_room: room with name {room_name} already exists")
            room = Room(self, room_name)
            self._rooms[room_name] = room
            logger.info(f'Room {room_name} added')
            self.broadcast_user_list()
            return room

    def delete_room(self, room_name: str):
        with common.mutex:
            if room_name in self._rooms:
                del self._rooms[room_name]
                logger.info(f'Room {room_name} deleted')
            self.broadcast_user_list()

    def join_room(self, connection: Connection, room_name: str):
        with common.mutex:
            assert connection.room is None
            room = self.get_room(room_name)
            if room is None:
                logger.info(f"Room {room_name} does not exist. Creating it.")
                room = self.add_room(room_name)

            peer = connection.address
            if peer in self._unjoined_connections:
                logger.debug("Reusing connection %s", peer)
                del self._unjoined_connections[peer]

            room.addClient(connection)
            self.broadcast_user_list()

    def leave_room(self, connection: Connection, room_name: str):
        with common.mutex:
            room = self.get_room(room_name)
            if room is None:
                raise ValueError(f"Room not found {room_name})")
            room.removeClient(connection)
            peer = connection.address
            assert peer not in self._unjoined_connections
            self._unjoined_connections[peer] = connection
            self.broadcast_user_list()

    def rooms_names(self) -> List[str]:
        return self._rooms.keys()

    def rooms(self) -> ValuesView[Room]:
        return self._rooms.values()

    def client_ids(self) -> List[Mapping]:
        with common.mutex:
            # gather all client ids
            client_ids = []
            for connection in self._unjoined_connections.values():
                client_ids.append(connection.client_id())
            for room in self._rooms.values():
                ids = room.client_ids()
                if ids is not None:
                    client_ids.extend(ids)
            return client_ids

    def broadcast_user_list(self):
        """
        Broadcast the list of all joined and unjoined clients to all
        joined and unjoined clients.

        This is called for every connection/join/clinet name change
        """
        with common.mutex:
            client_ids = self.client_ids()

            # broadcast
            for connection in self._unjoined_connections.values():
                connection.send_client_ids(client_ids=client_ids)
            for room in self._rooms.values():
                room.send_client_ids(client_ids=client_ids)

    def run(self):
        global SHUTDOWN
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((BINDING_HOST, common.DEFAULT_PORT))
        sock.setblocking(0)
        sock.listen(1000)

        logger.info("Listening on port % s", common.DEFAULT_PORT)
        while not self._shutdown:
            try:
                timeout = 0.1  # Check for a new client every 10th of a second
                readable, _, _ = select.select([sock], [], [], timeout)
                if len(readable) > 0:
                    client_socket, client_address = sock.accept()
                    connection = Connection(self, client_socket, client_address)
                    assert connection.address not in self._unjoined_connections
                    self._unjoined_connections[connection.address] = connection
                    connection.start()
                    logger.info(f"New connection from {client_address}")

                    # Let the new client know the room and user lists
                    self.broadcast_user_list()
            except KeyboardInterrupt:
                self.shutdown()

        logger.info("Shutting down server")
        SHUTDOWN = True
        sock.close()


def main():
    args, args_parser = parse_cli_args()
    cli_utils.init_logging(args)

    server = Server()
    server.run()


def parse_cli_args():
    parser = argparse.ArgumentParser(description='Start broadcasting server for DCC Sync')
    cli_utils.add_logging_cli_args(parser)
    return parser.parse_args(), parser


if __name__ == '__main__':
    main()
