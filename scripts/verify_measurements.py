"""Inspect MakeHuman ruler measurements on the neutral and a known deformed mesh.

The demonstration target is MakeHuman's built-in bust-circumference increase.
It is intentionally applied directly, rather than through calibration, so this
script stays a simple, reproducible check of mesh topology and ruler routes.

Usage:
    python scripts/verify_measurements.py
    python scripts/verify_measurements.py --export

With --export, write neutral and deformed GLBs to output/ so they can be
compared in avatar-viewer.html.
"""

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.anchors import extract_anchors
from pipeline.calibration import MEASUREMENT_VERTEX_PAIRS
from pipeline.deform import load_base_body_mesh
from pipeline.export import export_gltf

DATA_PATH = Path(__file__).parent.parent / "vendor" / "makehuman" / "data"
TARGET_NAME = "targets/measure/measure-bust-circ-incr"


def sample_measurements(vertices: np.ndarray) -> dict[str, float]:
    """Return MakeHuman-ruler measurements in millimetres."""
    result: dict[str, float] = {}
    for name, pairs in MEASUREMENT_VERTEX_PAIRS.items():
        result[name] = sum(
            float(np.linalg.norm(vertices[start] - vertices[end]))
            for start, end in pairs
        )
    return result


def apply_target(
    vertices: np.ndarray, target_archive: Path, target_name: str
) -> np.ndarray:
    """Apply one compiled MakeHuman target to millimetre-space vertices."""
    with np.load(target_archive, allow_pickle=False) as targets:
        indices = targets[f"{target_name}.index"]
        # Target vectors decode to decimetres with * 1e-3, then to mm with * 100.
        displacements_mm = targets[f"{target_name}.vector"] * 1e-1

    result = vertices.copy()
    result[indices] += displacements_mm
    return result


def print_measurement_report(
    neutral: dict[str, float],
    deformed: dict[str, float],
) -> None:
    print("\nMeasurement                         neutral       deformed       change")
    print("-" * 72)
    for name, baseline in neutral.items():
        after = deformed[name]
        print(
            f"{name:<28} {baseline:8.1f} mm  {after:8.1f} mm  {after - baseline:+8.1f} mm"
        )


def print_anchor_report(neutral: np.ndarray, deformed: np.ndarray) -> None:
    neutral_anchors = {
        anchor.name: anchor.position for anchor in extract_anchors(neutral)
    }
    deformed_anchors = {
        anchor.name: anchor.position for anchor in extract_anchors(deformed)
    }

    print("\nChest-anchor displacement after bust increase")
    print("-" * 72)
    for name in ("chest_front_centre", "left_chest_side", "right_chest_side"):
        before = np.asarray(neutral_anchors[name])
        after = np.asarray(deformed_anchors[name])
        delta = after - before
        print(
            f"{name:<28} dx={delta[0]:+7.1f}  dy={delta[1]:+7.1f}  dz={delta[2]:+7.1f} mm"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--export", action="store_true", help="write neutral and demo GLBs to output/"
    )
    args = parser.parse_args()

    neutral, faces = load_base_body_mesh(DATA_PATH / "3dobjs" / "base.obj")
    neutral *= 100.0
    neutral[:, 1] -= neutral[:, 1].min()

    deformed = apply_target(
        neutral,
        DATA_PATH / "targets" / "targets.npz",
        TARGET_NAME,
    )

    print(f"Known target: {TARGET_NAME} at weight 1.0")
    print_measurement_report(
        sample_measurements(neutral), sample_measurements(deformed)
    )
    print_anchor_report(neutral, deformed)

    if args.export:
        output_dir = Path(__file__).parent.parent / "output"
        output_dir.mkdir(exist_ok=True)
        for filename, vertices in (
            ("measurements_neutral.glb", neutral),
            ("measurements_bust_increased.glb", deformed),
        ):
            path = output_dir / filename
            path.write_bytes(export_gltf(vertices, faces, extract_anchors(vertices)))
            print(f"Exported {path}")


if __name__ == "__main__":
    main()
