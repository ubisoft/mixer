from extra.version_scripts.inject_version import main as inject_version, get_version

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

    parser.add_argument("major", type=int, help="Major version number")
    parser.add_argument("minor", type=int, help="Minor version number")
    parser.add_argument("bugfix", type=int, help="Bugfix version number")
    parser.add_argument("message", type=str, help="Message for version tag")

    args = parser.parse_args()

    tag_name = f"v{args.major}.{args.minor}.{args.bugfix}"

    if tag_name in all_tags:
        print(f"Version tag {tag_name} already defined.")
        exit(1)

    with open("CHANGELOG.md", "r") as f:
        if f"# {args.major}.{args.minor}.{args.bugfix}" not in f.read():
            print(
                f"No section for version {args.major}.{args.minor}.{args.bugfix} found in CHANGELOG.md, add one and commit first."
            )
            exit(1)

    exit(0)

    subprocess.run(["git", "tag", tag_name], check=True)
    inject_version()
    subprocess.run(["git", "commit", "-a", "--amend", "--no-edit"], check=True)
    subprocess.run(["git", "tag", "-f", tag_name, "-m", args.message], check=True)


if __name__ == "__main__":
    main()
