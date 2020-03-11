# https://blender.stackexchange.com/questions/41533/how-to-remotely-run-a-python-script-in-an-existing-blender-instance"

# Script to run from blender:
#   blender --python blender_server.py

PORT = 8081
HOST = "localhost"
PATH_MAX = 4096
STRING_MAX = 1024*1024


def exec_buffer(buffer: bytes):
    global_namespace = {
        "__name__": "__main__",
    }
    code = compile(buffer, '<string>', 'exec')
    exec(code, global_namespace)


def main():
    import socket

    serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    serversocket.bind((HOST, PORT))
    serversocket.listen(1)

    print("Listening on %s:%s" % (HOST, PORT))
    connection, address = serversocket.accept()
    while True:
        buf = connection.recv(STRING_MAX)
        if not buf:
            break

        print(f"Executing {len(buf)} bytes")
        try:
            exec_buffer(buf)
        except Exception:
            import traceback
            traceback.print_exc()


if __name__ == "__main__":
    main()
