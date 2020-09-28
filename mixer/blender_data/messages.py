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
Definition of messages used by the full Blender protocol

Currently used only in tests. Could be used also in all send_xxx() and build_xxx() functions
"""

from dataclasses import dataclass

from mixer.codec import Message


@dataclass(order=True)
class BlenderCreateMessage(Message):
    proxy_string: str


@dataclass(order=True)
class BlenderUpdateMessage(Message):
    proxy_string: str


@dataclass(order=True)
class BlenderRemoveMessage(Message):
    uuid: str
    debug_info: str


@dataclass(order=True)
class BlenderRenameMessage(Message):
    uuid: str
    new_name: str
    debug_info: str
