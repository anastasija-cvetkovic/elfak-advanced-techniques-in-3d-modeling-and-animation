# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec — build: pyinstaller konvertor.spec

Namerno --onedir: PyQt6 + VTK su nekoliko stotina MB, pa bi onefile pri svakom
pokretanju raspakivao sve u temp (desetine sekundi na prazan ekran), a VTK-ovi
native DLL-ovi u tom režimu često i ne prođu učitavanje.
"""

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

APP_NAME = "Max Mesh Decimator"

# VTK se skoro sve uvozi dinamički (pyvista bira module u runtime-u), pa ga
# statička analiza ne vidi — otud collect_submodules umesto nabrajanja.
hiddenimports = [
    *collect_submodules("vtkmodules"),
    *collect_submodules("pyvista"),
    *collect_submodules("pyvistaqt"),
    *collect_submodules("qtpy"),      # pyvistaqt ide na Qt preko qtpy apstrakcije
    # VTK-ovi Python pomoćni moduli — pyvista ih traži, a nisu vtkXxx ekstenzije
    # pa ih hookovi iz pyinstaller-hooks-contrib ne pokrivaju.
    "vtkmodules.all",
    "vtkmodules.util",
    "vtkmodules.util.numpy_support",
    "vtkmodules.util.data_model",
    "vtkmodules.util.execution_model",
    "vtkmodules.numpy_interface",
    "vtkmodules.numpy_interface.dataset_adapter",
    "vtkmodules.qt",
    "vtkmodules.qt.QVTKRenderWindowInteractor",
    "pyfqmr",                    # decimator.py ih bira u runtime-u, po dostupnosti
    "fast_simplification",
    "scipy.spatial",
    "scipy.spatial._ckdtree",
]

datas = [
    ("ui/styles.qss", "ui"),          # main.py — QSS stil
    ("core/export_ascii.ms", "core"),  # main_window.py — skripta za 3ds Max
    *collect_data_files("pyvista"),
]

# Ništa od ovoga aplikacija ne koristi; bez izbacivanja build naraste bez razloga.
#
# Pažnja: `pooch` NE sme ovde. Deluje kao alat za preuzimanje primera, ali ga
# `import pyvista` povlači bezuslovno — bez njega 3D prikaz tiho otkaže.
# Šta pyvista stvarno uvozi proverava se sa:
#     python -c "import sys,pyvista; print('pandas' in sys.modules)"
excludes = [
    "tkinter", "PyQt5", "PySide2", "PySide6",
    "IPython", "jupyter", "notebook", "pytest", "sphinx",
    "trame", "trame_client", "trame_server", "trame_vtk", "trame_vuetify",
    "pandas", "pyarrow",   # ~60 MB arrow DLL-ova; pyvista ih ne uvozi
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX kvari VTK/Qt DLL-ove
    console=False,      # GUI aplikacija — bez konzolnog prozora
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=APP_NAME,
)
