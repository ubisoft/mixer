import socket
import select
import threading

import os
import sys
sys.path.append(os.getcwd())
import common


TIMEOUT = 60.0
HOST = ''
PORT = 12800

class Connection:
    def __init__(self, socket, address):
        self.socket = socket
        self.address = address
        self.room = None
        self.commands = []
        self.start()

    def start(self):
        self.thread = threading.Thread(None, self.run)
        self.thread.start()

    def joinRoom(self, roomName):
        with common.mutex:
            room = rooms.get(roomName)
            if room is None:
                print ("Create room : " + roomName)
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
                command = common.Command(common.MessageType.LIST_ROOM_CLIENTS, common.encodeStringArray(room.clients))
                self.commands.append(command)

    def listClients(self):
        clients = set()
        with common.mutex:
            for room in rooms.values():
                for client in room.clients:
                    clients.add(client)
            command = common.Command(common.MessageType.LIST_CLIENTS, common.encodeStringArray(clients))
            self.commands.append(command)

    def run(self):
        while(True):
            try:
                command = common.readMessage(self.socket)
            except common.ClientDisconnectedException:
                break

            if command is not None:
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

                # Other commands
                elif command.type.value > common.MessageType.COMMAND.value:
                    if self.room is not None:
                        self.room.addCommand(command, self)
                    else:
                        print("COMMAND received but no room was joined")

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
        print (f"{self.address} closed")

class Room:
    def __init__(self, roomName):
        self.name = roomName
        self.clients = []
        self.commands = []

    def addClient(self, client):
        print (f"Add Client {client.address} to Room {self.name}")
        self.clients.append(client)
        if len(self.clients) == 1:
            command = common.Command(common.MessageType.CONTENT)
            client.addCommand(command)
        else:
            command = common.Command(common.MessageType.CLEAR_CONTENT)
            client.addCommand(command)

            for command in self.commands:
                client.addCommand(command)

    def close(self):
        command = common.Command(common.MessageType.LEAVE_ROOM, common.encodeString(self.name))
        self.addCommand(command, None)
        self.clients = []
        with common.mutex:
            del rooms[self.name]
            print(f'Room {self.name} deleted')

    def clear(self):
        self.commands = []

    def removeClient(self, client):
        print (f"Remove Client {client.address} from Room {self.name}")
        self.clients.remove(client)
        if len(self.clients) == 0:
            with common.mutex:
                del rooms[self.name]
                print (f'No more clients in room "{self.name}". Room deleted')

    def mergeCommands(self, command):
        commandType = command.type
        commandPath = common.decodeString(command.data,0)[0]
        if len(self.commands) > 0:
            storedCommand = self.commands[-1]
            if commandType == storedCommand.type and commandPath == common.decodeString(storedCommand.data,0)[0]:
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
    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connection.bind((HOST, PORT))
    connection.listen(1000)

    print(f"Listening on port {PORT}")
    while True:
        newConnection = connection.accept()
        print(f"New connection {newConnection[1]}")
        Connection(*newConnection)

    connection.close()

runServer()
