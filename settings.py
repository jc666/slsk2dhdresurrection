"""Saved settings and Windows folder helpers."""
import json
import os
import uuid
from pathlib import Path

import sys

APP_DIR = Path(__file__).resolve().parent
if getattr(sys, "frozen", False):  # running as the .exe: keep data in AppData, not next to the exe
    DATA_DIR = Path(os.environ.get("APPDATA") or Path.home()) / "SLSK 2D HD"
else:
    DATA_DIR = APP_DIR / "data"
SETTINGS_FILE = DATA_DIR / "settings.json"


def resource_path(name):
    """Path of a bundled file (fonts, icon), both from source and inside the .exe."""
    base = Path(getattr(sys, "_MEIPASS", APP_DIR))
    return str(base / name)

DEFAULTS = {
    "slsk_user": "",
    "slsk_pass": "",
    "save_root": "",
    "max_active": 10,
    "quality": "best",
    "lang": "es",
    "theme": "maligna",
}


def load():
    data = dict(DEFAULTS)
    try:
        data.update(json.loads(SETTINGS_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return data


def save(data):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")


def documents_folder():
    """The real Documents folder (follows OneDrive redirection on Windows)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                            ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

            u = uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7")  # FOLDERID_Documents
            guid = GUID(u.time_low, u.time_mid, u.time_hi_version,
                        (ctypes.c_ubyte * 8)(*u.bytes[8:]))
            ptr = ctypes.c_wchar_p()
            res = ctypes.windll.shell32.SHGetKnownFolderPath(
                ctypes.byref(guid), 0, None, ctypes.byref(ptr))
            if res == 0 and ptr.value:
                path = ptr.value
                ctypes.windll.ole32.CoTaskMemFree(ptr)
                return path
        except Exception:
            pass
    return str(Path.home() / "Documents")
