# 3DS Max → ASCII Konvertor

Desktop aplikacija za konverziju `.max` fajlova u custom ASCII triangle mesh format
sa interaktivnom decimacijom i 3D prikazom.

## Instalacija

```bash
pip install -r requirements.txt
```

## Pokretanje

```bash
python main.py
```

## Struktura projekta

```
max_ascii_converter/
├── main.py                  ← entry point
├── core/
│   ├── converter.py         ← load/save ASCII + 3ds Max poziv
│   ├── decimator.py         ← pyfqmr → QEM → cluster chain
│   ├── max_finder.py        ← pronalaženje 3dsmax.exe
│   └── mesh_model.py        ← centralno stanje aplikacije
├── ui/
│   ├── main_window.py       ← glavni prozor (PyQt6)
│   ├── viewer_widget.py     ← 3D prikaz (PyVista)
│   └── styles.qss           ← tamna tema
├── scripts/
│   └── export_ascii.ms      ← MaxScript za 3ds Max export
└── requirements.txt
```

## Korišćenje

1. **Učitaj ASCII fajl** — kliknite "Učitaj ASCII fajl (.txt)"
2. **Podesite decimaciju** — izaberite metodu i procenat smanjenja
3. **Pokrenite** — kliknite "Pokreni decimaciju"
4. **Pregledajte** — original (levo) vs decimirani (desno) u 3D
5. **Sačuvajte** — kliknite "Sačuvaj ASCII fajl"

## ASCII format

```
240          ← broj tačaka
480          ← broj trouglova
x y z        ← koordinate svake tačke
...
a b c        ← indeksi temena svakog trougla (0-based)
...
```

## Pakovanje u .exe

```bash
pyinstaller --onefile --windowed --name MeshConverter \
  --add-data "scripts/export_ascii.ms;scripts" \
  --add-data "ui/styles.qss;ui" \
  main.py
```

Rezultat: `dist/MeshConverter.exe`
