# GPLv3 License
#
# Copyright (C) 2020 Ubisoft
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

"""
This module contains useful functions that could be reused in other add-ons.
"""


def convert_version_str_to_tupple(version_str):
    """Convert a string formated like "1.23.48" to a tupple such as (1,23,48)"""
    version_splitted = version_str.split(".")
    return (int(version_splitted[0]), int(version_splitted[1]), int(version_splitted[2]))
