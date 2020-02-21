import common
# from broadcaster import common
import socket
import threading
import logging
import time

from typing import List, ValuesView, Mapping, Any

import os
import sys
sys.path.append(os.getcwd())

logging.basicConfig(level=logging.INFO)

TIMEOUT = 60.0
BINDING_HOST = ''

SHUTDOWN = False


class Connection:
    """ Represent a connection with a client """

    def __init__(self, server: 'Server', socket: socket.socket, address):
        self.socket = socket
        self.address = address
        self.clientname: str = None
        self.room: 'Room' = None
        self.commands = []  # Pending commands to send to the client
        self._server = server

    def start(self):
        self.thread = threading.Thread(None, self.run)
        self.thread.start()

    def client_id(self) -> Mapping[str, str]:
        return {'ip': self.address[0], 'port': self.address[1], 'name': self.clientname,
                'room': self.room.name if self.room is not None else None}

    def setClientName(self, name):
        self.clientname = name
        self._server.broadcast_user_list()

    def joinRoom(self, room_name: str):
        assert self.room is None
        with common.mutex:
            self.room = self._server.join_room(self, room_name)

    def leaveRoom(self, room_name: str):
        assert room_name == self.room.name
        with common.mutex:
            self._server.leave_room(self, room_name)
            self.room = None

    def deleteRoom(self, room_name: str):
        assert room_name == self.room.name
        with common.mutex:
            self._server.delete_room(room_name)

    def clearRoom(self, room_name: str):
        assert room_name == self.room.name
        with common.mutex:
            room = self._server.get_room(room_name)
            if room is not None:
                room.clear()

    def sendListRooms(self):
        data = common.encodeStringArray(self._server.rooms_names())
        command = common.Command(common.MessageType.LIST_ROOMS, data)
        with common.mutex:
            self.commands.append(command)

    def sendListRoomClients(self, room_name: str):
        with common.mutex:
            if room_name is None:
                ids = common.encodeJson([self.client_id()])
                command = common.Command(common.MessageType.LIST_ROOM_CLIENTS, ids)
            else:
                room = self._server.get_room(room_name)
                if room is not None:
                    ids = common.encodeJson(room.client_ids())
                    command = common.Command(common.MessageType.LIST_ROOM_CLIENTS, ids)
                else:
                    command = common.Command(common.MessageType.SEND_ERROR,
                                             common.encodeString(f'No room named {room_name}.'))
            self.commands.append(command)

    def sendListClients(self):
        with common.mutex:
            clients = []
            for room in self._server.rooms():
                clients += room.client_ids()
            command = common.Command(common.MessageType.LIST_CLIENTS, common.encodeJson(clients))
            self.commands.append(command)

    def run(self):
        global SHUTDOWN
        while not SHUTDOWN:
            try:
                command = common.readMessage(self.socket)
            except common.ClientDisconnectedException:
                break

            if command is not None:
                logging.info("client % s: % s: % s received", self.address[0], self.address[1], command.type)

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
                    self.sendListRoomClients(command.data.decode())

                elif command.type == common.MessageType.LIST_CLIENTS:
                    self.sendListClients()

                elif command.type == common.MessageType.SET_CLIENT_NAME:
                    self.setClientName(command.data.decode())

                # Other commands
                elif command.type.value > common.MessageType.COMMAND.value:
                    if self.room is not None:
                        self.room.addCommand(command, self)
                    else:
                        logging.error("COMMAND received but no room was joined")

            if len(self.commands) > 0:
                with common.mutex:
                    for command in self.commands:
                        common.writeMessage(self.socket, command)
                    self.commands = []

        self.close()

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
        logging.info("%s closed",  self.address)


class Room:
    def __init__(self, server: 'Server', roomName: str):
        self.name = roomName
        self._connections: List['Connection'] = []
        self.commands = []
        self._server: 'Server' = server

    def client_count(self):
        return len(self._connections)

    def addClient(self, connection: Connection):
        logging.info(f"Add Client {connection.address} to Room {self.name}")
        self._connections.append(connection)
        if len(self._connections) == 1:
            command = common.Command(common.MessageType.CONTENT)
            connection.addCommand(command)
        else:
            command = common.Command(common.MessageType.CLEAR_CONTENT)
            connection.addCommand(command)

            for command in self.commands:
                connection.addCommand(command)

        # broadcast user list
        # self._server.broadcast_user_list()
        self.broadcast_user_list()

    def broadcast_user_list(self):
        for connection in self._connections:
            connection.sendListRoomClients(self.name)

    def client_ids(self):
        return [c.client_id() for c in self._connections]

    def close(self):
        command = common.Command(common.MessageType.LEAVE_ROOM, common.encodeString(self.name))
        self.addCommand(command, None)
        # self.broadcast_user_list()
        self._connections = []
        self._server.delete_room(self.name)

    def clear(self):
        self.commands = []

    def removeClient(self, connection: Connection):
        logging.info("Remove Client % s from Room % s", connection.address, self.name)
        self._connections.remove(connection)
        if len(self._connections) == 0:
            self._server.delete_room(self.name)
            logging.info("No more clients in room \"%s\". Room deleted", self.name)
        else:
            logging.info(f'Connections left : "{len(self._connections)}".')
            self.broadcast_user_list()

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
        joined = 0
        for room in self._rooms.values():
            joined += room.client_count()
        unjoined = len(self._unjoined_connections)
        return (joined, unjoined)

    def remove_unjoined_client(self, connection: Connection):
        logging.debug("Server : removing unjoined client %s", connection.address)
        del self._unjoined_connections[connection.address]

    def get_room(self, room_name: str) -> Room:
        return self._rooms.get(room_name)

    def add_room(self, room_name: str) -> Room:
        if room_name in self._rooms:
            raise ValueError(f"add_room: room with name {room_name} already exists")
        room = Room(self, room_name)
        self._rooms[room_name] = room
        logging.info(f'Room {room_name} added')
        self.broadcast_user_list()
        return room

    def delete_room(self, room_name: str):
        with common.mutex:
            if room_name in self._rooms:
                del self._rooms[room_name]
                logging.info(f'Room {room_name} deleted')
        self.broadcast_user_list()

    def join_room(self, connection: Connection, room_name: str) -> Room:
        assert connection.room is None
        room = self.get_room(room_name)
        if room is None:
            logging.info(f"Room {room_name} does not exist. Creating it.")
            room = self.add_room(room_name)

        peer = connection.address
        if peer in self._unjoined_connections:
            logging.debug("Reusing connection %s", peer)
            del self._unjoined_connections[peer]

        room.addClient(connection)
        self.broadcast_user_list()
        return room

    def leave_room(self, connection: Connection, room_name: str):
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

    def broadcast_user_list(self):
        with common.mutex:
            for connection in self._unjoined_connections.values():
                if len(self._rooms) == 0:
                    connection.sendListRoomClients(None)
                else:
                    for room_name in self._rooms.keys():
                        connection.sendListRoomClients(room_name)
            for room in self._rooms.values():
                room.broadcast_user_list()

    def run(self):
        global SHUTDOWN
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind((BINDING_HOST, common.DEFAULT_PORT))
        sock.setblocking(0)
        sock.listen(1000)

        logging.info("Listening on port % s", common.DEFAULT_PORT)
        while not self._shutdown:
            try:
                (conn, remote_address) = sock.accept()
                connection = Connection(self, conn, remote_address)
                assert connection.address not in self._unjoined_connections
                self._unjoined_connections[connection.address] = connection
                connection.start()
                logging.info(f"New connection from {remote_address}")

                # Let the new client know the room and user lists
                self.broadcast_user_list()

            except KeyboardInterrupt:
                break
            except BlockingIOError:
                try:
                    time.sleep(60.0 / 1000.0)
                except KeyboardInterrupt:
                    break

        logging.info("Shutting down server")
        SHUTDOWN = True
        sock.close()


logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

if __name__ == '__main__':
    server = Server()
    server.run()
