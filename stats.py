import time
import os
import json
import logging
import copy
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__package__)


class StatsTimer():
    def __init__(self, parent_stats_dict, key, log=False):
        if log:
            logger.info(key)
        if not "children" in parent_stats_dict:
            parent_stats_dict["children"] = {}
        if not key in parent_stats_dict["children"]:
            parent_stats_dict["children"][key] = {
                "time": 0,
                "max_time": 0,
                "hit_count": 0
            }
        self.key = key
        self.stats_dict = parent_stats_dict["children"][key]
        self.log = log

    def __enter__(self):
        self.start = time.time()
        self.last_checkpoint_time = self.start
        return self

    def __exit__(self, *args):
        t = time.time() - self.start
        self.stats_dict["time"] += t
        self.stats_dict["max_time"] = max(t, self.stats_dict["max_time"])
        self.stats_dict["hit_count"] += 1
        return

    def reset_checkpoint(self):
        self.last_checkpoint_time = time.time()

    def checkpoint(self, key, log=None):
        if log == None:
            log = self.log
        t = StatsTimer(self.stats_dict, key, log)
        t.start = self.last_checkpoint_time
        t.__exit__()
        self.last_checkpoint_time = time.time()

    def child(self, key, log=None):
        if log == None:
            log = self.log
        return StatsTimer(self.stats_dict, key, log)


def get_stats_directory():
    # todo Improve this -> should be set by a launcher in an env var, should handle linux paths
    username = os.getlogin()
    base_shared_path = Path("//ubisoft.org/mtrstudio/World/UAS/Tech/uas_data/dcc_sync/users_statistics/")
    if os.path.exists(base_shared_path):
        return os.path.join(os.fspath(base_shared_path), username)
    user_dir_path = Path("C:/tmp/dccsync_stats/")
    return os.fspath(user_dir_path)


def get_stats_filename(run_id, session_id):
    return f"dccsync_stats_{run_id}_{session_id}.json"


def compute_final_statistics(stats_dict):
    new_dict = copy.deepcopy(stats_dict)

    def recursive_compute(d, parent, root):
        d["mean_time"] = d["time"] / d["hit_count"] if d["hit_count"] > 0 else 0
        if parent:
            d["parent_percent_time"] = 100 * d["time"] / parent["time"] if parent["time"] > 0 else 0
        if root:
            d["global_percent_time"] = 100 * d["time"] / root["time"] if root["time"] > 0 else 0
        if "children" in d:
            for child, child_dict in d["children"].items():
                recursive_compute(child_dict, d, root)

    for _, d in new_dict["children"].items():
        recursive_compute(d, None, d)
    return new_dict


def save_statistics(stats_dict, stats_directory):
    Path(stats_directory).mkdir(parents=True, exist_ok=True)
    file = os.path.join(stats_directory, stats_dict["statsfile"])
    with open(file, "w") as f:
        json.dump(compute_final_statistics(stats_dict), f, indent=2)
