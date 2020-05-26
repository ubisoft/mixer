from pathlib import Path
import unittest
from mixer.blender_data import blenddata

this_folder = str(Path(__file__).parent)


def main_ci():
    blenddata.register()
    suite = unittest.defaultTestLoader.discover(this_folder)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        # exitcode != 0 for gitlab test runner
        raise AssertionError("Tests failed")
    blenddata.unregister()


if __name__ == "__main__":
    main_ci()
    pass
