import queue
import socket
import threading
import logging

try:
    from . import common
except ImportError:
    import common


class Client:
    def __init__(self, name, host=common.DEFAULT_HOST, port=common.DEFAULT_PORT, delegate=None):

        self.name = name
        self.host = host
        self.port = port
        self.receivedCommands = queue.Queue()
        self.pendingCommands = queue.Queue()
        self.applyTransformCallback = None
        self.receivedCommandsProcessed = False
        self.blockSignals = False
        self._local_address = None
        self._delegate = delegate
        self.socket = None

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((host, port))
            self._local_address = self.socket.getsockname()
            logging.info("Connecting from local %s:%s to %s:%s",
                         self._local_address[0], self._local_address[1], host, port)
        except Exception as e:
            logging.error("Connection error %s", e)
            self.socket = None

        if self.socket:
            self.threadAlive = True
            self.thread = threading.Thread(None, self.run)
            self.thread.start()
        else:
            self.thread = None

    def __del__(self):
        if self.socket is not None:
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

    def send(self, data):
        with common.mutex:
            self.socket.send(data)

    def joinRoom(self, roomName):
        common.writeMessage(self.socket, common.Command(common.MessageType.JOIN_ROOM, roomName.encode('utf8'), 0))

    def leaveRoom(self, roomName):
        common.writeMessage(self.socket, common.Command(common.MessageType.LEAVE_ROOM, roomName.encode('utf8'), 0))

    def setClientName(self, userName):
        common.writeMessage(self.socket, common.Command(
            common.MessageType.SET_CLIENT_NAME, userName.encode('utf8'), 0))

    def run(self):
        while(self.threadAlive):
            try:
                if not self.blenderExists():
                    break
                command = common.readMessage(self.socket)
            except common.ClientDisconnectedException:
                logging.info("Connection lost for %s:%s", self.host, self.port)
                command = common.Command(common.MessageType.CONNECTION_LOST)
                self.receivedCommands.put(command)
                self.socket = None
                break

            if command is not None:
                with common.mutex:
                    self.receivedCommands.put(command)

            with common.mutex:
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

    def consume_one(self):
        try:
            command = self.receivedCommands.get_nowait()
        except queue.Empty:
            return None, None
        else:
            logging.debug("Client %s Command %s received (queue size = %d)",
                          self.name, command.type, self.receivedCommands.qsize())

            self.blockSignals = True
            self.receivedCommandsProcessed = True

            if command.type == common.MessageType.LIST_ROOMS:
                if self._delegate:
                    self._delegate.buildListRooms(command.data)
                return command, True
            elif command.type == common.MessageType.LIST_ROOM_CLIENTS:
                if self._delegate:
                    clients, _ = common.decodeJson(command.data, 0)
                    self._delegate.buildListRoomClients(clients)
                return command, True
            elif command.type == common.MessageType.CONNECTION_LOST:
                if self._delegate:
                    self._delegate.clearListRoomClients()
                return command, True

            return command, False

    def blenderExists(self):
        return True


class TestClient(Client):
    def __init__(self, *args, **kwargs):
        super(TestClient, self).__init__("noname", *args, **kwargs)

    def networkConsumer(self):
        while True:
            command, processed = super().consume_one()
            if command is None:
                return


# For tests
if __name__ == '__main__':
    client = TestClient()

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
