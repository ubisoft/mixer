import bpy
import asyncio
import argparse
import sys

"""
Socket server for Blender that receives python strings, compiles 
and executes them
To be used by tests for "remote controlling" Blender :
blender.exe --python python_server.py -- --port=8989

Requires AsyncioLoopOperator

Adapted from 
https://blender.stackexchange.com/questions/41533/how-to-remotely-run-a-python-script-in-an-existing-blender-instance"

"""

# hardcoded to avoid control from a remote machine
HOST = "127.0.0.1"
STRING_MAX = 1024*1024


async def exec_buffer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    while True:
        buffer = await reader.read(STRING_MAX)
        if not buffer:
            break
        addr = writer.get_extra_info('peername')
        print(f"-- Received {len(buffer)} bytes from {addr!r}")
        print(buffer.decode('utf-8'))
        try:
            code = compile(buffer, '<string>', 'exec')
            exec(code, {})
        except Exception:
            import traceback
            traceback.print_exc()
        print("-- Done")


async def serve(port: int):
    server = await asyncio.start_server(exec_buffer, HOST, port)
    addr = server.sockets[0].getsockname()
    print(f'Serving on {addr}')
    async with server:
        await server.serve_forever()


def parse():
    args_ = []
    copy_arg = False
    for arg in sys.argv:
        if arg == '--':
            copy_arg = True
        elif copy_arg:
            args_.append(arg)

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8888, help="port number to listen to")
    args, _ = parser.parse_known_args(args_)
    return args


if __name__ == '__main__':
    args = parse()
    asyncio.ensure_future(serve(args.port))
    bpy.ops.dcc_sync.asyncio_loop()
