"""
core/decimator.py
Decimacija mesh-a sa chain fallback strategijom:
  pyfqmr → fast_simplification (QEM) → vertex_clustering

Sav I/O radi na numpy nizovima za brzinu i konzistentnost.
"""

from __future__ import annotations
import numpy as np


def decimate(
    verts: np.ndarray,
    faces: np.ndarray,
    ratio: float,
    method: str = "auto",
) -> tuple[np.ndarray, np.ndarray]:
    """
    Smanjuje broj trouglova uz očuvanje oblika.

    Parametri
    ---------
    verts   — np.ndarray (N, 3) float
    faces   — np.ndarray (M, 3) int
    ratio   — 0.0–1.0; 0.5 = 50% originalnog broja trouglova
    method  — "auto" | "pyfqmr" | "qem" | "cluster" | "uniform"
    """
    verts = np.asarray(verts, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int32)

    if ratio >= 1.0:
        return verts, faces

    target_f = max(4, int(len(faces) * ratio))
    target_v = max(4, int(len(verts) * ratio))

    if method == "pyfqmr":
        result = _try_pyfqmr(verts, faces, target_f)
        if result is not None:
            return result
        raise RuntimeError("pyfqmr nije dostupan ili nije uspio.")

    if method == "qem":
        result = _try_qem(verts, faces, target_f)
        if result is not None:
            return result
        raise RuntimeError("QEM decimacija nije uspela.")

    if method == "cluster":
        return _vertex_clustering(verts, faces, target_v)

    if method == "uniform":
        result = _uniform_remesh(verts, faces, target_v)
        if result is not None:
            return result
        result = _try_pyfqmr(verts, faces, target_f)
        if result is not None:
            return result
        return _vertex_clustering(verts, faces, target_v)

    # auto — proba redom, uvek završi
    result = _try_pyfqmr(verts, faces, target_f)
    if result is not None:
        return result

    result = _try_qem(verts, faces, target_f)
    if result is not None:
        return result

    return _vertex_clustering(verts, faces, target_v)


# ── Implementacije ────────────────────────────────────────────────────────────

def _try_pyfqmr(
    verts: np.ndarray, faces: np.ndarray, target_faces: int
) -> tuple[np.ndarray, np.ndarray] | None:
    """
    Quadric Edge Collapse — pyfqmr.
    Čuva konture zahvaljujući preserve_border=True.
    """
    try:
        import pyfqmr

        s = pyfqmr.Simplify()
        s.setMesh(
            np.ascontiguousarray(verts, dtype=np.float64),
            np.ascontiguousarray(faces, dtype=np.int32),
        )
        s.simplify_mesh(
            target_count=target_faces,
            aggressiveness=7,
            preserve_border=True,
            verbose=False,
        )
        v, f, _ = s.getMesh()
        return np.asarray(v, dtype=np.float64), np.asarray(f, dtype=np.int32)

    except ImportError:
        return None
    except Exception:
        return None


def _try_qem(
    verts: np.ndarray, faces: np.ndarray, target_faces: int
) -> tuple[np.ndarray, np.ndarray] | None:
    """
    QEM implementacija iz fast_simplification (ako je instaliran).
    """
    try:
        import fast_simplification as fs

        # fast_simplification očekuje flat cells niz sa vodećom brojkom 3
        n = len(faces)
        cells = np.empty((n, 4), dtype=np.int32)
        cells[:, 0]  = 3
        cells[:, 1:] = faces
        cells = cells.flatten()

        target_ratio = 1.0 - (target_faces / max(1, len(faces)))
        target_ratio = float(np.clip(target_ratio, 0.0, 0.99))

        pts_out, cells_out = fs.simplify(
            verts.astype(np.float64), cells, target_reduction=target_ratio
        )

        # cells_out je varijadičan format: [3, i, j, k, 3, i, j, k, ...]
        # jer smo poslali samo trouglove, možemo direktno da reshape-ujemo
        faces_out = cells_out.reshape(-1, 4)[:, 1:].astype(np.int32)
        return np.asarray(pts_out, dtype=np.float64), faces_out

    except ImportError:
        return None
    except Exception:
        return None


def _uniform_remesh(
    verts: np.ndarray, faces: np.ndarray, target_verts: int
) -> tuple[np.ndarray, np.ndarray] | None:
    """
    Uniform remesh via PyVista decimate + laplacian smooth.
    Daje ravnomernije raspoređene trouglove od QEC.
    """
    try:
        import pyvista as pv

        n = len(faces)
        cells = np.empty((n, 4), dtype=np.int32)
        cells[:, 0]  = 3
        cells[:, 1:] = faces
        cells = cells.flatten()
        mesh = pv.PolyData(verts, cells).clean().triangulate()

        target_red = float(
            np.clip(1.0 - target_verts / max(1, len(verts)), 0.01, 0.99)
        )
        remeshed = mesh.decimate(target_red, volume_preservation=True)
        remeshed = remeshed.smooth(n_iter=30, relaxation_factor=0.1)

        f_np = remeshed.faces.reshape(-1, 4)[:, 1:].astype(np.int32)
        return np.asarray(remeshed.points, dtype=np.float64), f_np
    except Exception:
        return None


def _vertex_clustering(
    verts: np.ndarray, faces: np.ndarray, target_verts: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    Vertex clustering — fallback koji ne zahteva nikakve biblioteke.
    Grupiše tačke u voksel grid i zamenjuje ih centroidima.
    """
    bbox_min  = verts.min(axis=0)
    bbox_max  = verts.max(axis=0)
    bbox_size = bbox_max - bbox_min
    bbox_size[bbox_size == 0] = 1.0

    # Veličina voksela — podešava se dok broj tačaka ne bude blizu targeta
    n_side = max(2, int(np.cbrt(target_verts)))

    cell_idx = np.floor(
        (verts - bbox_min) / bbox_size * (n_side - 1)
    ).astype(np.int32)
    cell_id = (
        cell_idx[:, 0] * n_side * n_side
        + cell_idx[:, 1] * n_side
        + cell_idx[:, 2]
    )

    # Centroidi po ćeliji
    unique_ids, inverse = np.unique(cell_id, return_inverse=True)
    new_verts = np.zeros((len(unique_ids), 3), dtype=np.float64)
    counts    = np.zeros(len(unique_ids), dtype=np.int32)
    np.add.at(new_verts, inverse, verts)
    np.add.at(counts,    inverse, 1)
    new_verts /= counts[:, None]

    # Remapovanje face indeksa
    new_faces = inverse[faces].astype(np.int32)

    # Uklanjanje degenerisanih trouglova (dve/tri tačke ista ćelija)
    mask = (
        (new_faces[:, 0] != new_faces[:, 1])
        & (new_faces[:, 1] != new_faces[:, 2])
        & (new_faces[:, 0] != new_faces[:, 2])
    )
    new_faces = new_faces[mask]

    return new_verts, new_faces
