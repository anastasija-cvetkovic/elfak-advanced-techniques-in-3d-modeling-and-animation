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
import time
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


def _max_is_running() -> bool:
    """Da li 3dsmax.exe već radi (nova instanca bi se predala postojećoj)."""
    if os.name != "nt":
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq 3dsmax.exe", "/NH"],
            capture_output=True, text=True, timeout=15,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return False
    return "3dsmax.exe" in out.lower()


def export_from_max_gui(
    max_exe: str,
    ms_script: str,
    input_max: str,
    output_txt: str,
    timeout: int = 300,
    poll: float = 1.0,
) -> None:
    """
    Konvertuje .max → ASCII tako što pokrene 3ds Max VIDLJIVO i pusti mu skriptu.

    Zašto ovako, a ne headless: education licence ne dozvoljavaju batch režim.
    `3dsmaxbatch.exe` na takvoj licenci izlazi sa kodom -12 pre nego što uopšte
    pročita skriptu — provereno i skriptom od tri reda koja samo upisuje fajl.
    Interaktivni Max na istoj licenci radi normalno.

    Skripta dobija putanje kroz MAX_INPUT / MAX_OUTPUT, sama učita scenu,
    exportuje i zatvori Max. Ovde se samo čeka da se izlazni fajl pojavi.
    """
    if not max_exe or not os.path.exists(max_exe):
        raise FileNotFoundError(f"3ds Max nije pronađen: {max_exe}")
    if not os.path.exists(ms_script):
        raise FileNotFoundError(f"MaxScript nije pronađen: {ms_script}")
    if not os.path.exists(input_max):
        raise FileNotFoundError(f"Ulazni .max fajl ne postoji: {input_max}")

    # Ako Max vec radi, nova instanca preda posao postojecoj i odmah izadje —
    # skripta se nikad ne izvrsi, a mi vidimo samo izlazni kod -12.
    if _max_is_running():
        raise RuntimeError(
            "3ds Max je već pokrenut. Zatvorite ga pa pokušajte ponovo — "
            "nova instanca preda posao postojećoj i konverzija se ne izvrši."
        )

    if os.path.exists(output_txt):
        os.remove(output_txt)

    env = os.environ.copy()
    env["MAX_INPUT"]  = os.path.abspath(input_max)
    env["MAX_OUTPUT"] = os.path.abspath(output_txt)

    proc = subprocess.Popen(
        [max_exe, "-U", "MAXScript", os.path.abspath(ms_script)],
        env=env,
    )

    err_path = str(output_txt) + ".err"
    if os.path.exists(err_path):
        os.remove(err_path)

    deadline = time.time() + timeout
    exited_at = None
    grace = 90.0          # koliko se ceka posle izlaska pokretaca
    while time.time() < deadline:
        # Skripta upisuje izuzetak ovde umesto da ga baci — startup skripta
        # koja baci izuzetak natera Max da prijavi pad instalacije.
        if os.path.exists(err_path):
            with open(err_path, "r", errors="replace") as f:
                msg = f.read().strip()
            raise RuntimeError(f"MAXScript greška:\n{msg}")

        if os.path.exists(output_txt):
            # Fajl se piše u više navrata — sačekaj da mu veličina prestane
            # da raste pre nego što javimo da je gotov.
            size = -1
            while size != os.path.getsize(output_txt):
                size = os.path.getsize(output_txt)
                time.sleep(poll)
            return

        # Pokrenuti proces nije pouzdan pokazatelj: 3dsmax.exe ume da prepusti
        # posao drugom procesu i sam izadje. Zato se posle njegovog izlaska
        # ceka jos malo, pa tek onda odustaje.
        if proc.poll() is not None:
            if exited_at is None:
                exited_at = time.time()
            elif time.time() - exited_at > grace:
                raise RuntimeError(
                    f"3ds Max se zatvorio (kod {proc.returncode}) a izlazni "
                    "fajl nije kreiran. Proverite MAXScript Listener u Max-u."
                )
        time.sleep(poll)

    proc.terminate()
    raise TimeoutError(
        f"3ds Max nije završio konverziju u {timeout}s."
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
    if not max_exe or not os.path.exists(max_exe):
        raise FileNotFoundError(f"3ds Max nije pronađen: {max_exe}")
    # Ova provera je nedostajala, pa je nepostojeći core/export_ascii.ms
    # umesto jasne greške davao zbunjujući "Max završio ali fajl nije kreiran".
    if not os.path.exists(ms_script):
        raise FileNotFoundError(f"MaxScript nije pronađen: {ms_script}")
    if not os.path.exists(input_max):
        raise FileNotFoundError(f"Ulazni .max fajl ne postoji: {input_max}")

    env = os.environ.copy()
    env["MAX_INPUT"]  = str(input_max)
    env["MAX_OUTPUT"] = str(output_txt)

    # 3dsmaxbatch.exe je Autodesk-ov namenski alat za headless pokretanje i
    # jedini pouzdan način. Poziv "3dsmax.exe -q -silent -mxs ..." koji je ovde
    # ranije stajao vraća kod -12 (4294967284) i skripta se nikad ne izvrši.
    from core.max_finder import find_batch_exe

    batch_exe = find_batch_exe(max_exe)
    log_path = str(output_txt) + ".log"

    if batch_exe:
        cmd = [
            batch_exe, str(ms_script),
            "-sceneFile", str(input_max),
            "-mxsString", f"outputPath:{output_txt}",
            "-listenerlog", log_path,
            "-v", "5",
        ]
    else:
        cmd = [max_exe, "-q", "-silent", "-mxs", f'fileIn @"{ms_script}"']

    result = subprocess.run(
        cmd, env=env, timeout=timeout, capture_output=True, text=True,
    )

    def _log_tail(n: int = 25) -> str:
        """
        Poslednji deo Max-ovog log-a — bez toga je greška samo broj.

        Max piše log kao UTF-16; čitanje kao UTF-8 daje tekst razmaknut
        nulama ("0 6 / 0 9 ..."), pa se kodiranje bira po BOM-u.
        """
        try:
            with open(log_path, "rb") as f:
                raw = f.read()
        except OSError:
            return ""

        for bom, enc in ((b"\xff\xfe", "utf-16-le"), (b"\xfe\xff", "utf-16-be")):
            if raw.startswith(bom):
                text = raw[2:].decode(enc, errors="replace")
                break
        else:
            # Bez BOM-a: puno nul-bajtova i dalje znači UTF-16.
            enc = "utf-16-le" if raw.count(b"\x00") > len(raw) // 4 else "utf-8"
            text = raw.decode(enc, errors="replace")

        lines = [l.rstrip() for l in text.splitlines() if l.strip()]
        return "\n".join(lines[-n:])

    if result.returncode != 0:
        detail = _log_tail() or result.stderr or result.stdout or "(bez poruke)"
        raise RuntimeError(
            f"3ds Max greška (kod {result.returncode}):\n{detail}"
        )

    if not os.path.exists(output_txt):
        detail = _log_tail() or "(log prazan)"
        raise RuntimeError(
            "3ds Max je završio ali izlazni fajl nije kreiran.\n"
            f"Poslednje iz Max log-a:\n{detail}"
        )
