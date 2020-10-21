"""
This module defines Blender handlers for Mixer in generic synchronization mode
"""
from __future__ import annotations

import logging

import bpy

from mixer.blender_client import data as data_api
from mixer.blender_data.diff import BpyBlendDiff
from mixer.blender_data.filter import safe_properties


from mixer.share_data import share_data

logger = logging.getLogger(__name__)


def send_scene_data_to_server(scene, dummy):

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
        if depsgraph.updates:
            logger.info("send_scene_data_to_server canceled (not is_in_object_mode). Skipping updates")
            for update in depsgraph.updates:
                logger.info(" ......%s", update.id.original)
        return

    # Compute the difference between the proxy state and the Blender state
    # It is a coarse difference at the ID level(created, removed, renamed)
    diff = BpyBlendDiff()
    diff.diff(share_data.bpy_data_proxy, safe_properties)

    # Ask the proxy to compute the list of elements to synchronize and update itself
    depsgraph = bpy.context.evaluated_depsgraph_get()
    changeset = share_data.bpy_data_proxy.update(diff, safe_properties, depsgraph.updates)

    data_api.send_data_creations(changeset.creations)
    data_api.send_data_removals(changeset.removals)
    data_api.send_data_renames(changeset.renames)
    data_api.send_data_updates(changeset.updates)

    logger.debug("send_scene_data_to_server: end")
