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
from typing import List, Optional, TYPE_CHECKING, Union

from mixer.blender_data.json_codec import Codec, DecodeError
from mixer.broadcaster.common import (
    Command,
    decode_int,
    decode_py_array,
    decode_string,
    decode_string_array,
    encode_int,
    encode_py_array,
    encode_string,
    encode_string_array,
    MessageType,
)
from mixer.local_data import get_local_or_create_cache_file
from mixer.share_data import share_data

if TYPE_CHECKING:
    from mixer.blender_data.changeset import CreationChangeset, RemovalChangeset, UpdateChangeset, RenameChangeset
    from mixer.blender_data.datablock_proxy import DatablockProxy
    from mixer.blender_data.proxy import DeltaUpdate, Uuid


logger = logging.getLogger(__name__)


def send_media_creations(proxy: DatablockProxy):
    media_desc = getattr(proxy, "_media", None)
    if media_desc is None:
        return

    path, bytes_ = media_desc
    items = [encode_string(path), bytes_]
    command = Command(MessageType.BLENDER_DATA_MEDIA, b"".join(items), 0)
    share_data.client.add_command(command)


def build_data_media(buffer: bytes):
    # TODO save to resolved path.
    # The packed data with be saved to file, not a problem
    path, index = decode_string(buffer, 0)
    bytes_ = buffer[index:]
    # TODO this does not overwrite outdated local files
    get_local_or_create_cache_file(path, bytes_)


def send_data_creations(proxies: CreationChangeset):
    if share_data.use_vrtist_protocol():
        return

    codec = Codec()
    for datablock_proxy in proxies:
        logger.info("%s %s", "send_data_create", datablock_proxy)

        try:
            encoded_proxy = codec.encode(datablock_proxy)
        except Exception:
            logger.error(f"send_data_create: encode exception for {datablock_proxy}")
            for line in traceback.format_exc().splitlines():
                logger.error(line)
            continue

        send_media_creations(datablock_proxy)
        # creation so that it is available at bpy_data_ctor() time
        items: List[bytes] = []
        items.append(encode_string(encoded_proxy))
        items.extend(soa_buffers(datablock_proxy))
        command = Command(MessageType.BLENDER_DATA_CREATE, b"".join(items), 0)
        share_data.client.add_command(command)


def soa_buffers(datablock_proxy: Optional[DatablockProxy]) -> List[bytes]:
    if datablock_proxy is None:
        # empty update, should not happen
        return [encode_int(0)]

    # Layout is
    #   number of AosProxy: 2
    #       soa path in datablock : ("vertices")
    #       number of SoaElement : 2
    #           element name: "co"
    #           array
    #           element name: "normals"
    #           array
    #       soa path in datablock : ("edges")
    #       number of SoaElement : 1
    #           element name: "vertices"
    #           array

    items: List[bytes] = []
    items.append(encode_int(len(datablock_proxy._soas)))
    for path, soa_proxies in datablock_proxy._soas.items():
        path_string = json.dumps(path)
        items.append(encode_string(path_string))
        items.append(encode_int(len(soa_proxies)))
        for element_name, soa_element in soa_proxies:
            if soa_element._array is not None:
                items.append(encode_string(element_name))
                items.append(encode_py_array(soa_element._array))
    return items


def send_data_updates(updates: UpdateChangeset):
    if share_data.use_vrtist_protocol():
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

        items: List[bytes] = []
        items.append(encode_string(encoded_update))
        items.extend(soa_buffers(update.value))
        command = Command(MessageType.BLENDER_DATA_UPDATE, b"".join(items), 0)
        share_data.client.add_command(command)


def build_data_create(buffer):
    if share_data.use_vrtist_protocol():
        return

    proxy_string, index = decode_string(buffer, 0)
    codec = Codec()
    rename_changeset = None

    try:
        datablock_proxy: DatablockProxy = codec.decode(proxy_string)
        logger.info("%s: %s", "build_data_create", datablock_proxy)

        # TODO temporary until VRtist protocol uses Blenddata instead of blender_objects & co
        share_data.set_dirty()

        _, rename_changeset = share_data.bpy_data_proxy.create_datablock(datablock_proxy)
        _decode_and_build_soas(datablock_proxy.mixer_uuid(), buffer, index)
    except DecodeError as e:
        logger.error(f"Decode error for {str(e.args[1])[:100]} ...")
        logger.error("... possible version mismatch")
        return
    except Exception:
        logger.error("Exception during build_data_create")
        for line in traceback.format_exc().splitlines():
            logger.error(line)
        logger.error(buffer[0:200])
        logger.error("...")
        logger.error(buffer[-200:0])
        logger.error("ignored")
        return

    if rename_changeset:
        send_data_renames(rename_changeset)


def _decode_and_build_soas(uuid: Uuid, buffer: bytes, index: int):
    path: List[Union[int, str]] = ["unknown"]
    name = "unknown"
    try:
        # see soa_buffers()
        aos_count, index = decode_int(buffer, index)
        for _ in range(aos_count):
            path_string, index = decode_string(buffer, index)
            path = json.loads(path_string)

            logger.info("%s: %s %s", "build_soa", uuid, path)

            element_count, index = decode_int(buffer, index)
            soas = []
            for _ in range(element_count):
                name, index = decode_string(buffer, index)
                array, index = decode_py_array(buffer, index)
                soas.append((name, array))
            share_data.bpy_data_proxy.update_soa(uuid, path, soas)
    except Exception:
        logger.error(f"Exception during build_soa for {uuid} {path} {name}")
        for line in traceback.format_exc().splitlines():
            logger.error(line)
        logger.error("ignored")


def build_data_update(buffer: bytes):
    if share_data.use_vrtist_protocol():
        return

    proxy_string, index = decode_string(buffer, 0)
    codec = Codec()

    try:
        delta: DeltaUpdate = codec.decode(proxy_string)
        logger.info("%s: %s", "build_data_update", delta)
        # TODO temporary until VRtist protocol uses Blenddata instead of blender_objects & co
        share_data.set_dirty()
        share_data.bpy_data_proxy.update_datablock(delta)
        datablock_proxy = delta.value
        if datablock_proxy is not None:
            _decode_and_build_soas(datablock_proxy.mixer_uuid(), buffer, index)
    except DecodeError as e:
        logger.error(f"Decode error for {str(e.args[1])[:100]} ...")
        logger.error("... possible version mismatch")
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
    if share_data.use_vrtist_protocol():
        return

    for uuid, _, debug_info in removals:
        logger.info("send_removal: %s (%s)", uuid, debug_info)
        buffer = encode_string(uuid) + encode_string(debug_info)
        command = Command(MessageType.BLENDER_DATA_REMOVE, buffer, 0)
        share_data.client.add_command(command)


def build_data_remove(buffer):
    if share_data.use_vrtist_protocol():
        return

    uuid, index = decode_string(buffer, 0)
    debug_info, index = decode_string(buffer, index)
    logger.info("build_data_remove: %s (%s)", uuid, debug_info)
    share_data.bpy_data_proxy.remove_datablock(uuid)

    # TODO temporary until VRtist protocol uses Blenddata instead of blender_objects & co
    share_data.set_dirty()


def send_data_renames(renames: RenameChangeset):
    if not renames:
        return
    if share_data.use_vrtist_protocol():
        return

    items = []
    for uuid, old_name, new_name, debug_info in renames:
        logger.info("send_rename: %s (%s) into %s", uuid, debug_info, new_name)
        items.extend([uuid, old_name, new_name])

    buffer = encode_string_array(items)
    command = Command(MessageType.BLENDER_DATA_RENAME, buffer, 0)
    share_data.client.add_command(command)


def build_data_rename(buffer):
    if share_data.use_vrtist_protocol():
        return

    strings, _ = decode_string_array(buffer, 0)

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
