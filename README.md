# 3DS Max → ASCII Konvertor

Desktop aplikacija za rad sa custom ASCII triangle mesh formatom
sa interaktivnom decimacijom i 3D prikazom (pre / posle).

## Instalacija

```bash
pip install -r requirements.txt
```

## Pokretanje

```bash
python main.py
```

Na macOS-u sa conda okruženjem može biti potrebno da se postavi Qt plugin
putanja (poznati sukob PyQt6 wheel-a i conda-inog Qt-a):

```bash
QT_QPA_PLATFORM_PLUGIN_PATH="$(python -c 'import PyQt6, os; print(os.path.join(os.path.dirname(PyQt6.__file__), "Qt6", "plugins", "platforms"))')" python main.py
```

## Struktura projekta

```
elfak-.../
├── main.py                  ← entry point
├── core/
│   ├── converter.py         ← load/save ASCII (+ pomoćne funkcije za 3ds Max)
│   ├── decimator.py         ← chain fallback: pyfqmr → QEM → vertex clustering
│   ├── max_finder.py        ← pronalaženje 3dsmax.exe (Windows)
│   └── mesh_model.py        ← centralno stanje aplikacije (MVC)
├── ui/
│   ├── main_window.py       ← glavni prozor (PyQt6)
│   ├── viewer_widget.py     ← 3D prikaz (PyVista)
│   └── styles.qss           ← tamna tema
├── generate_examples.py     ← test ASCII fajlovi (sfera, torus, bunny…)
└── requirements.txt
```

## Korišćenje

1. **Učitaj ASCII fajl** — prevuci `.txt` u zonu ili klikni za dijalog
2. **Podesi decimaciju** — slajder = % smanjenja trouglova; izaberi metodu
3. **Pokreni** — klik na *Konvertuj i prikaži*
4. **Pregledaj** — original (levo) vs decimirani (desno) u 3D
5. **Sačuvaj** — ASCII `.txt` ili standardni `.obj`

## ASCII format

```
240          ← broj tačaka (vertices)
480          ← broj trouglova (faces)
x y z        ← koordinate svake tačke
...
a b c        ← indeksi temena svakog trougla (0-based)
...
```

## Generisanje test fajlova

```bash
python generate_examples.py
```

Kreira nekoliko ASCII mesheva u root folderu (sfera, cilindar, konus,
Möbius traka, elipsoid, torus, Figure-8 Klein…) plus opciono Stanford
Bunny/Dragon/Armadillo, Utah Teapot, Cow ako ima internet.

## 3ds Max integracija

**Status:** planirano. `core/converter.py` sadrži pomoćne funkcije
(`export_from_max`, `export_from_max_headless`) i `core/max_finder.py`
detektuje instalaciju, ali MaxScript export skript i UI dugme još nisu
priključeni. Trenutno aplikacija radi samo sa ASCII `.txt` ulazom.

## Metode decimacije

- **Quadric Edge Collapse** (`pyfqmr`) — najbolji odnos kvalitet/brzina,
  čuva ivice i konture. *Preporučeno.*
- **Vertex Clustering** — deli prostor u voksele i zamenjuje tačke
  centroidima. Vrlo brzo, gruba aproksimacija; fallback bez dodatnih
  zavisnosti.

## Pakovanje u .exe (Windows)

```bash
pyinstaller --onefile --windowed --name MeshConverter \
  --add-data "ui/styles.qss;ui" \
  main.py
```

Rezultat: `dist/MeshConverter.exe`
