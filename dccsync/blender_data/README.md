# Blender Type system

WARNING, this is a bit confusing

In all cases the Blender type of an attribute named attr*name can be obtained from
the `bl_rna.properties['attr_name']` of its \_parent*, but is is not straightforward.

    D = bpy.data
    s = D.scenes['Scene']
    type(gravity)
        <class 'Vector'>
    s.bl_rna_properties['gravity']
        <bpy_struct, FloatProperty("gravity")>
    s.bl_rna.properties['gravity'].is_array
        True
    s.bl_rna.properties['gravity'].array_length
        3
    s.bl_rna.properties['gravity'].array_dimensions
        <bpy_int[3], FloatProperty.array_dimensions>

So in this case `type(gravity)` is the easiest way to find out how to store this attribute.

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
