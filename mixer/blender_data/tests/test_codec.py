import unittest

import bpy
from bpy import data as D  # noqa
from bpy import types as T  # noqa
from mixer.blender_data.json_codec import Codec
from mixer.blender_data.proxy import (
    BpyBlendProxy,
    BpyIDProxy,
    BpyIDRefProxy,
)
from mixer.blender_data.tests.utils import register_bl_equals, test_blend_file

from mixer.blender_data.filter import test_context


class TestCodec(unittest.TestCase):
    def setUp(self):
        bpy.ops.wm.open_mainfile(filepath=test_blend_file)
        self.proxy = BpyBlendProxy()
        register_bl_equals(self, test_context)

    def test_camera(self):
        # test_codec.TestCodec.test_camera

        # prepare camera
        transmit_name = "transmit_camera"
        cam_sent = D.cameras["Camera_0"]

        cam_sent.dof.focus_object = D.objects["Cube"]

        # load into proxy
        self.proxy.load(test_context)

        # patch the name so that it does not get mixed up as we restore later in the same scene
        cam_proxy_sent = self.proxy.data("cameras").data("Camera_0")
        cam_proxy_sent._data["name"] = transmit_name
        self.assertIsInstance(cam_proxy_sent, BpyIDProxy)

        # encode
        codec = Codec()
        message = codec.encode(cam_proxy_sent)

        #
        # transmit
        #

        # create
        cam_received = D.cameras.new(transmit_name)

        # decode into proxy
        cam_proxy_received = codec.decode(message)

        focus_object_proxy = cam_proxy_received.data("dof").data("focus_object")
        self.assertIsInstance(focus_object_proxy, BpyIDRefProxy)
        self.assertEqual(focus_object_proxy.collection(), "objects")
        self.assertEqual(focus_object_proxy.key(), "Cube")

        # save into blender
        cam_proxy_received.save(D.cameras, transmit_name)
        self.assertEqual(cam_sent, cam_received)
        pass

    # TODO Generic test with randomized samples of all IDs ?
