from mixer.broadcaster.common import MessageType, encode_json
from mixer.broadcaster.common import Command
from mixer.broadcaster.common import ClientDisconnectedException
from mixer.broadcaster.common import command_to_byte_buffer
from mixer.broadcaster.client import Client
from typing import List, Tuple
import time
import logging

logger = logging.getLogger(__name__)


def download_room(host: str, port: int, room_name: str) -> Tuple[dict, List[Command]]:
    from mixer.broadcaster.common import decode_json

    commands = []

    with Client(host, port) as client:
        client.join_room(room_name)

        client.send_list_rooms()

        room_metadata = None

        attempts_max = 20
        attempts = 0
        try:
            while attempts < attempts_max:
                client.fetch_commands()
                command = client.get_next_received_command()
                if command is None:
                    attempts += 1
                    time.sleep(0.01)
                    continue
                attempts = 0

                if room_metadata is None and command.type == MessageType.LIST_ROOMS:
                    rooms_dict, _ = decode_json(command.data, 0)
                    room_metadata = rooms_dict[room_name]
                elif command.type <= MessageType.COMMAND:
                    continue
                # Ignore command serial Id, that may not match
                command.id = 0
                commands.append(command)
        except ClientDisconnectedException:
            logger.error(f"Disconnected while downloading room {room_name} from {host}:{port}")
            return []

        assert room_metadata is not None

        client.leave_room(room_name)

    return room_metadata, commands


def upload_room(host: str, port: int, room_name: str, room_metadata: dict, commands: List[Command]):
    with Client(host, port) as client:
        client.join_room(room_name)
        client.set_room_metadata(room_name, room_metadata)
        client.set_room_keep_open(room_name, True)

        for c in commands:
            client.add_command(c)

        client.fetch_commands()

        client.leave_room(room_name)
        client.wait_for(MessageType.LEAVE_ROOM)


def save_room(room_metadata: dict, commands: List[Command], file_path: str):
    with open(file_path, "wb") as f:
        f.write(encode_json(room_metadata))
        for c in commands:
            f.write(command_to_byte_buffer(c))


def load_room(file_path: str) -> Tuple[dict, List[Command]]:
    from mixer.broadcaster.common import bytes_to_int, int_to_message_type
    import json

    # todo factorize file reading with network reading
    room_medata = None
    commands = []
    with open(file_path, "rb") as f:
        data = f.read(4)
        string_length = bytes_to_int(data)
        metadata_string = f.read(string_length).decode()
        room_medata = json.loads(metadata_string)
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
