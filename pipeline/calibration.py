from __future__ import annotations

from itertools import pairwise

from anchor_map import ANCHOR_MAP
from models import BodyMeasurements


# ---------------------------------------------------------------------------
# Measurement vertex pairs
# MakeHuman's Ruler.Measures paths from
# makehuman/plugins/0_modeling_a_measurement.py.  Each path is an ordered
# surface route; pairwise(route) converts it into the line segments that
# MakeHuman itself sums for its on-screen measurement ruler.
# ---------------------------------------------------------------------------
def _adjacent_pairs(route: tuple[int, ...]) -> list[tuple[int, int]]:
    return list(pairwise(route))


MEASUREMENT_VERTEX_PAIRS: dict[str, list[tuple[int, int]]] = {
    # measure/measure-bust-circ-decr|incr
    "chest": _adjacent_pairs(
        (
            8439,
            8455,
            8462,
            8446,
            8478,
            8494,
            8557,
            8510,
            8526,
            8542,
            10720,
            10601,
            10603,
            10602,
            10612,
            10611,
            10610,
            10613,
            10604,
            10605,
            10606,
            3942,
            3941,
            3940,
            3950,
            3947,
            3948,
            3949,
            3938,
            3939,
            3937,
            4065,
            1870,
            1854,
            1838,
            1885,
            1822,
            1806,
            1774,
            1790,
            1783,
            1767,
            1799,
            8471,
        )
    ),
    # measure/measure-waist-circ-decr|incr
    "waist": _adjacent_pairs(
        (
            4121,
            10760,
            10757,
            10777,
            10776,
            10779,
            10780,
            10778,
            10781,
            10771,
            10773,
            10772,
            10775,
            10774,
            10814,
            10834,
            10816,
            10817,
            10818,
            10819,
            10820,
            10821,
            4181,
            4180,
            4179,
            4178,
            4177,
            4176,
            4175,
            4196,
            4173,
            4131,
            4132,
            4129,
            4130,
            4128,
            4138,
            4135,
            4137,
            4136,
            4133,
            4134,
            4108,
            4113,
            4118,
            4121,
        )
    ),
    # measure/measure-hips-circ-decr|incr
    "full_hip": _adjacent_pairs(
        (
            4341,
            10968,
            10969,
            10971,
            10970,
            10967,
            10928,
            10927,
            10925,
            10926,
            10923,
            10924,
            10868,
            10875,
            10861,
            10862,
            4228,
            4227,
            4226,
            4242,
            4234,
            4294,
            4293,
            4296,
            4295,
            4297,
            4298,
            4342,
            4345,
            4346,
            4344,
            4343,
            4361,
            4341,
        )
    ),
    # Seam's shoulder width is the distance between its selected shoulder
    # landmarks, rather than MakeHuman's single-side shoulder-length ruler.
    "shoulder_width": [
        (ANCHOR_MAP["left_shoulder"], ANCHOR_MAP["right_shoulder"]),
    ],
    # measure/measure-upperarm-circ-decr|incr
    "upper_arm": _adjacent_pairs(
        (
            8383,
            8393,
            8392,
            8391,
            8390,
            8394,
            8395,
            8399,
            10455,
            10516,
            8396,
            8397,
            8398,
            8388,
            8387,
            8386,
            10431,
            8385,
            8384,
            8389,
        )
    ),
    # measure/measure-thigh-circ-decr|incr
    "thigh": _adjacent_pairs(
        (
            11071,
            11080,
            11081,
            11086,
            11076,
            11077,
            11074,
            11075,
            11072,
            11073,
            11069,
            11070,
            11087,
            11085,
            11084,
            12994,
            11083,
            11082,
            11079,
            11071,
        )
    ),
}

# ---------------------------------------------------------------------------
# Phase 1 — direct mappings
# Height and gender are derived analytically from measurements.
# Age, Weight, Muscle default to 0.5 (neutral) as seeds for Phase 2.
# ---------------------------------------------------------------------------

# MakeHuman height modifier range in mm
# modifier 0.0 = dwarf (1500mm), modifier 1.0 = giant (2000mm)
_DWARF_HEIGHT_MM = 1500.0
_GIANT_HEIGHT_MM = 2000.0


def height_to_modifier(height_mm: float) -> float:
    """
    Map a height in mm to a MakeHuman Height modifier value in [0.0, 1.0].
    Linear interpolation between dwarf (1500mm) and giant (2000mm).
    """
    t = (height_mm - _DWARF_HEIGHT_MM) / (_GIANT_HEIGHT_MM - _DWARF_HEIGHT_MM)
    return max(0.0, min(1.0, t))


def gender_from_proportions(
    chest: float,
    full_hip: float,
    shoulder_width: float,
) -> float:
    """
    Estimate gender modifier value from body proportions.

    Higher bust/hip + lower shoulder/hip  → feminine  (→ 1.0)
    Lower bust/hip  + higher shoulder/hip → masculine (→ 0.0)

    This is a V1 empirical approximation — refined during Task 7.3 calibration
    tuning once we can compare against real MakeHuman deformation output.

    Returns a value in [0.0, 1.0].
    """
    if full_hip <= 0.0:
        return 0.5  # can't divide — return neutral

    bust_hip = chest / full_hip
    shoulder_hip = shoulder_width / full_hip

    # Blend: bust/hip contributes 60%, shoulder/hip inversion contributes 40%
    raw = (bust_hip * 0.6) + ((1.0 - shoulder_hip) * 0.4)
    return max(0.0, min(1.0, raw))


def _build_phase1_modifiers(m: BodyMeasurements) -> dict[str, float]:
    """
    Produce the five macro modifier seed values from direct measurement mappings.
    These are passed to Phase 2 as the starting point for L-BFGS-B optimisation.
    """
    # Height — direct linear mapping if available, else neutral
    if m.height is not None:
        height_val = height_to_modifier(m.height)
    else:
        height_val = 0.5

    # Gender — derived from proportions if all three fields are present
    if m.chest is not None and m.full_hip is not None and m.shoulder_width is not None:
        gender_val = gender_from_proportions(m.chest, m.full_hip, m.shoulder_width)
    else:
        gender_val = 0.5  # neutral

    return {
        # MakeHuman modifier full names as used in modeling_modifiers.json
        "macrodetails-height/Height": height_val,
        "macrodetails/Gender": gender_val,
        "macrodetails/Age": 0.5,  # fixed — not in BodyMeasurements
        "macrodetails-universal/Weight": 0.5,  # seed for Phase 2 optimisation
        "macrodetails-universal/Muscle": 0.5,  # seed for Phase 2 optimisation
    }


# ---------------------------------------------------------------------------
# Phase 2 — L-BFGS-B optimisation
# Adjusts a set of universal modifiers to minimise the difference between
# the mesh's sampled measurements and the target BodyMeasurements.
# ---------------------------------------------------------------------------

import logging
import math
from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import minimize

from errors import CALIBRATION_FAILED, AvatarError

if TYPE_CHECKING:
    from pipeline.deform import HeadlessDeformer

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# The modifiers included in the optimisation search space.
# These are universal modifiers that control specific body region sizes
# independently of the macro modifiers set in Phase 1.
#
# V1 set — tuned in Task 7.3. Add or remove entries based on residuals.
# ---------------------------------------------------------------------------
OPTIMISED_MODIFIERS: list[str] = [
    "macrodetails-universal/Weight",
    "macrodetails-universal/Muscle",
    "measure/measure-bust-circ-decr|incr",
    "measure/measure-waist-circ-decr|incr",
    "measure/measure-hips-circ-decr|incr",
    "measure/measure-upperarm-circ-decr|incr",
    "measure/measure-thigh-circ-decr|incr",
]

# Bounds for each optimised modifier: (min, max)
# Macro modifiers are [0.0, 1.0]; universal modifiers are [-1.0, 1.0]
BOUNDS: list[tuple[float, float]] = [
    (0.0, 1.0),  # Weight
    (0.0, 1.0),  # Muscle
    (-1.0, 1.0),  # bust
    (-1.0, 1.0),  # waist
    (-1.0, 1.0),  # hips
    (-1.0, 1.0),  # upperarm
    (-1.0, 1.0),  # thigh
]


def _target_fields(m: BodyMeasurements) -> list[tuple[str, float]]:
    """
    Return (field_name, value_mm) pairs for every measurement field that
    is present (not None). These are the fields included in the error function.
    """
    mapping = {
        "chest": m.chest,
        "waist": m.waist,
        "full_hip": m.full_hip,
        "shoulder_width": m.shoulder_width,
        "upper_arm": m.upper_arm,
        "thigh": m.thigh,
    }
    return [(k, v) for k, v in mapping.items() if v is not None]


def _objective(
    x: np.ndarray,
    deformer: HeadlessDeformer,
    phase1_modifiers: dict[str, float],
    target: BodyMeasurements,
) -> float:
    """
    Objective function for L-BFGS-B.

    Builds the full modifier dict (phase1 + current x values), applies it to
    the deformer, samples the resulting measurements, and returns the sum of
    squared errors in mm².

    Lower is better. The optimiser drives this toward zero.
    """
    # Merge phase1 seeds with the current optimiser proposal
    modifier_dict = {
        **phase1_modifiers,
        **dict(zip(OPTIMISED_MODIFIERS, x.tolist())),
    }

    deformer.apply_modifiers(modifier_dict)
    sampled = deformer.sample_measurements()
    deformer.reset()

    sse = 0.0
    for field, target_val in _target_fields(target):
        sampled_val = sampled.get(field, 0.0)
        sse += (sampled_val - target_val) ** 2

    return float(sse)


def calibrate(
    measurements: BodyMeasurements,
    deformer: HeadlessDeformer,
    max_seconds: int,
) -> tuple[dict[str, float], dict[str, float]]:
    """
    Map BodyMeasurements to a MakeHuman modifier dict.

    Phase 1: compute direct mappings (height, gender, age).
    Phase 2: run L-BFGS-B to minimise measurement residuals.

    Returns:
        modifier_dict  — full modifier name → float value, ready for
                         deformer.apply_modifiers()
        residuals_dict — field name → abs error in mm after optimisation
    """
    phase1 = _build_phase1_modifiers(measurements)

    # Initial point: phase1 values for the optimised modifiers, else 0.5
    x0 = np.array(
        [phase1.get(name, 0.5) for name in OPTIMISED_MODIFIERS], dtype=np.float64
    )

    result = minimize(
        _objective,
        x0,
        method="L-BFGS-B",
        bounds=BOUNDS,
        args=(deformer, phase1, measurements),
        options={
            "maxtime": float(max_seconds),
            "ftol": 1e-6,
            "gtol": 1e-5,
        },
    )

    # Build the final modifier dict from the optimiser result
    optimised_values = dict(zip(OPTIMISED_MODIFIERS, result.x.tolist()))
    final_modifiers = {**phase1, **optimised_values}

    # Compute residuals on the final deformation
    deformer.apply_modifiers(final_modifiers)
    sampled = deformer.sample_measurements()
    deformer.reset()

    residuals: dict[str, float] = {}
    for field, target_val in _target_fields(measurements):
        sampled_val = sampled.get(field, 0.0)
        residuals[field] = abs(sampled_val - target_val)

    # Log outcome
    if not result.success:
        final_sse = result.fun if result.fun is not None else float("inf")

        if math.isnan(final_sse) or math.isinf(final_sse):
            raise AvatarError(
                CALIBRATION_FAILED,
                f"Optimiser diverged: fun={final_sse}, message={result.message}",
            )

        # Convergence timeout or mild non-convergence — use best result found
        logger.warning(
            "Calibration did not fully converge",
            extra={
                "optimizer_message": result.message,
                "final_sse": final_sse,
                "residuals": residuals,
            },
        )
    else:
        logger.info(
            "Calibration converged",
            extra={"iterations": result.nit, "residuals": residuals},
        )

    return final_modifiers, residuals
