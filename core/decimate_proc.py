"""
core/decimate_proc.py
Decimacija velikih mesheva u odvojenom procesu.

Zašto proces, a ne samo thread
------------------------------
VTK, pyfqmr i fast_simplification su native biblioteke koje ne otpuštaju GIL
dok rade. Dok decimacija traje u QThread-u, main thread ne izvršava Python —
pa QTimer koji animira traku napretka ne dobija tick-ove. Izmereno na
`DRAGON.txt` (435 545 tačaka / 871 306 trouglova, ratio 0.5, metoda "auto"),
sa QTimer-om na 16 ms kao u SweepBar-u:

    tick-ova            224 od očekivanih 726   (30.8%)
    najveći prekid      4512 ms
    prekida > 100 ms    8

Dakle traka stoji po nekoliko sekundi — tačno ono što se vidi kao "loader koči".
U odvojenom procesu GIL main thread-a niko ne drži, pa animacija ide normalno.

Drugi razlog je bezbednost: VTK nije thread-safe. `decimator._try_vtk` pravi
vtkPolyData i vrti vtkQuadricDecimation u worker thread-u, dok main thread u
isto vreme renderuje dva živa vtkRenderWindow-a (a korisnik, pošto traka stoji,
najverovatnije i vrti model da proveri da li je app živ). Podproces ta dva
VTK pipeline-a razdvaja u potpunosti.

Cena
----
Start Pythona sa potrebnim importima je izmeren na ~1.8 s:

    numpy                    0.31 s
    numpy + pyvista          1.12 s
    numpy + pyvista + scipy  1.77 s

Na DRAGON-u je to 1.8 s na 12 s posla — prihvatljivo. Na meshevima iz zadatka
(TORUS, elisa — reda hiljadu trouglova) decimacija traje desetinke sekunde, pa
bi podproces bio višestruko skuplji od samog posla i ništa ne bi dobio: takav
posao ne uspeva ni da zadrži GIL dovoljno dugo da se primeti. Zato prag ispod
odlučuje, a ne fiksno pravilo.

Razmena podataka ide preko .npy fajlova u temp direktorijumu, ne preko pipe-a:
nizovi su reda 20 MB, a np.save/np.load na njima traje milisekunde.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

# Prag je izabran po izmerenom trajanju decimacije u tekućem procesu ("auto",
# ratio 0.5) — to je istovremeno i dužina zamrznutog UI-ja:
#
#     TORUS         480 f     0.05 s
#     elisa       2 574 f     0.09 s
#     COW         5 804 f     0.05 s
#     BUNNY      69 451 f     0.72 s
#     ARMADILLO 345 944 f     4.5  s
#     DRAGON    871 306 f    11.6  s
#
# Dakle ~13 µs po trouglu. Do oko sekunde zamrznuta traka se praktično ne vidi
# i ne vredi trostruko usporiti posao zbog nje; iznad par sekundi izgleda kao
# da je app stao. 150 000 trouglova je ta granica (~2 s).
PROC_MIN_FACES = 150_000

# Gornja granica čekanja: 60 s minimum, pa linearno sa veličinom mesha, da
# zaglavljen podproces ne drži UI zauvek. Na DRAGON-u (12 s posla) prag je 60 s.
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

    Ako podproces padne iz bilo kog razloga (nema python.exe, greška u
    startovanju), vraća se na izvršavanje u tekućem procesu: UI će tada
    zamrznuti, ali aplikacija radi. Greška same decimacije se propušta dalje.
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
        # Bez ovoga bi svaki poziv blicnuo crni konzolni prozor kada je app
        # pokrenut preko pythonw.exe.
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
