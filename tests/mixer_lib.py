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


def set_log_level(log_level):
    from mixer.bl_preferences import set_log_level

    set_log_level(None, log_level)


def create_room(room_name: str = "mixer_unittest", experimental_sync: bool = False):
    from mixer.connection import join_room

    join_room(room_name, experimental_sync)


def join_room(room_name: str = "mixer_unittest", experimental_sync: bool = False):
    from mixer.connection import join_room
    from mixer.broadcaster.common import RoomAttributes
    from mixer.share_data import share_data
    from mixer.blender_client.client import clear_scene_content
    import sys
    import time

    # prevent sending our contents in case of cross join. Easier to diagnose the problem
    clear_scene_content()

    start = time.monotonic()
    max_wait = 30

    def wait_joinable():
        share_data.client.send_list_rooms()
        joinable = False
        while not joinable and time.monotonic() - start < max_wait:
            time.sleep(0.1)
            share_data.client.fetch_incoming_commands()
            room_attributes = share_data.client.rooms_attributes.get(room_name)
            if room_attributes is not None:
                joinable = room_attributes.get(RoomAttributes.JOINABLE, False)

        return room_attributes is not None and room_attributes.get(RoomAttributes.JOINABLE, False)

    if wait_joinable():
        join_room(room_name, experimental_sync)
    else:
        print(f"ERROR: Cannot join room after {max_wait} seconds. Abort")
        time.sleep(5)
        sys.exit(1)


def keep_room_open(room_name: str = "mixer_unittest", keep_open: bool = False):
    from mixer.share_data import share_data

    share_data.client.set_room_keep_open(room_name, keep_open)
