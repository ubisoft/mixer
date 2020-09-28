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

import os
from pathlib import Path


def main():
    license_headers = {}
    for license in ["MIT", "GPL"]:
        with open(os.path.join(Path(__file__).parent, f"{license}_LICENSE_HEADER.txt")) as f:
            license_headers[license] = []
            for line in f.readlines():
                license_headers[license].append(line)

    for subdir, _dirs, files in os.walk("mixer"):
        for filename in files:
            filepath = Path(subdir) / filename

            if filename.endswith(".py"):
                if subdir.startswith(os.path.join("mixer", "broadcaster")):
                    inject_license_header_in_python_src_file(filepath, "MIT", license_headers["MIT"])
                else:
                    inject_license_header_in_python_src_file(filepath, "GPL", license_headers["GPL"])


def inject_license_header_in_python_src_file(filepath, license_name: str, header: str):
    file_content: str = ""
    with open(filepath, "r") as f:
        line = f.readline()
        if line != "" and f"# {header[0]}".startswith(line):
            print(f"{filepath} already contains license {license_name}.")
            return
        file_content += line
        for line in f.readlines():
            file_content += line

    with open(filepath, "w") as f:
        print(f"Adding license {license_name} to {filepath}")

        for line in header:
            if line != "\n":
                f.write(f"# {line}")
            else:
                f.write("#\n")  # avoid trailing whitespace
        f.write("\n\n")
        f.write(file_content)


if __name__ == "__main__":
    main()
