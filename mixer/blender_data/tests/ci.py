from pathlib import Path
import unittest

this_folder = str(Path(__file__).parent)


def main_ci():
    suite = unittest.defaultTestLoader.discover(this_folder)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        # exitcode != 0 for gitlab test runner
        raise AssertionError("Tests failed")


if __name__ == "__main__":
    main_ci()
    pass
