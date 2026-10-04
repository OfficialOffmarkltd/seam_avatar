"""Measure how each candidate MakeHuman modifier changes Seam's ruler values.

The report is a prerequisite for calibration tuning: an optimiser can only
match a measurement when at least one modifier demonstrably moves it.

Usage:
    python scripts/sweep_modifiers.py
    python scripts/sweep_modifiers.py --output output/modifier_sweep.json
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from pipeline.calibration import BOUNDS, OPTIMISED_MODIFIERS
from pipeline.deform import HeadlessDeformer

ROOT = Path(__file__).parent.parent
DATA_PATH = ROOT / "vendor" / "makehuman" / "data"
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "sample_measurements.json"
SHOULDER_DISTANCE_MODIFIER = "measure/measure-shoulder-dist-decr|incr"


def values_to_sweep(bounds: tuple[float, float]) -> list[float]:
    """Use meaningful endpoints and the neutral value for one modifier."""
    lower, upper = bounds
    neutral = 0.5 if lower >= 0.0 else 0.0
    return [lower, neutral, upper]


def rounded(values: dict[str, float]) -> dict[str, float]:
    return {name: round(value, 3) for name, value in values.items()}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "output" / "modifier_sweep.json",
        help="path for the JSON report",
    )
    args = parser.parse_args()

    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    deformer = HeadlessDeformer(str(DATA_PATH))
    neutral = deformer.sample_measurements()

    candidates = list(zip(OPTIMISED_MODIFIERS, BOUNDS))
    # The shoulder target is inspected even before it joins the optimiser.
    candidates.append((SHOULDER_DISTANCE_MODIFIER, (-1.0, 1.0)))

    modifiers: list[dict] = []
    for modifier, bounds in candidates:
        targets = deformer._modifier_targets.get(modifier, [])
        entry: dict = {
            "modifier": modifier,
            "bounds": list(bounds),
            "resolved_target_count": len(targets),
            "samples": {},
        }

        for value in values_to_sweep(bounds):
            deformer.apply_modifiers({modifier: value})
            sampled = deformer.sample_measurements()
            deformer.reset()
            entry["samples"][str(value)] = {
                "measurements_mm": rounded(sampled),
                "delta_from_neutral_mm": rounded(
                    {name: sampled[name] - neutral[name] for name in neutral}
                ),
            }

        modifiers.append(entry)

    report = {
        "fixture_mm": fixture,
        "neutral_measurements_mm": rounded(neutral),
        "modifiers": modifiers,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"Neutral measurements: {rounded(neutral)}")
    print(f"Wrote sweep report: {args.output}")
    print("\nLargest absolute measurement changes by modifier:")
    for entry in modifiers:
        changes = [
            (abs(delta), name, delta)
            for sample in entry["samples"].values()
            for name, delta in sample["delta_from_neutral_mm"].items()
        ]
        _, name, delta = max(changes)
        print(
            f"  {entry['modifier']}: {name} {delta:+.1f} mm "
            f"({entry['resolved_target_count']} target(s))"
        )


if __name__ == "__main__":
    main()
