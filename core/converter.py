"""
core/converter.py
Učitavanje i čuvanje ASCII mesh fajlova + poziv 3ds Max headless.

Format:
    n_verts
    n_faces
    x y z   (n_verts redova)
    a b c   (n_faces redova, 0-based indeksi)

Sav I/O radi na numpy nizovima radi brzine (10-100× brže od Python for petlji
za velike mesh-eve).
"""

from __future__ import annotations
import subprocess
import os
import numpy as np


def load_mesh(path: str) -> tuple[np.ndarray, np.ndarray]:
    """
    Čita ASCII mesh fajl i vraća:
        verts — np.ndarray oblika (N, 3), dtype float64
        faces — np.ndarray oblika (M, 3), dtype int32
    """
    with open(path, "r") as f:
        n_verts = int(f.readline())
        n_faces = int(f.readline())
        verts = np.loadtxt(f, dtype=np.float64, max_rows=n_verts)
        faces = np.loadtxt(f, dtype=np.int32,   max_rows=n_faces)

    # np.loadtxt vraća 1D niz kad je samo jedan red — normalizuj u 2D
    if verts.ndim == 1:
        verts = verts.reshape(-1, 3)
    if faces.ndim == 1:
        faces = faces.reshape(-1, 3)

    return verts, faces


def save_mesh(path: str, verts: np.ndarray, faces: np.ndarray) -> None:
    """
    Čuva mesh u ASCII formatu. Prima np.ndarray (ili bilo šta što se može
    konvertovati u ndarray).
    """
    verts = np.asarray(verts, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int32)

    with open(path, "w") as f:
        f.write(f"{len(verts)}\n")
        f.write(f"{len(faces)}\n")
        np.savetxt(f, verts, fmt="%.6f")
        np.savetxt(f, faces, fmt="%d")


def export_from_max(max_exe: str, ms_script: str) -> None:
    """
    Pokreće 3ds Max sa MaxScript-om koji exportuje aktivnu scenu u ASCII.
    Non-blocking — 3ds Max se otvara, korisnik bira gde da sačuva.
    """
    if not os.path.exists(max_exe):
        raise FileNotFoundError(f"3ds Max nije pronađen: {max_exe}")
    if not os.path.exists(ms_script):
        raise FileNotFoundError(f"MaxScript nije pronađen: {ms_script}")

    subprocess.Popen(
        [max_exe, "-U", "MAXScript", str(ms_script)],
        creationflags=subprocess.DETACHED_PROCESS
        if os.name == "nt" else 0,
    )


def export_from_max_headless(
    max_exe: str,
    ms_script: str,
    input_max: str,
    output_txt: str,
    timeout: int = 120,
) -> None:
    """
    Pokreće 3ds Max headless (bez prozora) i konvertuje .max → ASCII.
    Blokira dok konverzija ne završi ili ne istekne timeout.

    Varijable okoline koje MaxScript čita:
        MAX_INPUT  — putanja do .max fajla
        MAX_OUTPUT — putanja gde se čuva ASCII rezultat
    """
    if not os.path.exists(max_exe):
        raise FileNotFoundError(f"3ds Max nije pronađen: {max_exe}")

    env = os.environ.copy()
    env["MAX_INPUT"]  = str(input_max)
    env["MAX_OUTPUT"] = str(output_txt)

    result = subprocess.run(
        [max_exe, "-q", "-silent", "-mxs", f'fileIn @"{ms_script}"'],
        env=env,
        timeout=timeout,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"3ds Max greška (kod {result.returncode}):\n{result.stderr}"
        )

    if not os.path.exists(output_txt):
        raise RuntimeError(
            "3ds Max završio ali izlazni fajl nije kreiran. "
            "Proverite export_ascii.ms i putanje."
        )
