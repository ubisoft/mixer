# TODO

- PropertyGroup contents
- text beyond Scene
- unsupported type set() ??
  - Unsupported attribute type <class 'set'> without bl_rna for attribute {'INCREMENT'}
- collections (master, classic, viewlayer)

# Data

- properties
  - filter by bpy.type
    - by name
    - by type - bpy_func
  - clarify in type vs custom properties and plugins (cycles)
- elements types
  - arrays
  - collection of non -ids
  - CyclesMaterialSettings
  - property update (for scenes)
  - children
- proxy structure :
  - navigable ?

# Diff

- split Proxy and Diff ?
  - duplicate iteration algo & filters
- depsgraph update in diff
  - exclude some elements from the diff (vertices, images, ...)

# Message

- blender only
  - dense message cannot be a dict with so many attribute names
  - use a message format derived from type description. Beware version
- remote specific
- common messages, non blender dump
  - add collection to collection, add object_to_collection ...

## use cases

- lights
  - to blender : nodes, all attributes
  - to VRtist : limited information

## Doc

https://developer.blender.org/source/blender-file/
