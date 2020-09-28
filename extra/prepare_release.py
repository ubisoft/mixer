# MIT License
#
# Copyright (c) 2020 Ubisoft
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

from extra.inject_version import main as inject_version, get_version
from extra.get_release_description import get_release_description

import argparse
import re
import subprocess


def main():
    cp = subprocess.run(["git", "tag", "-l", "v*"], stdout=subprocess.PIPE, check=True)
    tags_str = str(cp.stdout, encoding="utf8").strip()
    all_tags = set(tags_str.split("\n")) if tags_str != "" else set()

    if len(all_tags) > 0:
        version = get_version()
        if "dirty" in version:
            print("Please commit or discard/stash your changes before running this script.")
            exit(1)

        print(f"Current version: {version}")

    parser = argparse.ArgumentParser(description="Set a new version number for the project.")

    # See https://semver.org/ in mind
    parser.add_argument("major", type=int, help="Major version number")
    parser.add_argument("minor", type=int, help="Minor version number")
    parser.add_argument("bugfix", type=int, help="Bugfix version number")
    parser.add_argument("--prerelease", type=str, default="", help="Prerelease (optional)")
    parser.add_argument("--build", type=str, default="", help="Build suffix (optional)")
    parser.add_argument("--skip-tests", action="store_true", help="If specified, skip tests for the tagged commit.")

    args = parser.parse_args()

    pattern = "^[0-9A-Za-z-]+$"

    tag_name = f"v{args.major}.{args.minor}.{args.bugfix}"
    if args.prerelease:
        if not re.match(pattern, args.prerelease):
            print(f'--prerelease argument "{args.prerelease}" does not match pattern {pattern}')
            exit(1)
        tag_name += f"-{args.prerelease}"
    if args.build:
        if not re.match(pattern, args.build):
            print(f'--build argument "{args.build}" does not match pattern {pattern}')
            exit(1)
        tag_name += f"+{args.build}"

    version_string = tag_name[1:]

    if tag_name in all_tags:
        print(f"Version tag {tag_name} already defined.")
        exit(1)

    release_description = get_release_description(version_string)
    if release_description == "":
        print(f"No section for version {version_string} in CHANGELOG.md, add one and commit first.")
        exit(1)

    subprocess.run(["git", "tag", tag_name], check=True)
    inject_version()

    cp = subprocess.run(["git", "status", "-s", "-uno"], stdout=subprocess.PIPE, check=True)
    if str(cp.stdout, encoding="utf8").strip() != "":
        # Only if something has changed according to git status:
        commit_message = f"Update version to {version_string}"
        if args.skip_tests:
            commit_message += " [skip-tests]"
        subprocess.run(["git", "commit", "-a", "-m", commit_message], check=True)
        subprocess.run(["git", "tag", "-f", tag_name, "-m", f"Version {version_string}"], check=True)

    version = get_version()
    print(f"New version: {version}")


if __name__ == "__main__":
    main()
