"""Export the canonical static avatar fixture used by the Seam MVP.

Usage:
    ./.venv/bin/python scripts/export_neutral_fixture.py

The MakeHuman data remains an input asset. The generated GLB and manifest are
the versioned avatar contract consumed by the backend adapter.
"""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from anchor_map import ANCHOR_MAP
from pipeline.anchors import extract_anchors
from pipeline.deform import load_base_body_mesh
from pipeline.export import export_gltf


ROOT = Path(__file__).parent.parent
DATA_PATH = Path(
    os.environ.get("MAKEHUMAN_DATA_PATH", str(ROOT / "vendor" / "makehuman" / "data"))
)
OUTPUT_DIR = ROOT / "output"
GLB_PATH = OUTPUT_DIR / "avatar_neutral_v1.glb"
MANIFEST_PATH = OUTPUT_DIR / "avatar_neutral_v1.json"


def main() -> None:
    vertices, faces = load_base_body_mesh(DATA_PATH / "3dobjs" / "base.obj")
    vertices = vertices * 100.0
    vertices[:, 1] -= vertices[:, 1].min()

    anchors = extract_anchors(vertices)
    glb = export_gltf(vertices, faces, anchors)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    GLB_PATH.write_bytes(glb)

    manifest = {
        "schema_version": 1,
        "avatar_version": "fixed-avatar-v1",
        "units": "millimetres",
        "coordinate_system": "seam_avatar_v1",
        "mesh": GLB_PATH.name,
        "vertex_count": int(len(vertices)),
        "triangle_count": int(len(faces)),
        "anchor_count": len(ANCHOR_MAP),
        "anchor_names": list(ANCHOR_MAP),
    }
    MANIFEST_PATH.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {GLB_PATH}")
    print(f"Wrote {MANIFEST_PATH}")
    print(f"Vertices: {len(vertices)}")
    print(f"Triangles: {len(faces)}")
    print(f"Anchors: {len(anchors)}")


if __name__ == "__main__":
    main()
