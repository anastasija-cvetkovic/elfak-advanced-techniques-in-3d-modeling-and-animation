"""
Decimacija mesh-a: VTK decimate → pyfqmr → fast_simplification (QEM) → clustering.

U režimu "auto" se pokreću svi dostupni kandidati i bira se onaj sa najmanjom
`_shape_error`. Sav I/O radi na numpy nizovima.
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

    verts  — (N, 3) float, faces — (M, 3) int
    ratio  — 0.0–1.0; 0.5 = 50% originalnog broja trouglova
    method — "auto" | "vtk" | "vtk_pro" | "pyfqmr" | "qem" | "cluster"
    """
    verts = np.asarray(verts, dtype=np.float64)
    faces = np.asarray(faces, dtype=np.int32)

    if ratio >= 1.0:
        return verts, faces

    target_f = max(4, int(len(faces) * ratio))
    target_v = max(4, int(len(verts) * ratio))

    if method in ("vtk", "vtk_pro", "uniform"):
        # "uniform" je alias radi kompatibilnosti sa starijim pozivima
        result = _try_vtk(verts, faces, target_f, pro=(method == "vtk_pro"))
        if result is not None:
            return result
        raise RuntimeError("VTK decimacija nije uspela (pyvista nedostupan?).")

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

    candidates = []
    for fn in (_try_vtk, _try_pyfqmr, _try_qem):
        r = fn(verts, faces, target_f)
        if r is not None and len(r[1]) > 0:
            candidates.append(r)

    if not candidates:
        return _vertex_clustering(verts, faces, target_v)

    return min(candidates, key=lambda r: _shape_error(verts, r[0], target_f, len(r[1])))


# ── Ocenjivanje kandidata ─────────────────────────────────────────────────────

def _max_nn_distance(src: np.ndarray, dst: np.ndarray) -> float:
    """Najveća udaljenost tačke iz `src` do najbliže tačke u `dst`."""
    try:
        from scipy.spatial import cKDTree
        return float(cKDTree(dst).query(src)[0].max())
    except ImportError:
        pass

    # numpy fallback: |a-b|² = |a|² - 2ab + |b|², bez (n, m, 3) međurezultata
    dst_sq = (dst ** 2).sum(axis=1)
    worst = 0.0
    step = max(1, 4_000_000 // max(1, len(dst)))
    for i in range(0, len(src), step):
        chunk = src[i:i + step]
        d2 = (chunk ** 2).sum(axis=1)[:, None] - 2.0 * (chunk @ dst.T) + dst_sq[None, :]
        worst = max(worst, float(np.sqrt(max(0.0, d2.min(axis=1).max()))))
    return worst


def _shape_error(
    orig_verts: np.ndarray, new_verts: np.ndarray, target_f: int, got_f: int
) -> float:
    """
    Manje je bolje. Kombinuje geometrijsku vernost, očuvanje siluete (rast
    bounding box-a) i promašaj ciljnog broja trouglova.
    """
    err = _max_nn_distance(orig_verts, new_verts)

    lo0, hi0 = orig_verts.min(axis=0), orig_verts.max(axis=0)
    grow = max(
        float(np.max(new_verts.max(axis=0) - hi0)),
        float(np.max(lo0 - new_verts.min(axis=0))),
        0.0,
    )

    miss = max(1.0, got_f / max(1, target_f))

    return (err + 5.0 * grow) * miss


# ── Implementacije ────────────────────────────────────────────────────────────

def _try_pyfqmr(
    verts: np.ndarray, faces: np.ndarray, target_faces: int
) -> tuple[np.ndarray, np.ndarray] | None:
    """Quadric Edge Collapse — pyfqmr."""
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
    """QEM implementacija iz fast_simplification (ako je instaliran)."""
    try:
        import fast_simplification as fs

        # fast_simplification traži trouglove kao 2D (N, 3) niz
        target_ratio = 1.0 - (target_faces / max(1, len(faces)))
        target_ratio = float(np.clip(target_ratio, 0.0, 0.99))

        pts_out, faces_out = fs.simplify(
            verts.astype(np.float64),
            np.ascontiguousarray(faces, dtype=np.int32),
            target_reduction=target_ratio,
        )

        return (np.asarray(pts_out, dtype=np.float64),
                np.asarray(faces_out, dtype=np.int32))

    except ImportError:
        return None
    except Exception:
        return None


def _try_vtk(
    verts: np.ndarray, faces: np.ndarray, target_faces: int, pro: bool = False
) -> tuple[np.ndarray, np.ndarray] | None:
    """
    VTK/pyvista quadric decimate — primarna metoda. Namerno bez smoothing-a,
    koji skuplja model i uništava konturu.

    pro=True koristi `decimate_pro`: samo uklanja postojeća temena i nikad ih
    ne pomera, pa nijedna nova tačka ne može da izađe van originalne siluete.
    """
    try:
        import pyvista as pv

        n = len(faces)
        cells = np.empty((n, 4), dtype=np.int32)
        cells[:, 0]  = 3
        cells[:, 1:] = faces
        mesh = pv.PolyData(verts, cells.ravel()).clean().triangulate()

        target_red = float(
            np.clip(1.0 - target_faces / max(1, len(faces)), 0.01, 0.99)
        )
        if pro:
            out = mesh.decimate_pro(target_red, preserve_topology=True)
        else:
            out = mesh.decimate(target_red, volume_preservation=True)

        f_np = out.faces.reshape(-1, 4)[:, 1:].astype(np.int32)
        if len(f_np) == 0:
            return None
        return np.asarray(out.points, dtype=np.float64), f_np
    except Exception:
        return None


_CLUSTER_MAX_SIDE = 4096  # gornja granica rezolucije grida (4096³ staje u int64)


def _cell_ids(verts: np.ndarray, n_side: int) -> np.ndarray:
    """Linearni indeks voksel ćelije za svako teme, pri rezoluciji `n_side`."""
    bbox_min  = verts.min(axis=0)
    bbox_size = verts.max(axis=0) - bbox_min
    bbox_size[bbox_size == 0] = 1.0

    cell_idx = np.floor((verts - bbox_min) / bbox_size * n_side).astype(np.int64)
    np.clip(cell_idx, 0, n_side - 1, out=cell_idx)   # tačke na max granici

    return (
        cell_idx[:, 0] * n_side * n_side
        + cell_idx[:, 1] * n_side
        + cell_idx[:, 2]
    )


def _cluster_at(
    verts: np.ndarray, faces: np.ndarray, n_side: int
) -> tuple[np.ndarray, np.ndarray]:
    """Jedan prolaz klasterovanja pri fiksnoj rezoluciji grida."""
    unique_ids, inverse = np.unique(_cell_ids(verts, n_side), return_inverse=True)
    inverse = inverse.ravel()

    # Centroidi po ćeliji
    new_verts = np.zeros((len(unique_ids), 3), dtype=np.float64)
    counts    = np.zeros(len(unique_ids), dtype=np.int64)
    np.add.at(new_verts, inverse, verts)
    np.add.at(counts,    inverse, 1)
    new_verts /= counts[:, None]

    # Remapovanje face indeksa
    new_faces = inverse[faces].astype(np.int32)

    # Uklanjanje degenerisanih trouglova (dve/tri tačke u istoj ćeliji)
    mask = (
        (new_faces[:, 0] != new_faces[:, 1])
        & (new_faces[:, 1] != new_faces[:, 2])
        & (new_faces[:, 0] != new_faces[:, 2])
    )
    new_faces = new_faces[mask]

    # Deduplikacija: više originalnih trouglova može da padne na isti trojac.
    # Ključ je sortiran trojac, ali vraćamo originalne redove da se ne pokvari
    # orijentacija (winding).
    if len(new_faces):
        _, keep = np.unique(np.sort(new_faces, axis=1), axis=0, return_index=True)
        new_faces = new_faces[np.sort(keep)]

    return new_verts, new_faces


def _vertex_clustering(
    verts: np.ndarray, faces: np.ndarray, target_verts: int
) -> tuple[np.ndarray, np.ndarray]:
    """
    Vertex clustering — fallback bez dodatnih biblioteka. Grupiše tačke u
    voksel grid i zamenjuje ih centroidima.

    Rezolucija grida se traži binarnom pretragom umesto zatvorenom formulom:
    mesh je površ, pa broj zauzetih ćelija raste kao n_side², a konstanta
    proporcionalnosti zavisi od modela. `cbrt(target)` je zato promašivao
    ciljni broj temena i po red veličine.
    """
    target_verts = max(4, int(target_verts))

    # Traži se najmanji n_side čiji broj zauzetih ćelija dostiže target.
    # Dovoljno je brojati ćelije — centroidi i remapovanje se rade jednom, na kraju.
    def n_cells(n_side: int) -> int:
        return len(np.unique(_cell_ids(verts, n_side)))

    # 1) Udvostručavanje dok se ne pređe target (bez heuristike o obliku modela).
    lo, hi = 2, 2
    while n_cells(hi) < target_verts and hi < _CLUSTER_MAX_SIDE:
        lo = hi
        hi = min(hi * 2, _CLUSTER_MAX_SIDE)

    # 2) Binarna pretraga u nađenom opsegu; pamti se najbliži viđeni kandidat,
    #    jer gridovi različitih rezolucija nisu ugnježdeni pa broj ćelija ume
    #    da odstupi od savršene monotonosti.
    best_side, best_gap = hi, abs(n_cells(hi) - target_verts)
    while lo <= hi:
        mid = (lo + hi) // 2
        got = n_cells(mid)
        gap = abs(got - target_verts)
        if gap < best_gap or (gap == best_gap and mid < best_side):
            best_side, best_gap = mid, gap
        if got < target_verts:
            lo = mid + 1
        else:
            hi = mid - 1

    new_verts, new_faces = _cluster_at(verts, faces, best_side)

    # 3) Guard: pri vrlo agresivnoj redukciji sve može da se sruči u nekoliko
    #    ćelija i ne ostane nijedan trougao. Podiže se rezolucija dok mesh ne
    #    postane validan — bolje promašiti target nego vratiti prazan model.
    side = best_side
    while len(new_faces) == 0 and side < _CLUSTER_MAX_SIDE:
        side = min(side * 2, _CLUSTER_MAX_SIDE)
        new_verts, new_faces = _cluster_at(verts, faces, side)

    return new_verts, new_faces
