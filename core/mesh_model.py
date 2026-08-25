"""
core/mesh_model.py
Centralno stanje aplikacije — drži originalni i decimirani mesh,
orchestrira konverziju i decimaciju.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

from core.converter import load_mesh, save_mesh
from core.decimator import decimate


@dataclass
class MeshStats:
    verts: int = 0
    faces: int = 0
    reduction_v: float = 0.0   # % smanjenja tačaka
    reduction_f: float = 0.0   # % smanjenja trouglova


class MeshModel:
    """
    Drži stanje mesheva i orkhestrira operacije nad njima.

    Atributi
    --------
    source_path     — putanja odakle je učitan mesh
    original_verts  — originalne tačke
    original_faces  — originalni trouglovi
    decimated_verts — tačke nakon decimacije (None ako nije urađena)
    decimated_faces — trouglovi nakon decimacije
    last_ratio      — poslednje korišćen ratio
    last_method     — poslednje korišćena metoda
    """

    def __init__(self) -> None:
        self.source_path:     Optional[str]        = None
        self.original_verts:  Optional[np.ndarray] = None
        self.original_faces:  Optional[np.ndarray] = None
        self.decimated_verts: Optional[np.ndarray] = None
        self.decimated_faces: Optional[np.ndarray] = None
        self.last_ratio:      float                = 1.0
        self.last_method:     str                  = "auto"
        self._shape_error:    Optional[float]      = None

    # ── Učitavanje ────────────────────────────────────────────────────────────

    def load(self, path: str) -> None:
        """
        Učitava ASCII mesh fajl.
        Resetuje prethodni decimirani rezultat i keš greške.
        """
        verts, faces = load_mesh(path)
        self.source_path     = path
        self.original_verts  = verts
        self.original_faces  = faces
        self.decimated_verts = None
        self.decimated_faces = None
        self._shape_error    = None

    def is_loaded(self) -> bool:
        return self.original_verts is not None

    # ── Decimacija ────────────────────────────────────────────────────────────

    def run_decimate(self, ratio: float, method: str = "auto") -> None:
        """
        Pokreće decimaciju nad originalnim mesh-om.
        Čuva rezultat u decimated_verts / decimated_faces.
        Na kraju keš-ira Hausdorff grešku (i sav taj račun ostaje u istom
        worker thread-u — main thread ostaje slobodan).
        Može se pozivati više puta sa različitim parametrima.
        """
        if not self.is_loaded():
            raise RuntimeError("Mesh nije učitan.")

        self.last_ratio  = ratio
        self.last_method = method
        self._shape_error = None  # invalidate keš pre novog računa

        v, f = decimate(
            self.original_verts,
            self.original_faces,
            ratio,
            method,
        )
        self.decimated_verts = v
        self.decimated_faces = f

        # Precomputamo grešku u istom thread-u kao decimacija — dok worker
        # radi svoje, UI je slobodan. shape_error_pct() posle samo čita keš.
        self._shape_error = self._compute_shape_error()

    def has_decimated(self) -> bool:
        return self.decimated_verts is not None

    # ── Čuvanje ───────────────────────────────────────────────────────────────

    def save(self, path: str, decimated: bool = True) -> None:
        """
        Čuva mesh u ASCII formatu.
        decimated=True  → čuva decimirani mesh (ako postoji)
        decimated=False → čuva originalni mesh
        """
        if decimated and self.has_decimated():
            save_mesh(path, self.decimated_verts, self.decimated_faces)
        elif self.is_loaded():
            save_mesh(path, self.original_verts, self.original_faces)
        else:
            raise RuntimeError("Nema mesh-a za čuvanje.")

    # ── Statistike ────────────────────────────────────────────────────────────

    def original_stats(self) -> MeshStats:
        if not self.is_loaded():
            return MeshStats()
        return MeshStats(
            verts=len(self.original_verts),
            faces=len(self.original_faces),
        )

    def decimated_stats(self) -> MeshStats:
        if not self.has_decimated():
            return MeshStats()
        ov = len(self.original_verts)
        of = len(self.original_faces)
        dv = len(self.decimated_verts)
        df = len(self.decimated_faces)
        return MeshStats(
            verts=dv,
            faces=df,
            reduction_v=round((1 - dv / ov) * 100, 1) if ov else 0.0,
            reduction_f=round((1 - df / of) * 100, 1) if of else 0.0,
        )

    def shape_error_pct(self) -> float | None:
        """
        Vraća keširanu Hausdorff grešku (%), izračunatu u run_decimate.
        Trivijalan getter — bezbedno se poziva iz UI thread-a.
        """
        return self._shape_error

    def _compute_shape_error(self) -> float | None:
        """
        Hausdorff distance (orig → dec) normalizovan dijagonalom bounding box-a, u %.
        Težak račun — zove se iz worker thread-a, ne iz UI-ja.
        """
        if not self.has_decimated():
            return None
        try:
            orig = self.original_verts
            dec  = self.decimated_verts

            diag = float(np.linalg.norm(orig.max(axis=0) - orig.min(axis=0)))
            if diag == 0:
                return 0.0

            sample = orig if len(orig) <= 5000 else orig[
                np.random.default_rng(0).choice(len(orig), 5000, replace=False)]

            try:
                from scipy.spatial import cKDTree
                # workers=-1 → cKDTree query koristi sva CPU jezgra paralelno
                dists, _ = cKDTree(dec).query(sample, k=1, workers=-1)
            except ImportError:
                dists = np.sqrt(((sample[:, None] - dec[None]) ** 2).sum(axis=2)).min(axis=1)

            return round(float(dists.max()) / diag * 100, 2)
        except Exception:
            return None

    def stats_dict(self) -> dict:
        """Vraća sve statistike kao dict pogodan za prikaz u UI-u."""
        o = self.original_stats()
        d = self.decimated_stats()
        return {
            "orig_verts":   o.verts,
            "orig_faces":   o.faces,
            "dec_verts":    d.verts if self.has_decimated() else None,
            "dec_faces":    d.faces if self.has_decimated() else None,
            "reduction_v":  d.reduction_v,
            "reduction_f":  d.reduction_f,
            "method":       self.last_method,
            "ratio":        self.last_ratio,
            "source":       Path(self.source_path).name if self.source_path else "",
        }
