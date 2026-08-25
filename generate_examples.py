"""
generate_examples.py
Generiše test ASCII mesh fajlove za aplikaciju.
Pokretanje: python generate_examples.py
"""

import sys
from pathlib import Path

try:
    import pyvista as pv
    import numpy as np
except ImportError:
    print("Greška: pyvista i numpy moraju biti instalirani.")
    sys.exit(1)

OUTPUT_DIR = Path(__file__).parent


def save_ascii(path: Path, mesh: "pv.PolyData") -> int:
    """Čuva PyVista mesh u ASCII formatu koji app čita. Vraća broj trouglova."""
    mesh = mesh.triangulate().clean()
    verts = mesh.points
    faces_raw = mesh.faces.reshape(-1, 4)[:, 1:]  # ukloni leading '3'

    with open(path, "w") as f:
        f.write(f"{len(verts)}\n")
        f.write(f"{len(faces_raw)}\n")
        for v in verts:
            f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for t in faces_raw:
            f.write(f"{t[0]} {t[1]} {t[2]}\n")

    return len(faces_raw)


def generate(name: str, mesh: "pv.PolyData"):
    path = OUTPUT_DIR / f"{name}.txt"
    try:
        n = save_ascii(path, mesh)
        v = mesh.triangulate().clean().n_points
        print(f"  OK  {name}.txt  {v:,} tacaka, {n:,} trouglova")
    except Exception as e:
        print(f"  GRESKA  {name}: {e}")


def try_download(name: str, fn):
    try:
        mesh = fn()
        generate(name, mesh)
    except Exception as e:
        print(f"  PRESKOCENO  {name} (nema interneta): {e}")


# ── Ugrađeni primitivi (uvek rade, bez interneta) ────────────────────────────

print("\n=== Ugradeni primitivi ===")

generate("SFERA",
    pv.Sphere(radius=100, theta_resolution=40, phi_resolution=40))

generate("CILINDAR",
    pv.Cylinder(radius=60, height=200, resolution=40, capping=True))

generate("KONUS",
    pv.Cone(radius=80, height=180, resolution=40, capping=True))

generate("KUPA_ZAOBLJENA",
    pv.Cone(radius=80, height=180, resolution=60, capping=False)
    .smooth(n_iter=80))

generate("MOBIUS",
    pv.ParametricMobius())

generate("BOX_SUBDIVIDED", (
    pv.Box(bounds=(-80, 80, -80, 80, -80, 80))
    .triangulate()
    .subdivide(3)
))

generate("ELIPSA",
    pv.Sphere(radius=1.0, theta_resolution=50, phi_resolution=50)
    .scale([120, 70, 50]))

generate("TORUS_DEBLJI",
    pv.ParametricTorus(ringradius=1.0, crosssectionradius=0.5)
    .scale([100, 100, 100]))

generate("FIGURA_8",
    pv.ParametricFigure8Klein()
    .scale([50, 50, 50]))

# ── Online primeri (zahtevaju internet, preskačemo ako nema) ─────────────────

print("\n=== Online primeri (Stanford) ===")

try_download("BUNNY",     lambda: pv.examples.download_bunny()
             .scale([10000, 10000, 10000], inplace=False))
try_download("DRAGON",    lambda: pv.examples.download_dragon()
             .scale([5000, 5000, 5000], inplace=False))
try_download("ARMADILLO", lambda: pv.examples.download_armadillo())

print("\n=== Online primeri (ostali) ===")

try_download("TEAPOT",    lambda: pv.examples.download_teapot()
             .scale([30, 30, 30], inplace=False))
try_download("COW",       lambda: pv.examples.download_cow()
             .scale([30, 30, 30], inplace=False))

print(f"\nGotovo! Fajlovi su u: {OUTPUT_DIR}")
