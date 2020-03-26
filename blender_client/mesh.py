from ..broadcaster import common
from ..stats import stats_timer
from ..shareData import shareData

import logging
import struct

import bpy
import bmesh
from mathutils import Vector

logger = logging.getLogger(f"dccsync")


def deprecated_buildMesh(obj, data, index):
    # Deprecated: Blender does not load a baked mesh
    byte_size, index = common.decodeInt(data, index)
    if byte_size == 0:
        return index

    positions, index = common.decodeVector3Array(data, index)
    normals, index = common.decodeVector3Array(data, index)
    uvs, index = common.decodeVector2Array(data, index)
    materialIndices, index = common.decodeInt2Array(data, index)
    triangles, index = common.decodeInt3Array(data, index)

    bm = bmesh.new()
    verts = []
    for i in range(len(positions)):
        vertex = bm.verts.new(positions[i])
        # according to https://blender.stackexchange.com/questions/49357/bmesh-how-can-i-import-custom-vertex-normals
        # normals are not working for bmesh...
        vertex.normal = normals[i]
        verts.append(vertex)

    uv_layer = None
    if len(uvs) > 0:
        uv_layer = bm.loops.layers.uv.new()

    currentMaterialIndex = 0
    indexInMaterialIndices = 0
    nextriangleIndex = len(triangles)
    if len(materialIndices) > 1:
        nextriangleIndex = materialIndices[indexInMaterialIndices + 1][0]
    if len(materialIndices) > 0:
        currentMaterialIndex = materialIndices[indexInMaterialIndices][1]

    for i in range(len(triangles)):
        if i >= nextriangleIndex:
            indexInMaterialIndices = indexInMaterialIndices + 1
            nextriangleIndex = len(triangles)
            if len(materialIndices) > indexInMaterialIndices + 1:
                nextriangleIndex = materialIndices[indexInMaterialIndices + 1][0]
            currentMaterialIndex = materialIndices[indexInMaterialIndices][1]

        triangle = triangles[i]
        i1 = triangle[0]
        i2 = triangle[1]
        i3 = triangle[2]
        try:
            face = bm.faces.new((verts[i1], verts[i2], verts[i3]))
            face.material_index = currentMaterialIndex
            if uv_layer:
                face.loops[0][uv_layer].uv = uvs[i1]
                face.loops[1][uv_layer].uv = uvs[i2]
                face.loops[2][uv_layer].uv = uvs[i3]
        except:
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


def decode_layer_float(elmt, layer, data, index):
    elmt[layer], index = common.decodeFloat(data, index)
    return index


def extract_layer_float(elmt, layer):
    return (elmt[layer],)


extract_layer_float.struct = "1f"


def decode_layer_int(elmt, layer, data, index):
    elmt[layer], index = common.decodeInt(data, index)
    return index


def extract_layer_int(elmt, layer):
    return (elmt[layer],)


extract_layer_int.struct = "1i"


def decode_layer_vector(elmt, layer, data, index):
    elmt[layer], index = common.decodeVector3(data, index)
    return index


def extract_layer_vector3(elmt, layer):
    v = elmt[layer]
    return (v[0], v[1], v[2])


extract_layer_vector3.struct = "3f"


def decode_layer_color(elmt, layer, data, index):
    elmt[layer], index = common.decodeColor(data, index)
    return index


def extract_layer_color(elmt, layer):
    color = elmt[layer]
    if len(color) == 3:
        return (color[0], color[1], color[2], 1.0)
    return (color[0], color[1], color[2], color[3])


extract_layer_color.struct = "4f"


def decode_layer_uv(elmt, layer, data, index):
    pin_uv, index = common.decodeBool(data, index)
    uv, index = common.decodeVector2(data, index)
    elmt[layer].pin_uv = pin_uv
    elmt[layer].uv = uv
    return index


def extract_layer_uv(elmt, layer):
    return (elmt[layer].pin_uv, *elmt[layer].uv)


extract_layer_uv.struct = "1I2f"


def decode_bmesh_layer(data, index, layer_collection, element_seq, decode_layer_value_func):
    layer_count, index = common.decodeInt(data, index)
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

    binary_buffer = struct.pack('1I', len(layer_collection))
    if len(layer_collection) > 0:
        binary_buffer += struct.pack(extract_layer_tuple_func.struct * count, *buffer)
    return binary_buffer

# We cannot iterate directory over bm.loops, so we use a generator


def loops_iterator(bm):
    for face in bm.faces:
        for loop in face.loops:
            yield loop


@stats_timer(shareData)
def buildMesh(obj, data, index):
    byte_size, index = common.decodeInt(data, index)
    if byte_size == 0:
        # No Blender mesh, lets read the baked mesh
        return deprecated_buildMesh(obj, data, index)

    bm = bmesh.new()

    position_count, index = common.decodeInt(data, index)
    logger.debug("Reading %d vertices", position_count)

    for pos_idx in range(position_count):
        co, index = common.decodeVector3(data, index)
        normal, index = common.decodeVector3(data, index)
        vert = bm.verts.new(co)
        vert.normal = normal

    bm.verts.ensure_lookup_table()

    index = decode_bmesh_layer(data, index, bm.verts.layers.bevel_weight, bm.verts, decode_layer_float)

    edgeCount, index = common.decodeInt(data, index)
    logger.debug("Reading %d edges", edgeCount)

    edgesData = struct.unpack(f'{edgeCount * 4}I', data[index:index + edgeCount * 4 * 4])
    index += edgeCount * 4 * 4

    for edgeIdx in range(edgeCount):
        v1 = edgesData[edgeIdx * 4]
        v2 = edgesData[edgeIdx * 4 + 1]
        edge = bm.edges.new((bm.verts[v1], bm.verts[v2]))
        edge.smooth = bool(edgesData[edgeIdx * 4 + 2])
        edge.seam = bool(edgesData[edgeIdx * 4 + 3])

    index = decode_bmesh_layer(data, index, bm.edges.layers.bevel_weight, bm.edges, decode_layer_float)
    index = decode_bmesh_layer(data, index, bm.edges.layers.crease, bm.edges, decode_layer_float)

    faceCount, index = common.decodeInt(data, index)
    logger.debug("Reading %d faces", faceCount)

    for fIdx in range(faceCount):
        materialIdx, index = common.decodeInt(data, index)
        smooth, index = common.decodeBool(data, index)
        vertCount, index = common.decodeInt(data, index)
        faceVertices = struct.unpack(f'{vertCount}I', data[index:index + vertCount * 4])
        index += vertCount * 4
        verts = [bm.verts[i] for i in faceVertices]
        face = bm.faces.new(verts)
        face.material_index = materialIdx
        face.smooth = smooth

    index = decode_bmesh_layer(data, index, bm.faces.layers.face_map, bm.faces, decode_layer_int)

    index = decode_bmesh_layer(data, index, bm.loops.layers.uv, loops_iterator(bm), decode_layer_uv)
    index = decode_bmesh_layer(data, index, bm.loops.layers.color, loops_iterator(bm), decode_layer_color)

    bm.to_mesh(obj.data)
    bm.free()

    # Load shape keys
    shape_keys_count, index = common.decodeInt(data, index)
    obj.shape_key_clear()
    if shape_keys_count > 0:
        logger.info("Loading %d shape keys", shape_keys_count)
        shapes_keys_list = []
        for i in range(shape_keys_count):
            shape_key_name, index = common.decodeString(data, index)
            shapes_keys_list.append(obj.shape_key_add(name=shape_key_name))
        for i in range(shape_keys_count):
            shapes_keys_list[i].vertex_group, index = common.decodeString(data, index)
        for i in range(shape_keys_count):
            relative_key_name, index = common.decodeString(data, index)
            print(relative_key_name)
            shapes_keys_list[i].relative_key = obj.data.shape_keys.key_blocks[relative_key_name]

        for i in range(shape_keys_count):
            shape_key = shapes_keys_list[i]
            shape_key.mute, index = common.decodeBool(data, index)
            shape_key.value, index = common.decodeFloat(data, index)
            shape_key.slider_min, index = common.decodeFloat(data, index)
            shape_key.slider_max, index = common.decodeFloat(data, index)
            shape_key_data_size, index = common.decodeInt(data, index)
            for i in range(shape_key_data_size):
                shape_key.data[i].co = Vector(struct.unpack('3f', data[index:index + 3 * 4]))
                index += 3 * 4
        obj.data.shape_keys.use_relative, index = common.decodeBool(data, index)

    # Vertex Groups
    vg_count, index = common.decodeInt(data, index)
    obj.vertex_groups.clear()
    for i in range(vg_count):
        vg_name, index = common.decodeString(data, index)
        vertex_group = obj.vertex_groups.new(name=vg_name)
        vertex_group.lock_weight, index = common.decodeBool(data, index)
        vg_size, index = common.decodeInt(data, index)
        for elmt_idx in range(vg_size):
            vert_idx, index = common.decodeInt(data, index)
            weight, index = common.decodeFloat(data, index)
            vertex_group.add([vert_idx], weight, 'REPLACE')

    # Normals
    obj.data.use_auto_smooth, index = common.decodeBool(data, index)
    obj.data.auto_smooth_angle, index = common.decodeFloat(data, index)

    # UV Maps and Vertex Colors are added automatically based on layers in the bmesh
    # We just need to update their name and active_render state:

    # UV Maps
    for uv_layer in obj.data.uv_layers:
        uv_layer.name, index = common.decodeString(data, index)
        uv_layer.active_render, index = common.decodeBool(data, index)

    # Vertex Colors
    for vertex_colors in obj.data.vertex_colors:
        vertex_colors.name, index = common.decodeString(data, index)
        vertex_colors.active_render, index = common.decodeBool(data, index)

    baked_mesh_byte_size, index = common.decodeInt(data, index)

    return index + baked_mesh_byte_size


@stats_timer(shareData)
def getMeshBuffers(obj):
    stats_timer = shareData.current_stats_timer

    vertices = []
    normals = []
    uvs = []
    indices = []
    materialIndices = []  # array of triangle index, material index

    # compute modifiers
    depsgraph = bpy.context.evaluated_depsgraph_get()
    obj = obj.evaluated_get(depsgraph)

    stats_timer.checkpoint("eval_depsgraph")

    # triangulate mesh (before calculating normals)
    mesh = obj.to_mesh()
    if not mesh:
        return None
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

    # get uv layer
    uvlayer = mesh.uv_layers.active

    currentMaterialIndex = -1
    currentfaceIndex = 0
    logger.debug("Writing %d polygons", len(mesh.polygons))
    for f in mesh.polygons:
        for loop_id in f.loop_indices:
            index = mesh.loops[loop_id].vertex_index
            vertices.extend(mesh.vertices[index].co)
            normals.extend(mesh.loops[loop_id].normal)
            if uvlayer:
                uvs.extend([x for x in uvlayer.data[loop_id].uv])
            indices.append(loop_id)

        if f.material_index != currentMaterialIndex:
            currentMaterialIndex = f.material_index
            materialIndices.append(currentfaceIndex)
            materialIndices.append(currentMaterialIndex)
        currentfaceIndex = currentfaceIndex + 1

    stats_timer.checkpoint("make_buffers")

    # Vericex count + binary vertices buffer
    size = len(vertices) // 3
    binaryVerticesBuffer = common.intToBytes(
        size, 4) + struct.pack(f'{len(vertices)}f', *vertices)

    stats_timer.checkpoint("write_verts")

    # Normals count + binary normals buffer
    size = len(normals) // 3
    binaryNormalsBuffer = common.intToBytes(
        size, 4) + struct.pack(f'{len(normals)}f', *normals)

    stats_timer.checkpoint("write_normals")

    # UVs count + binary uvs buffer
    size = len(uvs) // 2
    binaryUVsBuffer = common.intToBytes(
        size, 4) + struct.pack(f'{len(uvs)}f', *uvs)

    stats_timer.checkpoint("write_uvs")

    # material indices + binary material indices buffer
    size = len(materialIndices) // 2
    binaryMaterialIndicesBuffer = common.intToBytes(
        size, 4) + struct.pack(f'{len(materialIndices)}I', *materialIndices)

    stats_timer.checkpoint("write_material_indices")

    # triangle indices count + binary triangle indices buffer
    size = len(indices) // 3
    binaryIndicesBuffer = common.intToBytes(
        size, 4) + struct.pack(f'{len(indices)}I', *indices)

    stats_timer.checkpoint("write_tri_idx_buff")

    return binaryVerticesBuffer + binaryNormalsBuffer + binaryUVsBuffer + binaryMaterialIndicesBuffer + binaryIndicesBuffer


@stats_timer(shareData)
def dump_mesh(mesh_data):
    stats_timer = shareData.current_stats_timer

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
        verts_array.extend((*vert.co, *vert.normal))

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

    # Shape keys
    # source https://blender.stackexchange.com/questions/111661/creating-shape-keys-using-python
    if mesh_data.shape_keys == None:
        binary_buffer += common.encodeInt(0)  # Indicate 0 key blocks
    else:
        logger.debug("Writing %d shape keys", len(mesh_data.shape_keys.key_blocks))

        binary_buffer += common.encodeInt(len(mesh_data.shape_keys.key_blocks))
        # Encode names
        for key_block in mesh_data.shape_keys.key_blocks:
            binary_buffer += common.encodeString(key_block.name)
        # Encode vertex group names
        for key_block in mesh_data.shape_keys.key_blocks:
            binary_buffer += common.encodeString(key_block.vertex_group)
        # Encode relative key names
        for key_block in mesh_data.shape_keys.key_blocks:
            binary_buffer += common.encodeString(key_block.relative_key.name)
        # Encode data
        shape_keys_buffer = []
        fmt_str = ""
        for key_block in mesh_data.shape_keys.key_blocks:
            shape_keys_buffer.extend((key_block.mute, key_block.value, key_block.slider_min,
                                      key_block.slider_max, len(key_block.data)))
            fmt_str += f"1I1f1f1f1I{(3 * len(key_block.data))}f"
            for i in range(len(key_block.data)):
                shape_keys_buffer.extend(key_block.data[i].co)
        binary_buffer += struct.pack(f"{fmt_str}", *shape_keys_buffer)

        binary_buffer += common.encodeBool(mesh_data.shape_keys.use_relative)

    stats_timer.checkpoint("shape_keys")

    return binary_buffer


@stats_timer(shareData)
def getSourceMeshBuffers(obj):
    mesh_data = obj.to_mesh()
    if not mesh_data:
        return None
    binary_buffer = dump_mesh(mesh_data)

    # Vertex Groups
    verts_per_group = {}
    for vertex_group in obj.vertex_groups:
        verts_per_group[vertex_group.index] = []

    for vert in mesh_data.vertices:
        for vg in vert.groups:
            verts_per_group[vg.group].append((vert.index, vg.weight))

    binary_buffer += common.encodeInt(len(obj.vertex_groups))
    for vertex_group in obj.vertex_groups:
        binary_buffer += common.encodeString(vertex_group.name)
        binary_buffer += common.encodeBool(vertex_group.lock_weight)
        binary_buffer += common.encodeInt(len(verts_per_group[vertex_group.index]))
        for vg_elmt in verts_per_group[vertex_group.index]:
            binary_buffer += common.encodeInt(vg_elmt[0])
            binary_buffer += common.encodeFloat(vg_elmt[1])

    # Normals
    binary_buffer += common.encodeBool(mesh_data.use_auto_smooth)
    binary_buffer += common.encodeFloat(mesh_data.auto_smooth_angle)

    # UV Maps
    for uv_layer in mesh_data.uv_layers:
        binary_buffer += common.encodeString(uv_layer.name)
        binary_buffer += common.encodeBool(uv_layer.active_render)

    # Vertex Colors
    for vertex_colors in mesh_data.vertex_colors:
        binary_buffer += common.encodeString(vertex_colors.name)
        binary_buffer += common.encodeBool(vertex_colors.active_render)

    # todo: custom split normals
    # if mesh_data.has_custom_normals:
    #         # Custom normals are all (0, 0, 0) until calling calc_normals_split() or calc_tangents().
    #     mesh_data.calc_normals_split()

    return binary_buffer
