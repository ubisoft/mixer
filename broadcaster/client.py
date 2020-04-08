import queue
import socket
import logging


try:
    from . import common
except ImportError:
    import common

logger = logging.getLogger() if __name__ == "__main__" else logging.getLogger(__name__)


class Client:
    """
    The client class is responsible for:
    - handling the connection with the server
    - receiving packet of bytes to convert them to commands
    - send commands
    """

    def __init__(self, host=common.DEFAULT_HOST, port=common.DEFAULT_PORT):
        self.host = host
        self.port = port
        self.receivedCommands = queue.Queue()
        self.pendingCommands = queue.Queue()
        self.applyTransformCallback = None
        self.receivedCommandsProcessed = False
        self.blockSignals = False
        self._local_address = None
        self.socket = None

    def __del__(self):
        if self.socket is not None:
            self.disconnect()

    def connect(self):
        if self.isConnected():
            raise RuntimeError("Client.connect : already connected")

        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.connect((self.host, self.port))
            self._local_address = self.socket.getsockname()
            logger.info(
                "Connecting from local %s:%s to %s:%s",
                self._local_address[0],
                self._local_address[1],
                self.host,
                self.port,
            )
        except ConnectionRefusedError:
            self.socket = None
        except Exception as e:
            logger.error("Connection error %s", e, exc_info=True)
            self.socket = None
            raise

    def disconnect(self):
        if self.socket:
            self.socket.shutdown(socket.SHUT_RDWR)
            self.socket.close()
            self.socket = None

    def isConnected(self):
        return self.socket is not None

    def addCommand(self, command):
        self.pendingCommands.put(command)

    def joinRoom(self, roomName):
        common.writeMessage(self.socket, common.Command(common.MessageType.JOIN_ROOM, roomName.encode("utf8"), 0))

    def leaveRoom(self, roomName):
        common.writeMessage(self.socket, common.Command(common.MessageType.LEAVE_ROOM, roomName.encode("utf8"), 0))

    def setClientName(self, userName):
        common.writeMessage(self.socket, common.Command(common.MessageType.SET_CLIENT_NAME, userName.encode("utf8"), 0))

    def fetchIncomingCommands(self):
        """
        Gather incoming commands in receivedCommands queue.
        """
        while True:
            try:
                command = common.readMessage(self.socket)
            except common.ClientDisconnectedException:
                logger.info("Connection lost for %s:%s", self.host, self.port)
                self.socket = None  # Set socket to None before putting CONNECTION_LIST message to avoid sending/reading new messages
                command = common.Command(common.MessageType.CONNECTION_LOST)
                self.receivedCommands.put(command)
                break

            if command is None:
                break

            self.receivedCommands.put(command)

    def fetchOutgoingCommands(self):
        """
        Send commands in pendingCommands queue to the server.
        """
        while True:
            try:
                command = self.pendingCommands.get_nowait()
            except queue.Empty:
                break

            logger.info("Send %s (queue size = %d)", command.type, self.pendingCommands.qsize())
            common.writeMessage(self.socket, command)
            self.pendingCommands.task_done()

    def fetchCommands(self):
        self.fetchIncomingCommands()
        self.fetchOutgoingCommands()

    def getNextReceivedCommand(self):
        try:
            command = self.receivedCommands.get_nowait()
            logger.debug("Receive %s (queue size = %d)", command.type, self.receivedCommands.qsize())
            return command
        except queue.Empty:
            return None


# For tests
if __name__ == "__main__":
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

    client.disconnect()
