# Headless stub for MakeHuman's getpath module.
# The original version searches platform-specific user home directories for
# MakeHuman's data folder. Here we resolve everything relative to the
# MAKEHUMAN_DATA_PATH environment variable set in seam_avatar's config.

import os

def _data_path():
    path = os.environ.get("MAKEHUMAN_DATA_PATH", "")
    if not path:
        raise RuntimeError(
            "MAKEHUMAN_DATA_PATH environment variable is not set. "
            "Set it to the absolute path of the MakeHuman data directory."
        )
    return path

def getSysDataPath(subPath=""):
    base = _data_path()
    if subPath:
        return os.path.normpath(os.path.join(base, subPath)).replace("\\", "/")
    return os.path.normpath(base).replace("\\", "/")

def canonicalPath(path):
    return os.path.normpath(os.path.realpath(path)).replace("\\", "/")
