from enum import Enum
import threading
import select
import socket
import struct
import json
import time


mutex = threading.RLock()

DEFAULT_HOST = "localhost"
DEFAULT_PORT = 12800


class MessageType(Enum):
    JOIN_ROOM = 1
    CREATE_ROOM = 2
    LEAVE_ROOM = 3
    LIST_ROOMS = 4
    CONTENT = 5
    CLEAR_CONTENT = 6
    DELETE_ROOM = 7
    CLEAR_ROOM = 8
    # All clients that have joined a room
    LIST_ROOM_CLIENTS = 9
    # All joined clients for all rooes
    LIST_CLIENTS = 10
    SET_CLIENT_NAME = 11
    SEND_ERROR = 12
    CONNECTION_LOST = 13
    # All all joined and un joined clients
    LIST_ALL_CLIENTS = 14

    COMMAND = 100
    DELETE = 101
    CAMERA = 102
    LIGHT = 103
    MESHCONNECTION_DEPRECATED = 104
    RENAME = 105
    DUPLICATE = 106
    SEND_TO_TRASH = 107
    RESTORE_FROM_TRASH = 108
    TEXTURE = 109
    ADD_COLLECTION_TO_COLLECTION = 110
    REMOVE_COLLECTION_FROM_COLLECTION = 111
    ADD_OBJECT_TO_COLLECTION = 112
    REMOVE_OBJECT_FROM_COLLECTION = 113
    ADD_OBJECT_TO_SCENE = 114
    ADD_COLLECTION_TO_SCENE = 115
    INSTANCE_COLLECTION = 116
    COLLECTION = 117
    COLLECTION_REMOVED = 118
    SET_SCENE = 119
    GREASE_PENCIL_MESH = 120
    GREASE_PENCIL_MATERIAL = 121
    GREASE_PENCIL_CONNECTION = 122
    GREASE_PENCIL_TIME_OFFSET = 123
    FRAME = 124
    FRAME_START_END = 125
    CAMERA_ANIMATION = 126
    OPTIMIZED_COMMANDS = 200
    TRANSFORM = 201
    MESH = 202
    MATERIAL = 203


class LightType(Enum):
    SPOT = 0  # directly mapped from Unity enum
    SUN = 1
    POINT = 2


class SensorFitMode(Enum):
    AUTO = 0
    VERTICAL = 1
    HORIZONTAL = 2


class ClientDisconnectedException(Exception):
    '''When a client is disconnected and we try to read from it.'''


def intToBytes(value, size=8):
    return value.to_bytes(size, byteorder='little')


def bytesToInt(value):
    return int.from_bytes(value, 'little')


def intToMessageType(value):
    return MessageType(value)


def encodeBool(value):
    if value:
        return intToBytes(1, 4)
    else:
        return intToBytes(0, 4)


def decodeBool(data, index):
    value = bytesToInt(data[index:index+4])
    if value == 1:
        return True, index+4
    else:
        return False, index+4


def encodeString(value):
    encodedValue = value.encode()
    return intToBytes(len(encodedValue), 4) + encodedValue


def decodeString(data, index):
    stringLength = bytesToInt(data[index:index+4])
    start = index+4
    end = start+stringLength
    value = data[start:end].decode()
    return value, end


def encodeJson(value: dict):
    return encodeString(json.dumps(value))


def decodeJson(data, index):
    value, end = decodeString(data, index)
    return json.loads(value), end


def encodeFloat(value):
    return struct.pack('f', value)


def decodeFloat(data, index):
    return struct.unpack('f', data[index:index+4])[0], index+4


def encodeInt(value):
    return struct.pack('i', value)


def decodeInt(data, index):
    return struct.unpack('i', data[index:index+4])[0], index+4


def encodeVector2(value):
    return struct.pack('2f', *(value.x, value.y))


def decodeVector2(data, index):
    return struct.unpack('2f', data[index:index+2*4]), index+2*4


def encodeVector3(value):
    return struct.pack('3f', *(value.x, value.y, value.z))


def decodeVector3(data, index):
    return struct.unpack('3f', data[index:index+3*4]), index+3*4


def encodeColor(value):
    if len(value) == 3:
        return struct.pack('4f', *(value[0], value[1], value[2], 1.0))
    else:
        return struct.pack('4f', *(value[0], value[1], value[2], value[3]))


def decodeColor(data, index):
    return struct.unpack('4f', data[index:index+4*4]), index+4*4


def encodeVector4(value):
    return struct.pack('4f', *(value.x, value.y, value.z, value.w))


def decodeVector4(data, index):
    return struct.unpack('4f', data[index:index+4*4]), index+4*4


def encodeStringArray(values):
    buffer = encodeInt(len(values))
    for item in values:
        buffer += encodeString(item)
    return buffer


def decodeStringArray(data, index):
    count = bytesToInt(data[index:index+4])
    index = index + 4
    values = []
    for _ in range(count):
        string, index = decodeString(data, index)
        values.append(string)
    return values, index


def decodeArray(data, index, schema, inc):
    count = bytesToInt(data[index:index+4])
    start = index+4
    end = start
    values = []
    for _ in range(count):
        end = start+inc
        values.append(struct.unpack(schema, data[start:end]))
        start = end
    return values, end


def decodeFloatArray(data, index):
    return decodeArray(data, index, 'f', 4)


def decodeIntArray(data, index):
    count = bytesToInt(data[index:index+4])
    start = index+4
    values = []
    for _ in range(count):
        end = start+4
        values.extend(struct.unpack('I', data[start:end]))
        start = end
    return values, end


def decodeInt2Array(data, index):
    return decodeArray(data, index, '2I', 2*4)


def decodeInt3Array(data, index):
    return decodeArray(data, index, '3I', 3*4)


def decodeVector3Array(data, index):
    return decodeArray(data, index, '3f', 3*4)


def decodeVector2Array(data, index):
    return decodeArray(data, index, '2f', 2*4)


class Command:
    _id = 100

    def __init__(self, commandType: MessageType, data=b'', commandId=0):
        self.data = data or b''
        self.type = commandType
        self.id = commandId
        if commandId == 0:
            self.id = Command._id
            Command._id += 1


def recv(socket, size):
    attempts = 5
    timeout = 0.01
    while True:
        try:
            tmp = socket.recv(size)
            return tmp
        except:
            if attempts == 0:
                raise
            attempts -= 1
            time.sleep(timeout)


class CommandFormatter:
    def format_clients(self, clients):
        s = ''
        for c in clients:
            s += f'   - {c["ip"]}:{c["port"]} name = \"{c["name"]}\" room = \"{c["room"]}\"\n'
        return s

    def format(self, command: Command):

        s = f'={command.type.name}: '

        if command.type == MessageType.LIST_ROOMS:
            rooms, _ = decodeStringArray(command.data, 0)
            s += 'LIST_ROOMS: '
            if len(rooms) == 0:
                s += '  No rooms'
            else:
                s += f' {len(rooms)} room(s) : {rooms}'
        elif command.type == MessageType.LIST_ROOM_CLIENTS:
            clients, _ = decodeJson(command.data, 0)
            if len(clients) == 0:
                s += f'  No clients in room'
            else:
                s += f'  {len(clients)} client(s) in room :\n'
                s += self.format_clients(clients)
        elif command.type == MessageType.LIST_CLIENTS or command.type == MessageType.LIST_ALL_CLIENTS:
            clients, _ = decodeJson(command.data, 0)
            if len(clients) == 0:
                s += '  No clients\n'
            else:
                s += f'  {len(clients)} client(s):\n'
                s += self.format_clients(clients)
        elif command.type == MessageType.CONNECTION_LOST:
            s += 'CONNECTION_LOST:\n'
        elif command.type == MessageType.SEND_ERROR:
            s += f'ERROR: {decodeString(command.data, 0)[0]}\n'
        else:
            pass

        return s


def readMessage(socket: socket.socket) -> Command:
    if not socket:
        return None
    r, _, _ = select.select([socket], [], [], 0.0001)
    if len(r) > 0:
        try:
            msg = recv(socket, 14)
            frameSize = bytesToInt(msg[:8])
            commandId = bytesToInt(msg[8:12])
            messageType = bytesToInt(msg[12:])
            currentSize = frameSize
            msg = b''
            while currentSize != 0:
                tmp = recv(socket, currentSize)
                msg += tmp
                currentSize -= len(tmp)
            return Command(intToMessageType(messageType), msg, commandId)

        except ClientDisconnectedException:
            raise
        except Exception as e:
            print(e)
            raise ClientDisconnectedException()

    return None


def send(socket, buffer):
    attempts = 5
    timeout = 0.01
    while True:
        try:
            tmp = socket.send(buffer)
            return tmp
        except:
            if attempts == 0:
                raise
            attempts -= 1
            time.sleep(timeout)


def writeMessage(sock: socket.socket, command: Command):
    if not socket:
        return
    size = intToBytes(len(command.data), 8)
    commandId = intToBytes(command.id, 4)
    mtype = intToBytes(command.type.value, 2)

    buffer = size + commandId + mtype + command.data
    remainingSize = len(buffer)
    currentIndex = 0
    while remainingSize > 0:
        _, w, _ = select.select([], [sock], [], 0.0001)
        if len(w) > 0:
            sent = send(sock, buffer[currentIndex:])
            remainingSize -= sent
            currentIndex += sent


def is_debugger_attached():
    try:
        import ptvsd
        return ptvsd.is_attached()
    except Exception:
        pass
    return False
