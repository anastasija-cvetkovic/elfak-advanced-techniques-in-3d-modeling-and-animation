"""Entry point. Pokretanje: python main.py"""

import faulthandler
import sys
from datetime import datetime

# Decimacija velikih mesheva ide u podprocesu. Kao .exe nema zasebnog Python
# interpretera koji bi pokrenuo core/decimate_proc.py, pa se isti program
# pokreće ponovo sa ovom zastavicom. Mora pre Qt uvoza — dete ne pravi GUI.
if len(sys.argv) > 1 and sys.argv[1] == "--decimate-worker":
    from core.decimate_proc import run_worker

    sys.exit(run_worker(sys.argv[2:]))

# Provera spakovane verzije bez konzole — vidi core/selftest.py.
if len(sys.argv) > 1 and sys.argv[1] == "--selftest":
    from core.selftest import run

    sys.exit(run())

from PyQt6.QtWidgets import QApplication

from core.paths import resource_path, user_data_dir
from ui.main_window import MainWindow

# Padovi u native kodu (VTK/OpenGL) ne prolaze kroz Python izuzetke, pa
# faulthandler upisuje C stack u crash.log. Fajl ostaje otvoren dok proces živi.
_CRASH_LOG = open(user_data_dir() / "crash.log", "a", buffering=1)
_CRASH_LOG.write(f"\n=== pokretanje {datetime.now():%Y-%m-%d %H:%M:%S} ===\n")
faulthandler.enable(file=_CRASH_LOG, all_threads=True)


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("3DS Max ASCII Konvertor")
    app.setOrganizationName("MaxMeshDecimator")

    # Učitavanje QSS stila
    qss_path = resource_path("ui", "styles.qss")
    if qss_path.exists():
        with open(qss_path, "r", encoding="utf-8") as f:
            app.setStyleSheet(f.read())

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
