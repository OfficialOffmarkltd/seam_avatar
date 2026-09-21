import logging

import numpy as np

from anchor_map import ANCHOR_MAP
from errors import AvatarError, ANCHOR_EXTRACT_FAILED
from models import AvatarAnchor

logger = logging.getLogger(__name__)


def extract_anchors(vertex_array: np.ndarray) -> list[AvatarAnchor]:
    """
    Read the position of each named anchor from the deformed vertex array.

    vertex_array is shape [N, 3] float32, values in millimetres, Y-up.
    ANCHOR_MAP maps anchor names to vertex indices in the base mesh topology.
    Since topology never changes, the same indices are valid for any deformation.

    Raises AvatarError(ANCHOR_EXTRACT_FAILED) if any index in ANCHOR_MAP
    is out of range for the provided vertex array.
    """
    n_verts = vertex_array.shape[0]

    # Validate all indices before reading any — fail atomically
    missing = [
        name
        for name, idx in ANCHOR_MAP.items()
        if idx >= n_verts
    ]
    if missing:
        raise AvatarError(
            ANCHOR_EXTRACT_FAILED,
            f"Anchor indices out of range for mesh with {n_verts} vertices: "
            f"{', '.join(missing)}",
        )

    anchors = [
        AvatarAnchor(
            name=name,
            position=tuple(vertex_array[idx].tolist()),  # (x, y, z) mm
        )
        for name, idx in ANCHOR_MAP.items()
    ]

    logger.debug(f"Extracted {len(anchors)} anchors from vertex array")
    return anchors
