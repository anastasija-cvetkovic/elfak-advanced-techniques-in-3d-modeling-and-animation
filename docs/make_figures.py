"""
Generiše slike koje README koristi (docs/img/*.png).

Pokretanje iz korena repozitorijuma:

    python docs/make_figures.py

`TORUS.txt` je u repou; `elisa.txt` i `1.txt` se traže u repou pa u
roditeljskom folderu. Figura bez svog ulaza se preskače.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import numpy as np
import pyvista as pv

from core.converter import load_mesh
from core.decimator import decimate

pv.OFF_SCREEN = True

OUT = REPO / "docs" / "img"
OUT.mkdir(parents=True, exist_ok=True)

# Iste boje kao u aplikaciji (ui/viewer_widget.py)
BG      = "#181818"
ORIG_C  = "#4a9edd"
ORIG_E  = "#1a4a7a"
DEC_C   = "#e07060"
DEC_E   = "#8a3020"
TXT     = "#cfd3dc"


# ── pomoćne ──────────────────────────────────────────────────────────────────

def find_mesh(name: str) -> Path | None:
    for candidate in (REPO / name, REPO.parent / name):
        if candidate.exists():
            return candidate
    return None


def to_polydata(verts: np.ndarray, faces: np.ndarray) -> pv.PolyData:
    cells = np.empty((len(faces), 4), dtype=np.int32)
    cells[:, 0]  = 3
    cells[:, 1:] = faces
    return pv.PolyData(np.ascontiguousarray(verts, dtype=np.float64), cells.ravel())


def error_pct(orig: np.ndarray, dec: np.ndarray) -> float:
    """Hausdorff (orig → dec) normalizovan dijagonalom bbox-a — kao u UI-u."""
    from scipy.spatial import cKDTree
    diag = float(np.linalg.norm(orig.max(axis=0) - orig.min(axis=0)))
    dist, _ = cKDTree(dec).query(orig, k=1, workers=-1)
    return float(dist.max()) / diag * 100


def bbox_growth(orig: np.ndarray, dec: np.ndarray) -> float:
    lo, hi = orig.min(axis=0), orig.max(axis=0)
    return max(float(np.max(dec.max(axis=0) - hi)),
               float(np.max(lo - dec.min(axis=0))), 0.0)


def panel(plotter, verts, faces, title, original=False, zoom=1.45):
    plotter.set_background(BG)
    plotter.add_mesh(
        to_polydata(verts, faces),
        color=ORIG_C if original else DEC_C,
        show_edges=True,
        edge_color=ORIG_E if original else DEC_E,
        line_width=0.6,
    )
    plotter.add_text(title, position="upper_left", font_size=9, color=TXT)
    plotter.enable_lightkit()
    plotter.view_isometric()
    plotter.camera.zoom(zoom)


# ── figure ───────────────────────────────────────────────────────────────────

def levels(mesh: Path, out_name: str, ratios=(1.0, 0.5, 0.3, 0.1)) -> None:
    """Isti model kroz nekoliko jačina decimacije."""
    v0, f0 = load_mesh(str(mesh))
    p = pv.Plotter(shape=(1, len(ratios)), window_size=(1680, 400),
                   off_screen=True, border=False)
    for i, ratio in enumerate(ratios):
        p.subplot(0, i)
        if ratio >= 1.0:
            panel(p, v0, f0,
                  f"ORIGINAL\n{len(v0):,} tacaka  /  {len(f0):,} trouglova",
                  original=True)
        else:
            v, f = decimate(v0, f0, ratio, "auto")
            panel(p, v, f,
                  f"-{int(round((1 - ratio) * 100))}%   greska {error_pct(v0, v):.2f}%\n"
                  f"{len(v):,} tacaka  /  {len(f):,} trouglova")
    p.screenshot(str(OUT / out_name))
    p.close()
    print("ok", out_name)


def methods(mesh: Path, out_name: str, ratio: float = 0.3) -> None:
    """Sve metode na istom cilju."""
    labels = {
        "vtk":     "VTK decimate",
        "vtk_pro": "VTK decimate_pro",
        "pyfqmr":  "pyfqmr (QEM)",
        "cluster": "Vertex clustering",
    }
    v0, f0 = load_mesh(str(mesh))
    target = int(len(f0) * ratio)
    p = pv.Plotter(shape=(1, len(labels)), window_size=(1680, 400),
                   off_screen=True, border=False)
    for i, (method, label) in enumerate(labels.items()):
        p.subplot(0, i)
        v, f = decimate(v0, f0, ratio, method)
        panel(p, v, f,
              f"{label}\n"
              f"{len(f):,} trouglova (cilj {target:,})   greska {error_pct(v0, v):.2f}%\n"
              f"rast bbox-a {bbox_growth(v0, v):.2f}")
    p.screenshot(str(OUT / out_name))
    p.close()
    print("ok", out_name)


def max_export(ours: Path, reference: Path, out_name: str) -> None:
    """Konverzija .max fajla pored zadatog primera istog modela."""
    p = pv.Plotter(shape=(1, 2), window_size=(1400, 500), off_screen=True, border=False)
    for i, (mesh, title, is_orig) in enumerate((
        (ours,      "NASA KONVERZIJA  (1.max -> 1.txt, MAXScript)", False),
        (reference, "ZADATI PRIMER  (elisa.txt)",                   True),
    )):
        v, f = load_mesh(str(mesh))
        p.subplot(0, i)
        panel(p, v, f, f"{title}\n{len(v):,} tacaka  /  {len(f):,} trouglova",
              original=is_orig, zoom=1.5)
    p.screenshot(str(OUT / out_name))
    p.close()
    print("ok", out_name)


def main() -> int:
    torus = find_mesh("TORUS.txt")
    elisa = find_mesh("elisa.txt")
    ours  = find_mesh("1.txt")

    if torus:
        levels(torus, "torus-levels.png")
    else:
        print("preskacem torus-levels.png — nema TORUS.txt")

    if elisa:
        levels(elisa, "elisa-levels.png")
        methods(elisa, "methods-elisa.png")
    else:
        print("preskacem elisa figure — nema elisa.txt")

    if ours and elisa:
        max_export(ours, elisa, "max-export.png")
    else:
        print("preskacem max-export.png — nema 1.txt ili elisa.txt")

    return 0


if __name__ == "__main__":
    sys.exit(main())
