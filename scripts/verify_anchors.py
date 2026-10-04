"""
verify_anchors.py — Anchor map development tool

Loads the MakeHuman base mesh headlessly, finds the closest vertex to each
candidate anchor position, exports a .glb with the anchors embedded in
scene.extras, and prints the resulting ANCHOR_MAP dict ready to paste into
anchor_map.py.

Usage:
    python scripts/verify_anchors.py

Output:
    output/anchors_preview.glb  — drag this into avatar-viewer.html to see
                                   the orange dots on the mesh

Workflow:
    1. Run the script
    2. Open avatar-viewer.html in a browser
    3. Drag anchors_preview.glb onto the viewport
    4. Click "Anchors" button — orange dots appear on the mesh
    5. If a dot is in the wrong place, adjust the coordinates below and re-run
    6. When all dots look correct, copy the printed ANCHOR_MAP into anchor_map.py
"""

import json
import os
import struct
import sys
from pathlib import Path

import numpy as np

# Make the repository root importable when invoked as
# ``python scripts/verify_anchors.py``.
sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.deform import load_base_body_mesh

# ---------------------------------------------------------------------------
# Configuration — set MAKEHUMAN_DATA_PATH or edit this directly
# ---------------------------------------------------------------------------
MAKEHUMAN_DATA_PATH = os.environ.get(
    "MAKEHUMAN_DATA_PATH",
    str(Path(__file__).parent.parent / "vendor" / "makehuman" / "data"),
)

OUTPUT_DIR = Path(__file__).parent.parent / "output"
OUTPUT_GLB = OUTPUT_DIR / "anchors_preview.glb"

# ---------------------------------------------------------------------------
# Candidate anchor positions in MakeHuman internal units (decimetres, Y-up).
# Adjust these values if the dots land in the wrong place in the viewer.
# The script will find the NEAREST vertex to each position.
# ---------------------------------------------------------------------------
CANDIDATE_POSITIONS: dict[str, list[float]] = {
    # Mesh is centred at Y=0. Head top ≈ +8.5dm, feet ≈ -8.5dm.
    # Waist is near Y=0, chest ≈ +2.5dm, shoulders ≈ +5.5dm, neck ≈ +6.5dm
    # All values in decimetres (raw base.obj units).
    "neck_base_front":    [ 0.00,  5.75,  0.55],
    "neck_base_back":     [ 0.00,  5.75, -0.45],
    "neck_base_left":     [-0.35,  5.75,  0.05],
    "neck_base_right":    [ 0.35,  5.75,  0.05],
    "left_shoulder":      [-1.40,  5.30,  0.05],
    "right_shoulder":     [ 1.40,  5.30,  0.05],
    "left_underarm":      [-1.50,  4.50,  0.10],
    "right_underarm":     [ 1.50,  4.50,  0.10],
    "chest_front_centre": [ 0.00,  3.50,  1.10],
    "chest_back_centre":  [ 0.00,  3.50, -0.80],
    "left_chest_side":    [-1.60,  3.50,  0.15],
    "right_chest_side":   [ 1.60,  3.50,  0.15],
    "waist_front":        [ 0.00,  2.10,  0.90],
    "waist_back":         [ 0.00,  2.10, -0.65],
    "waist_left":         [-1.30,  2.10,  0.10],
    "waist_right":        [ 1.30,  2.10,  0.10],
    "hip_front":          [ 0.00,  0.50,  1.10],
    "hip_back":           [ 0.00,  0.50, -0.80],
    "hip_left":           [-1.30,  0.50,  0.10],
    "hip_right":          [ 1.30,  0.50,  0.10],
    "crotch_point":       [ 0.00,  0.25,  0.90],
    "left_knee":          [-1.65, -3.90,  0.20],
    "right_knee":         [ 1.65, -3.90,  0.20],
    "left_wrist":         [-8.60,  3.60,  -0.80],
    "right_wrist":        [ 8.60,  3.60,  -0.80],
}


# ---------------------------------------------------------------------------
# Step 1 — load mesh
# ---------------------------------------------------------------------------
def load_mesh(data_path: str) -> tuple[np.ndarray, np.ndarray]:
    obj_path = Path(data_path) / "3dobjs" / "base.obj"
    if not obj_path.exists():
        print(f"ERROR: base.obj not found at {obj_path}")
        print("Run scripts/fetch_mh_data.sh first.")
        sys.exit(1)

    print(f"Loading mesh from {obj_path} ...")
    verts, faces = load_base_body_mesh(obj_path)

    print(f"  {len(verts)} vertices, {len(faces)} body faces")
    print("  Raw units (dm):")
    print(f"    X: {verts[:, 0].min():.3f} to {verts[:, 0].max():.3f}")
    print(f"    Y: {verts[:, 1].min():.3f} to {verts[:, 1].max():.3f}")
    print(f"    Z: {verts[:, 2].min():.3f} to {verts[:, 2].max():.3f}")

    return verts, faces


# ---------------------------------------------------------------------------
# Step 2 — find nearest vertex for each anchor
# ---------------------------------------------------------------------------
def find_anchors(
    verts: np.ndarray,
    faces: np.ndarray,
    candidates: dict[str, list[float]],
) -> dict[str, dict]:
    """
    For each candidate position, find the index of the nearest vertex.
    Returns a dict: name → {index, position_dm, position_mm}

    Positions are stored in viewer-space mm: Y=0 at the feet (same offset
    the viewer applies when it translates the model so box.min.y = 0).
    """
    # Offset so feet sit at Y=0 — matches what the viewer does to the model
    y_offset_dm = float(abs(verts[:, 1].min()))
    print(f"\n  Y offset to floor: {y_offset_dm:.3f} dm ({y_offset_dm * 100:.1f} mm)")

    # Search only anatomical-body vertices.  The source OBJ includes helper
    # geometry (skirt, hair, eyes, joints, etc.); choosing one of those points
    # creates an anchor that is not on the avatar surface exported by the
    # service.
    body_indices = np.unique(faces.reshape(-1))
    body_verts = verts[body_indices]

    anchors = {}
    print(f"\nSearching {len(body_indices)} body-surface vertices ...")

    for name, target in candidates.items():
        t = np.array(target, dtype=np.float32)
        distances = np.linalg.norm(body_verts - t, axis=1)
        nearest_position = int(np.argmin(distances))
        idx = int(body_indices[nearest_position])
        pos_dm = verts[idx].tolist()

        # Shift Y by the floor offset, convert to mm
        pos_mm = [
            round(pos_dm[0] * 100, 2),
            round((pos_dm[1] + y_offset_dm) * 100, 2),
            round(pos_dm[2] * 100, 2),
        ]

        anchors[name] = {
            "index":       idx,
            "position_dm": pos_dm,
            "position_mm": pos_mm,
            "distance":    float(distances[nearest_position]),
        }

        print(
            f"  {name:<25} idx={idx:<6} "
            f"pos_dm=[{pos_dm[0]:6.3f}, {pos_dm[1]:6.3f}, {pos_dm[2]:6.3f}] "
            f"dist={distances[idx]:.3f}dm"
        )

    return anchors


# ---------------------------------------------------------------------------
# Step 3 — print ANCHOR_MAP ready to paste into anchor_map.py
# ---------------------------------------------------------------------------
def print_anchor_map(anchors: dict[str, dict]) -> None:
    print("\n" + "=" * 60)
    print("# Paste this into anchor_map.py:")
    print("ANCHOR_MAP: dict[str, int] = {")
    for name, info in anchors.items():
        pos = info["position_dm"]
        print(
            f'    "{name}": {info["index"]},  '
            f'# dm: [{pos[0]:.3f}, {pos[1]:.3f}, {pos[2]:.3f}]'
        )
    print("}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Step 4 — export .glb with anchors in scene.extras
# ---------------------------------------------------------------------------
def export_glb(
    verts: np.ndarray,
    faces: np.ndarray,
    anchors: dict[str, dict],
    output_path: Path,
) -> None:
    """
    Export a minimal binary glTF 2.0 (.glb) with:
      - The body mesh (vertices in mm, Y-up)
      - Anchor positions in scene.extras.avatar_anchors
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Convert vertices to mm for the export
    verts_mm = (verts * 100.0).astype(np.float32)

    # Compute vertex normals
    normals = compute_normals(verts_mm, faces)

    # Build avatar_anchors extras for scene.extras
    avatar_anchors = [
        {
            "name":     name,
            "position": info["position_mm"],
            "vertex_index": info["index"],
        }
        for name, info in anchors.items()
    ]

    # Build glTF JSON + binary buffer manually
    # (avoids pygltflib dependency for this utility script)
    vert_bytes   = verts_mm.tobytes()
    normal_bytes = normals.tobytes()
    face_bytes   = faces.astype(np.uint32).tobytes()

    # Single buffer containing: vertices | normals | indices
    buffer_data = vert_bytes + normal_bytes + face_bytes
    buffer_len  = len(buffer_data)

    n_verts = len(verts_mm)
    n_faces = len(faces) * 3  # number of indices

    v_min = verts_mm.min(axis=0).tolist()
    v_max = verts_mm.max(axis=0).tolist()

    gltf = {
        "asset":    {"version": "2.0", "generator": "seam_avatar verify_anchors.py"},
        "scene":    0,
        "scenes":   [{"nodes": [0], "extras": {"avatar_anchors": avatar_anchors}}],
        "nodes":    [{"mesh": 0}],
        "meshes":   [{
            "primitives": [{
                "attributes": {"POSITION": 0, "NORMAL": 1},
                "indices": 2,
                "mode": 4,
            }]
        }],
        "accessors": [
            {   # 0 — POSITION
                "bufferView": 0, "componentType": 5126, "count": n_verts,
                "type": "VEC3", "min": v_min, "max": v_max,
            },
            {   # 1 — NORMAL
                "bufferView": 1, "componentType": 5126,
                "count": n_verts, "type": "VEC3",
            },
            {   # 2 — indices
                "bufferView": 2, "componentType": 5125,
                "count": n_faces, "type": "SCALAR",
            },
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0,                        "byteLength": len(vert_bytes)},
            {"buffer": 0, "byteOffset": len(vert_bytes),          "byteLength": len(normal_bytes)},
            {"buffer": 0, "byteOffset": len(vert_bytes) + len(normal_bytes), "byteLength": len(face_bytes)},
        ],
        "buffers": [{"byteLength": buffer_len}],
    }

    json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")

    # Pad JSON to 4-byte alignment
    json_pad = (4 - len(json_bytes) % 4) % 4
    json_bytes += b" " * json_pad

    # Pad binary to 4-byte alignment
    bin_pad = (4 - buffer_len % 4) % 4
    buffer_data += b"\x00" * bin_pad

    # glTF binary (GLB) format:
    # 12-byte header | JSON chunk | BIN chunk
    total_length = 12 + 8 + len(json_bytes) + 8 + len(buffer_data) + bin_pad

    with open(output_path, "wb") as f:
        # GLB header
        f.write(struct.pack("<III", 0x46546C67, 2, total_length))  # magic, version, length
        # JSON chunk
        f.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))   # length, type=JSON
        f.write(json_bytes)
        # BIN chunk
        f.write(struct.pack("<II", len(buffer_data) + bin_pad, 0x004E4942))  # length, type=BIN
        f.write(buffer_data)

    print(f"\nExported: {output_path}")
    print(f"  File size: {output_path.stat().st_size / 1024:.1f} KB")
    print(f"  Anchors embedded: {len(avatar_anchors)}")
    print("\nDrag the .glb into avatar-viewer.html and click 'Anchors' to verify.")


def compute_normals(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]
    face_normals = np.cross(v1 - v0, v2 - v0).astype(np.float32)
    vertex_normals = np.zeros_like(verts)
    np.add.at(vertex_normals, faces[:, 0], face_normals)
    np.add.at(vertex_normals, faces[:, 1], face_normals)
    np.add.at(vertex_normals, faces[:, 2], face_normals)
    norms = np.linalg.norm(vertex_normals, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (vertex_normals / norms).astype(np.float32)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    print(f"MAKEHUMAN_DATA_PATH: {MAKEHUMAN_DATA_PATH}\n")

    verts, faces = load_mesh(MAKEHUMAN_DATA_PATH)
    anchors = find_anchors(verts, faces, CANDIDATE_POSITIONS)
    print_anchor_map(anchors)
    export_glb(verts, faces, anchors, OUTPUT_GLB)
