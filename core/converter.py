"""
core/converter.py
Učitavanje i čuvanje ASCII mesh fajlova + poziv 3ds Max headless.
"""

import subprocess
import os
from pathlib import Path


def load_mesh(path: str) -> tuple[list, list]:
    """
    Čita ASCII mesh fajl u formatu:
        n_verts
        n_faces
        x y z   (za svaku tačku)
        a b c   (za svaki trougao, 0-based indeksi)
    Vraća (verts, faces) kao liste listi.
    """
    with open(path, "r") as f:
        lines = [ln.strip() for ln in f if ln.strip()]

    idx = 0
    n_verts = int(lines[idx]); idx += 1
    n_faces = int(lines[idx]); idx += 1

    verts = []
    for _ in range(n_verts):
        x, y, z = map(float, lines[idx].split()); idx += 1
        verts.append([x, y, z])

    faces = []
    for _ in range(n_faces):
        a, b, c = map(int, lines[idx].split()); idx += 1
        faces.append([a, b, c])

    return verts, faces


def save_mesh(path: str, verts: list, faces: list) -> None:
    """
    Čuva mesh u ASCII formatu.
    """
    with open(path, "w") as f:
        f.write(f"{len(verts)}\n")
        f.write(f"{len(faces)}\n")
        for v in verts:
            f.write(f"{v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
        for t in faces:
            f.write(f"{t[0]} {t[1]} {t[2]}\n")


def export_from_max(max_exe: str, ms_script: str) -> None:
    """
    Pokreće 3ds Max sa MaxScript-om koji exportuje aktivnu scenu u ASCII.
    Non-blocking — 3ds Max se otvara, korisnik bira gde da sačuva.

    max_exe   — putanja do 3dsmax.exe
    ms_script — putanja do export_ascii.ms
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
