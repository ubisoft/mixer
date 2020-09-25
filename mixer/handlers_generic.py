"""
This module defines Blender handlers for Mixer in generic synchronization mode
"""
from __future__ import annotations

import logging

import bpy
from bpy.types import Depsgraph

from mixer.blender_client import data as data_api
from mixer.blender_client.client import update_params_generic
from mixer.blender_data.diff import BpyBlendDiff
from mixer.blender_data.filter import safe_context

from mixer.share_data import share_data

logger = logging.getLogger(__name__)


def update_objects_data(depsgraph: Depsgraph):
    if len(depsgraph.updates) == 0:
        return

    for update in depsgraph.updates:
        obj = update.id.original
        if obj.bl_rna is bpy.types.Object.bl_rna:
            update_params_generic(obj=obj)


def send_scene_data_to_server(scene, dummy):
    from mixer.handlers import is_in_object_mode

    logger.debug(
        "send_scene_data_to_server(): skip_next_depsgraph_update %s, pending_test_update %s",
        share_data.client.skip_next_depsgraph_update,
        share_data.pending_test_update,
    )

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

    # Compute the difference between the proxy state and the Blender state
    # It is a coarse difference at the ID level(created, removed, renamed)
    diff = BpyBlendDiff()
    diff.diff(share_data.bpy_data_proxy, safe_context)

    # Ask the proxy to compute the list of elements to synchronize and update itself
    depsgraph = bpy.context.evaluated_depsgraph_get()
    changeset = share_data.bpy_data_proxy.update(diff, safe_context, depsgraph.updates)

    # Send VRtist formatted messages for datablocks not yet supported by generic synchronization
    # i.e. Mesh, GreasePencil
    for proxy in changeset.creations:
        update_params_generic(proxy=proxy)

    data_api.send_data_creations(changeset.creations)
    data_api.send_data_removals(changeset.removals)
    data_api.send_data_renames(changeset.renames)
    data_api.send_data_updates(changeset.updates)
    share_data.bpy_data_proxy.debug_check_id_proxies()

    update_objects_data(depsgraph)

    logger.debug("send_scene_data_to_server: end")
