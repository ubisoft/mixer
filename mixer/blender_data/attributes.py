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

import logging
import traceback
from typing import Any, Optional, Union, TYPE_CHECKING

import bpy
import bpy.types as T  # noqa

from mixer.blender_data.blenddata import bl_rna_to_type
from mixer.blender_data.proxy import Delta, DeltaUpdate, Proxy
from mixer.blender_data.specifics import is_soable_collection
from mixer.blender_data.types import is_builtin, is_vector, is_matrix

if TYPE_CHECKING:
    from mixer.blender_data.bpy_data_proxy import Context

logger = logging.getLogger(__name__)


def is_ID_subclass_rna(bl_rna):  # noqa
    """
    Return true if the RNA is of a subclass of bpy.types.ID
    """
    return issubclass(bl_rna_to_type(bl_rna), bpy.types.ID)


MAX_DEPTH = 30


# @debug_check_stack_overflow
def read_attribute(attr: Any, key: Union[int, str], attr_property: T.Property, context: Context):
    """
    Load a property into a python object of the appropriate type, be it a Proxy or a native python object
    """
    attr_type = type(attr)

    if is_builtin(attr_type):
        return attr
    if is_vector(attr_type):
        return list(attr)
    if is_matrix(attr_type):
        return [list(col) for col in attr.col]

    # We have tested the types that are usefully reported by the python binding, now harder work.
    # These were implemented first and may be better implemented with the bl_rna property of the parent struct
    # TODO flatten
    if attr_type == T.bpy_prop_array:
        return list(attr)

    try:
        context.visit_state.recursion_guard.push(attr_property.identifier)
        if attr_type == T.bpy_prop_collection:
            if isinstance(attr_property.fixed_type, bpy.types.ID):
                from mixer.blender_data.datablock_collection_proxy import DatablockRefCollectionProxy

                return DatablockRefCollectionProxy().load(attr, key, context)
            elif is_soable_collection(attr_property):
                from mixer.blender_data.aos_proxy import AosProxy

                return AosProxy().load(attr, key, attr_property, context)
            else:
                from mixer.blender_data.struct_collection_proxy import StructCollectionProxy

                return StructCollectionProxy.make(attr_property).load(attr, key, attr_property, context)

        # TODO merge with previous case
        if isinstance(attr_property, T.CollectionProperty):
            from mixer.blender_data.struct_collection_proxy import StructCollectionProxy

            return StructCollectionProxy().load(attr, key, attr_property, context)

        bl_rna = attr_property.bl_rna
        if bl_rna is None:
            logger.warning("Not implemented: attribute %s", attr)
            return None

        if issubclass(attr_type, T.PropertyGroup):
            from mixer.blender_data.struct_proxy import StructProxy

            return StructProxy().load(attr, key, context)

        if issubclass(attr_type, T.ID):
            if attr.is_embedded_data:
                from mixer.blender_data.datablock_proxy import DatablockProxy

                return DatablockProxy.make(attr_property).load(attr, key, context)
            else:
                from mixer.blender_data.datablock_ref_proxy import DatablockRefProxy

                return DatablockRefProxy().load(attr, key, context)

        if issubclass(attr_type, T.bpy_struct):
            from mixer.blender_data.struct_proxy import StructProxy

            return StructProxy().load(attr, key, context)

        if attr is None and isinstance(attr_property, T.PointerProperty):
            from mixer.blender_data.misc_proxies import NonePtrProxy

            return NonePtrProxy()

        logger.error(
            f"Unsupported attribute {attr_type} {attr_property} {attr_property.fixed_type} at {context.visit_state.datablock_proxy._class_name}.{context.visit_state.path}.{attr_property.identifier}"
        )
    finally:
        context.visit_state.recursion_guard.pop()


def write_attribute(bl_instance, key: Union[str, int], value: Any, context: Context):
    """
    Write a value into a Blender property
    """
    # Like in apply_attribute parent and key are needed to specify a L-value
    if bl_instance is None:
        logger.warning("unexpected write None attribute")
        return

    try:
        if isinstance(value, Proxy):
            value.save(bl_instance, key, context)
        else:
            assert type(key) is str

            prop = bl_instance.bl_rna.properties.get(key)
            if prop is None:
                # Don't log this, too many messages
                # f"Attempt to write to non-existent attribute {bl_instance}.{key} : skipped"
                return

            if not prop.is_readonly:
                try:
                    setattr(bl_instance, key, value)
                except TypeError as e:
                    # common for enum that have unsupported default values, such as FFmpegSettings.ffmpeg_preset,
                    # which seems initialized at "" and triggers :
                    #   TypeError('bpy_struct: item.attr = val: enum "" not found in (\'BEST\', \'GOOD\', \'REALTIME\')')
                    logger.info(f"write attribute skipped {bl_instance}.{key}...")
                    logger.info(f" ...Exception: {repr(e)}")

    except TypeError:
        # common for enum that have unsupported default values, such as FFmpegSettings.ffmpeg_preset,
        # which seems initialized at "" and triggers :
        #   TypeError('bpy_struct: item.attr = val: enum "" not found in (\'BEST\', \'GOOD\', \'REALTIME\')')
        logger.warning(f"write attribute skipped {bl_instance}.{key}...")
        for line in traceback.format_exc().splitlines():
            logger.warning(f" ... {line}")
    except AttributeError as e:
        if isinstance(bl_instance, bpy.types.Collection) and bl_instance.name == "Master Collection" and key == "name":
            pass
        else:
            logger.warning(f"write attribute skipped {bl_instance}.{key}...")
            logger.warning(f" ...Exception: {repr(e)}")

    except Exception:
        logger.warning(f"write attribute skipped {bl_instance}.{key}...")
        for line in traceback.format_exc().splitlines():
            logger.warning(f" ... {line}")


def apply_attribute(parent, key: Union[str, int], proxy_value, delta: Delta, context: Context, to_blender=True) -> Any:
    """
    Applies a delta to the Blender attribute identified by bl_instance.key or bl_instance[key]

    Args:
        parent:
        key:
        proxy_value:
        delta:

    Returns: a value to store into the updated proxy
    """

    # Like in write_attribute parent and key are needed to specify a L-value
    # assert type(delta) == DeltaUpdate

    value = delta.value
    # assert proxy_value is None or type(proxy_value) == type(value)

    try:
        if isinstance(proxy_value, Proxy):
            return proxy_value.apply(parent, key, delta, context, to_blender)

        if to_blender:
            try:
                # try is less costly than fetching the property to find if the attribute is readonly
                setattr(parent, key, value)
            except Exception as e:
                logger.warning(f"apply_attribute: setattr({parent}, {key}, {value})")
                logger.warning(f"... exception {e!r})")
        return value

    except Exception as e:
        logger.warning(f"apply exception for attr: {e!r}")
        raise


def diff_attribute(
    item: Any, key: Union[int, str], item_property: T.Property, value: Any, context: Context
) -> Optional[DeltaUpdate]:
    """
    Computes a difference between a blender item and a proxy value

    Args:
        item: the blender item
        item_property: the property of item as found in its enclosing object
        value: a proxy value

    """
    try:
        if isinstance(value, Proxy):
            return value.diff(item, key, item_property, context)

        # An attribute mappable on a python builtin type
        # TODO overkill to call read_attribute because it is not a proxy type
        blender_value = read_attribute(item, key, item_property, context)
        if blender_value != value:
            # TODO This is too coarse (whole lists)
            return DeltaUpdate(blender_value)

    except Exception as e:
        logger.warning(f"diff exception for attr {item} : {e!r}")
        return None

    return None
