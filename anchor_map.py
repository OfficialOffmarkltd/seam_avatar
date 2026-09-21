# Anchor name → vertex index in the MakeHuman base mesh.
# Indices are fixed regardless of deformation — the base mesh topology never changes.
# Populated in Task 4.1. All values are placeholders (0) until then.
# Run scripts/verify_anchors.py to find real indices, then paste the output here.

ANCHOR_MAP: dict[str, int] = {
    "neck_base_front":    0,
    "neck_base_back":     0,
    "neck_base_left":     0,
    "neck_base_right":    0,
    "left_shoulder":      0,
    "right_shoulder":     0,
    "left_underarm":      0,
    "right_underarm":     0,
    "chest_front_centre": 0,
    "chest_back_centre":  0,
    "left_chest_side":    0,
    "right_chest_side":   0,
    "waist_front":        0,
    "waist_back":         0,
    "waist_left":         0,
    "waist_right":        0,
    "hip_front":          0,
    "hip_back":           0,
    "hip_left":           0,
    "hip_right":          0,
    "crotch_point":       0,
    "left_knee":          0,
    "right_knee":         0,
    "left_wrist":         0,
    "right_wrist":        0,
}
