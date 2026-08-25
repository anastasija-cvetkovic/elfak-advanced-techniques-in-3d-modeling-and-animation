"""
ui/viewer_widget.py
MeshViewer — dva PyVista QtInteractor-a jedan pored drugog (before/after).
Modovi prikaza: "solid" (surface + ivice), "smooth" (surface bez ivica), "wireframe"
"""

from __future__ import annotations

import numpy as np

try:
    from pyvistaqt import QtInteractor
    import pyvista as pv
    PYVISTA_OK = True
except ImportError:
    PYVISTA_OK = False

from PyQt6.QtWidgets import (
    QWidget, QHBoxLayout, QVBoxLayout, QLabel, QFrame
)
from PyQt6.QtCore import Qt


class _PanelLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setStyleSheet(
            "color: #888; font-size: 11px; font-weight: 500; "
            "letter-spacing: 1px; padding: 4px 0;"
        )


class _FallbackPanel(QWidget):
    def __init__(self, label: str, parent=None):
        super().__init__(parent)
        lv = QVBoxLayout(self)
        lbl = QLabel(f"{label}\n\n(PyVista nije dostupna)", self)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color: #555; font-size: 13px;")
        lv.addWidget(lbl)


# Konfiguracija po modu: (style, show_edges, smooth_shading)
_MODE_CFG = {
    "solid":     ("surface",   True,  False),
    "smooth":    ("surface",   False, True),
    "wireframe": ("wireframe", False, False),
}


class MeshViewer(QWidget):
    """
    Widget sa dva 3D panela (ORIGINAL / DECIMIRANI).
    Podržava tri moda: solid, smooth, wireframe.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = "solid"
        self._orig_verts = self._orig_faces = None
        self._dec_verts  = self._dec_faces  = None
        self._build_ui()

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        if PYVISTA_OK:
            left = QWidget(self)
            lv = QVBoxLayout(left)
            lv.setContentsMargins(0, 0, 0, 0); lv.setSpacing(0)
            lv.addWidget(_PanelLabel("ORIGINAL"))
            self.pl_before = QtInteractor(left)
            self.pl_before.set_background("#181818")
            lv.addWidget(self.pl_before)

            right = QWidget(self)
            rv = QVBoxLayout(right)
            rv.setContentsMargins(0, 0, 0, 0); rv.setSpacing(0)
            rv.addWidget(_PanelLabel("DECIMIRANI"))
            self.pl_after = QtInteractor(right)
            self.pl_after.set_background("#181818")
            rv.addWidget(self.pl_after)

            sep = QFrame(self)
            sep.setFrameShape(QFrame.Shape.VLine)
            sep.setStyleSheet("color: #333;")

            root.addWidget(left)
            root.addWidget(sep)
            root.addWidget(right)
        else:
            root.addWidget(_FallbackPanel("ORIGINAL", self))
            root.addWidget(_FallbackPanel("DECIMIRANI", self))

    # ── Interna pomoć ─────────────────────────────────────────────────

    @staticmethod
    def _to_polydata(verts: list, faces: list) -> "pv.PolyData":
        pts   = np.array(verts, dtype=np.float64)
        cells = np.hstack([
            np.full((len(faces), 1), 3, dtype=np.int32),
            np.array(faces, dtype=np.int32),
        ]).flatten()
        return pv.PolyData(pts, cells)

    def _render(self, plotter, verts, faces, color, edge_color):
        """Crta mesh na zadatom ploteru prema trenutnom modu."""
        style, show_edges, smooth = _MODE_CFG[self._mode]
        mesh = self._to_polydata(verts, faces)
        plotter.clear()

        if self._mode == "smooth":
            # Izračunaj normalne za glatko senčenje
            mesh = mesh.compute_normals(
                auto_orient_normals=True,
                consistent_normals=True,
                split_vertices=False,
            )
            # Camera-relative 3-point lighting — prati kameru pri rotaciji
            plotter.remove_all_lights()
            key = pv.Light(position=(1.2, 1.0, 1.5), focal_point=(0, 0, 0),
                           intensity=1.0)
            key.light_type = pv.Light.CAMERA_LIGHT
            fill = pv.Light(position=(-1.5, 0.5, 0.5), focal_point=(0, 0, 0),
                            intensity=0.5)
            fill.light_type = pv.Light.CAMERA_LIGHT
            rim = pv.Light(position=(0.0, -1.0, -0.8), focal_point=(0, 0, 0),
                           intensity=0.25)
            rim.light_type = pv.Light.CAMERA_LIGHT
            for light in (key, fill, rim):
                plotter.add_light(light)
            plotter.add_mesh(
                mesh,
                style="surface",
                color=color,
                show_edges=False,
                smooth_shading=True,
                ambient=0.1,
                diffuse=0.8,
                specular=0.5,
                specular_power=40,
            )
        else:
            # Standardno lightkit osvetljenje za solid/wireframe
            plotter.enable_lightkit()
            plotter.add_mesh(
                mesh,
                style=style,
                color=color,
                show_edges=show_edges,
                edge_color=edge_color,
                line_width=0.8,
                smooth_shading=smooth,
            )

        plotter.reset_camera()

    # ── Javni API ─────────────────────────────────────────────────────

    def show_original(self, verts: list, faces: list) -> None:
        if not PYVISTA_OK:
            return
        self._orig_verts, self._orig_faces = verts, faces
        self._render(self.pl_before, verts, faces, "#4a9edd", "#1a4a7a")

    def show_decimated(self, verts: list, faces: list) -> None:
        if not PYVISTA_OK:
            return
        self._dec_verts, self._dec_faces = verts, faces
        self._render(self.pl_after, verts, faces, "#e07060", "#8a3020")

    def set_display_mode(self, mode: str) -> None:
        """
        Prebacuje mod prikaza: 'solid' | 'smooth' | 'wireframe'.
        Automatski osvežava oba panela ako su meshevi učitani.
        """
        if not PYVISTA_OK or mode not in _MODE_CFG:
            return
        self._mode = mode
        if self._orig_verts is not None:
            self._render(self.pl_before, self._orig_verts, self._orig_faces,
                         "#4a9edd", "#1a4a7a")
        if self._dec_verts is not None:
            self._render(self.pl_after, self._dec_verts, self._dec_faces,
                         "#e07060", "#8a3020")

    def clear_after(self) -> None:
        if PYVISTA_OK:
            self._dec_verts = self._dec_faces = None
            self.pl_after.clear()
            self.pl_after.render()

    def reset_cameras(self) -> None:
        if PYVISTA_OK:
            for pl in (self.pl_before, self.pl_after):
                pl.reset_camera()
                pl.render()

    def close(self):
        if PYVISTA_OK:
            try:
                self.pl_before.close()
                self.pl_after.close()
            except Exception:
                pass
        super().close()
