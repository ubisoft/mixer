# GPLv3 License
#
# Copyright (C) 2020 Ubisoft
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
This module define Blender Panels and UI types for the addon.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

import bpy

import os

import logging
from mixer import bl_operators
from mixer.bl_utils import get_mixer_props, get_mixer_prefs
from mixer.bl_properties import UserItem
from mixer.share_data import share_data
from mixer.broadcaster.common import ClientAttributes
from mixer.blender_data.debug_addon import DebugDataPanel, use_debug_addon
from mixer import display_version
from mixer import icons
from mixer.local_data import get_data_directory

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
        data,
        property,
        icon="TRIA_DOWN" if getattr(data, property) else "TRIA_RIGHT",
        icon_only=True,
        emboss=False,
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
        split.label(text="Keep Open")
        split.label(text="Blender Version")
        split.label(text="Mixer Version")
        if get_mixer_props().display_rooms_details:
            split.label(text="No Version Check")
            split.label(text="Protocol")
            split.label(text="Command Count")
            split.label(text="Size (MB)")
            split.label(text="Joinable")

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split()
        split.label(text=item.name)  # avoids renaming the item by accident
        split.label(text=f"{item.users_count if item.users_count >= 0 else '?'} users")
        split.prop(item, "keep_open", text="")
        split.label(text=item.blender_version)
        split.label(text=item.mixer_version)
        if get_mixer_props().display_rooms_details:
            split.prop(item, "ignore_version_check", text="")
            split.label(text=item.protocol)
            split.prop(item, "command_count", text="")
            split.prop(item, "mega_byte_size", text="")
            split.prop(item, "joinable", text="")


class SHAREDFOLDER_UL_ItemRenderer(bpy.types.UIList):  # noqa
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname):
        layout.prop(item, "shared_folder", text="", emboss=False, icon_value=icon)


def draw_user_settings_ui(layout: bpy.types.UILayout):
    mixer_prefs = get_mixer_prefs()

    col = layout.column()
    col.separator(factor=0.5)

    grid = col.column_flow(columns=2)
    row = grid.row()
    sub_row = row.row()
    sub_row.scale_x = 0.4
    sub_row.label(text="User:")
    row.prop(mixer_prefs, "user", text="")
    row = grid.row()
    row.prop(mixer_prefs, "color", text="")
    icon = icons.icons_col["General_Explorer_32"]
    user_data_path = os.environ.get("MIXER_DATA_DIR", get_data_directory())
    #   from pathlib import Path
    #   user_data_path = Path(user_data_path).parent
    row.operator("mixer.open_explorer", text="", icon_value=icon.icon_id).path = str(user_data_path)

    col.separator(factor=1.0)


def draw_connection_settings_ui(layout: bpy.types.UILayout):
    mixer_prefs = get_mixer_prefs()

    col = layout.column()
    col.separator(factor=0.5)

    grid = col.column_flow(columns=2)
    row = grid.row()
    sub_row = row.row()
    sub_row.scale_x = 0.4
    sub_row.label(text="Host:")
    row.prop(mixer_prefs, "host", text="")
    row = grid.row()
    row.prop(mixer_prefs, "port")

    col.separator(factor=0.5)


def draw_shared_folders_settings_ui(layout: bpy.types.UILayout):
    mixer_props = get_mixer_props()
    mixer_prefs = get_mixer_prefs()
    row = layout.row()
    row.template_list(
        "SHAREDFOLDER_UL_ItemRenderer", "", mixer_prefs, "shared_folders", mixer_props, "shared_folder_index", rows=4
    )
    col = row.column(align=True)
    col.operator(bl_operators.SharedFoldersAddFolderOperator.bl_idname, text="", icon="ADD")
    col.operator(bl_operators.SharedFoldersRemoveFolderOperator.bl_idname, text="", icon="REMOVE")


def draw_advanced_settings_ui(layout: bpy.types.UILayout):
    mixer_prefs = get_mixer_prefs()
    layout.prop(mixer_prefs, "data_directory", text="Data Directory")
    layout.prop(mixer_prefs, "ignore_version_check")
    layout.prop(mixer_prefs, "log_level")
    layout.prop(mixer_prefs, "show_server_console")
    layout.prop(mixer_prefs, "vrtist_protocol")


def draw_developer_settings_ui(layout: bpy.types.UILayout):
    mixer_prefs = get_mixer_prefs()
    layout.prop(mixer_prefs, "no_send_scene_content", text="No send_scene_content")
    layout.prop(mixer_prefs, "no_start_server", text="Do not start server on connect")
    layout.prop(mixer_prefs, "send_base_meshes", text="Send Base Meshes")
    layout.prop(mixer_prefs, "send_baked_meshes", text="Send Baked Meshes")
    layout.prop(mixer_prefs, "commands_send_interval")
    layout.prop(mixer_prefs, "display_own_gizmos")
    layout.prop(mixer_prefs, "display_ids_gizmos")


def draw_gizmos_settings_ui(layout: bpy.types.UILayout):
    mixer_prefs = get_mixer_prefs()
    layout.prop(mixer_prefs, "display_frustums_gizmos")
    layout.prop(mixer_prefs, "display_frustums_names_gizmos")
    layout.prop(mixer_prefs, "display_selections_gizmos")
    layout.prop(mixer_prefs, "display_selections_names_gizmos")


def draw_preferences_ui(mixer_prefs: MixerPreferences, context: bpy.types.Context):
    mixer_prefs.layout.prop(mixer_prefs, "category")

    layout = mixer_prefs.layout.box().column()
    layout.label(text="Connection Settings")
    draw_user_settings_ui(layout.row())
    draw_connection_settings_ui(layout.row())

    layout = mixer_prefs.layout.box().column()
    layout.label(text="Room Settings")
    layout.prop(mixer_prefs, "room", text="Default Room Name")

    layout = mixer_prefs.layout.box().column()
    layout.label(text="Gizmos")
    draw_gizmos_settings_ui(layout)

    layout = mixer_prefs.layout.box().column()
    layout.label(text="Advanced Settings")
    draw_advanced_settings_ui(layout)

    layout = mixer_prefs.layout.box().column()
    layout.label(text="Developer Settings")
    draw_developer_settings_ui(layout)


class MixerSettingsPanel(bpy.types.Panel):
    bl_label = f"Mixer {display_version or '(Unknown version)'}"
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

    def connected(self):
        return share_data.client is not None and share_data.client.is_connected()

    def draw_header(self, context):
        self.layout.emboss = "NONE"
        icon = icons.icons_col["Mixer_32"]
        row = self.layout.row(align=True)
        row.operator("mixer.about", text="", icon_value=icon.icon_id)

    def draw_header_preset(self, context):
        self.layout.emboss = "NONE"
        row = self.layout.row(align=True)
        row.menu("MIXER_MT_prefs_main_menu", icon="PREFERENCES", text="")
        row.separator(factor=1.0)

    def draw(self, context):
        layout = self.layout.column()

        mixer_prefs = get_mixer_prefs()

        draw_user_settings_ui(layout.row())

        if not self.connected():
            draw_connection_settings_ui(layout.row())
            row = layout.row()
            row.scale_y = 1.5
            row.operator(bl_operators.ConnectOperator.bl_idname, text="Connect")
            layout.separator(factor=1.0)
        else:
            layout.separator(factor=0.5)
            layout.label(
                text=f"Connected to  {mixer_prefs.host}:{mixer_prefs.port}  with ID  {share_data.client.client_id}"
            )

            row = layout.row()
            row.scale_y = 1.5
            row.operator(bl_operators.DisconnectOperator.bl_idname, text="Disconnect", depress=True)
            layout.separator(factor=2.0)

            if not share_data.client.current_room:

                grid = layout.column_flow(columns=2)
                row = grid.row()
                sub_row = row.row()
                sub_row.scale_x = 0.5
                sub_row.label(text="Room:")
                row.prop(mixer_prefs, "room", text="")
                row = grid.row()
                row.operator(bl_operators.CreateRoomOperator.bl_idname)
            else:
                split = layout.split(factor=0.6)
                split.label(text=f"Room: {share_data.client.current_room}")
                split.label(text=f"Join: {get_mixer_props().joining_percentage * 100:.2f} %")
                split.operator(bl_operators.LeaveRoomOperator.bl_idname, text="Leave Room", depress=True)

            self.draw_rooms(layout)
            self.draw_users(layout)

        self.draw_shared_folders_options(layout)
        if self.connected():
            self.draw_gizmos_options(layout)
        self.draw_advanced_options(layout)

    def draw_rooms(self, layout):
        mixer_props = get_mixer_props()
        if collapsable_panel(layout, mixer_props, "display_rooms", text="Server Rooms"):
            layout = layout.box().column()
            ROOM_UL_ItemRenderer.draw_header(layout)
            layout.template_list("ROOM_UL_ItemRenderer", "", mixer_props, "rooms", mixer_props, "room_index", rows=2)
            if share_data.client.current_room is None:
                layout.operator(bl_operators.JoinRoomOperator.bl_idname)
            else:
                layout.operator(bl_operators.LeaveRoomOperator.bl_idname)
            if collapsable_panel(layout, mixer_props, "display_advanced_room_control", text="Advanced Room Controls"):
                box = layout.box()
                col = box.column()
                col.operator(bl_operators.DeleteRoomOperator.bl_idname)
                col.operator(bl_operators.DownloadRoomOperator.bl_idname)
                subbox = col.box()
                subbox.row().operator(bl_operators.UploadRoomOperator.bl_idname)
                row = subbox.row()
                row.prop(mixer_props, "upload_room_name", text="Name")
                row.prop(
                    mixer_props,
                    "upload_room_filepath",
                    text="File",
                    icon=("ERROR" if not os.path.exists(mixer_props.upload_room_filepath) else "NONE"),
                )

    def draw_shared_folders_options(self, layout):
        mixer_props = get_mixer_props()
        collapsable_panel(layout, mixer_props, "display_shared_folders_options", text="Shared Folders")
        if mixer_props.display_shared_folders_options:
            draw_shared_folders_settings_ui(layout.box().column())

    def draw_gizmos_options(self, layout):
        mixer_props = get_mixer_props()
        collapsable_panel(layout, mixer_props, "display_gizmos_options", text="Gizmos")
        if mixer_props.display_gizmos_options:
            draw_gizmos_settings_ui(layout.box().column())

    def draw_advanced_options(self, layout):
        mixer_props = get_mixer_props()
        collapsable_panel(layout, mixer_props, "display_advanced_options", text="Advanced Options")
        if mixer_props.display_advanced_options:
            draw_advanced_settings_ui(layout.box().column())

    def draw_developer_options(self, layout):
        mixer_props = get_mixer_props()
        if collapsable_panel(layout, mixer_props, "display_developer_options", text="Developer Options"):
            draw_developer_settings_ui(layout.box().column())


class VRtistSettingsPanel(bpy.types.Panel):
    bl_label = "VRtist"
    bl_idname = "MIXER_PT_vrtist_settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "VRtist"

    def draw(self, context):
        layout = self.layout
        mixer_prefs = get_mixer_prefs()

        draw_user_settings_ui(layout.row())
        draw_connection_settings_ui(layout.row())
        layout.prop(mixer_prefs, "room", text="Room")

        layout.operator(bl_operators.LaunchVRtistOperator.bl_idname, text="Launch VRTist")
        layout.prop(
            mixer_prefs, "VRtist", text="Path", icon=("ERROR" if not os.path.exists(mixer_prefs.VRtist) else "NONE")
        )


panels = [
    MixerSettingsPanel,
    VRtistSettingsPanel,
]

if use_debug_addon:
    panels.append(DebugDataPanel)


def update_panels_category(self, context):
    mixer_prefs = get_mixer_prefs()
    try:
        for panel in panels:
            if "bl_rna" in panel.__dict__:
                bpy.utils.unregister_class(panel)

        for panel in panels:
            if panel.bl_label == "VRtist":
                panel.bl_category = mixer_prefs.vrtist_category
            else:
                panel.bl_category = mixer_prefs.category
            bpy.utils.register_class(panel)

    except Exception as e:
        logger.error(f"Updating Panel category has failed {e!r}")


classes = (ROOM_UL_ItemRenderer, SHAREDFOLDER_UL_ItemRenderer, MixerSettingsPanel, VRtistSettingsPanel)
register_factory, unregister_factory = bpy.utils.register_classes_factory(classes)


def register():
    register_factory()
    update_panels_category(None, None)


def unregister():
    unregister_factory()
