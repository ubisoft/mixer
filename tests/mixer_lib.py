"""
Functions to be remotely executed in Blender via python_server.py

Remote execution relies on source code extractiona and transmission to the
execution sever, so each function must contain its imports
"""


def connect():
    import bpy

    bpy.ops.mixer.connect()


def disconnect():
    import bpy

    bpy.ops.mixer.disconnect()


def create_room():
    import bpy

    bpy.ops.mixer.create_room()


def set_log_level(log_level):
    from mixer.bl_preferences import set_log_level

    set_log_level(None, log_level)


def join_room(room_name: str = "mixer_unittest"):
    from mixer.blender_client import join_room

    join_room(room_name)


def keep_room_open(room_name: str = "mixer_unittest", keep_open: bool = False):
    from mixer.share_data import share_data

    share_data.client.set_room_keep_open(room_name, keep_open)
