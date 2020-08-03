import os
import logging
import random

import bpy

from mixer.broadcaster import common
from mixer.broadcaster.common import ClientAttributes
from mixer.share_data import share_data
from mixer.stats import get_stats_directory
from mixer.bl_panels import draw_preferences_ui, update_panels_category

logger = logging.getLogger(__name__)


def gen_random_color():
    r = random.random()
    g = random.random()
    b = random.random()
    return [r, g, b]


def set_log_level(self, value):
    logging.getLogger(__package__).setLevel(value)
    logger.log(value, "Logging level changed")


class MixerPreferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    def on_user_changed(self, context):
        client = share_data.client
        if client and client.is_connected():
            client.set_client_attributes({ClientAttributes.USERNAME: self.user})

    def on_user_color_changed(self, context):
        client = share_data.client
        if client and client.is_connected():
            client.set_client_attributes({ClientAttributes.USERCOLOR: list(self.color)})

    category: bpy.props.StringProperty(
        name="Tab Category",
        description="Choose a name for the category of the panel.",
        default=os.environ.get("MIXER_CATEGORY", "Mixer"),
        update=update_panels_category,
    )

    # Allows to change behavior according to environment: production or development
    env: bpy.props.EnumProperty(
        name="Execution Environment",
        description="Execution environment: production, development or testing",
        items=[
            ("production", "production", "", 0),
            ("development", "development", "", 1),
            ("testing", "testing", "", 2),
        ],
        default=os.environ.get("MIXER_ENV", "production"),
    )

    host: bpy.props.StringProperty(name="Host", default=os.environ.get("VRTIST_HOST", common.DEFAULT_HOST))
    port: bpy.props.IntProperty(name="Port", default=int(os.environ.get("VRTIST_PORT", common.DEFAULT_PORT)))
    room: bpy.props.StringProperty(name="Room", default=os.environ.get("VRTIST_ROOM", os.getlogin()))

    # User name as displayed in peers user list
    user: bpy.props.StringProperty(name="User", default=os.getlogin(), update=on_user_changed)
    color: bpy.props.FloatVectorProperty(
        name="Color", subtype="COLOR", default=gen_random_color(), update=on_user_color_changed
    )

    def get_log_level(self):
        return logging.getLogger(__package__).level

    log_level: bpy.props.EnumProperty(
        name="Log Level",
        description="Logging level to use",
        items=[
            ("ERROR", "Error", "", logging.ERROR),
            ("WARNING", "Warning", "", logging.WARNING),
            ("INFO", "Info", "", logging.INFO),
            ("DEBUG", "Debug", "", logging.DEBUG),
        ],
        set=set_log_level,
        get=get_log_level,
    )

    experimental_sync: bpy.props.BoolProperty(
        name="Experimental sync", default=os.environ.get("MIXER_EXPERIMENTAL_SYNC") is not None
    )

    show_server_console: bpy.props.BoolProperty(name="Show Server Console", default=False)

    VRtist: bpy.props.StringProperty(
        name="VRtist", default=os.environ.get("VRTIST_EXE", "D:/unity/VRtist/Build/VRtist.exe"), subtype="FILE_PATH"
    )
    statistics_directory: bpy.props.StringProperty(
        name="Stats Directory", default=os.environ.get("MIXER_STATS_DIR", get_stats_directory()), subtype="FILE_PATH"
    )
    auto_save_statistics: bpy.props.BoolProperty(default=True)

    # Developer option to avoid sending scene content to server at the first connexion
    # Allow to quickly iterate debugging/test on large scenes with only one client in room
    # Main usage: optimization of client timers to check if updates are required
    no_send_scene_content: bpy.props.BoolProperty(default=False)

    send_base_meshes: bpy.props.BoolProperty(default=True)
    send_baked_meshes: bpy.props.BoolProperty(default=True)

    display_own_gizmos: bpy.props.BoolProperty(default=False, name="Display Own Gizmos")
    display_frustums_gizmos: bpy.props.BoolProperty(default=True, name="Display Frustums Gizmos")
    display_names_gizmos: bpy.props.BoolProperty(default=True, name="Display Name Gizmos")
    display_ids_gizmos: bpy.props.BoolProperty(default=False, name="Display ID Gizmos")
    display_selections_gizmos: bpy.props.BoolProperty(default=True, name="Display Selection Gizmos")

    commands_send_interval: bpy.props.FloatProperty(
        name="Command Send Interval",
        description="Debug tool to specify a number of seconds to wait between each command emission toward the server.",
        default=0,
    )

    def draw(self, context):
        draw_preferences_ui(self, context)


classes = (MixerPreferences,)

register_factory, unregister_factory = bpy.utils.register_classes_factory(classes)


def register():
    register_factory()


def unregister():
    unregister_factory()
