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

from __future__ import annotations

from typing import List, Tuple

import bpy.types as T  # noqa


from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.proxy import DeltaUpdate


CreationChangeset = List[DatablockProxy]
UpdateChangeset = List[DeltaUpdate]
# uuid, debug_display
RemovalChangeset = List[Tuple[str, str]]
# uuid, old_name, new_name, debug_display
RenameChangeset = List[Tuple[str, str, str, str]]


class Changeset:
    def __init__(self):
        self.creations: CreationChangeset = []
        self.removals: RemovalChangeset = []
        self.renames: RenameChangeset = []
        self.updates: UpdateChangeset = []
