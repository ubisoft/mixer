import bpy
import asyncio
import argparse
import sys
import logging

"""
Socket server for Blender that receives python strings, compiles
and executes them
To be used by tests for "remote controlling" Blender :
blender.exe --python python_server.py -- --port=8989

Requires AsyncioLoopOperator

Adapted from
https://blender.stackexchange.com/questions/41533/how-to-remotely-run-a-python-script-in-an-existing-blender-instance"

"""

logger = logging.getLogger("tests")
logger.setLevel(logging.DEBUG)
# hardcoded to avoid control from a remote machine
HOST = "127.0.0.1"
STRING_MAX = 1024*1024


async def exec_buffer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    while True:
        buffer = await reader.read(STRING_MAX)
        if not buffer:
            break
        addr = writer.get_extra_info('peername')
        logger.info('-- Received %s bytes from %s', len(buffer), addr)
        logger.debug(buffer.decode('utf-8'))
        try:
            code = compile(buffer, '<string>', 'exec')
            exec(code, {})
        except Exception:
            import traceback
            logger.error('Exception')
            logger.error(traceback.format_exc())
        logger.info('-- Done')


async def serve(port: int):
    server = await asyncio.start_server(exec_buffer, HOST, port)
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
    parser.add_argument("--ptvsd", type=int, default=5688, help="Vscode debugger port")
    args, _ = parser.parse_known_args(args_)
    return args


def forcebreak():
    print("Waiting for debugger attach")
    import ptvsd
    ptvsd.enable_attach(address=('localhost', 5678), redirect_output=True)
    ptvsd.wait_for_attach()
    breakpoint()


if __name__ == '__main__':

    # forcebreak()

    args = parse()
    if args.ptvsd:
        try:
            import ptvsd
            ptvsd.enable_attach(address=('localhost', args.ptvsd), redirect_output=True)
        except ImportError:
            pass

    logger.info('Starting:')
    logger.info('  python port %s', args.port)
    logger.info('  ptvsd  port %s', args.ptvsd)

    asyncio.ensure_future(serve(args.port))
    bpy.ops.dcc_sync.asyncio_loop()
