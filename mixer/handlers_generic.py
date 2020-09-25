"""
This module defines Blender handlers for Mixer in generic synchronization mode
"""

from collections import defaultdict
import logging
from typing import Dict, List

import bpy

from mixer.blender_client import data as data_api
from mixer.blender_client import grease_pencil as grease_pencil_api
from mixer.blender_data.diff import BpyBlendDiff
from mixer.blender_data.filter import safe_context
from mixer.blender_data.proxy import BpyIDProxy

from mixer.share_data import share_data

logger = logging.getLogger(__name__)


def update_unhandled_object_proxy_data(proxies: List[BpyIDProxy]) -> List[bpy.types.ID]:
    datablocks = []
    for proxy in proxies:
        if proxy.collection_name != "objects":
            continue
        object_datablock = proxy.collection[proxy.data("name")]
        datablocks.append(object_datablock)
        if object_datablock.data is not None:
            datablocks.append(object_datablock.data)

    update_unhandled_updated_datablocks(datablocks)


def update_unhandled_updated_datablocks(datablocks: List[bpy.types.ID]):
    """Send messages for datablocks not yet handled by the generic synchronization

    Materials are handled inside mesh/grease pencil send
    """

    unhandled_types = (bpy.types.Mesh, bpy.types.GreasePencil)
    d: Dict[bpy.types.ID, bpy.types.Object] = defaultdict(list)
    for datablock in datablocks:
        if isinstance(datablock, bpy.types.Object):
            if (
                datablock.data is not None
                and isinstance(datablock.data, unhandled_types)
                and datablock.mode == "OBJECT"
            ):
                d[datablock.data].append(datablock)
        elif isinstance(datablock, bpy.types.Material):
            share_data.client.send_material(datablock)

    for data, objects in d.items():
        if isinstance(data, bpy.types.Mesh):
            for obj in objects:
                share_data.client.send_mesh(obj)
        elif isinstance(data, bpy.types.GreasePencil):
            # TODO material will be send more than once ?
            for obj in objects:
                for material in obj.materials:
                    share_data.client.send_material(material)
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
    update_unhandled_object_proxy_data(changeset.creations)

    data_api.send_data_creations(changeset.creations)
    data_api.send_data_removals(changeset.removals)
    data_api.send_data_renames(changeset.renames)
    data_api.send_data_updates(changeset.updates)
    share_data.bpy_data_proxy.debug_check_id_proxies()

    datablocks = [update.id.original for update in depsgraph.updates]
    update_unhandled_updated_datablocks(datablocks)

    logger.debug("send_scene_data_to_server: end")
