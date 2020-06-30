import queue
import socket
import logging

import mixer.broadcaster.common as common

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
        self._receivedCommandsProcessed = False
        self.blockSignals = False
        self._local_address = None
        self.socket = None

    def __del__(self):
        if self.socket is not None:
            self.disconnect()

    @property
    def receivedCommandsProcessed(self):  # noqa N802
        return self._receivedCommandsProcessed

    @receivedCommandsProcessed.setter
    def receivedCommandsProcessed(self, value):  # noqa N802
        logger.debug("setting receivedCommandsProcessed to %s", value)
        self._receivedCommandsProcessed = value

    def connect(self):
        if self.is_connected():
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

    def is_connected(self):
        return self.socket is not None

    def add_command(self, command):
        self.pendingCommands.put(command)

    def join_room(self, room_name):
        common.write_message(self.socket, common.Command(common.MessageType.JOIN_ROOM, room_name.encode("utf8"), 0))

    def leave_room(self, room_name):
        common.write_message(self.socket, common.Command(common.MessageType.LEAVE_ROOM, room_name.encode("utf8"), 0))

    def set_client_name(self, user_name):
        common.write_message(
            self.socket, common.Command(common.MessageType.SET_CLIENT_NAME, user_name.encode("utf8"), 0)
        )

    def fetch_incoming_commands(self):
        """
        Gather incoming commands in receivedCommands queue.
        """
        while True:
            try:
                command = common.read_message(self.socket)
            except common.ClientDisconnectedException:
                logger.info("Connection lost for %s:%s", self.host, self.port)
                # Set socket to None before putting CONNECTION_LIST message to avoid sending/reading new messages
                self.socket = None
                command = common.Command(common.MessageType.CONNECTION_LOST)
                self.receivedCommands.put(command)
                break

            if command is None:
                break

            self.receivedCommands.put(command)

    def fetch_outgoing_commands(self):
        """
        Send commands in pendingCommands queue to the server.
        """
        while True:
            try:
                command = self.pendingCommands.get_nowait()
            except queue.Empty:
                break

            logger.debug("Send %s (queue size = %d)", command.type, self.pendingCommands.qsize())
            common.write_message(self.socket, command)
            self.pendingCommands.task_done()

    def fetch_commands(self):
        self.fetch_incoming_commands()
        self.fetch_outgoing_commands()

    def get_next_received_command(self):
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

        encoded_msg = msg.encode()

        if msg.startswith("Transform"):
            client.add_command(common.Command(common.MessageType.TRANSFORM, encoded_msg[9:]))
        if msg.startswith("Delete"):
            client.add_command(common.Command(common.MessageType.DELETE, encoded_msg[6:]))
        elif msg.startswith("Room"):
            client.join_room(msg[4:])

    client.disconnect()
