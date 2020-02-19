import common
import socket
import threading
import logging
import time

from typing import List, ValuesView, Mapping

import os
import sys
sys.path.append(os.getcwd())


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
        self.start()

    def start(self):
        self.thread = threading.Thread(None, self.run)
        self.thread.start()

    def joinRoom(self, room_name: str):
        assert self.room is None
        with common.mutex:
            self._server.join_room(self, room_name)

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
            room = self._server.get_room(room_name)
            if room is not None:
                command = common.Command(common.MessageType.LIST_ROOM_CLIENTS, common.encodeJson(room.getClients()))
            else:
                command = common.Command(common.MessageType.SEND_ERROR,
                                         common.encodeString(f'No room named {room_name}.'))
            self.commands.append(command)

    def sendListClients(self):
        with common.mutex:
            clients = []
            for room in self._server.rooms():
                clients += room.getClients()
            command = common.Command(common.MessageType.LIST_CLIENTS, common.encodeJson(clients))
            self.commands.append(command)

    def setClientName(self, name):
        self.clientname = name
        self.room.broadcast_user_list()

    def run(self):
        global SHUTDOWN
        while not SHUTDOWN:
            try:
                command = common.readMessage(self.socket)
            except common.ClientDisconnectedException:
                break

            if command is not None:
                logging.info(f"client {self.address}: {command.type} received")

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
        if self.room is not None:
            self.room.removeClient(self)
        try:
            self.socket.close()
        except Exception:
            pass
        logging.info(f"{self.address} closed")


class Room:
    def __init__(self, server: 'Server', roomName: str):
        self.name = roomName
        self._connections: List['Connection'] = []
        self.commands = []
        self._server: 'Server' = server

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

    def getClients(self):
        return [dict(ip=c.address[0], port=c.address[1],
                     name=c.clientname, room=self.name) for c in self._connections]

    def close(self):
        command = common.Command(common.MessageType.LEAVE_ROOM, common.encodeString(self.name))
        self.addCommand(command, None)
        # self.broadcast_user_list()
        self._connections = []
        self._server.delete_room(self.name)

    def clear(self):
        self.commands = []

    def removeClient(self, connection: Connection):
        logging.info(f"Remove Client {connection.address} from Room {self.name}")
        self._connections.remove(connection)
        if len(self._connections) == 0:
            self._server.delete_room(self.name)
            logging.info(f'No more clients in room "{self.name}". Room deleted')
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
        self._rooms: Mapping[str, Room] = {}
        # Connections not joined to any room
        self._homelessConnections: List[Connection] = []

    def get_room(self, room_name: str) -> Room:
        return self._rooms.get(room_name)

    def add_room(self, room_name: str) -> Room:
        if room_name in self._rooms:
            raise ValueError(f"add_room: room with name {room_name} already exists")
        room = Room(self, room_name)
        self._rooms[room_name] = room
        logging.info(f'Room {room_name} added')

        return room

    def delete_room(self, room_name: str):
        with common.mutex:
            if room_name in self._rooms:
                del self._rooms[room_name]
                logging.info(f'Room {room_name} deleted')

    def join_room(self, connection: Connection, room_name: str):
        room = self.get_room(room_name)
        if room is None:
            logging.info(f"Room {room_name} does not exist. Creating it.")
            room = self.add_room(room_name)

        peername = connection.socket.getpeername()
        if peername in self._homelessConnections:
            logging.debug("Reusing connection %s", peername)
            del self._homelessConnections[peername]

        room.addClient(connection)

    def leave_room(self, connection: Connection, room_name: str):
        room = self.get_room(room_name)
        if room is None:
            raise ValueError(f"Room not found {room_name})")
        room.removeClient(connection)
        peername = connection.socket.getpeername()
        assert peername not in self._homelessConnections
        self._homelessConnections[peername] = connection

    def rooms_names(self) -> List[str]:
        return self._rooms.keys()

    def rooms(self) -> ValuesView[Room]:
        return self._rooms.values()

    def broadcast_user_list(self):
        for room in self._rooms.values():
            room.broadcast_user_list()
        for connection in self._homelessConnections():
            connection.broadcast_user_list()

    def run(self):
        global SHUTDOWN

        connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        connection.bind((BINDING_HOST, common.DEFAULT_PORT))
        connection.setblocking(0)
        connection.listen(1000)

        logging.info(f"Listening on port {common.DEFAULT_PORT}")
        while True:
            try:
                sock = connection.accept()
                Connection(self, *sock)
                logging.info(f"New connection {sock[1]}")

            except KeyboardInterrupt:
                break
            except BlockingIOError:
                try:
                    time.sleep(60.0 / 1000.0)
                except KeyboardInterrupt:
                    break

        logging.info("Shutting down server")
        SHUTDOWN = True
        connection.close()


logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

server = Server()
server.run()
