import bpy
import bmesh
import itertools
import struct
from .broadcaster import common

#  s = bpy.context.selected_objects
# getMeshBuffers(s[0].data)

def getMeshBuffers(blenderMesh):
    bm = bmesh.new()
    bm.from_mesh(blenderMesh)

    # pack vertices
    verts = ((vert.co.x, vert.co.y, vert.co.z) for vert in bm.verts)
    flatBuffer = list(itertools.chain.from_iterable(verts))
    # store vertices count & vertices buffer
    binaryVerticesBuffer = common.intToBytes(len(flatBuffer)) + struct.pack('%sf' % len(flatBuffer), *flatBuffer)
    
    # pack normals
    normals = (vert.normal for vert in bm.verts)
    flatBuffer = list(itertools.chain.from_iterable(normals))
    # store normals buffer
    binaryNormalsBuffer = struct.pack('%sf' % len(flatBuffer), *flatBuffer)

    # pack faces
    flatFaces = []
    faces = (face for face in bm.faces)
    for face in faces:
        count = len(face.verts)
        flatFaces.append(count)
        for ind in range(count):
            flatFaces.append(face.verts[ind].index)
    # store faces count + faces buffer
    binaryFacesBuffer = common.intToBytes(len(flatFaces)) + struct.pack('%sf' % len(flatFaces), *flatFaces)

    return binaryVerticesBuffer + binaryNormalsBuffer + binaryFacesBuffer


