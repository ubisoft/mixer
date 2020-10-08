"""
This module defines Blender handlers for Mixer in generic synchronization mode
"""
from __future__ import annotations

import logging
from typing import Dict, List, Set, TYPE_CHECKING

import bpy

from mixer.blender_client import data as data_api
from mixer.blender_client import grease_pencil as grease_pencil_api
from mixer.blender_data.diff import BpyBlendDiff
from mixer.blender_data.filter import safe_properties

if TYPE_CHECKING:
    from mixer.blender_data.datablock_proxy import DatablockProxy

from mixer.share_data import share_data

logger = logging.getLogger(__name__)


def unhandled_created_datablocks(proxies: List[DatablockProxy]) -> Set[bpy.types.ID]:
    datablocks = set()
    for proxy in proxies:
        if proxy.collection_name != "objects":
            continue
        object_datablock = proxy.collection[proxy.data("name")]
        datablocks.add(object_datablock)
        if object_datablock.data is not None:
            datablocks.add(object_datablock.data)
    return datablocks


def update_unhandled_updated_datablocks(datablocks: Set[bpy.types.ID]):
    """Send messages for datablocks not yet handled by the generic synchronization

    Materials are handled inside mesh/grease pencil send
    """

    unhandled_types = (bpy.types.Mesh, bpy.types.GreasePencil)
    d: Dict[bpy.types.ID, bpy.types.Object] = {}

    for datablock in datablocks:
        if isinstance(datablock, unhandled_types):
            d[datablock] = []

    for datablock in datablocks:
        if isinstance(datablock, bpy.types.Object):
            if (
                datablock.data is not None
                and isinstance(datablock.data, unhandled_types)
                and datablock.mode == "OBJECT"
            ):
                if datablock.data in d:
                    d[datablock.data].append(datablock)

    for data, objects in d.items():
        if isinstance(data, bpy.types.Mesh):
            for obj in objects:
                share_data.client.send_mesh(obj)
        elif isinstance(data, bpy.types.GreasePencil):
            for obj in objects:
                grease_pencil_api.send_grease_pencil_mesh(share_data.client, obj)
                grease_pencil_api.send_grease_pencil_connection(share_data.client, obj)


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

    # Send VRtist formatted messages for datablocks not yet supported by generic synchronization
    # i.e. Mesh, GreasePencil
    # Need to process changeset.creations while sending initial scene contents, depsgraph updates, but
    # subsequent creations are reported both as creations and updates, but must not be processed twice
    # unhandled = unhandled_created_datablocks(changeset.creations)
    # unhandled.update({update.id.original for update in depsgraph.updates})
    # update_unhandled_updated_datablocks(unhandled)

    logger.debug("send_scene_data_to_server: end")
