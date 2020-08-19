"""
This module handles generic updates using the blender_data package.

The goal for Mixer is to replace all code specific to entities (camera, light, material, ...) by this generic update
mechanism.
"""

import logging
import traceback
from typing import Callable, Union

from mixer.blender_data.json_codec import Codec
from mixer.blender_data.proxy import (
    BpyIDProxy,
    BpyBlendProxy,
    CreationChangeset,
    RemovalChangeset,
    UpdateChangeset,
    RenameChangeset,
)
from mixer.broadcaster import common
from mixer.share_data import share_data

logger = logging.getLogger(__name__)


def _send_data_create_or_update(
    proxies: Union[CreationChangeset, UpdateChangeset], display_name: str, message: common.MessageType
):
    if not share_data.use_experimental_sync():
        return

    codec = Codec()
    for proxy in proxies:
        logger.info("%s %s", display_name, proxy)

        try:
            encoded_proxy = codec.encode(proxy)
        except Exception:
            logger.error(f"{display_name}: encode exception for {proxy}")
            for line in traceback.format_exc().splitlines():
                logger.error(line)
            continue

        # For BpyIdProxy, the target is encoded in the proxy._blenddata_path
        buffer = common.encode_string(encoded_proxy)
        command = common.Command(message, buffer, 0)
        share_data.client.add_command(command)


def send_data_creations(proxies: CreationChangeset):
    _send_data_create_or_update(proxies, "send_data_create", common.MessageType.BLENDER_DATA_CREATE)


def send_data_updates(proxies: UpdateChangeset):
    _send_data_create_or_update(proxies, "send_data_update", common.MessageType.BLENDER_DATA_UPDATE)


def _build_data_update_or_create(buffer, display_name: str, func: Callable[[BpyBlendProxy], BpyIDProxy]):
    """
    Process a datablock update request
    """

    def log_exception(when: str):
        logger.error(f"Exception during {display_name}, decode")
        for line in traceback.format_exc().splitlines():
            logger.error(line)
        logger.error(f"During {when}")
        logger.error(buffer[0:200])
        logger.error("...")
        logger.error(buffer[-200:0])
        logger.error(f"ignored")

    if not share_data.use_experimental_sync():
        return

    buffer, _ = common.decode_string(buffer, 0)
    codec = Codec()

    try:
        id_proxy = codec.decode(buffer)
    except Exception:
        log_exception("decode")

    logger.info("%s: %s", display_name, id_proxy)
    try:
        func(share_data.bpy_data_proxy, id_proxy)
    except Exception:
        log_exception(f"processing of buffer for {id_proxy}")

    # TODO temporary until VRtist protocol uses Blenddata instead of blender_objects & co
    share_data.set_dirty()


def build_data_create(buffer):
    _build_data_update_or_create(buffer, "build_data_create", BpyBlendProxy.create_datablock)


def build_data_update(buffer):
    _build_data_update_or_create(buffer, "build_data_update", BpyBlendProxy.update_datablock)


def send_data_removals(removals: RemovalChangeset):
    if not share_data.use_experimental_sync():
        return

    for uuid, debug_info in removals:
        logger.info("send_removal: %s (%s)", uuid, debug_info)
        buffer = common.encode_string(uuid) + common.encode_string(debug_info)
        command = common.Command(common.MessageType.BLENDER_DATA_REMOVE, buffer, 0)
        share_data.client.add_command(command)


def build_data_remove(buffer):
    if not share_data.use_experimental_sync():
        return

    uuid, index = common.decode_string(buffer, 0)
    debug_info, index = common.decode_string(buffer, index)
    logger.info("build_data_remove: %s (%s)", uuid, debug_info)
    share_data.bpy_data_proxy.remove_datablock(uuid)

    # TODO temporary until VRtist protocol uses Blenddata instead of blender_objects & co
    share_data.set_dirty()


def send_data_renames(renames: RenameChangeset):
    if not share_data.use_experimental_sync():
        return

    for uuid, new_name, debug_info in renames:
        logger.info("send_rename: %s %s (%s)", uuid, new_name, debug_info)
        buffer = common.encode_string(uuid) + common.encode_string(new_name) + common.encode_string(debug_info)
        command = common.Command(common.MessageType.BLENDER_DATA_RENAME, buffer, 0)
        share_data.client.add_command(command)


def build_data_rename(buffer):
    if not share_data.use_experimental_sync():
        return

    uuid, index = common.decode_string(buffer, 0)
    new_name, index = common.decode_string(buffer, index)
    debug_info, index = common.decode_string(buffer, index)
    logger.info("build_data_rename: %s (%s) into %s", uuid, debug_info, new_name)
    share_data.bpy_data_proxy.rename_datablock(uuid, new_name)

    # TODO temporary until VRtist protocol uses Blenddata instead of blender_objects & co
    share_data.set_dirty()
