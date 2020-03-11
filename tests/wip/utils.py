import bpy


def get_dcc_sync_props():
    return bpy.context.window_manager.dcc_sync


def connect():
    bpy.ops.dcc_sync.connect('EXEC_DEFAULT')


def disconnect():
    bpy.ops.dcc_sync.disconnect('EXEC_DEFAULT')


def join(room: str = "TEST_ROOM"):
    props = get_dcc_sync_props()
    props.room = room
    bpy.ops.dcc_sync.create_room('EXEC_DEFAULT')
