"""
ui/main_window.py
Layout identičan screenshotu:
  - Tamna tema
  - Levo: zona za fajl (drag&drop, tri stanja), slider, metoda, prikaz, dugmad
  - Desno: 3D prikaz sa toolbar-om (Orbita / Ceo ekran)
  - Desno dole: statistike (Originalne tačke, Nakon optimizacije, Trouglovi, Greška)
"""

from __future__ import annotations
import os
import time
from pathlib import Path

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QPushButton, QLabel, QSlider, QRadioButton, QButtonGroup,
    QFileDialog, QStatusBar, QStackedLayout, QScrollArea,
    QFrame, QSizePolicy,
)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal, QSettings, QMimeData, QUrl
from PyQt6.QtGui import (
    QAction, QDragEnterEvent, QDropEvent, QPainter, QColor, QLinearGradient,
    QFontMetrics,
)

from core.mesh_model import MeshModel
from core.max_finder import find_max_exe, save_max_exe, max_version_from_path
from ui.viewer_widget import MeshViewer


# ── Pozadinski threadovi ─────────────────────────────────────────────────────
#
# Svi workeri emituju `done`, a ne `finished`. `finished` je ime koje QThread
# već koristi za svoj signal "thread je izašao"; pyqtSignal sa tim imenom ga u
# podklasi zaklanja, pa se na pravi QThread.finished više nije moglo vezati —
# a upravo on je jedini bezbedan trenutak da se referenca na worker ispusti.
# Bez toga se `self.worker = None` izvršavalo iz handlera signala emitovanog na
# kraju run(), dok thread još nije izašao: brisanje QThread objekta u tom
# trenutku je "QThread: Destroyed while thread is still running" i pad procesa.
# Vidi MainWindow._reap_worker.


class LoadWorker(QThread):
    """Učitava ASCII mesh fajl u pozadini da UI ne bi zamrzao."""
    done  = pyqtSignal(float)   # elapsed sekunde
    error = pyqtSignal(str)

    def __init__(self, model, path):
        super().__init__()
        self.model = model
        self.path  = path

    def run(self):
        t0 = time.perf_counter()
        try:
            self.model.load(self.path)
            self.done.emit(time.perf_counter() - t0)
        except Exception as e:
            self.error.emit(str(e))


class MaxConvertWorker(QThread):
    """Konvertuje .max → ASCII u pozadini koristeći 3ds Max headless."""
    done  = pyqtSignal(str)   # putanja do generisanog .txt
    error = pyqtSignal(str)

    def __init__(self, max_exe, ms_script, input_max, output_txt):
        super().__init__()
        self.max_exe    = max_exe
        self.ms_script  = ms_script
        self.input_max  = input_max
        self.output_txt = output_txt

    def run(self):
        try:
            # Vidljivi Max, ne headless: education licence ne dozvoljavaju
            # batch režim (3dsmaxbatch.exe izlazi sa -12 pre nego što uopšte
            # pročita skriptu). Interaktivni Max na istoj licenci radi.
            from core.converter import export_from_max_gui
            export_from_max_gui(
                self.max_exe, self.ms_script,
                self.input_max, self.output_txt,
            )
            self.done.emit(self.output_txt)
        except Exception as e:
            self.error.emit(str(e))


class DecimateWorker(QThread):
    done  = pyqtSignal(float)
    error = pyqtSignal(str)

    def __init__(self, model, ratio, method):
        super().__init__()
        self.model = model; self.ratio = ratio; self.method = method

    def run(self):
        t0 = time.perf_counter()
        try:
            self.model.run_decimate(self.ratio, self.method)
            self.done.emit(time.perf_counter() - t0)
        except Exception as e:
            self.error.emit(str(e))


# ── Sweep progress bar ───────────────────────────────────────────────────────

class SweepBar(QWidget):
    """Indeterminate progress bar — tračak svetlosti koji klizi s leva na desno."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(6)
        self._pos = -0.4
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self.setVisible(False)

    def start(self):
        self._pos = -0.4
        self.setVisible(True)
        self._timer.start(16)

    def stop(self):
        self._timer.stop()
        self.setVisible(False)

    def _tick(self):
        self._pos += 0.014
        if self._pos > 1.4:
            self._pos = -0.4
        self.update()

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#2e3140"))
        p.drawRoundedRect(0, 0, w, h, 3, 3)

        cx = self._pos * w
        sw = w * 0.45
        grad = QLinearGradient(cx - sw, 0, cx + sw, 0)
        grad.setColorAt(0.0,  QColor(0, 0, 0, 0))
        grad.setColorAt(0.38, QColor("#4a7adf"))
        grad.setColorAt(0.5,  QColor("#7ab0ff"))
        grad.setColorAt(0.62, QColor("#4a7adf"))
        grad.setColorAt(1.0,  QColor(0, 0, 0, 0))

        p.setBrush(grad)
        p.drawRoundedRect(0, 0, w, h, 3, 3)
        p.end()


# ── Zona za fajl: jedna, fiksne visine, tri stanja ───────────────────────────

class FileZone(QFrame):
    """Prazno → učitavanje → učitano, sve u istom okviru fiksne visine.

    Ranije su ovo bila dva odvojena widgeta (upload zona + fajl kartica) koja su
    se međusobno sakrivala. Zona je 110px, kartica 46px — pa je pri svakom
    učitavanju cela leva kolona skakala ~140px, i još jednom nazad pri zameni
    fajla. Sada se menja samo sadržaj okvira; ništa ispod se ne pomera.

    Ispod separatora je stalno podnožje sa .max dugmetom — i to je "učitaj
    fajl" akcija, pa nema razloga da stoji izvan okvira. Podnožje je isto u
    sva tri stanja; menja se samo deo iznad njega.

    Drop i klik rade u svim stanjima osim tokom učitavanja — zamena fajla ne
    traži nikakav prethodni korak.
    """

    file_dropped     = pyqtSignal(str)   # putanja prevučenog fajla
    browse_requested = pyqtSignal()      # klik → otvori dijalog

    STACK_H  = 104   # visina dela koji se menja; podnožje dolazi ispod
    NAME_MAX = 200   # px pre elidiranja imena fajla
    BAR_MIN  = 120   # najmanja širina trake za učitavanje
    BAR_PAD  = 24    # margina do ivica zone koju traka nikad ne prelazi

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fileZone")
        self.setAcceptDrops(True)
        self._state = ""

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)

        host = QWidget()
        host.setStyleSheet("background:transparent;")
        host.setFixedHeight(self.STACK_H)
        self._stack = QStackedLayout(host)
        self._stack.setContentsMargins(12, 10, 12, 10)
        self._stack.addWidget(self._build_empty())     # 0
        self._stack.addWidget(self._build_loading())   # 1
        self._stack.addWidget(self._build_loaded())    # 2
        outer.addWidget(host)

        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet("background:#2e3140; border:none;")
        outer.addWidget(line)

        outer.addWidget(self._build_max_footer())

        self.set_empty()

    def _build_max_footer(self):
        """Stalno podnožje: .max dugme + verzija Maxa. Isto u svim stanjima."""
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        # Klik na praznu površinu podnožja ne sme da otvori .txt dijalog —
        # bez ovoga bi propao do FileZone.mousePressEvent.
        w.mousePressEvent = lambda e: None
        w.setCursor(Qt.CursorShape.ArrowCursor)

        lv = QVBoxLayout(w)
        lv.setContentsMargins(11, 9, 11, 10); lv.setSpacing(6)

        self.btn_max = QPushButton()
        self.btn_max.setObjectName("btnLoadMax")
        self.btn_max.setFixedHeight(28)
        self.btn_max.setCursor(Qt.CursorShape.PointingHandCursor)

        self.lbl_max = QLabel()
        self.lbl_max.setObjectName("maxPathHint")
        self.lbl_max.setWordWrap(False)
        self.lbl_max.setFixedHeight(14)
        self.lbl_max.setCursor(Qt.CursorShape.PointingHandCursor)

        lv.addWidget(self.btn_max); lv.addWidget(self.lbl_max)
        return w

    # ── Stranice ─────────────────────────────────────────────────────
    def _build_empty(self):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(3)
        lv.setAlignment(Qt.AlignmentFlag.AlignCenter)

        for text, css in (
            ("⬆", "font-size:24px; color:#4a5080;"),
            ("Prevucite ASCII .txt fajl ovde", "font-size:13px; font-weight:500; color:#ccc;"),
            ("ili kliknite za pregled", "font-size:11px; color:#5a5f70;"),
        ):
            l = QLabel(text)
            l.setStyleSheet(css + " background:transparent;")
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lv.addWidget(l)
        return w

    def _build_loading(self):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(7)
        lv.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        # Red ikonica + ime je sopstveni widget (a ne layout sa stretch-evima)
        # da bi mu se moglo pročitati sizeHint — po njemu se meri traka ispod.
        self._load_head = QWidget()
        self._load_head.setStyleSheet("background:transparent;")
        row = QHBoxLayout(self._load_head)
        row.setContentsMargins(0, 0, 0, 0); row.setSpacing(8)
        self._load_icon = QLabel("⏳")
        self._load_icon.setStyleSheet("font-size:16px; background:transparent;")
        self._load_name = QLabel("—")
        self._load_name.setStyleSheet(
            "font-size:12px; font-weight:500; color:#fff; background:transparent;")
        row.addWidget(self._load_icon); row.addWidget(self._load_name)
        lv.addWidget(self._load_head, alignment=Qt.AlignmentFlag.AlignHCenter)

        self._load_meta = QLabel("—")
        self._load_meta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._load_meta.setStyleSheet("font-size:11px; color:#8892a8; background:transparent;")
        lv.addWidget(self._load_meta)

        # Progres stoji uz fajl koji se učitava, a ne dole kod dugmeta za
        # decimaciju — feedback treba da bude tamo gde se akcija desila.
        # Traka se ne razvlači celom širinom okvira: širina joj se u
        # set_loading() postavlja na širinu teksta iznad, pa je centrirana.
        self._load_bar = SweepBar()
        bar_row = QHBoxLayout(); bar_row.setContentsMargins(0, 0, 0, 0)
        bar_row.addStretch()
        bar_row.addWidget(self._load_bar)
        bar_row.addStretch()
        lv.addLayout(bar_row)
        return w

    def _build_loaded(self):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(8)
        lv.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        row = QHBoxLayout(); row.setSpacing(8)
        icon = QLabel("📄")
        icon.setStyleSheet("font-size:17px; background:transparent;")
        info = QVBoxLayout(); info.setSpacing(1)
        self._done_name = QLabel("—")
        self._done_name.setStyleSheet(
            "font-size:12px; font-weight:500; color:#fff; background:transparent;")
        self._done_meta = QLabel("—")
        self._done_meta.setStyleSheet("font-size:11px; color:#8892a8; background:transparent;")
        info.addWidget(self._done_name); info.addWidget(self._done_meta)
        row.addStretch()
        row.addWidget(icon); row.addLayout(info)
        row.addStretch()
        lv.addLayout(row)

        # Vidljiva meta za klik. Cela zona i dalje reaguje na klik, ali bez
        # dugmeta se to ne vidi — a sitan tekst se ne čita.
        actions = QHBoxLayout(); actions.setSpacing(7)
        btn = QPushButton("Izaberi drugi")
        btn.setObjectName("btnPickAnother")
        btn.setFixedHeight(24)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self.browse_requested.emit)
        hint = QLabel("ili prevuci ovde")
        hint.setStyleSheet("font-size:11px; color:#5a5f70; background:transparent;")
        actions.addStretch()
        actions.addWidget(btn); actions.addWidget(hint)
        actions.addStretch()
        lv.addLayout(actions)
        return w

    # ── Prelazi između stanja ────────────────────────────────────────
    def _set_state(self, state: str):
        self._state = state
        self.setProperty("state", state)
        self.setCursor(
            Qt.CursorShape.ArrowCursor if state == "loading"
            else Qt.CursorShape.PointingHandCursor
        )
        self.style().unpolish(self)
        self.style().polish(self)

    def _elide(self, name: str) -> str:
        return QFontMetrics(self.font()).elidedText(
            name, Qt.TextElideMode.ElideMiddle, self.NAME_MAX)

    def _bar_width(self) -> int:
        """Širina trake za učitavanje — po najširem redu teksta iznad nje.

        Ime fajla je elidirano na NAME_MAX pa je gornja granica poznata, a
        donja postoji da traka ostane čitljiva i za kratka imena.
        """
        content = max(self._load_head.sizeHint().width(),
                      self._load_meta.sizeHint().width())
        avail = self.width() - 2 * self.BAR_PAD
        return max(self.BAR_MIN, min(content, avail if avail > 0 else content))

    def set_empty(self):
        self._load_bar.stop()
        self._stack.setCurrentIndex(0)
        self._set_state("empty")

    def set_loading(self, name: str, meta: str):
        self._load_name.setText(self._elide(name))
        self._load_name.setToolTip(name)
        self._load_meta.setText(meta)
        self._load_bar.setFixedWidth(self._bar_width())
        self._stack.setCurrentIndex(1)
        self._set_state("loading")
        self._load_bar.start()

    def set_loaded(self, name: str, meta: str):
        self._load_bar.stop()
        self._done_name.setText(self._elide(name))
        self._done_name.setToolTip(name)
        self._done_meta.setText(meta)
        self._stack.setCurrentIndex(2)
        self._set_state("loaded")

    # ── Drag & drop / klik ───────────────────────────────────────────
    def _set_drag_active(self, active: bool):
        self.setProperty("dragActive", active)
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e: QDragEnterEvent):
        if self._state == "loading":
            return
        if e.mimeData().hasUrls() and any(
            u.toLocalFile().lower().endswith('.txt') for u in e.mimeData().urls()
        ):
            self._set_drag_active(True)
            e.acceptProposedAction()

    def dragLeaveEvent(self, e):
        self._set_drag_active(False)

    def dropEvent(self, e: QDropEvent):
        self._set_drag_active(False)
        for url in e.mimeData().urls():
            path = url.toLocalFile()
            if path.lower().endswith('.txt'):
                self.file_dropped.emit(path)
                break
        e.acceptProposedAction()

    def mousePressEvent(self, e):
        if self._state != "loading":
            self.browse_requested.emit()


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




# ── Glavni prozor ─────────────────────────────────────────────────────────────

class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()
        self.model       = MeshModel()
        self.worker      = None   # DecimateWorker
        self.load_worker = None   # LoadWorker
        self.max_worker  = None   # MaxConvertWorker
        self.max_exe     = find_max_exe()
        self.settings    = QSettings("MeshConverter", "App")
        self._fullscreen_viewer = False

        self.setWindowTitle("3DS Max → ASCII Konvertor")
        self.resize(1140, 700)
        self.setMinimumSize(900, 560)

        self._build_ui()
        self._build_statusbar()
        self._refresh()

    def _build_ui(self):
        root = QWidget()
        root.setObjectName("rootPanel")
        root.setStyleSheet("QWidget#rootPanel { background:#1a1c23; }")
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
        w.setObjectName("leftPanel")
        w.setFixedWidth(300)
        w.setStyleSheet(
            "QWidget#leftPanel { background:#1a1c23; border-right:1px solid #2e3140; }"
        )

        lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(0)

        # Sadržaj
        content = QWidget()
        content.setStyleSheet("background:transparent;")
        sv = QVBoxLayout(content)
        sv.setContentsMargins(16, 16, 16, 16)
        sv.setSpacing(16)

        self._opt_section = self._section_optimization()

        sv.addWidget(self._section_upload())
        sv.addWidget(_sep())
        sv.addWidget(self._opt_section)
        sv.addWidget(_sep())
        sv.addWidget(self._section_prikaz())
        sv.addStretch()
        sv.addWidget(self._section_buttons())

        # Sekcijama treba ~640px, a panel ih na 700px prozoru dobije manje —
        # bez scroll area Qt ih stisne ispod minimuma i widgeti se preklope
        # (dugme za .max je ulazilo u zonu za fajl). Sa scroll-om svaka sekcija
        # dobija punu visinu, a višak se skroluje.
        scroll = QScrollArea()
        scroll.setWidget(content)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background:transparent;")
        scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.viewport().setStyleSheet("background:transparent;")

        lv.addWidget(scroll, stretch=1)
        return w

    def _section_upload(self):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(w); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(10)
        lv.addWidget(_section_label("UČITAVANJE FAJLA"))

        self.file_zone = FileZone()
        self.file_zone.file_dropped.connect(self._load_file)
        self.file_zone.browse_requested.connect(self._on_browse)
        lv.addWidget(self.file_zone)

        # .max kontrole žive u podnožju zone; ovde ih samo ožičimo. Dugme je
        # UVEK vidljivo — ranije se sakrivalo kad Max nije pronađen, pa je
        # izgledalo kao da funkcionalnost ne postoji, bez traga zašto.
        self.btn_load_max = self.file_zone.btn_max
        self.btn_load_max.clicked.connect(self._on_load_max)

        # Labela uvek zauzima svoju visinu — i kad Max nije nađen. Sakrivanje
        # bi pomerilo sve ispod nje.
        self.lbl_max_path = self.file_zone.lbl_max
        self.lbl_max_path.mousePressEvent = lambda e: self._pick_max_exe()

        self._refresh_max_ui()
        return w

    def _section_optimization(self):
        w = QWidget(); w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(w); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(10)
        lv.addWidget(_section_label("OPTIMIZACIJA MREŽE"))

        # Stilovi ovih labela žive u styles.qss (a ne inline) da bi imali i
        # :disabled varijantu — cela sekcija se prigušuje dok nema fajla.
        row = QHBoxLayout()
        lbl = QLabel("Jačina smanjenja")
        lbl.setObjectName("optLabel")
        self.lbl_ratio = QLabel("−70%")
        self.lbl_ratio.setObjectName("ratioPill")
        row.addWidget(lbl); row.addStretch(); row.addWidget(self.lbl_ratio)
        lv.addLayout(row)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(5, 95); self.slider.setValue(70)
        self.slider.valueChanged.connect(self._on_slider_changed)
        lv.addWidget(self.slider)

        self.lbl_hint = QLabel("Zadržava se ~30% trouglova")
        self.lbl_hint.setObjectName("optHint")
        lv.addWidget(self.lbl_hint)

        lv.addWidget(_section_label("METODA DECIMACIJE"))

        self.rb_qec     = QRadioButton("Quadric Edge Collapse")
        self.rb_cluster = QRadioButton("Vertex Clustering")
        self.rb_qec.setChecked(True)

        self._rbg = QButtonGroup(self)
        for rb in (self.rb_qec, self.rb_cluster):
            self._rbg.addButton(rb)
            lv.addWidget(rb)
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
        lv = QVBoxLayout(w); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(6)

        self.btn_convert = QPushButton("↻  Konvertuj i prikaži")
        self.btn_convert.setObjectName("btnConvert")
        self.btn_convert.setFixedHeight(40)
        self.btn_convert.clicked.connect(self._on_decimate)
        lv.addWidget(self.btn_convert)

        # Traka drži svoje mesto i kad je nevidljiva (da dugmad ne skaču), ali
        # je razmak bio 34px ukupno — previše za 6px traku. Sada 22px.
        prog_wrap = QWidget(); prog_wrap.setFixedHeight(10)
        prog_wl = QVBoxLayout(prog_wrap)
        prog_wl.setContentsMargins(0, 2, 0, 2)
        self.progress = SweepBar()
        prog_wl.addWidget(self.progress)
        lv.addWidget(prog_wrap)

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
        w = QWidget()
        w.setObjectName("rightPanel")
        w.setStyleSheet("QWidget#rightPanel { background:#12141a; }")
        lv = QVBoxLayout(w); lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(0)

        # Viewer toolbar
        vtb = QWidget()
        vtb.setObjectName("viewerToolbar")
        vtb.setFixedHeight(46)
        vtb.setStyleSheet(
            "QWidget#viewerToolbar { background:#12141a; border-bottom:1px solid #2e3140; }"
        )
        vth = QHBoxLayout(vtb)
        vth.setContentsMargins(16, 8, 16, 8); vth.setSpacing(8)
        lbl3d = QLabel("3D prikaz")
        lbl3d.setStyleSheet("font-size:13px; color:#666; background:transparent;")
        vth.addWidget(lbl3d); vth.addStretch()

        self.btn_orbit  = QPushButton("⊕  Reset kamere")
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
        bar.setObjectName("statsBar")
        bar.setFixedHeight(76)
        bar.setStyleSheet(
            "QWidget#statsBar { background:#1a1c23; border-top:1px solid #2e3140; }"
        )
        hv = QHBoxLayout(bar)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.setSpacing(0)

        def vsep():
            f = QFrame()
            f.setFixedWidth(1)
            f.setStyleSheet("background:#2e3140; border:none;")
            return f

        orig, self._orig_tacke, self._orig_trouglovi = self._stat_group("ORIGINALNO")
        opt,  self._opt_tacke,  self._opt_trouglovi  = self._stat_group("OPTIMIZOVANO")

        # Desna polovina = OPTIMIZOVANO + GREŠKA u jednom kontejneru stretch=1,
        # da linija između leve i desne polovine odgovara liniji u 3D prikazu.
        right = QWidget(); right.setStyleSheet("background:transparent;")
        rh = QHBoxLayout(right); rh.setContentsMargins(0, 0, 0, 0); rh.setSpacing(0)
        rh.addWidget(opt, stretch=1)
        rh.addWidget(vsep())
        rh.addWidget(self._stat_err_group())

        hv.addWidget(orig, stretch=1)
        hv.addWidget(vsep())
        hv.addWidget(right, stretch=1)
        return bar

    def _stat_group(self, title: str):
        w = QWidget()
        w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(w)
        lv.setContentsMargins(18, 8, 18, 8)
        lv.setSpacing(4)

        ttl = QLabel(title)
        ttl.setStyleSheet(
            "font-size:9px; font-weight:500; color:#4a5080; "
            "letter-spacing:1.5px; background:transparent;")
        lv.addWidget(ttl)

        row = QHBoxLayout()
        row.setSpacing(20)
        row.setContentsMargins(0, 0, 0, 0)

        def cell(sub_text):
            cw = QWidget(); cw.setStyleSheet("background:transparent;")
            cv = QVBoxLayout(cw); cv.setContentsMargins(0, 0, 0, 0); cv.setSpacing(1)
            sub = QLabel(sub_text)
            sub.setStyleSheet(
                "font-size:9px; font-weight:500; color:#444; "
                "letter-spacing:1px; background:transparent;")
            val = QLabel("—")
            val.setStyleSheet(
                "font-size:22px; font-weight:500; color:#e0e0e0; background:transparent;")
            cv.addWidget(sub); cv.addWidget(val)
            return cw, val

        tacke_w,     val_t = cell("TAČKE")
        trouglovi_w, val_f = cell("TROUGLOVI")
        row.addWidget(tacke_w); row.addWidget(trouglovi_w); row.addStretch()
        lv.addLayout(row)
        return w, val_t, val_f

    def _stat_err_group(self):
        w = QWidget()
        w.setFixedWidth(120)
        w.setStyleSheet("background:transparent;")
        lv = QVBoxLayout(w)
        lv.setContentsMargins(0, 8, 0, 8)
        lv.setAlignment(Qt.AlignmentFlag.AlignCenter)

        ttl = QLabel("GREŠKA")
        ttl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ttl.setStyleSheet(
            "font-size:9px; font-weight:500; color:#555; "
            "letter-spacing:1.5px; background:transparent;")

        self._err_val = QLabel("—")
        self._err_val.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._err_val.setStyleSheet(
            "font-size:22px; font-weight:500; color:#e0e0e0; background:transparent;")

        lv.addWidget(ttl); lv.addWidget(self._err_val)
        return w

    # ── Status bar ────────────────────────────────────────────────────
    def _build_statusbar(self):
        self.status = QStatusBar(self)
        self.setStatusBar(self.status)
        self.status.showMessage("Spreman")

    # ── Životni ciklus workera ────────────────────────────────────────
    def _reap_worker(self, attr: str):
        """Ispušta referencu na worker tek kad thread stvarno izađe.

        Vezuje se na QThread.finished (ne na naš `done`), jer se `done`
        emituje iz run() dok je thread još živ. Brisanje QThread objekta u tom
        trenutku ubija proces — a to je bilo lako pogoditi na velikim
        meshevima, gde handler posle `done` radi sekundu-dve na renderu.
        """
        w = getattr(self, attr, None)
        setattr(self, attr, None)
        if w is not None:
            w.deleteLater()
        self._refresh()

    # ── Refresh ───────────────────────────────────────────────────────
    def _refresh(self):
        loaded    = self.model.is_loaded()
        decimated = self.model.has_decimated()
        busy      = any((self.worker, self.load_worker, self.max_worker))

        self.btn_convert.setEnabled(loaded and not busy)
        self.btn_ascii.setEnabled(loaded and not busy)
        self.btn_obj.setEnabled(loaded and not busy)
        # Cela sekcija, ne samo slajder — radio dugmad su ranije izgledala
        # aktivno iako nisu radila ništa dok nema fajla.
        self._opt_section.setEnabled(loaded and not busy)

        s = self.model.stats_dict()

        if not loaded:
            self._orig_tacke.setText("—"); self._orig_trouglovi.setText("—")
            self._opt_tacke.setText("—");  self._opt_trouglovi.setText("—")
            self._err_val.setText("—")
            return

        ov = s['orig_verts']; of = s['orig_faces']
        self._orig_tacke.setText(f"{ov:,}" if ov else "—")
        self._orig_trouglovi.setText(f"{of:,}" if of else "—")

        if decimated:
            dv = s['dec_verts']; df = s['dec_faces']
            self._opt_tacke.setText(f"{dv:,}" if dv else "—")
            self._opt_trouglovi.setText(f"{df:,}" if df else "—")
            err = self.model.shape_error_pct()
            self._err_val.setText(f"{err}%" if err is not None else "—")
        else:
            self._opt_tacke.setText("—"); self._opt_trouglovi.setText("—")
            self._err_val.setText("—")

    # ── Slajder ──────────────────────────────────────────────────────
    def _on_slider_changed(self, v: int):
        self.lbl_ratio.setText(f"−{v}%")
        self.lbl_hint.setText(f"Zadržava se ~{100 - v}% trouglova")

    # ── Učitavanje fajla ─────────────────────────────────────────────
    @staticmethod
    def _human_size(path: str) -> str:
        kb = Path(path).stat().st_size // 1024
        return f"{kb / 1024:.1f} MB" if kb >= 1024 else f"{kb} KB"

    def _on_browse(self):
        last = self.settings.value("last_dir", "")
        path, _ = QFileDialog.getOpenFileName(
            self, "Učitaj ASCII mesh fajl", last,
            "ASCII Mesh (*.txt);;Svi fajlovi (*)")
        if path:
            self._load_file(path)

    def _restore_zone(self):
        """Vrati zonu na stanje koje odgovara modelu (posle neuspeha)."""
        if self.model.is_loaded() and self.model.source_path:
            src = self.model.source_path
            o = self.model.original_stats()
            self.file_zone.set_loaded(
                Path(src).name, f"{self._human_size(src)} · {o.verts:,} tačaka")
        else:
            self.file_zone.set_empty()

    def _load_file(self, path: str):
        if self.load_worker or self.worker:
            self.status.showMessage("Sačekajte da se prethodni posao završi…")
            return

        name = Path(path).name
        size_str = self._human_size(path)
        self.file_zone.set_loading(name, f"{size_str} · čitanje…")
        self.status.showMessage(f"Čitanje: {name} ({size_str})…")
        self._pending_path = path

        self.load_worker = LoadWorker(self.model, path)
        self.load_worker.done.connect(self._on_load_done)
        self.load_worker.error.connect(self._on_load_error)
        self.load_worker.finished.connect(lambda: self._reap_worker("load_worker"))
        self.load_worker.start()
        self._refresh()

    def _on_load_done(self, elapsed: float):
        path = getattr(self, "_pending_path", "")
        self.settings.setValue("last_dir", str(Path(path).parent))
        name = Path(path).name
        o = self.model.original_stats()
        self.file_zone.set_loaded(
            name, f"{self._human_size(path)} · {o.verts:,} tačaka")

        self.status.showMessage("Priprema 3D prikaza…")
        # Render velikog mesha drži main thread; wait kursor je jedini signal
        # da app radi, jer se u međuvremenu ništa ne iscrtava.
        QApplication.processEvents()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            self.viewer.show_original(self.model.original_verts,
                                      self.model.original_faces)
            self.viewer.clear_after()
        finally:
            QApplication.restoreOverrideCursor()

        self._refresh()
        self.status.showMessage(
            f"Učitano za {elapsed:.2f}s — {name} "
            f"({o.verts:,} tačaka, {o.faces:,} trouglova)"
        )

    def _on_load_error(self, msg: str):
        self._restore_zone()
        self._refresh()
        self.status.showMessage(f"Greška pri učitavanju: {msg}")

    # ── .max konverzija ──────────────────────────────────────────────
    def _refresh_max_ui(self):
        """Tekst dugmeta i putanje zavise od toga da li je Max pronađen."""
        if self.max_exe:
            ver = max_version_from_path(self.max_exe)
            self.btn_load_max.setText("⬆  Učitaj .max fajl")
            self.btn_load_max.setToolTip(self.max_exe)
            self.lbl_max_path.setText(f"3ds Max {ver}  ·  promeni")
            self.lbl_max_path.setToolTip(self.max_exe)
        else:
            # Labela ostaje vidljiva — sakrivanje bi pomerilo sve ispod nje.
            self.btn_load_max.setText("🔗  Poveži 3ds Max…")
            self.btn_load_max.setToolTip("Izaberi 3dsmax.exe ručno")
            self.lbl_max_path.setText("Potreban samo za .max fajlove")
            self.lbl_max_path.setToolTip("")

    def _pick_max_exe(self) -> bool:
        """Ručni izbor 3dsmax.exe. Izbor se pamti između pokretanja."""
        start = os.path.dirname(self.max_exe) if self.max_exe else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Izaberi 3dsmax.exe", start, "3ds Max (3dsmax.exe)"
        )
        if not path:
            return False

        save_max_exe(path)
        self.max_exe = path
        self._refresh_max_ui()
        self.status.showMessage(f"3ds Max povezan: {path}")
        return True

    def _on_load_max(self):
        if self.max_worker or self.load_worker or self.worker:
            return

        # Max nije pronađen — prvo ga poveži, pa tek onda biraj .max fajl.
        if not self.max_exe and not self._pick_max_exe():
            return

        path, _ = QFileDialog.getOpenFileName(
            self, "Izaberi .max fajl", "", "3ds Max fajlovi (*.max)"
        )
        if not path:
            return

        from pathlib import Path as _Path
        out_txt = str(_Path(path).with_suffix(".txt"))
        ms_script = str(_Path(__file__).parent.parent / "core" / "export_ascii.ms")

        # Konverzija koristi istu zonu kao i učitavanje — jedno mesto za
        # napredak, umesto trake dole kod dugmeta za decimaciju.
        self.file_zone.set_loading(_Path(path).name, "konverzija u 3ds Max…")
        self.btn_load_max.setEnabled(False)
        self.status.showMessage(f"Konverzija .max → ASCII: {_Path(path).name}…")

        self.max_worker = MaxConvertWorker(self.max_exe, ms_script, path, out_txt)
        self.max_worker.done.connect(self._on_max_done)
        self.max_worker.error.connect(self._on_max_error)
        self.max_worker.finished.connect(lambda: self._reap_worker("max_worker"))
        self.max_worker.start()
        self._refresh()

    def _on_max_done(self, txt_path: str):
        self.btn_load_max.setEnabled(True)
        self.status.showMessage("Konverzija završena — učitavam mesh…")
        self._load_file(txt_path)

    def _on_max_error(self, msg: str):
        self.btn_load_max.setEnabled(True)
        self._restore_zone()
        self._refresh()
        self.status.showMessage(f"Greška pri konverziji: {msg}")

    # ── Decimacija ───────────────────────────────────────────────────
    def _on_decimate(self):
        if not self.model.is_loaded() or self.worker or self.load_worker:
            return
        pct    = self.slider.value()
        ratio  = 1.0 - pct / 100.0
        # "auto" bira najbolju dostupnu metodu (VTK → pyfqmr → QEM → cluster).
        # Ranije je bilo hardkodovano "pyfqmr", koji na elisi ne dostiže target
        # i gubi konturu — vidi core/decimator.py i .claude/ZADATAK.md.
        method = "auto" if self.rb_qec.isChecked() else "cluster"
        self.progress.start()
        self.btn_convert.setEnabled(False)
        self.status.showMessage(f"Konverzija u toku ({pct}% smanjenje, {method})...")
        self.worker = DecimateWorker(self.model, ratio, method)
        self.worker.done.connect(self._on_done)
        self.worker.error.connect(self._on_error)
        self.worker.finished.connect(lambda: self._reap_worker("worker"))
        self.worker.start()

    def _on_done(self, elapsed: float):
        self.progress.stop()
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
        self.progress.stop()
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
            import numpy as np
            use_dec = self.model.has_decimated()
            verts = self.model.decimated_verts if use_dec else self.model.original_verts
            faces = self.model.decimated_faces if use_dec else self.model.original_faces
            with open(path, "w") as f:
                f.write("# Exported by 3DS Max ASCII Konvertor\n")
                np.savetxt(f, verts, fmt="v %.6f %.6f %.6f")
                # OBJ trouglovi su 1-based indeksi
                np.savetxt(f, faces + 1, fmt="f %d %d %d")
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
        # Ako se app zatvori dok worker radi, interpreter bi rušio QThread koji
        # je još u run() — isti pad kao kod ranog ispuštanja reference. Čekamo
        # ga, ograničeno, da zatvaranje ne visi ako se posao zaglavi.
        for attr in ("worker", "load_worker", "max_worker"):
            w = getattr(self, attr, None)
            if w is not None and w.isRunning():
                self.status.showMessage("Čekam da se posao u pozadini završi…")
                w.wait(5000)
        self.viewer.close()
        super().closeEvent(event)
