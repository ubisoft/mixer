import bpy
import os
from mixer import operators
from mixer.data import get_mixer_props, get_mixer_prefs, UserItem
from mixer.share_data import share_data
from mixer.broadcaster.common import ClientMetadata

import logging

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
    if share_data.client_ids is None:
        redraw_if(do_redraw)
        return

    for client_id, client in share_data.client_ids.items():
        item = props.users.add()
        item.is_me = client_id == share_data.client.client_id
        item.name = (
            client[ClientMetadata.USERNAME]
            if (ClientMetadata.USERNAME in client and client[ClientMetadata.USERNAME])
            else "<unamed>"
        )
        item.ip = client[ClientMetadata.IP]
        item.port = client[ClientMetadata.PORT]
        item.ip_port = f"{item.ip}:{item.port}"
        item.room = client[ClientMetadata.ROOM] or ""
        item.internal_color = client[ClientMetadata.USERCOLOR] if ClientMetadata.USERCOLOR in client else (0, 0, 0)
        if "blender_windows" in client:
            for window in client["blender_windows"]:
                window_item = item.windows.add()
                window_item.scene = window["scene"]
                window_item.view_layer = window["view_layer"]
                window_item.screen = window["screen"]
                window_item.areas_3d_count = len(window["areas_3d"])
        if ClientMetadata.USERSCENES in client:
            for scene_name, scene_dict in client[ClientMetadata.USERSCENES].items():
                scene_item = item.scenes.add()
                scene_item.scene = scene_name
                if ClientMetadata.USERSCENES_FRAME in scene_dict:
                    scene_item.frame = scene_dict[ClientMetadata.USERSCENES_FRAME]

    redraw_if(do_redraw)


def update_room_list(do_redraw=True):
    props = get_mixer_props()
    props.rooms.clear()
    if share_data.rooms_dict is None:
        redraw_if(do_redraw)
        return

    for room_name, _ in share_data.rooms_dict.items():
        item = props.rooms.add()
        item.name = room_name
        item.users_count = len(
            [client for client in share_data.client_ids.values() if client[ClientMetadata.ROOM] == room_name]
        )

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

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        split = layout.split()
        split.label(text=item.name)  # avoids renaming the item by accident
        split.label(text=f"{item.users_count} users")
        split.prop(item, "experimental_sync", text="")
        split.prop(item, "keep_open", text="")
        if get_mixer_props().display_rooms_details:
            split.prop(item, "command_count", text="")
            split.prop(item, "mega_byte_size", text="")


class MixerSettingsPanel(bpy.types.Panel):
    bl_label = "Mixer"
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
                return user.room == share_data.current_room or (share_data.current_room is None and user.room == "")
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
                row.label(text=f"{(user.room or '<no room>')}")
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
            if share_data.current_room is None:
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

        row = layout.row()
        row.prop(mixer_prefs, "user", text="User")
        row.prop(mixer_prefs, "color", text="")

        if not self.connected():
            row = layout.row()
            row.prop(mixer_prefs, "host", text="Host")
            row.prop(mixer_prefs, "port", text="Port")
            layout.operator(operators.ConnectOperator.bl_idname, text="Connect")
        else:
            layout.label(
                text=f"Connected to {mixer_prefs.host}:{mixer_prefs.port} with ID {share_data.client.client_id}"
            )
            layout.operator(operators.DisconnectOperator.bl_idname, text="Disconnect")

            if not operators.share_data.current_room:
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
                    text=f"Room: {share_data.current_room}{(' (experimental sync)' if mixer_prefs.experimental_sync else '')}"
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
            if share_data.current_room is None:
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
        mixer_prefs = get_mixer_prefs()
        collapsable_panel(layout, mixer_props, "display_advanced_options", text="Advanced options")
        if mixer_props.display_advanced_options:
            col = layout.box().column()
            col.prop(mixer_prefs, "log_level", text="Log Level")
            col.prop(mixer_prefs, "env", text="Execution Environment")
            if not self.connected():
                col.prop(mixer_prefs, "show_server_console", text="Show server console (self hosting only)")

    def draw_developer_options(self, layout):
        mixer_props = get_mixer_props()
        mixer_prefs = get_mixer_prefs()
        if collapsable_panel(layout, mixer_props, "display_developer_options", text="Developer options"):
            col = layout.box().column()
            col.prop(mixer_prefs, "statistics_directory", text="Stats Directory")
            col.operator(operators.OpenStatsDirOperator.bl_idname, text="Open Directory")
            col.operator(operators.WriteStatisticsOperator.bl_idname, text="Write Statistics")
            col.prop(mixer_prefs, "auto_save_statistics", text="Auto Save Statistics")
            col.prop(mixer_prefs, "no_send_scene_content", text="No send_scene_content")
            col.prop(mixer_prefs, "send_base_meshes", text="Send Base Meshes")
            col.prop(mixer_prefs, "send_baked_meshes", text="Send Baked Meshes")
            col.prop(mixer_props, "commands_send_interval")

            box = col.box().column()
            box.label(text="Gizmos")
            box.prop(mixer_prefs, "display_own_gizmos")
            box.prop(mixer_prefs, "display_frustums_gizmos")
            box.prop(mixer_prefs, "display_names_gizmos")
            box.prop(mixer_prefs, "display_ids_gizmos")
            box.prop(mixer_prefs, "display_selections_gizmos")


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


classes = (ROOM_UL_ItemRenderer, MixerSettingsPanel, VRtistSettingsPanel)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():
    for _ in classes:
        bpy.utils.unregister_class(_)
