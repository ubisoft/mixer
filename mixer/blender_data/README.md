# Current task

(metaballs)

## todo

- write sequence

      WARNING:root:Not implemented: write sequence of different length (incoming: 1, existing: 0)for <bpy_struct, MetaBall("Mball")>.elements

  and also the collestion of Metaball has a new(metaballtype)

- auto_texture space -> do not save if auto ?

      WARNING:root:write attribute skipped texspace_location for <bpy_struct, MetaBall("Mball")>...
      WARNING:root: ...Error: AttributeError('bpy_struct: attribute "texspace_location" from "MetaBall" is read-only')
      WARNING:root:write attribute skipped texspace_size for <bpy_struct, MetaBall("Mball")>...
      WARNING:root: ...Error: AttributeError('bpy_struct: attribute "texspace_size" from "MetaBall" is read-only')

- TODOs in BpyIdProxySave

## done

- saves a metaball without elements
- build_add_object_to_scene creates wrong type:
- BlendData.instance().reset() on reload plugin, disconnect, connect, join, leave?
- Receive an update for a non existing items means a creation
- `__mixer_blenddata_collection__` deserialized as a \_data field. Use another
  BpyProxyAttribute and manage in Codec ?
- manage differently collection_name and collection_key, not useful n the receiver
  (derive collecion from type, but need to encode type)

# Blender Type system

WARNING, this is a bit confusing

In all cases the Blender type of an attribute named attr*name can be obtained from
the `bl_rna.properties['attr_name']` of its \_parent*, but is is not straightforward.

    D = bpy.data
    s = D.scenes['Scene']
    type(s.gravity)
        <class 'Vector'>
    s.bl_rna_properties['gravity']
        <bpy_struct, FloatProperty("gravity")>
    s.bl_rna.properties['gravity'].is_array
        True
    s.bl_rna.properties['gravity'].array_length
        3
    s.bl_rna.properties['gravity'].array_dimensions
        <bpy_int[3], FloatProperty.array_dimensions>

So in this case `type(s.gravity)` is the easiest way to find out how to store this attribute.

In some cases, it can be obtained from the `bl_rna` of the attribute, but is does not always exist.
For instance, `bl_rna` does not exist for some properties
from plugins (e.g. `cycles`) :

    cycles = bpy.data.scenes['Scene'].view_layers['View Layer'].cycles
    aovs = cycles.aovs
    type(aovs)
        <class 'bpy_prop_collection_idprop'>                                # unusable
    type(cycles.bl_rna.properties['aovs'])
        <class 'bpy.types.CollectionProperty'>                              # unusable
    cycles.bl_rna.properties['aovs']
        <bpy_struct, CollectionProperty("aovs")>                            # useful information from the parent
    cycles.bl_rna.properties['aovs'].fixed_type
        <bpy_struct, Struct("CyclesAOVPass")>                               # The collection element type
    type(cycles.bl_rna.properties['aovs'].fixed_type)
        <class 'cycles.properties.CyclesAOVPass'>                           #
    cycles.bl_rna.properties['aovs'].fixed_type.bl_rna.properties.items()
        [ ('name', <bpy_struct, StringProperty("name")>),                   # yessss
            ('type', <bpy_struct, EnumProperty("type")>)
            ...
        ]

For some types the python binding will do the job, so try it first by testing `type(attr)`.

Also consider :

    D.objects['Cube'].data
        bpy.data.meshes['Cube']
    type(D.objects['Cube'].data)
        <class 'bpy_types.Mesh'>
    D.objects['Cube'].bl_rna.properties['data']
        <bpy_struct, PointerProperty("data")>
    D.objects['Cube'].bl_rna.properties['data'].fixed_type
        <bpy_struct, Struct("ID")>

When `isinstance(attr_property.bl_rna, T.PointerProperty)` is `True`, then `type(attr)` is the _pointee_ type

About collections

    s = D.scenes['Scene']
    # The master collection is a collection on its own, not in D.collections
    s.collection
      bpy.data.scenes['Scene_0'].collection
    type(s.collection)
      <class 'bpy_types.Collection'>
    T.Scene.bl_rna.properties['collection']
      <bpy_struct, PointerProperty("collection")>
    T.Scene.bl_rna.properties['collection'].fixed_type
      <bpy_struct, Struct("Collection")>

    # A collection in D.collections
    D.collections[0]
      bpy.data.collections['Collection_0_0']
    type(D.collections[0])
      <class 'bpy_types.Collection'>
    D.bl_rna.properties['collections']
      <bpy_struct, CollectionProperty("collections")>
    D.bl_rna.properties['collections'].fixed_type
      <bpy_struct, Struct("Collection")>

    D.collections[0].children
      bpy.data.collections['Collection_0_0'].children
    T.Collection.bl_rna.properties['children']
      <bpy_struct, CollectionProperty("children")>
    T.Collection.bl_rna.properties['children'].fixed_type
      <bpy_struct, Struct("Collection")>

    D.collections[0].children[0]
      bpy.data.collections['Collection_0_0_0']
    type(D.collections[0].children[0])
      <class 'bpy_types.Collection'>

Determine explicitely

| Property                                       | Useful ? | Def or ref to Blenddata |
| ---------------------------------------------- | :------: | :---------------------: |
| `T.BlendData.bl_rna.properties['collections']` |    Y     |           Def           |
| `T.Scene.bl_rna.properties['collection']`      |    Y     |          _Def_          |
| `T.Scene.bl_rna.properties['objects']`         |    N     |           Ref           |
| `T.Collection.bl_rna.properties['children']`   |    Y     |           Ref           |
| `T.Collection.bl_rna.properties['objects']`    |    N     |           Ref           |

Exclude all readonly except specified (pointer, collections) ?

Custom properties : `oj.keys()` :
https://stackoverflow.com/questions/21265676/how-do-i-read-out-custom-properties-in-blender-with-python

# Performance for array of structures

## Use foreach_get

In this commit, loading GPencilStrokePoint alone with the following devides SS_2_82 proxy load time by 3. A similar work can be done for meshes

    if hasattr(bl_collection, "bl_rna") and bl_collection.bl_rna is T.GPencilStrokePoints.bl_rna:
      n_points = len(bl_collection)
      args = [
        ("co", 3),
        ("pressure", 1),
        ("select", 1),
        ("strength", 1),
        ("uv_factor", 1),
        ("uv_rotation", 1),
      ]
      for name, l in args:
        self.\_data[name] = [0] _ l _ n_points
        bl_collection.foreach_get(name, self.\_data[name])

https://github.com/KhronosGroup/glTF-Blender-IO/issues/76
https://blender.stackexchange.com/questions/1412/efficient-way-to-get-selected-vertices-via-python-without-iterating-over-the-en

https://blenderartists.org/t/use-of-foreach-get-and-foreach-set/524646/4
https://blender.stackexchange.com/questions/2407/how-to-create-a-mesh-programmatically-without-bmesh

## Load with a generator expresssion into a numpy array

Superseded by `foreach_get`

A possibility to save Arrays of structure (`MeshVertices`, `GPencilStrokePoint`) in a 'single' pass

m=D.meshes['Cube']
vx=m.vertices.values()

1D array, from gererator expression (!). Must be 1D, but can be reshaped afterwards vertex/co-no/xyz or co-no/vertices/xyz

    gen_expr = (f for vertex in vertices for f in (list(vertex.co) + list(vertex.normal)))
    np.fromiter((gen_expr), numpy.float, len(vx)*6)

for gp strokepoint

    gen_expr = (float_ for p in points for float_ in (p.co[0], p.co[1], p.co[2], p.pressure, float(p.select), p.strength, p.uv_factor, p.uv_rotation))
    float_count = 8
    np.fromiter((gen_expr), numpy.float, len(points) \* float_count)

2D, from a list comprehension

    np.asarray([(list(v.co), list(v.normal)) for v in vertices])

# Use cases for (de)serialization

simple strut, nested

    'name': 'scn01'
    'camera': // IDref
    'gravity: [0,0,-10]
    'eevee': // is a Ptr, include or reference ?
    'view_layers' :
    'eevee STRUCT' :
    'view_layers COLL' :

    sparse update
      'scenes' : {
        'scn00' : {
          eevee: {
            use_bloom=False
          }
          current_frame: 2
        }
      }

par type ou categories de type ?

# TODO

## Prio 1

Problèmes structurants qui peuvent masquer une incompréhension

- les sous collections sont inlinées au lieu d'être référencées

# Design and questions (en vrac)

## Data

- Q?? : les pointerproperty peuvent pointer vers un ID (a priori dans blenddata, pas de problème), mais aussi
  sur une structure. Cette dernière structure peut elle etre partagé&e
- properties
  - filter by bpy.type
    - by name
    - by type - bpy_func
  - clarify in type vs custom properties and plugins (cycles)
- elements types
  - arrays
  - collection of non -ids
  - property update (for scenes)
  - children
- proxy structure :
  - navigable ?

## Diff

- split Proxy and Diff ?
  - duplicate iteration algo & filters
- depsgraph update in diff
  - exclude some elements from the diff (vertices, images, ...)

## Message

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

# Docs and links

https://developer.blender.org/source/blender-file/

https://blender.stackexchange.com/questions/55423/how-to-get-the-class-type-of-a-blender-collection-property

https://blender.stackexchange.com/questions/6975/is-it-possible-to-use-bpy-props-pointerproperty-to-store-a-pointer-to-an-object

# For fun

To crash Blender :

    D.screens['Animation'].areas[2].spaces[0].overlay.grid_scale_unit
