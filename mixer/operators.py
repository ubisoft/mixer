import itertools
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

from mixer.share_data import share_data, object_visibility
from mixer.blender_client import collection as collection_api
from mixer.blender_client import data as data_api
from mixer.blender_client import grease_pencil as grease_pencil_api
from mixer.blender_client import object_ as object_api
from mixer.blender_client import scene as scene_api
from mixer.blender_client.camera import send_camera
from mixer.blender_client.light import send_light
from mixer import clientBlender
from mixer import ui
from mixer.bl_utils import get_mixer_props, get_mixer_prefs
from mixer.stats import StatsTimer, save_statistics, get_stats_filename, stats_timer
from mixer.blender_data.diff import BpyBlendDiff
from mixer.blender_data.filter import safe_context
from mixer.blender_data.blenddata import BlendData
from mixer.broadcaster.common import ClientMetadata, RoomMetadata
from mixer.draw import remove_draw_handlers

import mixer.shot_manager as shot_manager

logger = logging.getLogger(__name__)


class HandlerManager:
    """Manages Blender handlers activation state

    HandlerManager.set_handlers(wanted_state) will enable or disable the handlers activation and
    should be used for initial or final state handling when enterring or leaving a room.

    Temporary activation or desactivation should be performed using
        with HandlerManager.set_handlers(wanted_state):
            do_something()
    """

    _current_state = False

    def __init__(self, wanted_state: bool):
        self._wanted_state = wanted_state
        self._enter_state = None

    def __enter__(self):
        self._enter_state = HandlerManager._current_state
        if self._wanted_state != self._enter_state:
            self._set_handlers(self._wanted_state)
            HandlerManager._current_state = self._wanted_state
        return self

    def __exit__(self, *exc):
        if self._current_state != self._enter_state:
            self._set_handlers(self._enter_state)
            HandlerManager._current_state = self._enter_state
        return False

    @classmethod
    def _set_handlers(cls, connect: bool):
        try:
            if connect:
                bpy.app.handlers.frame_change_post.append(handler_send_frame_changed)
                bpy.app.handlers.depsgraph_update_post.append(handler_send_scene_data_to_server)
                bpy.app.handlers.undo_pre.append(on_undo_redo_pre)
                bpy.app.handlers.redo_pre.append(on_undo_redo_pre)
                bpy.app.handlers.undo_post.append(on_undo_redo_post)
                bpy.app.handlers.redo_post.append(on_undo_redo_post)
                bpy.app.handlers.load_post.append(on_load)
            else:
                bpy.app.handlers.load_post.remove(on_load)
                bpy.app.handlers.frame_change_post.remove(handler_send_frame_changed)
                bpy.app.handlers.depsgraph_update_post.remove(handler_send_scene_data_to_server)
                bpy.app.handlers.undo_pre.remove(on_undo_redo_pre)
                bpy.app.handlers.redo_pre.remove(on_undo_redo_pre)
                bpy.app.handlers.undo_post.remove(on_undo_redo_post)
                bpy.app.handlers.redo_post.remove(on_undo_redo_post)

                remove_draw_handlers()
        except Exception as e:
            logger.error("Exception during set_handlers(%s) : %s", connect, e)

    @classmethod
    def set_handlers(cls, wanted_state: bool):
        if wanted_state != cls._current_state:
            cls._set_handlers(wanted_state)
            cls._current_state = wanted_state


@persistent
def handler_send_frame_changed(scene):
    logger.debug("handler_send_frame_changed")
    if share_data.client.block_signals:
        logger.debug("handler_send_frame_changed canceled (block_signals = True)")
        return

    send_frame_changed(scene)


@persistent
def handler_send_scene_data_to_server(scene, dummy):
    logger.debug("handler_send_scene_data_to_server")

    # Ensure we will rebuild accessors when a depsgraph update happens
    # todo investigate why we need this...
    share_data.set_dirty()

    if share_data.client.block_signals:
        logger.debug("handler_send_scene_data_to_server canceled (block_signals = True)")
        return

    send_scene_data_to_server(scene, dummy)


class TransformStruct:
    def __init__(self, translate, quaternion, scale, visible):
        self.translate = translate
        self.quaternion = quaternion
        self.scale = scale
        self.visible = visible


def update_params(obj):
    # send collection instances
    if obj.instance_type == "COLLECTION":
        collection_api.send_collection_instance(share_data.client, obj)
        return

    if not hasattr(obj, "data"):
        return

    typename = obj.bl_rna.name
    if obj.data:
        typename = obj.data.bl_rna.name

    supported_lights = ["Sun Light", "Point Light", "Spot Light", "Area Light"]
    if (
        typename != "Camera"
        and typename != "Mesh"
        and typename != "Curve"
        and typename != "Text Curve"
        and typename != "Grease Pencil"
        and typename not in supported_lights
    ):
        return

    if typename == "Camera":
        send_camera(share_data.client, obj)

    if typename in supported_lights:
        send_light(share_data.client, obj)

    if typename == "Grease Pencil":
        for material in obj.data.materials:
            share_data.client.send_material(material)
        grease_pencil_api.send_grease_pencil_mesh(share_data.client, obj)
        grease_pencil_api.send_grease_pencil_connection(share_data.client, obj)

    if typename == "Mesh" or typename == "Curve" or typename == "Text Curve":
        if obj.mode == "OBJECT":
            share_data.client.send_mesh(obj)


def update_transform(obj):
    share_data.client.send_transform(obj)


def update_frame_start_end():
    if bpy.context.scene.frame_start != share_data.start_frame or bpy.context.scene.frame_end != share_data.end_frame:
        share_data.client.send_frame_start_end(bpy.context.scene.frame_start, bpy.context.scene.frame_end)
        share_data.start_frame = bpy.context.scene.frame_start
        share_data.end_frame = bpy.context.scene.frame_end


def set_client_metadata():
    prefs = get_mixer_prefs()
    username = prefs.user
    usercolor = prefs.color
    share_data.client.set_client_metadata(
        {ClientMetadata.USERNAME: username, ClientMetadata.USERCOLOR: list(usercolor)}
    )


def join_room(room_name: str):
    logger.info("join_room")

    assert share_data.current_room is None
    BlendData.instance().reset()
    share_data.session_id += 1
    share_data.current_room = room_name
    set_client_metadata()
    share_data.client.join_room(room_name)
    share_data.client.send_set_current_scene(bpy.context.scene.name_full)

    share_data.current_statistics = {
        "session_id": share_data.session_id,
        "blendfile": bpy.data.filepath,
        "statsfile": get_stats_filename(share_data.runId, share_data.session_id),
        "user": get_mixer_prefs().user,
        "room": room_name,
        "children": {},
    }
    prefs = get_mixer_prefs()
    share_data.auto_save_statistics = prefs.auto_save_statistics
    share_data.statistics_directory = prefs.statistics_directory
    share_data.set_experimental_sync(prefs.experimental_sync)
    share_data.pending_test_update = False

    # join a room <==> want to track local changes
    HandlerManager.set_handlers(True)


def leave_current_room():
    logger.info("leave_current_room")

    if share_data.current_room:
        share_data.leave_current_room()
        HandlerManager.set_handlers(False)

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


def find_renamed(items_before: Mapping[Any, Any], items_after: Mapping[Any, Any]):
    """
    Split before/after mappings into added/removed/renamed

    Rename detection is based on the mapping keys (e.g. uuids)
    """
    uuids_before = {uuid for uuid in items_before.keys()}
    uuids_after = {uuid for uuid in items_after.keys()}
    renamed_uuids = {uuid for uuid in uuids_after & uuids_before if items_before[uuid] != items_after[uuid]}
    added_items = [items_after[uuid] for uuid in uuids_after - uuids_before - renamed_uuids]
    removed_items = [items_before[uuid] for uuid in uuids_before - uuids_after - renamed_uuids]
    renamed_items = [(items_before[uuid], items_after[uuid]) for uuid in renamed_uuids]
    return added_items, removed_items, renamed_items


def update_scenes_state():
    """
    Must be called before update_collections_state so that non empty collections added to master
    collection are processed
    """

    for scene in share_data.blender_scenes.values():
        if not scene.mixer_uuid:
            scene.mixer_uuid = str(uuid4())

    scenes_after = {
        scene.mixer_uuid: name
        for name, scene in share_data.blender_scenes.items()
        if name != "__last_scene_to_be_removed__"
    }
    scenes_before = {
        scene.mixer_uuid: name
        for name, scene in share_data.scenes_info.items()
        if name != "__last_scene_to_be_removed__"
    }
    share_data.scenes_added, share_data.scenes_removed, share_data.scenes_renamed = find_renamed(
        scenes_before, scenes_after
    )

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
            scene_api.send_remove_object_from_scene(share_data.client, scene_name, object_name)
            changed = True
    return changed


def remove_objects_from_collections():
    """
    Non master collections, actually
    """
    changed = False
    for collection_name, object_names in share_data.objects_removed_from_collection.items():
        for object_name in object_names:
            collection_api.send_remove_object_from_collection(share_data.client, collection_name, object_name)
            changed = True
    return changed


def remove_collections_from_scenes():
    changed = False
    for scene_name, collection_name in share_data.collections_removed_from_scene:
        scene_api.send_remove_collection_from_scene(share_data.client, scene_name, collection_name)
        changed = True
    return changed


def remove_collections_from_collections():
    """
    Non master collections, actually
    """
    changed = False
    for parent_name, child_name in share_data.collections_removed_from_collection:
        collection_api.send_remove_collection_from_collection(share_data.client, parent_name, child_name)
        changed = True
    return changed


def add_scenes():
    changed = False
    for scene in share_data.scenes_added:
        scene_api.send_scene(share_data.client, scene)
        changed = True
    for old_name, new_name in share_data.scenes_renamed:
        scene_api.send_scene_renamed(share_data.client, old_name, new_name)
        changed = True
    return changed


def remove_scenes():
    changed = False
    for scene in share_data.scenes_removed:
        scene_api.send_scene_removed(share_data.client, scene)
        changed = True
    return changed


def remove_collections():
    changed = False
    for collection in share_data.collections_removed:
        collection_api.send_collection_removed(share_data.client, collection)
        changed = True
    return changed


def add_objects():
    changed = False
    for obj_name in share_data.objects_added:
        obj = share_data.blender_objects.get(obj_name)
        if obj:
            update_params(obj)
            changed = True
    return changed


def update_transforms():
    changed = False
    for obj_name in share_data.objects_added:
        obj = share_data.blender_objects.get(obj_name)
        if obj:
            update_transform(obj)
            changed = True
    return changed


def add_collections():
    changed = False
    for item in share_data.collections_added:
        collection_api.send_collection(share_data.client, get_collection(item))
        changed = True
    return changed


def add_collections_to_collections():
    changed = False
    for parent_name, child_name in share_data.collections_added_to_collection:
        collection_api.send_add_collection_to_collection(share_data.client, parent_name, child_name)
        changed = True
    return changed


def add_collections_to_scenes():
    changed = False
    for scene_name, collection_name in share_data.collections_added_to_scene:
        scene_api.send_add_collection_to_scene(share_data.client, scene_name, collection_name)
        changed = True
    return changed


def add_objects_to_collections():
    changed = False
    for collection_name, object_names in share_data.objects_added_to_collection.items():
        for object_name in object_names:
            collection_api.send_add_object_to_collection(share_data.client, collection_name, object_name)
            changed = True
    return changed


def add_objects_to_scenes():
    changed = False
    for scene_name, object_names in share_data.objects_added_to_scene.items():
        for object_name in object_names:
            scene_api.send_add_object_to_scene(share_data.client, scene_name, object_name)
            changed = True
    return changed


def update_collections_parameters():
    changed = False
    for collection in share_data.blender_collections.values():
        info = share_data.collections_info.get(collection.name_full)
        if info:
            layer_collection = share_data.blender_layer_collections.get(collection.name_full)
            temporary_hidden = False
            if layer_collection:
                temporary_hidden = layer_collection.hide_viewport
            if (
                info.temporary_hide_viewport != temporary_hidden
                or info.hide_viewport != collection.hide_viewport
                or info.instance_offset != collection.instance_offset
            ):
                collection_api.send_collection(share_data.client, collection)
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
    objects = itertools.chain(share_data.objects_added, share_data.objects_visibility_changed)
    for obj_name in objects:
        if obj_name in share_data.blender_objects:
            obj = share_data.blender_objects[obj_name]
            update_transform(obj)
            object_api.send_object_visibility(share_data.client, obj)
            changed = True
    return changed


def update_objects_transforms():
    # changed = False
    for obj_name in share_data.objects_transformed:
        if obj_name in share_data.blender_objects:
            update_transform(share_data.blender_objects[obj_name])
            # changed = True
    return False  # To allow mesh sending after "apply transform"


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
            scene_api.send_add_object_to_vrtist(share_data.client, bpy.context.scene.name_full, obj.name_full)
            changed = True
    return changed


def update_objects_data():
    depsgraph = bpy.context.evaluated_depsgraph_get()

    if len(depsgraph.updates) == 0:
        return  # Exit here to avoid noise if you want to put breakpoints in this function

    data_container = {}
    data = set()
    transforms = set()

    for update in depsgraph.updates:
        obj = update.id.original
        typename = obj.bl_rna.name

        if typename == "Object":
            if hasattr(obj, "data"):
                if obj.data in data_container:
                    data_container[obj.data].append(obj)
                else:
                    data_container[obj.data] = [obj]
            if obj.name_full not in share_data.objects_transformed:
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

        if typename == "Scene":
            update_frame_start_end()
            shot_manager.update_scene()

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


def send_animated_camera_data():
    animated_camera_set = set()
    camera_dict = {}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for update in depsgraph.updates:
        obj = update.id.original
        typename = obj.bl_rna.name
        camera_action_name = ""
        if typename == "Object":
            if obj.data and obj.data.bl_rna.name == "Camera" and obj.animation_data is not None:
                camera_action_name = obj.animation_data.action.name_full
                camera_dict[camera_action_name] = obj
        if typename == "Action" and camera_dict.get(camera_action_name):
            animated_camera_set.add(camera_dict[camera_action_name])

    for camera in animated_camera_set:
        share_data.client.send_camera_attributes(camera)


def send_frame_changed(scene):
    logger.debug("send_frame_changed")

    if not share_data.client:
        logger.debug("send_frame_changed cancelled (no client instance)")
        return

    # We can arrive here because of scene deletion (bpy.ops.scene.delete({'scene': to_remove}) that happens during build_scene)
    # so we need to prevent processing self events
    if share_data.client.skip_next_depsgraph_update:
        share_data.client.skip_next_depsgraph_update = False
        logger.debug("send_frame_changed canceled (skip_next_depsgraph_update = True)")
        return

    if not is_in_object_mode():
        logger.debug("send_frame_changed canceled (not is_in_object_mode)")
        return

    with StatsTimer(share_data, "send_frame_changed") as timer:
        with timer.child("setFrame"):
            if not share_data.client.block_signals:
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

        # temporary code :
        # animated parameters are not sent, we need camera animated parameters for VRtist
        # (focal lens etc.)
        # please remove this when animation is managed
        with timer.child("send_animated_camera_data"):
            send_animated_camera_data()

        with timer.child("send_current_camera"):
            scene_camera_name = ""
            if bpy.context.scene.camera is not None:
                scene_camera_name = bpy.context.scene.camera.name_full

            if share_data.current_camera != scene_camera_name:
                share_data.current_camera = scene_camera_name
                share_data.client.send_current_camera(share_data.current_camera)

        with timer.child("send_shot_manager_current_shot"):
            shot_manager.send_frame()


@stats_timer(share_data)
def send_scene_data_to_server(scene, dummy):
    logger.debug(
        "send_scene_data_to_server(): skip_next_depsgraph_update %s, pending_test_update %s",
        share_data.client.skip_next_depsgraph_update,
        share_data.pending_test_update,
    )

    timer = share_data.current_stats_timer

    if not share_data.client:
        logger.info("send_scene_data_to_server canceled (no client instance)")
        return

    share_data.set_dirty()
    with timer.child("clear_lists"):
        share_data.clear_lists()

    depsgraph = bpy.context.evaluated_depsgraph_get()
    if depsgraph.updates:
        logger.debug("Current dg updates ...")
        for update in depsgraph.updates:
            logger.debug(" ......%s", update.id.original)

    # prevent processing self events, but always process test updates
    if not share_data.pending_test_update and share_data.client.skip_next_depsgraph_update:
        share_data.client.skip_next_depsgraph_update = False
        logger.debug("send_scene_data_to_server canceled (skip_next_depsgraph_update = True) ...")
        return

    share_data.pending_test_update = False

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

        # Updates from the VRtist protocol and from the full Blender protocol must be cafully intermixed
        # This is an unfortunate requirements from the current coexistence status of
        # both protocols

        # After creation of meshes : meshes are not yet supported by full Blender protocol,
        # but needed to properly create objects
        # Before creation of objects :  the VRtint protocol  will implicitely create objects with
        # unappropriate default values (e.g. transform creates an object with no data)
        if share_data.use_experimental_sync():
            # Compute the difference between the proxy state and the Blender state
            # It is a coarse difference at the ID level(created, removed, renamed)
            diff = BpyBlendDiff()
            diff.diff(share_data.proxy, safe_context)

            # Ask the proxy to compute the list of elements to synchronize and update itself
            depsgraph = bpy.context.evaluated_depsgraph_get()
            updates, removals = share_data.proxy.update(diff, safe_context, depsgraph.updates)

            # Send the data update messages (includes serialization)
            data_api.send_data_removals(removals)
            data_api.send_data_updates(updates)
            share_data.proxy.debug_check_id_proxies()

        # send the VRtist transforms after full Blender protocol has the opportunity to create the object data
        # that is not handled by VRtist protocol, otherwise the receiver creates an empty when it receives a transform
        changed |= update_transforms()
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
        changed |= shot_manager.check_montage_mode()

    if not changed:
        with timer.child("update_objects_data"):
            update_objects_data()

    # update for next change
    with timer.child("update_current_data"):
        share_data.update_current_data()

    logger.debug("send_scene_data_to_server: end")


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

    share_data.update_current_data()


def clear_scene_content():
    with HandlerManager(False):

        data = [
            "cameras",
            "collections",
            "curves",
            "grease_pencils",
            "images",
            "lights",
            "objects",
            "materials",
            "metaballs",
            "meshes",
            "textures",
            "worlds",
            "sounds",
        ]

        for name in data:
            collection = getattr(bpy.data, name)
            for obj in collection:
                collection.remove(obj)

        # Cannot remove the last scene at this point, treat it differently
        for scene in bpy.data.scenes[:-1]:
            scene_api.delete_scene(scene)

        share_data.clear_before_state()

        if len(bpy.data.scenes) == 1:
            scene = bpy.data.scenes[0]
            scene.name = "__last_scene_to_be_removed__"


def is_parent_in_collection(collection, obj):
    parent = obj.parent
    while parent is not None:
        if parent in collection.objects[:]:
            return True
        parent = parent.parent
    return False


@stats_timer(share_data)
def send_scene_content():
    if get_mixer_prefs().no_send_scene_content:
        return

    with HandlerManager(False):
        # mesh baking may trigger depsgraph_updatewhen more than one view layer and
        # cause to reenter send_scene_data_to_server() and send duplicate messages

        share_data.clear_before_state()
        share_data.init_proxy()
        share_data.client.send_group_begin()

        # Temporary waiting for material sync. Should move to send_scene_data_to_server
        for material in bpy.data.materials:
            share_data.client.send_material(material)

        send_scene_data_to_server(None, None)

        shot_manager.send_scene()
        share_data.client.send_frame_start_end(bpy.context.scene.frame_start, bpy.context.scene.frame_end)
        share_data.start_frame = bpy.context.scene.frame_start
        share_data.end_frame = bpy.context.scene.frame_end
        share_data.client.send_frame(bpy.context.scene.frame_current)

        share_data.client.send_group_end()


def wait_for_server(host, port):
    attempts = 0
    max_attempts = 10
    while not create_main_client(host, port) and attempts < max_attempts:
        attempts += 1
        time.sleep(0.2)
    return attempts < max_attempts


def start_local_server():
    import mixer

    dir_path = Path(mixer.__file__).parent.parent  # broadcaster is submodule of mixer

    if get_mixer_prefs().show_server_console:
        args = {"creationflags": subprocess.CREATE_NEW_CONSOLE}
    else:
        args = {}

    share_data.localServerProcess = subprocess.Popen(
        [bpy.app.binary_path_python, "-m", "mixer.broadcaster.apps.server", "--port", str(get_mixer_prefs().port)],
        cwd=dir_path,
        shell=False,
        **args,
    )


def is_localhost(host):
    # does not catch local address
    return host == "localhost" or host == "127.0.0.1"


def connect():
    logger.info("connect")
    BlendData.instance().reset()
    if share_data.client is not None:
        # a server shutdown was not processed
        logger.debug("connect: share_data.client is not None")
        share_data.client = None

    prefs = get_mixer_prefs()
    if not create_main_client(prefs.host, prefs.port):
        if is_localhost(prefs.host):
            start_local_server()
            if not wait_for_server(prefs.host, prefs.port):
                logger.error("Unable to start local server")
                return False
        else:
            logger.error("Unable to connect to remote server %s:%s", prefs.host, prefs.port)
            return False

    assert is_client_connected()

    set_client_metadata()

    return True


def disconnect():
    logger.info("disconnect")

    leave_current_room()
    BlendData.instance().reset()

    remove_draw_handlers()

    if bpy.app.timers.is_registered(network_consumer_timer):
        bpy.app.timers.unregister(network_consumer_timer)

    # the socket has already been disconnected
    if share_data.client is not None:
        if share_data.client.is_connected():
            share_data.client.disconnect()
        share_data.client = None

    share_data.client_ids = None
    share_data.rooms_dict = None
    share_data.current_room = None

    ui.update_ui_lists()
    ui.redraw()


def on_disconnect_from_server():
    share_data.client = None
    disconnect()


def is_client_connected():
    return share_data.client is not None and share_data.client.is_connected()


def on_frame_update():
    send_frame_changed(bpy.context.scene)


def on_query_object_data(object_name):
    if object_name not in share_data.blender_objects:
        return
    ob = share_data.blender_objects[object_name]
    update_params(ob)


def network_consumer_timer():
    if not share_data.client.is_connected():
        error_msg = "Timer still registered but client disconnected."
        logger.error(error_msg)
        if get_mixer_prefs().env != "production":
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
    if share_data.client is not None:
        # a server shutdown was not processed
        logger.debug("create_main_client: share_data.client is not None")
        share_data.client = None

    client = clientBlender.ClientBlender(host, port)
    client.connect()
    if not client.is_connected():
        return False

    share_data.client = client
    share_data.client.add_callback("SendContent", send_scene_content)
    share_data.client.add_callback("ClearContent", clear_scene_content)
    share_data.client.add_callback("Disconnect", on_disconnect_from_server)
    share_data.client.add_callback("QueryObjectData", on_query_object_data)
    if not bpy.app.timers.is_registered(network_consumer_timer):
        bpy.app.timers.register(network_consumer_timer)

    return True


poll_is_client_connected = (lambda: is_client_connected(), "Client not connected")
poll_rooms_received_from_server = (lambda: share_data.rooms_dict is not None, "Rooms not received from server")
poll_already_in_a_room = (lambda: not share_data.current_room, "Already in a room")


def generic_poll(cls, context):
    for func, _reason in cls.poll_functors(context):
        if not func():
            return False
    return True


def generic_description(cls, context, properties):
    result = cls.__doc__
    for func, reason in cls.poll_functors(context):
        if not func():
            result += f" (Error: {reason})"
            break
    return result


class CreateRoomOperator(bpy.types.Operator):
    """Create a new room on Mixer server"""

    bl_idname = "mixer.create_room"
    bl_label = "Create Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll_functors(cls, context):
        return [
            poll_is_client_connected,
            poll_rooms_received_from_server,
            poll_already_in_a_room,
            (lambda: get_mixer_prefs().room != "", "Room name cannot be empty"),
            (lambda: get_mixer_prefs().room not in share_data.rooms_dict, "Room already exists"),
        ]

    @classmethod
    def poll(cls, context):
        return generic_poll(cls, context)

    @classmethod
    def description(cls, context, properties):
        return generic_description(cls, context, properties)

    def execute(self, context):
        assert share_data.current_room is None
        if not is_client_connected():
            return {"CANCELLED"}

        join_room(get_mixer_prefs().room)

        return {"FINISHED"}


def get_selected_room_dict():
    room_index = get_mixer_props().room_index
    assert room_index < len(get_mixer_props().rooms)
    return share_data.rooms_dict[get_mixer_props().rooms[room_index].name]


class JoinRoomOperator(bpy.types.Operator):
    """Join a room"""

    bl_idname = "mixer.join_room"
    bl_label = "Join Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll_functors(cls, context):
        return [
            poll_is_client_connected,
            poll_rooms_received_from_server,
            poll_already_in_a_room,
            (lambda: get_mixer_props().room_index < len(get_mixer_props().rooms), "Invalid room selection"),
            (
                lambda: (
                    ("experimental_sync" not in get_selected_room_dict() and not get_mixer_prefs().experimental_sync)
                    or (
                        "experimental_sync" in get_selected_room_dict()
                        and get_mixer_prefs().experimental_sync == get_selected_room_dict()["experimental_sync"]
                    )
                ),
                "Experimental flag does not match selected room",
            ),
            (
                lambda: get_selected_room_dict().get(RoomMetadata.JOINABLE, False),
                "Room is not joinable, first client has not finished sending initial content.",
            ),
        ]

    @classmethod
    def poll(cls, context):
        return generic_poll(cls, context)

    @classmethod
    def description(cls, context, properties):
        return generic_description(cls, context, properties)

    def execute(self, context):
        assert not share_data.current_room
        share_data.set_dirty()
        share_data.current_room = None

        props = get_mixer_props()
        room_index = props.room_index
        room = props.rooms[room_index].name
        join_room(room)

        return {"FINISHED"}


class DeleteRoomOperator(bpy.types.Operator):
    """Delete an empty room"""

    bl_idname = "mixer.delete_room"
    bl_label = "Delete Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        room_index = get_mixer_props().room_index
        return (
            is_client_connected()
            and room_index < len(get_mixer_props().rooms)
            and (get_mixer_props().rooms[room_index].users_count == 0)
        )

    def execute(self, context):
        props = get_mixer_props()
        room_index = props.room_index
        room = props.rooms[room_index].name
        share_data.client.delete_room(room)

        return {"FINISHED"}


class DownloadRoomOperator(bpy.types.Operator):
    """Download content of an empty room"""

    bl_idname = "mixer.download_room"
    bl_label = "Download Room"
    bl_options = {"REGISTER"}

    filepath: bpy.props.StringProperty(subtype="FILE_PATH")

    @classmethod
    def poll(cls, context):
        room_index = get_mixer_props().room_index
        return (
            is_client_connected()
            and room_index < len(get_mixer_props().rooms)
            and (get_mixer_props().rooms[room_index].users_count == 0)
        )

    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}

    def execute(self, context):
        from mixer.broadcaster.room_bake import download_room, save_room

        prefs = get_mixer_prefs()
        props = get_mixer_props()
        room_index = props.room_index
        room = props.rooms[room_index].name
        metadata, commands = download_room(prefs.host, prefs.port, room)
        save_room(metadata, commands, self.filepath)

        return {"FINISHED"}


class UploadRoomOperator(bpy.types.Operator):
    """Upload content of an empty room"""

    bl_idname = "mixer.upload_room"
    bl_label = "Upload Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        mixer_props = get_mixer_props()
        return (
            is_client_connected()
            and share_data.rooms_dict is not None
            and os.path.exists(mixer_props.upload_room_filepath)
            and mixer_props.upload_room_name not in share_data.rooms_dict
        )

    def execute(self, context):
        from mixer.broadcaster.room_bake import load_room, upload_room

        prefs = get_mixer_prefs()
        props = get_mixer_props()

        metadata, commands = load_room(props.upload_room_filepath)
        upload_room(prefs.host, prefs.port, props.upload_room_name, metadata, commands)

        return {"FINISHED"}


class LeaveRoomOperator(bpy.types.Operator):
    """Leave the current room"""

    bl_idname = "mixer.leave_room"
    bl_label = "Leave Room"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return is_client_connected() and share_data.current_room is not None

    def execute(self, context):
        leave_current_room()
        ui.update_ui_lists()
        return {"FINISHED"}


class ConnectOperator(bpy.types.Operator):
    """Connect to the Mixer server"""

    bl_idname = "mixer.connect"
    bl_label = "Connect to server"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return not is_client_connected()

    def execute(self, context):
        prefs = get_mixer_prefs()
        try:
            self.report({"INFO"}, f'Connecting to "{prefs.host}:{prefs.port}" ...')
            if not connect():
                self.report({"ERROR"}, "unknown error")
                return {"CANCELLED"}

            self.report({"INFO"}, f'Connected to "{prefs.host}:{prefs.port}" ...')
        except socket.gaierror as e:
            msg = f'Cannot connect to "{prefs.host}": invalid host name or address'
            self.report({"ERROR"}, msg)
            if prefs.env != "production":
                raise e
        except Exception as e:
            self.report({"ERROR"}, repr(e))
            if prefs.env != "production":
                raise e
            return {"CANCELLED"}

        return {"FINISHED"}


class DisconnectOperator(bpy.types.Operator):
    """Disconnect from the Mixer server"""

    bl_idname = "mixer.disconnect"
    bl_label = "Disconnect from server"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return is_client_connected()

    def execute(self, context):
        disconnect()
        self.report({"INFO"}, "Disconnected ...")
        return {"FINISHED"}


class SendSelectionOperator(bpy.types.Operator):
    """Send current selection to Mixer server"""

    bl_idname = "mixer.send_selection"
    bl_label = "Mixer Send selection"
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
        return os.path.isfile(get_mixer_prefs().VRtist)

    def execute(self, context):
        bpy.data.window_managers["WinMan"].mixer.send_base_meshes = False
        mixer_prefs = get_mixer_prefs()
        if not share_data.current_room:
            if not connect():
                return {"CANCELLED"}
            join_room(mixer_prefs.room)

        args = [
            mixer_prefs.VRtist,
            "--room",
            share_data.current_room,
            "--hostname",
            mixer_prefs.host,
            "--port",
            str(mixer_prefs.port),
        ]
        subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=False)
        return {"FINISHED"}


class WriteStatisticsOperator(bpy.types.Operator):
    """Write Mixer statistics in a file"""

    bl_idname = "mixer.write_statistics"
    bl_label = "Mixer Write Statistics"
    bl_options = {"REGISTER"}

    def execute(self, context):
        if share_data.current_statistics is not None:
            save_statistics(share_data.current_statistics, get_mixer_props().statistics_directory)
        return {"FINISHED"}


class OpenStatsDirOperator(bpy.types.Operator):
    """Write Mixer stats directory in explorer"""

    bl_idname = "mixer.open_stats_dir"
    bl_label = "Mixer Open Stats Directory"
    bl_options = {"REGISTER"}

    def execute(self, context):
        os.startfile(get_mixer_prefs().statistics_directory)
        return {"FINISHED"}


classes = (
    LaunchVRtistOperator,
    CreateRoomOperator,
    ConnectOperator,
    DisconnectOperator,
    SendSelectionOperator,
    JoinRoomOperator,
    DeleteRoomOperator,
    LeaveRoomOperator,
    WriteStatisticsOperator,
    OpenStatsDirOperator,
    DownloadRoomOperator,
    UploadRoomOperator,
)


def register():
    for _ in classes:
        bpy.utils.register_class(_)


def unregister():
    disconnect()

    for _ in classes:
        bpy.utils.unregister_class(_)
