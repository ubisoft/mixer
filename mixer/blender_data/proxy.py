from __future__ import annotations

import array
from contextlib import contextmanager
from collections import defaultdict
from dataclasses import dataclass
from enum import IntEnum
import itertools
import logging
import traceback
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple, TypeVar, Union
from uuid import uuid4

import bpy
import bpy.types as T  # noqa
import mathutils

from mixer.blender_data.filter import Context, safe_depsgraph_updates, safe_context, skip_bpy_data_item
from mixer.blender_data import specifics
from mixer.blender_data.blenddata import (
    BlendData,
    collection_name_to_type,
    rna_identifier_to_collection_name,
    bl_rna_to_type,
)
from mixer.blender_data.types import bases_of, is_builtin, is_vector, is_matrix, is_pointer_to, sub_id_type

DEBUG = True

BpyBlendDiff = TypeVar("BpyBlendDiff")
BpyPropCollectionDiff = TypeVar("BpyPropCollectionDiff")
BpyIDProxy = TypeVar("BpyIDProxy")

logger = logging.getLogger(__name__)

# Access path to the ID starting from bpy.data, such as ("cameras", "Camera")
BlenddataPath = Tuple[str, str]


# storing everything in a single dictionary is easier for serialization
MIXER_SEQUENCE = "__mixer_sequence__"


def debug_check_stack_overflow(func, *args, **kwargs):
    """
    Use as a function decorator to detect probable stack overflow in case of circular references

    Beware : inspect performance is very poor.
    sys.setrecursionlimit cannot be used because it will possibly break the Blender VScode
    plugin and StackOverflowException is not caught by VScode "Raised exceptions" breakpoint.
    """

    def wrapper(*args, **kwargs):
        import inspect

        if len(inspect.stack(0)) > 50:
            raise RuntimeError("Possible stackoverflow")
        return func(*args, **kwargs)

    return wrapper


# Using a context doubles load time in SS2.82. This remains true for a null context
# Remmoving the "with" lines halves loading time (!!)
class DebugContext:
    """
    Context class only used during BpyBlendProxy construction, to keep contextual data during traversal
    of the blender data hierarchy and perform safety checkes
    """

    serialized_addresses: Set[bpy.types.ID] = set()  # Already serialized addresses (struct or IDs), for debug
    property_stack: List[Tuple[str, any]] = []  # Stack of properties up to this point in the visit
    property_value: Any
    limit_notified: bool = False

    @contextmanager
    def enter(self, property_name, property_value):
        self.property_stack.append((property_name, property_value))
        yield
        self.property_stack.pop()
        self.serialized_addresses.add(id(property_value))

    def visit_depth(self):
        # Utility for debug
        return len(self.property_stack)

    def property_fullpath(self):
        # Utility for debug
        return ".".join([p[0] for p in self.property_stack])


@dataclass
class UnresolvedRef:
    """A datablock reference that could not be resolved when target.init() needed to be called
    because the referenced datablock was not yet received.

    No suitable ordering can easily be provided by the sender for many reasons including Collection.children
    referencing other collections and Scene.sequencer strips that can reference other scenes
    """

    target: T.bpy_prop_collection
    proxy: BpyIDRefProxy


RootIds = Set[T.ID]
IDProxies = Mapping[str, BpyIDProxy]
IDs = Mapping[str, T.ID]
UnresolvedRefs = Dict[str, UnresolvedRef]


@dataclass
class VisitState:
    # This class remains from an early implementation. It gathers BpyBlendProxy state encapsulated
    # so that it can be used during the data traversal
    # This parts need refactoring and simplification (some items are now useless)
    root_ids: RootIds
    id_proxies: IDProxies
    ids: IDs
    unresolved_refs: UnresolvedRefs
    context: Context
    debug_context: DebugContext = DebugContext()


class LoadElementAs(IntEnum):
    STRUCT = 0
    ID_REF = 1
    ID_DEF = 2


def same_rna(a, b):
    return a.bl_rna == b.bl_rna


def is_ID_subclass_rna(bl_rna):  # noqa
    """
    Return true if the RNA is of a subclass of bpy.types.ID
    """
    return issubclass(bl_rna_to_type(bl_rna), bpy.types.ID)


def load_as_what(attr_property: bpy.types.Property, attr: any, root_ids: RootIds):
    """
    Determine if we must load an attribute as a struct, a blenddata collection element (ID_DEF)
    or a reference to a BlendData collection element (ID_REF)

    All T.Struct are loaded as struct
    All T.ID are loaded ad IDRef (that is pointer into a D.blendata collection) except
    for specific case. For instance the scene master "collection" is not a D.collections item.

    Arguments
    parent -- the type that contains the attribute names attr_name, for instance T.Scene
    attr_property -- a bl_rna property of a attribute, that can be a CollectionProperty or a "plain" attribute
    """
    # Reference to an ID element at the root of the blend file
    if attr in root_ids:
        return LoadElementAs.ID_REF

    if same_rna(attr_property, T.CollectionProperty):
        if is_ID_subclass_rna(attr_property.fixed_type.bl_rna):
            # Collections at root level are not handled by this code (See BpyBlendProxy.load()) so here it
            # should be a nested collection and IDs should be ref to root collections.
            return LoadElementAs.ID_REF
        else:
            # Only collections at the root level of blendfile are id def, so here it can only be struct
            return LoadElementAs.STRUCT

    if isinstance(attr, T.Mesh):
        return LoadElementAs.ID_REF

    if same_rna(attr_property, T.PointerProperty):
        element_property = attr_property.fixed_type
    else:
        element_property = attr_property

    if is_ID_subclass_rna(element_property.bl_rna):
        # TODO this is wrong for scene master collection
        return LoadElementAs.ID_DEF

    return LoadElementAs.STRUCT


class Delta:
    def __init__(self, value: Optional[Any] = None):
        self.value = value

    def __str__(self):
        return f"<{self.__class__.__name__}({self.value})>"


class DeltaAddition(Delta):
    pass


class DeltaDeletion(Delta):
    # TODO it is overkill to have the deleted value in DeltaDeletion in all cases.
    # we mostly need it if it is a BpyIDRefProxy
    pass


class DeltaUpdate(Delta):
    pass


class ProxyDiff:
    def __init__(self):
        self._data: Dict[Union[str, int], Any] = {}

    def append(self, k: Union[str, int], delta: Delta):
        assert k not in self._data.keys()
        self._data[k] = delta

    def empty(self):
        return len(self._data) != 0


MAX_DEPTH = 30


# @debug_check_stack_overflow
def read_attribute(attr: Any, attr_property: T.Property, visit_state: VisitState):
    """
    Load a property into a python object of the appropriate type, be it a Proxy or a native python object


    """
    debug_context = visit_state.debug_context
    if debug_context.visit_depth() > MAX_DEPTH:
        # stop before hitting the recursion limit, it is easier to debug
        # if we arrive here, we have cyclical data references that should be excluded in filter.py
        if not debug_context.limit_notified:
            debug_context.limit_notified = True
            logger.error("Maximum property depth exceeded. Deeper properties ignored. Path :")
            logger.error(debug_context.property_fullpath())
        return

    attr_type = type(attr)

    if is_builtin(attr_type):
        return attr
    if is_vector(attr_type):
        return list(attr)
    if is_matrix(attr_type):
        return [list(col) for col in attr.col]

    # We have tested the types that are usefully reported by the python binding, now harder work.
    # These were implemented first and may be better implemented with the bl_rna property of the parent struct
    if attr_type == T.bpy_prop_array:
        return [e for e in attr]

    if attr_type == T.bpy_prop_collection:
        # need to know for each element if it is a ref or id
        load_as = load_as_what(attr_property, attr, visit_state.root_ids)
        assert load_as != LoadElementAs.ID_DEF
        if load_as == LoadElementAs.STRUCT:
            return BpyPropStructCollectionProxy.make(attr_property).load(attr, attr_property, visit_state)
        else:
            # LoadElementAs.ID_REF:
            # References into Blenddata collection, for instance D.scenes[0].objects
            return BpyPropDataCollectionProxy().load_as_IDref(attr, visit_state)

    # TODO merge with previous case
    if isinstance(attr_property, T.CollectionProperty):
        return BpyPropStructCollectionProxy().load(attr, attr_property, visit_state)

    bl_rna = attr_property.bl_rna
    if bl_rna is None:
        logger.warning("Not implemented: attribute %s", attr)
        return None

    if issubclass(attr_type, T.PropertyGroup):
        return BpyPropertyGroupProxy().load(attr, visit_state)

    if issubclass(attr_type, T.ID):
        if attr.is_embedded_data:
            return BpyIDProxy.make(attr_property).load(attr, visit_state)
        else:
            return BpyIDRefProxy().load(attr, visit_state)
    elif issubclass(attr_type, T.bpy_struct):
        return BpyStructProxy().load(attr, visit_state)

    raise ValueError(f"Unsupported attribute type {attr_type} without bl_rna for attribute {attr} ")


class Proxy:
    def __eq__(self, other):
        if self.__class__ is not other.__class__:
            return False
        if len(self._data) != len(other._data):
            return False

        # TODO test same keys
        # TODO test _bpy_collection
        for k, v in self._data.items():
            if k not in other._data.keys():
                return False
            if v != other._data[k]:
                return False
        return True

    def __contains__(self, value):
        return value in self._data

    def init(self, _):
        pass

    def data(self, key: Union[str, int], resolve_delta=True) -> Any:
        """Return the data at key, which may be a struct member, a dict value or an array value,

        Args:
            key: Integer or string to be used as index or key to the data
            resolve_delta: If True, and the data is a Delta, will return the delta value
        """

        def resolve(data):
            if isinstance(data, Delta) and resolve_delta:
                return data.value
            return data

        if isinstance(key, int):
            if MIXER_SEQUENCE in self._data:
                try:
                    return resolve(self._data[MIXER_SEQUENCE][key])
                except IndexError:
                    return None
            else:
                # used by the diff mode that generates a dict with int keys
                return resolve(self._data.get(key))
        else:
            return resolve(self._data.get(key))

    def save(self, bl_instance: any, attr_name: str):
        """
        Save this proxy into a blender object
        """
        logger.warning(f"Not implemented: save() for {self.__class__} {bl_instance}.{attr_name}")

    def apply(
        self,
        parent: Any,
        key: Union[int, str],
        delta: Optional[DeltaUpdate],
        visit_state: VisitState,
        to_blender: bool = True,
    ) -> Proxy:
        raise NotImplementedError(f"Proxy.apply() for {parent}[{key}]")

    def diff(
        self, container: Union[T.bpy_prop_collection, T.Struct], key: Union[str, int], visit_state: VisitState
    ) -> Optional[ProxyDiff]:
        raise NotImplementedError(f"diff for {container}[{key}]")


class StructLikeProxy(Proxy):
    """
    Holds a copy of a Blender bpy_struct
    """

    # TODO limit depth like in multiuser. Anyhow, there are circular references in f-curves
    def __init__(self):

        # We care for some non readonly properties. Collection object are tagged read_only byt can be updated with

        # Beware :

        # >>> bpy.types.Scene.bl_rna.properties['collection']
        # <bpy_struct, PointerProperty("collection")>

        # TODO is_readonly may be only interesting for "base types". FOr Collections it seems always set to true
        # meaning that the collection property slot cannot be updated although the object is mutable
        # TODO we also care for some readonly properties that are in fact links to data collections

        # The property information are taken from the containing class, not from the attribute.
        # So we get :
        #   T.Scene.bl_rna.properties['collection']
        #       <bpy_struct, PointerProperty("collection")>
        #   T.Scene.bl_rna.properties['collection'].fixed_type
        #       <bpy_struct, Struct("Collection")>
        # But if we take the information in the attribute we get information for the dereferenced
        # data
        #   D.scenes[0].collection.bl_rna
        #       <bpy_struct, Struct("Collection")>
        #
        # We need the former to make a difference between T.Scene.collection and T.Collection.children.
        # the former is a pointer
        self._data = {}
        pass

    def load(self, bl_instance: any, visit_state: VisitState):

        """
        Load a Blender object into this proxy
        """
        self._data.clear()
        properties = visit_state.context.properties(bl_instance)
        # includes properties from the bl_rna only, not the "view like" properties like MeshPolygon.edge_keys
        # that we do not want to load anyway
        properties = specifics.conditional_properties(bl_instance, properties)
        for name, bl_rna_property in properties:
            attr = getattr(bl_instance, name)
            attr_value = read_attribute(attr, bl_rna_property, visit_state)
            # Also write None values. We use them to reset attributes like Camera.dof.focus_object
            self._data[name] = attr_value
        return self

    def save(self, bl_instance: Any, key: Union[int, str], visit_state: VisitState):
        """
        Save this proxy into a Blender attribute
        """
        assert isinstance(key, (int, str))

        if isinstance(key, int):
            target = bl_instance[key]
        elif isinstance(bl_instance, T.bpy_prop_collection):
            # TODO append an element :
            # https://blenderartists.org/t/how-delete-a-bpy-prop-collection-element/642185/4
            target = bl_instance.get(key)
            if target is None:
                target = specifics.add_element(self, bl_instance, key, visit_state)
        else:
            specifics.pre_save_struct(self, bl_instance, key)
            target = getattr(bl_instance, key, None)

        if target is None:
            if isinstance(bl_instance, T.bpy_prop_collection):
                logger.warning(f"Cannot write to '{bl_instance}', attribute '{key}' because it does not exist.")
                logger.warning("Note: Not implemented write to dict")
            else:
                # Don't log this because it produces too many log messages when participants have plugins
                # f"Note: May be due to a plugin used by the sender and not on this Blender"
                # f"Note: May be due to unimplemented 'use_{key}' implementation for type {type(bl_instance)}"
                # f"Note: May be {bl_instance}.{key} should not have been saved"
                pass

            return

        for k, v in self._data.items():
            write_attribute(target, k, v, visit_state)

    def apply(
        self,
        parent: Any,
        key: Union[int, str],
        struct_delta: Optional[DeltaUpdate],
        visit_state: VisitState,
        to_blender: bool = True,
    ) -> StructLikeProxy:
        """
        Apply diff to the Blender attribute at parent[key] or parent.key and update accordingly this proxy entry
        at key.

        Args:
            parent ([type]): [description]
            key ([type]): [description]
            delta ([type]): [description]
            visit_state ([type]): [description]

        Returns:
            [type]: [description]
        """
        if struct_delta is None:
            return

        assert isinstance(key, (int, str))

        # TODO factozize with save

        if isinstance(key, int):
            struct = parent[key]
        elif isinstance(parent, T.bpy_prop_collection):
            # TODO append an element :
            # https://blenderartists.org/t/how-delete-a-bpy-prop-collection-element/642185/4
            struct = parent.get(key)
            if struct is None:
                struct = specifics.add_element(self, parent, key, visit_state)
        else:
            specifics.pre_save_struct(self, parent, key)
            struct = getattr(parent, key, None)

        struct_update = struct_delta.value
        assert type(struct_update) == type(self)
        for k, member_delta in struct_update._data.items():
            try:
                current_value = self._data.get(k)
                self._data[k] = apply_attribute(struct, k, current_value, member_delta, visit_state, to_blender)
            except Exception as e:
                logger.warning(f"StructLike.apply(). Processing {member_delta}")
                logger.warning(f"... for {struct}.{k}")
                logger.warning(f"... Exception: {e}")
                logger.warning("... Update ignored")
                continue
        return self

    def diff(self, struct: T.Struct, _: T.Property, visit_state: VisitState) -> Optional[DeltaUpdate]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        As this proxy tracks a Struct or ID, the result will be a DeltaUpdate that contains a BpyStructProxy
        or a BpyIDProxy with an Delta item per added, deleted or updated property. One expect only DeltaUpdate,
        although DeltalAddition or DeltaDeletion may be produced when an addon is loaded or unloaded while
        a room is joined. This situation, is not really supported as there is no handler to track
        addon changes.

        Args:
            struct: the Struct that must be diffed against this proxy
            struct_property: the Property of struct as found in its enclosing object
        """

        # Create a proxy that will be populated with attributes differences, resulting in a hollow dict,
        # as opposed as the dense self
        diff = self.__class__()
        diff.init(struct)

        # PERF accessing the properties from the context is **far** cheaper that iterating over
        # _data and the getting the properties with
        #   member_property = struct.bl_rna.properties[k]
        # line to which py-spy attributes 20% of the total diff !

        for k, member_property in visit_state.context.properties(struct):
            # TODO in test_differential.StructDatablockRef.test_remove
            # target et a scene, k is world and v (current world value) is None
            # so diff fails. v should be a BpyIDRefNoneProxy

            # make a difference between None value and no member
            try:
                member = getattr(struct, k)
            except AttributeError:
                logger.warning(f"diff: unknown attribute {k} in {struct}")
                continue

            proxy_data = self._data.get(k)
            delta = diff_attribute(member, member_property, proxy_data, visit_state)
            if delta is not None:
                diff._data[k] = delta

        # if anything has changed, wrap the hollow proxy in a DeltaUpdate. This may be superfluous but
        # it is homogenous with additions and deletions
        if len(diff._data):
            return DeltaUpdate(diff)

        return None


class BpyPropertyGroupProxy(StructLikeProxy):
    pass


class BpyStructProxy(StructLikeProxy):
    pass


class BpyIDProxy(BpyStructProxy):
    """
    Holds a copy of a datablock, standalone (bpy.data.cameras['Camera']) or embedded.
    """

    # name of the bpy.data collection this datablock belongs to, None if embedded in another datablock

    def __init__(self):
        super().__init__()
        self._bpy_data_collection: str = None
        self._class_name: str = ""
        self._datablock_uuid: Optional[str] = None

    def init(self, datablock: T.ID):
        if datablock is not None:
            if not datablock.is_embedded_data:
                type_name = sub_id_type(type(datablock)).bl_rna.identifier
                self._bpy_data_collection = rna_identifier_to_collection_name[type_name]
                self._datablock_uuid = datablock.mixer_uuid
            self._class_name = datablock.__class__.__name__

    @classmethod
    def make(cls, attr_property):

        if is_pointer_to(attr_property, T.NodeTree):
            return NodeTreeProxy()
        return BpyIDProxy()

    @property
    def is_standalone_datablock(self):
        return self._bpy_data_collection is not None

    @property
    def is_embedded_data(self):
        return self._bpy_data_collection is None

    def mixer_uuid(self) -> Optional[str]:
        return self._datablock_uuid

    def rename(self, new_name: str):
        self._data["name"] = new_name
        self._data["name_full"] = new_name

    def __str__(self) -> str:
        return f"BpyIDProxy {self.mixer_uuid()} for bpy.data.{self.collection_name}[{self.data('name')}]"

    def update_from_datablock(self, bl_instance: T.ID, visit_state: VisitState):
        self.load(bl_instance, visit_state, bpy_data_collection_name=None)

    def load(
        self,
        bl_instance: T.ID,
        visit_state: VisitState,
        bpy_data_collection_name: str = None,
    ):
        """"""
        if bl_instance.is_embedded_data and bpy_data_collection_name is not None:
            logger.error(
                f"BpyIDProxy.load() for {bl_instance} : is_embedded_data is True and bpy_prop_collection is {bpy_data_collection_name}. Item ignored"
            )
            return

        if bl_instance.is_embedded_data:
            self._bpy_data_collection = None

        if bpy_data_collection_name is not None:
            self._bpy_data_collection = bpy_data_collection_name

        self._class_name = bl_instance.__class__.__name__
        self._data.clear()
        properties = visit_state.context.properties(bl_instance)
        # this assumes that specifics.py apply only to ID, not Struct
        properties = specifics.conditional_properties(bl_instance, properties)
        for name, bl_rna_property in properties:
            attr = getattr(bl_instance, name)
            attr_value = read_attribute(attr, bl_rna_property, visit_state)
            # Also write None values to reset attributes like Camera.dof.focus_object
            # TODO for scene, test difference, only send update if dirty as continuous updates to scene
            # master collection will conflicting writes with Master Collection
            self._data[name] = attr_value

        specifics.post_save_id(self, bl_instance)

        uuid = bl_instance.get("mixer_uuid")
        if uuid:
            # It is a bpy.data ID, not an ID "embedded" inside another ID, like scene.collection
            id_ = visit_state.ids.get(uuid)
            if id_ is not bl_instance:
                # this occurs when
                # - when we find a reference to a BlendData ID that was not loaded
                # - the ID are not properly ordred at creation time, for instance (objects, meshes)
                # instead of (meshes, objects) : a bug
                logger.debug("BpyIDProxy.load(): %s not in visit_state.ids[uuid]", bl_instance)
            self._datablock_uuid = bl_instance.mixer_uuid
            visit_state.id_proxies[uuid] = self

        return self

    @property
    def collection_name(self) -> Optional[str]:
        """
        The name of the bpy.data collection this object is a proxy, None if an embedded ID
        """
        return self._bpy_data_collection

    @property
    def collection(self) -> T.bpy_prop_collection:
        return getattr(bpy.data, self.collection_name)

    def target(self, visit_state: VisitState) -> T.ID:
        return visit_state.ids.get(self.mixer_uuid())

    def create_standalone_datablock(self, visit_state: VisitState) -> Tuple[Optional[T.ID], Optional[str]]:
        """
        Save this proxy into its target standalone datablock
        """
        if self.target(visit_state):
            logger.warning(f"create_standalone_datablock: datablock already registered : {self}")
            logger.warning("... update ignored")
            return None, None
        renames = []
        incoming_name = self.data("name")
        existing_datablock = self.collection.get(incoming_name)
        if existing_datablock:
            if not existing_datablock.mixer_uuid:
                # A datablock created by VRtist command in the same command batch
                # Not an error, we will make it ours by adding the uuid and registering it
                logger.info(f"create_standalone_datablock for {self} found existing datablock from VRtist")
                datablock = existing_datablock
            else:
                if existing_datablock.mixer_uuid != self.mixer_uuid():
                    # local has a datablock with the same name as remote wants to create, but a different uuid.
                    # It is a simultaneous creation : rename local's datablock. Remote will do the same thing on its side
                    # and we will end up will all renamed datablocks
                    unique_name = f"{existing_datablock.name}_{existing_datablock.mixer_uuid}"
                    logger.warning(
                        f"create_standalone_datablock: Creation name conflict. Renamed existing bpy.data.{self.collection_name}[{existing_datablock.name}] into {unique_name}"
                    )

                    # Rename local's and issue a rename command
                    renames.append(
                        (
                            existing_datablock.mixer_uuid,
                            existing_datablock.name,
                            unique_name,
                            f"Conflict bpy.data.{self.collection_name}[{self.data('name')}] into {unique_name}",
                        )
                    )
                    existing_datablock.name = unique_name

                    datablock = specifics.bpy_data_ctor(self.collection_name, self, visit_state)
                else:
                    # a creation for a datablock that we already have. This should not happen
                    logger.error(f"create_standalone_datablock: unregistered uuid for {self}")
                    logger.error("... update ignored")
                    return None, None
        else:
            datablock = specifics.bpy_data_ctor(self.collection_name, self, visit_state)

        if datablock is None:
            logger.warning(f"Cannot create bpy.data.{self.collection_name}[{self.data('name')}]")
            return None, None

        if DEBUG:
            name = self.data("name")
            if self.collection.get(name) != datablock:
                logger.error(f"Name mismatch after creation of bpy.data.{self.collection_name}[{name}] ")

        datablock.mixer_uuid = self.mixer_uuid()

        datablock = specifics.pre_save_id(self, datablock, visit_state)
        if datablock is None:
            logger.warning(f"BpyIDProxy.update_standalone_datablock() {self} pre_save_id returns None")
            return None, None

        for k, v in self._data.items():
            write_attribute(datablock, k, v, visit_state)

        return datablock, renames

    def update_standalone_datablock(self, datablock: T.ID, delta: DeltaUpdate, visit_state: VisitState) -> T.ID:
        """
        Update this proxy and datablock according to delta
        """
        datablock = specifics.pre_save_id(delta.value, datablock, visit_state)
        if datablock is None:
            logger.warning(f"BpyIDProxy.update_standalone_datablock() {self} pre_save_id returns None")
            return None

        self.apply(self.collection, datablock.name, delta, visit_state)
        return datablock

    def save(self, bl_instance: any = None, attr_name: str = None, visit_state: VisitState = None) -> T.ID:
        """
        Save this proxy into an existing datablock that may be
        - a bpy.data member item
        - an embedded datablock
        """
        collection_name = self.collection_name
        if collection_name is not None:
            logger.info(f"IDproxy save standalone {self}")
            # a standalone datablock in a bpy.data collection

            if bl_instance is None:
                bl_instance = self.collection
            if attr_name is None:
                attr_name = self.data("name")
            id_ = bl_instance.get(attr_name)

            if id_ is None:
                logger.warning(f"IDproxy save standalone {self}, not found. Creating")
                id_ = specifics.bpy_data_ctor(collection_name, self, visit_state)
                if id_ is None:
                    logger.warning(f"Cannot create bpy.data.{collection_name}[{attr_name}]")
                    return None
                if DEBUG:
                    if bl_instance.get(attr_name) != id_:
                        logger.error(f"Name mismatch after creation of bpy.data.{collection_name}[{attr_name}] ")
                id_.mixer_uuid = self.mixer_uuid()
        else:
            logger.info(f"IDproxy save embedded {self}")
            # an is_embedded_data datablock. pre_save id will retrieve it by calling target
            id_ = getattr(bl_instance, attr_name)
            pass

        target = specifics.pre_save_id(self, id_, visit_state)
        if target is None:
            logger.warning(f"BpyIDProxy.save() {bl_instance}.{attr_name} is None")
            return None

        for k, v in self._data.items():
            write_attribute(target, k, v, visit_state)

        return target

    def update_from_proxy(self, other: BpyIDProxy):
        # Currently, we receive the full list of attributes, so replace everything.
        # Do not keep existing attribute as they may not be applicable any more to the new object. For instance
        # if a light has been morphed from POINT to SUN, the 'falloff_curve' attribute no more exists
        #
        # To perform differential updates in the future, we will need markers for removed attributes
        self._data = other._data

    def apply_to_proxy(
        self,
        datablock: T.ID,
        delta: Optional[DeltaUpdate],
        visit_state: VisitState,
    ):
        """
        Apply diff to this proxy entry, but do not update Blender

        Args:
            parent ([type]): [description]
            key ([type]): [description]
            delta ([type]): [description]
            visit_state ([type]): [description]

        Returns:
            [type]: [description]
        """
        if delta is None:
            return

        update = delta.value
        assert type(update) == type(self)
        for k, delta in update._data.items():
            try:
                current_value = self._data.get(k)
                self._data[k] = apply_attribute(datablock, k, current_value, delta, visit_state, to_blender=False)
            except Exception as e:
                logger.warning(f"StructLike.apply(). Processing {delta}")
                logger.warning(f"... for {datablock}.{k}")
                logger.warning(f"... Exception: {e}")
                logger.warning("... Update ignored")
                continue


class NodeLinksProxy(BpyStructProxy):
    def __init__(self):
        super().__init__()

    def load(self, bl_instance, _, visit_state: VisitState):
        # NodeLink contain pointers to Node and NodeSocket.
        # Just keep the names to restore the links in ShaderNodeTreeProxy.save

        seq = []
        for link in bl_instance:
            link_data = (
                link.from_node.name,
                link.from_socket.name,
                link.to_node.name,
                link.to_socket.name,
            )
            seq.append(link_data)
        self._data[MIXER_SEQUENCE] = seq
        return self


class NodeTreeProxy(BpyIDProxy):
    def __init__(self):
        super().__init__()

    def save(self, bl_instance: any, attr_name: str, visit_state: VisitState):
        # see https://stackoverflow.com/questions/36185377/how-i-can-create-a-material-select-it-create-new-nodes-with-this-material-and
        # Saving NodeTree.links require access to NodeTree.nodes, so we need an implementation at the NodeTree level

        node_tree = getattr(bl_instance, attr_name)

        # save links last
        for k, v in self._data.items():
            if k != "links":
                write_attribute(node_tree, k, v, visit_state)

        node_tree.links.clear()
        seq = self.data("links").data(MIXER_SEQUENCE)
        for src_node, src_socket, dst_node, dst_socket in seq:
            src_socket = node_tree.nodes[src_node].outputs[src_socket]
            dst_socket = node_tree.nodes[dst_node].inputs[dst_socket]
            node_tree.links.new(src_socket, dst_socket)


class BpyIDRefProxy(Proxy):
    """
    A reference to a standalone datablock

    Examples of such references are :
    - Camera.dof.focus_object
    """

    def __init__(self):
        self._datablock_uuid: str = None
        # Not used but "required" by the json codec
        self._data: Dict[str, Any] = {}
        self._bpy_data_collection: str = None
        self._initial_name: str = None

        self._debug_name = None

    def __str__(self) -> str:
        return f"{self.__class__.__name__}({self._datablock_uuid}, bpy.data.{self._bpy_data_collection}, name at creation: {self._initial_name})"

    def load(self, datablock: T.ID, visit_state: VisitState) -> BpyIDRefProxy:
        """
        Load the reference to a standalone datablock
        """
        assert not datablock.is_embedded_data

        # see HACK in target()
        # Base type closest to ID (e.g. Light for Point)
        type_ = bases_of(type(datablock).bl_rna)[-2]
        type_name = type_.bl_rna.identifier
        self._bpy_data_collection = rna_identifier_to_collection_name[type_name]
        self._initial_name = datablock.name

        self._datablock_uuid = datablock.mixer_uuid

        self._debug_name = str(datablock)
        return self

    def save(self, container: Union[T.ID, T.bpy_prop_collection], key: str, visit_state: VisitState):
        """
        Save the standalone datablock reference represented by self into a datablock member (Scene.camera)
        or a collection item (Scene.collection.children["Collection"])
        """
        ref_target = self.target(visit_state)
        if ref_target is None:
            logger.warning(f"BpyIDRefProxy. Target of {container}.{key} not found. Last known name {self._debug_name}")
        if isinstance(container, T.bpy_prop_collection):
            # reference stored in a collection
            if isinstance(key, str):
                try:
                    container[key] = ref_target
                except TypeError as e:
                    logger.warning(
                        f"BpyIDRefProxy.save() exception while saving {ref_target} into {container}[{key}]..."
                    )
                    logger.warning(f"...{e}")
            else:
                # is there a case for this ?
                logger.warning(f"Not implemented: BpyIDRefProxy.save() for IDRef into collection {container}[{key}]")
        else:
            # reference stored in a struct
            if not container.bl_rna.properties[key].is_readonly:
                try:
                    # This is what saves Camera.dof.focus_object
                    setattr(container, key, ref_target)
                except Exception as e:
                    logger.warning(f"write attribute skipped {key} for {container}...")
                    logger.warning(f" ...Error: {repr(e)}")

    def target(self, visit_state: VisitState) -> T.ID:
        """
        The datablock referenced
        """
        datablock = visit_state.ids.get(self._datablock_uuid)
        if datablock is None:
            # HACK
            # We are trying to find the target of a datablock reference like Object.mesh and the datablock
            # is not known to the proxy state (visit_state). This occurs when the target datablock is of
            # un unsynchronized type (Mesh, currently). If the datablock can be found by name, consider
            # it was created under the hood by a VRtist command and register it.
            collection = getattr(bpy.data, self._bpy_data_collection, None)
            if collection is None:
                logger.warning(f"{self}: reference to unknown collection bpy.data.{self.collection_name}")
                return None

            datablock = collection.get(self._initial_name)
            if datablock is None:
                logger.warning(f"{self}: target unknown")
                return None

            assert datablock.mixer_uuid == ""
            datablock.mixer_uuid = self._datablock_uuid
            visit_state.ids[self._datablock_uuid] = datablock
            logger.warning(f"{self}: registering {datablock}")

        return datablock

    def apply(
        self,
        parent: Any,
        key: Union[int, str],
        delta: Optional[DeltaUpdate],
        visit_state: VisitState,
        to_blender: bool = True,
    ) -> StructLikeProxy:
        update: BpyIDRefProxy = delta.value
        if to_blender:
            assert type(update) == type(self)
            assert self._bpy_data_collection == update._bpy_data_collection

            datablock = visit_state.ids.get(update._datablock_uuid)
            setattr(parent, key, datablock)
        return update

    def diff(self, datablock: T.ID, datablock_property: T.Property, visit_state: VisitState) -> Optional[ProxyDiff]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        As this proxy tracks a reference to a standalone datablock, the result

        Args:
            datablock: the databloc tha must be diffed against this proxy
            datablock_property: the property of datablock as found in its enclosing object
        """

        if datablock is None:
            return DeltaDeletion()

        value = read_attribute(datablock, datablock_property, visit_state)
        assert isinstance(value, BpyIDRefProxy)
        if value._datablock_uuid != self._datablock_uuid:
            return DeltaUpdate(value)
        else:
            return None


def ensure_uuid(item: bpy.types.ID) -> str:
    uuid = item.get("mixer_uuid")
    if not uuid:
        uuid = str(uuid4())
        item.mixer_uuid = uuid
    return uuid


# in sync with soa_initializers
soable_properties = {
    T.BoolProperty,
    T.IntProperty,
    T.FloatProperty,
    mathutils.Vector,
    mathutils.Color,
    mathutils.Quaternion,
}

# in sync with soa_initializers
soa_initializers = {
    bool: [False],
    int: array.array("l", [0]),
    float: array.array("f", [0.0]),
    mathutils.Vector: array.array("f", [0.0]),
    mathutils.Color: array.array("f", [0.0]),
    mathutils.Quaternion: array.array("f", [0.0]),
}


# TODO : is there any way to find these automatically ? Seems easy to determine if a struct is simple enough so that
# an array of struct can be loaded as an Soa. Is it worth ?
# Beware that MeshVertex must be handled as SOA although "groups" is a variable length item.
# Enums are not handled by foreach_get()
soable_collection_properties = {
    T.GPencilStroke.bl_rna.properties["points"],
    T.GPencilStroke.bl_rna.properties["triangles"],
    T.Mesh.bl_rna.properties["vertices"],
    T.Mesh.bl_rna.properties["edges"],
    T.Mesh.bl_rna.properties["loops"],
    # messy: :MeshPolygon.vertices has variable length, not 3 as stated in the doc, so ignore
    # T.Mesh.bl_rna.properties["polygons"],
    T.MeshUVLoopLayer.bl_rna.properties["data"],
    T.MeshLoopColorLayer.bl_rna.properties["data"],
}


def is_soable_collection(prop):
    return prop in soable_collection_properties


def is_soable_property(bl_rna_property):
    return any(isinstance(bl_rna_property, soable) for soable in soable_properties)


def soa_initializer(attr_type, length):
    # According to bpy_rna.c:foreach_getset() and rna_access.c:rna_raw_access() implementations,
    # some cases are implemented as memcpy (buffer interface) or array iteration (sequences),
    # with more subcases that require reallocation when the buffer type is not suitable,
    # TODO try to be smart
    element_init = soa_initializers[attr_type]
    if isinstance(element_init, array.array):
        return array.array(element_init.typecode, element_init.tolist() * length)
    elif isinstance(element_init, list):
        return element_init * length


class AosElement(Proxy):
    """
    A structure member inside a bpy_prop_collection loaded as a structure of array element

    For instance, MeshVertex.groups is a bpy_prop_collection of variable size and it cannot
    be loaded as an Soa in Mesh.vertices. So Mesh.vertices loads a "groups" AosElement
    """

    def __init__(self):
        self._data: Mapping[str, List] = {}

    def load(
        self,
        bl_collection: bpy.types.bpy_prop_collection,
        item_bl_rna,
        attr_name: str,
        visit_state: VisitState,
    ):
        """
        - bl_collection: a collection of structure, e.g. T.Mesh.vertices
        - item_bl_rna: the bl_rna if the structure contained in the collection, e.g. T.MeshVertices.bl_rna
        - attr_name: a member if the structure to be loaded as a sequence, e.g. "groups"
        """

        logger.warning(f"Not implemented. Load AOS  element for {bl_collection}.{attr_name} ")
        return self

        # The code below was initially written for MeshVertex.groups, but MeshVertex.groups is updated
        # via Object.vertex_groups so it is useless in this case. Any other usage ?

        # self._data.clear()
        # attr_property = item_bl_rna.properties[attr_name]
        # # A bit overkill:
        # # for T.Mesh.vertices[...].groups, generates a BpyPropStructCollectionProxy per Vertex even if empty
        # self._data[MIXER_SEQUENCE] = [
        #     read_attribute(getattr(item, attr_name), attr_property, context, visit_context) for item in bl_collection
        # ]
        # return self

    def save(self, bl_collection: bpy.types.bpy_prop_collection, attr_name: str, visit_state: VisitState):

        logger.warning(f"Not implemented. Save AOS  element for {bl_collection}.{attr_name} ")

        # see comment in load()

        # sequence = self._data.get(MIXER_SEQUENCE)
        # if sequence is None:
        #     return

        # if len(sequence) != len(bl_collection):
        #     # Avoid by writing SOA first ? Is is enough to resize the target
        #     logger.warning(
        #         f"Not implemented. Save AO size mistmatch (incoming {len(sequence)}, target {len(bl_collection)}for {bl_collection}.{attr_name} "
        #     )
        #     return

        # for i, value in enumerate(sequence):
        #     target = bl_collection[i]
        #     write_attribute(target, attr_name, value)


class SoaElement(Proxy):
    """
    A structure member inside a bpy_prop_collection loaded as a structure of array element

    For instance, Mesh.vertices[].co is loaded as an SoaElement of Mesh.vertices. Its _data is an array
    """

    def __init__(self):
        self._data: Union[array.array, [List]] = None

    def load(self, bl_collection: bpy.types.bpy_prop_collection, attr_name: str, prototype_item):
        attr = getattr(prototype_item, attr_name)
        attr_type = type(attr)
        length = len(bl_collection)
        if is_vector(attr_type):
            length *= len(attr)
        elif attr_type is T.bpy_prop_array:
            length *= len(attr)
            attr_type = type(attr[0])

        buffer = soa_initializer(attr_type, length)

        # "RuntimeError: internal error setting the array" means that the array is ill-formed.
        # Check rna_access.c:rna_raw_access()
        bl_collection.foreach_get(attr_name, buffer)
        self._data = buffer
        return self

    def save(self, bl_collection, attr_name, visit_state: VisitState):
        # TODO : serialization currently not performed
        bl_collection.foreach_set(attr_name, self._data)


# TODO make these functions generic after enough sequences have been seen
# TODO move to specifics.py
def write_curvemappoints(target, src_sequence, visit_state: VisitState):
    src_length = len(src_sequence)

    # CurveMapPoints specific (alas ...)
    if src_length < 2:
        logger.error(f"Invalid length for curvemap: {src_length}. Expected at least 2")
        return

    # truncate dst
    while src_length < len(target):
        target.remove(target[-1])

    # extend dst
    while src_length > len(target):
        # .new() parameters are CurveMapPoints specific
        # for CurvemapPoint, we can initialize to anything then overwrite. Not sure this is doable for other types
        # new inserts in head !
        # Not optimal for big arrays, but much simpler given that the new() parameters depend on the collection
        # in a way that cannot be determined automatically
        target.new(0.0, 0.0)

    assert src_length == len(target)
    for i in range(src_length):
        write_attribute(target, i, src_sequence[i], visit_state)


def write_metaballelements(target, src_sequence, visit_state: VisitState):
    src_length = len(src_sequence)

    # truncate dst
    while src_length < len(target):
        target.remove(target[-1])

    # extend dst
    while src_length > len(target):
        # Creates a BALL, but will be changed by write_attribute
        target.new()

    assert src_length == len(target)
    for i in range(src_length):
        write_attribute(target, i, src_sequence[i], visit_state)


class BpyPropStructCollectionProxy(Proxy):
    """
    Proxy to a bpy_prop_collection of non-ID in bpy.data
    """

    def __init__(self):
        self._data: Mapping[Union[str, int], BpyIDProxy] = {}

    @classmethod
    def make(cls, attr_property: T.Property):
        if attr_property.srna == T.NodeLinks.bl_rna:
            return NodeLinksProxy()
        return BpyPropStructCollectionProxy()

    def load(self, bl_collection: T.bpy_prop_collection, bl_collection_property: T.Property, visit_state: VisitState):

        if len(bl_collection) == 0:
            self._data.clear()
            return self

        if is_soable_collection(bl_collection_property):
            # TODO too much work at load time to find soable information. Do it once for all.

            # Hybrid array_of_struct/ struct_of_array
            # Hybrid because MeshVertex.groups does not have a fixed size and is not soa-able, but we want
            # to treat other MeshVertex members as SOAs.
            # Could be made more efficient later on. Keep the code simple until save() is implemented
            # and we need better
            prototype_item = bl_collection[0]
            item_bl_rna = bl_collection_property.fixed_type.bl_rna
            for attr_name, bl_rna_property in visit_state.context.properties(item_bl_rna):
                if is_soable_property(bl_rna_property):
                    # element type supported by foreach_get
                    self._data[attr_name] = SoaElement().load(bl_collection, attr_name, prototype_item)
                else:
                    # no foreach_get (variable length arrays like MeshVertex.groups, enums, ...)
                    self._data[attr_name] = AosElement().load(bl_collection, item_bl_rna, attr_name, visit_state)
        else:
            # no keys means it is a sequence. However bl_collection.items() returns [(index, item)...]
            is_sequence = not bl_collection.keys()
            if is_sequence:
                # easier for the encoder to always have a dict
                self._data = {MIXER_SEQUENCE: [BpyStructProxy().load(v, visit_state) for v in bl_collection.values()]}
            else:
                self._data = {k: BpyStructProxy().load(v, visit_state) for k, v in bl_collection.items()}

        return self

    def save(self, bl_instance: any, attr_name: str, visit_state: VisitState):
        """
        Save this proxy into a Blender object
        """
        target = getattr(bl_instance, attr_name, None)
        if target is None:
            # # Don't log this, too many messages
            # f"Saving {self} into non existent attribute {bl_instance}.{attr_name} : ignored"
            return

        sequence = self._data.get(MIXER_SEQUENCE)
        if sequence:
            srna = bl_instance.bl_rna.properties[attr_name].srna
            if srna:
                # TODO move to specifics
                if srna.bl_rna is bpy.types.CurveMapPoints.bl_rna:
                    write_curvemappoints(target, sequence, visit_state)
                elif srna.bl_rna is bpy.types.MetaBallElements.bl_rna:
                    write_metaballelements(target, sequence, visit_state)
                else:
                    # TODO WHAT ??
                    pass

            elif len(target) == len(sequence):
                for i, v in enumerate(sequence):
                    # TODO this way can only save items at pre-existing slots. The bpy_prop_collection API
                    # uses struct specific API and ctors:
                    # - CurveMapPoints uses: .new(x, y) and .remove(point), no .clear(). new() inserts in head !
                    #   Must have at least 2 points left !
                    # - NodeTreeOutputs uses: .new(type, name), .remove(socket), has .clear()
                    # - ActionFCurves uses: .new(data_path, index=0, action_group=""), .remove(fcurve)
                    # - GPencilStrokePoints: .add(count), .pop()
                    write_attribute(target, i, v, visit_state)
            else:
                logger.warning(
                    f"Not implemented: write sequence of different length (incoming: {len(sequence)}, existing: {len(target)})for {bl_instance}.{attr_name}"
                )
        else:
            # dictionary
            specifics.truncate_collection(target, self._data.keys())
            for k, v in self._data.items():
                write_attribute(target, k, v, visit_state)

    def apply(
        self, parent: Any, key: Union[int, str], delta: Optional[DeltaUpdate], visit_state: VisitState, to_blender=True
    ) -> StructLikeProxy:

        assert isinstance(key, (int, str))

        # TODO factozize with save

        if isinstance(key, int):
            collection = parent[key]
        elif isinstance(parent, T.bpy_prop_collection):
            # TODO append an element :
            # https://blenderartists.org/t/how-delete-a-bpy-prop-collection-element/642185/4
            collection = parent.get(key)
            if collection is None:
                collection = specifics.add_element(self, parent, key, visit_state)
        else:
            specifics.pre_save_struct(self, parent, key)
            collection = getattr(parent, key, None)

        update = delta.value
        assert type(update) == type(self)

        sequence = self._data.get(MIXER_SEQUENCE)
        if sequence:

            # input validity assertions
            add_indices = [i for i, delta in enumerate(update._data.values()) if isinstance(delta, DeltaAddition)]
            del_indices = [i for i, delta in enumerate(update._data.values()) if isinstance(delta, DeltaDeletion)]
            if add_indices or del_indices:
                # Cannot have deletions and additions
                assert not add_indices or not del_indices
                indices = add_indices if add_indices else del_indices
                # Check that adds and deleted are at the end
                assert not indices or indices[-1] == len(update._data) - 1
                # check that adds and deletes are contiguous
                assert all(a + 1 == b for a, b in zip(indices, iter(indices[1:])))

            for k, delta in update._data.items():
                try:
                    if isinstance(delta, DeltaUpdate):
                        sequence[k] = apply_attribute(collection, k, sequence[k], delta, visit_state, to_blender)
                    elif isinstance(delta, DeltaDeletion):
                        item = collection[k]
                        if to_blender:
                            collection.remove(item)
                        del sequence[k]
                    else:  # DeltaAddition
                        raise NotImplementedError("Not implemented: DeltaAddition for array")
                        # TODO pre save for use_curves
                        # since ordering does not include this requirement
                        if to_blender:
                            write_attribute(collection, k, delta.value, visit_state)
                        sequence[k] = delta.value

                except Exception as e:
                    logger.warning(f"BpyPropStructCollectionProxy.apply(). Processing {delta}")
                    logger.warning(f"... for {collection}[{k}]")
                    logger.warning(f"... Exception: {e}")
                    logger.warning("... Update ignored")
                    continue
        else:
            for k, delta in update._data.items():
                try:
                    if isinstance(delta, DeltaDeletion):
                        # TODO do all collections have remove ?
                        # see "name collision" in diff()
                        k = k[1:]
                        if to_blender:
                            item = collection[k]
                            collection.remove(item)
                        del self._data[k]
                    elif isinstance(delta, DeltaAddition):
                        # TODO pre save for use_curves
                        # since ordering does not include this requirement

                        # see "name collision" in diff()
                        k = k[1:]
                        if to_blender:
                            write_attribute(collection, k, delta.value, visit_state)
                        self._data[k] = delta.value
                    else:
                        self._data[k] = apply_attribute(collection, k, self._data[k], delta, visit_state, to_blender)
                except Exception as e:
                    logger.warning(f"BpyPropStructCollectionProxy.apply(). Processing {delta}")
                    logger.warning(f"... for {collection}[{k}]")
                    logger.warning(f"... Exception: {e}")
                    logger.warning("... Update ignored")
                    continue

        return self

    def diff(
        self, collection: T.bpy_prop_collection, collection_property: T.Property, visit_state: VisitState
    ) -> Optional[ProxyDiff]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        This proxy tracks a collection of items indexed by string (e.g Scene.render.views) or int.
        The result will be a ProxyDiff that contains a Delta item per added, deleted or updated item

        Args:
            collection; the collection that must be diffed agains this proxy
            collection_property; the property os collection as found in its enclosing object
        """

        diff = self.__class__()
        item_property = collection_property.fixed_type

        sequence = self._data.get(MIXER_SEQUENCE)
        if sequence:
            # indexed by int
            # TODO This produces one DeltaDeletion by removed item. Produce a range in case may items are
            # deleted

            # since the diff sequence is hollow, we cannot store it in a list. Use a dict with int keys instead
            for i, (proxy_value, blender_value) in enumerate(itertools.zip_longest(sequence, collection)):
                if proxy_value is None:
                    value = read_attribute(collection[i], item_property, visit_state)
                    diff._data[i] = DeltaAddition(value)
                elif blender_value is None:
                    diff._data[i] = DeltaDeletion(self.data(i))
                else:
                    delta = diff_attribute(collection[i], item_property, proxy_value, visit_state)
                    if delta is not None:
                        diff._data[i] = delta
        else:
            # index by string. This is similar to BpyPropDataCollectionproxy.diff
            # Renames are detected as Deletion + Addition

            # This assumes that keys ordring is the same in the proxy and in blender, which is
            # guaranteed by the fact that proxy load uses Context.properties()

            bl_rna = getattr(collection, "bl_rna", None)
            if bl_rna is not None and isinstance(
                bl_rna, (type(T.ObjectModifiers.bl_rna), type(T.ObjectGpencilModifiers))
            ):
                # TODO move this into specifics.py
                # order-dependant collections with different types like Modifiers
                proxy_names = list(self._data.keys())
                blender_names = collection.keys()
                proxy_types = [self.data(name).data("type") for name in proxy_names]
                blender_types = [collection[name].type for name in blender_names]
                if proxy_types == blender_types and proxy_names == blender_names:
                    # Same types and names : do sparse modification
                    for name in proxy_names:
                        delta = diff_attribute(collection[name], item_property, self.data(name), visit_state)
                        if delta is not None:
                            diff._data[name] = delta
                else:
                    # names or types do not match, rebuild all
                    # There are name collisions during Modifier order change for instance, so prefix
                    # the names to avoid them (using a tuple fails in the json encoder)
                    for name in proxy_names:
                        diff._data["D" + name] = DeltaDeletion(self.data(name))
                    for name in blender_names:
                        value = read_attribute(collection[name], item_property, visit_state)
                        diff._data["A" + name] = DeltaAddition(value)
            else:
                # non order dependant, uniform types
                proxy_keys = self._data.keys()
                blender_keys = collection.keys()
                added_keys = blender_keys - proxy_keys
                for k in added_keys:
                    value = read_attribute(collection[k], item_property, visit_state)
                    diff._data["A" + k] = DeltaAddition(value)

                deleted_keys = proxy_keys - blender_keys
                for k in deleted_keys:
                    diff._data["D" + k] = DeltaDeletion(self.data(k))

                maybe_updated_keys = proxy_keys & blender_keys
                for k in maybe_updated_keys:
                    delta = diff_attribute(collection[k], item_property, self.data(k), visit_state)
                    if delta is not None:
                        diff._data[k] = delta
        if len(diff._data):
            return DeltaUpdate(diff)

        return None


CreationChangeset = List[BpyIDProxy]
UpdateChangeset = List[DeltaUpdate]
# uuid, debug_display
RemovalChangeset = List[Tuple[str, str]]
# uuid, old_name, new_name, debug_display
RenameChangeset = List[Tuple[str, str, str, str]]


class Changeset:
    def __init__(self):
        self.creations: CreationChangeset = []
        self.removals: RemovalChangeset = []
        self.renames: RenameChangeset = []
        self.updates: UpdateChangeset = []


class BpyPropDataCollectionProxy(Proxy):
    """
    Proxy to a bpy_prop_collection of standalone datablocks, be it one of bpy.data collections
    or a collection like Scene.collection.objects.

    This proxy keeps track of the state of the whole collection. If the tracked collection is a bpy.data
    collection (e.g.bpy.data.objects), the proxy contents will be instances of BpyIDProxy.
    Otherwise (e.g. Scene.collection.objects) the proxy contents are instances of BpyIDRefProxy
    that reference items in bpy.data collections
    """

    def __init__(self):
        # On item per datablock. The key is the uuid, which eases rename management
        self._data: Mapping[str, BpyIDProxy] = {}

    def __len__(self):
        return len(self._data)

    def load_as_ID(self, bl_collection: bpy.types.bpy_prop_collection, visit_state: VisitState):  # noqa N802
        """
        Load bl_collection elements as plain IDs, with all element properties. Use this to load from bpy.data
        """
        for name, item in bl_collection.items():
            collection_name = BlendData.instance().bl_collection_name_from_ID(item)
            if skip_bpy_data_item(collection_name, item):
                continue
            with visit_state.debug_context.enter(name, item):
                uuid = ensure_uuid(item)
                # # HACK: Skip objects with a mesh in order to process D.objects withtout processing D.meshes
                # # - writing meshes is not currently implemented and we must avoid double processing with VRtist
                # # - reading objects is required for metaballs
                # if collection_name == "objects" and isinstance(item.data, T.Mesh):
                #     continue
                # # /HACK
                self._data[uuid] = BpyIDProxy().load(item, visit_state, bpy_data_collection_name=collection_name)

        return self

    def load_as_IDref(self, bl_collection: bpy.types.bpy_prop_collection, visit_state: VisitState):  # noqa N802
        """
        Load bl_collection elements as referenced into bpy.data
        """
        for name, item in bl_collection.items():
            with visit_state.debug_context.enter(name, item):
                uuid = item.mixer_uuid
                self._data[uuid] = BpyIDRefProxy().load(item, visit_state)
        return self

    def save(self, parent: Any, key: str, visit_state: VisitState):
        """
        Save this Proxy into a Blender property
        """
        if not self._data:
            return

        target = getattr(parent, key, None)
        if target is None:
            # Don't log this, too many messages
            # f"Saving {self} into non existent attribute {bl_instance}.{attr_name} : ignored"
            return

        link = getattr(target, "link", None)
        unlink = getattr(target, "unlink", None)
        if link is not None and unlink is not None:
            if not len(target):
                for _, ref_proxy in self._data.items():
                    datablock = ref_proxy.target(visit_state)
                    if datablock:
                        link(datablock)
                    else:
                        # The reference will be resolved when the referenced datablock will be loaded
                        uuid = ref_proxy._datablock_uuid
                        logger.info(f"unresolved reference {parent}.{key} -> {ref_proxy}")
                        unresolved_list = visit_state.unresolved_refs[uuid]
                        unresolved_list.append((target, ref_proxy))
            else:
                logger.warning(f"Saving into non empty collection: {target}. Ignored")
        else:
            for k, v in self._data.items():
                write_attribute(target, k, v, visit_state)

    def find(self, key: str):
        return self._data.get(key)

    def create_datablock(
        self, incoming_proxy: BpyIDProxy, visit_state: VisitState
    ) -> Tuple[Optional[T.ID], Optional[RenameChangeset]]:
        """Create a bpy.data datablock from a received BpyIDProxy and update the proxy structures accordingly

        Receiver side

        Args:
            incoming_proxy : this proxy contents is used to update the bpy.data collection item
        """

        datablock, renames = incoming_proxy.create_standalone_datablock(visit_state)

        # One existing scene from the document loaded at join time could not be removed. Remove it now
        if (
            incoming_proxy.collection_name == "scenes"
            and len(bpy.data.scenes) == 2
            and bpy.data.scenes[0].name == "_mixer_to_be_removed_"
        ):
            from mixer.blender_client.scene import delete_scene

            delete_scene(bpy.data.scenes[0])

        if not datablock:
            return None, None

        uuid = incoming_proxy.mixer_uuid()
        self._data[uuid] = incoming_proxy
        visit_state.root_ids.add(datablock)
        visit_state.ids[uuid] = datablock
        visit_state.id_proxies[uuid] = incoming_proxy

        unresolved_refs = visit_state.unresolved_refs.get(uuid)
        if unresolved_refs:
            for collection, ref_proxy in unresolved_refs:
                ref_target = ref_proxy.target(visit_state)
                logger.info(f"create_datablock: resolving reference {collection}.link({ref_target}")
                collection.link(ref_target)
            del visit_state.unresolved_refs[uuid]

        return datablock, renames

    def update_datablock(self, delta: DeltaUpdate, visit_state: VisitState):
        """Update a bpy.data item from a received BpyIDProxy and update the proxy structures accordingly

        Receiver side

        Args:
            proxy : this proxy contents is used to update the bpy.data collection item
        """
        incoming_proxy = delta.value
        uuid = incoming_proxy.mixer_uuid()

        proxy: BpyIDProxy = visit_state.id_proxies.get(uuid)
        if proxy is None:
            logger.error(
                f"update_datablock(): Missing proxy for bpy.data.{incoming_proxy.collection_name}[{incoming_proxy.data('name')}] uuid {uuid}"
            )
            return

        if proxy.mixer_uuid() != incoming_proxy.mixer_uuid():
            logger.error(
                f"update_datablock : uuid mismatch between incoming {incoming_proxy.mixer_uuid()} ({incoming_proxy}) and existing {proxy.mixer_uuid} ({proxy})"
            )
            return

        # the ID will have changed if the object has been morphed (change light type, for instance)
        existing_id = visit_state.ids.get(uuid)
        if existing_id is None:
            logger.warning(f"Non existent uuid {uuid} while updating {proxy.collection_name}[{proxy.data('name')}]")
            return None

        id_ = proxy.update_standalone_datablock(existing_id, delta, visit_state)
        if existing_id != id_:
            # Not a problem for light morphing
            logger.warning(f"Update_datablock changes datablock {existing_id} to {id_}")
            visit_state.root_ids.remove(existing_id)
            visit_state.root_ids.add(id_)
            visit_state.ids[uuid] = id_

        return id_

    def remove_datablock(self, proxy: BpyIDProxy, datablock: T.ID):
        """Remove a bpy.data collection item and update the proxy structures

        Receiver side

        Args:
            uuid: the mixer_uuid of the datablock
        """
        # TODO scene and last_scene_ ...
        logger.info("Perform removal for %s", proxy)
        try:
            if isinstance(datablock, T.Scene):
                from mixer.blender_client.scene import delete_scene

                delete_scene(datablock)
            else:
                proxy.collection.remove(datablock)
        except ReferenceError as e:
            # We probably have processed previously the deletion of a datablock referenced by Object.data (e.g. Light).
            # On both sides it deletes the Object as well. So the sender issues a message for object deletion
            # but deleting the light on this side has already deleted the object.
            # Alternatively we could try to sort messages on the sender side
            logger.warning(f"Exception during remove_datablock for {proxy}")
            logger.warning(f"... {e}")
        uuid = proxy.mixer_uuid()
        del self._data[uuid]

    def rename_datablock(self, proxy: BpyIDProxy, new_name: str, datablock: T.ID):
        """
        Rename a bpy.data collection item and update the proxy structures

        Receiver side

        Args:
            uuid: the mixer_uuid of the datablock
        """
        logger.info("rename_datablock proxy %s datablock %s into %s", proxy, datablock, new_name)
        proxy.rename(new_name)
        datablock.name = new_name

    def update(self, diff: BpyPropCollectionDiff, visit_state: VisitState) -> Changeset:
        """
        Update the proxy according to the diff
        """
        changeset = Changeset()
        # Sort so that the tests receive the messages in deterministic order. Sad but not very harmfull
        added_names = sorted(diff.items_added.keys())
        for name in added_names:
            collection_name = diff.items_added[name]
            logger.info("Perform update/creation for %s[%s]", collection_name, name)
            try:
                # TODO could have a datablock directly
                collection = getattr(bpy.data, collection_name)
                id_ = collection.get(name)
                if id_ is None:
                    logger.error("update/ request addition for %s[%s] : not found", collection_name, name)
                    continue
                uuid = ensure_uuid(id_)
                visit_state.root_ids.add(id_)
                visit_state.ids[uuid] = id_
                proxy = BpyIDProxy().load(id_, visit_state, bpy_data_collection_name=collection_name)
                visit_state.id_proxies[uuid] = proxy
                self._data[uuid] = proxy
                changeset.creations.append(proxy)
            except Exception:
                logger.error(f"Exception during update/added for {collection_name}[{name}]:")
                for line in traceback.format_exc().splitlines():
                    logger.error(line)

        for proxy in diff.items_removed:
            try:
                logger.info("Perform removal for %s", proxy)
                uuid = proxy.mixer_uuid()
                changeset.removals.append((uuid, str(proxy)))
                del self._data[uuid]
                id_ = visit_state.ids[uuid]
                visit_state.root_ids.remove(id_)
                del visit_state.id_proxies[uuid]
                del visit_state.ids[uuid]
            except Exception:
                logger.error(f"Exception during update/removed for proxy {proxy})  :")
                for line in traceback.format_exc().splitlines():
                    logger.error(line)

        #
        # Handle spontaneous renames
        #
        # Say
        # - local and remote are synced with 2 objects with uuid/name D7/A FC/B
        # - local renames D7/A into B
        #   - D7 is actually renamed into B.001 !
        #   - we detect (D7 -> B.001)
        #   - remote proceses normally
        # - local renames D7/B.001 into B
        #   - D7 is renamed into B
        #   - FC is renamed into B.001
        #   - we detect (D7->B, FC->B.001)
        #   - local result is (D7/B, FC/B.001)
        # - local repeatedly renames the item named B.001 into B
        # - at some point on remote, the execution of a rename command will provoke a spontaneous rename,
        #   resulting in a situation where remote has FC/B.001 and D7/B.002 linked to the
        #   Master collection and also a FC/B unlinked
        #
        for proxy, new_name in diff.items_renamed:
            uuid = proxy.mixer_uuid()
            if proxy.collection[new_name] is not visit_state.ids[uuid]:
                logger.error(
                    f"update rename : {proxy.collection}[{new_name}] is not {visit_state.ids[uuid]} for {proxy}, {uuid}"
                )
            if visit_state.ids[uuid] not in visit_state.root_ids:
                logger.error(f"update rename : {visit_state.ids[uuid]} not in visit_state.root_ids for {proxy}, {uuid}")

            old_name = proxy.data("name")
            changeset.renames.append((proxy.mixer_uuid(), old_name, new_name, str(proxy)))
            proxy.rename(new_name)

        return changeset

    def apply(
        self,
        parent: Any,
        key: Union[int, str],
        collection_delta: Optional[DeltaUpdate],
        visit_state: VisitState,
        to_blender: bool = True,
    ) -> BpyPropDataCollectionProxy:

        # WARNING this is only for collections of IDrefs, like Scene.collection.objects
        # not the right place

        collection_update: BpyPropDataCollectionProxy = collection_delta.value
        assert type(collection_update) == type(self)
        collection = getattr(parent, key)
        for k, ref_delta in collection_update._data.items():
            try:
                if not isinstance(ref_delta, (DeltaAddition, DeltaDeletion)):
                    logger.warning(f"unexpected type for delta at {collection}[{k}]: {ref_delta}. Ignored")
                    continue
                ref_update: BpyIDRefProxy = ref_delta.value
                if not isinstance(ref_update, BpyIDRefProxy):
                    logger.warning(f"unexpected type for delta_value at {collection}[{k}]: {ref_update}. Ignored")
                    continue

                assert isinstance(ref_update, BpyIDRefProxy)
                if to_blender:
                    # TODO another case for rename trouble ik k remains the name
                    # should be fixed automatically if the key is the uuid at
                    # BpyPropDataCollectionProxy load
                    uuid = ref_update._datablock_uuid
                    datablock = visit_state.ids.get(uuid)
                    if datablock is None:
                        logger.warning(
                            f"delta apply for {parent}[{key}]: unregistered uuid {uuid} for {ref_update._debug_name}"
                        )
                        continue
                    if isinstance(ref_delta, DeltaAddition):
                        collection.link(datablock)
                    else:
                        collection.unlink(datablock)

                if isinstance(ref_delta, DeltaAddition):
                    self._data[k] = ref_update
                else:
                    del self._data[k]
            except Exception as e:
                logger.warning(f"BpyPropDataCollectionProxy.apply(). Processing {ref_delta} to_blender {to_blender}")
                logger.warning(f"... for {collection}[{k}]")
                logger.warning(f"... Exception: {e}")
                logger.warning("... Update ignored")
                continue

        return self

    def diff(
        self, collection: T.bpy_prop_collection, collection_property: T.Property, visit_state: VisitState
    ) -> Optional[ProxyDiff]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        As this proxy tracks a collection, the result will be a DeltaUpdate that contains a BpyPropDataCollectionProxy
        with an Delta item per added, deleted or update item

        Args:
            collection: the collection diff against this proxy
            collection_property: the property of collection in its enclosing object
        """

        # This method is called from the depsgraph handler. The proxy holds a representation of the Blender state
        # before the modification being processed. So the changeset is (Blender state - proxy state)

        # TODO how can this replace BpyBlendDiff ?

        diff = self.__class__()

        item_property = collection_property.fixed_type

        # keys are uuids
        proxy_keys = self._data.keys()
        blender_items = {item.mixer_uuid: item for item in collection.values()}
        blender_keys = blender_items.keys()
        added_keys = blender_keys - proxy_keys
        deleted_keys = proxy_keys - blender_keys
        maybe_updated_keys = proxy_keys & blender_keys

        for k in added_keys:
            value = read_attribute(blender_items[k], item_property, visit_state)
            assert isinstance(value, (BpyIDProxy, BpyIDRefProxy))
            diff._data[k] = DeltaAddition(value)

        for k in deleted_keys:
            diff._data[k] = DeltaDeletion(self._data[k])

        for k in maybe_updated_keys:
            delta = diff_attribute(blender_items[k], item_property, self.data(k), visit_state)
            if delta is not None:
                assert isinstance(delta, DeltaUpdate)
                diff._data[k] = delta

        if len(diff._data):
            return DeltaUpdate(diff)

        return None

    def search(self, name: str) -> [BpyIDProxy]:
        """Convenience method to find proxies by name instead of uuid (for tests only)"""
        results = []
        for uuid in self._data.keys():
            proxy_or_update = self.data(uuid)
            proxy = proxy_or_update if isinstance(proxy_or_update, Proxy) else proxy_or_update.value
            if proxy.data("name") == name:
                results.append(proxy)
        return results

    def search_one(self, name: str) -> BpyIDProxy:
        """Convenience method to find a proxy by name instead of uuid (for tests only)"""
        results = self.search(name)
        return None if not results else results[0]


# to sort delta in the bottom up order in rough reference hierarchy
# TODO useless since unresolved references are handled
_creation_order = {
    # anything before objects (meshes, lights, cameras)
    # Mesh must be received before Object because Object creation requires the Mesh, that cannot be updated afterwards
    "objects": 10,
    "collections": 20,
    "scenes": 30,
}


def _pred_by_creation_order(item: Tuple[str, Any]):
    return _creation_order.get(item[0], 0)


class BpyBlendProxy(Proxy):
    def __init__(self, *args, **kwargs):
        # ID elements stored in bpy.data.* collections, computed before recursive visit starts:
        self.root_ids: RootIds = set()

        self.id_proxies: IDProxies = {}

        # Only needed to cleanup root_ids and id_proxies on ID removal
        self.ids: IDs = {}

        self._data: Mapping[str, BpyPropDataCollectionProxy] = {
            name: BpyPropDataCollectionProxy() for name in BlendData.instance().collection_names()
        }

        # Pending unresolved references.
        self._unresolved_refs: UnresolvedRefs = defaultdict(list)

    def clear(self):
        self._data.clear()
        self.root_ids.clear()
        self.id_proxies.clear()
        self.ids.clear()

    def visit_state(self, context: Context = safe_context):
        return VisitState(self.root_ids, self.id_proxies, self.ids, self._unresolved_refs, context)

    def get_non_empty_collections(self):
        return {key: value for key, value in self._data.items() if len(value) > 0}

    def initialize_ref_targets(self, context: Context):
        """Keep track of all bpy.data items so that loading recognizes references to them

        Call this before updating the proxy from send_scene_content. It is not needed on the
        receiver side.

        TODO check is this is actually required or if we can rely upon is_embedded_data being False
        """
        # Normal operation no more involve BpyBlendProxy.load() ad initial synchronization behaves
        # like a creation. The current load_as_what() implementation relies on root_ids to determine if
        # a T.ID must ne loaded as an IDRef (pointer to bpy.data) or an IDDef (pointer to an "owned" ID).
        # so we need to load all the root_ids before loading anything into the proxy.
        # However, root_ids may no more be required if we can load all the proxies inside out (deepmost first, i.e
        # (Mesh, Metaball, ..), then Object, the Scene). This should be possible as as we sort
        # the updates inside out in update() to the receiver gets them in order
        for name, _ in context.properties(bpy_type=T.BlendData):
            if name in collection_name_to_type:
                # TODO use BlendData
                bl_collection = getattr(bpy.data, name)
                for _id_name, item in bl_collection.items():
                    uuid = ensure_uuid(item)
                    self.root_ids.add(item)
                    self.ids[uuid] = item

    def load(self, context: Context):
        """Load the current scene into this proxy

        Only used for test. The initial load is performed by update()
        """
        self.initialize_ref_targets(context)
        visit_state = self.visit_state(context)

        for name, _ in context.properties(bpy_type=T.BlendData):
            collection = getattr(bpy.data, name)
            with visit_state.debug_context.enter(name, collection):
                self._data[name] = BpyPropDataCollectionProxy().load_as_ID(collection, visit_state)
        return self

    def find(self, collection_name: str, key: str) -> BpyIDProxy:
        # TODO not used ?
        if not self._data:
            return None
        collection_proxy = self._data.get(collection_name)
        if collection_proxy is None:
            return None
        return collection_proxy.find(key)

    def update(
        self, diff: BpyBlendDiff, context: Context = safe_context, depsgraph_updates: T.bpy_prop_collection = ()
    ) -> Changeset:
        """Update the proxy using the state of the Blendata collections (ID creation, deletion)
        and the depsgraph updates (ID modification)

        Sender side

        Returns:
            A list a creations/updates and a list of removals
        """
        changeset: Changeset = Changeset()

        # Update the bpy.data collections status and get the list of newly created bpy.data entries.
        # Updated proxies will contain the IDs to send as an initial transfer.
        # There is no difference between a creation and a subsequent update
        visit_state = self.visit_state(context)

        # sort the updates deppmost first so that the receiver will create meshes and lights
        # before objects, for instance
        deltas = sorted(diff.collection_deltas, key=_pred_by_creation_order)
        for delta_name, delta in deltas:
            collection_changeset = self._data[delta_name].update(delta, visit_state)
            changeset.creations.extend(collection_changeset.creations)
            changeset.removals.extend(collection_changeset.removals)
            changeset.renames.extend(collection_changeset.renames)

        # Update the ID proxies from the depsgraph update
        # this should iterate inside_out (Object.data, Object) in the adequate creation order
        # (creating an Object requires its data)

        # WARNING:
        #   depsgraph_updates[i].id.original IS NOT bpy.lights['Point']
        # or whatever as you might expect, so you cannot use it to index into the map
        # to find the proxy to update.
        # However
        #   - mixer_uuid attributes have the same value
        #   - __hash__() returns the same value

        depsgraph_updated_ids = reversed([update.id.original for update in depsgraph_updates])
        for datablock in depsgraph_updated_ids:
            if not isinstance(datablock, safe_depsgraph_updates):
                logger.info("depsgraph update: ignoring untracked type %s", datablock)
                continue
            if isinstance(datablock, T.Scene) and datablock.name == "_mixer_to_be_removed_":
                continue
            proxy = self.id_proxies.get(datablock.mixer_uuid)
            if proxy is None:
                # Not an error for embedded IDs.
                if not datablock.is_embedded_data:
                    logger.warning(f"depsgraph update for {datablock} : no proxy and not datablock.is_embedded_data")

                # For instance Scene.node_tree is not a reference to a bpy.data collection element
                # but a "pointer" to a NodeTree owned by Scene. In such a case, the update list contains
                # scene.node_tree, then scene. We can ignore the scene.node_tree update since the
                # processing of scene will process scene.node_tree.
                # However, it is not obvious to detect the safe cases and remove the message in such cases
                logger.info("depsgraph update: Ignoring embedded %s", datablock)
                continue
            delta = proxy.diff(datablock, None, visit_state)
            if delta:
                logger.info("depsgraph update: update %s", datablock)
                # TODO add an apply mode to diff instead to avoid two traversals ?
                proxy.apply_to_proxy(datablock, delta, visit_state)
                changeset.updates.append(delta)
            else:
                logger.info("depsgraph update: ignore empty delta %s", datablock)

        return changeset

    def create_datablock(
        self, incoming_proxy: BpyIDProxy, context: Context = safe_context
    ) -> Tuple[Optional[T.ID], Optional[RenameChangeset]]:
        """
        Create bpy.data collection item and update the proxy accordingly

        Receiver side
        """
        bpy_data_collection_proxy = self._data.get(incoming_proxy.collection_name)
        if bpy_data_collection_proxy is None:
            logger.warning(
                f"create_datablock: no bpy_data_collection_proxy with name {incoming_proxy.collection_name} "
            )
            return None

        visit_state = self.visit_state(context)
        return bpy_data_collection_proxy.create_datablock(incoming_proxy, visit_state)

    def update_datablock(self, update: DeltaUpdate, context: Context = safe_context) -> Optional[T.ID]:
        """
        Update a bpy.data collection item and update the proxy accordingly

        Receiver side
        """
        assert isinstance(update, DeltaUpdate)
        incoming_proxy: BpyIDProxy = update.value
        bpy_data_collection_proxy = self._data.get(incoming_proxy.collection_name)
        if bpy_data_collection_proxy is None:
            logger.warning(
                f"update_datablock: no bpy_data_collection_proxy with name {incoming_proxy.collection_name} "
            )
            return None

        visit_state = self.visit_state(context)
        return bpy_data_collection_proxy.update_datablock(update, visit_state)

    def remove_datablock(self, uuid: str):
        """
        Remove a bpy.data collection item and update the proxy accordingly

        Receiver side
        """
        proxy = self.id_proxies.get(uuid)
        if proxy is None:
            logger.error(f"remove_datablock(): no proxy for {uuid} (debug info)")

        bpy_data_collection_proxy = self._data.get(proxy.collection_name)
        if bpy_data_collection_proxy is None:
            logger.warning(f"remove_datablock: no bpy_data_collection_proxy with name {proxy.collection_name} ")
            return None

        datablock = self.ids[uuid]
        bpy_data_collection_proxy.remove_datablock(proxy, datablock)
        self.root_ids.remove(datablock)
        del self.id_proxies[uuid]
        del self.ids[uuid]

    def rename_datablocks(self, items: List[str, str, str]):
        """
        Rename a bpy.data collection item and update the proxy accordingly

        Args:
            items: list of (uuid, new_name) tuples
        """
        renames = []
        for uuid, old_name, new_name in items:
            proxy = self.id_proxies.get(uuid)
            if proxy is None:
                logger.error(f"rename_datablocks(): no proxy for {uuid} (debug info)")
                return

            bpy_data_collection_proxy = self._data.get(proxy.collection_name)
            if bpy_data_collection_proxy is None:
                logger.warning(f"rename_datablock: no bpy_data_collection_proxy with name {proxy.collection_name} ")
                continue

            datablock = self.ids[uuid]
            tmp_name = f"_mixer_tmp_{uuid}"
            if datablock.name != new_name and datablock.name != old_name:
                # local receives a rename, but its datablock name does not match the remote datablock name before
                # the rename. This means that one of these happened:
                # - local has renamed the datablock and remote will receive the rename command later on
                # - local has processed a rename command that remote had not yet processed, but will process later on
                # ensure that everyone renames its datablock with the **same** name
                new_name = new_name = f"_mixer_rename_conflict_{uuid}"
                logger.warning(f"rename_datablocks: conflict for existing {datablock} and incoming old name {old_name}")
                logger.warning(f"... using {new_name}")
            renames.append([bpy_data_collection_proxy, proxy, old_name, tmp_name, new_name, datablock])

        # The rename process is handled in two phases to avoid spontaneous renames from Blender
        # see BpyPropDataCollectionProxy.update() for explanation
        for bpy_data_collection_proxy, proxy, _, tmp_name, _, datablock in renames:
            bpy_data_collection_proxy.rename_datablock(proxy, tmp_name, datablock)

        for bpy_data_collection_proxy, proxy, _, _, new_name, datablock in renames:
            bpy_data_collection_proxy.rename_datablock(proxy, new_name, datablock)

    def debug_check_id_proxies(self):
        return 0
        # try to find stale entries ASAP: access them all
        dummy = 0
        try:
            dummy = sum(len(id_.name) for id_ in self.root_ids)
        except ReferenceError:
            logger.warning("BpyBlendProxy: Stale reference in root_ids")
        try:
            dummy = sum(len(id_.name) for id_ in self.ids.values())
        except ReferenceError:
            logger.warning("BpyBlendProxy: Stale reference in root_ids")

        return dummy

    def diff(self, context: Context) -> Optional[BpyBlendProxy]:
        # Currently for tests only
        diff = self.__class__()
        visit_state = self.visit_state(context)
        for name, proxy in self._data.items():
            collection = getattr(bpy.data, name, None)
            if collection is None:
                logger.warning(f"Unknown, collection bpy.data.{name}")
                continue
            collection_property = bpy.data.bl_rna.properties.get(name)
            delta = proxy.diff(collection, collection_property, visit_state)
            if delta is not None:
                diff._data[name] = diff
        if len(diff._data):
            return diff
        return None


proxy_classes = [
    BpyIDProxy,
    BpyIDRefProxy,
    BpyStructProxy,
    BpyPropertyGroupProxy,
    BpyPropStructCollectionProxy,
    BpyPropDataCollectionProxy,
    SoaElement,
    AosElement,
]


def write_attribute(bl_instance, key: Union[str, int], value: Any, visit_state: VisitState):
    """
    Write a value into a Blender property
    """
    # Like in apply_attribute parent and key are needed to specify a L-value
    if bl_instance is None:
        logger.warning("unexpected write None attribute")
        return

    try:
        if isinstance(value, Proxy):
            value.save(bl_instance, key, visit_state)
        else:
            assert type(key) is str

            prop = bl_instance.bl_rna.properties.get(key)
            if prop is None:
                # Don't log this, too many messages
                # f"Attempt to write to non-existent attribute {bl_instance}.{key} : skipped"
                return

            if not prop.is_readonly:
                try:
                    setattr(bl_instance, key, value)
                except TypeError as e:
                    # common for enum that have unsupported default values, such as FFmpegSettings.ffmpeg_preset,
                    # which seems initialized at "" and triggers :
                    #   TypeError('bpy_struct: item.attr = val: enum "" not found in (\'BEST\', \'GOOD\', \'REALTIME\')')
                    logger.info(f"write attribute skipped {bl_instance}.{key}...")
                    logger.info(f" ...Exception: {repr(e)}")

    except TypeError:
        # common for enum that have unsupported default values, such as FFmpegSettings.ffmpeg_preset,
        # which seems initialized at "" and triggers :
        #   TypeError('bpy_struct: item.attr = val: enum "" not found in (\'BEST\', \'GOOD\', \'REALTIME\')')
        logger.warning(f"write attribute skipped {bl_instance}.{key}...")
        for line in traceback.format_exc().splitlines():
            logger.warning(f" ... {line}")
    except AttributeError as e:
        if isinstance(bl_instance, bpy.types.Collection) and bl_instance.name == "Master Collection" and key == "name":
            pass
        else:
            logger.warning(f"write attribute skipped {bl_instance}.{key}...")
            logger.warning(f" ...Exception: {repr(e)}")

    except Exception:
        logger.warning(f"write attribute skipped {bl_instance}.{key}...")
        for line in traceback.format_exc().splitlines():
            logger.warning(f" ... {line}")


def apply_attribute(parent, key: Union[str, int], proxy_value, delta: Delta, visit_state: VisitState, to_blender=True):
    """
    Applies a delta to the Blender attribute identified by bl_instance.key or bl_instance[key]

    Args:
        parent:
        key:
        proxy_value:
        delta:

    Returns: a value to store into the updated proxy
    """

    # Like in write_attribute parent and key are needed to specify a L-value
    assert type(delta) == DeltaUpdate

    value = delta.value
    assert proxy_value is None or type(proxy_value) == type(value)

    try:
        if isinstance(proxy_value, Proxy):
            return proxy_value.apply(parent, key, delta, visit_state, to_blender)

        if to_blender:
            try:
                # try is less costly than fetching the property to find if the attribute is readonly
                setattr(parent, key, value)
            except Exception:
                pass
        return value

    except Exception as e:
        logger.warning(f"diff exception for attr: {e}")
        raise


def diff_attribute(item: Any, item_property: T.Property, value: Any, visit_state: VisitState) -> Optional[Delta]:
    """
    Computes a difference between a blender item and a proxy value

    Args:
        item: the blender item
        item_property: the property of item as found in its enclosing object
        value: a proxy value

    """
    try:
        if isinstance(value, Proxy):
            return value.diff(item, item_property, visit_state)

        # An attribute mappable on a python builtin type
        # TODO overkill to call read_attribute because it is not a proxy type
        blender_value = read_attribute(item, item_property, visit_state)
        if blender_value != value:
            # TODO This is too coarse (whole lists)
            return DeltaUpdate(blender_value)

    except Exception as e:
        logger.warning(f"diff exception for attr: {e}")
        raise

    return None
