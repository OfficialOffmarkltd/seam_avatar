import json
from pathlib import Path

import numpy as np
import pytest
import trimesh

from anchor_map import ANCHOR_MAP
from pipeline.anchors import extract_anchors
from pipeline.deform import load_base_body_mesh


ROOT = Path(__file__).parent.parent
DATA_PATH = Path(
    __import__("os").environ.get(
        "MAKEHUMAN_DATA_PATH", str(ROOT / "vendor" / "makehuman" / "data")
    )
)
FIXTURE_PATH = ROOT / "output" / "avatar_neutral_v1.glb"
MANIFEST_PATH = ROOT / "output" / "avatar_neutral_v1.json"


def require_data() -> None:
    if not (DATA_PATH / "3dobjs" / "base.obj").exists():
        pytest.skip("MakeHuman data assets are not present")


def test_anchor_map_contains_body_surface_vertices() -> None:
    require_data()
    _, faces = load_base_body_mesh(DATA_PATH / "3dobjs" / "base.obj")
    body_indices = set(np.unique(faces).tolist())

    assert len(ANCHOR_MAP) == 25
    assert set(ANCHOR_MAP.values()) <= body_indices


def test_neutral_fixture_matches_avatar_contract() -> None:
    require_data()
    assert FIXTURE_PATH.exists()
    assert MANIFEST_PATH.exists()

    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 1
    assert manifest["avatar_version"] == "fixed-avatar-v1"
    assert manifest["units"] == "millimetres"
    assert manifest["coordinate_system"] == "seam_avatar_v1"
    assert manifest["anchor_count"] == 25

    scene = trimesh.load(FIXTURE_PATH, force="scene")
    assert scene.bounds[0][1] == pytest.approx(0.0, abs=0.1)
    assert len(scene.geometry) == 1

    anchors = scene.metadata["avatar_anchors"]
    assert len(anchors) == 25
    assert {anchor["name"] for anchor in anchors} == set(ANCHOR_MAP)
