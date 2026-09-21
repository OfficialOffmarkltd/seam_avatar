import json
import logging
import struct

import numpy as np

from errors import EXPORT_FAILED, AvatarError
from models import AvatarAnchor

logger = logging.getLogger(__name__)


def compute_normals(verts: np.ndarray, faces: np.ndarray) -> np.ndarray:
    """
    Compute smooth vertex normals by accumulating face normals at each vertex
    and normalising.

    verts: [N, 3] float32
    faces: [M, 3] uint32
    returns: [N, 3] float32 normalised normals
    """
    v0 = verts[faces[:, 0]]
    v1 = verts[faces[:, 1]]
    v2 = verts[faces[:, 2]]

    # Cross product of two edges gives the face normal
    face_normals = np.cross(v1 - v0, v2 - v0).astype(np.float32)

    # Accumulate face normals at each vertex (each vertex averages its adjacent faces)
    vertex_normals = np.zeros_like(verts)
    np.add.at(vertex_normals, faces[:, 0], face_normals)
    np.add.at(vertex_normals, faces[:, 1], face_normals)
    np.add.at(vertex_normals, faces[:, 2], face_normals)

    # Normalise — replace zero-length normals with (0, 1, 0) to avoid NaN
    norms = np.linalg.norm(vertex_normals, axis=1, keepdims=True)
    norms = np.where(norms == 0, 1.0, norms)
    return (vertex_normals / norms).astype(np.float32)


def export_gltf(
    vertex_array: np.ndarray,
    face_array: np.ndarray,
    anchors: list[AvatarAnchor],
) -> bytes:
    """
    Export a deformed avatar mesh as a binary glTF 2.0 (.glb).

    vertex_array: [N, 3] float32, millimetres, Y-up
    face_array:   [M, 3] uint32  triangle indices
    anchors:      named anatomical positions embedded in scene.extras

    Returns raw .glb bytes ready for S3 upload.
    Raises AvatarError(EXPORT_FAILED) on any error.
    """
    try:
        verts   = vertex_array.astype(np.float32)
        faces   = face_array.astype(np.uint32)
        normals = compute_normals(verts, faces)

        # ── binary buffer ────────────────────────────────────────────────────
        # Layout: [vertex positions] [vertex normals] [face indices]
        vert_bytes   = verts.tobytes()
        normal_bytes = normals.tobytes()
        face_bytes   = faces.tobytes()

        buffer_data = vert_bytes + normal_bytes + face_bytes

        n_verts  = len(verts)
        n_indices = len(faces) * 3  # 3 indices per triangle

        v_min = verts.min(axis=0).tolist()
        v_max = verts.max(axis=0).tolist()

        # ── avatar_anchors extras ────────────────────────────────────────────
        avatar_anchors_json = [
            {"name": a.name, "position": list(a.position)}
            for a in anchors
        ]

        # ── glTF JSON ────────────────────────────────────────────────────────
        gltf = {
            "asset": {
                "version":   "2.0",
                "generator": "seam_avatar",
            },
            "scene":  0,
            "scenes": [{
                "nodes":  [0],
                "extras": {"avatar_anchors": avatar_anchors_json},
            }],
            "nodes": [{"mesh": 0}],
            "meshes": [{
                "primitives": [{
                    "attributes": {
                        "POSITION": 0,
                        "NORMAL":   1,
                    },
                    "indices": 2,
                    "mode":    4,   # TRIANGLES
                }],
            }],
            "accessors": [
                {   # 0 — POSITION
                    "bufferView":    0,
                    "componentType": 5126,      # FLOAT
                    "count":         n_verts,
                    "type":          "VEC3",
                    "min":           v_min,
                    "max":           v_max,
                },
                {   # 1 — NORMAL
                    "bufferView":    1,
                    "componentType": 5126,      # FLOAT
                    "count":         n_verts,
                    "type":          "VEC3",
                },
                {   # 2 — indices
                    "bufferView":    2,
                    "componentType": 5125,      # UNSIGNED_INT
                    "count":         n_indices,
                    "type":          "SCALAR",
                },
            ],
            "bufferViews": [
                {   # 0 — positions
                    "buffer":     0,
                    "byteOffset": 0,
                    "byteLength": len(vert_bytes),
                },
                {   # 1 — normals
                    "buffer":     0,
                    "byteOffset": len(vert_bytes),
                    "byteLength": len(normal_bytes),
                },
                {   # 2 — indices
                    "buffer":     0,
                    "byteOffset": len(vert_bytes) + len(normal_bytes),
                    "byteLength": len(face_bytes),
                },
            ],
            "buffers": [{
                "byteLength": len(buffer_data),
            }],
        }

        # ── assemble GLB ─────────────────────────────────────────────────────
        # GLB format:
        #   12-byte file header
        #   JSON chunk  (length u32 | type u32 "JSON" | data padded to 4 bytes)
        #   BIN  chunk  (length u32 | type u32 "BIN\0" | data padded to 4 bytes)

        json_bytes = json.dumps(gltf, separators=(",", ":")).encode("utf-8")

        # Pad to 4-byte boundary with spaces (required by spec)
        json_pad   = (4 - len(json_bytes) % 4) % 4
        json_bytes += b" " * json_pad

        # Pad binary to 4-byte boundary with zero bytes
        bin_pad     = (4 - len(buffer_data) % 4) % 4
        buffer_data += b"\x00" * bin_pad

        total_length = (
            12                       # file header
            + 8 + len(json_bytes)    # JSON chunk header + data
            + 8 + len(buffer_data)   # BIN  chunk header + data
        )

        import io
        buf = io.BytesIO()

        # File header: magic "glTF", version 2, total length
        buf.write(struct.pack("<III", 0x46546C67, 2, total_length))

        # JSON chunk
        buf.write(struct.pack("<II", len(json_bytes), 0x4E4F534A))  # type = "JSON"
        buf.write(json_bytes)

        # BIN chunk
        buf.write(struct.pack("<II", len(buffer_data), 0x004E4942))  # type = "BIN\0"
        buf.write(buffer_data)

        glb_bytes = buf.getvalue()

        logger.info(
            f"Exported .glb — "
            f"{n_verts} verts, {len(faces)} triangles, "
            f"{len(anchors)} anchors, "
            f"{len(glb_bytes) / 1024:.1f} KB"
        )

        if len(glb_bytes) > 15 * 1024 * 1024:
            logger.warning(
                f".glb size {len(glb_bytes) / 1024 / 1024:.1f} MB exceeds 15 MB limit"
            )

        return glb_bytes

    except AvatarError:
        raise
    except Exception as e:
        raise AvatarError(EXPORT_FAILED, str(e)) from e
