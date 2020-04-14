import logging
import os
import socket
import subprocess
import time
from pathlib import Path
from typing import Mapping, Any
from uuid import uuid4

import bpy
from bpy.app.handlers import persistent

from .share_data import share_data, object_visibility
from .blender_client import scene as scene_lib
from .blender_client import collection as collection_lib
from .blender_client import object_ as object_lib

from . import clientBlender
from . import ui
from .data import get_dcc_sync_props
from .stats import StatsTimer, save_statistics, get_stats_filename, stats_timer

logger = logging.getLogger(__name__)


class TransformStruct:
    def __init__(self, translate, quaternion, scale, visible):
        self.translate = translate
        self.quaternion = quaternion
        self.scale = scale
        self.visible = visible


def update_params(obj):
    # send collection instances
    if obj.instance_type == "COLLECTION":
        collection_lib.send_collection_instance(share_data.client, obj)
        return

    if not hasattr(obj, "data"):
        return

    typename = obj.bl_rna.name
    if obj.data:
        typename = obj.data.bl_rna.name

    if (
        typename != "Camera"
        and typename != "Mesh"
        and typename != "Curve"
        and typename != "Text Curve"
        and typename != "Sun Light"
        and typename != "Point Light"
        and typename != "Spot Light"
        and typename != "Grease Pencil"
    ):
        return

    if typename == "Camera":
        share_data.client.send_camera(obj)

    if typename == "Sun Light" or typename == "Point Light" or typename == "Spot Light":
        share_data.client.send_light(obj)

    if typename == "Grease Pencil":
        for material in obj.data.materials:
            share_data.client.send_material(material)
        share_data.client.send_grease_pencil_mesh(obj)
        share_data.client.send_grease_pencil_connection(obj)

    if typename == "Mesh" or typename == "Curve" or typename == "Text Curve":
        if obj.mode == "OBJECT":
            share_data.client.send_mesh(obj)


def update_transform(obj):
    share_data.client.send_transform(obj)


def join_room(room_name: str):
    logger.info("join_room")

    assert share_data.current_room is None
    user = get_dcc_sync_props().user
    share_data.session_id += 1
    share_data.current_room = room_name
    share_data.client.join_room(room_name)
    share_data.client.set_client_name(user)
    share_data.client.send_set_current_scene(bpy.context.scene.name_full)

    share_data.current_statistics = {
        "session_id": share_data.session_id,
        "blendfile": bpy.data.filepath,
        "statsfile": get_stats_filename(share_data.runId, share_data.session_id),
        "user": user,
        "room": room_name,
        "children": {},
    }
    share_data.auto_save_statistics = get_dcc_sync_props().auto_save_statistics
    share_data.statistics_directory = get_dcc_sync_props().statistics_directory
    # join a room <==> want to track local changes
    set_handlers(True)


def leave_current_room():
    logger.info("leave_current_room")

    if share_data.current_room:
        share_data.leave_current_room()
        set_handlers(False)

    share_data.clear_before_state()

    if share_data.current_statistics is not None and share_data.auto_save_statistics:
        save_statistics(share_data.current_statistics, share_data.statistics_directory)
    share_data.current_statistics = None
    share_data.auto_save_statistics = False
    share_data.statistics_directory = None


def is_joined():
    connected = share_data.client is not None and share_data.client.is_connected()
    return connected and share_data.current_room


@persistent
def on_load(scene):
    logger.info("on_load")

    disconnect()


def get_scene(scene_name):
    return share_data.blender_scenes.get(scene_name)


def get_collection(collection_name):
    """
    May only return a non master collection
    """
    return share_data.blender_collections.get(collection_name)


def get_parent_collections(collection_name):
    """
    May return a master or non master collection
    """
    parents = []
    for col in share_data.blender_collections.values():
        children_names = {x.name_full for x in col.children}
        if collection_name in children_names:
            parents.append(col)
    return parents


def find_renamed(new_items: Mapping[Any, Any], old_items: Mapping[Any, Any]):
    """

    """
    new_uuids = {uuid for uuid in new_items.keys()}
    old_uuids = {uuid for uuid in old_items.keys()}
    renamed_uuids = {uuid for uuid in new_uuids & old_uuids if old_items[uuid] != new_items[uuid]}
    added_items = [new_items[uuid] for uuid in new_uuids - old_uuids - renamed_uuids]
    removed_items = [old_items[uuid] for uuid in old_uuids - new_uuids - renamed_uuids]
    renamed_items = [(old_items[uuid], new_items[uuid]) for uuid in renamed_uuids]
    return added_items, removed_items, renamed_items


def update_scenes_state():
    """
    Must be called before update_collections_state so that non empty collections added to master
    collection are processed
    """

    for scene in share_data.blender_scenes.values():
        if not scene.uuid:
            scene.uuid = str(uuid4())

    new_scenes = {scene.uuid: name for name, scene in share_data.blender_scenes.items()}
    old_scenes = {scene.uuid: name for name, scene in share_data.scenes_info.items()}
    share_data.scenes_added, share_data.scenes_removed, share_data.scenes_renamed = find_renamed(new_scenes, old_scenes)

    for old_name, new_name in share_data.scenes_renamed:
        share_data.scenes_info[new_name] = share_data.scenes_info[old_name]
        del share_data.scenes_info[old_name]

    # walk the old scenes
    for scene_name, scene_info in share_data.scenes_info.items():
        scene = get_scene(scene_name)
        if not scene:
            continue
        scene_name = scene.name_full
        old_children = set(scene_info.children)
        new_children = {x.name_full for x in scene.collection.children}

        for x in new_children - old_children:
            share_data.collections_added_to_scene.add((scene_name, x))

        for x in old_children - new_children:
            share_data.collections_removed_from_scene.add((scene_name, x))

        old_objects = {share_data.objects_renamed.get(x, x) for x in scene_info.objects}
        new_objects = {x.name_full for x in scene.collection.objects}

        added_objects = list(new_objects - old_objects)
        if len(added_objects) > 0:
            share_data.objects_added_to_scene[scene_name] = added_objects

        removed_objects = list(old_objects - new_objects)
        if len(removed_objects) > 0:
            share_data.objects_removed_from_scene[scene_name] = removed_objects

    # now the new scenes (in case of rename)
    for scene_name in share_data.scenes_added:
        scene = get_scene(scene_name)
        if not scene:
            continue
        new_children = {x.name_full for x in scene.collection.children}
        for x in new_children:
            share_data.collections_added_to_scene.add((scene_name, x))

        added_objects = {x.name_full for x in scene.collection.objects}
        if len(added_objects) > 0:
            share_data.objects_added_to_scene[scene_name] = added_objects


def update_collections_state():
    """
    Update non master collection state
    """
    new_collections_names = share_data.blender_collections.keys()
    old_collections_names = share_data.collections_info.keys()

    share_data.collections_added |= new_collections_names - old_collections_names
    share_data.collections_removed |= old_collections_names - new_collections_names

    # walk the old collections
    for collection_name, collection_info in share_data.collections_info.items():
        collection = get_collection(collection_name)
        if not collection:
            continue
        old_children = set(collection_info.children)
        new_children = {x.name_full for x in collection.children}

        for x in new_children - old_children:
            share_data.collections_added_to_collection.add((collection.name_full, x))

        for x in old_children - new_children:
            share_data.collections_removed_from_collection.add((collection_name, x))

        new_objects = {x.name_full for x in collection.objects}
        old_objects = {share_data.objects_renamed.get(x, x) for x in collection_info.objects}

        added_objects = [x for x in new_objects - old_objects]
        if len(added_objects) > 0:
            share_data.objects_added_to_collection[collection_name] = added_objects

        removed_objects = [x for x in old_objects - new_objects]
        if len(removed_objects) > 0:
            share_data.objects_removed_from_collection[collection_name] = removed_objects

    # now the new collections (in case of rename)
    for collection_name in share_data.collections_added:
        collection = get_collection(collection_name)
        if not collection:
            continue
        new_children = {x.name_full for x in collection.children}
        for x in new_children:
            share_data.collections_added_to_collection.add((collection.name_full, x))

        added_objects = {x.name_full for x in collection.objects}
        if len(added_objects) > 0:
            share_data.objects_added_to_collection[collection_name] = added_objects


def update_frame_changed_related_objects_state(old_objects: dict, new_objects: dict):
    for obj_name, matrix in share_data.objects_transforms.items():
        new_obj = share_data.old_objects.get(obj_name)
        if not new_obj:
            continue
        if new_obj.matrix_local != matrix:
            share_data.objects_transformed.add(obj_name)


@stats_timer(share_data)
def update_object_state(old_objects: dict, new_objects: dict):
    stats_timer = share_data.current_stats_timer

    with stats_timer.child("checkobjects_addedAndRemoved"):
        objects = set(new_objects.keys())
        share_data.objects_added = objects - old_objects.keys()
        share_data.objects_removed = old_objects.keys() - objects

    share_data.old_objects = new_objects

    if len(share_data.objects_added) == 1 and len(share_data.objects_removed) == 1:
        share_data.objects_renamed[list(share_data.objects_removed)[0]] = list(share_data.objects_added)[0]
        share_data.objects_added.clear()
        share_data.objects_removed.clear()
        return

    for obj_name in share_data.objects_removed:
        if obj_name in share_data.old_objects:
            del share_data.old_objects[obj_name]

    with stats_timer.child("updateObjectsParentingChanged"):
        for obj_name, parent in share_data.objects_parents.items():
            if obj_name not in share_data.old_objects:
                continue
            new_obj = share_data.old_objects[obj_name]
            new_obj_parent = "" if new_obj.parent is None else new_obj.parent.name_full
            if new_obj_parent != parent:
                share_data.objects_reparented.add(obj_name)

    with stats_timer.child("update_objects_visibilityChanged"):
        for obj_name, visibility in share_data.objects_visibility.items():
            new_obj = share_data.old_objects.get(obj_name)
            if not new_obj:
                continue
            if visibility != object_visibility(new_obj):
                share_data.objects_visibility_changed.add(obj_name)

    update_frame_changed_related_objects_state(old_objects, new_objects)


def is_in_object_mode():
    return not hasattr(bpy.context, "active_object") or (
        not bpy.context.active_object or bpy.context.active_object.mode == "OBJECT"
    )


def remove_objects_from_scenes():
    changed = False
    for scene_name, object_names in share_data.objects_removed_from_scene.items():
        for object_name in object_names:
            scene_lib.send_remove_object_from_scene(share_data.client, scene_name, object_name)
            changed = True
    return changed


def remove_objects_from_collections():
    """
    Non master collections, actually
    """
    changed = False
    for collection_name, object_names in share_data.objects_removed_from_collection.items():
        for object_name in object_names:
            collection_lib.send_remove_object_from_collection(share_data.client, collection_name, object_name)
            changed = True
    return changed


def remove_collections_from_scenes():
    changed = False
    for scene_name, collection_name in share_data.collections_removed_from_scene:
        scene_lib.send_remove_collection_from_scene(share_data.client, scene_name, collection_name)
        changed = True
    return changed


def remove_collections_from_collections():
    """
    Non master collections, actually
    """
    changed = False
    for parent_name, child_name in share_data.collections_removed_from_collection:
        collection_lib.send_remove_collection_from_collection(share_data.client, parent_name, child_name)
        changed = True
    return changed


def add_scenes():
    changed = False
    for scene in share_data.scenes_added:
        scene_lib.send_scene(share_data.client, scene)
        changed = True
    for old_name, new_name in share_data.scenes_renamed:
        scene_lib.send_scene_renamed(share_data.client, old_name, new_name)
        changed = True
    return changed


def remove_scenes():
    changed = False
    for scene in share_data.scenes_removed:
        scene_lib.send_scene_removed(share_data.client, scene)
        changed = True
    return changed


def remove_collections():
    changed = False
    for collection in share_data.collections_removed:
        collection_lib.send_collection_removed(share_data.client, collection)
        changed = True
    return changed


def add_objects():
    changed = False
    for obj_name in share_data.objects_added:
        obj = share_data.blender_objects.get(obj_name)
        if obj:
            update_params(obj)
            update_transform(obj)
            changed = True
    return changed


def add_collections():
    changed = False
    for item in share_data.collections_added:
        collection_lib.send_collection(share_data.client, get_collection(item))
        changed = True
    return changed


def add_collections_to_collections():
    changed = False
    for parent_name, child_name in share_data.collections_added_to_collection:
        collection_lib.send_add_collection_to_collection(share_data.client, parent_name, child_name)
        changed = True
    return changed


def add_collections_to_scenes():
    changed = False
    for scene_name, collection_name in share_data.collections_added_to_scene:
        scene_lib.send_add_collection_to_scene(share_data.client, scene_name, collection_name)
        changed = True
    return changed


def add_objects_to_collections():
    changed = False
    for collection_name, object_names in share_data.objects_added_to_collection.items():
        for object_name in object_names:
            collection_lib.send_add_object_to_collection(share_data.client, collection_name, object_name)
            changed = True
    return changed


def add_objects_to_scenes():
    changed = False
    for scene_name, object_names in share_data.objects_added_to_scene.items():
        for object_name in object_names:
            scene_lib.send_add_object_to_scene(share_data.client, scene_name, object_name)
            changed = True
    return changed


def update_collections_parameters():
    changed = False
    for collection in share_data.blender_collections.values():
        info = share_data.collections_info.get(collection.name_full)
        if info:
            if info.hide_viewport != collection.hide_viewport or info.instance_offset != collection.instance_offset:
                collection_lib.send_collection(share_data.client, collection)
                changed = True
    return changed


def delete_scene_objects():
    changed = False
    for obj_name in share_data.objects_removed:
        share_data.client.send_deleted_object(obj_name)
        changed = True
    return changed


def rename_objects():
    changed = False
    for old_name, new_name in share_data.objects_renamed.items():
        share_data.client.send_renamed_objects(old_name, new_name)
        changed = True
    return changed


def update_objects_visibility():
    changed = False
    for obj_name in share_data.objects_visibility_changed:
        if obj_name in share_data.blender_objects:
            obj = share_data.blender_objects[obj_name]
            update_transform(obj)
            object_lib.send_object_visibility(share_data.client, obj)
            changed = True
    return changed


def update_objects_transforms():
    changed = False
    for obj_name in share_data.objects_transformed:
        if obj_name in share_data.blender_objects:
            update_transform(share_data.blender_objects[obj_name])
            changed = True
    return changed


def reparent_objects():
    changed = False
    for obj_name in share_data.objects_reparented:
        obj = share_data.blender_objects.get(obj_name)
        if obj:
            update_transform(obj)
            changed = True
    return changed


def create_vrtist_objects():
    """
    VRtist will filter the received messages and handle only the objects that belong to the
    same scene as the one initially synchronized
    """
    changed = False
    for obj_name in share_data.objects_added:
        if obj_name in bpy.context.scene.objects:
            obj = bpy.context.scene.objects[obj_name]
            scene_lib.send_add_object_to_vrtist(share_data.client, bpy.context.scene.name_full, obj.name_full)
            changed = True
    return changed


def update_objects_data():
    if len(share_data.depsgraph.updates) == 0:
        return  # Exit here to avoid noise if you want to put breakpoints in this function

    data_container = {}
    data = set()
    transforms = set()

    for update in share_data.depsgraph.updates:
        obj = update.id.original
        typename = obj.bl_rna.name

        if typename == "Object":
            if hasattr(obj, "data"):
                if obj.data in data_container:
                    data_container[obj.data].append(obj)
                else:
                    data_container[obj.data] = [obj]
            transforms.add(obj)

        if (
            typename == "Camera"
            or typename == "Mesh"
            or typename == "Curve"
            or typename == "Text Curve"
            or typename == "Sun Light"
            or typename == "Point Light"
            or typename == "Spot Light"
            or typename == "Grease Pencil"
        ):
            data.add(obj)

        if typename == "Material":
            share_data.client.send_material(obj)

    # Send transforms
    for obj in transforms:
        update_transform(obj)

    # Send data (mesh) of objects
    for d in data:
        container = data_container.get(d)
        if not container:
            continue
        for c in container:
            update_params(c)


@persistent
def send_frame_changed(scene):
    logger.info("send_frame_changed")

    if not share_data.client:
        logger.info("send_frame_changed cancelled (no client instance)")
        return

    # We can arrive here because of scene deletion (bpy.ops.scene.delete({'scene': to_remove}) that append during build_scene)
    # so we need to prevent processing self events
    if share_data.client.receivedCommandsProcessed:
        if not share_data.client.blockSignals:
            share_data.client.receivedCommandsProcessed = False
        logger.info("send_frame_changed canceled (receivedCommandsProcessed = True)")
        return

    if not is_in_object_mode():
        logger.info("send_frame_changed canceled (not is_in_object_mode)")
        return

    with StatsTimer(share_data, "send_frame_changed") as timer:
        with timer.child("setFrame"):
            share_data.client.send_frame(scene.frame_current)

        with timer.child("clear_lists"):
            share_data.clear_changed_frame_related_lists()

        with timer.child("update_frame_changed_related_objects_state"):
            update_frame_changed_related_objects_state(share_data.old_objects, share_data.blender_objects)

        with timer.child("checkForChangeAndSendUpdates"):
            update_objects_transforms()

        # update for next change
        with timer.child("update_objects_info"):
            share_data.update_objects_info()


@stats_timer(share_data)
@persistent
def send_scene_data_to_server(scene, dummy):
    logger.info("send_scene_data_to_server")

    timer = share_data.current_stats_timer

    if not share_data.client:
        logger.info("send_scene_data_to_server canceled (no client instance)")
        return

    share_data.set_dirty()
    with timer.child("clear_lists"):
        share_data.clear_lists()

    # prevent processing self events
    if share_data.client.receivedCommandsProcessed:
        if not share_data.client.blockSignals:
            share_data.client.receivedCommandsProcessed = False
        logger.info("send_scene_data_to_server canceled (receivedCommandsProcessed = True)")
        return

    if not is_in_object_mode():
        logger.info("send_scene_data_to_server canceled (not is_in_object_mode)")
        return

    update_object_state(share_data.old_objects, share_data.blender_objects)

    with timer.child("update_scenes_state"):
        update_scenes_state()

    with timer.child("update_collections_state"):
        update_collections_state()

    changed = False
    with timer.child("checkForChangeAndSendUpdates"):
        changed |= remove_objects_from_collections()
        changed |= remove_objects_from_scenes()
        changed |= remove_collections_from_collections()
        changed |= remove_collections_from_scenes()
        changed |= remove_collections()
        changed |= remove_scenes()
        changed |= add_scenes()
        changed |= add_collections()
        changed |= add_objects()
        changed |= add_collections_to_scenes()
        changed |= add_collections_to_collections()
        changed |= add_objects_to_collections()
        changed |= add_objects_to_scenes()
        changed |= update_collections_parameters()
        changed |= create_vrtist_objects()
        changed |= delete_scene_objects()
        changed |= rename_objects()
        changed |= update_objects_visibility()
        changed |= update_objects_transforms()
        changed |= reparent_objects()

    if not changed:
        with timer.child("update_objects_data"):
            share_data.depsgraph = bpy.context.evaluated_depsgraph_get()
            update_objects_data()

    # update for next change
    with timer.child("update_current_data"):
        share_data.update_current_data()


@persistent
def on_undo_redo_pre(scene):
    logger.info("on_undo_redo_pre")
    send_scene_data_to_server(scene, None)


def remap_objects_info():
    # update objects references
    added_objects = set(share_data.blender_objects.keys()) - set(share_data.old_objects.keys())
    removed_objects = set(share_data.old_objects.keys()) - set(share_data.blender_objects.keys())
    # we are only able to manage one object rename
    if len(added_objects) == 1 and len(removed_objects) == 1:
        old_name = list(removed_objects)[0]
        new_name = list(added_objects)[0]

        visible = share_data.objects_visibility[old_name]
        del share_data.objects_visibility[old_name]
        share_data.objects_visibility[new_name] = visible

        parent = share_data.objects_parents[old_name]
        del share_data.objects_parents[old_name]
        share_data.objects_parents[new_name] = parent
        for name, parent in share_data.objects_parents.items():
            if parent == old_name:
                share_data.objects_parents[name] = new_name

        matrix = share_data.objects_transforms[old_name]
        del share_data.objects_transforms[old_name]
        share_data.objects_transforms[new_name] = matrix

    share_data.old_objects = share_data.blender_objects


@stats_timer(share_data)
@persistent
def on_undo_redo_post(scene, dummy):
    logger.info("on_undo_redo_post")

    share_data.set_dirty()
    share_data.clear_lists()
    # apply only in object mode
    if not is_in_object_mode():
        return

    old_objects_name = dict([(k, None) for k in share_data.old_objects.keys()])  # value not needed
    remap_objects_info()
    for k, v in share_data.old_objects.items():
        if k in old_objects_name:
            old_objects_name[k] = v

    update_object_state(old_objects_name, share_data.old_objects)

    update_collections_state()
    update_scenes_state()

    remove_objects_from_scenes()
    remove_objects_from_collections()
    remove_collections_from_scenes()
    remove_collections_from_collections()

    remove_collections()
    remove_scenes()
    add_scenes()
    add_objects()
    add_collections()

    add_collections_to_scenes()
    add_collections_to_collections()

    add_objects_to_collections()
    add_objects_to_scenes()

    update_collections_parameters()
    create_vrtist_objects()
    delete_scene_objects()
    rename_objects()
    update_objects_visibility()
    update_objects_transforms()
    reparent_objects()

    # send selection content (including data)
    materials = set()
    for obj in bpy.context.selected_objects:
        update_transform(obj)
        if hasattr(obj, "data"):
            update_params(obj)
        if hasattr(obj, "material_slots"):
            for slot in obj.material_slots[:]:
                materials.add(slot.material)

    for material in materials:
        share_data.client.send_material(material)

    share_data.depsgraph = bpy.context.evaluated_depsgraph_get()

    share_data.update_current_data()


def update_list_users(client_ids: Mapping[str, str] = None):
    share_data.client_ids = client_ids


def clear_scene_content():
    set_handlers(False)

    for obj in bpy.data.objects:
        bpy.data.objects.remove(obj)

    for obj in bpy.data.cameras:
        bpy.data.cameras.remove(obj)

    for obj in bpy.data.lights:
        bpy.data.lights.remove(obj)

    for block in bpy.data.meshes:
        bpy.data.meshes.remove(block)

    for block in bpy.data.curves:
        bpy.data.curves.remove(block)

    for block in bpy.data.grease_pencils:
        bpy.data.grease_pencils.remove(block)

    for block in bpy.data.materials:
        bpy.data.materials.remove(block)

    for block in bpy.data.textures:
        bpy.data.textures.remove(block)

    for block in bpy.data.images:
        bpy.data.images.remove(block)

    for collection in bpy.data.collections:
        bpy.data.collections.remove(collection)

    # Cannot remove the last scene at this point, treat it differently
    for scene in bpy.data.scenes[:-1]:
        scene_lib.delete_scene(scene)

    share_data.clear_before_state()

    if len(bpy.data.scenes) == 1:
        scene = bpy.data.scenes[0]
        scene.name = "__last_scene_to_be_removed__"

    set_handlers(True)


def is_parent_in_collection(collection, obj):
    parent = obj.parent
    while parent is not None:
        if parent in collection.objects[:]:
            return True
        parent = parent.parent
    return False


@stats_timer(share_data)
def send_scene_content():
    if get_dcc_sync_props().no_send_scene_content:
        return

    share_data.clear_before_state()

    share_data.client.send_group_begin()

    # Temporary waiting for material sync. Should move to send_scene_data_to_server
    for material in bpy.data.materials:
        share_data.client.send_material(material)

    send_scene_data_to_server(None, None)

    share_data.client.send_frame_start_end(bpy.context.scene.frame_start, bpy.context.scene.frame_end)
    share_data.client.send_frame(bpy.context.scene.frame_current)

    share_data.client.send_group_end()


def set_handlers(connect: bool):
    try:
        if connect:
            share_data.depsgraph = bpy.context.evaluated_depsgraph_get()
            bpy.app.handlers.frame_change_post.append(send_frame_changed)
            bpy.app.handlers.depsgraph_update_post.append(send_scene_data_to_server)
            bpy.app.handlers.undo_pre.append(on_undo_redo_pre)
            bpy.app.handlers.redo_pre.append(on_undo_redo_pre)
            bpy.app.handlers.undo_post.append(on_undo_redo_post)
            bpy.app.handlers.redo_post.append(on_undo_redo_post)
            bpy.app.handlers.load_post.append(on_load)
        else:
            bpy.app.handlers.load_post.remove(on_load)
            bpy.app.handlers.frame_change_post.remove(send_frame_changed)
            bpy.app.handlers.depsgraph_update_post.remove(send_scene_data_to_server)
            bpy.app.handlers.undo_pre.remove(on_undo_redo_pre)
            bpy.app.handlers.redo_pre.remove(on_undo_redo_pre)
            bpy.app.handlers.undo_post.remove(on_undo_redo_post)
            bpy.app.handlers.redo_post.remove(on_undo_redo_post)
            share_data.depsgraph = None
    except Exception as e:
        logger.error("Exception during set_handlers(%s) : %s", connect, e)


def wait_for_server(host, port):
    attempts = 0
    max_attempts = 10
    while not create_main_client(host, port) and attempts < max_attempts:
        attempts += 1
        time.sleep(0.2)
    return attempts < max_attempts


def start_local_server():
    dir_path = Path(__file__).parent
    server_path = dir_path / "broadcaster" / "dccBroadcaster.py"

    if get_dcc_sync_props().show_server_console:
        args = {"creationflags": subprocess.CREATE_NEW_CONSOLE}
    else:
        args = {}

    share_data.localServerProcess = subprocess.Popen(
        [bpy.app.binary_path_python, str(server_path)], shell=False, **args
    )


def is_localhost(host):
    # does not catch local address
    return host == "localhost" or host == "127.0.0.1"


def connect():
    logger.info("connect")

    assert share_data.client is None

    props = get_dcc_sync_props()
    if not create_main_client(props.host, props.port):
        if is_localhost(props.host):
            start_local_server()
            if not wait_for_server(props.host, props.port):
                logger.error("Unable to start local server")
                return False
        else:
            logger.error("Unable to connect to remote server %s:%s", props.host, props.port)
            return False

    assert is_client_connected()

    share_data.client.set_client_name(props.user)

    return True


def disconnect():
    logger.info("disconnect")

    leave_current_room()

    if bpy.app.timers.is_registered(network_consumer_timer):
        bpy.app.timers.unregister(network_consumer_timer)

    # the socket has already been disconnected
    if share_data.client is not None:
        if share_data.client.is_connected():
            share_data.client.disconnect()
        share_data.client = None

    share_data.client_ids = None
    share_data.current_room = None

    ui.update_ui_lists()
    ui.redraw()


def on_disconnect_from_server():
    share_data.client = None
    disconnect()


def is_client_connected():
    return share_data.client is not None and share_data.client.is_connected()


def network_consumer_timer():
    if not share_data.client.is_connected():
        error_msg = "Timer still registered but client disconnected."
        logger.error(error_msg)
        if get_dcc_sync_props().env != "production":
            raise RuntimeError(error_msg)
        # Returning None from a timer unregister it
        return None

    # Encapsulate call to share_data.client.network_consumer because
    # if we register it directly, then bpy.app.timers.is_registered(share_data.client.network_consumer)
    # return False...
    # However, with a simple function bpy.app.timers.is_registered works.
    share_data.client.network_consumer()

    # Run every 1 / 100 seconds
    return 0.01


def create_main_client(host: str, port: int):
    assert share_data.client is None
    client = clientBlender.ClientBlender(host, port)
    client.connect()
    if not client.is_connected():
        return False

    share_data.client = client
    share_data.client.add_callback("SendContent", send_scene_content)
    share_data.client.add_callback("ClearContent", clear_scene_content)
    share_data.client.add_callback("Disconnect", on_disconnect_from_server)
    if not bpy.app.timers.is_registered(network_consumer_timer):
        bpy.app.timers.register(network_consumer_timer)

    return True


class CreateRoomOperator(bpy.types.Operator):
    """Create a new room on DCC Sync server"""

    bl_idname = "dcc_sync.create_room"
    bl_label = "DCCSync Create Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        props = get_dcc_sync_props()
        return is_client_connected() and not share_data.current_room and bool(props.room)

    def execute(self, context):
        assert share_data.current_room is None
        if not is_client_connected():
            return {"CANCELLED"}

        props = get_dcc_sync_props()
        join_room(props.room)
        return {"FINISHED"}


class JoinRoomOperator(bpy.types.Operator):
    """Join a room"""

    bl_idname = "dcc_sync.join_room"
    bl_label = "DCCSync Join Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        room_index = get_dcc_sync_props().room_index
        return is_client_connected() and room_index < len(get_dcc_sync_props().rooms)

    def execute(self, context):
        assert not share_data.current_room
        share_data.set_dirty()
        share_data.current_room = None

        share_data.isLocal = False
        props = get_dcc_sync_props()
        room_index = props.room_index
        room = props.rooms[room_index].name
        join_room(room)
        return {"FINISHED"}


class LeaveRoomOperator(bpy.types.Operator):
    """Reave the current room"""

    bl_idname = "dcc_sync.leave_room"
    bl_label = "DCCSync Leave Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return is_client_connected() and share_data.current_room is not None

    def execute(self, context):
        leave_current_room()
        ui.update_ui_lists()
        return {"FINISHED"}


class ConnectOperator(bpy.types.Operator):
    """Connect to the DCCSync server"""

    bl_idname = "dcc_sync.connect"
    bl_label = "Connect to server"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return not is_client_connected()

    def execute(self, context):
        props = get_dcc_sync_props()
        try:
            self.report({"INFO"}, f'Connecting to "{props.host}:{props.port}" ...')
            if not connect():
                self.report({"ERROR"}, "unknown error")
                return {"CANCELLED"}

            self.report({"INFO"}, f'Connected to "{props.host}:{props.port}" ...')
        except socket.gaierror:
            msg = f'Cannot connect to "{props.host}": invalid host name or address'
            self.report({"ERROR"}, msg)
        except Exception as e:
            self.report({"ERROR"}, repr(e))
            return {"CANCELLED"}

        return {"FINISHED"}


class DisconnectOperator(bpy.types.Operator):
    """Disconnect from the DccSync server"""

    bl_idname = "dcc_sync.disconnect"
    bl_label = "Disconnect from server"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return is_client_connected()

    def execute(self, context):
        disconnect()
        self.report({"INFO"}, f"Disconnected ...")
        return {"FINISHED"}


class SendSelectionOperator(bpy.types.Operator):
    """Send current selection to DCC Sync server"""

    bl_idname = "dcc_sync.send_selection"
    bl_label = "DCCSync Send selection"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if share_data.client is None:
            return {"CANCELLED"}

        selected_objects = bpy.context.selected_objects
        for obj in selected_objects:
            try:
                for slot in obj.material_slots[:]:
                    share_data.client.send_material(slot.material)
            except Exception:
                logger.error("materials not found")

            update_params(obj)
            update_transform(obj)

        return {"FINISHED"}


class LaunchVRtistOperator(bpy.types.Operator):
    """Launch a VRtist instance"""

    bl_idname = "vrtist.launch"
    bl_label = "Launch VRtist"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return True

    def execute(self, context):
        dcc_sync_props = get_dcc_sync_props()
        if not share_data.current_room:
            if not connect():
                return {"CANCELLED"}

            props = get_dcc_sync_props()
            join_room(props.room)

        hostname = "localhost"
        if not share_data.isLocal:
            hostname = dcc_sync_props.host
        args = [
            dcc_sync_props.VRtist,
            "--room",
            share_data.current_room,
            "--hostname",
            hostname,
            "--port",
            str(dcc_sync_props.port),
        ]
        subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
        return {"FINISHED"}


class WriteStatisticsOperator(bpy.types.Operator):
    """Write dccsync statistics in a file"""

    bl_idname = "dcc_sync.write_statistics"
    bl_label = "DCCSync Write Statistics"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if share_data.current_statistics is not None:
            save_statistics(share_data.current_statistics, get_dcc_sync_props().statistics_directory)
        return {"FINISHED"}


class OpenStatsDirOperator(bpy.types.Operator):
    """Write dccsync stats directory in explorer"""

    bl_idname = "dcc_sync.open_stats_dir"
    bl_label = "DCCSync Open Stats Directory"
    bl_options = {"REGISTER"}

    def execute(self, context):
        os.startfile(get_dcc_sync_props().statistics_directory)
        return {"FINISHED"}


classes = (
    LaunchVRtistOperator,
    CreateRoomOperator,
    ConnectOperator,
    DisconnectOperator,
    SendSelectionOperator,
    JoinRoomOperator,
    LeaveRoomOperator,
    WriteStatisticsOperator,
    OpenStatsDirOperator,
)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():
    disconnect()

    for _ in classes:
        bpy.utils.unregister_class(_)
