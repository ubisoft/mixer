import unittest

import bpy
from bpy import data as D  # noqa
from bpy import types as T  # noqa
from mixer.blender_data.json_codec import Codec
from mixer.blender_data.proxy import BpyBlendProxy
from mixer.blender_data.tests.utils import register_bl_equals

from mixer.blender_data.filter import safe_context
from mixer.blender_data.diff import BpyBlendDiff


class TestWorld(unittest.TestCase):
    def setUp(self):
        self.proxy = BpyBlendProxy()
        self.diff = BpyBlendDiff()
        register_bl_equals(self, safe_context)

    def test_world(self):
        world = bpy.data.worlds[0]
        world.use_nodes = True
        self.assertGreaterEqual(len(world.node_tree.nodes), 2)

        self.diff.diff(self.proxy, safe_context)
        sent_ids = {}
        sent_ids.update({("worlds", world.name): world})

        updates, _ = self.proxy.update(self.diff, safe_context)
        # avoid clash on restore
        world.name = world.name + "_bak"

        codec = Codec()
        for update in updates:
            key = (update.collection_name(), update.collection_key())
            sent_id = sent_ids.get(key)
            if sent_id is None:
                continue

            encoded = codec.encode(update)
            # sender side
            #######################
            # receiver side
            decoded = codec.decode(encoded)
            created = self.proxy.update_one(decoded)
            self.assertEqual(created, sent_id)
