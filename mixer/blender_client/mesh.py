import logging
import struct

import bpy
import bmesh
from mathutils import Vector

from dccsync.broadcaster import common
from dccsync.stats import stats_timer
from dccsync.share_data import share_data
from dccsync.blender_client import material as material_api

logger = logging.getLogger(__name__)


def decode_layer_float(elmt, layer, data, index):
    elmt[layer], index = common.decode_float(data, index)
    return index


def extract_layer_float(elmt, layer):
    return (elmt[layer],)


extract_layer_float.struct = "1f"


def decode_layer_int(elmt, layer, data, index):
    elmt[layer], index = common.decode_int(data, index)
    return index


def extract_layer_int(elmt, layer):
    return (elmt[layer],)


extract_layer_int.struct = "1i"


def decode_layer_vector(elmt, layer, data, index):
    elmt[layer], index = common.decode_vector3(data, index)
    return index


def extract_layer_vector3(elmt, layer):
    v = elmt[layer]
    return (v[0], v[1], v[2])


extract_layer_vector3.struct = "3f"


def decode_layer_color(elmt, layer, data, index):
    elmt[layer], index = common.decode_color(data, index)
    return index


def extract_layer_color(elmt, layer):
    color = elmt[layer]
    if len(color) == 3:
        return (color[0], color[1], color[2], 1.0)
    return (color[0], color[1], color[2], color[3])


extract_layer_color.struct = "4f"


def decode_layer_uv(elmt, layer, data, index):
    pin_uv, index = common.decode_bool(data, index)
    uv, index = common.decode_vector2(data, index)
    elmt[layer].pin_uv = pin_uv
    elmt[layer].uv = uv
    return index


def extract_layer_uv(elmt, layer):
    return (elmt[layer].pin_uv, *elmt[layer].uv)


extract_layer_uv.struct = "1I2f"


def decode_bmesh_layer(data, index, layer_collection, element_seq, decode_layer_value_func):
    layer_count, index = common.decode_int(data, index)
    while layer_count > len(layer_collection):
        if not layer_collection.is_singleton:
            layer_collection.new()
        else:
            layer_collection.verify()  # Will create a layer and returns it
            break  # layer_count should be one but break just in case
    for i in range(layer_count):
        layer = layer_collection[i]
        for elt in element_seq:
            index = decode_layer_value_func(elt, layer, data, index)
    return index


def encode_bmesh_layer(layer_collection, element_seq, extract_layer_tuple_func):
    buffer = []
    count = 0
    for i in range(len(layer_collection)):
        layer = layer_collection[i]
        for elt in element_seq:
            buffer.extend(extract_layer_tuple_func(elt, layer))
            count += 1

    binary_buffer = struct.pack("1I", len(layer_collection))
    if len(layer_collection) > 0:
        binary_buffer += struct.pack(extract_layer_tuple_func.struct * count, *buffer)
    return binary_buffer


# We cannot iterate directly over bm.loops, so we use a generator
def loops_iterator(bm):
    for face in bm.faces:
        for loop in face.loops:
            yield loop


@stats_timer(share_data)
def encode_baked_mesh(obj):
    """
    Bake an object as a triangle mesh and encode it.
    """
    stats_timer = share_data.current_stats_timer

    # Bake modifiers
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj = obj.evaluated_get(depsgraph)

    stats_timer.checkpoint("eval_depsgraph")

    # Triangulate mesh (before calculating normals)
    mesh = obj.data if obj.type == "MESH" else obj.to_mesh()
    if mesh is None:
        # This happens for empty curves
        return bytes()

    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.triangulate(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()

    stats_timer.checkpoint("triangulate_mesh")

    # Calculate normals, necessary if auto-smooth option enabled
    mesh.calc_normals()
    mesh.calc_normals_split()
    # calc_loop_triangles resets normals so... don't use it

    stats_timer.checkpoint("calc_normals")

    # get active uv layer
    uvlayer = mesh.uv_layers.active

    vertices = []
    normals = []
    uvs = []
    indices = []
    material_indices = []  # array of triangle index, material index

    current_material_index = -1
    current_face_index = 0
    logger.debug("Writing %d polygons", len(mesh.polygons))
    for f in mesh.polygons:
        for loop_id in f.loop_indices:
            index = mesh.loops[loop_id].vertex_index
            vertices.extend(mesh.vertices[index].co)
            normals.extend(mesh.loops[loop_id].normal)
            if uvlayer:
                uvs.extend([x for x in uvlayer.data[loop_id].uv])
            indices.append(loop_id)

        if f.material_index != current_material_index:
            current_material_index = f.material_index
            material_indices.append(current_face_index)
            material_indices.append(current_material_index)
        current_face_index = current_face_index + 1

    if obj.type != "MESH":
        obj.to_mesh_clear()

    stats_timer.checkpoint("make_buffers")

    # Vericex count + binary vertices buffer
    size = len(vertices) // 3
    binary_vertices_buffer = common.int_to_bytes(size, 4) + struct.pack(f"{len(vertices)}f", *vertices)

    stats_timer.checkpoint("write_verts")

    # Normals count + binary normals buffer
    size = len(normals) // 3
    binary_normals_buffer = common.int_to_bytes(size, 4) + struct.pack(f"{len(normals)}f", *normals)

    stats_timer.checkpoint("write_normals")

    # UVs count + binary uvs buffer
    size = len(uvs) // 2
    binary_uvs_buffer = common.int_to_bytes(size, 4) + struct.pack(f"{len(uvs)}f", *uvs)

    stats_timer.checkpoint("write_uvs")

    # material indices + binary material indices buffer
    size = len(material_indices) // 2
    binary_material_indices_buffer = common.int_to_bytes(size, 4) + struct.pack(
        f"{len(material_indices)}I", *material_indices
    )

    stats_timer.checkpoint("write_material_indices")

    # triangle indices count + binary triangle indices buffer
    size = len(indices) // 3
    binary_indices_buffer = common.int_to_bytes(size, 4) + struct.pack(f"{len(indices)}I", *indices)

    stats_timer.checkpoint("write_tri_idx_buff")

    return (
        binary_vertices_buffer
        + binary_normals_buffer
        + binary_uvs_buffer
        + binary_material_indices_buffer
        + binary_indices_buffer
    )


@stats_timer(share_data)
def encode_base_mesh_geometry(mesh_data):
    stats_timer = share_data.current_stats_timer

    # We do not synchronize "select" and "hide" state of mesh elements
    # because we consider them user specific.

    bm = bmesh.new()
    bm.from_mesh(mesh_data)

    stats_timer.checkpoint("bmesh_from_mesh")

    binary_buffer = bytes()

    logger.debug("Writing %d vertices", len(bm.verts))
    bm.verts.ensure_lookup_table()

    verts_array = []
    for vert in bm.verts:
        verts_array.extend((*vert.co,))

    stats_timer.checkpoint("make_verts_buffer")

    binary_buffer += struct.pack(f"1I{len(verts_array)}f", len(bm.verts), *verts_array)

    stats_timer.checkpoint("encode_verts_buffer")

    # Vertex layers
    # Ignored layers for now:
    # - skin (BMVertSkin)
    # - deform (BMDeformVert)
    # - paint_mask (float)
    # Other ignored layers:
    # - shape: shape keys are handled with Shape Keys at the mesh and object level
    # - float, int, string: don't really know their role
    binary_buffer += encode_bmesh_layer(bm.verts.layers.bevel_weight, bm.verts, extract_layer_float)

    stats_timer.checkpoint("verts_layers")

    logger.debug("Writing %d edges", len(bm.edges))
    bm.edges.ensure_lookup_table()

    edges_array = []
    for edge in bm.edges:
        edges_array.extend((edge.verts[0].index, edge.verts[1].index, edge.smooth, edge.seam))

    stats_timer.checkpoint("make_edges_buffer")

    binary_buffer += struct.pack(f"1I{len(edges_array)}I", len(bm.edges), *edges_array)

    stats_timer.checkpoint("encode_edges_buffer")

    # Edge layers
    # Ignored layers for now: None
    # Other ignored layers:
    # - freestyle: of type NotImplementedType, maybe reserved for future dev
    # - float, int, string: don't really know their role
    binary_buffer += encode_bmesh_layer(bm.edges.layers.bevel_weight, bm.edges, extract_layer_float)
    binary_buffer += encode_bmesh_layer(bm.edges.layers.crease, bm.edges, extract_layer_float)

    stats_timer.checkpoint("edges_layers")

    logger.debug("Writing %d faces", len(bm.faces))
    bm.faces.ensure_lookup_table()

    faces_array = []
    for face in bm.faces:
        faces_array.extend((face.material_index, face.smooth, len(face.verts)))
        faces_array.extend((vert.index for vert in face.verts))

    stats_timer.checkpoint("make_faces_buffer")

    binary_buffer += struct.pack(f"1I{len(faces_array)}I", len(bm.faces), *faces_array)

    stats_timer.checkpoint("encode_faces_buffer")

    # Face layers
    # Ignored layers for now: None
    # Other ignored layers:
    # - freestyle: of type NotImplementedType, maybe reserved for future dev
    # - float, int, string: don't really know their role
    binary_buffer += encode_bmesh_layer(bm.faces.layers.face_map, bm.faces, extract_layer_int)

    stats_timer.checkpoint("faces_layers")

    # Loops layers
    # A loop is an edge attached to a face (so each edge of a manifold can have 2 loops at most).
    # Ignored layers for now: None
    # Other ignored layers:
    # - float, int, string: don't really know their role
    binary_buffer += encode_bmesh_layer(bm.loops.layers.uv, loops_iterator(bm), extract_layer_uv)
    binary_buffer += encode_bmesh_layer(bm.loops.layers.color, loops_iterator(bm), extract_layer_color)

    stats_timer.checkpoint("loops_layers")

    bm.free()

    return binary_buffer


@stats_timer(share_data)
def encode_base_mesh(obj):

    # Temporary for curves and other objects that support to_mesh()
    # #todo Implement correct base encoding for these objects
    mesh_data = obj.data if obj.type == "MESH" else obj.to_mesh()
    if mesh_data is None:
        # This happens for empty curves
        # This is temporary, when curves will be fully implemented we will encode something
        return bytes()

    binary_buffer = encode_base_mesh_geometry(mesh_data)

    # Shape keys
    # source https://blender.stackexchange.com/questions/111661/creating-shape-keys-using-python
    if mesh_data.shape_keys is None:
        binary_buffer += common.encode_int(0)  # Indicate 0 key blocks
    else:
        logger.debug("Writing %d shape keys", len(mesh_data.shape_keys.key_blocks))

        binary_buffer += common.encode_int(len(mesh_data.shape_keys.key_blocks))
        # Encode names
        for key_block in mesh_data.shape_keys.key_blocks:
            binary_buffer += common.encode_string(key_block.name)
        # Encode vertex group names
        for key_block in mesh_data.shape_keys.key_blocks:
            binary_buffer += common.encode_string(key_block.vertex_group)
        # Encode relative key names
        for key_block in mesh_data.shape_keys.key_blocks:
            binary_buffer += common.encode_string(key_block.relative_key.name)
        # Encode data
        shape_keys_buffer = []
        fmt_str = ""
        for key_block in mesh_data.shape_keys.key_blocks:
            shape_keys_buffer.extend(
                (key_block.mute, key_block.value, key_block.slider_min, key_block.slider_max, len(key_block.data))
            )
            fmt_str += f"1I1f1f1f1I{(3 * len(key_block.data))}f"
            for i in range(len(key_block.data)):
                shape_keys_buffer.extend(key_block.data[i].co)
        binary_buffer += struct.pack(f"{fmt_str}", *shape_keys_buffer)

        binary_buffer += common.encode_bool(mesh_data.shape_keys.use_relative)

    # Vertex Groups
    verts_per_group = {}
    for vertex_group in obj.vertex_groups:
        verts_per_group[vertex_group.index] = []

    for vert in mesh_data.vertices:
        for vg in vert.groups:
            verts_per_group[vg.group].append((vert.index, vg.weight))

    binary_buffer += common.encode_int(len(obj.vertex_groups))
    for vertex_group in obj.vertex_groups:
        binary_buffer += common.encode_string(vertex_group.name)
        binary_buffer += common.encode_bool(vertex_group.lock_weight)
        binary_buffer += common.encode_int(len(verts_per_group[vertex_group.index]))
        for vg_elmt in verts_per_group[vertex_group.index]:
            binary_buffer += common.encode_int(vg_elmt[0])
            binary_buffer += common.encode_float(vg_elmt[1])

    # Normals
    binary_buffer += common.encode_bool(mesh_data.use_auto_smooth)
    binary_buffer += common.encode_float(mesh_data.auto_smooth_angle)
    binary_buffer += common.encode_bool(mesh_data.has_custom_normals)

    if mesh_data.has_custom_normals:
        mesh_data.calc_normals_split()  # Required otherwise all normals are (0, 0, 0)
        normals = []
        for loop in mesh_data.loops:
            normals.extend((*loop.normal,))
        binary_buffer += struct.pack(f"{len(normals)}f", *normals)

    # UV Maps
    for uv_layer in mesh_data.uv_layers:
        binary_buffer += common.encode_string(uv_layer.name)
        binary_buffer += common.encode_bool(uv_layer.active_render)

    # Vertex Colors
    for vertex_colors in mesh_data.vertex_colors:
        binary_buffer += common.encode_string(vertex_colors.name)
        binary_buffer += common.encode_bool(vertex_colors.active_render)

    if obj.type != "MESH":
        obj.to_mesh_clear()

    return binary_buffer


@stats_timer(share_data)
def encode_mesh(obj, do_encode_base_mesh, do_encode_baked_mesh):
    binary_buffer = bytes()

    if do_encode_base_mesh:
        mesh_buffer = encode_base_mesh(obj)
        binary_buffer += common.encode_int(len(mesh_buffer))
        binary_buffer += mesh_buffer
    else:
        binary_buffer += common.encode_int(0)

    if do_encode_baked_mesh:
        mesh_buffer = encode_baked_mesh(obj)
        binary_buffer += common.encode_int(len(mesh_buffer))
        binary_buffer += mesh_buffer
    else:
        binary_buffer += common.encode_int(0)

    # Materials
    materials = []
    for material in obj.data.materials:
        materials.append(material.name_full if material is not None else "")
    binary_buffer += common.encode_string_array(materials)

    return binary_buffer


@stats_timer(share_data)
def decode_bakes_mesh(obj, data, index):
    # Note: Blender should not load a baked mesh but we have this function to debug the encoding part
    # and as an exemple for implementations that load baked meshes
    byte_size, index = common.decode_int(data, index)
    if byte_size == 0:
        return index

    positions, index = common.decode_vector3_array(data, index)
    normals, index = common.decode_vector3_array(data, index)
    uvs, index = common.decode_vector2_array(data, index)
    material_indices, index = common.decode_int2_array(data, index)
    triangles, index = common.decode_int3_array(data, index)

    bm = bmesh.new()
    for i in range(len(positions)):
        vertex = bm.verts.new(positions[i])
        # according to https://blender.stackexchange.com/questions/49357/bmesh-how-can-i-import-custom-vertex-normals
        # normals are not working for bmesh...
        vertex.normal = normals[i]
    bm.verts.ensure_lookup_table()

    uv_layer = None
    if len(uvs) > 0:
        uv_layer = bm.loops.layers.uv.new()

    current_material_index = 0
    index_in_material_indices = 0
    next_triangle_index = len(triangles)
    if len(material_indices) > 1:
        next_triangle_index = material_indices[index_in_material_indices + 1][0]
    if len(material_indices) > 0:
        current_material_index = material_indices[index_in_material_indices][1]

    for i in range(len(triangles)):
        if i >= next_triangle_index:
            index_in_material_indices = index_in_material_indices + 1
            next_triangle_index = len(triangles)
            if len(material_indices) > index_in_material_indices + 1:
                next_triangle_index = material_indices[index_in_material_indices + 1][0]
            current_material_index = material_indices[index_in_material_indices][1]

        triangle = triangles[i]
        i1 = triangle[0]
        i2 = triangle[1]
        i3 = triangle[2]
        try:
            face = bm.faces.new((bm.verts[i1], bm.verts[i2], bm.verts[i3]))
            face.material_index = current_material_index
            if uv_layer:
                face.loops[0][uv_layer].uv = uvs[i1]
                face.loops[1][uv_layer].uv = uvs[i2]
                face.loops[2][uv_layer].uv = uvs[i3]
        except Exception:
            pass

    me = obj.data

    bm.to_mesh(me)
    bm.free()

    # hack ! Since bmesh cannot be used to set custom normals
    normals2 = []
    for l in me.loops:
        normals2.append(normals[l.vertex_index])
    me.normals_split_custom_set(normals2)
    me.use_auto_smooth = True

    return index


@stats_timer(share_data)
def decode_base_mesh(client, obj, data, index):
    bm = bmesh.new()

    position_count, index = common.decode_int(data, index)
    logger.debug("Reading %d vertices", position_count)

    for _pos_idx in range(position_count):
        co, index = common.decode_vector3(data, index)
        bm.verts.new(co)

    bm.verts.ensure_lookup_table()

    index = decode_bmesh_layer(data, index, bm.verts.layers.bevel_weight, bm.verts, decode_layer_float)

    edge_count, index = common.decode_int(data, index)
    logger.debug("Reading %d edges", edge_count)

    edges_data = struct.unpack(f"{edge_count * 4}I", data[index : index + edge_count * 4 * 4])
    index += edge_count * 4 * 4

    for edge_idx in range(edge_count):
        v1 = edges_data[edge_idx * 4]
        v2 = edges_data[edge_idx * 4 + 1]
        edge = bm.edges.new((bm.verts[v1], bm.verts[v2]))
        edge.smooth = bool(edges_data[edge_idx * 4 + 2])
        edge.seam = bool(edges_data[edge_idx * 4 + 3])

    index = decode_bmesh_layer(data, index, bm.edges.layers.bevel_weight, bm.edges, decode_layer_float)
    index = decode_bmesh_layer(data, index, bm.edges.layers.crease, bm.edges, decode_layer_float)

    face_count, index = common.decode_int(data, index)
    logger.debug("Reading %d faces", face_count)

    for _face_idx in range(face_count):
        material_idx, index = common.decode_int(data, index)
        smooth, index = common.decode_bool(data, index)
        vert_count, index = common.decode_int(data, index)
        face_vertices = struct.unpack(f"{vert_count}I", data[index : index + vert_count * 4])
        index += vert_count * 4
        verts = [bm.verts[i] for i in face_vertices]
        face = bm.faces.new(verts)
        face.material_index = material_idx
        face.smooth = smooth

    index = decode_bmesh_layer(data, index, bm.faces.layers.face_map, bm.faces, decode_layer_int)

    index = decode_bmesh_layer(data, index, bm.loops.layers.uv, loops_iterator(bm), decode_layer_uv)
    index = decode_bmesh_layer(data, index, bm.loops.layers.color, loops_iterator(bm), decode_layer_color)

    bm.normal_update()
    bm.to_mesh(obj.data)
    bm.free()

    # Load shape keys
    shape_keys_count, index = common.decode_int(data, index)
    obj.shape_key_clear()
    if shape_keys_count > 0:
        logger.debug("Loading %d shape keys", shape_keys_count)
        shapes_keys_list = []
        for _i in range(shape_keys_count):
            shape_key_name, index = common.decode_string(data, index)
            shapes_keys_list.append(obj.shape_key_add(name=shape_key_name))
        for i in range(shape_keys_count):
            shapes_keys_list[i].vertex_group, index = common.decode_string(data, index)
        for i in range(shape_keys_count):
            relative_key_name, index = common.decode_string(data, index)
            shapes_keys_list[i].relative_key = obj.data.shape_keys.key_blocks[relative_key_name]

        for i in range(shape_keys_count):
            shape_key = shapes_keys_list[i]
            shape_key.mute, index = common.decode_bool(data, index)
            shape_key.value, index = common.decode_float(data, index)
            shape_key.slider_min, index = common.decode_float(data, index)
            shape_key.slider_max, index = common.decode_float(data, index)
            shape_key_data_size, index = common.decode_int(data, index)
            for i in range(shape_key_data_size):
                shape_key.data[i].co = Vector(struct.unpack("3f", data[index : index + 3 * 4]))
                index += 3 * 4
        obj.data.shape_keys.use_relative, index = common.decode_bool(data, index)

    # Vertex Groups
    vg_count, index = common.decode_int(data, index)
    obj.vertex_groups.clear()
    for _i in range(vg_count):
        vg_name, index = common.decode_string(data, index)
        vertex_group = obj.vertex_groups.new(name=vg_name)
        vertex_group.lock_weight, index = common.decode_bool(data, index)
        vg_size, index = common.decode_int(data, index)
        for _elmt_idx in range(vg_size):
            vert_idx, index = common.decode_int(data, index)
            weight, index = common.decode_float(data, index)
            vertex_group.add([vert_idx], weight, "REPLACE")

    # Normals
    obj.data.use_auto_smooth, index = common.decode_bool(data, index)
    obj.data.auto_smooth_angle, index = common.decode_float(data, index)

    has_custom_normal, index = common.decode_bool(data, index)

    if has_custom_normal:
        normals = []
        for _loop in obj.data.loops:
            normal, index = common.decode_vector3(data, index)
            normals.append(normal)
        obj.data.normals_split_custom_set(normals)

    # UV Maps and Vertex Colors are added automatically based on layers in the bmesh
    # We just need to update their name and active_render state:

    # UV Maps
    for uv_layer in obj.data.uv_layers:
        uv_layer.name, index = common.decode_string(data, index)
        uv_layer.active_render, index = common.decode_bool(data, index)

    # Vertex Colors
    for vertex_colors in obj.data.vertex_colors:
        vertex_colors.name, index = common.decode_string(data, index)
        vertex_colors.active_render, index = common.decode_bool(data, index)

    return index


@stats_timer(share_data)
def decode_mesh(client, obj, data, index):
    assert obj.data

    # Clear materials before building faces because it erase material idx of faces
    obj.data.materials.clear()

    byte_size, index = common.decode_int(data, index)
    if byte_size == 0:
        # No base mesh, lets read the baked mesh
        index = decode_bakes_mesh(obj, data, index)
    else:
        index = decode_base_mesh(client, obj, data, index)
        # Skip the baked mesh (its size is encoded here)
        baked_mesh_byte_size, index = common.decode_int(data, index)
        index += baked_mesh_byte_size

    # Materials
    material_names, index = common.decode_string_array(data, index)
    for material_name in material_names:
        material = material_api.get_or_create_material(material_name) if material_name != "" else None
        obj.data.materials.append(material)

    return index
