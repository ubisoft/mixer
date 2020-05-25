from typing import Any, ItemsView, Iterable, List, Mapping, Union

from bpy import types as T  # noqa

from mixer.blender_data.types import is_pointer_to


class Filter:
    def is_active(self):
        return True


# TODO FilterNameIn, FilterNameOut, FilterNameAdd
# properties (included, excluded)


class TypeFilter(Filter):
    """
    Filter on type or Pointer to type.

    T.SceneEEVEE wil match D.scenes[0].eevee although the later is a T.PointerProperty
    """

    def __init__(self, types: Union[Any, Iterable[Any]]):
        types = types if isinstance(types, Iterable) else [types]
        self._types: Iterable[Any] = [t.bl_rna for t in types]

    def matches(self, bl_rna_property):
        return bl_rna_property.bl_rna in self._types or any([is_pointer_to(bl_rna_property, t) for t in self._types])


class TypeFilterIn(TypeFilter):
    def apply(self, properties):
        return [p for p in properties if self.matches(p)]


class TypeFilterOut(TypeFilter):
    def apply(self, properties):
        return [p for p in properties if not self.matches(p)]


class CollectionFilterOut(TypeFilter):
    def apply(self, properties):
        # srna looks like the type inside the collection
        return [
            p
            for p in properties
            if p.bl_rna is not T.CollectionProperty.bl_rna or p.srna and p.srna.bl_rna not in self._types
        ]


class FuncFilterOut(Filter):
    pass


class NameFilter(Filter):
    def __init__(self, names: Union[Any, Iterable[str]]):
        names = names if isinstance(names, Iterable) else [names]
        self._names: Iterable[str] = names


class NameFilterOut(NameFilter):
    def apply(self, properties):
        return [p for p in properties if p.identifier not in self._names]


class NameFilterIn(NameFilter):
    def apply(self, properties):
        return [p for p in properties if p.identifier in self._names]


# true class with isactive()
FilterSet = Mapping[Any, Iterable[Filter]]


def bases(bl_rna):
    b = bl_rna
    while b is not None:
        yield b
        b = None if b.base is None else b.base.bl_rna
    yield None


class FilterStack:
    def __init__(self):
        self._filter_stack: List[FilterSet] = []

    def get(self, bl_rna):
        pass

    def apply(self, bl_rna, properties):
        for class_ in bases(bl_rna):
            bl_rna = None if class_ is None else class_.bl_rna
            for filter_set in self._filter_stack:
                filters = filter_set.get(bl_rna, [])
                filters = filters if isinstance(filters, Iterable) else [filters]
                for filter_ in filters:
                    properties = filter_.apply(properties)
        return properties

    def append(self, filter_set: FilterSet):
        self._filter_stack.append({None if k is None else k.bl_rna: v for k, v in filter_set.items()})


BlRna = Any
PropertyName = str
Property = Any
Properties = Mapping[PropertyName, Property]


class Context:

    # TODO check plugins and appearing disappearing attributes

    def __init__(self, filter_stack):
        self._properties: Mapping[BlRna, Properties] = {}
        self._filter_stack: FilterStack = filter_stack

    def properties(self, bl_rna_property: T.Property = None, bpy_type=None) -> ItemsView:
        if (bl_rna_property is None) and (bpy_type is None):
            return []
        if (bl_rna_property is not None) and (bpy_type is not None):
            raise ValueError("Exactly one of bl_rna and bpy_type must be provided")
        if bl_rna_property is not None:
            bl_rna = bl_rna_property.bl_rna
        elif bpy_type is not None:
            bl_rna = bpy_type.bl_rna
        bl_rna_properties = self._properties.get(bl_rna)
        if bl_rna_properties is None:
            filtered_properties = self._filter_stack.apply(bl_rna, list(bl_rna.properties))
            bl_rna_properties = {p.identifier: p for p in filtered_properties}
            self._properties[bl_rna] = bl_rna_properties
        return bl_rna_properties.items()


default_filter = FilterStack()
blenddata_exclude = [
    # "brushes" generates harmless warnings when EnumProperty properties are initialized with a value not in the enum
    "brushes",
    # TODO actions require to handle the circular reference between ActionGroup.channel and FCurve.group
    "actions",
    # we do not need those
    "screens",
    "window_managers",
    "workspaces",
    # "grease_pencils",
]

# TODO some of these will be included in future read_only exclusion
_exclude_names = {
    "type_info",  # for Available (?) keyingset
    "depsgraph",  # found in Viewlayer
    "rna_type",
    "is_evaluated",
    "original",
    "users",
    "use_fake_user",
    "tag",
    "is_library_indirect",
    "library",
    "override_library",
    "preview",
    "mixer_uuid",
}

# TODO Change to (type, filter) for easier maintenance
default_exclusions = {
    T.BlendData: [NameFilterOut(blenddata_exclude), TypeFilterIn(T.CollectionProperty)],  # selected collections
    # TODO this avoids the recursion path Node.socket , NodeSocker.Node
    # can probably be included in the readonly filter
    T.NodeSocket: [NameFilterOut("node")],
    T.ActionGroup: [NameFilterOut("channels")],
    T.Node: [NameFilterOut("internal_links")],
    #
    T.Image: [NameFilterOut("pixels")],
    T.CompositorNodeRLayers: [NameFilterOut("scene")],
    None: [TypeFilterOut(T.MeshVertex), NameFilterOut(_exclude_names)],
    T.LayerCollection: [
        # Scene.viewlayers[i].layer_collection.collection is Scene.collection,
        # see test_scene_viewlayer_layercollection_is_master
        NameFilterOut("collection"),
        # Seems to be a view of the master collection children
        NameFilterOut("children"),
    ],
    T.ViewLayer: [
        # Not useful. Requires array insertion (to do shortly)
        NameFilterOut("freestyle_settings")
    ],
    T.Scene: [
        # Not required and messy: plenty of uninitialized enums, several settings, like "scuplt" are None and
        # it is unclear how to do it.
        NameFilterOut("tool_settings")
    ],
    T.MeshPolygon: [NameFilterOut("area"), NameFilterOut("edge_keys"), NameFilterOut("loop_indices"),],
}

default_filter.append(default_exclusions)
default_context = Context(default_filter)


safe_filter = FilterStack()
safe_filter.append(default_exclusions)
safe_blenddata = ["cameras", "lights"]
safe_filter.append({T.BlendData: NameFilterIn(safe_blenddata)})
safe_context = Context(safe_filter)
