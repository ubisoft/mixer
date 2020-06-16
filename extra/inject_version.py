import os
import subprocess


def get_version():
    cp = subprocess.run(["git", "describe", "--tags", "--dirty", "--match=v*"], stdout=subprocess.PIPE, check=True,)
    version = str(cp.stdout, encoding="utf8").strip()

    version_tokens = version.split("-")
    if len(version_tokens) == 1:
        return version_tokens[0]
    return version_tokens[0] + "+" + "-".join(version_tokens[1:])


def main():
    version = get_version()

    pyproject_file = "pyproject.toml"
    new_projectfile_str = ""
    tool_poetry_found = False
    with open(pyproject_file, "r") as fp:
        for line in fp.readlines():
            if line.startswith("[tool.poetry]"):
                tool_poetry_found = True
            if tool_poetry_found and line.startswith("version = "):
                new_projectfile_str += f'version = "{version}"\n'
                tool_poetry_found = False
            else:
                new_projectfile_str += f"{line}"
    with open(pyproject_file, "w") as fp:
        fp.write(new_projectfile_str)

    version_numbers = [int(n) for n in version[1:].split("+")[0].split("-")[0].split(".")]
    if "+" in version:
        commit_version_str = version[1:].split("+")[1].split("-")[0]
        if commit_version_str != "dirty":
            version_numbers += [int(commit_version_str)]

    init_file = os.path.join("mixer", "__init__.py")
    new_init_file_str = ""
    bl_info_state = 0
    with open(init_file, "r") as fp:
        for line in fp.readlines():
            if bl_info_state == 0 and "bl_info" in line:
                bl_info_state = 1
            if bl_info_state == 1 and '"version"' in line:
                offset = line.find("(")
                line = line[:offset] + str(tuple(version_numbers))
                new_init_file_str += f"{line},\n"
                bl_info_state = 2
            else:
                new_init_file_str += f"{line}"

    with open(init_file, "w") as fp:
        fp.write(new_init_file_str)


if __name__ == "__main__":
    main()
