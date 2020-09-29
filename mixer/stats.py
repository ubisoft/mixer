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
This module defines utilities for statistics computation and export.
"""

import time
import os
import json
import logging
import copy
import tempfile
from pathlib import Path
import functools

from mixer.os_utils import getuser

logger = logging.getLogger(__name__)


class StatsTimer:
    """
    Class to measure execution time of a code section. Can be used as a context manager.
    """

    def __init__(self, share_data, key, log=None):
        assert share_data.current_statistics

        if log is None:
            if share_data.current_stats_timer is None:
                log = False
            else:
                log = share_data.current_stats_timer.log

        self.share_data = share_data
        if not share_data.current_stats_timer:
            parent_stats_dict = share_data.current_statistics
        else:
            parent_stats_dict = share_data.current_stats_timer.stats_dict

        if log:
            logger.debug(key)
        if "children" not in parent_stats_dict:
            parent_stats_dict["children"] = {}
        if key not in parent_stats_dict["children"]:
            parent_stats_dict["children"][key] = {"time": 0, "max_time": 0, "hit_count": 0}
        self.key = key
        self.stats_dict = parent_stats_dict["children"][key]
        self.log = log

    def __enter__(self):
        self.start = time.time()
        self.last_checkpoint_time = self.start
        self.previous_stats_timer = self.share_data.current_stats_timer
        self.share_data.current_stats_timer = self
        return self

    def __exit__(self, *args):
        t = time.time() - self.start
        self.stats_dict["time"] += t
        self.stats_dict["max_time"] = max(t, self.stats_dict["max_time"])
        self.stats_dict["hit_count"] += 1
        self.share_data.current_stats_timer = self.previous_stats_timer
        if self.log:
            logger.debug(f"{self.key} done. Time = %f", t)
        return

    def reset_checkpoint(self):
        self.last_checkpoint_time = time.time()

    def checkpoint(self, key, log=None):
        with StatsTimer(self.share_data, key, log) as t:
            t.start = self.last_checkpoint_time  # Change start to measure time since previous checkpoint
        self.last_checkpoint_time = time.time()

    def child(self, key, log=None):
        return StatsTimer(self.share_data, key, log)


def get_stats_directory():
    if "MIXER_USER_STATS_DIR" in os.environ:
        username = getuser()
        base_shared_path = Path(os.environ["MIXER_USER_STATS_DIR"])
        if os.path.exists(base_shared_path):
            return os.path.join(os.fspath(base_shared_path), username)
        logger.error(
            f"MIXER_USER_STATS_DIR env var set to {base_shared_path}, but directory does not exists. Falling back to default location."
        )
    return os.path.join(os.fspath(tempfile.gettempdir()), "mixer")


def get_stats_filename(run_id, session_id):
    return f"mixer_stats_{run_id}_{session_id}.json"


def compute_final_statistics(stats_dict):
    new_dict = copy.deepcopy(stats_dict)

    def recursive_compute(d, parent, root):
        d["mean_time"] = d["time"] / d["hit_count"] if d["hit_count"] > 0 else 0
        if parent:
            d["parent_percent_time"] = 100 * d["time"] / parent["time"] if parent["time"] > 0 else 0
        if root:
            d["global_percent_time"] = 100 * d["time"] / root["time"] if root["time"] > 0 else 0
        if "children" in d:
            for _child, child_dict in d["children"].items():
                recursive_compute(child_dict, d, root)

    for _, d in new_dict["children"].items():
        recursive_compute(d, None, d)
    return new_dict


def save_statistics(stats_dict, stats_directory):
    Path(stats_directory).mkdir(parents=True, exist_ok=True)
    file = os.path.join(stats_directory, stats_dict["statsfile"])
    with open(file, "w") as f:
        json.dump(compute_final_statistics(stats_dict), f, indent=2)


def stats_timer(share_data, log=None):
    """
    A decorator to measure and store execution time of a function with respec to
    the call stack.
    """

    def inner_decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if share_data.current_statistics is None:
                return func(*args, **kwargs)

            with StatsTimer(share_data, func.__name__, log):
                return func(*args, **kwargs)

        return wrapper

    return inner_decorator
