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

"""Interface to the bpy.data collections
"""
import functools
import logging
from typing import Iterable, Mapping

import bpy
import bpy.types as T  # noqa N812

logger = logging.getLogger(__name__)


def bl_rna_to_type(bl_rna):
    return getattr(T, bl_rna.identifier)


# Map root collection name to object type
# e.g. "objects" -> bpy.types.Object, "lights" -> bpy.types.Light, ...
collection_name_to_type = {
    p.identifier: bl_rna_to_type(p.fixed_type)
    for p in T.BlendData.bl_rna.properties
    if p.bl_rna.identifier == "CollectionProperty"
}

# Map object type name to root collection
# e.g. "Object" -> "objects", "Light" -> "lights"
rna_identifier_to_collection_name = {value.bl_rna.identifier: key for key, value in collection_name_to_type.items()}


class BlendDataCollection:
    """
    Wrapper to any of the collections inside bpy.data
    """

    # DO NOT keep references to bpy.data collection. They become stale and to not show modifications

    def __init__(self, name: str):
        self._name = name
        self._dirty: bool = True
        self._items = {}

    def __getitem__(self, key):
        item = self.items.get(key)
        if item is None:
            self._reload()
        return self.items.get(key)

    def name(self):
        return self._name

    def bpy_collection(self) -> T.bpy_prop_collection:
        return getattr(bpy.data, self._name)

    @property
    def items(self):
        if not self._dirty:
            return self._items

        self._reload()
        return self._items

    def _reload(self):
        self._items = {x.name_full: x for x in self.bpy_collection()}
        self._dirty = False

    def remove(self, name_full):
        if self._name == "scenes":
            # search for __last_scene_to_be_removed__
            logger.error("Not implemented : remove scene %s", name_full)
            return
        item = self.items.get(name_full)
        if item is None:
            logger.warning(f"BlendDataCollection.remove(): item not found {self._name}[{name_full}]")
            return
        collection = self.bpy_collection()
        if collection.find(name_full) != -1:
            self.bpy_collection().remove(item)
        else:
            logger.info(
                f"BlendDataCollection.remove(): attempt to remove non-existent_object bpy.data.{self._name}[{name_full}]. Ignoring"
            )
        self.set_dirty()

    def rename(self, old_name, new_name):
        item = self.items[old_name]
        item.name = new_name
        del self._items[old_name]
        self._items[new_name] = item

    def set_dirty(self):
        self._dirty = True
        # avoid stale entries, that might cause problems while debugging
        self._items.clear()


class BlendData:
    """
    Wrapper to bpy.data, with linear time access to collection items by name.

    These objects keep live reference to Blender blenddata collection, so they must not be used after the
    file has been reloaded, hence the handler below.
    """

    # TODO rework the APi to look more like bpy.data, with a bpy_data() instead of BlendData.instance()

    # DO NOT keep references to bpy.data collection. They become stale and to not show modifications

    def __init__(self):
        self.reset()

    @classmethod
    @functools.lru_cache(1)
    def instance(cls):
        """
        Work around a situation where a BlendData object cannot be initialized during addon loading because an exception
        is thrown like in
        https://blender.stackexchange.com/questions/8702/attributeerror-restrictdata-object-has-no-attribute-filepath
        but about bpy.data
        """

        # In the end this is very messy. This structure is to avoid hadcoding information about Blenddata.
        # The trouble is that during addon loading, getattr(bpy.data, 'cameras') will fail with error
        #   AttributeError: '_RestrictData' object has no attribute 'cameras'
        # So any python module that instanciates this class at the module level will cause the error

        return cls()

    def reset(self):
        self._collections = {name: BlendDataCollection(name) for name in collection_name_to_type.keys()}

        # "Object": "objects"
        self._collections_name_from_inner_identifier: Mapping[str, str] = {
            type_.bl_rna.identifier: name for name, type_ in collection_name_to_type.items()
        }

    def __getitem__(self, attrname):
        return self._collections[attrname].items

    def set_dirty(self):
        for data in self._collections.values():
            data.set_dirty()

    def clear(self):
        for data in self._collections.values():
            data.clear()

    def collection_names(self) -> Iterable[str]:
        return self._collections

    def collection(self, collection_name: str) -> BlendDataCollection:
        return self._collections.get(collection_name)

    def bpy_collection(self, collection_name: str) -> T.bpy_prop_collection:
        return self._collections.get(collection_name).bpy_collection()

    def bl_collection_name_from_inner_identifier(self, type_identifier: str) -> str:
        """
        Blenddata collection from the name of the inner type (e.g. 'Object', 'Light')
        """
        return self._collections_name_from_inner_identifier[type_identifier]

    def bl_collection_name_from_ID(self, id: T.ID) -> str:  # noqa N802
        """
        Blenddata collection from an Id.
        """
        # Find the topmost type below ID, e.g. Light for AreaLight
        bl_rna = id.bl_rna
        while bl_rna is not None and bl_rna.base.bl_rna is not bpy.types.ID.bl_rna:
            bl_rna = bl_rna.base
        if bl_rna is None:
            return None
        type_identifier = bl_rna.identifier
        return self._collections_name_from_inner_identifier[type_identifier]


@bpy.app.handlers.persistent
def on_load(dummy):
    BlendData.instance().reset()


def register():
    for t in collection_name_to_type.values():
        t.mixer_uuid = bpy.props.StringProperty(default="")

    # unfortunately cannot use reset during plugin load/unload
    bpy.app.handlers.load_post.append(on_load)


def unregister():
    bpy.app.handlers.load_post.remove(on_load)
