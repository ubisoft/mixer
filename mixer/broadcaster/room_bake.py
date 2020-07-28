from mixer.broadcaster.common import MessageType, encode_json
from mixer.broadcaster.common import Command
from mixer.broadcaster.common import ClientDisconnectedException
from mixer.broadcaster.client import Client
from typing import List, Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)


def download_room(host: str, port: int, room_name: str) -> Tuple[Dict[str, Any], List[Command]]:
    from mixer.broadcaster.common import decode_json, RoomAttributes

    logger.info("Downloading room %s", room_name)

    commands = []

    with Client(host, port) as client:
        client.join_room(room_name)

        room_attributes = None

        try:
            while room_attributes is None or len(commands) < room_attributes[RoomAttributes.COMMAND_COUNT]:
                client.fetch_outgoing_commands()
                received_commands = client.fetch_incoming_commands()
                command = client.get_next_received_command()
                if received_commands is None:
                    raise ClientDisconnectedException()
                for command in received_commands:
                    if room_attributes is None and command.type == MessageType.LIST_ROOMS:
                        rooms_attributes, _ = decode_json(command.data, 0)
                        if room_name not in rooms_attributes:
                            logger.error("Room %s does not exist on server", room_name)
                            return {}, []
                        room_attributes = rooms_attributes[room_name]
                        logger.info(
                            "Meta data received, number of commands in the room: %d",
                            room_attributes[RoomAttributes.COMMAND_COUNT],
                        )
                    elif command.type <= MessageType.COMMAND:
                        continue  # don't store server protocol commands

                    commands.append(command)
                    if room_attributes is not None:
                        logger.debug(
                            "Command %d / %d received", len(commands), room_attributes[RoomAttributes.COMMAND_COUNT]
                        )
        except ClientDisconnectedException:
            logger.error(f"Disconnected while downloading room {room_name} from {host}:{port}")
            return {}, []

        assert room_attributes is not None

        client.leave_room(room_name)

    return room_attributes, commands


def upload_room(host: str, port: int, room_name: str, room_attributes: dict, commands: List[Command]):
    with Client(host, port) as client:
        client.join_room(room_name)
        client.set_room_attributes(room_name, room_attributes)
        client.set_room_keep_open(room_name, True)

        for c in commands:
            client.add_command(c)

        client.fetch_outgoing_commands()

        client.leave_room(room_name)
        if client.wait_for(MessageType.LEAVE_ROOM) is None:
            raise ClientDisconnectedException("Client disconnected before the end of upload room")


def save_room(room_attributes: dict, commands: List[Command], file_path: str):
    with open(file_path, "wb") as f:
        f.write(encode_json(room_attributes))
        for c in commands:
            f.write(c.to_byte_buffer())


def load_room(file_path: str) -> Tuple[dict, List[Command]]:
    from mixer.broadcaster.common import bytes_to_int, int_to_message_type
    import json

    # todo factorize file reading with network reading
    room_medata = None
    commands = []
    with open(file_path, "rb") as f:
        data = f.read(4)
        string_length = bytes_to_int(data)
        attributes_string = f.read(string_length).decode()
        room_medata = json.loads(attributes_string)
        while True:
            prefix_size = 14
            msg = f.read(prefix_size)
            if not msg:
                break

            frame_size = bytes_to_int(msg[:8])
            command_id = bytes_to_int(msg[8:12])
            message_type = bytes_to_int(msg[12:])

            msg = f.read(frame_size)

            commands.append(Command(int_to_message_type(message_type), msg, command_id))

    assert room_medata is not None

    return room_medata, commands
