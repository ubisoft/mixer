import argparse
import logging

import mixer.broadcaster.client as client
import mixer.broadcaster.common as common
import mixer.broadcaster.cli_utils as cli_utils

TIMEOUT = 10  # in seconds

logger = logging.getLogger() if __name__ == "__main__" else logging.getLogger(__name__)


class ServerError(RuntimeError):
    def __init__(self, message):
        super().__init__(message)


class CliClient(client.Client):
    def __init__(self, args):
        super().__init__(args.host, args.port)
        self.connect()
        self.formatter = common.CommandFormatter()

    def list_rooms(self):
        command = common.Command(common.MessageType.LIST_ROOMS)
        self.add_and_process_command(command, common.MessageType.LIST_ROOMS)

    def delete_room(self, name):
        command = common.Command(common.MessageType.DELETE_ROOM, name.encode())
        self.add_and_process_command(command)

    def list_clients(self):
        command = common.Command(common.MessageType.LIST_CLIENTS)
        self.add_and_process_command(command, common.MessageType.LIST_CLIENTS)

    def add_and_process_command(self, command: common.Command, expected_response_type: common.MessageType = None):
        if not self.send_command(command):
            self.disconnect()
            return

        received = None
        while received is None or (expected_response_type is not None and received.type != expected_response_type):
            received_commands = self.fetch_incoming_commands()

            for command in received_commands:
                if command.type == common.MessageType.SEND_ERROR:
                    logger.error(common.decode_string(command.data, 0)[0])
                    return
                elif command.type == expected_response_type or expected_response_type is None:
                    received = command
                    break
                else:
                    logger.info("Ignoring command %s", command.type)

        if expected_response_type is not None:
            print(self.formatter.format(received))


def process_room_command(args):
    client = None

    try:
        if args.command == "list":
            client = CliClient(args)
            client.list_rooms()

        elif args.command == "delete":
            count = len(args.name)
            if count:
                client = CliClient(args)
                for name in args.name:
                    client.delete_room(name)
            else:
                print("Expected one or more room names")
    except ServerError as e:
        logger.error(e, exc_info=True)
    finally:
        if client:
            client.disconnect()


def process_client_command(args):
    client = None

    try:
        if args.command == "list":
            client = CliClient(args)
            client.list_clients()
    except ServerError as e:
        logger.error(e, exc_info=True)
    finally:
        if client is not None:
            client.disconnect()


commands = [
    "connect",
    "disconnect",
    "listrooms",
    "join <roomname>",
    "leave <roomname>",
    "listjoinedclients",
    "listallclients",
    "setclientname <clientname>",
    "listroomclients <roomname>",
    "help",
    "exit",  # this loop
]


def help():
    print("Allowed commands : ")
    for c in commands:
        print(" ", c)
    print()


def interactive_loop(args):
    client = CliClient(args)
    done = False
    while not done:
        try:
            prompt = "> "
            print(prompt, end="", flush=False)
            user_input = input()
            items = user_input.split()
            if not items:
                continue
            input_command = items[0]
            candidates = [c for c in commands if c.startswith(input_command)]
            if len(candidates) == 0:
                print(f"Command not recognised : {input_command}.")
                help()
                continue
            if len(candidates) >= 2:
                print(f"ambigous command {input_command} : found {candidates}.")
                continue

            command = candidates[0].split()[0]
            command_args = items[1:]
            if input_command != command:
                print(command, command_args)
            if command == "connect":
                if client is None or not client.is_connected():
                    client = CliClient(args)
                else:
                    print(f"Error : already connected. Use disconnect first")
            elif command == "exit":
                done = True
            elif command == "help":
                help()
            else:
                if client is None or not client.is_connected():
                    raise RuntimeError('Not connected, use "connect" first')
                if command == "listrooms":
                    client.list_rooms()
                elif command == "listclients":
                    client.list_clients()
                elif command == "join":
                    client.join_room(command_args[0])
                elif command == "leave":
                    client.leave_room(command_args[0])
                elif command == "setclientname":
                    client.set_client_attributes({common.ClientAttributes.USERNAME: command_args[0]})
                elif command == "disconnect":
                    client.disconnect()
                    client = None
                else:
                    pass
        except Exception as e:
            logger.error(f"Exception: {e}", exc_info=True)


def main():
    args, args_parser = parse_cli_args()
    cli_utils.init_logging(args)

    if hasattr(args, "func"):
        args.func(args)
    else:
        interactive_loop(args)


def parse_cli_args():
    parser = argparse.ArgumentParser(prog="cli", description="Command Line Interface for Mixer server")
    cli_utils.add_logging_cli_args(parser)

    sub_parsers = parser.add_subparsers()

    parser.add_argument("--host", help="Host name", default=common.DEFAULT_HOST)
    parser.add_argument("--port", help="Port", default=common.DEFAULT_PORT)
    parser.add_argument("--timeout", help="Timeout for server response", default=TIMEOUT)

    # Room commands are relative to... a room!
    room_parser = sub_parsers.add_parser("room", help="Rooms related commands")
    room_parser.add_argument(
        "command",
        help='Commands. Use "list" to list all the rooms of the server. Use "delete" to delete one or more rooms. Use "clear" to clear the commands stack of rooms. Use "clients" to list the clients connected to rooms.',
        choices=("list", "delete", "clear", "clients"),
    )
    room_parser.add_argument(
        "name", help="Room name. You can specify multiple room names separated by spaces.", nargs="*"
    )
    room_parser.set_defaults(func=process_room_command)

    # Client commands are relative to a client independently of any room
    client_parser = sub_parsers.add_parser("client", help="Clients related commands")
    client_parser.add_argument("command", help="", choices=("list"))
    client_parser.set_defaults(func=process_client_command)

    return parser.parse_args(), parser


if __name__ == "__main__":
    main()
