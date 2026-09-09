"""
Sklapa ZIP za isporuku od već napravljenog builda.

Redosled:
    pyinstaller konvertor.spec
    python package_release.py

Rezultat: dist/3DS-Max-ASCII-Konvertor.zip — exe, primeri i uputstvo.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APP_NAME = "3DS Max ASCII Konvertor"
BUILD_DIR = ROOT / "dist" / APP_NAME
STAGE_DIR = ROOT / "dist" / "_paket"
ZIP_BASE = ROOT / "dist" / "3DS-Max-ASCII-Konvertor"

# Primeri se generišu skriptom generate_examples.py i ne idu u repo, pa se traže
# i u roditeljskom folderu gde su ranije generisani.
EXAMPLE_DIRS = [ROOT, ROOT.parent]
EXAMPLES = [
    "TORUS.txt",           # ~500 trouglova — trenutan odziv
    "BOX_SUBDIVIDED.txt",
    "COW.txt",
    "BUNNY.txt",           # ~70k — vidi se razlika u kvalitetu decimacije
    "ARMADILLO.txt",       # ~350k — ide u podproces, UI ostaje živ
]

README = """3DS Max ASCII Konvertor
==================

POKRETANJE
    1. Raspakuj ZIP u folder sa KRATKOM putanjom — na primer C:\\Konvertor
       ili direktno na Desktop. Windows ne ume da ucita biblioteke ako
       putanja predje 260 znakova, pa program tada ostane bez 3D prikaza.

    2. Udji u folder "{app}" i pokreni "{app}.exe".

    Windows ce prvi put prijaviti "Windows protected your PC" jer program
    nije potpisan sertifikatom. Klikni "More info" pa "Run anyway".

STA MOZE
    - Ucitavanje ASCII mesh fajla (.txt) i prikaz u 3D
    - Decimacija — smanjenje broja trouglova, klizacem od 0 do 99%
    - Poredjenje original / decimirani jedan pored drugog
    - Cuvanje rezultata u isti ASCII format
    - Konverzija .max fajla u ASCII (zahteva instaliran 3ds Max)

PROBA BEZ 3DS MAX-a
    U folderu "primeri" su gotovi ASCII fajlovi. Prevuci bilo koji na prozor
    aplikacije ili ga otvori dugmetom "Ucitaj .txt".

    TORUS.txt          ~500 trouglova
    BOX_SUBDIVIDED.txt ~800
    COW.txt            ~6.000
    BUNNY.txt          ~70.000
    ARMADILLO.txt      ~350.000   (decimacija ide u odvojenom procesu)

KONVERZIJA .max FAJLA
    Trazi instaliran 3ds Max. Aplikacija ga sama nadje; ako ne uspe, pitace
    za putanju do 3dsmax.exe. 3ds Max mora biti ZATVOREN pre konverzije —
    nova instanca preda posao postojecoj i konverzija se ne izvrsi.

ASCII FORMAT
    broj_temena
    broj_trouglova
    x y z            (po jedan red za svako teme)
    ...
    i1 i2 i3         (indeksi temena, po jedan red za svaki trougao)
    ...

AKO NESTO NE RADI
    Detalji pada se upisuju u %APPDATA%\\MeshConverter\\crash.log

    Ako se prozor otvori ali 3D prikaz ostane prazan, pokreni u Command
    Promptu (cmd) iz foldera "{app}":

        "{app}.exe" --selftest

    Izvestaj o tome sta nedostaje ostaje u
    %APPDATA%\\MeshConverter\\selftest.txt
""".format(app=APP_NAME)


def main() -> int:
    if not BUILD_DIR.is_dir():
        print(f"Greska: nema builda u {BUILD_DIR}")
        print("Prvo pokreni: pyinstaller konvertor.spec")
        return 1

    if STAGE_DIR.exists():
        shutil.rmtree(STAGE_DIR)
    STAGE_DIR.mkdir(parents=True)

    print(f"Kopiram build -> {STAGE_DIR / APP_NAME}")
    shutil.copytree(BUILD_DIR, STAGE_DIR / APP_NAME)

    examples_dir = STAGE_DIR / "primeri"
    examples_dir.mkdir()
    missing = []
    for name in EXAMPLES:
        src = next((d / name for d in EXAMPLE_DIRS if (d / name).is_file()), None)
        if src is None:
            missing.append(name)
            continue
        shutil.copy2(src, examples_dir / name)
        print(f"  primer  {name}  ({src.stat().st_size / 1024:,.0f} KB)")

    if missing:
        print(f"  nedostaju (pokreni generate_examples.py): {', '.join(missing)}")

    (STAGE_DIR / "PROCITAJ ME.txt").write_text(README, encoding="utf-8")

    print("Pakujem ZIP…")
    if ZIP_BASE.with_suffix(".zip").exists():
        ZIP_BASE.with_suffix(".zip").unlink()
    shutil.make_archive(str(ZIP_BASE), "zip", root_dir=STAGE_DIR)
    shutil.rmtree(STAGE_DIR)

    size_mb = ZIP_BASE.with_suffix(".zip").stat().st_size / 1024 / 1024
    print(f"\nGotovo: {ZIP_BASE.with_suffix('.zip')}  ({size_mb:,.0f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
