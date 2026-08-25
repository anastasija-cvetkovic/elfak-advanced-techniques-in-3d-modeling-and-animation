"""
core/decimator.py
Decimacija mesh-a sa chain fallback strategijom:
  pyfqmr → qem_decimate → vertex_clustering
"""

from __future__ import annotations
import numpy as np


def decimate(
    verts: list,
    faces: list,
    ratio: float,
    method: str = "auto",
) -> tuple[list, list]:
    """
    Smanjuje broj trouglova uz očuvanje oblika.

    Parametri
    ---------
    verts   — lista [x, y, z] tačaka
    faces   — lista [a, b, c] indeksa trouglova
    ratio   — 0.0–1.0; 0.5 = 50% originalnog broja trouglova
    method  — "auto" | "pyfqmr" | "qem" | "cluster"

    Vraća (verts, faces) kao liste listi.
    """
    if ratio >= 1.0:
        return verts, faces

    target_f = max(4, int(len(faces) * ratio))
    target_v = max(4, int(len(verts) * ratio))

    if method == "pyfqmr":
        result = _try_pyfqmr(verts, faces, target_f)
        if result:
            return result
        raise RuntimeError("pyfqmr nije dostupan ili nije uspio.")

    if method == "qem":
        result = _try_qem(verts, faces, target_f)
        if result:
            return result
        raise RuntimeError("QEM decimacija nije uspela.")

    if method == "cluster":
        return _vertex_clustering(verts, faces, target_v)

    if method == "uniform":
        result = _uniform_remesh(verts, faces, target_v)
        if result:
            return result
        result = _try_pyfqmr(verts, faces, target_f)
        if result:
            return result
        return _vertex_clustering(verts, faces, target_v)

    # auto — proba redom, uvek završi
    result = _try_pyfqmr(verts, faces, target_f)
    if result:
        return result

    result = _try_qem(verts, faces, target_f)
    if result:
        return result

    return _vertex_clustering(verts, faces, target_v)


# ── Implementacije ────────────────────────────────────────────────────────────

def _try_pyfqmr(
    verts: list, faces: list, target_faces: int
) -> tuple[list, list] | None:
    """
    Quadric Edge Collapse — pyfqmr.
    Čuva konture zahvaljujući preserve_border=True.
    """
    try:
        import pyfqmr

        s = pyfqmr.Simplify()
        s.setMesh(
            np.array(verts, dtype=np.float64),
            np.array(faces, dtype=np.int32),
        )
        s.simplify_mesh(
            target_count=target_faces,
            aggressiveness=7,
            preserve_border=True,
            verbose=False,
        )
        v, f, _ = s.getMesh()
        return v.tolist(), f.tolist()

    except ImportError:
        return None
    except Exception:
        return None


def _try_qem(
    verts: list, faces: list, target_faces: int
) -> tuple[list, list] | None:
    """
    QEM implementacija iz fast_simplification (ako je instaliran).
    """
    try:
        import fast_simplification as fs
        import numpy as np

        pts = np.array(verts, dtype=np.float64)
        cells = np.hstack(
            [np.full((len(faces), 1), 3), np.array(faces, dtype=np.int32)]
        ).flatten()

        target_ratio = 1.0 - (target_faces / max(1, len(faces)))
        target_ratio = float(np.clip(target_ratio, 0.0, 0.99))

        pts_out, cells_out = fs.simplify(pts, cells, target_reduction=target_ratio)

        faces_out = []
        i = 0
        while i < len(cells_out):
            n = cells_out[i]; i += 1
            if n == 3:
                faces_out.append(cells_out[i:i+3].tolist())
            i += n

        return pts_out.tolist(), faces_out

    except ImportError:
        return None
    except Exception:
        return None


def _uniform_remesh(
    verts: list, faces: list, target_verts: int
) -> tuple[list, list] | None:
    """
    Uniform remesh via PyVista decimate + laplacian smooth.
    Daje ravnomernije raspoređene trouglove od QEC.
    """
    try:
        import pyvista as pv
        import numpy as np

        pts   = np.array(verts, dtype=np.float64)
        cells = np.hstack([
            np.full((len(faces), 1), 3, dtype=np.int32),
            np.array(faces, dtype=np.int32),
        ]).flatten()
        mesh = pv.PolyData(pts, cells).clean().triangulate()

        target_red = float(np.clip(1.0 - target_verts / max(1, len(verts)), 0.01, 0.99))
        remeshed   = mesh.decimate(target_red, volume_preservation=True)
        remeshed   = remeshed.smooth(n_iter=30, relaxation_factor=0.1)

        f_np = remeshed.faces.reshape(-1, 4)
        return remeshed.points.tolist(), f_np[:, 1:].tolist()
    except Exception:
        return None


def _vertex_clustering(
    verts: list, faces: list, target_verts: int
) -> tuple[list, list]:
    """
    Vertex clustering — fallback koji ne zahteva nikakve biblioteke.
    Grupiše tačke u voksel grid i zamenjuje ih centroidima.
    """
    pts = np.array(verts, dtype=np.float64)
    fcs = np.array(faces, dtype=np.int32)

    bbox_min = pts.min(axis=0)
    bbox_max = pts.max(axis=0)
    bbox_size = bbox_max - bbox_min
    bbox_size[bbox_size == 0] = 1.0

    # Veličina voksela — podešava se dok broj tačaka ne bude blizu targeta
    n_side = max(2, int(np.cbrt(target_verts)))

    cell_idx = np.floor(
        (pts - bbox_min) / bbox_size * (n_side - 1)
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
    np.add.at(new_verts, inverse, pts)
    np.add.at(counts,    inverse, 1)
    new_verts /= counts[:, None]

    # Remapovanje face indeksa
    new_faces = inverse[fcs]

    # Uklanjanje degenerisanih trouglova (sve 3 tačke iste ćelije)
    mask = (
        (new_faces[:, 0] != new_faces[:, 1])
        & (new_faces[:, 1] != new_faces[:, 2])
        & (new_faces[:, 0] != new_faces[:, 2])
    )
    new_faces = new_faces[mask]

    return new_verts.tolist(), new_faces.tolist()
