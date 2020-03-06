import common
import socket
import select
import threading
import logging
import time

import os
import sys
sys.path.append(os.getcwd())


TIMEOUT = 60.0
BINDING_HOST = ''

SHUTDOWN = False


class Connection:
    """ Represent a connection with a client """

    def __init__(self, socket, address):
        self.socket = socket
        self.address = address
        self.clientname = None
        self.room = None
        self.commands = []  # Pending commands to send to the client
        self.start()

    def start(self):
        self.thread = threading.Thread(None, self.run)
        self.thread.start()

    def joinRoom(self, roomName):
        with common.mutex:
            room = rooms.get(roomName)
            if room is None:
                logging.info("Room %s does not exist. Creating it.", roomName)
                room = Room(roomName)
                rooms[roomName] = room
            room.addClient(self)
            self.room = room

    def deleteRoom(self, name):
        with common.mutex:
            room = rooms.get(name)
            if room is not None:
                room.close()

    def clearRoom(self, name):
        with common.mutex:
            room = rooms.get(name)
            if room is not None:
                room.clear()

    def listRooms(self):
        data = common.encodeStringArray(list(rooms.keys()))
        command = common.Command(common.MessageType.LIST_ROOMS, data)
        with common.mutex:
            self.commands.append(command)

    def listRoomClients(self, name):
        with common.mutex:
            room = rooms.get(name)
            if room is not None:
                command = common.Command(common.MessageType.LIST_ROOM_CLIENTS, common.encodeJson(room.getClients()))
            else:
                command = common.Command(common.MessageType.SEND_ERROR, common.encodeString(f'No room named {name}.'))
            self.commands.append(command)

    def listClients(self):
        with common.mutex:
            clients = []
            for room in rooms.values():
                clients += room.getClients()
            command = common.Command(common.MessageType.LIST_CLIENTS, common.encodeJson(clients))
            self.commands.append(command)

    def setClientName(self, name):
        self.clientname = name

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

                elif command.type == common.MessageType.LIST_ROOMS:
                    self.listRooms()

                elif command.type == common.MessageType.DELETE_ROOM:
                    self.deleteRoom(command.data.decode())

                elif command.type == common.MessageType.CLEAR_ROOM:
                    self.clearRoom(command.data.decode())

                elif command.type == common.MessageType.LIST_ROOM_CLIENTS:
                    self.listRoomClients(command.data.decode())

                elif command.type == common.MessageType.LIST_CLIENTS:
                    self.listClients()

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
        logging.info("%s closed",  self.address)


class Room:
    def __init__(self, roomName):
        self.name = roomName
        self.clients = []
        self.commands = []

    def addClient(self, client):
        logging.info("Add Client % s to Room % s", client.address, self.name)
        self.clients.append(client)
        if len(self.clients) == 1:
            command = common.Command(common.MessageType.CONTENT)
            client.addCommand(command)
        else:
            command = common.Command(common.MessageType.CLEAR_CONTENT)
            client.addCommand(command)

            for command in self.commands:
                client.addCommand(command)

    def getClients(self):
        return [dict(ip=client.address[0], port=client.address[1],
                     name=client.clientname, room=self.name) for client in self.clients]

    def close(self):
        command = common.Command(common.MessageType.LEAVE_ROOM, common.encodeString(self.name))
        self.addCommand(command, None)
        self.clients = []
        with common.mutex:
            del rooms[self.name]
            logging.info("Room % s deleted", self.name)

    def clear(self):
        self.commands = []

    def removeClient(self, client):
        logging.info("Remove Client % s from Room % s", client.address, self.name)
        self.clients.remove(client)
        if len(self.clients) == 0:
            with common.mutex:
                del rooms[self.name]
                logging.info("No more clients in room \"%s\". Room deleted", self.name)

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
            for client in self.clients:
                if client != sender:
                    client.addCommand(command)


rooms = {}


def runServer():
    global SHUTDOWN

    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.bind((BINDING_HOST, common.DEFAULT_PORT))
    connection.setblocking(0)
    connection.listen(1000)

    logging.info("Listening on port % s", common.DEFAULT_PORT)
    while True:
        try:
            newConnection = connection.accept()
            logging.info("New connection %s", newConnection[1])
            Connection(*newConnection)
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
    format='%(asctime)s - %(levelname)s - %(message)s', level=logging.ERROR)

runServer()
