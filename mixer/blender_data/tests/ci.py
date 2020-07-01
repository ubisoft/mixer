import os
from pathlib import Path
import unittest

import xmlrunner

from mixer.blender_data import blenddata

this_folder = str(Path(__file__).parent)


def main_ci():
    blenddata.register()

    os.makedirs("logs/tests", exist_ok=True)
    with open("logs/tests/blender_data.xml", "wb") as output:
        suite = unittest.defaultTestLoader.discover(this_folder)
        runner = xmlrunner.XMLTestRunner(verbosity=2, output=output)
        result = runner.run(suite)
        if not result.wasSuccessful():
            # exitcode != 0 for gitlab test runner
            raise AssertionError("Tests failed")

    blenddata.unregister()


if __name__ == "__main__":
    main_ci()
    pass
