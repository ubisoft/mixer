
"""
Functions to be remotely executed in Blender via python_server.py

Remote execution relies on source code extractiona and transmission to the
execution sever, so each function must contain its imports
"""


def connect():
    import bpy
    bpy.ops.dcc_sync.connect()


def create_room():
    import bpy
    bpy.ops.dcc_sync.create_room()


def join_room():
    import dccsync
    dccsync.operators.join_room('plop')
