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
Proxy of a collection

See synchronization.md
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING, Union

import bpy.types as T  # noqa

from mixer.blender_data import specifics
from mixer.blender_data.aos_soa_proxy import AosElement, SoaElement
from mixer.blender_data.specifics import is_soable_property
from mixer.blender_data.attributes import write_attribute
from mixer.blender_data.proxy import DeltaUpdate
from mixer.blender_data.proxy import Proxy

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Context

logger = logging.getLogger(__name__)


class AosProxy(Proxy):
    """
    Proxy to a bpy_prop_collection of non-datablock Struct.

    It can track an array (int keys) or a dictionnary(string keys). Both implementation are
    in the same class as it is not possible to know at creation time the type of an empty collection
    """

    def __init__(self):
        self._data: Dict[str, SoaElement] = {}
        self._aos_length = 0

    @property
    def length(self) -> int:
        return self._aos_length

    def load(self, bl_collection: T.bpy_prop_collection, bl_collection_property: T.Property, context: Context):
        self._aos_length = len(bl_collection)
        if self._aos_length == 0:
            self._data.clear()
            return self

        prototype_item = bl_collection[0]

        try:
            context.visit_state.path.append(bl_collection_property.identifier)
            # TODO too much work at l   oad time to find soable information. Do it once for all.

            # Hybrid array_of_struct/ struct_of_array
            # Hybrid because MeshVertex.groups does not have a fixed size and is not soa-able, but we want
            # to treat other MeshVertex members as SOAs.
            # Could be made more efficient later on. Keep the code simple until save() is implemented
            # and we need better
            item_bl_rna = bl_collection_property.fixed_type.bl_rna
            for attr_name, bl_rna_property in context.synchronized_properties.properties(item_bl_rna):
                if is_soable_property(bl_rna_property):
                    # element type supported by foreach_get
                    self._data[attr_name] = SoaElement().load(bl_collection, attr_name, prototype_item, context)
                else:
                    # no foreach_get (variable length arrays like MeshVertex.groups, enums, ...)
                    self._data[attr_name] = AosElement().load(bl_collection, item_bl_rna, attr_name, context)
        finally:
            context.visit_state.path.pop()
        return self

    def save(self, bl_instance: Any, attr_name: str, context: Context):
        """
        Save this proxy the Blender property
        """
        target = getattr(bl_instance, attr_name, None)
        if target is None:
            return

        try:
            context.visit_state.path.append(attr_name)
            specifics.truncate_collection(target, self, context)
            for k, v in self._data.items():
                write_attribute(target, k, v, context)
        finally:
            context.visit_state.path.pop()

    def apply(
        self, parent: Any, key: Union[int, str], delta: Optional[DeltaUpdate], context: Context, to_blender=True
    ) -> AosProxy:
        raise NotImplementedError("AosProxy.apply()")

    def diff(
        self, collection: T.bpy_prop_collection, collection_property: T.Property, context: Context
    ) -> Optional[DeltaUpdate]:
        """
        Computes the difference between the state of an item tracked by this proxy and its Blender state.

        This proxy tracks a collection of items indexed by string (e.g Scene.render.views) or int.
        The result will be a ProxyDiff that contains a Delta item per added, deleted or updated item

        Args:
            collection; the collection that must be diffed agains this proxy
            collection_property; the property os collection as found in its enclosing object
        """
        raise NotImplementedError("AosProxy.diff")
