"""
Functions to be remotely executed in Blender via python_server.py

Remote execution relies on source code extractiona and transmission to the
execution sever, so each function must contain its imports
"""


def connect():
    import bpy

    bpy.ops.dcc_sync.connect()


def disconnect():
    import bpy

    bpy.ops.dcc_sync.disconnect()


def create_room():
    import bpy

    bpy.ops.dcc_sync.create_room()


def set_log_level(log_level):
    import dccsync

    dccsync.data.set_log_level(None, log_level)


def join_room(room_name: str = "dccsync_unittest"):
    import dccsync

    dccsync.operators.join_room(room_name)
