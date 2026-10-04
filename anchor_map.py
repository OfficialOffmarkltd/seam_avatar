# Anchor name → vertex index in the MakeHuman base mesh.
# Indices are fixed regardless of deformation — the base mesh topology never changes.
# Candidate indices selected before helper geometry was excluded from export.
# Re-run scripts/verify_anchors.py and re-check visually: anchors must refer
# to vertices on the anatomical body surface, not MakeHuman helper meshes.

ANCHOR_MAP: dict[str, int] = {
    "neck_base_front": 809,  # dm: [0.000, 5.781, 0.692]
    "neck_base_back": 1491,  # dm: [0.000, 5.696, -0.343]
    "neck_base_left": 760,  # dm: [-0.545, 5.806, 0.186]
    "neck_base_right": 7479,  # dm: [0.545, 5.806, 0.186]
    "left_shoulder": 1545,  # dm: [-1.418, 5.669, -0.173]
    "right_shoulder": 8224,  # dm: [1.418, 5.669, -0.173]
    "left_underarm": 1665,  # dm: [-1.548, 4.465, 0.027]
    "right_underarm": 8337,  # dm: [1.548, 4.465, 0.027]
    "chest_front_centre": 1893,  # dm: [0.000, 3.616, 1.550]
    "chest_back_centre": 3959,  # dm: [-0.170, 3.693, -0.323]
    "left_chest_side": 3963,  # dm: [-1.248, 3.547, 0.220]
    "right_chest_side": 10625,  # dm: [1.248, 3.547, 0.220]
    "waist_front": 4106,  # dm: [0.000, 2.069, 1.397]
    "waist_back": 4180,  # dm: [-0.153, 2.042, -0.338]
    "waist_left": 4131,  # dm: [-1.245, 2.004, 0.028]
    "waist_right": 10774,  # dm: [1.245, 2.004, 0.028]
    "hip_front": 4329,  # dm: [0.000, 0.312, 1.300]
    "hip_back": 4223,  # dm: [0.000, 0.564, -0.761]
    "hip_left": 4287,  # dm: [-1.612, 0.591, -0.139]
    "hip_right": 10917,  # dm: [1.612, 0.591, -0.139]
    "crotch_point": 4335,  # dm: [0.000, 0.069, 1.215]
    "left_knee": 4649,  # dm: [-2.060, -3.781, 0.141]
    "right_knee": 11267,  # dm: [2.060, -3.781, 0.141]
    "left_wrist": 3488,  # dm: [-4.176, 2.732, 1.155]
    "right_wrist": 10156,  # dm: [4.176, 2.732, 1.155]
}
