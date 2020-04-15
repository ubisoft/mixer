# current

### Fixes

- Support more object visibility atributes (#54)
- Collections linked to multiple collections (#44)
- Undo failures for collection rename and other cases (#45)
- Fix scene rename (#43)

# 0.1.0alpha (2020-04-03)

### Release Highlights

First _official_ release of dccsync (to be renamed one day) addon for Blender. This addon allows to work collaboratively between multiple Blender and [VRtist](https://gitlab-ncsa.ubisoft.org/motion-pictures/vrtist).

This alpha version offers basic functionnality to start working in collaboration. However it is not safe at all and can break the scene of the first user that connects to a session.

### Features

Here are features supported for the synchronization of data among Blender clients.

- Object sync
  - Transform
  - Parenting
  - Collections
- Mesh sync
  - Geometry
    - vertices, edges, faces
    - bevel, crease, seam, uv
  - Custom Split Normals
  - Shape Keys
  - Vertex Colors
  - Vertex Groups
- Collections
  - Name
  - Objects
  - Parenting
- Scenes
  - However, while it is technically possible to create and sync scenes, many crash of Blender occurs when switching between them. This issue will be resolved in the next release of dccsync.
- Grease Pencil Objects

### Known Bugs/Limitations

These bugs and limitations are known and will be addressed in future releases:

- Collections
  - Linked into multiple collections
- Scenes
  - Changing active scene can lead to crashes
  - Can possibly happen when changing view layers
- Undo might not work in some cases
- Materials
  - Incomplete, only sync a subset of Principled Material Node
  - Textures will be erased on the first client when sync happen between all of them
- Some grease pencil objects will not be fully synced
- Performance: right now meshes can be fully re-synched even when the geometry is not changed (just selecting another shape key trigger the resync). It can be quite expensive for big meshes.
- Working from computers on differents networks has not been tested enough

Things that are not mentionned are not supported at all right know, in particular:

- Modifiers
- Contraints
- Bones
- Animation
- Specific object attributes (lights attributes, cameras attributes)
- World
- Curves (they will be synched but as meshes, not curves)
- etc.

### Reporting issues

For now, if the issue is for sync Blender - Blender, send an email to:

- laurent.noel@ubisoft.com
- philippe.crassous@ubisoft.com

If the issue if for sync Blender - VRtist, end an email to:

- thomas.capelle@ubisoft.com
- sylvain.magdelaine@ubisoft.com
- nicolas.fauvet@ubisoft.com
