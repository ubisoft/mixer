import argparse
from sys import stderr


def get_release_description(version):
    release_description = ""
    found = False
    with open("CHANGELOG.md", "r") as f:
        for line in f.readlines():
            if not found and line.startswith(f"# {version}"):
                found = True
            elif found and line.startswith("# "):
                break
            if found:
                release_description += f"{line}"
    return release_description


def main():
    parser = argparse.ArgumentParser(description="Extract description of a release from CHANGELOG.md")
    parser.add_argument("version", help="Version number without 'v' prefix.")
    args = parser.parse_args()

    release_description = get_release_description(args.version)
    if release_description == "":
        print(f"Error: No release description found for version {args.version}", file=stderr)
        exit(1)
    print(release_description)


if __name__ == "__main__":
    main()
