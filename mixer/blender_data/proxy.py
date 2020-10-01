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

from enum import IntEnum
import logging
from typing import Any, Optional, TYPE_CHECKING, Union
from uuid import uuid4

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.blenddata import bl_rna_to_type

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import VisitState

logger = logging.getLogger(__name__)

# storing everything in a single dictionary is easier for serialization
MIXER_SEQUENCE = "__mixer_sequence__"


def debug_check_stack_overflow(func, *args, **kwargs):
    """
    Use as a function decorator to detect probable stack overflow in case of circular references

    Beware : inspect performance is very poor.
    sys.setrecursionlimit cannot be used because it will possibly break the Blender VScode
    plugin and StackOverflowException is not caught by VScode "Raised exceptions" breakpoint.
    """

    def wrapper(*args, **kwargs):
        import inspect

        if len(inspect.stack(0)) > 50:
            raise RuntimeError("Possible stackoverflow")
        return func(*args, **kwargs)

    return wrapper


class LoadElementAs(IntEnum):
    STRUCT = 0
    ID_REF = 1
    ID_DEF = 2


def same_rna(a, b):
    return a.bl_rna == b.bl_rna


def is_ID_subclass_rna(bl_rna):  # noqa
    """
    Return true if the RNA is of a subclass of bpy.types.ID
    """
    return issubclass(bl_rna_to_type(bl_rna), bpy.types.ID)


class Delta:
    def __init__(self, value: Optional[Any] = None):
        self.value = value

    def __str__(self):
        return f"<{self.__class__.__name__}({self.value})>"


class DeltaAddition(Delta):
    pass


class DeltaDeletion(Delta):
    # TODO it is overkill to have the deleted value in DeltaDeletion in all cases.
    # we mostly need it if it is a DatablockRefProxy
    pass


class DeltaUpdate(Delta):
    pass


MAX_DEPTH = 30


class Proxy:
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

    def save(self, bl_instance: any, attr_name: str):
        """
        Save this proxy into a blender object
        """
        logger.warning(f"Not implemented: save() for {self.__class__} {bl_instance}.{attr_name}")

    def apply(
        self,
        parent: Any,
        key: Union[int, str],
        delta: Optional[DeltaUpdate],
        visit_state: VisitState,
        to_blender: bool = True,
    ) -> Proxy:
        raise NotImplementedError(f"Proxy.apply() for {parent}[{key}]")

    def diff(
        self, container: Union[T.bpy_prop_collection, T.Struct], key: Union[str, int], visit_state: VisitState
    ) -> Optional[DeltaUpdate]:
        raise NotImplementedError(f"diff for {container}[{key}]")


def ensure_uuid(item: bpy.types.ID) -> str:
    uuid = item.get("mixer_uuid")
    if not uuid:
        uuid = str(uuid4())
        item.mixer_uuid = uuid
    return uuid
