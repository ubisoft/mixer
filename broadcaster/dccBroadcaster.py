import socket
import select
import threading
import common

TIMEOUT = 60.0
HOST = ''
PORT = 12800

class Client:
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
        with common.Mutex() as _:
            room = rooms.get(roomName)
            if room is None:
                room = Room(roomName)
                rooms[roomName] = room
            room.addClient(self)
            self.room = room

            
    def run(self):
        while(True):
            try:
                messageType, data = common.readMessage(self.socket)
            except common.ClientDisconnectedException:
                break

            if messageType is not None:
            
                if messageType == common.MessageType.ROOM:
                    self.joinRoom(data.decode())
                    
                elif messageType.value > common.MessageType.COMMAND.value:
                    if self.room is not None:               
                        self.room.addCommand(common.Command(messageType, data), self)
                    else:
                        print("COMMAND received but no room was joined")

            if len(self.commands) > 0:
                with common.Mutex() as _:
                    for command in self.commands:
                        common.writeMessage(self.socket, command.type, command.data)
                    self.commands = []

        self.close()

    def addCommand(self, command):
        self.commands.append(command)

    def close(self):
        if self.room is not None:
            self.room.removeClient(self)
        try:
            self.socket.send(b"Disconnect")
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
        for command in self.commands:
            client.addCommand(command)            

    def removeClient(self, client):
        print (f"Remove Client {client.address} from Room {self.name}")
        self.clients.remove(client)
        if len(self.clients) == 0:
            with common.Mutex() as _:
                del rooms[self.name]   

    def addCommand(self, command, sender):
        with common.Mutex() as _:
            self.commands.append(command)
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
        newClient = connection.accept()
        print(f"New client {newClient[1]}")
        Client(*newClient)

    connection.close()

runServer()