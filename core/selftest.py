"""
Provera spakovane verzije: `"Max Mesh Decimator.exe" --selftest`.

GUI build nema konzolu, pa se izveštaj upisuje i u %APPDATA%\\MaxMeshDecimator\\
selftest.txt. Bez ovoga se ne vidi zašto 3D prikaz ćutke izostane — uvoz VTK-a
puca u native sloju, a viewer_widget ga hvata i prelazi na fallback panele.
"""

from __future__ import annotations

import sys
import traceback
from datetime import datetime

import os

from core.paths import clean_env, is_frozen, resource_path, user_data_dir

# Redosled je namerno od najniže zavisnosti naviše — prvi neuspeh je uzrok,
# ostali su posledica.
_MODULES = [
    "numpy",
    "scipy.spatial",
    "pyfqmr",
    "fast_simplification",
    "qtpy",
    "PyQt6.QtWidgets",
    "vtkmodules.vtkCommonCore",
    "vtkmodules.vtkRenderingOpenGL2",
    "vtkmodules.qt.QVTKRenderWindowInteractor",
    "pyvista",
    "pyvistaqt",
]

_RESOURCES = [
    ("ui", "styles.qss"),
    ("core", "export_ascii.ms"),
]


def _render_check() -> str:
    """
    Renderuje pravi mesh offscreen i meri koliko piksela nije pozadina.

    Uvoz modula prolazi i kad VTK-u nedostaje OpenGL sloj — tek render pokaže
    radi li grafika stvarno. Ide bez GUI-ja, pa se može pokrenuti bilo gde.
    """
    try:
        import numpy as np
        import pyvista as pv

        mesh = pv.Sphere(theta_resolution=24, phi_resolution=24)
        pl = pv.Plotter(off_screen=True, window_size=(200, 200))
        pl.set_background("#181818")
        pl.add_mesh(mesh, color="#4a9edd")
        img = np.asarray(pl.screenshot(return_img=True))
        pl.close()

        # Pozadina je ujednačena; svaki piksel koji odstupa je nacrtan mesh.
        bg = img[0, 0]
        drawn = int(np.abs(img.astype(int) - bg.astype(int)).sum(axis=2).astype(bool).sum())
        total = img.shape[0] * img.shape[1]
        pct = 100.0 * drawn / total

        if drawn == 0:
            return f"PAO  render — slika {img.shape} je prazna (sve pozadina {tuple(bg)})"
        return f"OK   render — {drawn}/{total} piksela nacrtano ({pct:.0f}%)"
    except Exception:
        return "PAO  render\n" + traceback.format_exc()


def _report() -> str:
    lines = [
        f"selftest {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"frozen: {is_frozen()}",
        f"sys.executable: {sys.executable}",
        "",
        "--- resursi ---",
    ]

    for parts in _RESOURCES:
        path = resource_path(*parts)
        lines.append(f"{'OK  ' if path.exists() else 'NEMA'} {path}")

    lines += ["", "--- moduli ---"]
    for name in _MODULES:
        try:
            __import__(name)
            lines.append(f"OK   {name}")
        except Exception:
            lines.append(f"PAO  {name}")
            lines.append(traceback.format_exc())

    lines += ["", "--- okruzenje za 3ds Max ---"]
    lines += _env_check()

    lines += ["", "--- grafika ---", _render_check()]
    return "\n".join(lines)


def _env_check() -> list[str]:
    """
    Šta bi 3ds Max nasledio od nas.

    Bez čišćenja nasledi naš QT_PLUGIN_PATH i _internal na početku PATH-a, pa
    startuje sa našim Qt-om umesto svojim i padne — vidi core/paths.clean_env.
    """
    raw, clean = os.environ, clean_env()
    out = []

    for name in ("QT_PLUGIN_PATH", "QML2_IMPORT_PATH", "QT_QPA_PLATFORM_PLUGIN_PATH"):
        before = "postavljeno" if name in raw else "nema"
        after = "PROPUSTENO" if name in clean else "uklonjeno"
        out.append(f"{'OK  ' if name not in clean else 'PAO '} {name}: {before} -> {after}")

    head_raw = raw.get("PATH", "").split(os.pathsep)[:1]
    head_clean = clean.get("PATH", "").split(os.pathsep)[:1]
    bundle = getattr(sys, "_MEIPASS", "")
    leaked = bool(bundle) and any(bundle in p for p in clean.get("PATH", "").split(os.pathsep))
    out.append(f"{'PAO ' if leaked else 'OK  '} PATH[0]: {head_raw} -> {head_clean}")

    return out


def run() -> int:
    text = _report()
    out = user_data_dir() / "selftest.txt"
    out.write_text(text, encoding="utf-8")

    # U windowed buildu stdout ne postoji ako roditelj nije dao pipe.
    try:
        print(text)
    except Exception:
        pass

    return 0 if "PAO " not in text and "NEMA " not in text else 1
