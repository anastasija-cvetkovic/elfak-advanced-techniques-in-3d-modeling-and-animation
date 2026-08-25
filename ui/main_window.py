"""
ui/main_window.py
Layout identičan screenshotu:
  - Tamna tema
  - Levo: naslov app, upload zona (drag&drop), fajl kartica, slider, metoda, prikaz, dugmad
  - Desno: 3D prikaz sa toolbar-om (Orbita / Ceo ekran)
  - Desno dole: statistike (Originalne tačke, Nakon optimizacije, Trouglovi, Greška)
"""

from __future__ import annotations
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QSlider, QRadioButton, QButtonGroup,
    QFileDialog, QProgressBar, QStatusBar,
    QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSettings, QMimeData, QUrl
from PyQt6.QtGui import QAction, QDragEnterEvent, QDropEvent

from core.mesh_model import MeshModel
from core.max_finder import find_max_exe
from ui.viewer_widget import MeshViewer


# ── Pozadinski thread za decimaciju ──────────────────────────────────────────

class DecimateWorker(QThread):
    finished = pyqtSignal(float)
    error    = pyqtSignal(str)

    def __init__(self, model, ratio, method):
        super().__init__()
        self.model = model; self.ratio = ratio; self.method = method

    def run(self):
        t0 = time.perf_counter()
        try:
            self.model.run_decimate(self.ratio, self.method)
            self.finished.emit(time.perf_counter() - t0)
        except Exception as e:
            self.error.emit(str(e))


# ── Upload zona sa drag & drop podrškom ──────────────────────────────────────

class UploadZone(QFrame):
    file_dropped = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("uploadZone")
        self.setFixedHeight(110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAcceptDrops(True)

        lv = QVBoxLayout(self)
        lv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lv.setSpacing(4)

        icon = QLabel("⬆")
        icon.setStyleSheet("font-size:26px; color:#4a5080; background:transparent;")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        txt = QLabel("Prevucite .max fajl ovde")
        txt.setStyleSheet("font-size:14px; font-weight:500; color:#ccc; background:transparent;")
        txt.setAlignment(Qt.AlignmentFlag.AlignCenter)

        sub = QLabel("ili kliknite za pregled")
        sub.setStyleSheet("font-size:12px; color:#555; background:transparent;")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lv.addWidget(icon); lv.addWidget(txt); lv.addWidget(sub)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if e.mimeData().hasUrls():
            urls = e.mimeData().urls()
            if any(u.toLocalFile().lower().endswith(('.txt', '.max')) for u in urls):
                self.setStyleSheet(self.styleSheet() + "border-color:#4a7adf;")
                e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self.setStyleSheet(self.objectName())

    def dropEvent(self, e: QDropEvent):
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith(('.txt', '.max')):
                self.file_dropped.emit(path)
                break
        e.acceptProposedAction()

    def mousePressEvent(self, e):
        self.file_dropped.emit("")


# ── Pomoćni widgeti ───────────────────────────────────────────────────────────

def _sep(parent=None):
    f = QFrame(parent)
    f.setFrameShape(QFrame.Shape.HLine)
    f.setFixedHeight(1)
    f.setStyleSheet("background:#2e3140; border:none;")
    return f


def _section_label(text: str, parent=None):
    l = QLabel(text, parent)
    l.setObjectName("sectionLabel")
    return l


class StatBlock(QWidget):
    """Blok statistike: mala labela gore, velika vrednost dole + tag promene."""
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        lv = QVBoxLayout(self)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(2)

        self._lbl = QLabel(label)
        self._lbl.setStyleSheet(
            "font-size:10px; color:#555; letter-spacing:1px; "
            "background:transparent; font-weight:500;")

        row = QHBoxLayout(); row.setSpacing(6)
        self._val = QLabel("—")
        self._val.setStyleSheet(
            "font-size:20px; font-weight:500; color:#e0e0e0; background:transparent;")
        self._tag = QLabel("")
        self._tag.setStyleSheet(
            "font-size:11px; color:#4caf82; background:transparent;")
        self._sub = QLabel("")
        self._sub.setStyleSheet(
            "font-size:10px; color:#555; background:transparent;")
        row.addWidget(self._val); row.addWidget(self._tag)
        row.addWidget(self._sub); row.addStretch()

        lv.addWidget(self._lbl); lv.addLayout(row)

    def set_value(self, val, tag="", sub=""):
        self._val.setText(str(val) if val is not None else "—")
        self._tag.setText(tag)
        self._sub.setText(sub)


# ── Glavni prozor ─────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.model     = MeshModel()
        self.worker    = None
        self.max_exe   = find_max_exe()
        self.settings  = QSettings("MeshConverter", "App")
        self._fullscreen_viewer = False

        self.setWindowTitle("3DS Max → ASCII Konvertor")
        self.resize(1140, 700)
        self.setMinimumSize(900, 560)

        self._build_ui()
        self._build_statusbar()
        self._refresh()

    def _build_ui(self):
        root = QWidget()
        root.setStyleSheet("background:#1a1c23;")
        self.setCentralWidget(root)

        hv = QHBoxLayout(root)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.setSpacing(0)

        self._left_panel = self._build_left()
        hv.addWidget(self._left_panel)
        hv.addWidget(self._build_right(), stretch=1)

    # ── LEVI PANEL ────────────────────────────────────────────────────
    def _build_left(self):
        w = QWidget()
        w.setFixedWidth(300)
        w.setStyleSheet("background:#1a1c23; border-right:1px solid #2e3140;")

        lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)

        # Naslov
        header = QWidget()
        header.setStyleSheet("background:#252830; border-bottom:1px solid #2e3140;")
        hh = QHBoxLayout(header)
        hh.setContentsMargins(16, 14, 16, 14); hh.setSpacing(10)
        icon = QLabel("⬡")
        icon.setStyleSheet("font-size:20px; color:#4a7adf; background:transparent;")
        titles = QVBoxLayout()
        t1 = QLabel("3DS Max → ASCII konvertor")
        t1.setObjectName("appTitle")
        t2 = QLabel("Učitajte .max fajl, podesite optimizaciju i eksportujte")
        t2.setObjectName("appSubtitle")
        t2.setWordWrap(True)
        titles.addWidget(t1); titles.addWidget(t2)
        hh.addWidget(icon); hh.addLayout(titles)
        lv.addWidget(header)

        # Sadržaj
        scroll = QWidget()
        scroll.setStyleSheet("background:transparent;")
        sv = QVBoxLayout(scroll)
        sv.setContentsMargins(16, 16, 16, 16)
        sv.setSpacing(16)

        sv.addWidget(self._section_upload())
        sv.addWidget(_sep())
        sv.addWidget(self._section_optimization())
        sv.addWidget(_sep())
        sv.addWidget(self._section_prikaz())
        sv.addStretch()
        sv.addWidget(self._section_buttons())

        lv.addWidget(scroll, stretch=1)
        return w

    def _section_upload(self):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(w); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(10)
        lv.addWidget(_section_label("UČITAVANJE FAJLA"))

        self.upload_zone = UploadZone()
        self.upload_zone.file_dropped.connect(self._on_drop_or_click)
        lv.addWidget(self.upload_zone)

        # Kartica učitanog fajla
        self.file_card = QFrame()
        self.file_card.setObjectName("fileCard")
        self.file_card.setVisible(False)
        fcv = QHBoxLayout(self.file_card)
        fcv.setContentsMargins(12, 10, 12, 10); fcv.setSpacing(10)
        ficon = QLabel("📄")
        ficon.setStyleSheet("font-size:20px; background:transparent;")
        finfo = QVBoxLayout(); finfo.setSpacing(1)
        self.lbl_fname = QLabel("—")
        self.lbl_fname.setStyleSheet(
            "font-size:13px; font-weight:500; color:#fff; background:transparent;")
        self.lbl_fsize = QLabel("—")
        self.lbl_fsize.setStyleSheet(
            "font-size:11px; color:#666; background:transparent;")
        finfo.addWidget(self.lbl_fname); finfo.addWidget(self.lbl_fsize)
        fcv.addWidget(ficon); fcv.addLayout(finfo); fcv.addStretch()
        lv.addWidget(self.file_card)
        return w

    def _section_optimization(self):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(w); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(10)
        lv.addWidget(_section_label("OPTIMIZACIJA MREŽE"))

        row = QHBoxLayout()
        lbl = QLabel("Smanjenje tacaka")
        lbl.setStyleSheet(
            "font-size:13px; font-weight:500; color:#e0e0e0; background:transparent;")
        self.lbl_ratio = QLabel("70%")
        self.lbl_ratio.setStyleSheet(
            "font-size:13px; font-weight:500; color:#fff; "
            "background:#2e3140; border-radius:12px; padding:2px 8px;")
        row.addWidget(lbl); row.addStretch(); row.addWidget(self.lbl_ratio)
        lv.addLayout(row)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(5, 95); self.slider.setValue(70)
        self.slider.valueChanged.connect(lambda v: self.lbl_ratio.setText(f"{v}%"))
        lv.addWidget(self.slider)

        hint = QLabel("Manji % = više detalja, veći fajl")
        hint.setStyleSheet("font-size:11px; color:#555; background:transparent;")
        lv.addWidget(hint)

        lv.addWidget(_section_label("METODA DECIMACIJE"))

        self.rb_qec     = QRadioButton("Quadric Edge Collapse")
        self.rb_cluster = QRadioButton("Vertex Clustering")
        self.rb_qec.setChecked(True)

        row2 = QHBoxLayout(); row2.setSpacing(6)
        row2.addWidget(self.rb_qec)
        tag = QLabel("(preporučeno)")
        tag.setStyleSheet("font-size:11px; color:#555; background:transparent;")
        row2.addWidget(tag); row2.addStretch()

        self._rbg = QButtonGroup(self)
        for rb in (self.rb_qec, self.rb_cluster):
            self._rbg.addButton(rb)

        lv.addLayout(row2)
        lv.addWidget(self.rb_cluster)
        return w

    def _section_prikaz(self):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(w); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(8)
        lv.addWidget(_section_label("PRIKAZ"))

        self.rb_solid  = QRadioButton("Solid")
        self.rb_smooth = QRadioButton("Solid (bez linija)")
        self.rb_wire   = QRadioButton("Wireframe")
        self.rb_solid.setChecked(True)

        self._rbg2 = QButtonGroup(self)
        for rb in (self.rb_solid, self.rb_smooth, self.rb_wire):
            self._rbg2.addButton(rb)
            lv.addWidget(rb)

        self.rb_solid.toggled.connect(
            lambda c: c and self.viewer.set_display_mode("solid"))
        self.rb_smooth.toggled.connect(
            lambda c: c and self.viewer.set_display_mode("smooth"))
        self.rb_wire.toggled.connect(
            lambda c: c and self.viewer.set_display_mode("wireframe"))
        return w

    def _section_buttons(self):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(w); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(8)

        self.btn_convert = QPushButton("↻  Konvertuj i prikaži")
        self.btn_convert.setObjectName("btnConvert")
        self.btn_convert.setFixedHeight(40)
        self.btn_convert.clicked.connect(self._on_decimate)
        lv.addWidget(self.btn_convert)

        self.progress = QProgressBar()
        self.progress.setRange(0, 0); self.progress.setFixedHeight(4)
        self.progress.setVisible(False)
        lv.addWidget(self.progress)

        row = QHBoxLayout(); row.setSpacing(8)
        self.btn_ascii = QPushButton("⬇ ASCII .txt")
        self.btn_ascii.setObjectName("btnAscii")
        self.btn_ascii.clicked.connect(self._on_save_ascii)
        self.btn_obj = QPushButton("📄 .obj")
        self.btn_obj.setObjectName("btnObj")
        self.btn_obj.clicked.connect(self._on_save_obj)
        row.addWidget(self.btn_ascii); row.addWidget(self.btn_obj)
        lv.addLayout(row)
        return w

    # ── DESNI PANEL ───────────────────────────────────────────────────
    def _build_right(self):
        w = QWidget(); w.setStyleSheet("background:#12141a;")
        lv = QVBoxLayout(w); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(0)

        # Viewer toolbar
        vtb = QWidget()
        vtb.setFixedHeight(46)
        vtb.setStyleSheet("background:#12141a; border-bottom:1px solid #2e3140;")
        vth = QHBoxLayout(vtb)
        vth.setContentsMargins(16, 8, 16, 8); vth.setSpacing(8)
        lbl3d = QLabel("3D prikaz")
        lbl3d.setStyleSheet("font-size:13px; color:#666; background:transparent;")
        vth.addWidget(lbl3d); vth.addStretch()

        self.btn_orbit  = QPushButton("⊕  Orbita")
        self.btn_orbit.setFixedHeight(30)
        self.btn_orbit.clicked.connect(self._on_reset_camera)

        self.btn_screen = QPushButton("⤢  Ceo ekran")
        self.btn_screen.setFixedHeight(30)
        self.btn_screen.clicked.connect(self._on_toggle_fullscreen)

        vth.addWidget(self.btn_orbit); vth.addWidget(self.btn_screen)
        lv.addWidget(vtb)

        # 3D viewer
        self.viewer = MeshViewer()
        lv.addWidget(self.viewer, stretch=1)

        # Stats traka
        lv.addWidget(self._build_stats_bar())
        return w

    def _build_stats_bar(self):
        bar = QWidget()
        bar.setFixedHeight(70)
        bar.setStyleSheet("background:#1a1c23; border-top:1px solid #2e3140;")
        hv = QHBoxLayout(bar)
        hv.setContentsMargins(20, 8, 20, 8); hv.setSpacing(0)

        self.s_orig  = StatBlock("ORIGINALNE TAČKE")
        self.s_after = StatBlock("NAKON OPTIMIZACIJE")
        self.s_tris  = StatBlock("TROUGLOVI")
        self.s_err   = StatBlock("GREŠKA OBLIKA")

        for i, s in enumerate((self.s_orig, self.s_after, self.s_tris, self.s_err)):
            hv.addWidget(s, stretch=1)
            if i < 3:
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet("color:#2e3140; background:#2e3140; max-width:1px;")
                hv.addWidget(sep)
        return bar

    # ── Status bar ────────────────────────────────────────────────────
    def _build_statusbar(self):
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.status.showMessage("Spreman")

    # ── Refresh ───────────────────────────────────────────────────────
    def _refresh(self):
        loaded    = self.model.is_loaded()
        decimated = self.model.has_decimated()
        busy      = self.worker is not None

        self.btn_convert.setEnabled(loaded and not busy)
        self.btn_ascii.setEnabled(loaded)
        self.btn_obj.setEnabled(loaded)
        self.slider.setEnabled(loaded)

        s = self.model.stats_dict()

        if not loaded:
            for blk in (self.s_orig, self.s_after, self.s_tris, self.s_err):
                blk.set_value(None)
            return

        ov = s['orig_verts']; of = s['orig_faces']
        self.s_orig.set_value(f"{ov:,}" if ov else "—")

        if decimated:
            dv = s['dec_verts']; df = s['dec_faces']
            rv = s['reduction_v']
            self.s_after.set_value(f"{dv:,}" if dv else "—",
                                   tag=f"−{rv}%" if dv else "")
            self.s_tris.set_value(f"{df:,}" if df else "—",
                                  sub=f"orig: {of:,}" if of else "")
            err = self.model.shape_error_pct()
            self.s_err.set_value(f"{err}%" if err is not None else "—")
        else:
            self.s_after.set_value("—")
            self.s_tris.set_value(f"{of:,}" if of else "—")
            self.s_err.set_value("—")

    # ── Učitavanje fajla ─────────────────────────────────────────────
    def _on_drop_or_click(self, path: str):
        if not path:
            last = self.settings.value("last_dir", "")
            path, _ = QFileDialog.getOpenFileName(
                self, "Učitaj ASCII mesh fajl", last,
                "ASCII Mesh (*.txt);;Svi fajlovi (*)")
        if not path:
            return
        self._load_file(path)

    def _load_file(self, path: str):
        try:
            self.model.load(path)
            self.settings.setValue("last_dir", str(Path(path).parent))
            name = Path(path).name
            size_kb = Path(path).stat().st_size // 1024
            self.lbl_fname.setText(name)
            self.lbl_fsize.setText(f"{size_kb} KB · ASCII Mesh")
            self.file_card.setVisible(True)
            self.viewer.show_original(self.model.original_verts,
                                      self.model.original_faces)
            self.viewer.clear_after()
            self._refresh()
            o = self.model.original_stats()
            self.status.showMessage(
                f"Učitano: {name}  —  {o.verts:,} tačaka, {o.faces:,} trouglova")
        except Exception as e:
            self.status.showMessage(f"Greška pri učitavanju: {e}")

    # ── Decimacija ───────────────────────────────────────────────────
    def _on_decimate(self):
        if not self.model.is_loaded() or self.worker:
            return
        pct    = self.slider.value()
        ratio  = 1.0 - pct / 100.0
        method = "pyfqmr" if self.rb_qec.isChecked() else "cluster"
        self.progress.setVisible(True)
        self.btn_convert.setEnabled(False)
        self.status.showMessage(f"Konverzija u toku ({pct}% smanjenje, {method})...")
        self.worker = DecimateWorker(self.model, ratio, method)
        self.worker.finished.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.start()

    def _on_done(self, elapsed: float):
        self.worker = None
        self.progress.setVisible(False)
        self.viewer.show_decimated(self.model.decimated_verts,
                                   self.model.decimated_faces)
        self._refresh()
        s = self.model.decimated_stats()
        err = self.model.shape_error_pct()
        err_str = f"  |  greška {err}%" if err is not None else ""
        self.status.showMessage(
            f"Gotovo za {elapsed:.2f}s  —  "
            f"{s.verts:,} tačaka / {s.faces:,} trouglova  (−{s.reduction_f}%){err_str}")

    def _on_error(self, msg: str):
        self.worker = None
        self.progress.setVisible(False)
        self._refresh()
        self.status.showMessage(f"Greška: {msg}")

    # ── Export ───────────────────────────────────────────────────────
    def _on_save_ascii(self):
        if not self.model.is_loaded():
            return
        last = self.settings.value("last_dir", "")
        path, _ = QFileDialog.getSaveFileName(
            self, "Sačuvaj ASCII mesh fajl",
            str(Path(last) / "output_mesh.txt"),
            "ASCII Mesh (*.txt);;Svi fajlovi (*)")
        if not path:
            return
        try:
            self.model.save(path, decimated=self.model.has_decimated())
            kind = "decimirani" if self.model.has_decimated() else "originalni"
            self.status.showMessage(f"Sačuvan {kind} mesh: {Path(path).name}")
        except Exception as e:
            self.status.showMessage(f"Greška pri čuvanju: {e}")

    def _on_save_obj(self):
        if not self.model.is_loaded():
            return
        last = self.settings.value("last_dir", "")
        path, _ = QFileDialog.getSaveFileName(
            self, "Sačuvaj kao .obj",
            str(Path(last) / "output_mesh.obj"),
            "Wavefront OBJ (*.obj);;Svi fajlovi (*)")
        if not path:
            return
        try:
            use_dec = self.model.has_decimated()
            verts = self.model.decimated_verts if use_dec else self.model.original_verts
            faces = self.model.decimated_faces if use_dec else self.model.original_faces
            with open(path, "w") as f:
                f.write("# Exported by 3DS Max ASCII Konvertor\n")
                for v in verts:
                    f.write(f"v {v[0]:.6f} {v[1]:.6f} {v[2]:.6f}\n")
                for t in faces:
                    f.write(f"f {t[0]+1} {t[1]+1} {t[2]+1}\n")
            kind = "decimirani" if use_dec else "originalni"
            self.status.showMessage(f"Sačuvan {kind} mesh kao OBJ: {Path(path).name}")
        except Exception as e:
            self.status.showMessage(f"Greška pri čuvanju OBJ: {e}")

    # ── Viewer kontrole ──────────────────────────────────────────────
    def _on_reset_camera(self):
        self.viewer.reset_cameras()
        self.status.showMessage("Kamera resetovana")

    def _on_toggle_fullscreen(self):
        self._fullscreen_viewer = not self._fullscreen_viewer
        self._left_panel.setVisible(not self._fullscreen_viewer)
        self.btn_screen.setText(
            "✕  Izađi" if self._fullscreen_viewer else "⤢  Ceo ekran")

    def closeEvent(self, event):
        self.viewer.close()
        super().closeEvent(event)
