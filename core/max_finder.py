"""
core/max_finder.py
Automatsko pronalaženje instalacije 3ds Max na Windows-u.
"""

from __future__ import annotations
import glob
import os


# Standardne lokacije instalacije
_PATTERNS = [
    r"C:\Program Files\Autodesk\3ds Max *\3dsmax.exe",
    r"C:\Program Files (x86)\Autodesk\3ds Max *\3dsmax.exe",
    r"D:\Program Files\Autodesk\3ds Max *\3dsmax.exe",
    r"D:\Autodesk\3ds Max *\3dsmax.exe",
]


def find_max_exe() -> str | None:
    """
    Pretražuje standardne lokacije i vraća putanju do najnovijeg
    3dsmax.exe, ili None ako nije pronađen.
    """
    candidates = []
    for pattern in _PATTERNS:
        found = glob.glob(pattern)
        candidates.extend(found)

    if not candidates:
        return None

    # Sortiranjem po imenu foldera dobijamo najnoviju verziju
    candidates.sort()
    return candidates[-1]


def find_max_exe_or_raise() -> str:
    """
    Isto kao find_max_exe() ali baca grešku ako nije pronađen.
    """
    path = find_max_exe()
    if path is None:
        raise FileNotFoundError(
            "3ds Max nije pronađen na standardnim lokacijama.\n"
            "Podesite putanju ručno u Podešavanjima."
        )
    return path


def max_version_from_path(exe_path: str) -> str:
    """
    Izvlači naziv verzije iz putanje.
    Npr. 'C:\\...\\3ds Max 2025\\3dsmax.exe' → '2025'
    """
    parts = os.path.normpath(exe_path).split(os.sep)
    for part in reversed(parts):
        if part.lower().startswith("3ds max"):
            return part.replace("3ds Max", "").strip()
    return "Nepoznata"
