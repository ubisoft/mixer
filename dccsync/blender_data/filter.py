from typing import Mapping, Iterable, Any, List, Union
from bpy import types as T


class Filter:
    pass


class IncludeTypeFilter(Filter):
    def __init__(self, types: Iterable[Any]):
        self._types: Iterable[Any] = [t.bl_rna for t in types]

    def apply(self, properties):
        return [p for p in properties if p.bl_rna in self._types]


class ExcludeFuncFilter(Filter):
    pass


class ExcludeNameFilter(Filter):
    def __init__(self, names: Iterable[str]):
        self._names: Iterable[str] = names

    def apply(self, properties):
        return [p for p in properties if p.identifier not in self._names]


class IncludeNameFilter(Filter):
    def __init__(self, names: Iterable[str]):
        self._names: Iterable[str]

    def apply(self, properties):
        return [p for p in properties if p.identifier in self._names]


class FilterStack:
    def __init__(self):
        self._filters: Mapping[Any, List[Filter]] = {}

    def get(self, bl_rna):
        pass

    def apply(self, bl_rna, properties):
        filters = self._filters.get(bl_rna, [])
        for filter_ in filters:
            properties = filter_.apply(properties)
        return properties

    def append(self, bl_rna, filters: Union[Filter, Iterable[Filter]]):
        if not isinstance(filters, Iterable):
            filters = [filters]
        current_filters = self._filters.get(bl_rna, [])
        if not current_filters:
            self._filters[bl_rna] = current_filters
        current_filters.extend(filters)


class Context:

    # TODO check plugins and appearing disappearing attributes

    def __init__(self, filter_stack):
        # bl_rna -> properties
        self._properties: Mapping[Any, Iterable[Any]] = {}
        self._filter_stack: FilterStack = filter_stack

    def properties(self, bl_rna):
        properties = self._properties.get(bl_rna)
        if properties is None:
            properties = self._filter_stack.apply(bl_rna, list(bl_rna.properties))
            self._properties[bl_rna] = properties
        return properties


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
]
default_filter.append(
    T.BlendData.bl_rna, (ExcludeNameFilter(blenddata_exclude), IncludeTypeFilter([T.CollectionProperty]))
)
default_context = Context(default_filter)
# todebug
# default_filter.append(T.BlendData.bl_rna, IncludeNameFilter("collections"))
