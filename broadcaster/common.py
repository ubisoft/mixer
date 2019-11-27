from enum import Enum
import threading
import select
import socket

mutex = threading.Lock()

class MessageType(Enum):
    ROOM = 1
    COMMAND = 2
    TRANSFORM = 3
    DELETE = 4
    MESH = 5
    

class ClientDisconnectedException(Exception):
    '''When a client is disconnected and we try to read from it.'''

def intToBytes(value, size = 8):
    return value.to_bytes(size, byteorder='big')

def bytesToInt(value):
    return int.from_bytes(value, 'big')

def intToMessageType(value):
    return MessageType(value)

def readMessage(socket):
    r,_,_ = select.select([socket],[],[],0.0001)
    if len(r) > 0:
        try:
            msg = socket.recv(10)
            frameSize = bytesToInt(msg[:8])
            messageType = bytesToInt(msg[8:])
            currentSize = frameSize
            msg = b''
            while currentSize != 0:
                tmp = socket.recv(currentSize)
                msg += tmp
                currentSize -= len(tmp)
            return intToMessageType(messageType), msg
        except Exception as e:
            print (e)
            raise ClientDisconnectedException()

    return None, None

def writeMessage(socket, messageType, data):
    size = intToBytes(len(data),8)
    mtype = intToBytes(messageType.value,2)
    _,w,_ = select.select([],[socket],[],0.0001)
    if len(w) > 0:
        socket.send(size + mtype + data)

class Mutex:
    def __enter__(self):
        mutex.acquire()
        return mutex

    def __exit__(self ,type, value, traceback):
        mutex.release()

class Command:
    def __init__(self, commandType, data):
        self.data = data
        self.type = commandType
