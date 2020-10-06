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
Proxies for bpy.types.NodeTree and bpy.types.NodeLinks
"""
from __future__ import annotations

import logging
from typing import Any, TYPE_CHECKING
import bpy.types as T  # noqa

from mixer.blender_data.datablock_proxy import DatablockProxy
from mixer.blender_data.proxy import MIXER_SEQUENCE
from mixer.blender_data.attributes import write_attribute
from mixer.blender_data.struct_proxy import StructProxy

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Context

logger = logging.getLogger(__name__)


class NodeLinksProxy(StructProxy):
    """Proxy for bpy.types.NodeLinks"""

    def __init__(self):
        super().__init__()

    def load(self, bl_instance, _, context: Context):
        # NodeLink contain pointers to Node and NodeSocket.
        # Just keep the names to restore the links in ShaderNodeTreeProxy.save

        seq = []
        for link in bl_instance:
            link_data = (
                link.from_node.name,
                link.from_socket.name,
                link.to_node.name,
                link.to_socket.name,
            )
            seq.append(link_data)
        self._data[MIXER_SEQUENCE] = seq
        return self


class NodeTreeProxy(DatablockProxy):
    """Proxies for bpy.types.NodeTree"""

    def __init__(self):
        super().__init__()

    def save(self, bl_instance: Any, attr_name: str, context: Context):
        # see https://stackoverflow.com/questions/36185377/how-i-can-create-a-material-select-it-create-new-nodes-with-this-material-and
        # Saving NodeTree.links require access to NodeTree.nodes, so we need an implementation at the NodeTree level

        node_tree = getattr(bl_instance, attr_name)

        # save links last
        for k, v in self._data.items():
            if k != "links":
                write_attribute(node_tree, k, v, context)

        node_tree.links.clear()
        seq = self.data("links").data(MIXER_SEQUENCE)
        for src_node, src_socket, dst_node, dst_socket in seq:
            src_socket = node_tree.nodes[src_node].outputs[src_socket]
            dst_socket = node_tree.nodes[dst_node].inputs[dst_socket]
            node_tree.links.new(src_socket, dst_socket)
