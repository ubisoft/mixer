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
Utility proxy classes

See synchronization.md
"""
from __future__ import annotations

import logging
from typing import Optional, TYPE_CHECKING, Union

import bpy.types as T  # noqa

from mixer.blender_data.attributes import read_attribute
from mixer.blender_data.proxy import Delta, DeltaUpdate, Proxy
from mixer.blender_data.datablock_ref_proxy import DatablockRefProxy

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Context

logger = logging.getLogger(__name__)


class NonePtrProxy(Proxy):
    """Proxy for a None PointerProperty value.

    When setting a PointerProperty from None to a valid reference, apply_attributs requires that
    the proxyfied value implements apply().

    This is used for Pointers to standalone datablocks like Scene.camera.

    TODO Check it it is meaningfull for anything else ?
    """

    def target(self, context: Context) -> None:
        return None

    @property
    def mixer_uuid(self) -> str:
        return "00000000-0000-0000-0000-000000000000"

    def load(self, *_):
        return self

    def save(self, unused_attribute, parent: T.bpy_struct, key: Union[int, str], context: Context):
        """Save None into parent.key or parent[key]"""

        if isinstance(key, int):
            parent[key] = None
        else:
            try:
                setattr(parent, key, None)
            except AttributeError as e:
                # Motsly errors like
                #   AttributeError: bpy_struct: attribute "node_tree" from "Material" is read-only
                # Avoiding them would require filtering attrivutes on save in order not to set
                # Material.node_tree if Material.use_nodes is False
                logger.debug("NonePtrProxy.save() exception for {parent}[{key}]...")
                logger.debug(f"... {repr(e)}")

    def apply(
        self,
        attribute: Union[T.bpy_struct, T.bpy_prop_collection],
        parent: Union[T.bpy_struct, T.bpy_prop_collection],
        key: Union[int, str],
        delta: Delta,
        context: Context,
        to_blender: bool = True,
    ) -> Union[DatablockRefProxy, NonePtrProxy]:
        """
        Apply delta to an attribute with None value.

        This is used for instance Scene.camera is None and updatde to hold a valid Camera reference

        Args:
            attribute: the Blender attribute to update (e.g a_scene.camera)
            parent: the attribute that contains attribute (e.g. a Scene instance)
            key: the key that identifies attribute in parent (e.g; "camera").
            delta: the delta to apply
            context: proxy and visit state
            to_blender: update attribute in addition to this Proxy
        """
        update = delta.value

        if isinstance(update, DatablockRefProxy):
            if to_blender:
                datablock = context.proxy_state.datablocks.get(update._datablock_uuid)
                if isinstance(key, int):
                    parent[key] = datablock
                else:
                    setattr(parent, key, datablock)
            return update

        # A none PointerProperty that can point to something that is not a datablock.
        # Can this happen ?
        logger.error(f"apply({parent}, {key}) called with a {type(update)} at {context.visit_state.path}")
        return self

    def diff(
        self,
        container: Union[T.bpy_prop_collection, T.Struct],
        key: Union[str, int],
        prop: T.Property,
        context: Context,
    ) -> Optional[DeltaUpdate]:
        attr = read_attribute(container, key, prop, context)
        if isinstance(attr, NonePtrProxy):
            return None
        return DeltaUpdate(attr)
