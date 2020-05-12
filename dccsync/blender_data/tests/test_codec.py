import json
import unittest

import bpy
from bpy import data as D  # noqa
from bpy import types as T  # noqa
from dccsync.blender_data.json_codec import Codec
from dccsync.blender_data.proxy import (
    BpyBlendProxy,
    BpyIDProxy,
)
from dccsync.blender_data.tests.utils import register_bl_equals, test_blend_file

from dccsync.blender_data.filter import default_context


class TestCodec(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=test_blend_file)
        self.proxy = BpyBlendProxy()
        self.proxy.load(default_context)
        register_bl_equals(self, default_context)

    def test_object(self):
        bl_cam = D.cameras["Camera_0"]
        cam = self.proxy._data["cameras"]._data["Camera_0"]
        self.assertIsInstance(cam, BpyIDProxy)
        codec = Codec()
        s = codec.encode(cam)
        o = json.loads(s)
        print(json.dumps(o, sort_keys=True, indent=4))
        o2 = codec.decode(s)
        self.assertEqual(cam, o2)
        o2.save(bl_cam)
        pass

    def test_cam(self):
        cam_sent = D.cameras["Camera_0"]
        cam_proxy_sent = self.proxy._data["cameras"]._data["Camera_0"]
        self.assertIsInstance(cam_proxy_sent, BpyIDProxy)
        codec = Codec()
        message = codec.encode(cam_proxy_sent)
        # transmit
        cam_proxy_received = codec.decode(message)
        cam_proxy_received._data["name"] = "cam_received"
        cam_received = D.cameras.new("cam_received")
        cam_proxy_received.save(cam_received)
        self.assertEqual(cam_sent, cam_received)
        pass
