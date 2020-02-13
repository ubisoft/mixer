import time
import queue
import argparse

import common
import client


TIMEOUT = 10  # in seconds


class CliClient(client.Client):
    def __init__(self, args):
        super().__init__(args.host, args.port)
        self.timeout = args.timeout

    def listRooms(self):
        def _printResult(command: common.Command):
            rooms, _ = common.decodeStringArray(command.data, 0)
            if len(rooms) == 0:
                print('No rooms')
            else:
                print(f'{len(rooms)} room(s):\n  - ', end='')
                print('\n  - '.join(rooms))

        command = common.Command(common.MessageType.LIST_ROOMS)
        self.processCommand(command, _printResult)

    def deleteRoom(self, name):
        command = common.Command(common.MessageType.DELETE_ROOM, name.encode())
        self.processCommand(command)

    def clearRoom(self, name):
        command = common.Command(common.MessageType.CLEAR_ROOM, name.encode())
        self.processCommand(command)

    def listRoomClients(self, name):
        def _printResult(command: common.Command):
            clients, _ = common.decodeStringArray(command.data, 0)
            if len(clients) == 0:
                print(f'No clients in "{name}" room')
            else:
                print(f'{len(clients)} client(s) in "{name}" room:\n  - ', end='')
                print('\n  - '.join(clients))

        command = common.Command(common.MessageType.LIST_ROOM_CLIENTS, name.encode())
        self.processCommand(command, _printResult)

    def listClients(self):
        def _printResult(command: common.Command):
            clients, _ = common.decodeStringArray(command.data, 0)
            if len(clients) == 0:
                print('No clients')
            else:
                print(f'{len(clients)} client(s):\n  - ', end='')
                print('\n  - '.join(clients))

        command = common.Command(common.MessageType.LIST_CLIENTS)
        self.processCommand(command, _printResult)

    def processCommand(self, command: common.Command, callback=None):
        if not self.isConnected():
            print(f'CLI not connected to server {self.host}:{self.port}')
            return

        self.addCommand(command)
        if callback is not None:
            command = self.consume()
            if command:
                callback(command)

    def consume(self):
        try:
            command = self.receivedCommands.get(timeout=self.timeout)
            self.receivedCommands.task_done()
        except queue.Empty:
            print(f'Timeout error: no server response (waited {self.timeout}s)')
            return
        return command


def process_room_command(args):
    client = None

    if args.command == 'list':
        client = CliClient(args)
        client.listRooms()

    elif args.command == 'delete':
        count = len(args.name)
        if count:
            client = CliClient(args)
            for name in args.name:
                client.deleteRoom(name)
        else:
            print('Expected one or more room names')

    elif args.command == 'clear':
        count = len(args.name)
        if count:
            client = CliClient(args)
            for name in args.name:
                client.clearRoom(name)
        else:
            print('Expected one or more room names')

    elif args.command == 'clients':
        count = len(args.name)
        if count:
            client = CliClient(args)
            for name in args.name:
                client.listRoomClients(name)
        else:
            print('Expected one or more room names')

    if client:
        client.disconnect()


def process_client_command(args):
    client = None

    if args.command == 'list':
        client = CliClient(args)
        client.listClients()

    if client is not None:
        client.disconnect()


parser = argparse.ArgumentParser(prog='cli', description='Command Line Interface for VRtist server')
sub_parsers = parser.add_subparsers()

parser.add_argument('--host', help='Host name', default=common.DEFAULT_HOST)
parser.add_argument('--port', help='Port', default=common.DEFAULT_PORT)
parser.add_argument('--timeout', help='Timeout for server response', default=TIMEOUT)

# Room commands are relative to... a room!
room_parser = sub_parsers.add_parser('room', help='Rooms related commands')
room_parser.add_argument('command', help='Commands. Use "list" to list all the rooms of the server. Use "delete" to delete one or more rooms. Use "clear" to clear the commands stack of rooms. Use "clients" to list the clients connected to rooms.', choices=(
    'list', 'delete', 'clear', 'clients'))
room_parser.add_argument('name', help='Room name. You can specify multiple room names separated by spaces.', nargs='*')
room_parser.set_defaults(func=process_room_command)

# Client commands are relative to a client independently of any room
client_parser = sub_parsers.add_parser('client', help='Clients related commands')
client_parser.add_argument('command', help='', choices=('list', 'disconnect'))
client_parser.set_defaults(func=process_client_command)

args = parser.parse_args()
if hasattr(args, 'func'):
    args.func(args)
