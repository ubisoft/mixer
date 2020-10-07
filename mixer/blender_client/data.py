# GPLv3 License
#
# Copyright (C) 2020 Ubisoft
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
This module handles generic updates using the blender_data package.

The goal for Mixer is to replace all code specific to entities (camera, light, material, ...) by this generic update
mechanism.
"""
from __future__ import annotations

import itertools
import json
import logging
import traceback
from typing import TYPE_CHECKING

from mixer.blender_data.json_codec import Codec
from mixer.broadcaster import common
from mixer.share_data import share_data

if TYPE_CHECKING:
    from mixer.blender_data.changeset import CreationChangeset, RemovalChangeset, UpdateChangeset, RenameChangeset
    from mixer.blender_data.proxy import Delta


logger = logging.getLogger(__name__)


def send_data_creations(proxies: CreationChangeset):
    if not share_data.use_experimental_sync():
        return

    codec = Codec()
    for proxy in proxies:
        logger.info("%s %s", "send_data_create", proxy)

        try:
            encoded_proxy = codec.encode(proxy)
        except Exception:
            logger.error(f"send_data_create: encode exception for {proxy}")
            for line in traceback.format_exc().splitlines():
                logger.error(line)
            continue

        buffer = common.encode_string(encoded_proxy)
        command = common.Command(common.MessageType.BLENDER_DATA_CREATE, buffer, 0)
        share_data.client.add_command(command)

        # send SOA commands i.e. one command for all items in MeshVertex.vertices
        # TODO may be possible to group per structure, i.e send all MeshVertex element at once
        uuid = common.encode_string(proxy._datablock_uuid)
        for path, soa_proxies in proxy._soas.items():
            items = [uuid]
            path_string = json.dumps(path)
            items.append(common.encode_string(path_string))
            items.append(common.encode_int(len(soa_proxies)))
            for element_name, soa_proxy in soa_proxies:
                items.append(common.encode_string(element_name))
                items.append(common.encode_py_array(soa_proxy._buffer))
            buffer = b"".join(items)
            command = common.Command(common.MessageType.BLENDER_DATA_SOAS, buffer, 0)
            share_data.client.add_command(command)


def send_data_updates(updates: UpdateChangeset):
    if not share_data.use_experimental_sync():
        return

    codec = Codec()
    for update in updates:
        logger.info("%s %s", "send_data_update", update)

        try:
            encoded_update = codec.encode(update)
        except Exception:
            logger.error(f"send_data_update: encode exception for {update}")
            for line in traceback.format_exc().splitlines():
                logger.error(line)
            continue

        buffer = common.encode_string(encoded_update)
        command = common.Command(common.MessageType.BLENDER_DATA_UPDATE, buffer, 0)
        share_data.client.add_command(command)


def build_data_create(buffer):
    if not share_data.use_experimental_sync():
        return

    buffer, _ = common.decode_string(buffer, 0)
    codec = Codec()
    rename_changeset = None

    try:
        id_proxy = codec.decode(buffer)
        logger.info("%s: %s", "build_data_create", id_proxy)
        # TODO temporary until VRtist protocol uses Blenddata instead of blender_objects & co
        share_data.set_dirty()
        _, rename_changeset = share_data.bpy_data_proxy.create_datablock(id_proxy)
    except Exception:
        logger.error("Exception during build_data_create")
        for line in traceback.format_exc().splitlines():
            logger.error(line)
        logger.error(buffer[0:200])
        logger.error("...")
        logger.error(buffer[-200:0])
        logger.error("ignored")

    if rename_changeset:
        send_data_renames(rename_changeset)


def build_soa(buffer):
    try:
        uuid, _ = common.decode_string(buffer, 0)
        logger.info("%s: %s", "build_soa", uuid)

        uuid, index = common.decode_string(buffer, 0)
        path_string, index = common.decode_string(buffer, index)
        path = json.loads(path_string)
        element_count, index = common.decode_int(buffer, index)
        soas = []
        for _ in range(element_count):
            name, index = common.decode_string(buffer, index)
            array, index = common.decode_py_array(buffer, index)
            soas.append((name, array))
        share_data.bpy_data_proxy.update_soa(uuid, path, soas)
    except Exception:
        logger.error("Exception during build_soa")
        for line in traceback.format_exc().splitlines():
            logger.error(line)
        logger.error("ignored")


def build_data_update(buffer):
    if not share_data.use_experimental_sync():
        return

    buffer, _ = common.decode_string(buffer, 0)
    codec = Codec()

    try:
        delta: Delta = codec.decode(buffer)
        logger.info("%s: %s", "build_data_update", delta)
        # TODO temporary until VRtist protocol uses Blenddata instead of blender_objects & co
        share_data.set_dirty()
        share_data.bpy_data_proxy.update_datablock(delta)
    except Exception:
        logger.error("Exception during build_data_update")
        for line in traceback.format_exc().splitlines():
            logger.error(line)
        logger.error(f"During processing of buffer for {delta}")
        logger.error(buffer[0:200])
        logger.error("...")
        logger.error(buffer[-200:0])
        logger.error("ignored")


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
    if not renames:
        return
    if not share_data.use_experimental_sync():
        return

    items = []
    for uuid, old_name, new_name, debug_info in renames:
        logger.info("send_rename: %s (%s) into %s", uuid, debug_info, new_name)
        items.extend([uuid, old_name, new_name])

    buffer = common.encode_string_array(items)
    command = common.Command(common.MessageType.BLENDER_DATA_RENAME, buffer, 0)
    share_data.client.add_command(command)


def build_data_rename(buffer):
    if not share_data.use_experimental_sync():
        return

    strings, _ = common.decode_string_array(buffer, 0)

    # (uuid1, old1, new1, uuid2, old2, new2, ...) to ((uuid1, old1, new1), (uuid2, old2, new2), ...)
    args = [iter(strings)] * 3
    # do not consume the iterator on the log loop !
    items = list(itertools.zip_longest(*args))

    for uuid, old_name, new_name in items:
        logger.info("build_data_rename: %s (%s) into %s", uuid, old_name, new_name)

    rename_changeset = share_data.bpy_data_proxy.rename_datablocks(items)

    # TODO temporary until VRtist protocol uses Blenddata instead of blender_objects & co
    share_data.set_dirty()

    if rename_changeset:
        send_data_renames(rename_changeset)
