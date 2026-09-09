"""
Pronalaženje instalacije 3ds Max.

Redosled: korisnikov ručni izbor → ADSK_3DSMAX_* promenljive → registry →
PATH → uobičajene instalacione putanje.
"""

from __future__ import annotations
import glob
import json
import os
import re
import shutil

_EXE = "3dsmax.exe"
_BATCH = "3dsmaxbatch.exe"

_PATTERNS = [
    r"C:\Program Files\Autodesk\3ds Max *\3dsmax.exe",
    r"C:\Program Files (x86)\Autodesk\3ds Max *\3dsmax.exe",
    r"D:\Program Files\Autodesk\3ds Max *\3dsmax.exe",
    r"D:\Autodesk\3ds Max *\3dsmax.exe",
]

_REG_KEYS = [
    r"SOFTWARE\Autodesk\3dsMax",
    r"SOFTWARE\WOW6432Node\Autodesk\3dsMax",
]


# ── trajno pamćenje korisnikovog izbora ───────────────────────────────────────

def _config_path() -> str:
    base = os.environ.get("APPDATA") or os.path.expanduser("~/.config")
    return os.path.join(base, "MaxMeshDecimator", "settings.json")


def get_saved_max_exe() -> str | None:
    """Putanja koju je korisnik ranije ručno izabrao, ako još postoji."""
    try:
        with open(_config_path(), "r", encoding="utf-8") as f:
            path = json.load(f).get("max_exe")
    except (OSError, ValueError):
        return None
    return path if path and os.path.exists(path) else None


def save_max_exe(path: str) -> None:
    """Pamti korisnikov izbor da se ne bira ponovo pri svakom pokretanju."""
    cfg = _config_path()
    os.makedirs(os.path.dirname(cfg), exist_ok=True)

    data = {}
    try:
        with open(cfg, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        pass

    data["max_exe"] = path
    with open(cfg, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


# ── pojedinačni načini detekcije ──────────────────────────────────────────────

def _version_key(text: str) -> tuple:
    """'29.0' -> (29, 0); sortiranje po verziji, ne po stringu."""
    return tuple(int(c) if c.isdigit() else 0
                 for c in re.split(r"[.\-_]", text))


def _from_env() -> list[tuple[tuple, str]]:
    """Autodesk postavlja ADSK_3DSMAX_x64_<godina> na instalacioni folder."""
    found = []
    for name, value in os.environ.items():
        if not name.upper().startswith("ADSK_3DSMAX"):
            continue
        exe = os.path.join(value, _EXE)
        if os.path.exists(exe):
            year = re.findall(r"(\d{4})", name)
            found.append((_version_key(year[-1] if year else "0"), exe))
    return found


def _from_registry() -> list[tuple[tuple, str]]:
    if os.name != "nt":
        return []
    try:
        import winreg
    except ImportError:
        return []

    found = []
    for key_path in _REG_KEYS:
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as root:
                for i in range(winreg.QueryInfoKey(root)[0]):
                    try:
                        ver = winreg.EnumKey(root, i)
                        with winreg.OpenKey(root, ver) as sub:
                            install_dir, _ = winreg.QueryValueEx(sub, "Installdir")
                        exe = os.path.join(install_dir, _EXE)
                        if os.path.exists(exe):
                            found.append((_version_key(ver), exe))
                    except OSError:
                        continue
        except OSError:
            continue
    return found


def _from_path() -> list[tuple[tuple, str]]:
    exe = shutil.which(_EXE)
    return [((0,), exe)] if exe else []


def _from_patterns() -> list[tuple[tuple, str]]:
    found = []
    for pattern in _PATTERNS:
        for exe in glob.glob(pattern):
            year = re.findall(r"(\d{4})", exe)
            found.append((_version_key(year[-1] if year else "0"), exe))
    return found


# ── javni API ─────────────────────────────────────────────────────────────────

def find_max_exe() -> str | None:
    """Putanja do 3dsmax.exe, ili None. Ručni izbor ima prednost nad detekcijom."""
    saved = get_saved_max_exe()
    if saved:
        return saved

    for method in (_from_env, _from_registry, _from_path, _from_patterns):
        found = method()
        if found:
            found.sort()
            return found[-1][1]      # najnovija verzija
    return None


def find_all_max_exe() -> list[str]:
    """Sve pronađene instalacije, bez duplikata — za izbor kad ih ima više."""
    seen, result = set(), []
    for method in (_from_env, _from_registry, _from_path, _from_patterns):
        for _, exe in sorted(method()):
            key = os.path.normcase(os.path.abspath(exe))
            if key not in seen:
                seen.add(key)
                result.append(exe)
    return result


def find_batch_exe(max_exe: str) -> str | None:
    """3dsmaxbatch.exe iz istog foldera — Autodesk-ov alat za headless pokretanje."""
    if not max_exe:
        return None
    batch = os.path.join(os.path.dirname(max_exe), _BATCH)
    return batch if os.path.exists(batch) else None


def find_max_exe_or_raise() -> str:
    path = find_max_exe()
    if path is None:
        raise FileNotFoundError(
            "3ds Max nije pronađen automatski.\n"
            "Izaberite 3dsmax.exe ručno."
        )
    return path


def max_version_from_path(exe_path: str) -> str:
    """'...\\3ds Max 2027\\3dsmax.exe' → '2027'"""
    year = re.findall(r"(\d{4})", exe_path or "")
    if year:
        return year[-1]
    for part in reversed(os.path.normpath(exe_path or "").split(os.sep)):
        if part.lower().startswith("3ds max"):
            return part[7:].strip() or "nepoznata"
    return "nepoznata"
