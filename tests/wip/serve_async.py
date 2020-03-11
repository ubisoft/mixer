import asyncio

PORT = 8081
HOST = "127.0.0.1"
STRING_MAX = 1024*1024


async def exec_buffer(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    while True:
        buffer = await reader.read(STRING_MAX)
        if not buffer:
            break
        addr = writer.get_extra_info('peername')
        print(f"-- Received {len(buffer)} bytes from {addr!r}")

        try:
            code = compile(buffer, '<string>', 'exec')
            exec(code, {})
            print("-- Done")
        except Exception:
            import traceback
            traceback.print_exc()


async def serve():
    server = await asyncio.start_server(exec_buffer, HOST, PORT)
    addr = server.sockets[0].getsockname()
    print(f'Serving on {addr}')
    async with server:
        await server.serve_forever()

asyncio.run(serve())
