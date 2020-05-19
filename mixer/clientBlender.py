import logging
import struct
import os
from typing import Set

import bpy
from mathutils import Matrix, Quaternion
import mixer
from mixer import ui
from mixer import data
from mixer.share_data import share_data
from mixer.broadcaster import common
from mixer.broadcaster.client import Client
from mixer.blender_client import camera as camera_api
from mixer.blender_client import collection as collection_api
from mixer.blender_client import grease_pencil as grease_pencil_api
from mixer.blender_client import light as light_api
from mixer.blender_client import material as material_api
from mixer.blender_client import mesh as mesh_api
from mixer.blender_client import object_ as object_api
from mixer.blender_client import scene as scene_api
from mixer.stats import stats_timer

_STILL_ACTIVE = 259

logger = logging.getLogger(__name__)


class ClientBlender(Client):
    def __init__(self, host=common.DEFAULT_HOST, port=common.DEFAULT_PORT):
        super(ClientBlender, self).__init__(host, port)

        self.textures: Set[str] = set()
        self.callbacks = {}

        self.blenderPID = os.getpid()

    def add_callback(self, name, func):
        self.callbacks[name] = func

    # returns the path of an object
    def get_object_path(self, obj):
        return mixer.blender_client.misc.get_object_path(obj)

    # get first collection
    def get_or_create_collection(self, name: str):
        collection = share_data.blender_collections.get(name)
        if not collection:
            bpy.ops.collection.create(name=name)
            collection = bpy.data.collections[name]
            share_data._blender_collections[name] = collection
            bpy.context.scene.collection.children.link(collection)
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
        visible, start = common.decode_bool(data, start)

        try:
            obj = self.get_or_create_path(object_path)
        except KeyError:
            # Object doesn't exist anymore
            return
        if obj:
            self.set_transform(obj, parent_invert_matrix, basis_matrix, local_matrix)
            obj.hide_viewport = not visible

    def build_rename(self, data):
        old_path, index = common.decode_string(data, 0)
        new_path, index = common.decode_string(data, index)
        old_name = old_path.split("/")[-1]
        new_name = new_path.split("/")[-1]
        share_data.blender_objects.get(old_name).name = new_name

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
        visible = not obj.hide_viewport
        return (
            common.encode_string(path)
            + common.encode_matrix(obj.matrix_parent_inverse)
            + common.encode_matrix(obj.matrix_basis)
            + common.encode_matrix(obj.matrix_local)
            + common.encode_bool(visible)
        )

    def send_transform(self, obj):
        transform_buffer = self.get_transform_buffer(obj)
        self.add_command(common.Command(common.MessageType.TRANSFORM, transform_buffer, 0))

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
                logger.error("could not write file %s (%s)", path, e)

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
                logger.error("could not read file %s (%s)", path, e)

    def send_texture_data(self, path, data):
        name_buffer = common.encode_string(path)
        self.textures.add(path)
        self.add_command(
            common.Command(common.MessageType.TEXTURE, name_buffer + common.encode_int(len(data)) + data, 0)
        )

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

    def send_group_begin(self):
        # The integer sent is for future use: the server might fill it with the group size once all messages
        # have been received, and give the opportunity to future clients to know how many messages they need to process
        # in the group (en probably show a progress bar to their user if their is a lot of message, e.g. initial scene
        # creation)
        self.add_command(common.Command(common.MessageType.GROUP_BEGIN, common.encode_int(0)))

    def send_group_end(self):
        self.add_command(common.Command(common.MessageType.GROUP_END))

    def send_material(self, material):
        if not material:
            return
        if material.grease_pencil:
            grease_pencil_api.send_grease_pencil_material(self, material)
        else:
            self.add_command(
                common.Command(common.MessageType.MATERIAL, material_api.get_material_buffer(self, material), 0)
            )

    def get_mesh_name(self, mesh):
        return mesh.name_full

    @stats_timer(share_data)
    def send_mesh(self, obj):
        mesh = obj.data
        mesh_name = self.get_mesh_name(mesh)
        path = self.get_object_path(obj)

        binary_buffer = common.encode_string(path) + common.encode_string(mesh_name)

        binary_buffer += mesh_api.encode_mesh(
            obj, data.get_mixer_props().send_base_meshes, data.get_mixer_props().send_baked_meshes
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

        self.add_command(common.Command(common.MessageType.MESH, binary_buffer, 0))

    @stats_timer(share_data)
    def build_mesh(self, command_data):
        index = 0

        path, index = common.decode_string(command_data, index)
        mesh_name, index = common.decode_string(command_data, index)

        obj = self.get_or_create_object_data(path, self.get_or_create_mesh(mesh_name))
        if obj.mode == "EDIT":
            logger.error("Received a mesh for object %s while begin in EDIT mode, ignoring.", path)
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
                slot.material = self.get_or_create_material(material_name)

    def send_set_current_scene(self, name):
        buffer = common.encode_string(name)
        self.add_command(common.Command(common.MessageType.SET_SCENE, buffer, 0))

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
                    self.add_command(common.Command(common.MessageType.CAMERA_ANIMATION, buffer, 0))
                    return

    def send_camera_animations(self, obj):
        self.send_animation_buffer(obj.name_full, obj.animation_data, "location", 0)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "location", 1)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "location", 2)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "rotation_euler", 0)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "rotation_euler", 1)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "rotation_euler", 2)
        self.send_animation_buffer(obj.name_full, obj.data.animation_data, "lens")

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
        self.add_command(common.Command(common.MessageType.RENAME, self.get_rename_buffer(old_name, new_name), 0))

    def get_delete_buffer(self, name):
        encoded_name = name.encode()
        buffer = common.int_to_bytes(len(encoded_name), 4) + encoded_name
        return buffer

    def send_delete(self, obj_name):
        self.add_command(common.Command(common.MessageType.DELETE, self.get_delete_buffer(obj_name), 0))

    def send_list_rooms(self):
        self.add_command(common.Command(common.MessageType.LIST_ROOMS))

    def on_connection_lost(self):
        if "Disconnect" in self.callbacks:
            self.callbacks["Disconnect"]()

    def build_list_all_clients(self, client_ids):
        share_data.client_ids = client_ids
        ui.update_ui_lists()

    def send_scene_content(self):
        if "SendContent" in self.callbacks:
            self.callbacks["SendContent"]()

    def build_frame(self, data):
        start = 0
        frame, start = common.decode_int(data, start)
        bpy.context.scene.frame_current = frame

    def send_frame(self, frame):
        self.add_command(common.Command(common.MessageType.FRAME, common.encode_int(frame), 0))

    def send_frame_start_end(self, start, end):
        self.add_command(
            common.Command(common.MessageType.FRAME_START_END, common.encode_int(start) + common.encode_int(end), 0)
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

    def clear_content(self):
        if "ClearContent" in self.callbacks:
            self.callbacks["ClearContent"]()

    def query_object_data(self, object_name):
        previous_value = share_data.client.receivedCommandsProcessed
        share_data.client.receivedCommandsProcessed = False
        if "QueryObjectData" in self.callbacks:
            self.callbacks["QueryObjectData"](object_name)
        share_data.client.receivedCommandsProcessed = previous_value

    def query_current_frame(self):
        previous_value = share_data.client.receivedCommandsProcessed
        share_data.client.receivedCommandsProcessed = False
        if "QueryCurrentFrame" in self.callbacks:
            self.callbacks["QueryCurrentFrame"]()
        share_data.client.receivedCommandsProcessed = previous_value

    @stats_timer(share_data)
    def network_consumer(self):
        assert self.is_connected()

        group_count = 0

        # Loop remains infinite while we have GROUP_BEGIN commands without their corresponding GROUP_END received
        while True:
            self.fetch_commands()

            set_dirty = True
            # Process all received commands
            while True:
                command = self.get_next_received_command()
                if command is None:
                    break

                if command.type == common.MessageType.GROUP_BEGIN:
                    group_count += 1
                    continue

                if command.type == common.MessageType.GROUP_END:
                    group_count -= 1
                    continue

                processed = False
                if command.type == common.MessageType.LIST_ALL_CLIENTS:
                    clients, _ = common.decode_json(command.data, 0)
                    self.build_list_all_clients(clients)
                    processed = True
                elif command.type == common.MessageType.CONNECTION_LOST:
                    self.on_connection_lost()
                    break

                if set_dirty:
                    share_data.set_dirty()
                    set_dirty = False

                self.blockSignals = True
                self.receivedCommandsProcessed = True
                if processed:
                    # this was a room protocol command that was processed
                    self.receivedCommandsProcessed = False
                else:
                    if command.type == common.MessageType.CONTENT:
                        # The server asks for scene content (at room creation)
                        self.receivedCommandsProcessed = False
                        self.send_scene_content()

                    elif command.type == common.MessageType.GREASE_PENCIL_MESH:
                        grease_pencil_api.build_grease_pencil_mesh(command.data)
                    elif command.type == common.MessageType.GREASE_PENCIL_MATERIAL:
                        grease_pencil_api.build_grease_pencil_material(command.data)
                    elif command.type == common.MessageType.GREASE_PENCIL_CONNECTION:
                        grease_pencil_api.build_grease_pencil_connection(command.data)

                    elif command.type == common.MessageType.CLEAR_CONTENT:
                        self.clear_content()
                    elif command.type == common.MessageType.MESH:
                        self.build_mesh(command.data)
                    elif command.type == common.MessageType.TRANSFORM:
                        self.build_transform(command.data)
                    elif command.type == common.MessageType.MATERIAL:
                        material_api.build_material(command.data)
                    elif command.type == common.MessageType.ASSIGN_MATERIAL:
                        material_api.build_assign_material(command.data)
                    elif command.type == common.MessageType.DELETE:
                        self.build_delete(command.data)
                    elif command.type == common.MessageType.CAMERA:
                        camera_api.build_camera(command.data)
                    elif command.type == common.MessageType.LIGHT:
                        light_api.build_light(command.data)
                    elif command.type == common.MessageType.RENAME:
                        self.build_rename(command.data)
                    elif command.type == common.MessageType.DUPLICATE:
                        self.build_duplicate(command.data)
                    elif command.type == common.MessageType.SEND_TO_TRASH:
                        self.build_send_to_trash(command.data)
                    elif command.type == common.MessageType.RESTORE_FROM_TRASH:
                        self.build_restore_from_trash(command.data)
                    elif command.type == common.MessageType.TEXTURE:
                        self.build_texture_file(command.data)

                    elif command.type == common.MessageType.COLLECTION:
                        collection_api.build_collection(command.data)
                    elif command.type == common.MessageType.COLLECTION_REMOVED:
                        collection_api.build_collection_removed(command.data)

                    elif command.type == common.MessageType.INSTANCE_COLLECTION:
                        collection_api.build_collection_instance(command.data)

                    elif command.type == common.MessageType.ADD_COLLECTION_TO_COLLECTION:
                        collection_api.build_collection_to_collection(command.data)
                    elif command.type == common.MessageType.REMOVE_COLLECTION_FROM_COLLECTION:
                        collection_api.build_remove_collection_from_collection(command.data)
                    elif command.type == common.MessageType.ADD_OBJECT_TO_COLLECTION:
                        collection_api.build_add_object_to_collection(command.data)
                    elif command.type == common.MessageType.REMOVE_OBJECT_FROM_COLLECTION:
                        collection_api.build_remove_object_from_collection(command.data)

                    elif command.type == common.MessageType.ADD_COLLECTION_TO_SCENE:
                        scene_api.build_collection_to_scene(command.data)
                    elif command.type == common.MessageType.REMOVE_COLLECTION_FROM_SCENE:
                        scene_api.build_remove_collection_from_scene(command.data)
                    elif command.type == common.MessageType.ADD_OBJECT_TO_SCENE:
                        scene_api.build_add_object_to_scene(command.data)
                    elif command.type == common.MessageType.REMOVE_OBJECT_FROM_SCENE:
                        scene_api.build_remove_object_from_scene(command.data)

                    elif command.type == common.MessageType.SCENE:
                        scene_api.build_scene(command.data)
                    elif command.type == common.MessageType.SCENE_REMOVED:
                        scene_api.build_scene_removed(command.data)
                    elif command.type == common.MessageType.SCENE_RENAMED:
                        scene_api.build_scene_renamed(command.data)

                    elif command.type == common.MessageType.OBJECT_VISIBILITY:
                        object_api.build_object_visibility(command.data)

                    elif command.type == common.MessageType.FRAME:
                        self.build_frame(command.data)
                    elif command.type == common.MessageType.QUERY_CURRENT_FRAME:
                        self.query_current_frame()

                    elif command.type == common.MessageType.PLAY:
                        self.build_play(command.data)
                    elif command.type == common.MessageType.PAUSE:
                        self.build_pause(command.data)
                    elif command.type == common.MessageType.ADD_KEYFRAME:
                        self.build_add_keyframe(command.data)
                    elif command.type == common.MessageType.REMOVE_KEYFRAME:
                        self.build_remove_keyframe(command.data)
                    elif command.type == common.MessageType.QUERY_OBJECT_DATA:
                        self.build_query_object_data(command.data)

                    self.receivedCommands.task_done()
                    self.blockSignals = False

            if group_count == 0:
                break

        if not set_dirty:
            share_data.update_current_data()

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
