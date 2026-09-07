"""
Decimacija velikih mesheva u odvojenom procesu.

VTK, pyfqmr i fast_simplification su native biblioteke koje ne otpuštaju GIL,
pa u QThread-u zamrznu UI; uz to VTK nije thread-safe, a main thread u isto
vreme renderuje dva živa vtkRenderWindow-a. Razmena podataka ide preko .npy
fajlova u temp direktorijumu.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

# Ispod ovog praga posao traje do ~2 s, pa se zamrznuti UI praktično ne vidi,
# a pokretanje podprocesa (~1,8 s) bilo bi skuplje od samog posla.
PROC_MIN_FACES = 150_000

# Gornja granica čekanja: 60 s minimum, pa linearno sa veličinom mesha.
_TIMEOUT_BASE_S      = 60.0
_TIMEOUT_FACES_PER_S = 20_000.0


def should_use_process(faces: np.ndarray) -> bool:
    return len(faces) >= PROC_MIN_FACES


def decimate_auto(
    verts: np.ndarray,
    faces: np.ndarray,
    ratio: float,
    method: str = "auto",
) -> tuple[np.ndarray, np.ndarray]:
    """
    Decimira mesh — u podprocesu ako je velik, inače na mestu.

    Ako se podproces ne može pokrenuti, vraća se na izvršavanje u tekućem
    procesu. Greška same decimacije se propušta dalje.
    """
    if not should_use_process(faces):
        from core.decimator import decimate
        return decimate(verts, faces, ratio, method)

    try:
        return _decimate_in_process(verts, faces, ratio, method)
    except _SubprocessUnavailable:
        from core.decimator import decimate
        return decimate(verts, faces, ratio, method)


class _SubprocessUnavailable(RuntimeError):
    """Podproces se nije mogao pokrenuti — razlikuje se od greške decimacije."""


def _decimate_in_process(
    verts: np.ndarray, faces: np.ndarray, ratio: float, method: str
) -> tuple[np.ndarray, np.ndarray]:
    timeout = _TIMEOUT_BASE_S + len(faces) / _TIMEOUT_FACES_PER_S

    with tempfile.TemporaryDirectory(prefix="mesh_decim_") as tmp:
        d = Path(tmp)
        in_v, in_f   = d / "in_v.npy",  d / "in_f.npy"
        out_v, out_f = d / "out_v.npy", d / "out_f.npy"
        np.save(in_v, np.ascontiguousarray(verts, dtype=np.float64))
        np.save(in_f, np.ascontiguousarray(faces, dtype=np.int32))

        cmd = [
            sys.executable, "-u", str(Path(__file__).resolve()),
            str(in_v), str(in_f), str(ratio), method, str(out_v), str(out_f),
        ]
        # Bez ovoga bi svaki poziv blicnuo konzolni prozor pod pythonw.exe.
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=timeout, creationflags=flags,
            )
        except FileNotFoundError as e:
            raise _SubprocessUnavailable(str(e)) from e
        except OSError as e:
            raise _SubprocessUnavailable(str(e)) from e
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Decimacija je prekinuta posle {timeout:.0f}s — mesh je "
                f"prevelik ili se metoda zaglavila."
            ) from None

        if proc.returncode != 0 or not (out_v.exists() and out_f.exists()):
            raise RuntimeError(_child_error(proc))

        return np.load(out_v), np.load(out_f)


def _child_error(proc: subprocess.CompletedProcess) -> str:
    """Poslednje smislene linije stderr-a podprocesa, za status bar."""
    lines = [l.strip() for l in (proc.stderr or "").splitlines() if l.strip()]
    tail = " | ".join(lines[-3:]) if lines else "bez detalja"
    return f"decimacija u podprocesu nije uspela (izlaz {proc.returncode}): {tail}"


# ── Podproces ─────────────────────────────────────────────────────────────────

def _main(argv: list[str]) -> int:
    in_v, in_f, ratio, method, out_v, out_f = argv
    # Pokreće se kao skripta, pa koren projekta nije na sys.path-u.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from core.decimator import decimate

    v, f = np.load(in_v), np.load(in_f)
    nv, nf = decimate(v, f, float(ratio), method)
    np.save(out_v, np.ascontiguousarray(nv, dtype=np.float64))
    np.save(out_f, np.ascontiguousarray(nf, dtype=np.int32))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
