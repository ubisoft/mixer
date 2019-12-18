import socket
import select
import threading
import queue

try:
    from . import common
except ImportError:
    import common

HOST = "localhost"
PORT = 12800

class Client:
    def __init__(self, host = HOST, port = PORT):
        self.receivedCommands = queue.Queue()
        self.pendingCommands = queue.Queue()
        self.applyTransformCallback = None
        self.receivedCommandsProcessed = False

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
            print(f"Connection on port {port}")
        except Exception as e:
            print("Connection error ",e)
            self.socket = None
            pass

        if self.socket:
            self.threadAlive = True
            self.thread = threading.Thread(None, self.run)
            self.thread.start()
        else:
            self.thread = None

    def __del__(self): 
        if not self.socket is None:
            self.disconnect()

    def disconnect(self):
        if self.thread is not None:
            self.threadAlive = False
            self.thread.join()            

        if self.socket:
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()
            self.socket = None

    def isConnected(self):
        if self.thread and self.socket:
            return True
        return False

    def addCommand(self, command):
        self.pendingCommands.put(command)

    def joinRoom(self, roomName):
        common.writeMessage(self.socket,common.Command(common.MessageType.JOIN_ROOM, roomName.encode('utf8'), 0) )

    def send(self, data):
        with common.Mutex() as _:
            self.socket.send(data)

    def run(self):
        while(self.threadAlive):
            try:
                if not self.blenderExists():
                    break
                command = common.readMessage(self.socket)
            except common.ClientDisconnectedException:
                print("Connection lost")
                self.socket = None
                break
                
            if command is not None:                
                with common.Mutex() as _:
                    self.receivedCommands.put(command)

            with common.Mutex() as _:
                while True:
                    try:
                        command = self.pendingCommands.get_nowait()
                    except queue.Empty:
                        break
                    else:
                        common.writeMessage(self.socket, command)
                        self.pendingCommands.task_done()

        self.threadAlive = False
        self.thread = None

    def blenderExists(self):
        return True
  

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

