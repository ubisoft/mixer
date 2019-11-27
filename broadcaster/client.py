import socket
import select
import threading
try:
    from . import common
except ImportError:
    import common

HOST = "localhost"
PORT = 12800



class Client:
    def __init__(self, host = HOST, port = PORT):
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.socket.connect((host, port))
        print(f"Connection on port {port}")

        self.receivedCommands = []
        self.pendingCommands = []

        self.thread = threading.Thread(None, self.run)
        self.thread.start()

    def addCommand(self, command):
        with common.Mutex() as _:
            self.pendingCommands.append(command)

    def joinRoom(self, roomName):
        common.writeMessage(self.socket,common.MessageType.ROOM, roomName.encode('utf8') )

    def send(self, data):
        with common.Mutex() as _:
            self.socket.send(data)

    def run(self):
        while(True):
            try:
                messageType, data = common.readMessage(self.socket)
            except common.ClientDisconnectedException:
                break
                
            if messageType is not None:
                if messageType.value > common.MessageType.COMMAND.value:
                    with common.Mutex() as _:
                        self.receivedCommands.append(common.Command(messageType, data))
                        print (f"Received {messageType} {data}")

            with common.Mutex() as _:
                if len(self.pendingCommands) > 0:
                    for command in self.pendingCommands:
                        common.writeMessage(self.socket, command.type, command.data)
                    self.pendingCommands = []


# For tests
if __name__ == '__main__':
    client = Client()

    while True:
        msg = input("> ")
        # Peut planter si vous tapez des caractères spéciaux
        if msg == "end":
            break

        encodedMsg = msg.encode()

        if msg.startswith("Transform"):
            client.addCommand(common.Command(common.MessageType.TRANSFORM, encodedMsg[9:]))
        if msg.startswith("Delete"):
            client.addCommand(common.Command(common.MessageType.DELETE, encodedMsg[6:]))
        elif msg.startswith("Room"): 
            client.joinRoom(msg[4:])       

