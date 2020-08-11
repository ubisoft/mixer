"""
This module define how the addon connect and interact with the server, for the Mixer protocol.
It updates the addon state according to this connection.
"""

import logging

import bpy
from mixer.bl_utils import get_mixer_prefs
from mixer.share_data import share_data
from mixer.broadcaster.common import ClientAttributes, ClientDisconnectedException
import subprocess
import time
from pathlib import Path

from mixer.stats import save_statistics, get_stats_filename
from mixer.blender_data.blenddata import BlendData
from mixer.draw_handlers import remove_draw_handlers
from mixer.blender_client import SendSceneContentFailed, BlenderClient
from mixer.handlers import HandlerManager


logger = logging.getLogger(__name__)


def set_client_attributes():
    prefs = get_mixer_prefs()
    username = prefs.user
    usercolor = prefs.color
    share_data.client.set_client_attributes(
        {ClientAttributes.USERNAME: username, ClientAttributes.USERCOLOR: list(usercolor)}
    )


def join_room(room_name: str):
    logger.info("join_room")

    assert share_data.client.current_room is None
    BlendData.instance().reset()
    share_data.session_id += 1
    # todo tech debt -> current_room should be set when JOIN_ROOM is received
    # todo _joining_room_name should be set in client timer
    share_data.client.current_room = room_name
    share_data.client._joining_room_name = room_name
    set_client_attributes()
    share_data.client.join_room(room_name)
    share_data.client.send_set_current_scene(bpy.context.scene.name_full)

    share_data.current_statistics = {
        "session_id": share_data.session_id,
        "blendfile": bpy.data.filepath,
        "statsfile": get_stats_filename(share_data.run_id, share_data.session_id),
        "user": get_mixer_prefs().user,
        "room": room_name,
        "children": {},
    }
    prefs = get_mixer_prefs()
    share_data.auto_save_statistics = prefs.auto_save_statistics
    share_data.statistics_directory = prefs.statistics_directory
    share_data.set_experimental_sync(prefs.experimental_sync)
    share_data.pending_test_update = False

    # join a room <==> want to track local changes
    HandlerManager.set_handlers(True)


def leave_current_room():
    logger.info("leave_current_room")

    if share_data.client and share_data.client.current_room:
        share_data.leave_current_room()
        HandlerManager.set_handlers(False)

    share_data.clear_before_state()

    if share_data.current_statistics is not None and share_data.auto_save_statistics:
        save_statistics(share_data.current_statistics, share_data.statistics_directory)
    share_data.current_statistics = None
    share_data.auto_save_statistics = False
    share_data.statistics_directory = None


def is_joined():
    connected = share_data.client is not None and share_data.client.is_connected()
    return connected and share_data.client.current_room


def wait_for_server(host, port):
    attempts = 0
    max_attempts = 10
    while not create_main_client(host, port) and attempts < max_attempts:
        attempts += 1
        time.sleep(0.2)
    return attempts < max_attempts


def start_local_server():
    import mixer

    dir_path = Path(mixer.__file__).parent.parent  # broadcaster is submodule of mixer

    if get_mixer_prefs().show_server_console:
        args = {"creationflags": subprocess.CREATE_NEW_CONSOLE}
    else:
        args = {}

    share_data.local_server_process = subprocess.Popen(
        [bpy.app.binary_path_python, "-m", "mixer.broadcaster.apps.server", "--port", str(get_mixer_prefs().port)],
        cwd=dir_path,
        shell=False,
        **args,
    )


def is_localhost(host):
    # does not catch local address
    return host == "localhost" or host == "127.0.0.1"


def connect():
    logger.info("connect")
    BlendData.instance().reset()
    if share_data.client is not None:
        # a server shutdown was not processed
        logger.debug("connect: share_data.client is not None")
        share_data.client = None

    prefs = get_mixer_prefs()
    if not create_main_client(prefs.host, prefs.port):
        if is_localhost(prefs.host):
            start_local_server()
            if not wait_for_server(prefs.host, prefs.port):
                raise RuntimeError("Unable to start local server")
        else:
            raise RuntimeError(f"Unable to connect to remote server {prefs.host}:{prefs.port}")

    assert is_client_connected()

    set_client_attributes()


def disconnect():
    from mixer.bl_panels import update_ui_lists

    logger.info("disconnect")

    leave_current_room()
    BlendData.instance().reset()

    remove_draw_handlers()

    if bpy.app.timers.is_registered(network_consumer_timer):
        bpy.app.timers.unregister(network_consumer_timer)

    # the socket has already been disconnected
    if share_data.client is not None:
        if share_data.client.is_connected():
            share_data.client.disconnect()
        share_data.client = None

    update_ui_lists()


def is_client_connected():
    return share_data.client is not None and share_data.client.is_connected()


def network_consumer_timer():
    if not share_data.client.is_connected():
        error_msg = "Timer still registered but client disconnected."
        logger.error(error_msg)
        if get_mixer_prefs().env != "production":
            raise RuntimeError(error_msg)
        # Returning None from a timer unregister it
        return None

    # Encapsulate call to share_data.client.network_consumer because
    # if we register it directly, then bpy.app.timers.is_registered(share_data.client.network_consumer)
    # return False...
    # However, with a simple function bpy.app.timers.is_registered works.
    try:
        share_data.client.network_consumer()
    except (ClientDisconnectedException, SendSceneContentFailed) as e:
        logger.warning(e)
        share_data.client = None
        disconnect()
        return None
    except Exception as e:
        logger.error(e, stack_info=True)
        if get_mixer_prefs().env == "development":
            raise

    # Run every 1 / 100 seconds
    return 0.01


def create_main_client(host: str, port: int):
    if share_data.client is not None:
        # a server shutdown was not processed
        logger.debug("create_main_client: share_data.client is not None")
        share_data.client = None

    client = BlenderClient(host, port)
    client.connect()
    if not client.is_connected():
        return False

    share_data.client = client
    if not bpy.app.timers.is_registered(network_consumer_timer):
        bpy.app.timers.register(network_consumer_timer)

    return True
