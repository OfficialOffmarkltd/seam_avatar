from __future__ import annotations

from models import BodyMeasurements

# ---------------------------------------------------------------------------
# Measurement vertex pairs
# Populated in Task 4.2 after MakeHuman exploratory work.
# Each entry is a list of (vertex_i, vertex_j) pairs whose Euclidean distances
# sum to approximate the circumference of that body region.
# ---------------------------------------------------------------------------
MEASUREMENT_VERTEX_PAIRS: dict[str, list[tuple[int, int]]] = {
    "chest":          [],   # TODO: fill in Task 4.2
    "waist":          [],   # TODO: fill in Task 4.2
    "full_hip":       [],   # TODO: fill in Task 4.2
    "shoulder_width": [],   # TODO: fill in Task 4.2
    "upper_arm":      [],   # TODO: fill in Task 4.2
    "thigh":          [],   # TODO: fill in Task 4.2
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

    bust_hip     = chest        / full_hip
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
        "macrodetails/Gender":        gender_val,
        "macrodetails/Age":           0.5,   # fixed — not in BodyMeasurements
        "macrodetails-universal/Weight": 0.5,  # seed for Phase 2 optimisation
        "macrodetails-universal/Muscle": 0.5,  # seed for Phase 2 optimisation
    }

# ---------------------------------------------------------------------------
# Phase 2 — L-BFGS-B optimisation
# Adjusts a set of universal modifiers to minimise the difference between
# the mesh's sampled measurements and the target BodyMeasurements.
# ---------------------------------------------------------------------------
from __future__ import annotations

import logging
import math
from typing import TYPE_CHECKING

import numpy as np
from scipy.optimize import minimize

from errors import AvatarError, CALIBRATION_FAILED

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
    "measure/bust-decrease|increase",
    "measure/waist-decrease|increase",
    "measure/hips-decrease|increase",
    "measure/upperarm-decrease|increase",
    "measure/thigh-decrease|increase",
]

# Bounds for each optimised modifier: (min, max)
# Macro modifiers are [0.0, 1.0]; universal modifiers are [-1.0, 1.0]
BOUNDS: list[tuple[float, float]] = [
    (0.0,  1.0),   # Weight
    (0.0,  1.0),   # Muscle
    (-1.0, 1.0),   # bust
    (-1.0, 1.0),   # waist
    (-1.0, 1.0),   # hips
    (-1.0, 1.0),   # upperarm
    (-1.0, 1.0),   # thigh
]


def _target_fields(m: BodyMeasurements) -> list[tuple[str, float]]:
    """
    Return (field_name, value_mm) pairs for every measurement field that
    is present (not None). These are the fields included in the error function.
    """
    mapping = {
        "chest":          m.chest,
        "waist":          m.waist,
        "full_hip":       m.full_hip,
        "shoulder_width": m.shoulder_width,
        "upper_arm":      m.upper_arm,
        "thigh":          m.thigh,
    }
    return [(k, v) for k, v in mapping.items() if v is not None]


def _objective(
    x: np.ndarray,
    deformer: "HeadlessDeformer",
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
    deformer: "HeadlessDeformer",
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
    x0 = np.array([
        phase1.get(name, 0.5) for name in OPTIMISED_MODIFIERS
    ], dtype=np.float64)

    result = minimize(
        _objective,
        x0,
        method="L-BFGS-B",
        bounds=BOUNDS,
        args=(deformer, phase1, measurements),
        options={
            "maxtime": float(max_seconds),
            "ftol":    1e-6,
            "gtol":    1e-5,
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
                "message":   result.message,
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
