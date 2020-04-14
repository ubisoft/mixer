import logging
import struct
import os

import bpy
from mathutils import Matrix, Quaternion
from . import ui
from . import data
from .share_data import share_data
from .broadcaster import common
from .broadcaster.client import Client
from .blender_client import collection as collection_api
from .blender_client import mesh as mesh_api
from .blender_client import object_ as object_api
from .blender_client import scene as scene_api
from .stats import stats_timer

_STILL_ACTIVE = 259

logger = logging.getLogger(__name__)


class ClientBlender(Client):
    def __init__(self, host=common.DEFAULT_HOST, port=common.DEFAULT_PORT):
        super(ClientBlender, self).__init__(host, port)

        self.textures = set()
        self.callbacks = {}

        self.blenderPID = os.getpid()

    def add_callback(self, name, func):
        self.callbacks[name] = func

    # returns the path of an object
    def get_object_path(self, obj):
        path = obj.name_full
        while obj.parent:
            obj = obj.parent
            if obj:
                path = obj.name_full + "/" + path
        return path

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
        index = path.rfind("/")
        if index != -1:
            share_data.pending_parenting.add(path)  # Parenting is resolved after consumption of all messages

        # Create or get object
        elem = path[index + 1 :]
        ob = share_data.blender_objects.get(elem)
        if not ob:
            ob = bpy.data.objects.new(elem, data)
            share_data._blender_objects[ob.name_full] = ob
        return ob

    def get_or_create_object_data(self, path, data):
        return self.get_or_create_path(path, data)

    def get_or_create_camera(self, camera_name):
        camera = share_data.blender_cameras.get(camera_name)
        if camera:
            return camera
        camera = bpy.data.cameras.new(camera_name)
        share_data._blender_cameras[camera.name_full] = camera
        return camera

    def build_camera(self, data):
        camera_path, start = common.decode_string(data, 0)

        camera_name = camera_path.split("/")[-1]
        camera = self.get_or_create_camera(camera_name)

        camera.lens, start = common.decode_float(data, start)
        camera.clip_start, start = common.decode_float(data, start)
        camera.clip_end, start = common.decode_float(data, start)
        camera.dof.aperture_fstop, start = common.decode_float(data, start)
        sensor_fit, start = common.decode_int(data, start)
        camera.sensor_width, start = common.decode_float(data, start)
        camera.sensor_height, start = common.decode_float(data, start)

        if sensor_fit == 0:
            camera.sensor_fit = "AUTO"
        elif sensor_fit == 1:
            camera.sensor_fit = "VERTICAL"
        else:
            camera.sensor_fit = "HORIZONTAL"

        self.get_or_create_object_data(camera_path, camera)

    def get_or_create_light(self, light_name, light_type):
        light = share_data.blender_lights.get(light_name)
        if light:
            return light
        light = bpy.data.lights.new(light_name, type=light_type)
        share_data._blender_lights[light.name_full] = light
        return light

    def build_light(self, data):
        light_path, start = common.decode_string(data, 0)
        light_type, start = common.decode_int(data, start)
        blighttype = "POINT"
        if light_type == common.LightType.SUN.value:
            blighttype = "SUN"
        elif light_type == common.LightType.POINT.value:
            blighttype = "POINT"
        else:
            blighttype = "SPOT"

        light_name = light_path.split("/")[-1]
        light = self.get_or_create_light(light_name, blighttype)

        shadow, start = common.decode_int(data, start)
        if shadow != 0:
            light.use_shadow = True
        else:
            light.use_shadow = False

        color, start = common.decode_color(data, start)
        light.color = (color[0], color[1], color[2])
        light.energy, start = common.decode_float(data, start)
        if light_type == common.LightType.SPOT.value:
            light.spot_size, start = common.decode_float(data, start)
            light.spot_blend, start = common.decode_float(data, start)

        self.get_or_create_object_data(light_path, light)

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

    def get_or_create_material(self, material_name):
        material = share_data.blender_materials.get(material_name)
        if material:
            material.use_nodes = True
            return material

        material = bpy.data.materials.new(name=material_name)
        share_data._blender_materials[material.name_full] = material
        material.use_nodes = True
        return material

    def build_texture(self, principled, material, channel, is_color, data, index):
        file_name, index = common.decode_string(data, index)
        if len(file_name) > 0:
            tex_image = material.node_tree.nodes.new("ShaderNodeTexImage")
            try:
                tex_image.image = bpy.data.images.load(file_name)
                if not is_color:
                    tex_image.image.colorspace_settings.name = "Non-Color"
            except Exception as e:
                logger.error(e)
            material.node_tree.links.new(principled.inputs[channel], tex_image.outputs["Color"])
        return index

    def build_material(self, data):
        material_name_length = common.bytes_to_int(data[:4])
        start = 4
        end = start + material_name_length
        material_name = data[start:end].decode()
        start = end

        material = self.get_or_create_material(material_name)
        nodes = material.node_tree.nodes
        # Get a principled node
        principled = None
        if nodes:
            for n in nodes:
                if n.type == "BSDF_PRINCIPLED":
                    principled = n
                    break

        if not principled:
            logger.error("Cannot find Principled BSDF node")
            return

        index = start

        # Transmission ( 1 - opacity)
        transmission, index = common.decode_float(data, index)
        transmission = 1 - transmission
        principled.inputs["Transmission"].default_value = transmission
        file_name, index = common.decode_string(data, index)
        if len(file_name) > 0:
            invert = material.node_tree.nodes.new("ShaderNodeInvert")
            material.node_tree.links.new(principled.inputs["Transmission"], invert.outputs["Color"])
            tex_image = material.node_tree.nodes.new("ShaderNodeTexImage")
            try:
                tex_image.image = bpy.data.images.load(file_name)
                tex_image.image.colorspace_settings.name = "Non-Color"
            except Exception as e:
                logger.error("could not load file %s (%s)", file_name, e)
            material.node_tree.links.new(invert.inputs["Color"], tex_image.outputs["Color"])

        # Base Color
        base_color, index = common.decode_color(data, index)
        material.diffuse_color = (base_color[0], base_color[1], base_color[2], 1)
        principled.inputs["Base Color"].default_value = material.diffuse_color
        index = self.build_texture(principled, material, "Base Color", True, data, index)

        # Metallic
        material.metallic, index = common.decode_float(data, index)
        principled.inputs["Metallic"].default_value = material.metallic
        index = self.build_texture(principled, material, "Metallic", False, data, index)

        # Roughness
        material.roughness, index = common.decode_float(data, index)
        principled.inputs["Roughness"].default_value = material.roughness
        index = self.build_texture(principled, material, "Roughness", False, data, index)

        # Normal
        file_name, index = common.decode_string(data, index)
        if len(file_name) > 0:
            normal_map = material.node_tree.nodes.new("ShaderNodeNormalMap")
            material.node_tree.links.new(principled.inputs["Normal"], normal_map.outputs["Normal"])
            tex_image = material.node_tree.nodes.new("ShaderNodeTexImage")
            try:
                tex_image.image = bpy.data.images.load(file_name)
                tex_image.image.colorspace_settings.name = "Non-Color"
            except Exception as e:
                logger.error("could not load file %s (%s)", file_name, e)
            material.node_tree.links.new(normal_map.inputs["Color"], tex_image.outputs["Color"])

        # Emission
        emission, index = common.decode_color(data, index)
        principled.inputs["Emission"].default_value = emission
        index = self.build_texture(principled, material, "Emission", False, data, index)

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

    def get_material_buffer(self, material):
        name = material.name_full
        buffer = common.encode_string(name)
        principled = None
        diffuse = None
        # Get the nodes in the node tree
        if material.node_tree:
            nodes = material.node_tree.nodes
            # Get a principled node
            if nodes:
                for n in nodes:
                    if n.type == "BSDF_PRINCIPLED":
                        principled = n
                        break
                    if n.type == "BSDF_DIFFUSE":
                        diffuse = n
            # principled = next(n for n in nodes if n.type == 'BSDF_PRINCIPLED')
        if principled is None and diffuse is None:
            base_color = (0.8, 0.8, 0.8)
            metallic = 0.0
            roughness = 0.5
            opacity = 1.0
            emission_color = (0.0, 0.0, 0.0)
            buffer += common.encode_float(opacity) + common.encode_string("")
            buffer += common.encode_color(base_color) + common.encode_string("")
            buffer += common.encode_float(metallic) + common.encode_string("")
            buffer += common.encode_float(roughness) + common.encode_string("")
            buffer += common.encode_string("")
            buffer += common.encode_color(emission_color) + common.encode_string("")
            return buffer
        elif diffuse:
            opacity = 1.0
            opacity_texture = None
            metallic = 0.0
            metallic_texture = None
            emission = (0.0, 0.0, 0.0)
            emission_texture = None

            # Get the slot for 'base color'
            # Or principled.inputs[0]
            base_color = (1.0, 1.0, 1.0)
            base_color_texture = None
            base_color_input = diffuse.inputs.get("Color")
            # Get its default value (not the value from a possible link)
            if base_color_input:
                base_color = base_color_input.default_value
                base_color_texture = self.get_texture(base_color_input)

            roughness = 1.0
            roughness_texture = None
            roughness_input = diffuse.inputs.get("Roughness")
            if roughness_input:
                roughness_texture = self.get_texture(roughness_input)
                if len(roughness_input.links) == 0:
                    roughness = roughness_input.default_value

            normal_texture = None
            norma_input = diffuse.inputs.get("Normal")
            if norma_input:
                if len(norma_input.links) == 1:
                    normal_map = norma_input.links[0].from_node
                    if "Color" in normal_map.inputs:
                        color_input = normal_map.inputs["Color"]
                        normal_texture = self.get_texture(color_input)

        else:
            opacity = 1.0
            opacity_texture = None
            opacity_input = principled.inputs.get("Transmission")
            if opacity_input:
                if len(opacity_input.links) == 1:
                    invert = opacity_input.links[0].from_node
                    if "Color" in invert.inputs:
                        color_input = invert.inputs["Color"]
                        opacity_texture = self.get_texture(color_input)
                else:
                    opacity = 1.0 - opacity_input.default_value

            # Get the slot for 'base color'
            # Or principled.inputs[0]
            base_color = (1.0, 1.0, 1.0)
            base_color_texture = None
            base_color_input = principled.inputs.get("Base Color")
            # Get its default value (not the value from a possible link)
            if base_color_input:
                base_color = base_color_input.default_value
                base_color_texture = self.get_texture(base_color_input)

            metallic = 0.0
            metallic_texture = None
            metallic_input = principled.inputs.get("Metallic")
            if metallic_input:
                metallic_texture = self.get_texture(metallic_input)
                if len(metallic_input.links) == 0:
                    metallic = metallic_input.default_value

            roughness = 1.0
            roughness_texture = None
            roughness_input = principled.inputs.get("Roughness")
            if roughness_input:
                roughness_texture = self.get_texture(roughness_input)
                if len(roughness_input.links) == 0:
                    roughness = roughness_input.default_value

            normal_texture = None
            norma_input = principled.inputs.get("Normal")
            if norma_input:
                if len(norma_input.links) == 1:
                    normal_map = norma_input.links[0].from_node
                    if "Color" in normal_map.inputs:
                        color_input = normal_map.inputs["Color"]
                        normal_texture = self.get_texture(color_input)

            emission = (0.0, 0.0, 0.0)
            emission_texture = None
            emission_input = principled.inputs.get("Emission")
            if emission_input:
                # Get its default value (not the value from a possible link)
                emission = emission_input.default_value
                emission_texture = self.get_texture(emission_input)

        buffer += common.encode_float(opacity)
        if opacity_texture:
            buffer += common.encode_string(opacity_texture)
        else:
            buffer += common.encode_string("")
        buffer += common.encode_color(base_color)
        if base_color_texture:
            buffer += common.encode_string(base_color_texture)
        else:
            buffer += common.encode_string("")

        buffer += common.encode_float(metallic)
        if metallic_texture:
            buffer += common.encode_string(metallic_texture)
        else:
            buffer += common.encode_string("")

        buffer += common.encode_float(roughness)
        if roughness_texture:
            buffer += common.encode_string(roughness_texture)
        else:
            buffer += common.encode_string("")

        if normal_texture:
            buffer += common.encode_string(normal_texture)
        else:
            buffer += common.encode_string("")

        buffer += common.encode_color(emission)
        if emission_texture:
            buffer += common.encode_string(emission_texture)
        else:
            buffer += common.encode_string("")

        return buffer

    def get_material_buffers(self, obj):
        try:
            buffers = []
            for slot in obj.material_slots[:]:
                if slot.material:
                    buffer = self.get_material_buffer(slot.material)
                    buffers.append(buffer)
            return buffers
        except Exception as e:
            logger.error(e)

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
            self.send_grease_pencil_material(material)
        else:
            self.add_command(common.Command(common.MessageType.MATERIAL, self.get_material_buffer(material), 0))

    def get_mesh_name(self, mesh):
        return mesh.name_full

    @stats_timer(share_data)
    def send_mesh(self, obj):
        mesh = obj.data
        mesh_name = self.get_mesh_name(mesh)
        path = self.get_object_path(obj)

        binary_buffer = common.encode_string(path) + common.encode_string(mesh_name)

        binary_buffer += mesh_api.encode_mesh(
            obj, data.get_dcc_sync_props().send_base_meshes, data.get_dcc_sync_props().send_baked_meshes
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
                    keys = []
                    for keyframe in fcurve.keyframe_points:
                        keys.extend(keyframe.co)
                    buffer = (
                        common.encode_string(obj_name)
                        + common.encode_string(channel_name)
                        + common.encode_int(channel_index)
                        + common.int_to_bytes(key_count, 4)
                        + struct.pack(f"{len(keys)}f", *keys)
                    )
                    self.add_command(common.Command(common.MessageType.CAMERA_ANIMATION, buffer, 0))
                    return

    def send_camera_animations(self, obj):
        self.send_animation_buffer(obj.name_full, obj.animation_data, "location", 0)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "location", 1)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "location", 2)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "rotation", 0)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "rotation", 1)
        self.send_animation_buffer(obj.name_full, obj.animation_data, "rotation", 2)
        self.send_animation_buffer(obj.name_full, obj.data.animation_data, "lens")

    def get_camera_buffer(self, obj):
        cam = obj.data
        focal = cam.lens
        front_clip_plane = cam.clip_start
        far_clip_plane = cam.clip_end
        aperture = cam.dof.aperture_fstop
        sensor_fit_name = cam.sensor_fit
        sensor_fit = common.SensorFitMode.AUTO
        if sensor_fit_name == "AUTO":
            sensor_fit = common.SensorFitMode.AUTO
        elif sensor_fit_name == "HORIZONTAL":
            sensor_fit = common.SensorFitMode.HORIZONTAL
        elif sensor_fit_name == "VERTICAL":
            sensor_fit = common.SensorFitMode.VERTICAL
        sensor_width = cam.sensor_width
        sensor_height = cam.sensor_height

        path = self.get_object_path(obj)
        return (
            common.encode_string(path)
            + common.encode_float(focal)
            + common.encode_float(front_clip_plane)
            + common.encode_float(far_clip_plane)
            + common.encode_float(aperture)
            + common.encode_int(sensor_fit.value)
            + common.encode_float(sensor_width)
            + common.encode_float(sensor_height)
        )

    def send_camera(self, obj):
        camera_buffer = self.get_camera_buffer(obj)
        if camera_buffer:
            self.add_command(common.Command(common.MessageType.CAMERA, camera_buffer, 0))
        self.send_camera_animations(obj)

    def get_light_buffer(self, obj):
        light = obj.data
        light_type_name = light.type
        light_type = common.LightType.SUN
        if light_type_name == "POINT":
            light_type = common.LightType.POINT
        elif light_type_name == "SPOT":
            light_type = common.LightType.SPOT
        elif light_type_name == "SUN":
            light_type = common.LightType.SUN
        else:
            return None
        color = light.color
        power = light.energy
        if bpy.context.scene.render.engine == "CYCLES":
            shadow = light.cycles.cast_shadow
        else:
            shadow = light.use_shadow

        spot_blend = 10.0
        spot_size = 0.0
        if light_type == common.LightType.SPOT:
            spot_size = light.spot_size
            spot_blend = light.spot_blend

        return (
            common.encode_string(self.get_object_path(obj))
            + common.encode_int(light_type.value)
            + common.encode_int(shadow)
            + common.encode_color(color)
            + common.encode_float(power)
            + common.encode_float(spot_size)
            + common.encode_float(spot_blend)
        )

    def send_light(self, obj):
        light_buffer = self.get_light_buffer(obj)
        if light_buffer:
            self.add_command(common.Command(common.MessageType.LIGHT, light_buffer, 0))

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

    # -----------------------------------------------------------------------------------------------------------
    #
    # Grease Pencil
    #
    # -----------------------------------------------------------------------------------------------------------

    def send_grease_pencil_stroke(self, stroke):
        buffer = common.encode_int(stroke.material_index)
        buffer += common.encode_int(stroke.line_width)

        points = list()

        for point in stroke.points:
            points.extend(point.co)
            points.append(point.pressure)
            points.append(point.strength)

        binary_points_buffer = common.int_to_bytes(len(stroke.points), 4) + struct.pack(f"{len(points)}f", *points)
        buffer += binary_points_buffer
        return buffer

    def send_grease_pencil_frame(self, frame):
        buffer = common.encode_int(frame.frame_number)
        buffer += common.encode_int(len(frame.strokes))
        for stroke in frame.strokes:
            buffer += self.send_grease_pencil_stroke(stroke)
        return buffer

    def send_grease_pencil_layer(self, layer, name):
        buffer = common.encode_string(name)
        buffer += common.encode_bool(layer.hide)
        buffer += common.encode_int(len(layer.frames))
        for frame in layer.frames:
            buffer += self.send_grease_pencil_frame(frame)
        return buffer

    def send_grease_pencil_time_offset(self, obj):
        grease_pencil = obj.data
        buffer = common.encode_string(grease_pencil.name_full)

        for modifier in obj.grease_pencil_modifiers:
            if modifier.type != "GP_TIME":
                continue
            offset = modifier.offset
            scale = modifier.frame_scale
            custom_range = modifier.use_custom_frame_range
            frame_start = modifier.frame_start
            frame_end = modifier.frame_end
            buffer += (
                common.encode_int(offset)
                + common.encode_float(scale)
                + common.encode_bool(custom_range)
                + common.encode_int(frame_start)
                + common.encode_int(frame_end)
            )
            self.add_command(common.Command(common.MessageType.GREASE_PENCIL_TIME_OFFSET, buffer, 0))
            break

    def send_grease_pencil_mesh(self, obj):
        grease_pencil = obj.data
        buffer = common.encode_string(grease_pencil.name_full)

        buffer += common.encode_int(len(grease_pencil.materials))
        for material in grease_pencil.materials:
            if not material:
                material_name = "Default"
            else:
                material_name = material.name_full
            buffer += common.encode_string(material_name)

        buffer += common.encode_int(len(grease_pencil.layers))
        for name, layer in grease_pencil.layers.items():
            buffer += self.send_grease_pencil_layer(layer, name)

        self.add_command(common.Command(common.MessageType.GREASE_PENCIL_MESH, buffer, 0))

        self.send_grease_pencil_time_offset(obj)

    def send_grease_pencil_material(self, material):
        gp_material = material.grease_pencil
        stroke_enable = gp_material.show_stroke
        stroke_mode = gp_material.mode
        stroke_style = gp_material.stroke_style
        stroke_color = gp_material.color
        stroke_overlap = gp_material.use_overlap_strokes
        fill_enable = gp_material.show_fill
        fill_style = gp_material.fill_style
        fill_color = gp_material.fill_color
        gp_material_buffer = common.encode_string(material.name_full)
        gp_material_buffer += common.encode_bool(stroke_enable)
        gp_material_buffer += common.encode_string(stroke_mode)
        gp_material_buffer += common.encode_string(stroke_style)
        gp_material_buffer += common.encode_color(stroke_color)
        gp_material_buffer += common.encode_bool(stroke_overlap)
        gp_material_buffer += common.encode_bool(fill_enable)
        gp_material_buffer += common.encode_string(fill_style)
        gp_material_buffer += common.encode_color(fill_color)
        self.add_command(common.Command(common.MessageType.GREASE_PENCIL_MATERIAL, gp_material_buffer, 0))

    def send_grease_pencil_connection(self, obj):
        buffer = common.encode_string(self.get_object_path(obj))
        buffer += common.encode_string(obj.data.name_full)
        self.add_command(common.Command(common.MessageType.GREASE_PENCIL_CONNECTION, buffer, 0))

    def build_grease_pencil_connection(self, data):
        path, start = common.decode_string(data, 0)
        grease_pencil_name, start = common.decode_string(data, start)
        gp = share_data.blender_grease_pencils[grease_pencil_name]
        self.get_or_create_object_data(path, gp)

    def decode_grease_pencil_stroke(self, grease_pencil_frame, stroke_index, data, index):
        material_index, index = common.decode_int(data, index)
        line_width, index = common.decode_int(data, index)
        points, index = common.decode_array(data, index, "5f", 5 * 4)

        if stroke_index >= len(grease_pencil_frame.strokes):
            stroke = grease_pencil_frame.strokes.new()
        else:
            stroke = grease_pencil_frame.strokes[stroke_index]

        stroke.material_index = material_index
        stroke.line_width = line_width

        p = stroke.points
        if len(points) > len(p):
            p.add(len(points) - len(p))
        if len(points) < len(p):
            max_index = len(points) - 1
            for _i in range(max_index, len(p)):
                p.pop(max_index)

        for i in range(len(p)):
            point = points[i]
            p[i].co = (point[0], point[1], point[2])
            p[i].pressure = point[3]
            p[i].strength = point[4]
        return index

    def decode_grease_pencil_frame(self, grease_pencil_layer, data, index):
        grease_pencil_frame, index = common.decode_int(data, index)
        frame = None
        for f in grease_pencil_layer.frames:
            if f.frame_number == grease_pencil_frame:
                frame = f
                break
        if not frame:
            frame = grease_pencil_layer.frames.new(grease_pencil_frame)
        stroke_count, index = common.decode_int(data, index)
        for stroke_index in range(stroke_count):
            index = self.decode_grease_pencil_stroke(frame, stroke_index, data, index)
        return index

    def decode_grease_pencil_layer(self, grease_pencil, data, index):
        grease_pencil_layer_name, index = common.decode_string(data, index)
        layer = grease_pencil.get(grease_pencil_layer_name)
        if not layer:
            layer = grease_pencil.layers.new(grease_pencil_layer_name)
        layer.hide, index = common.decode_bool(data, index)
        frame_count, index = common.decode_int(data, index)
        for _ in range(frame_count):
            index = self.decode_grease_pencil_frame(layer, data, index)
        return index

    def build_grease_pencil_mesh(self, data):
        grease_pencil_name, index = common.decode_string(data, 0)

        grease_pencil = share_data.blender_grease_pencils.get(grease_pencil_name)
        if not grease_pencil:
            grease_pencil = bpy.data.grease_pencils.new(grease_pencil_name)
            share_data._blender_grease_pencils[grease_pencil.name_full] = grease_pencil

        grease_pencil.materials.clear()
        material_count, index = common.decode_int(data, index)
        for _ in range(material_count):
            material_name, index = common.decode_string(data, index)
            material = share_data.blender_materials.get(material_name)
            grease_pencil.materials.append(material)

        layer_count, index = common.decode_int(data, index)
        for _ in range(layer_count):
            index = self.decode_grease_pencil_layer(grease_pencil, data, index)

    def build_grease_pencil_material(self, data):
        grease_pencil_material_name, start = common.decode_string(data, 0)
        material = share_data.blender_materials.get(grease_pencil_material_name)
        if not material:
            material = bpy.data.materials.new(grease_pencil_material_name)
            share_data._blender_materials[material.name_full] = material
        if not material.grease_pencil:
            bpy.data.materials.create_gpencil_data(material)

        gp_material = material.grease_pencil
        gp_material.show_stroke, start = common.decode_bool(data, start)
        gp_material.mode, start = common.decode_string(data, start)
        gp_material.stroke_style, start = common.decode_string(data, start)
        gp_material.color, start = common.decode_color(data, start)
        gp_material.use_overlap_strokes, start = common.decode_bool(data, start)
        gp_material.show_fill, start = common.decode_bool(data, start)
        gp_material.fill_style, start = common.decode_string(data, start)
        gp_material.fill_color, start = common.decode_color(data, start)

    def build_grease_pencil(self, data):
        object_path, start = common.decode_string(data, 0)
        grease_pencil_name, start = common.decode_string(data, start)
        grease_pencil = share_data.blender_grease_pencils.get(grease_pencil_name)
        if not grease_pencil:
            grease_pencil = bpy.data.grease_pencils.new(grease_pencil_name)
            self.get_or_create_object_data(object_path, grease_pencil)

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

    def send_frame(self, frame):
        self.add_command(common.Command(common.MessageType.FRAME, common.encode_int(frame), 0))

    def send_frame_start_end(self, start, end):
        self.add_command(
            common.Command(common.MessageType.FRAME_START_END, common.encode_int(start) + common.encode_int(end), 0)
        )

    def clear_content(self):
        if "ClearContent" in self.callbacks:
            self.callbacks["ClearContent"]()

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
                        self.build_grease_pencil_mesh(command.data)
                    elif command.type == common.MessageType.GREASE_PENCIL_MATERIAL:
                        self.build_grease_pencil_material(command.data)
                    elif command.type == common.MessageType.GREASE_PENCIL_CONNECTION:
                        self.build_grease_pencil_connection(command.data)

                    elif command.type == common.MessageType.CLEAR_CONTENT:
                        self.clear_content()
                    elif command.type == common.MessageType.MESH:
                        self.build_mesh(command.data)
                    elif command.type == common.MessageType.TRANSFORM:
                        self.build_transform(command.data)
                    elif command.type == common.MessageType.MATERIAL:
                        self.build_material(command.data)
                    elif command.type == common.MessageType.DELETE:
                        self.build_delete(command.data)
                    elif command.type == common.MessageType.CAMERA:
                        self.build_camera(command.data)
                    elif command.type == common.MessageType.LIGHT:
                        self.build_light(command.data)
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
