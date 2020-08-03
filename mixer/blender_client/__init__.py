import logging
import os
import struct
from typing import Set, Tuple, Optional

import bpy
from mathutils import Matrix, Quaternion
import mixer
from mixer import ui
from mixer.bl_utils import get_mixer_prefs, get_mixer_props
from mixer.share_data import share_data
from mixer.broadcaster import common
from mixer.broadcaster.common import ClientAttributes, MessageType, RoomAttributes
from mixer.broadcaster.client import Client
from mixer.blender_client import camera as camera_api
from mixer.blender_client import collection as collection_api
from mixer.blender_client import data as data_api
from mixer.blender_client import grease_pencil as grease_pencil_api
from mixer.blender_client import light as light_api
from mixer.blender_client import material as material_api
from mixer.blender_client import mesh as mesh_api
from mixer.blender_client import object_ as object_api
from mixer.blender_client import scene as scene_api
import mixer.shot_manager as shot_manager
from mixer.stats import stats_timer
from mixer.draw import set_draw_handlers
import itertools
import subprocess
import time
from pathlib import Path
from typing import Mapping, Any
from uuid import uuid4

from bpy.app.handlers import persistent

from mixer.share_data import object_visibility
from mixer.blender_client.camera import send_camera
from mixer.blender_client.light import send_light
from mixer.stats import StatsTimer, save_statistics, get_stats_filename
from mixer.blender_data.diff import BpyBlendDiff
from mixer.blender_data.filter import safe_context
from mixer.blender_data.blenddata import BlendData
from mixer.draw import remove_draw_handlers

_STILL_ACTIVE = 259

logger = logging.getLogger(__name__)


def get_target(region: bpy.types.Region, region_3d: bpy.types.RegionView3D, pixel_coords: Tuple[float, float]):
    from bpy_extras import view3d_utils

    view_vector = view3d_utils.region_2d_to_vector_3d(region, region_3d, pixel_coords)
    ray_origin = view3d_utils.region_2d_to_origin_3d(region, region_3d, pixel_coords)
    target = ray_origin + view_vector

    return [target.x, target.y, target.z]


def get_view_frustum_attributes(region: bpy.types.Region, region_3d: bpy.types.RegionView3D):
    from bpy_extras import view3d_utils

    width = region.width
    height = region.height

    eye = view3d_utils.region_2d_to_origin_3d(region, region_3d, (width * 0.5, height * 0.5))
    v1 = get_target(region, region_3d, (0, 0))  # bottom left
    v2 = get_target(region, region_3d, (width, 0))  # bottom right
    v3 = get_target(region, region_3d, (width, height))  # top right
    v4 = get_target(region, region_3d, (0, height))  # top left

    return {
        ClientAttributes.USERSCENES_VIEWS_EYE: list(eye),
        ClientAttributes.USERSCENES_VIEWS_TARGET: list(region_3d.view_location),
        ClientAttributes.USERSCENES_VIEWS_SCREEN_CORNERS: [v1, v2, v3, v4],
    }


class SendSceneContentFailed(Exception):
    pass


class BlenderClient(Client):
    def __init__(self, host=common.DEFAULT_HOST, port=common.DEFAULT_PORT):
        super(BlenderClient, self).__init__(host, port)

        self.textures: Set[str] = set()

        self.skip_next_depsgraph_update = False
        # skip_next_depsgraph_update is set to True in the main timer function when a received command
        # affect blender data and will trigger a depsgraph update; in that case we want to ignore it
        # because it will produce some kind of infinite recursive update
        self.block_signals = False
        # block_signals is set to True when our timer transforms received commands into scene updates

        self._joining: bool = False
        self._joining_room_name: Optional[str] = None
        self._received_command_count: int = 0
        self._received_byte_size: int = 0

    # returns the path of an object
    def get_object_path(self, obj):
        return mixer.blender_client.misc.get_object_path(obj)

    # get first collection
    def get_or_create_collection(self, name: str):
        collection = share_data.blender_collections.get(name)
        if not collection:
            collection = bpy.data.collections.new(name)
            share_data._blender_collections[name] = collection
            bpy.context.scene.collection.children.link(collection)
            share_data.update_collection_temporary_visibility(name)
        return collection

    def get_or_create_path(self, path, data=None) -> bpy.types.Object:
        return mixer.blender_client.misc.get_or_create_path(path, data)

    def get_or_create_object_data(self, path, data):
        return self.get_or_create_path(path, data)

    def get_or_create_mesh(self, mesh_name):
        me = share_data.blender_meshes.get(mesh_name)
        if not me:
            me = bpy.data.meshes.new(mesh_name)
            share_data._blender_meshes[me.name_full] = me
        return me

    def set_transform(self, obj, parent_inverse_matrix, basis_matrix, local_matrix):
        obj.matrix_parent_inverse = parent_inverse_matrix
        obj.matrix_basis = basis_matrix
        obj.matrix_local = local_matrix

    def build_matrix_from_components(self, translate, rotate, scale):
        t = Matrix.Translation(translate)
        r = Quaternion(rotate).to_matrix().to_4x4()
        s = Matrix()
        s[0][0] = scale[0]
        s[1][1] = scale[1]
        s[2][2] = scale[2]
        return s @ r @ t

    def decode_matrix(self, data, index):
        matrix_data, index = common.decode_matrix(data, index)
        m = Matrix()
        m.col[0] = matrix_data[0]
        m.col[1] = matrix_data[1]
        m.col[2] = matrix_data[2]
        m.col[3] = matrix_data[3]
        return m, index

    def build_transform(self, data):
        start = 0
        object_path, start = common.decode_string(data, start)
        parent_invert_matrix, start = self.decode_matrix(data, start)
        basis_matrix, start = self.decode_matrix(data, start)
        local_matrix, start = self.decode_matrix(data, start)

        try:
            obj = self.get_or_create_path(object_path)
        except KeyError:
            # Object doesn't exist anymore
            return
        if obj:
            self.set_transform(obj, parent_invert_matrix, basis_matrix, local_matrix)

    def build_rename(self, data):
        # Object rename, actually
        # renaming the data referenced by Object.data (Light, Camera, ...) is not supported
        old_path, index = common.decode_string(data, 0)
        new_path, index = common.decode_string(data, index)
        logger.info("build_rename %s into %s", old_path, new_path)
        old_name = old_path.split("/")[-1]
        new_name = new_path.split("/")[-1]
        share_data.blender_objects.get(old_name).name = new_name
        share_data.blender_objects_dirty = True
        share_data.old_objects = share_data.blender_objects

    def build_duplicate(self, data):
        src_path, index = common.decode_string(data, 0)
        dst_name, index = common.decode_string(data, index)
        basis_matrix, index = self.decode_matrix(data, index)

        try:
            obj = self.get_or_create_path(src_path)
            new_obj = obj.copy()
            new_obj.name = dst_name
            if hasattr(obj, "data"):
                new_obj.data = obj.data.copy()
                new_obj.data.name = dst_name
                new_obj.animation_data_clear()
            for collection in obj.users_collection:
                collection.objects.link(new_obj)

            self.set_transform(new_obj, obj.matrix_parent_invert, basis_matrix, obj.matrix_parent_invert @ basis_matrix)
        except Exception:
            pass

    def build_delete(self, data):
        path, _ = common.decode_string(data, 0)

        try:
            obj = share_data.blender_objects[path.split("/")[-1]]
        except KeyError:
            # Object doesn't exist anymore
            return
        del share_data._blender_objects[obj.name_full]
        bpy.data.objects.remove(obj, do_unlink=True)

    def build_send_to_trash(self, data):
        path, _ = common.decode_string(data, 0)
        obj = self.get_or_create_path(path)

        share_data.restore_to_collections[obj.name_full] = []
        restore_to = share_data.restore_to_collections[obj.name_full]
        for collection in obj.users_collection:
            restore_to.append(collection.name_full)
            collection.objects.unlink(obj)
        # collection = self.get_or_create_collection()
        # collection.objects.unlink(obj)
        trash_collection = self.get_or_create_collection("__Trash__")
        trash_collection.hide_viewport = True
        trash_collection.objects.link(obj)

    def build_restore_from_trash(self, data):
        name, index = common.decode_string(data, 0)
        path, index = common.decode_string(data, index)

        obj = share_data.blender_objects[name]
        trash_collection = self.get_or_create_collection("__Trash__")
        trash_collection.hide_viewport = True
        trash_collection.objects.unlink(obj)
        restore_to = share_data.restore_to_collections[obj.name_full]
        for collection_name in restore_to:
            collection = self.get_or_create_collection(collection_name)
            collection.objects.link(obj)
        del share_data.restore_to_collections[obj.name_full]
        if len(path) > 0:
            parent_name = path.split("/")[-1]
            obj.parent = share_data.blender_objects.get(parent_name, None)

    def get_transform_buffer(self, obj):
        path = self.get_object_path(obj)
        return (
            common.encode_string(path)
            + common.encode_matrix(obj.matrix_parent_inverse)
            + common.encode_matrix(obj.matrix_basis)
            + common.encode_matrix(obj.matrix_local)
        )

    def send_transform(self, obj):
        transform_buffer = self.get_transform_buffer(obj)
        self.add_command(common.Command(MessageType.TRANSFORM, transform_buffer, 0))

    def build_texture_file(self, data):
        path, index = common.decode_string(data, 0)
        if not os.path.exists(path):
            size, index = common.decode_int(data, index)
            try:
                f = open(path, "wb")
                f.write(data[index : index + size])
                f.close()
                self.textures.add(path)
            except Exception as e:
                logger.error("could not write file %s ...", path)
                logger.error("... %s", e)

    def send_texture_file(self, path):
        if path in self.textures:
            return
        if os.path.exists(path):
            try:
                f = open(path, "rb")
                data = f.read()
                f.close()
                self.send_texture_data(path, data)
            except Exception as e:
                logger.error("could not read file %s ...", path)
                logger.error("... %s", e)

    def send_texture_data(self, path, data):
        name_buffer = common.encode_string(path)
        self.textures.add(path)
        self.add_command(common.Command(MessageType.TEXTURE, name_buffer + common.encode_int(len(data)) + data, 0))

    def get_texture(self, inputs):
        if not inputs:
            return None
        if len(inputs.links) == 1:
            connected_node = inputs.links[0].from_node
            if type(connected_node).__name__ == "ShaderNodeTexImage":
                image = connected_node.image
                pack = image.packed_file
                path = bpy.path.abspath(image.filepath)
                path = path.replace("\\", "/")
                if pack:
                    self.send_texture_data(path, pack.data)
                else:
                    self.send_texture_file(path)
                return path
        return None

    def build_add_keyframe(self, data):
        index = 0
        name, index = common.decode_string(data, index)
        if name not in share_data.blender_objects:
            return name
        ob = share_data.blender_objects[name]
        channel, index = common.decode_string(data, index)
        channel_index, index = common.decode_int(data, index)
        frame, index = common.decode_int(data, index)
        value, index = common.decode_float(data, index)

        if not hasattr(ob, channel):
            ob = ob.data

        attr = getattr(ob, channel)
        if channel_index != -1:
            attr[channel_index] = value
        else:
            attr = value
        setattr(ob, channel, attr)
        ob.keyframe_insert(channel, frame=float(frame), index=channel_index)
        return name

    def build_remove_keyframe(self, data):
        index = 0
        name, index = common.decode_string(data, index)
        if name not in share_data.blender_objects:
            return name
        ob = share_data.blender_objects[name]
        channel, index = common.decode_string(data, index)
        channel_index, index = common.decode_int(data, index)
        if not hasattr(ob, channel):
            ob = ob.data
        ob.keyframe_delete(channel, index=channel_index)
        return name

    def build_query_object_data(self, data):
        index = 0
        name, index = common.decode_string(data, index)
        self.query_object_data(name)

    def build_clear_animations(self, data):
        index = 0
        name, index = common.decode_string(data, index)
        ob = share_data.blender_objects[name]
        ob.animation_data_clear()
        if ob.data:
            ob.data.animation_data_clear()

    def build_montage_mode(self, data):
        index = 0
        montage, index = common.decode_bool(data, index)
        winman = bpy.data.window_managers["WinMan"]
        if hasattr(winman, "UAS_shot_manager_handler_toggle"):
            winman.UAS_shot_manager_handler_toggle = montage

    def send_group_begin(self):
        # The integer sent is for future use: the server might fill it with the group size once all messages
        # have been received, and give the opportunity to future clients to know how many messages they need to process
        # in the group (en probably show a progress bar to their user if their is a lot of message, e.g. initial scene
        # creation)
        self.add_command(common.Command(MessageType.GROUP_BEGIN, common.encode_int(0)))

    def send_group_end(self):
        self.add_command(common.Command(MessageType.GROUP_END))

    def send_material(self, material):
        if not material:
            return
        if material.grease_pencil:
            grease_pencil_api.send_grease_pencil_material(self, material)
        else:
            self.add_command(common.Command(MessageType.MATERIAL, material_api.get_material_buffer(self, material), 0))

    def get_mesh_name(self, mesh):
        return mesh.name_full

    @stats_timer(share_data)
    def send_mesh(self, obj):
        logger.info("send_mesh %s", obj.name_full)
        mesh = obj.data
        mesh_name = self.get_mesh_name(mesh)
        path = self.get_object_path(obj)

        binary_buffer = common.encode_string(path) + common.encode_string(mesh_name)

        binary_buffer += mesh_api.encode_mesh(
            obj, get_mixer_prefs().send_base_meshes, get_mixer_prefs().send_baked_meshes
        )

        # For now include material slots in the same message, but maybe it should be a separated message
        # like Transform
        material_link_dict = {"OBJECT": 0, "DATA": 1}
        material_links = [material_link_dict[slot.link] for slot in obj.material_slots]
        assert len(material_links) == len(obj.data.materials)
        binary_buffer += struct.pack(f"{len(material_links)}I", *material_links)

        for slot in obj.material_slots:
            if slot.link == "DATA":
                binary_buffer += common.encode_string("")
            else:
                binary_buffer += common.encode_string(slot.material.name if slot.material is not None else "")

        self.add_command(common.Command(MessageType.MESH, binary_buffer, 0))

    @stats_timer(share_data)
    def build_mesh(self, command_data):
        index = 0

        path, index = common.decode_string(command_data, index)
        mesh_name, index = common.decode_string(command_data, index)
        logger.info("build_mesh %s", mesh_name)
        obj = self.get_or_create_object_data(path, self.get_or_create_mesh(mesh_name))
        if obj.mode == "EDIT":
            logger.error("Received a mesh for object %s while begin in EDIT mode, ignoring.", path)
            return

        if obj.data is None:
            logger.warning(f"build_mesh: obj.data is None for {obj}")
            return

        index = mesh_api.decode_mesh(self, obj, command_data, index)

        material_slot_count = len(obj.data.materials)
        material_link_dict = ["OBJECT", "DATA"]
        material_links = struct.unpack(f"{material_slot_count}I", command_data[index : index + 4 * material_slot_count])
        for link, slot in zip(material_links, obj.material_slots):
            slot.link = material_link_dict[link]
        index += 4 * material_slot_count

        for slot in obj.material_slots:
            material_name, index = common.decode_string(command_data, index)
            if slot.link == "OBJECT" and material_name != "":
                slot.material = material_api.get_or_create_material(material_name)

    def send_set_current_scene(self, name):
        buffer = common.encode_string(name)
        self.add_command(common.Command(MessageType.SET_SCENE, buffer, 0))

    def send_animation_buffer(self, obj_name, animation_data, channel_name, channel_index=-1):
        if not animation_data:
            return
        action = animation_data.action
        if not action:
            return
        for fcurve in action.fcurves:
            if fcurve.data_path == channel_name:
                if channel_index == -1 or fcurve.array_index == channel_index:
                    key_count = len(fcurve.keyframe_points)
                    times = []
                    values = []
                    for keyframe in fcurve.keyframe_points:
                        times.append(int(keyframe.co[0]))
                        values.append(keyframe.co[1])
                    buffer = (
                        common.encode_string(obj_name)
                        + common.encode_string(channel_name)
                        + common.encode_int(channel_index)
                        + common.int_to_bytes(key_count, 4)
                        + struct.pack(f"{len(times)}i", *times)
                        + struct.pack(f"{len(values)}f", *values)
                    )
                    self.add_command(common.Command(MessageType.CAMERA_ANIMATION, buffer, 0))
                    return

    def send_camera_animations(self, obj):
        self.send_animation_buffer(obj.name_full, obj.animation_data, "location", 0)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "location", 1)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "location", 2)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "rotation_euler", 0)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "rotation_euler", 1)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "rotation_euler", 2)
        self.send_animation_buffer(obj.name_full, obj.data.animation_data, "lens")

    def send_camera_attributes(self, obj):
        buffer = (
            common.encode_string(obj.name_full)
            + common.encode_float(obj.data.lens)
            + common.encode_float(obj.data.dof.aperture_fstop)
            + common.encode_float(obj.data.dof.focus_distance)
        )
        self.add_command(common.Command(MessageType.CAMERA_ATTRIBUTES, buffer, 0))

    def send_current_camera(self, camera_name):
        buffer = common.encode_string(camera_name)
        self.add_command(common.Command(MessageType.CURRENT_CAMERA, buffer, 0))

    def send_deleted_object(self, obj_name):
        self.send_delete(obj_name)

    def send_renamed_objects(self, old_name, new_name):
        if old_name != new_name:
            self.send_rename(old_name, new_name)

    def get_rename_buffer(self, old_name, new_name):
        encoded_old_name = old_name.encode()
        encoded_new_name = new_name.encode()
        buffer = (
            common.int_to_bytes(len(encoded_old_name), 4)
            + encoded_old_name
            + common.int_to_bytes(len(encoded_new_name), 4)
            + encoded_new_name
        )
        return buffer

    def send_rename(self, old_name, new_name):
        logger.info("send_rename %s into %s", old_name, new_name)
        self.add_command(common.Command(MessageType.RENAME, self.get_rename_buffer(old_name, new_name), 0))

    def get_delete_buffer(self, name):
        encoded_name = name.encode()
        buffer = common.int_to_bytes(len(encoded_name), 4) + encoded_name
        return buffer

    def send_delete(self, obj_name):
        logger.info("send_delate %s", obj_name)
        self.add_command(common.Command(MessageType.DELETE, self.get_delete_buffer(obj_name), 0))

    def on_connection_lost(self):
        share_data.client = None
        disconnect()

    def build_frame(self, data):
        start = 0
        frame, start = common.decode_int(data, start)
        if bpy.context.scene.frame_current != frame:
            previous_value = share_data.client.skip_next_depsgraph_update
            share_data.client.skip_next_depsgraph_update = False
            bpy.context.scene.frame_set(frame)
            share_data.client.skip_next_depsgraph_update = previous_value

    def send_frame(self, frame):
        self.add_command(common.Command(MessageType.FRAME, common.encode_int(frame), 0))

    def send_frame_start_end(self, start, end):
        self.add_command(
            common.Command(MessageType.FRAME_START_END, common.encode_int(start) + common.encode_int(end), 0)
        )

    def override_context(self):
        for window in bpy.context.window_manager.windows:
            for area in window.screen.areas:
                if area.type == "VIEW_3D":
                    override = bpy.context.copy()
                    override["window"] = window
                    override["screen"] = window.screen
                    override["area"] = window.screen.areas[0]
                    return override
        return None

    def build_play(self, command):
        ctx = self.override_context()
        if ctx:
            if not ctx["screen"].is_animation_playing:
                bpy.ops.screen.animation_play(ctx)

    def build_pause(self, command):
        ctx = self.override_context()
        if ctx:
            if ctx["screen"].is_animation_playing:
                bpy.ops.screen.animation_play(ctx)

    def query_object_data(self, object_name):
        previous_value = share_data.client.skip_next_depsgraph_update
        share_data.client.skip_next_depsgraph_update = False

        if object_name not in share_data.blender_objects:
            return
        ob = share_data.blender_objects[object_name]
        update_params(ob)

        share_data.client.skip_next_depsgraph_update = previous_value

    def query_current_frame(self):
        share_data.client.send_frame(bpy.context.scene.frame_current)

    def compute_client_custom_attributes(self):
        scene_attributes = {}
        for scene in bpy.data.scenes:
            scene_attributes[scene.name_full] = {ClientAttributes.USERSCENES_FRAME: scene.frame_current}
            scene_selection = set()
            for obj in scene.objects:
                for view_layer in scene.view_layers:
                    if obj.select_get(view_layer=view_layer):
                        scene_selection.add(obj.name_full)
            scene_attributes[scene.name_full][ClientAttributes.USERSCENES_SELECTED_OBJECTS] = list(scene_selection)
            scene_attributes[scene.name_full][ClientAttributes.USERSCENES_VIEWS] = dict()

        # Send information about opened windows and 3d areas
        # Will server later to display view frustums of users
        windows = []
        for wm in bpy.data.window_managers:
            for window in wm.windows:
                areas_3d = []
                scene = window.scene.name_full
                view_layer = window.view_layer.name
                screen = window.screen.name_full
                for area in window.screen.areas:
                    if area.type == "VIEW_3D":
                        for region in area.regions:
                            if region.type == "WINDOW":
                                view_id = str(area.as_pointer())
                                view_dict = get_view_frustum_attributes(region, area.spaces.active.region_3d)
                                scene_attributes[scene][ClientAttributes.USERSCENES_VIEWS][view_id] = view_dict
                                areas_3d.append(view_id)
                windows.append({"scene": scene, "view_layer": view_layer, "screen": screen, "areas_3d": areas_3d})

        return {"blender_windows": windows, common.ClientAttributes.USERSCENES: scene_attributes}

    @stats_timer(share_data)
    def network_consumer(self):
        assert self.is_connected()

        set_draw_handlers()

        # Loop remains infinite while we have GROUP_BEGIN commands without their corresponding GROUP_END received
        # todo Change this -> probably not a good idea because the sending client might disconnect before GROUP_END occurs
        # or it needs to be guaranteed by the server
        group_count = 0
        while True:
            received_commands = self.fetch_commands(get_mixer_prefs().commands_send_interval)
            if received_commands is None:
                self.on_connection_lost()
                break

            set_dirty = True
            # Process all received commands
            for command in received_commands:
                if self._joining and command.type.value > common.MessageType.COMMAND.value:
                    self._received_byte_size += command.byte_size()
                    self._received_command_count += 1
                    if self._joining_room_name in self.rooms_attributes:
                        get_mixer_props().joining_percentage = (
                            self._received_byte_size
                            / self.rooms_attributes[self._joining_room_name][RoomAttributes.BYTE_SIZE]
                        )
                        ui.redraw()

                if command.type == MessageType.GROUP_BEGIN:
                    group_count += 1
                    continue

                if command.type == MessageType.GROUP_END:
                    group_count -= 1
                    continue

                if self.has_default_handler(command.type):
                    if command.type == MessageType.JOIN_ROOM and self._joining:
                        self._joining = False
                        get_mixer_props().joining_percentage = 1

                    ui.update_ui_lists()
                    self.block_signals = False  # todo investigate why we should but this to false here
                    continue

                if set_dirty:
                    share_data.set_dirty()
                    set_dirty = False

                self.block_signals = True

                try:
                    if command.type == MessageType.CONTENT:
                        # The server asks for scene content (at room creation)
                        try:
                            assert share_data.client.current_room is not None
                            self.set_room_attributes(
                                share_data.client.current_room,
                                {"experimental_sync": get_mixer_prefs().experimental_sync},
                            )
                            send_scene_content()
                            # Inform end of content
                            self.add_command(common.Command(MessageType.CONTENT))
                        except Exception as e:
                            self.on_connection_lost()
                            raise SendSceneContentFailed() from e
                        continue

                    # Put this to true by default
                    # todo Check build commands that do not trigger depsgraph update
                    # because it can lead to ignoring real updates when a false positive is encountered
                    command_triggers_depsgraph_update = True

                    if command.type == MessageType.GREASE_PENCIL_MESH:
                        grease_pencil_api.build_grease_pencil_mesh(command.data)
                    elif command.type == MessageType.GREASE_PENCIL_MATERIAL:
                        grease_pencil_api.build_grease_pencil_material(command.data)
                    elif command.type == MessageType.GREASE_PENCIL_CONNECTION:
                        grease_pencil_api.build_grease_pencil_connection(command.data)

                    elif command.type == MessageType.CLEAR_CONTENT:
                        clear_scene_content()
                        self._joining = True
                        self._received_command_count = 0
                        self._received_byte_size = 0
                        get_mixer_props().joining_percentage = 0
                        ui.redraw()
                    elif command.type == MessageType.MESH:
                        self.build_mesh(command.data)
                    elif command.type == MessageType.TRANSFORM:
                        self.build_transform(command.data)
                    elif command.type == MessageType.MATERIAL:
                        material_api.build_material(command.data)
                    elif command.type == MessageType.ASSIGN_MATERIAL:
                        material_api.build_assign_material(command.data)
                    elif command.type == MessageType.DELETE:
                        self.build_delete(command.data)
                    elif command.type == MessageType.CAMERA:
                        camera_api.build_camera(command.data)
                    elif command.type == MessageType.LIGHT:
                        light_api.build_light(command.data)
                    elif command.type == MessageType.RENAME:
                        self.build_rename(command.data)
                    elif command.type == MessageType.DUPLICATE:
                        self.build_duplicate(command.data)
                    elif command.type == MessageType.SEND_TO_TRASH:
                        self.build_send_to_trash(command.data)
                    elif command.type == MessageType.RESTORE_FROM_TRASH:
                        self.build_restore_from_trash(command.data)
                    elif command.type == MessageType.TEXTURE:
                        self.build_texture_file(command.data)

                    elif command.type == MessageType.COLLECTION:
                        collection_api.build_collection(command.data)
                    elif command.type == MessageType.COLLECTION_REMOVED:
                        collection_api.build_collection_removed(command.data)

                    elif command.type == MessageType.INSTANCE_COLLECTION:
                        collection_api.build_collection_instance(command.data)

                    elif command.type == MessageType.ADD_COLLECTION_TO_COLLECTION:
                        collection_api.build_collection_to_collection(command.data)
                    elif command.type == MessageType.REMOVE_COLLECTION_FROM_COLLECTION:
                        collection_api.build_remove_collection_from_collection(command.data)
                    elif command.type == MessageType.ADD_OBJECT_TO_COLLECTION:
                        collection_api.build_add_object_to_collection(command.data)
                    elif command.type == MessageType.REMOVE_OBJECT_FROM_COLLECTION:
                        collection_api.build_remove_object_from_collection(command.data)

                    elif command.type == MessageType.ADD_COLLECTION_TO_SCENE:
                        scene_api.build_collection_to_scene(command.data)
                    elif command.type == MessageType.REMOVE_COLLECTION_FROM_SCENE:
                        scene_api.build_remove_collection_from_scene(command.data)
                    elif command.type == MessageType.ADD_OBJECT_TO_SCENE:
                        scene_api.build_add_object_to_scene(command.data)
                    elif command.type == MessageType.REMOVE_OBJECT_FROM_SCENE:
                        scene_api.build_remove_object_from_scene(command.data)

                    elif command.type == MessageType.SCENE:
                        scene_api.build_scene(command.data)
                    elif command.type == MessageType.SCENE_REMOVED:
                        scene_api.build_scene_removed(command.data)
                    elif command.type == MessageType.SCENE_RENAMED:
                        scene_api.build_scene_renamed(command.data)

                    elif command.type == MessageType.OBJECT_VISIBILITY:
                        object_api.build_object_visibility(command.data)

                    elif command.type == MessageType.FRAME:
                        self.build_frame(command.data)
                    elif command.type == MessageType.QUERY_CURRENT_FRAME:
                        self.query_current_frame()

                    elif command.type == MessageType.PLAY:
                        self.build_play(command.data)
                    elif command.type == MessageType.PAUSE:
                        self.build_pause(command.data)
                    elif command.type == MessageType.ADD_KEYFRAME:
                        self.build_add_keyframe(command.data)
                    elif command.type == MessageType.REMOVE_KEYFRAME:
                        self.build_remove_keyframe(command.data)
                    elif command.type == MessageType.QUERY_OBJECT_DATA:
                        self.build_query_object_data(command.data)

                    elif command.type == MessageType.CLEAR_ANIMATIONS:
                        self.build_clear_animations(command.data)
                    elif command.type == MessageType.SHOT_MANAGER_MONTAGE_MODE:
                        self.build_montage_mode(command.data)
                    elif command.type == MessageType.SHOT_MANAGER_ACTION:
                        shot_manager.build_shot_manager_action(command.data)

                    elif command.type == MessageType.BLENDER_DATA_UPDATE:
                        data_api.build_data_update(command.data)
                    elif command.type == MessageType.BLENDER_DATA_REMOVE:
                        data_api.build_data_remove(command.data)
                    else:
                        # Command is ignored, so no depsgraph update can be triggered
                        command_triggers_depsgraph_update = False

                    if command_triggers_depsgraph_update:
                        self.skip_next_depsgraph_update = True

                except Exception as e:
                    logger.warning(f"Exception during processing of message {str(command.type)} ...\n", stack_info=True)
                    if get_mixer_prefs().env == "development" or isinstance(e, SendSceneContentFailed):
                        raise

                self.block_signals = False

            if group_count == 0:
                break

        if not set_dirty:
            share_data.update_current_data()

        # Some objects may have been obtained before their parent
        # In that case we resolve parenting here
        # todo Parenting strategy should be changed: we should store the name of the parent in the command instead of
        # having a path as name
        if len(share_data.pending_parenting) > 0:
            remaining_parentings = set()
            for path in share_data.pending_parenting:
                path_elem = path.split("/")
                ob = None
                parent = None
                for elem in path_elem:
                    ob = share_data.blender_objects.get(elem)
                    if not ob:
                        remaining_parentings.add(path)
                        break
                    if ob.parent != parent:  # do it only if needed, otherwise it resets matrix_parent_inverse
                        ob.parent = parent
                    parent = ob
            share_data.pending_parenting = remaining_parentings

        self.set_client_attributes(self.compute_client_custom_attributes())


class HandlerManager:
    """Manages Blender handlers activation state

    HandlerManager.set_handlers(wanted_state) will enable or disable the handlers activation and
    should be used for initial or final state handling when enterring or leaving a room.

    Temporary activation or desactivation should be performed using
        with HandlerManager.set_handlers(wanted_state):
            do_something()
    """

    _current_state = False

    def __init__(self, wanted_state: bool):
        self._wanted_state = wanted_state
        self._enter_state = None

    def __enter__(self):
        self._enter_state = HandlerManager._current_state
        if self._wanted_state != self._enter_state:
            self._set_handlers(self._wanted_state)
            HandlerManager._current_state = self._wanted_state
        return self

    def __exit__(self, *exc):
        if self._current_state != self._enter_state:
            self._set_handlers(self._enter_state)
            HandlerManager._current_state = self._enter_state
        return False

    @classmethod
    def _set_handlers(cls, connect: bool):
        try:
            if connect:
                bpy.app.handlers.frame_change_post.append(handler_send_frame_changed)
                bpy.app.handlers.depsgraph_update_post.append(handler_send_scene_data_to_server)
                bpy.app.handlers.undo_pre.append(on_undo_redo_pre)
                bpy.app.handlers.redo_pre.append(on_undo_redo_pre)
                bpy.app.handlers.undo_post.append(on_undo_redo_post)
                bpy.app.handlers.redo_post.append(on_undo_redo_post)
                bpy.app.handlers.load_post.append(on_load)
            else:
                bpy.app.handlers.load_post.remove(on_load)
                bpy.app.handlers.frame_change_post.remove(handler_send_frame_changed)
                bpy.app.handlers.depsgraph_update_post.remove(handler_send_scene_data_to_server)
                bpy.app.handlers.undo_pre.remove(on_undo_redo_pre)
                bpy.app.handlers.redo_pre.remove(on_undo_redo_pre)
                bpy.app.handlers.undo_post.remove(on_undo_redo_post)
                bpy.app.handlers.redo_post.remove(on_undo_redo_post)

                remove_draw_handlers()
        except Exception as e:
            logger.error("Exception during set_handlers(%s) : %s", connect, e)

    @classmethod
    def set_handlers(cls, wanted_state: bool):
        if wanted_state != cls._current_state:
            cls._set_handlers(wanted_state)
            cls._current_state = wanted_state


@persistent
def handler_send_frame_changed(scene):
    logger.debug("handler_send_frame_changed")
    if share_data.client.block_signals:
        logger.debug("handler_send_frame_changed canceled (block_signals = True)")
        return

    send_frame_changed(scene)


@persistent
def handler_send_scene_data_to_server(scene, dummy):
    logger.debug("handler_send_scene_data_to_server")

    # Ensure we will rebuild accessors when a depsgraph update happens
    # todo investigate why we need this...
    share_data.set_dirty()

    if share_data.client.block_signals:
        logger.debug("handler_send_scene_data_to_server canceled (block_signals = True)")
        return

    send_scene_data_to_server(scene, dummy)


class TransformStruct:
    def __init__(self, translate, quaternion, scale, visible):
        self.translate = translate
        self.quaternion = quaternion
        self.scale = scale
        self.visible = visible


def update_params(obj):
    # send collection instances
    if obj.instance_type == "COLLECTION":
        collection_api.send_collection_instance(share_data.client, obj)
        return

    if not hasattr(obj, "data"):
        return

    typename = obj.bl_rna.name
    if obj.data:
        typename = obj.data.bl_rna.name

    supported_lights = ["Sun Light", "Point Light", "Spot Light", "Area Light"]
    if (
        typename != "Camera"
        and typename != "Mesh"
        and typename != "Curve"
        and typename != "Text Curve"
        and typename != "Grease Pencil"
        and typename not in supported_lights
    ):
        return

    if typename == "Camera":
        send_camera(share_data.client, obj)

    if typename in supported_lights:
        send_light(share_data.client, obj)

    if typename == "Grease Pencil":
        for material in obj.data.materials:
            share_data.client.send_material(material)
        grease_pencil_api.send_grease_pencil_mesh(share_data.client, obj)
        grease_pencil_api.send_grease_pencil_connection(share_data.client, obj)

    if typename == "Mesh" or typename == "Curve" or typename == "Text Curve":
        if obj.mode == "OBJECT":
            share_data.client.send_mesh(obj)


def update_transform(obj):
    share_data.client.send_transform(obj)


def update_frame_start_end():
    if bpy.context.scene.frame_start != share_data.start_frame or bpy.context.scene.frame_end != share_data.end_frame:
        share_data.client.send_frame_start_end(bpy.context.scene.frame_start, bpy.context.scene.frame_end)
        share_data.start_frame = bpy.context.scene.frame_start
        share_data.end_frame = bpy.context.scene.frame_end


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


@persistent
def on_load(scene):
    logger.info("on_load")

    disconnect()


def get_scene(scene_name):
    return share_data.blender_scenes.get(scene_name)


def get_collection(collection_name):
    """
    May only return a non master collection
    """
    return share_data.blender_collections.get(collection_name)


def get_parent_collections(collection_name):
    """
    May return a master or non master collection
    """
    parents = []
    for col in share_data.blender_collections.values():
        children_names = {x.name_full for x in col.children}
        if collection_name in children_names:
            parents.append(col)
    return parents


def find_renamed(items_before: Mapping[Any, Any], items_after: Mapping[Any, Any]):
    """
    Split before/after mappings into added/removed/renamed

    Rename detection is based on the mapping keys (e.g. uuids)
    """
    uuids_before = {uuid for uuid in items_before.keys()}
    uuids_after = {uuid for uuid in items_after.keys()}
    renamed_uuids = {uuid for uuid in uuids_after & uuids_before if items_before[uuid] != items_after[uuid]}
    added_items = [items_after[uuid] for uuid in uuids_after - uuids_before - renamed_uuids]
    removed_items = [items_before[uuid] for uuid in uuids_before - uuids_after - renamed_uuids]
    renamed_items = [(items_before[uuid], items_after[uuid]) for uuid in renamed_uuids]
    return added_items, removed_items, renamed_items


def update_scenes_state():
    """
    Must be called before update_collections_state so that non empty collections added to master
    collection are processed
    """

    for scene in share_data.blender_scenes.values():
        if not scene.mixer_uuid:
            scene.mixer_uuid = str(uuid4())

    scenes_after = {
        scene.mixer_uuid: name
        for name, scene in share_data.blender_scenes.items()
        if name != "__last_scene_to_be_removed__"
    }
    scenes_before = {
        scene.mixer_uuid: name
        for name, scene in share_data.scenes_info.items()
        if name != "__last_scene_to_be_removed__"
    }
    share_data.scenes_added, share_data.scenes_removed, share_data.scenes_renamed = find_renamed(
        scenes_before, scenes_after
    )

    for old_name, new_name in share_data.scenes_renamed:
        share_data.scenes_info[new_name] = share_data.scenes_info[old_name]
        del share_data.scenes_info[old_name]

    # walk the old scenes
    for scene_name, scene_info in share_data.scenes_info.items():
        scene = get_scene(scene_name)
        if not scene:
            continue
        scene_name = scene.name_full
        old_children = set(scene_info.children)
        new_children = {x.name_full for x in scene.collection.children}

        for x in new_children - old_children:
            share_data.collections_added_to_scene.add((scene_name, x))

        for x in old_children - new_children:
            share_data.collections_removed_from_scene.add((scene_name, x))

        old_objects = {share_data.objects_renamed.get(x, x) for x in scene_info.objects}
        new_objects = {x.name_full for x in scene.collection.objects}

        added_objects = list(new_objects - old_objects)
        if len(added_objects) > 0:
            share_data.objects_added_to_scene[scene_name] = added_objects

        removed_objects = list(old_objects - new_objects)
        if len(removed_objects) > 0:
            share_data.objects_removed_from_scene[scene_name] = removed_objects

    # now the new scenes (in case of rename)
    for scene_name in share_data.scenes_added:
        scene = get_scene(scene_name)
        if not scene:
            continue
        new_children = {x.name_full for x in scene.collection.children}
        for x in new_children:
            share_data.collections_added_to_scene.add((scene_name, x))

        added_objects = {x.name_full for x in scene.collection.objects}
        if len(added_objects) > 0:
            share_data.objects_added_to_scene[scene_name] = added_objects


def update_collections_state():
    """
    Update non master collection state
    """
    new_collections_names = share_data.blender_collections.keys()
    old_collections_names = share_data.collections_info.keys()

    share_data.collections_added |= new_collections_names - old_collections_names
    share_data.collections_removed |= old_collections_names - new_collections_names

    # walk the old collections
    for collection_name, collection_info in share_data.collections_info.items():
        collection = get_collection(collection_name)
        if not collection:
            continue
        old_children = set(collection_info.children)
        new_children = {x.name_full for x in collection.children}

        for x in new_children - old_children:
            share_data.collections_added_to_collection.add((collection.name_full, x))

        for x in old_children - new_children:
            share_data.collections_removed_from_collection.add((collection_name, x))

        new_objects = {x.name_full for x in collection.objects}
        old_objects = {share_data.objects_renamed.get(x, x) for x in collection_info.objects}

        added_objects = [x for x in new_objects - old_objects]
        if len(added_objects) > 0:
            share_data.objects_added_to_collection[collection_name] = added_objects

        removed_objects = [x for x in old_objects - new_objects]
        if len(removed_objects) > 0:
            share_data.objects_removed_from_collection[collection_name] = removed_objects

    # now the new collections (in case of rename)
    for collection_name in share_data.collections_added:
        collection = get_collection(collection_name)
        if not collection:
            continue
        new_children = {x.name_full for x in collection.children}
        for x in new_children:
            share_data.collections_added_to_collection.add((collection.name_full, x))

        added_objects = {x.name_full for x in collection.objects}
        if len(added_objects) > 0:
            share_data.objects_added_to_collection[collection_name] = added_objects


def update_frame_changed_related_objects_state(old_objects: dict, new_objects: dict):
    for obj_name, matrix in share_data.objects_transforms.items():
        new_obj = share_data.old_objects.get(obj_name)
        if not new_obj:
            continue
        if new_obj.matrix_local != matrix:
            share_data.objects_transformed.add(obj_name)


@stats_timer(share_data)
def update_object_state(old_objects: dict, new_objects: dict):
    stats_timer = share_data.current_stats_timer

    with stats_timer.child("checkobjects_addedAndRemoved"):
        objects = set(new_objects.keys())
        share_data.objects_added = objects - old_objects.keys()
        share_data.objects_removed = old_objects.keys() - objects

    share_data.old_objects = new_objects

    if len(share_data.objects_added) == 1 and len(share_data.objects_removed) == 1:
        share_data.objects_renamed[list(share_data.objects_removed)[0]] = list(share_data.objects_added)[0]
        share_data.objects_added.clear()
        share_data.objects_removed.clear()
        return

    for obj_name in share_data.objects_removed:
        if obj_name in share_data.old_objects:
            del share_data.old_objects[obj_name]

    with stats_timer.child("updateObjectsParentingChanged"):
        for obj_name, parent in share_data.objects_parents.items():
            if obj_name not in share_data.old_objects:
                continue
            new_obj = share_data.old_objects[obj_name]
            new_obj_parent = "" if new_obj.parent is None else new_obj.parent.name_full
            if new_obj_parent != parent:
                share_data.objects_reparented.add(obj_name)

    with stats_timer.child("update_objects_visibilityChanged"):
        for obj_name, visibility in share_data.objects_visibility.items():
            new_obj = share_data.old_objects.get(obj_name)
            if not new_obj:
                continue
            if visibility != object_visibility(new_obj):
                share_data.objects_visibility_changed.add(obj_name)

    update_frame_changed_related_objects_state(old_objects, new_objects)


def is_in_object_mode():
    return not hasattr(bpy.context, "active_object") or (
        not bpy.context.active_object or bpy.context.active_object.mode == "OBJECT"
    )


def remove_objects_from_scenes():
    changed = False
    for scene_name, object_names in share_data.objects_removed_from_scene.items():
        for object_name in object_names:
            scene_api.send_remove_object_from_scene(share_data.client, scene_name, object_name)
            changed = True
    return changed


def remove_objects_from_collections():
    """
    Non master collections, actually
    """
    changed = False
    for collection_name, object_names in share_data.objects_removed_from_collection.items():
        for object_name in object_names:
            collection_api.send_remove_object_from_collection(share_data.client, collection_name, object_name)
            changed = True
    return changed


def remove_collections_from_scenes():
    changed = False
    for scene_name, collection_name in share_data.collections_removed_from_scene:
        scene_api.send_remove_collection_from_scene(share_data.client, scene_name, collection_name)
        changed = True
    return changed


def remove_collections_from_collections():
    """
    Non master collections, actually
    """
    changed = False
    for parent_name, child_name in share_data.collections_removed_from_collection:
        collection_api.send_remove_collection_from_collection(share_data.client, parent_name, child_name)
        changed = True
    return changed


def add_scenes():
    changed = False
    for scene in share_data.scenes_added:
        scene_api.send_scene(share_data.client, scene)
        changed = True
    for old_name, new_name in share_data.scenes_renamed:
        scene_api.send_scene_renamed(share_data.client, old_name, new_name)
        changed = True
    return changed


def remove_scenes():
    changed = False
    for scene in share_data.scenes_removed:
        scene_api.send_scene_removed(share_data.client, scene)
        changed = True
    return changed


def remove_collections():
    changed = False
    for collection in share_data.collections_removed:
        collection_api.send_collection_removed(share_data.client, collection)
        changed = True
    return changed


def add_objects():
    changed = False
    for obj_name in share_data.objects_added:
        obj = share_data.blender_objects.get(obj_name)
        if obj:
            update_params(obj)
            changed = True
    return changed


def update_transforms():
    changed = False
    for obj_name in share_data.objects_added:
        obj = share_data.blender_objects.get(obj_name)
        if obj:
            update_transform(obj)
            changed = True
    return changed


def add_collections():
    changed = False
    for item in share_data.collections_added:
        collection_api.send_collection(share_data.client, get_collection(item))
        changed = True
    return changed


def add_collections_to_collections():
    changed = False
    for parent_name, child_name in share_data.collections_added_to_collection:
        collection_api.send_add_collection_to_collection(share_data.client, parent_name, child_name)
        changed = True
    return changed


def add_collections_to_scenes():
    changed = False
    for scene_name, collection_name in share_data.collections_added_to_scene:
        scene_api.send_add_collection_to_scene(share_data.client, scene_name, collection_name)
        changed = True
    return changed


def add_objects_to_collections():
    changed = False
    for collection_name, object_names in share_data.objects_added_to_collection.items():
        for object_name in object_names:
            collection_api.send_add_object_to_collection(share_data.client, collection_name, object_name)
            changed = True
    return changed


def add_objects_to_scenes():
    changed = False
    for scene_name, object_names in share_data.objects_added_to_scene.items():
        for object_name in object_names:
            scene_api.send_add_object_to_scene(share_data.client, scene_name, object_name)
            changed = True
    return changed


def update_collections_parameters():
    changed = False
    for collection in share_data.blender_collections.values():
        info = share_data.collections_info.get(collection.name_full)
        if info:
            layer_collection = share_data.blender_layer_collections.get(collection.name_full)
            temporary_hidden = False
            if layer_collection:
                temporary_hidden = layer_collection.hide_viewport
            if (
                info.temporary_hide_viewport != temporary_hidden
                or info.hide_viewport != collection.hide_viewport
                or info.instance_offset != collection.instance_offset
            ):
                collection_api.send_collection(share_data.client, collection)
                changed = True
    return changed


def delete_scene_objects():
    changed = False
    for obj_name in share_data.objects_removed:
        share_data.client.send_deleted_object(obj_name)
        changed = True
    return changed


def rename_objects():
    changed = False
    for old_name, new_name in share_data.objects_renamed.items():
        share_data.client.send_renamed_objects(old_name, new_name)
        changed = True
    return changed


def update_objects_visibility():
    changed = False
    objects = itertools.chain(share_data.objects_added, share_data.objects_visibility_changed)
    for obj_name in objects:
        if obj_name in share_data.blender_objects:
            obj = share_data.blender_objects[obj_name]
            update_transform(obj)
            object_api.send_object_visibility(share_data.client, obj)
            changed = True
    return changed


def update_objects_transforms():
    # changed = False
    for obj_name in share_data.objects_transformed:
        if obj_name in share_data.blender_objects:
            update_transform(share_data.blender_objects[obj_name])
            # changed = True
    return False  # To allow mesh sending after "apply transform"


def reparent_objects():
    changed = False
    for obj_name in share_data.objects_reparented:
        obj = share_data.blender_objects.get(obj_name)
        if obj:
            update_transform(obj)
            changed = True
    return changed


def create_vrtist_objects():
    """
    VRtist will filter the received messages and handle only the objects that belong to the
    same scene as the one initially synchronized
    """
    changed = False
    for obj_name in share_data.objects_added:
        if obj_name in bpy.context.scene.objects:
            obj = bpy.context.scene.objects[obj_name]
            scene_api.send_add_object_to_vrtist(share_data.client, bpy.context.scene.name_full, obj.name_full)
            changed = True
    return changed


def update_objects_data():
    depsgraph = bpy.context.evaluated_depsgraph_get()

    if len(depsgraph.updates) == 0:
        return  # Exit here to avoid noise if you want to put breakpoints in this function

    data_container = {}
    data = set()
    transforms = set()

    for update in depsgraph.updates:
        obj = update.id.original
        typename = obj.bl_rna.name

        if typename == "Object":
            if hasattr(obj, "data"):
                if obj.data in data_container:
                    data_container[obj.data].append(obj)
                else:
                    data_container[obj.data] = [obj]
            if obj.name_full not in share_data.objects_transformed:
                transforms.add(obj)

        if (
            typename == "Camera"
            or typename == "Mesh"
            or typename == "Curve"
            or typename == "Text Curve"
            or typename == "Sun Light"
            or typename == "Point Light"
            or typename == "Spot Light"
            or typename == "Grease Pencil"
        ):
            data.add(obj)

        if typename == "Material":
            share_data.client.send_material(obj)

        if typename == "Scene":
            update_frame_start_end()
            shot_manager.update_scene()

    # Send transforms
    for obj in transforms:
        update_transform(obj)

    # Send data (mesh) of objects
    for d in data:
        container = data_container.get(d)
        if not container:
            continue
        for c in container:
            update_params(c)


def send_animated_camera_data():
    animated_camera_set = set()
    camera_dict = {}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for update in depsgraph.updates:
        obj = update.id.original
        typename = obj.bl_rna.name
        camera_action_name = ""
        if typename == "Object":
            if obj.data and obj.data.bl_rna.name == "Camera" and obj.animation_data is not None:
                camera_action_name = obj.animation_data.action.name_full
                camera_dict[camera_action_name] = obj
        if typename == "Action" and camera_dict.get(camera_action_name):
            animated_camera_set.add(camera_dict[camera_action_name])

    for camera in animated_camera_set:
        share_data.client.send_camera_attributes(camera)


def send_frame_changed(scene):
    logger.debug("send_frame_changed")

    if not share_data.client:
        logger.debug("send_frame_changed cancelled (no client instance)")
        return

    # We can arrive here because of scene deletion (bpy.ops.scene.delete({'scene': to_remove}) that happens during build_scene)
    # so we need to prevent processing self events
    if share_data.client.skip_next_depsgraph_update:
        share_data.client.skip_next_depsgraph_update = False
        logger.debug("send_frame_changed canceled (skip_next_depsgraph_update = True)")
        return

    if not is_in_object_mode():
        logger.debug("send_frame_changed canceled (not is_in_object_mode)")
        return

    with StatsTimer(share_data, "send_frame_changed") as timer:
        with timer.child("setFrame"):
            if not share_data.client.block_signals:
                share_data.client.send_frame(scene.frame_current)

        with timer.child("clear_lists"):
            share_data.clear_changed_frame_related_lists()

        with timer.child("update_frame_changed_related_objects_state"):
            update_frame_changed_related_objects_state(share_data.old_objects, share_data.blender_objects)

        with timer.child("checkForChangeAndSendUpdates"):
            update_objects_transforms()

        # update for next change
        with timer.child("update_objects_info"):
            share_data.update_objects_info()

        # temporary code :
        # animated parameters are not sent, we need camera animated parameters for VRtist
        # (focal lens etc.)
        # please remove this when animation is managed
        with timer.child("send_animated_camera_data"):
            send_animated_camera_data()

        with timer.child("send_current_camera"):
            scene_camera_name = ""
            if bpy.context.scene.camera is not None:
                scene_camera_name = bpy.context.scene.camera.name_full

            if share_data.current_camera != scene_camera_name:
                share_data.current_camera = scene_camera_name
                share_data.client.send_current_camera(share_data.current_camera)

        with timer.child("send_shot_manager_current_shot"):
            shot_manager.send_frame()


@stats_timer(share_data)
def send_scene_data_to_server(scene, dummy):
    logger.debug(
        "send_scene_data_to_server(): skip_next_depsgraph_update %s, pending_test_update %s",
        share_data.client.skip_next_depsgraph_update,
        share_data.pending_test_update,
    )

    timer = share_data.current_stats_timer

    if not share_data.client:
        logger.info("send_scene_data_to_server canceled (no client instance)")
        return

    share_data.set_dirty()
    with timer.child("clear_lists"):
        share_data.clear_lists()

    depsgraph = bpy.context.evaluated_depsgraph_get()
    if depsgraph.updates:
        logger.debug("Current dg updates ...")
        for update in depsgraph.updates:
            logger.debug(" ......%s", update.id.original)

    # prevent processing self events, but always process test updates
    if not share_data.pending_test_update and share_data.client.skip_next_depsgraph_update:
        share_data.client.skip_next_depsgraph_update = False
        logger.debug("send_scene_data_to_server canceled (skip_next_depsgraph_update = True) ...")
        return

    share_data.pending_test_update = False

    if not is_in_object_mode():
        logger.info("send_scene_data_to_server canceled (not is_in_object_mode)")
        return

    update_object_state(share_data.old_objects, share_data.blender_objects)

    with timer.child("update_scenes_state"):
        update_scenes_state()

    with timer.child("update_collections_state"):
        update_collections_state()

    changed = False
    with timer.child("checkForChangeAndSendUpdates"):
        changed |= remove_objects_from_collections()
        changed |= remove_objects_from_scenes()
        changed |= remove_collections_from_collections()
        changed |= remove_collections_from_scenes()
        changed |= remove_collections()
        changed |= remove_scenes()
        changed |= add_scenes()
        changed |= add_collections()
        changed |= add_objects()

        # Updates from the VRtist protocol and from the full Blender protocol must be cafully intermixed
        # This is an unfortunate requirements from the current coexistence status of
        # both protocols

        # After creation of meshes : meshes are not yet supported by full Blender protocol,
        # but needed to properly create objects
        # Before creation of objects :  the VRtint protocol  will implicitely create objects with
        # unappropriate default values (e.g. transform creates an object with no data)
        if share_data.use_experimental_sync():
            # Compute the difference between the proxy state and the Blender state
            # It is a coarse difference at the ID level(created, removed, renamed)
            diff = BpyBlendDiff()
            diff.diff(share_data.proxy, safe_context)

            # Ask the proxy to compute the list of elements to synchronize and update itself
            depsgraph = bpy.context.evaluated_depsgraph_get()
            updates, removals = share_data.proxy.update(diff, safe_context, depsgraph.updates)

            # Send the data update messages (includes serialization)
            data_api.send_data_removals(removals)
            data_api.send_data_updates(updates)
            share_data.proxy.debug_check_id_proxies()

        # send the VRtist transforms after full Blender protocol has the opportunity to create the object data
        # that is not handled by VRtist protocol, otherwise the receiver creates an empty when it receives a transform
        changed |= update_transforms()
        changed |= add_collections_to_scenes()
        changed |= add_collections_to_collections()
        changed |= add_objects_to_collections()
        changed |= add_objects_to_scenes()
        changed |= update_collections_parameters()
        changed |= create_vrtist_objects()
        changed |= delete_scene_objects()
        changed |= rename_objects()
        changed |= update_objects_visibility()
        changed |= update_objects_transforms()
        changed |= reparent_objects()
        changed |= shot_manager.check_montage_mode()

    if not changed:
        with timer.child("update_objects_data"):
            update_objects_data()

    # update for next change
    with timer.child("update_current_data"):
        share_data.update_current_data()

    logger.debug("send_scene_data_to_server: end")


@persistent
def on_undo_redo_pre(scene):
    logger.info("on_undo_redo_pre")
    send_scene_data_to_server(scene, None)


def remap_objects_info():
    # update objects references
    added_objects = set(share_data.blender_objects.keys()) - set(share_data.old_objects.keys())
    removed_objects = set(share_data.old_objects.keys()) - set(share_data.blender_objects.keys())
    # we are only able to manage one object rename
    if len(added_objects) == 1 and len(removed_objects) == 1:
        old_name = list(removed_objects)[0]
        new_name = list(added_objects)[0]

        visible = share_data.objects_visibility[old_name]
        del share_data.objects_visibility[old_name]
        share_data.objects_visibility[new_name] = visible

        parent = share_data.objects_parents[old_name]
        del share_data.objects_parents[old_name]
        share_data.objects_parents[new_name] = parent
        for name, parent in share_data.objects_parents.items():
            if parent == old_name:
                share_data.objects_parents[name] = new_name

        matrix = share_data.objects_transforms[old_name]
        del share_data.objects_transforms[old_name]
        share_data.objects_transforms[new_name] = matrix

    share_data.old_objects = share_data.blender_objects


@stats_timer(share_data)
@persistent
def on_undo_redo_post(scene, dummy):
    logger.info("on_undo_redo_post")

    share_data.set_dirty()
    share_data.clear_lists()
    # apply only in object mode
    if not is_in_object_mode():
        return

    old_objects_name = dict([(k, None) for k in share_data.old_objects.keys()])  # value not needed
    remap_objects_info()
    for k, v in share_data.old_objects.items():
        if k in old_objects_name:
            old_objects_name[k] = v

    update_object_state(old_objects_name, share_data.old_objects)

    update_collections_state()
    update_scenes_state()

    remove_objects_from_scenes()
    remove_objects_from_collections()
    remove_collections_from_scenes()
    remove_collections_from_collections()

    remove_collections()
    remove_scenes()
    add_scenes()
    add_objects()
    add_collections()

    add_collections_to_scenes()
    add_collections_to_collections()

    add_objects_to_collections()
    add_objects_to_scenes()

    update_collections_parameters()
    create_vrtist_objects()
    delete_scene_objects()
    rename_objects()
    update_objects_visibility()
    update_objects_transforms()
    reparent_objects()

    # send selection content (including data)
    materials = set()
    for obj in bpy.context.selected_objects:
        update_transform(obj)
        if hasattr(obj, "data"):
            update_params(obj)
        if hasattr(obj, "material_slots"):
            for slot in obj.material_slots[:]:
                materials.add(slot.material)

    for material in materials:
        share_data.client.send_material(material)

    share_data.update_current_data()


def clear_scene_content():
    with HandlerManager(False):

        data = [
            "cameras",
            "collections",
            "curves",
            "grease_pencils",
            "images",
            "lights",
            "objects",
            "materials",
            "metaballs",
            "meshes",
            "textures",
            "worlds",
            "sounds",
        ]

        for name in data:
            collection = getattr(bpy.data, name)
            for obj in collection:
                collection.remove(obj)

        # Cannot remove the last scene at this point, treat it differently
        for scene in bpy.data.scenes[:-1]:
            scene_api.delete_scene(scene)

        share_data.clear_before_state()

        if len(bpy.data.scenes) == 1:
            scene = bpy.data.scenes[0]
            scene.name = "__last_scene_to_be_removed__"


@stats_timer(share_data)
def send_scene_content():
    if get_mixer_prefs().no_send_scene_content:
        return

    with HandlerManager(False):
        # mesh baking may trigger depsgraph_updatewhen more than one view layer and
        # cause to reenter send_scene_data_to_server() and send duplicate messages

        share_data.clear_before_state()
        share_data.init_proxy()
        share_data.client.send_group_begin()

        # Temporary waiting for material sync. Should move to send_scene_data_to_server
        for material in bpy.data.materials:
            share_data.client.send_material(material)

        send_scene_data_to_server(None, None)

        shot_manager.send_scene()
        share_data.client.send_frame_start_end(bpy.context.scene.frame_start, bpy.context.scene.frame_end)
        share_data.start_frame = bpy.context.scene.frame_start
        share_data.end_frame = bpy.context.scene.frame_end
        share_data.client.send_frame(bpy.context.scene.frame_current)

        share_data.client.send_group_end()


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
                logger.error("Unable to start local server")
                return False
        else:
            logger.error("Unable to connect to remote server %s:%s", prefs.host, prefs.port)
            return False

    assert is_client_connected()

    set_client_attributes()

    return True


def disconnect():
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

    ui.update_ui_lists()
    ui.redraw()


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
    share_data.client.network_consumer()

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
