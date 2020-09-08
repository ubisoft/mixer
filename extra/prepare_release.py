from extra.inject_version import main as inject_version, get_version
from extra.get_release_description import get_release_description

import argparse
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

    tag_name = f"v{args.major}.{args.minor}.{args.bugfix}"
    if args.prerelease:
        tag_name += f"-{args.prerelease}"
    if args.build:
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
