"""
Putanje do resursa i korisničkih podataka.

Iz izvornog koda sve leži u korenu projekta. Iz PyInstaller .exe-a resursi se
raspakuju u privremeni sys._MEIPASS koji nestaje po izlasku iz programa, pa sve
što treba da preživi gašenje ide u %APPDATA%.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_APP_DIR = "MaxMeshDecimator"


def is_frozen() -> bool:
    """Da li program radi kao spakovani .exe."""
    return getattr(sys, "frozen", False)


def resource_path(*parts: str) -> Path:
    """
    Fajl koji je deo aplikacije — styles.qss, export_ascii.ms.

    Putanje se zadaju relativno u odnosu na koren projekta:
        resource_path("ui", "styles.qss")
    """
    base = getattr(sys, "_MEIPASS", None)
    root = Path(base) if base else Path(__file__).resolve().parent.parent
    return root.joinpath(*parts)


# PyInstaller-ov runtime hook ih upisuje u okruženje procesa da bi Qt našao
# spakovane pluginove. Nasleđuje ih svaki podproces — a 3ds Max je i sam Qt
# aplikacija, pa bi sa ovima startovao sa našim Qt-om i pao pri pokretanju.
_PYI_ENV_VARS = (
    "QT_PLUGIN_PATH",
    "QML2_IMPORT_PATH",
    "QT_QPA_PLATFORM_PLUGIN_PATH",
    "_PYI_APPLICATION_HOME_DIR",
    "_PYI_ARCHIVE_FILE",
    "_PYI_PARENT_PROCESS_LEVEL",
    "_MEIPASS2",
)


def clean_env() -> dict[str, str]:
    """
    Okruženje za pokretanje tuđih programa — bez tragova PyInstaller-a.

    Za pokretanje same ove aplikacije (podproces decimacije) NE koristiti: njoj
    te promenljive trebaju i sama ih postavlja.
    """
    env = dict(os.environ)
    if not is_frozen():
        return env

    for name in _PYI_ENV_VARS:
        env.pop(name, None)

    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        # Na PATH-u završi i sam _internal (PyInstaller-ov hook) i _internal\
        # PyQt6\Qt6\bin (dodaje ga PyQt6 pri uvozu). Izbacuje se sve unutar
        # bundle-a — inače bi tuđi program odatle povukao naše Qt/VTK DLL-ove.
        root = os.path.normcase(os.path.normpath(bundle))
        parts = [
            p for p in env.get("PATH", "").split(os.pathsep)
            if p and not _inside(p, root)
        ]
        env["PATH"] = os.pathsep.join(parts)

    return env


def _inside(path: str, root: str) -> bool:
    """Da li je `path` sam `root` ili nešto ispod njega. `root` je normalizovan."""
    norm = os.path.normcase(os.path.normpath(path))
    return norm == root or norm.startswith(root + os.sep)


def user_data_dir() -> Path:
    """
    Folder za podatke koji nadživljavaju pokretanje — settings.json, crash.log.

    Kreira se ako ne postoji.
    """
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    path = Path(base) / _APP_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path
