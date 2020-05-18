from pathlib import Path
import unittest
from mixer.blender_data.blenddata import create_uuids

this_folder = str(Path(__file__).parent)


def main_ci():
    create_uuids()
    suite = unittest.defaultTestLoader.discover(this_folder)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        # exitcode != 0 for gitlab test runner
        raise AssertionError("Tests failed")


if __name__ == "__main__":
    main_ci()
    pass
