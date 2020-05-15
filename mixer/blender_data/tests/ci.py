import sys
import unittest


def main_ci():
    module = sys.modules[__name__]
    suite = unittest.defaultTestLoader.loadTestsFromModule(module)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if not result.wasSuccessful():
        # exitcode != 0 for gitlab test runner
        raise AssertionError("Tests failed")


if __name__ == "__main__":
    main_ci()
