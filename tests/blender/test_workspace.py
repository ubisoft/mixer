"""Tests for shared_folders"""
import unittest
from parameterized import parameterized_class

from tests import files_folder
from tests.blender.blender_testcase import BlenderTestCase
from tests.mixer_testcase import BlenderDesc


class TestCase(BlenderTestCase):
    def setUp(self):
        sender_blendfile = files_folder() / "empty.blend"
        receiver_blendfile = files_folder() / "empty.blend"
        sender = BlenderDesc(load_file=sender_blendfile, wait_for_debugger=False)
        receiver = BlenderDesc(load_file=receiver_blendfile, wait_for_debugger=False)
        blenderdescs = [sender, receiver]
        super().setUp(blenderdescs=blenderdescs)


def _get_class_name(cls, num, params_dict):
    # By default the generated class named includes either the "name"
    # parameter (if present), or the first string value. This example shows
    # multiple parameters being included in the generated class name:
    return "%s_%s_%s" % (
        cls.__name__,
        num,
        params_dict["name"],
    )


@parameterized_class(
    [
        {
            "ws0": files_folder() / "shared_folder" / "ws0_0",
            "ws1": files_folder() / "shared_folder" / "ws0_0",
            "name": "Same",
        },
        {
            "ws0": files_folder() / "shared_folder" / "ws0_0",
            "ws1": files_folder() / "shared_folder" / "ws1_0",
            "name": "Different",
        },
    ],
    class_name_func=_get_class_name,
)
class TestImageOneFolder(TestCase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def setUp(self):
        self.shared_folders = [
            [str(self.ws0)],
            [str(self.ws1)],
        ]
        super().setUp()

    def test_create_one_file(self):
        path_a = str(self.ws0 / "image_a.png")
        create = f"""
import bpy
bpy.data.images.load(r"{path_a}")
"""
        self.send_string(create)
        self.end_test()

    def test_create_two_files(self):
        path_a = str(self.ws0 / "image_a.png")
        path_b = str(self.ws0 / "image_b.png")
        create = f"""
import bpy
bpy.data.images.load(r"{path_a}")
bpy.data.images.load(r"{path_b}")
"""
        self.send_string(create)
        self.end_test()


@parameterized_class(
    [
        {
            "ws0": [files_folder() / "shared_folder" / "ws0_0", files_folder() / "shared_folder" / "ws0_1"],
            "ws1": [files_folder() / "shared_folder" / "ws1_0", files_folder() / "shared_folder" / "ws1_1"],
            "name": "",
        },
    ],
    class_name_func=_get_class_name,
)
class TestImageTwoFolders(TestCase):
    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

    def setUp(self):
        self.shared_folders = [
            [str(ws) for ws in self.ws0],
            [str(ws) for ws in self.ws1],
        ]
        super().setUp()

    def test_create(self):
        path_a = str(self.ws0[0] / "image_a.png")
        path_c = str(self.ws0[1] / "image_c.png")
        create = f"""
import bpy
bpy.data.images.load(r"{path_a}")
bpy.data.images.load(r"{path_c}")
"""
        self.send_string(create)
        self.end_test()


if __name__ == "__main__":
    unittest.main()
