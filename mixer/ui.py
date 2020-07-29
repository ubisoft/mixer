from __future__ import annotations
from typing import TYPE_CHECKING

import bpy
import os
import logging
from mixer import operators
from mixer.bl_utils import get_mixer_props, get_mixer_prefs
from mixer.bl_properties import UserItem
from mixer.share_data import share_data
from mixer.broadcaster.common import ClientAttributes
from mixer.blender_data.debug_addon import DebugDataPanel
from mixer import __version__

if TYPE_CHECKING:
    from mixer.bl_preferences import MixerPreferences

logger = logging.getLogger(__name__)


def redraw():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                for region in area.regions:
                    if region.type == "UI":
                        region.tag_redraw()
                        break


def redraw_if(condition: bool):
    if condition:
        redraw()


def update_ui_lists():
    update_room_list(do_redraw=False)
    update_user_list()


def update_user_list(do_redraw=True):
    props = get_mixer_props()
    props.users.clear()
    if share_data.client is None:
        redraw_if(do_redraw)
        return

    for client_id, client in share_data.client.clients_attributes.items():
        item = props.users.add()
        item.is_me = client_id == share_data.client.client_id
        item.name = client.get(ClientAttributes.USERNAME, "<unamed>")
        item.ip = client.get(ClientAttributes.IP, "")
        item.port = client.get(ClientAttributes.PORT, 0)
        item.ip_port = f"{item.ip}:{item.port}"
        item.room = client.get(ClientAttributes.ROOM, "<no room>") or "<no room>"
        item.internal_color = client.get(ClientAttributes.USERCOLOR, (0, 0, 0))
        if "blender_windows" in client:
            for window in client["blender_windows"]:
                window_item = item.windows.add()
                window_item.scene = window["scene"]
                window_item.view_layer = window["view_layer"]
                window_item.screen = window["screen"]
                window_item.areas_3d_count = len(window["areas_3d"])
        if ClientAttributes.USERSCENES in client:
            for scene_name, scene_dict in client[ClientAttributes.USERSCENES].items():
                scene_item = item.scenes.add()
                scene_item.scene = scene_name
                if ClientAttributes.USERSCENES_FRAME in scene_dict:
                    scene_item.frame = scene_dict[ClientAttributes.USERSCENES_FRAME]

    redraw_if(do_redraw)


def update_room_list(do_redraw=True):
    props = get_mixer_props()
    props.rooms.clear()
    if share_data.client is None:
        redraw_if(do_redraw)
        return

    for room_name, _ in share_data.client.rooms_attributes.items():
        item = props.rooms.add()
        item.name = room_name
        if share_data.client is not None:
            item.users_count = len(
                [
                    client
                    for client in share_data.client.clients_attributes.values()
                    if client.get(ClientAttributes.ROOM, None) == room_name
                ]
            )
        else:
            item.users_count = -1

    redraw_if(do_redraw)


def collapsable_panel(
    layout: bpy.types.UILayout, data: bpy.types.AnyType, property: str, alert: bool = False, **kwargs
):
    row = layout.row()
    row.prop(
        data, property, icon="TRIA_DOWN" if getattr(data, property) else "TRIA_RIGHT", icon_only=True, emboss=False,
    )
    if alert:
        row.alert = True
    row.label(**kwargs)
    return getattr(data, property)


class ROOM_UL_ItemRenderer(bpy.types.UIList):  # noqa
    @classmethod
    def draw_header(cls, layout):
        row = layout.row()
        row.prop(get_mixer_props(), "display_rooms_details")
        box = layout.box()
        split = box.split()
        split.alignment = "CENTER"
        split.label(text="Name")
        split.label(text="Users")
        split.label(text="Experimental Sync")
        split.label(text="Keep Open")
        if get_mixer_props().display_rooms_details:
            split.label(text="Command Count")
            split.label(text="Size (MB)")
            split.label(text="Joinable")

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split()
        split.label(text=item.name)  # avoids renaming the item by accident
        split.label(text=f"{item.users_count if item.users_count >= 0 else '?'} users")
        split.prop(item, "experimental_sync", text="")
        split.prop(item, "keep_open", text="")
        if get_mixer_props().display_rooms_details:
            split.prop(item, "command_count", text="")
            split.prop(item, "mega_byte_size", text="")
            split.prop(item, "joinable", text="")


def draw_user_settings_ui(layout: bpy.types.UILayout):
    mixer_prefs = get_mixer_prefs()
    layout.prop(mixer_prefs, "user")
    layout.prop(mixer_prefs, "color", text="")


def draw_connection_settings_ui(layout: bpy.types.UILayout):
    mixer_prefs = get_mixer_prefs()
    layout.prop(mixer_prefs, "host")
    layout.prop(mixer_prefs, "port")


def draw_advanced_settings_ui(layout: bpy.types.UILayout):
    mixer_prefs = get_mixer_prefs()
    layout.prop(mixer_prefs, "log_level")
    layout.prop(mixer_prefs, "env")
    layout.prop(mixer_prefs, "show_server_console")


def draw_developer_settings_ui(layout: bpy.types.UILayout):
    mixer_prefs = get_mixer_prefs()
    layout.prop(mixer_prefs, "statistics_directory", text="Stats Directory")
    layout.operator(operators.OpenStatsDirOperator.bl_idname, text="Open Directory")
    layout.operator(operators.WriteStatisticsOperator.bl_idname, text="Write Statistics")
    layout.prop(mixer_prefs, "auto_save_statistics", text="Auto Save Statistics")
    layout.prop(mixer_prefs, "no_send_scene_content", text="No send_scene_content")
    layout.prop(mixer_prefs, "send_base_meshes", text="Send Base Meshes")
    layout.prop(mixer_prefs, "send_baked_meshes", text="Send Baked Meshes")
    layout.prop(mixer_prefs, "commands_send_interval")

    box = layout.box().column()
    box.label(text="Gizmos")
    box.prop(mixer_prefs, "display_own_gizmos")
    box.prop(mixer_prefs, "display_frustums_gizmos")
    box.prop(mixer_prefs, "display_names_gizmos")
    box.prop(mixer_prefs, "display_ids_gizmos")
    box.prop(mixer_prefs, "display_selections_gizmos")


def draw_preferences_ui(mixer_prefs: MixerPreferences, context: bpy.types.Context):
    mixer_prefs.layout.prop(mixer_prefs, "category")

    layout = mixer_prefs.layout.box().column()
    layout.label(text="Connection Settings")
    draw_user_settings_ui(layout.row())
    draw_connection_settings_ui(layout.row())

    layout = mixer_prefs.layout.box().column()
    layout.label(text="Room Settings")
    layout.prop(mixer_prefs, "room", text="Default Room Name")
    layout.prop(mixer_prefs, "experimental_sync")

    layout = mixer_prefs.layout.box().column()
    layout.label(text="Advanced Settings")
    draw_advanced_settings_ui(layout)

    layout = mixer_prefs.layout.box().column()
    layout.label(text="Developer Settings")
    draw_developer_settings_ui(layout)


class MixerSettingsPanel(bpy.types.Panel):
    bl_label = f"Mixer {__version__}"
    bl_idname = "MIXER_PT_mixer_settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Mixer"

    def draw_users(self, layout):
        mixer_props = get_mixer_props()

        def is_user_displayed(user: UserItem):
            if mixer_props.display_users_filter == "all":
                return True
            if mixer_props.display_users_filter == "no_room":
                return user.room == ""
            if mixer_props.display_users_filter == "current_room":
                return user.room == share_data.client.current_room or (
                    share_data.client.current_room is None and user.room == ""
                )
            if mixer_props.display_users_filter == "selected_room":
                if mixer_props.room_index >= 0 and mixer_props.room_index < len(mixer_props.rooms):
                    return user.room == mixer_props.rooms[mixer_props.room_index].name
                return user.room == ""

        collapsable_panel(layout, mixer_props, "display_users", text="Server Users")
        if mixer_props.display_users:
            box = layout.box()
            box.row().prop(mixer_props, "display_users_details")
            box.row().prop(mixer_props, "display_users_filter", expand=True)
            for user in (user for user in mixer_props.users if is_user_displayed(user)):
                user_layout = box
                if mixer_props.display_users_details:
                    user_layout = box.box()
                row = user_layout.split()
                row.label(text=f"{user.name}", icon="HOME" if user.is_me else "NONE")
                row.label(text=f"{user.room}")
                row.prop(user, "color", text="")
                if mixer_props.display_users_details:
                    row.label(text=f"{user.ip_port}")
                    window_count = len(user.windows)
                    row.label(text=f"{window_count} window{'s' if window_count > 1 else ''}")

                    frame_of_scene = {}
                    for scene in user.scenes:
                        frame_of_scene[scene.scene] = scene.frame

                    for window in user.windows:
                        split = user_layout.split(align=True)
                        split.label(text="  ")
                        split.label(text=window.scene, icon="SCENE_DATA")
                        split.label(text=str(frame_of_scene[window.scene]), icon="TIME")
                        split.label(text=window.view_layer, icon="RENDERLAYERS")
                        split.label(text=window.screen, icon="SCREEN_BACK")
                        split.label(text=f"{window.areas_3d_count}", icon="VIEW_CAMERA")
                        split.scale_y = 0.5
                    user_layout.separator(factor=0.2)

        if collapsable_panel(
            layout, mixer_props, "display_snapping_options", alert=True, text=f"Sync Options - Not implemented yet"
        ):
            box = layout.box().column()
            if share_data.client.current_room is None:
                box.label(text="You must join a room to select sync options")
            else:
                row = box.row()
                row.prop(mixer_props, "snap_view_user_enabled", text="3D View: ")
                row.prop(mixer_props, "snap_view_user", text="", icon="USER")
                row.prop(mixer_props, "snap_view_area", text="", icon="VIEW_CAMERA")
                row = box.row()
                row.prop(mixer_props, "snap_time_user_enabled", text="Time: ")
                row.prop(mixer_props, "snap_time_user", text="", icon="USER")
                row = box.row()
                row.prop(mixer_props, "snap_3d_cursor_user_enabled", text="3D Cursor: ")
                row.prop(mixer_props, "snap_3d_cursor_user", text="", icon="USER")

    def connected(self):
        return share_data.client is not None and share_data.client.is_connected()

    def draw(self, context):
        layout = self.layout.column()

        mixer_prefs = get_mixer_prefs()

        draw_user_settings_ui(layout.row())

        if not self.connected():
            draw_connection_settings_ui(layout.row())
            layout.operator(operators.ConnectOperator.bl_idname, text="Connect")
        else:
            layout.label(
                text=f"Connected to {mixer_prefs.host}:{mixer_prefs.port} with ID {share_data.client.client_id}"
            )
            layout.operator(operators.DisconnectOperator.bl_idname, text="Disconnect")

            if not operators.share_data.client.current_room:
                split = layout.split(factor=0.6)
                split.prop(mixer_prefs, "room", text="Room")
                split.operator(operators.CreateRoomOperator.bl_idname)
                row = layout.row()
                row.prop(
                    mixer_prefs,
                    "experimental_sync",
                    text="Experimental sync (should be checked/unchecked before joining room)",
                )
            else:
                split = layout.split(factor=0.6)
                split.label(
                    text=f"Room: {share_data.client.current_room}{(' (experimental sync)' if mixer_prefs.experimental_sync else '')}"
                )
                split.operator(operators.LeaveRoomOperator.bl_idname, text=f"Leave Room")

            self.draw_rooms(layout)
            self.draw_users(layout)

        self.draw_advanced_options(layout)
        self.draw_developer_options(layout)

    def draw_rooms(self, layout):
        mixer_props = get_mixer_props()
        if collapsable_panel(layout, mixer_props, "display_rooms", text="Server Rooms"):
            layout = layout.box().column()
            ROOM_UL_ItemRenderer.draw_header(layout)
            layout.template_list("ROOM_UL_ItemRenderer", "", mixer_props, "rooms", mixer_props, "room_index", rows=2)
            if share_data.client.current_room is None:
                layout.operator(operators.JoinRoomOperator.bl_idname)
            else:
                layout.operator(operators.LeaveRoomOperator.bl_idname)
            if collapsable_panel(layout, mixer_props, "display_advanced_room_control", text="Advanced room controls"):
                box = layout.box()
                col = box.column()
                col.operator(operators.DeleteRoomOperator.bl_idname)
                col.operator(operators.DownloadRoomOperator.bl_idname)
                subbox = col.box()
                subbox.row().operator(operators.UploadRoomOperator.bl_idname)
                row = subbox.row()
                row.prop(mixer_props, "upload_room_name", text="Name")
                row.prop(
                    mixer_props,
                    "upload_room_filepath",
                    text="File",
                    icon=("ERROR" if not os.path.exists(mixer_props.upload_room_filepath) else "NONE"),
                )

    def draw_advanced_options(self, layout):
        mixer_props = get_mixer_props()
        collapsable_panel(layout, mixer_props, "display_advanced_options", text="Advanced options")
        if mixer_props.display_advanced_options:
            draw_advanced_settings_ui(layout.box().column())

    def draw_developer_options(self, layout):
        mixer_props = get_mixer_props()
        if collapsable_panel(layout, mixer_props, "display_developer_options", text="Developer options"):
            draw_developer_settings_ui(layout.box().column())


class VRtistSettingsPanel(bpy.types.Panel):
    bl_label = "VRtist"
    bl_idname = "MIXER_PT_vrtist_settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Mixer"

    def draw(self, context):
        layout = self.layout
        mixer_prefs = get_mixer_prefs()
        layout.prop(
            mixer_prefs, "VRtist", text="Path", icon=("ERROR" if not os.path.exists(mixer_prefs.VRtist) else "NONE")
        )
        layout.operator(operators.LaunchVRtistOperator.bl_idname, text="Launch VRTist")


panels = (
    MixerSettingsPanel,
    VRtistSettingsPanel,
    DebugDataPanel,
)


def update_panels_category(self, context):
    mixer_prefs = get_mixer_prefs()
    try:
        for panel in panels:
            if "bl_rna" in panel.__dict__:
                bpy.utils.unregister_class(panel)

        for panel in panels:
            panel.bl_category = mixer_prefs.category
            bpy.utils.register_class(panel)

    except Exception as e:
        logger.error(f"Updating Panel category has failed {e}")


classes = (ROOM_UL_ItemRenderer, MixerSettingsPanel, VRtistSettingsPanel)
register_factory, unregister_factory = bpy.utils.register_classes_factory(classes)


def register():
    register_factory()
    update_panels_category(None, None)


def unregister():
    unregister_factory()
