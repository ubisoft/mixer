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
Base class and utilities for the proxy system.

See synchronization.md
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING, Union
from uuid import uuid4

import bpy
import bpy.types as T  # noqa

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context
    from mixer.blender_data.datablock_ref_proxy import DatablockRefProxy

logger = logging.getLogger(__name__)

MIXER_SEQUENCE = "__mixer_sequence__"

Uuid = str


@dataclass
class UnresolvedRef:
    """A datablock reference that could not be resolved when target.init() needed to be called
    because the referenced datablock was not yet received.

    No suitable ordering can easily be provided by the sender for many reasons including Collection.children
    referencing other collections and Scene.sequencer strips that can reference other scenes
    """

    target: T.bpy_prop_collection
    proxy: DatablockRefProxy


class UnresolvedRefs:
    """For each each Struct ot collection of datablocks, a list or unresolved references
    Datablock referenced may be temporarily unresolved when referenced datablocks
    (e.g. a bpy.types.Collection) are received before the item that references it
    (e.g. bpy.types.Collection.children)
    """

    SrcLink = Callable[[T.ID], None]

    def __init__(self):
        self._refs: Dict[Uuid, List[self.Func]] = defaultdict(list)

    def append(self, dst_uuid: Uuid, src_link: SrcLink):
        self._refs[dst_uuid].append(src_link)

    def resolve(self, dst_uuid: Uuid, dst_datablock: T.ID):
        if dst_uuid in self._refs:
            for src_link in self._refs[dst_uuid]:
                src_link(dst_datablock)
                logger.info(f"resolving reference to {dst_datablock}")
            del self._refs[dst_uuid]


class MaxDepthExceeded(Exception):
    """Thrown when attribute depth is too large"""

    pass


class Delta:
    """
    A Delta records the difference between the proxy state and Blender state.

    It is created with Proxy.diff() and applied with Proxy.apply()
    """

    def __init__(self, value: Optional[Any] = None):
        self.value = value

    def __str__(self):
        return f"<{self.__class__.__name__}({self.value})>"


class DeltaAddition(Delta):
    pass


class DeltaDeletion(Delta):
    pass


class DeltaUpdate(Delta):
    pass


class Proxy:
    """
    Base class for all proxies.
    """

    def __eq__(self, other):
        if self.__class__ is not other.__class__:
            return False
        if len(self._data) != len(other._data):
            return False

        # TODO test same keys
        # TODO test _bpy_collection
        for k, v in self._data.items():
            if k not in other._data.keys():
                return False
            if v != other._data[k]:
                return False
        return True

    def __contains__(self, value):
        return value in self._data

    def init(self, _):
        pass

    def data(self, key: Union[str, int], resolve_delta=True) -> Any:
        """Return the data at key, which may be a struct member, a dict value or an array value,

        Args:
            key: Integer or string to be used as index or key to the data
            resolve_delta: If True, and the data is a Delta, will return the delta value
        """

        def resolve(data):
            if isinstance(data, Delta) and resolve_delta:
                return data.value
            return data

        if isinstance(key, int):
            if MIXER_SEQUENCE in self._data:
                try:
                    return resolve(self._data[MIXER_SEQUENCE][key])
                except IndexError:
                    return None
            else:
                # used by the diff mode that generates a dict with int keys
                return resolve(self._data.get(key))
        else:
            return resolve(self._data.get(key))

    def save(self, bl_instance: Any, attr_name: str, context: Context):
        """
        Save this proxy into a blender object
        """
        logger.warning(f"Not implemented: save() for {self.__class__} {bl_instance}.{attr_name}")

    def apply(
        self,
        parent: Any,
        key: Union[int, str],
        delta: Optional[DeltaUpdate],
        context: Context,
        to_blender: bool = True,
    ) -> Proxy:
        raise NotImplementedError(f"Proxy.apply() for {parent}[{key}]")

    def diff(
        self, container: Union[T.bpy_prop_collection, T.Struct], key: Union[str, int], context: Context
    ) -> Optional[DeltaUpdate]:
        raise NotImplementedError(f"diff for {container}[{key}]")

    def find_by_path(
        self, bl_item: Union[T.bpy_struct, T.bpy_prop_collection], path: List[Union[int, str]]
    ) -> Optional[Tuple[Union[T.bpy_struct, T.bpy_prop_collection], Proxy]]:
        head, *tail = path
        if isinstance(bl_item, T.bpy_struct):
            bl = getattr(bl_item, head)
        elif isinstance(bl_item, T.bpy_prop_collection):
            if isinstance(head, int) and head + 1 > len(bl_item):
                logger.error(f"Index {head} > len({bl_item}) ({len(bl_item)})")
                return None
            if isinstance(head, str) and head not in bl_item:
                logger.error(f"Key {head} not in {bl_item}")
                return None
            bl = bl_item[head]
        else:
            return None

        proxy = self.data(head)
        if proxy is None:
            logger.warning(f"find_by_path: No proxy for {bl_item} {path}")
            return

        if not tail:
            return bl, proxy

        return proxy.find_by_path(bl, tail)


def ensure_uuid(item: bpy.types.ID) -> str:
    """Ensures that the item datablock has a mixer_uuid property"""
    uuid = item.get("mixer_uuid")
    if not uuid:
        uuid = str(uuid4())
        item.mixer_uuid = uuid
    return uuid
