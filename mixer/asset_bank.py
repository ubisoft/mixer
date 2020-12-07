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
This module defines how Asset Bank messages are handled.

Asset Bank is another addon we develop and that can be controlled through Mixer.
We plan to extract this code in a plug-in system in the future to avoid polluting the core of Mixer.
"""

from enum import IntEnum

import bpy
from mixer.share_data import share_data

import mixer.broadcaster.common as common


class AssetBankAction(IntEnum):
    LIST = 0
    IMPORT = 1


def send_asset_bank_entries():
    if bpy.context.window_manager.uas_asset_bank is None:
        return

    assets = bpy.context.window_manager.uas_asset_bank.assets
    names = []
    tags = []
    thumbnails = []

    for asset in assets:
        names.append(asset.nice_name)
        tags.append(asset.tags)
        thumbnails.append(asset.thumbnail_path)

    buffer = common.encode_string_array(names)
    +common.encode_string_array(tags)
    +common.encode_string_array(thumbnails)

    share_data.client.add_command(common.Command(common.MessageType.ASSET_BANK, buffer, 0))


def receive_message(data):
    index = 0
    action, index = common.decode_int(data, index)

    if action == AssetBankAction.LIST:
        send_asset_bank_entries()
    elif action == AssetBankAction.IMPORT:
        import_asset(data, index)


def import_asset(data, index):
    name, index = common.decode_string(data, index)
    asset_index = -1
    for asset in bpy.context.window_manager.uas_asset_bank.assets:
        asset_index += 1
        if asset.nice_name == name:
            bpy.ops.uas.asset_bank_import(asset_index)
            return
