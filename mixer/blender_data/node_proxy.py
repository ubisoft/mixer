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
from typing import Any, Dict, List, Optional, TYPE_CHECKING
import bpy.types as T  # noqa

from mixer.blender_data.proxy import DeltaUpdate
from mixer.blender_data.struct_collection_proxy import StructCollectionProxy

if TYPE_CHECKING:
    from mixer.blender_data.proxy import Context

logger = logging.getLogger(__name__)


class NodeLinksProxy(StructCollectionProxy):
    """Proxy for bpy.types.NodeLinks"""

    def _load(self, links: T.NodeLinks) -> List[Dict[str, str]]:
        seq = []
        for link in links:
            item = {}
            # NodeLink contain pointers to Node and NodeSocket.
            # Just keep the names to restore the links in ShaderNodeTreeProxy.save
            item["from_node"] = link.from_node.name
            item["from_socket"] = link.from_socket.name
            item["to_node"] = link.to_node.name
            item["to_socket"] = link.to_socket.name
            seq.append(item)
        return seq

    def load(self, links: T.NodeLinks, key: str, _, context: Context) -> NodeLinksProxy:
        self._sequence = self._load(links)
        return self

    def save(self, unused_attribute, node_tree: T.NodeTree, unused_key: str, context: Context):
        """Saves this proxy into node_tree.links"""
        if not isinstance(node_tree, T.NodeTree):
            logger.error(f"NodeLinksProxy.save() called with {node_tree}. Expected a bpy.types.NodeTree")
            return

        node_tree.links.clear()
        for link_proxy in self._sequence:
            from_node_name = link_proxy["from_node"]
            from_socket_name = link_proxy["from_socket"]
            to_node_name = link_proxy["to_node"]
            to_socket_name = link_proxy["to_socket"]

            from_node = node_tree.nodes.get(from_node_name)
            if from_node is None:
                logger.error(f"save(): from_node {node_tree}.nodes[{from_node_name}] is None")
                return

            from_socket = from_node.outputs.get(from_socket_name)
            if from_socket is None:
                logger.error(f"save(): from_socket {node_tree}.nodes[{from_socket_name}] is None")
                return

            to_node = node_tree.nodes.get(to_node_name)
            if to_node is None:
                logger.error(f"save(): to_node {node_tree}.nodes[{to_node_name}] is None")
                return

            to_socket = to_node.inputs.get(to_socket_name)
            if to_socket is None:
                logger.error(f"save(): to_socket {node_tree}.nodes[{to_socket_name}] is None")
                return

            node_tree.links.new(from_socket, to_socket)

    def apply(
        self,
        parent: Any,
        key: str,
        struct_delta: Optional[DeltaUpdate],
        context: Context,
        to_blender: bool = True,
    ) -> Optional[NodeLinksProxy]:

        struct_update = struct_delta.value
        self._sequence = struct_update._sequence

        node_tree = getattr(parent, key)
        # update Blender
        if to_blender:
            self.save(node_tree, parent, key, context)

        if node_tree is None:
            return None

        return self

    def diff(self, links: T.NodeLinks, key, prop, context: Context) -> Optional[DeltaUpdate]:
        # always complete updates
        blender_links = self._load(links)
        if blender_links == self._sequence:
            return None

        diff = self.__class__()
        diff.init(None)
        diff._sequence = blender_links
        return DeltaUpdate(diff)
