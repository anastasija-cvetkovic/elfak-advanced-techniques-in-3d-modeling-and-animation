"""
main.py — entry point
Pokretanje: python main.py
"""

import faulthandler
import sys
from datetime import datetime
from pathlib import Path

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from ui.main_window import MainWindow

# Padovi u native kodu (VTK/OpenGL, decimacione biblioteke) ne prolaze kroz
# Python izuzetke — proces samo nestane, bez traga. faulthandler upisuje C
# stack u crash.log, pa se posle pada vidi u kojoj biblioteci je puklo.
# Fajl mora da ostane otvoren dok proces živi, zato modul-level referenca.
_CRASH_LOG = open(Path(__file__).parent / "crash.log", "a", buffering=1)
_CRASH_LOG.write(f"\n=== pokretanje {datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
faulthandler.enable(file=_CRASH_LOG, all_threads=True)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("3DS Max ASCII Konvertor")
    app.setOrganizationName("MeshConverter")

    # Učitavanje QSS stila
    qss_path = Path(__file__).parent / "ui" / "styles.qss"
    if qss_path.exists():
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
