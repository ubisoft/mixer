"""Type specific helpers for Proxy load and save
"""
import logging
from pathlib import Path
import traceback
from typing import ItemsView, List, TypeVar, Union

import bpy
import bpy.types as T  # noqa N812
import bpy.path

from mixer.blender_data.blenddata import BlendData

logger = logging.getLogger(__name__)
Proxy = TypeVar("Proxy")
BpyIDProxy = TypeVar("BpyIDProxy")


def bpy_data_ctor(collection_name: str, proxy: BpyIDProxy) -> Union[T.ID, None]:
    collection = getattr(bpy.data, collection_name)
    BlendData.instance().collection(collection_name).set_dirty
    if collection_name == "images":
        is_packed = proxy.data("packed_file") is not None
        image = None
        if is_packed:
            name = proxy.data("name")
            size = proxy.data("size")
            width = size.data(0)
            height = size.data(1)
            image = collection.new(name, width, height)
            # remaning attributes will be saved from the received proxy attributes
        else:
            path = proxy.data("filepath")
            if path != "":
                image = collection.load(path)
                # we may have received an ID named xxx.001 although filepath is xxx, so fix it now
                image.name = proxy.data("name")
        return image

    if collection_name == "objects":
        name = proxy.data("name")
        target_proxy = proxy.data("data")
        if target_proxy is not None:
            target = target_proxy.target()
        else:
            target = None
        object_ = collection.new(name, target)
        return object_

    if collection_name == "lights":
        name = proxy.data("name")
        light_type = proxy.data("type")
        light = collection.new(name, light_type)
        return light

    if collection_name == "sounds":
        filepath = proxy.data("filepath")
        # TODO what about "check_existing" ?
        id_ = collection.load(filepath)
        # we may have received an ID named xxx.001 although filepath is xxx, so fix it now
        id_.name = proxy.data("name")

        return id_

    name = proxy.data("name")
    try:
        id_ = collection.new(name)
    except TypeError as e:
        logger.error(f"Exception while calling : bpy.data.{collection_name}.new({name})")
        logger.error(f"TypeError : {e}")
        return None

    return id_


filter_crop_transform = [
    T.EffectSequence,
    T.ImageSequence,
    T.MaskSequence,
    T.MetaSequence,
    T.MovieClipSequence,
    T.MovieSequence,
    T.SceneSequence,
]


def conditional_properties(bpy_struct: T.Struct, properties: ItemsView) -> ItemsView:
    """Filter properties list according to a specific property value in the same ID

    This prevents loading values that cannot always be saved, such as Object.instance_collection
    that can only be saved when Object.data is None

    Args:
        properties: the properties list to filter
    Returns:

    """
    if isinstance(bpy_struct, T.ColorManagedViewSettings):
        if bpy_struct.use_curve_mapping:
            # Empty
            return properties
        filtered = {}
        filter_props = ["curve_mapping"]
        filtered = {k: v for k, v in properties if k not in filter_props}
        return filtered.items()

    if isinstance(bpy_struct, T.Object):
        if not bpy_struct.data:
            # Empty
            return properties
        filtered = {}
        filter_props = ["instance_collection"]
        filtered = {k: v for k, v in properties if k not in filter_props}
        return filtered.items()

    if isinstance(bpy_struct, T.MetaBall):
        if not bpy_struct.use_auto_texspace:
            return properties
        filter_props = ["texspace_location", "texspace_size"]
        filtered = {k: v for k, v in properties if k not in filter_props}
        return filtered.items()

    if isinstance(bpy_struct, T.Node):
        if bpy_struct.hide:
            return properties

        # not hidden: saving width_hidden is ignored
        filter_props = ["width_hidden"]
        filtered = {k: v for k, v in properties if k not in filter_props}
        return filtered.items()

    filter_props = []
    if any(isinstance(bpy_struct, t) for t in filter_crop_transform):
        if not bpy_struct.use_crop:
            filter_props.append("crop")
        if not bpy_struct.use_translation:
            filter_props.append("transform")

    if not filter_props:
        return properties
    filtered = {k: v for k, v in properties if k not in filter_props}
    return filtered.items()

    return properties


def pre_save_id(proxy: Proxy, collection: T.bpy_prop_collection, key: str) -> T.Struct:
    """Process attributes that must be saved first and return a possibily updated reference to the target

    Args:
        bpy_struct: The collection that contgains the ID
        attr_name: Its key

    Returns:
        [bpy.types.ID]: a possibly new ID
    """
    target = proxy.target(collection, key)
    if isinstance(target, T.Scene):
        # Set 'use_node' to True first is the only way I know to be able to set the 'node_tree' attribute
        use_nodes = proxy.data("use_nodes")
        if use_nodes:
            target.use_nodes = True
        sequence_editor = proxy.data("sequence_editor")
        if sequence_editor is not None and target.sequence_editor is None:
            target.sequence_editor_create()
    elif isinstance(target, T.Light):
        # required first to have access to new light type attributes
        light_type = proxy.data("type")
        if light_type is not None and light_type != target.type:
            target.type = light_type
            # must reload the reference
            target = proxy.target(collection, key)
    elif isinstance(target, T.ColorManagedViewSettings):
        use_curve_mapping = proxy.data("use_curve_mapping")
        if use_curve_mapping:
            target.use_curve_mapping = True
    elif isinstance(target, bpy.types.World):
        use_nodes = proxy.data("use_nodes")
        if use_nodes:
            target.use_nodes = True
    return target


def pre_save_struct(proxy: Proxy, bpy_struct: T.Struct, attr_name: str):
    """Process attributes that must be saved first
    """
    target = getattr(bpy_struct, attr_name, None)
    if target is None:
        return None
    if isinstance(target, T.ColorManagedViewSettings):
        use_curve_mapping = proxy.data("use_curve_mapping")
        if use_curve_mapping:
            target.use_curve_mapping = True


def post_save_id(proxy: Proxy, bpy_id: T.ID):
    """Apply type specific patches after loading bpy_struct into proxy
    """
    if isinstance(bpy_id, T.Image):
        # So far, the receiver has no valid "current file", so he cannot load relative files
        for attr_name in ("filepath", "filepath_raw"):
            path = proxy._data[attr_name]
            if path:
                proxy._data[attr_name] = bpy.path.abspath(path)

    if isinstance(bpy_id, T.Sound):
        # So far, the receiver has no valid "current file", so he cannot load relative files
        attr_name = "filepath"
        path = proxy._data[attr_name]
        if path:
            proxy._data[attr_name] = bpy.path.abspath(path)


non_effect_sequences = {"IMAGE", "SOUND", "META", "SCENE", "MOVIE", "MOVIECLIP", "MASK"}
effect_sequences = set(T.EffectSequence.bl_rna.properties["type"].enum_items.keys()) - non_effect_sequences


def add_element(proxy: Proxy, collection: T.bpy_prop_collection, key: str):
    """Add an element to a bpy_prop_collection using the collection specific API
    """

    bl_rna = getattr(collection, "bl_rna", None)
    if bl_rna is not None:
        if isinstance(bl_rna, type(T.KeyingSets.bl_rna)):
            idname = proxy.data("bl_idname")
            return collection.new(name=key, idname=idname)

        if isinstance(bl_rna, type(T.KeyingSetPaths.bl_rna)):
            # TODO current implementation fails
            # All keying sets paths have an empty name, and insertion with add()à failes
            # with an empty name
            target_ref = proxy.data("id")
            if target_ref is None:
                target = None
            else:
                target = target_ref.target()
            data_path = proxy.data("data_path")
            index = proxy.data("array_index")
            group_method = proxy.data("group_method")
            group_name = proxy.data("group")
            return collection.add(
                target_id=target, data_path=data_path, index=index, group_method=group_method, group_name=group_name
            )

        if isinstance(bl_rna, type(T.Nodes.bl_rna)):
            node_type = proxy.data("bl_idname")
            return collection.new(node_type)

        if isinstance(bl_rna, type(T.Sequences.bl_rna)):
            type_ = proxy.data("type")
            name = proxy.data("name")
            channel = proxy.data("channel")
            frame_start = proxy.data("frame_start")
            if type_ in effect_sequences:
                # overwritten anyway
                frame_end = frame_start + 1
                return collection.new_effect(name, type_, channel, frame_start, frame_end=frame_end)
            if type_ == "SOUND":
                sound = proxy.data("sound")
                target = sound.target()
                if not target:
                    logger.warning(f"missing target ID block for bpy.data.{sound.collection}[{sound.key}] ")
                    return None
                filepath = target.filepath
                return collection.new_sound(name, filepath, channel, frame_start)
            if type_ == "MOVIE":
                filepath = proxy.data("filepath")
                return collection.new_movie(name, filepath, channel, frame_start)
            if type_ == "IMAGE":
                directory = proxy.data("directory")
                filename = proxy.data("elements").data(0).data("filename")
                filepath = str(Path(directory) / filename)
                return collection.new_image(name, filepath, channel, frame_start)

            logger.warning(f"Sequence type not implemented: {type_}")
            # SCENE may be harder than it seems, since we cannot order scene creations.
            # Currently the creation order is the "deepmost" order as listed in proxy.py:_creation_order
            # but it does not work for this case
            return None

        if isinstance(bl_rna, type(T.SequenceModifiers.bl_rna)):
            name = proxy.data("name")
            type_ = proxy.data("type")
            return collection.new(name, type_)

    try:
        return collection.add()
    except Exception:
        pass

    # try our best
    new_or_add = getattr(collection, "new", None)
    if new_or_add is None:
        new_or_add = getattr(collection, "add", None)
    if new_or_add is None:
        logger.warning(f"Not implemented new or add for bpy.data.{collection}[{key}] ...")
        return None
    try:
        return new_or_add(key)
    except Exception:
        logger.warning(f"Not implemented new or add for type {type(collection)} for {collection}[{key}] ...")
        for s in traceback.format_exc().splitlines():
            logger.warning(f"...{s}")
        return None


# order dependent, so always clear
always_clear = [type(T.ObjectModifiers.bl_rna), type(T.SequenceModifiers.bl_rna)]


def truncate_collection(target: T.bpy_prop_collection, incoming_keys: List[str]):
    if not hasattr(target, "bl_rna"):
        return

    target_rna = target.bl_rna
    if any(isinstance(target_rna, t) for t in always_clear):
        target.clear()
        return

    incoming_keys = set(incoming_keys)
    existing_keys = set(target.keys())
    truncate_keys = existing_keys - incoming_keys
    if not truncate_keys:
        return
    if isinstance(target_rna, type(T.KeyingSets.bl_rna)):
        for k in truncate_keys:
            target.active_index = target.find(k)
            bpy.ops.anim.keying_set_remove()
    else:
        try:
            for k in truncate_keys:
                target.remove(target[k])
        except Exception:
            logger.warning(f"Not implemented truncate_collection for type {target.bl_rna} for {target} ...")
            for s in traceback.format_exc().splitlines():
                logger.warning(f"...{s}")
