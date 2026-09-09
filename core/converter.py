"""Učitavanje i čuvanje ASCII mesh fajlova + poziv 3ds Max-a."""

from __future__ import annotations
import subprocess
import os
import time
import numpy as np

from core.paths import clean_env


def load_mesh(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Čita ASCII mesh fajl i vraća verts (N, 3) float64 i faces (M, 3) int32."""
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
    """Čuva mesh u ASCII formatu."""
    verts = np.asarray(verts, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int32)

    with open(path, "w") as f:
        f.write(f"{len(verts)}\n")
        f.write(f"{len(faces)}\n")
        np.savetxt(f, verts, fmt="%.6f")
        np.savetxt(f, faces, fmt="%d")


def export_from_max(max_exe: str, ms_script: str) -> None:
    """Otvara 3ds Max sa MaxScript-om koji exportuje aktivnu scenu. Non-blocking."""
    if not os.path.exists(max_exe):
        raise FileNotFoundError(f"3ds Max nije pronađen: {max_exe}")
    if not os.path.exists(ms_script):
        raise FileNotFoundError(f"MaxScript nije pronađen: {ms_script}")

    subprocess.Popen(
        [max_exe, "-U", "MAXScript", str(ms_script)],
        env=clean_env(),
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
    Konvertuje .max → ASCII tako što pokrene 3ds Max vidljivo i pusti mu skriptu.

    Education licence ne dozvoljavaju batch režim, pa headless varijanta ne radi.
    Skripta putanje dobija kroz MAX_INPUT / MAX_OUTPUT; ovde se čeka izlazni fajl.
    """
    if not max_exe or not os.path.exists(max_exe):
        raise FileNotFoundError(f"3ds Max nije pronađen: {max_exe}")
    if not os.path.exists(ms_script):
        raise FileNotFoundError(f"MaxScript nije pronađen: {ms_script}")
    if not os.path.exists(input_max):
        raise FileNotFoundError(f"Ulazni .max fajl ne postoji: {input_max}")

    if _max_is_running():
        raise RuntimeError(
            "3ds Max je već pokrenut. Zatvorite ga pa pokušajte ponovo — "
            "nova instanca preda posao postojećoj i konverzija se ne izvrši."
        )

    if os.path.exists(output_txt):
        os.remove(output_txt)

    env = clean_env()
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
    grace = 90.0          # koliko se čeka posle izlaska pokretača
    while time.time() < deadline:
        if os.path.exists(err_path):
            with open(err_path, "r", errors="replace") as f:
                msg = f.read().strip()
            raise RuntimeError(f"MAXScript greška:\n{msg}")

        if os.path.exists(output_txt):
            # Fajl se piše u više navrata — čekaj da mu veličina prestane da raste.
            size = -1
            while size != os.path.getsize(output_txt):
                size = os.path.getsize(output_txt)
                time.sleep(poll)
            return

        # 3dsmax.exe ume da prepusti posao drugom procesu i sam izađe, pa se
        # posle njegovog izlaska čeka još malo.
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
    Konvertuje .max → ASCII preko headless Max-a. Blokira do kraja ili timeout-a.

    MaxScript čita putanje iz MAX_INPUT i MAX_OUTPUT.
    """
    if not max_exe or not os.path.exists(max_exe):
        raise FileNotFoundError(f"3ds Max nije pronađen: {max_exe}")
    if not os.path.exists(ms_script):
        raise FileNotFoundError(f"MaxScript nije pronađen: {ms_script}")
    if not os.path.exists(input_max):
        raise FileNotFoundError(f"Ulazni .max fajl ne postoji: {input_max}")

    env = clean_env()
    env["MAX_INPUT"]  = str(input_max)
    env["MAX_OUTPUT"] = str(output_txt)

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
        """Poslednji deo Max-ovog log-a; kodiranje se bira po BOM-u (Max piše UTF-16)."""
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
