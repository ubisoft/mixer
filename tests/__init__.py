from pathlib import Path


def files_folder() -> Path:
    return Path(__file__).parent / "files"
