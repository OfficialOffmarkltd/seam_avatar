import json
import logging
import os
import sys
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def load_base_body_mesh(obj_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Load only MakeHuman's anatomical ``body`` faces from ``base.obj``.

    MakeHuman's base OBJ also contains helper geometry (hair, skirt, tights,
    eyes, teeth, skeleton joints, and similar authoring aids).  Those faces
    are useful to the desktop application but must never be part of Seam's
    avatar surface.  This small OBJ reader deliberately preserves the original
    vertex array and face indices: morph targets, ruler paths, and ANCHOR_MAP
    all use MakeHuman's original vertex numbering.
    """
    vertices: list[list[float]] = []
    body_faces: list[list[int]] = []
    active_group: str | None = None

    try:
        with obj_path.open(encoding="utf-8") as obj_file:
            for line in obj_file:
                parts = line.split()
                if not parts or parts[0].startswith("#"):
                    continue

                if parts[0] == "v":
                    if len(parts) < 4:
                        raise RuntimeError(f"Malformed vertex in {obj_path}")
                    vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
                elif parts[0] == "g":
                    active_group = parts[1] if len(parts) > 1 else None
                elif parts[0] == "f" and active_group == "body":
                    # OBJ indices are one-based. MakeHuman stores its body as
                    # quads, while glTF requires triangles. Fan triangulation
                    # retains every original vertex index and winding order.
                    if len(parts) < 4:
                        raise RuntimeError(f"Malformed body face in {obj_path}: {line.strip()}")
                    face: list[int] = []
                    for value in parts[1:]:
                        raw_index = int(value.split("/", maxsplit=1)[0])
                        index = raw_index - 1 if raw_index > 0 else len(vertices) + raw_index
                        if not 0 <= index < len(vertices):
                            raise RuntimeError(
                                f"Body face references invalid vertex {raw_index} in {obj_path}"
                            )
                        face.append(index)
                    body_faces.extend(
                        [face[0], face[position], face[position + 1]]
                        for position in range(1, len(face) - 1)
                    )
    except OSError as exc:
        raise RuntimeError(f"Unable to read MakeHuman base mesh {obj_path}: {exc}") from exc

    if not vertices:
        raise RuntimeError(f"No vertices found in MakeHuman base mesh {obj_path}")
    if not body_faces:
        raise RuntimeError(f"No 'body' faces found in MakeHuman base mesh {obj_path}")

    return (
        np.asarray(vertices, dtype=np.float32),
        np.asarray(body_faces, dtype=np.uint32),
    )


class HeadlessDeformer:
    """
    Wraps MakeHuman's core deformation without any GUI initialisation.
    Loads base mesh + all morph targets once at construction.
    Not thread-safe: one instance per worker process.
    """

    def __init__(self, makehuman_data_path: str):
        # Put vendor stubs on sys.path before any MakeHuman import
        vendor_path = str(Path(__file__).parent.parent / "vendor" / "makehuman")
        if vendor_path not in sys.path:
            sys.path.insert(0, vendor_path)

        # getpath.py reads this env var to resolve getSysDataPath()
        os.environ["MAKEHUMAN_DATA_PATH"] = makehuman_data_path

        # Load base mesh
        obj_path = Path(makehuman_data_path) / "3dobjs" / "base.obj"
        logger.info(f"Loading base mesh from {obj_path}")
        vertices, faces = load_base_body_mesh(obj_path)

        # MakeHuman stores vertices in decimetres (1 unit = 10cm)
        # Multiply by 100 to convert to millimetres
        vertices *= 100.0

        # Shift so feet sit at Y=0 — the mesh is centred at Y=0 in base.obj
        # (head at +850mm, feet at -850mm). After this shift, feet are at 0
        # and head is at ~1700mm, matching the Y-up convention seam_backend expects.
        vertices[:, 1] -= vertices[:, 1].min()

        # Validate scale — standing height should be 1500–2000mm
        height = float(vertices[:, 1].max())
        if not (1500.0 <= height <= 2000.0):
            raise RuntimeError(
                f"Base mesh Y max is {height:.1f}mm — expected 1500–2000mm. "
                f"Check MAKEHUMAN_DATA_PATH and unit scaling."
            )

        # Validate face count per spec requirement
        if len(faces) < 5000:
            raise RuntimeError(
                f"Base mesh has only {len(faces)} faces — minimum is 5000. "
                f"Data may be incomplete."
            )

        # Anchors are part of the public avatar contract.  They must identify
        # vertices on the rendered anatomical surface, never a vertex used only
        # by MakeHuman helper geometry that is deliberately excluded above.
        from anchor_map import ANCHOR_MAP

        body_vertex_indices = set(faces.reshape(-1).tolist())
        non_surface_anchors = [
            name for name, index in ANCHOR_MAP.items()
            if index not in body_vertex_indices
        ]
        if non_surface_anchors:
            raise RuntimeError(
                "ANCHOR_MAP contains vertices outside the exported body surface: "
                f"{', '.join(non_surface_anchors)}. "
                "Re-run scripts/verify_anchors.py and select only body-surface anchors."
            )

        # Load compiled morph target archive
        npz_path = Path(makehuman_data_path) / "targets" / "targets.npz"
        logger.info(f"Loading morph targets from {npz_path}")
        self._npz = np.load(str(npz_path), allow_pickle=False)
        logger.info(f"Loaded {len(self._npz.files) // 2} morph targets")

        # Build the modifier → target weights table from MakeHuman's JSON definitions.
        # This resolves names like "macrodetails-height/Height" to the list of
        # target file paths and their blending factors.
        self._modifier_targets = self._build_modifier_table(makehuman_data_path)

        # Three vertex arrays:
        #   _base_verts    — never modified after __init__, the reference state
        #   _current_verts — working copy, reset before each job
        self._base_verts    = vertices.copy()
        self._current_verts = vertices.copy()
        self._faces         = faces
        self._data_path     = makehuman_data_path

        logger.info(
            f"HeadlessDeformer ready — "
            f"{len(vertices)} vertices, {len(faces)} faces, "
            f"{len(self._modifier_targets)} modifiers loaded"
        )

    # ── public API ────────────────────────────────────────────────────────────

    def apply_modifiers(self, modifier_dict: dict[str, float]) -> None:
        """
        Reset to base mesh, then apply each modifier in modifier_dict.
        modifier_dict maps modifier full names (e.g. "macrodetails-height/Height")
        to float values in their valid range ([0.0, 1.0] for macro modifiers).
        """
        self.reset()

        for modifier_name, value in modifier_dict.items():
            targets = self._modifier_targets.get(modifier_name)
            if targets is None:
                logger.debug(f"Unknown modifier '{modifier_name}' — skipping")
                continue

            for target_path, target_weight in targets:
                # Bidirectional universal modifiers use a signed value:
                # +1 applies only the ``incr`` target and -1 applies only the
                # ``decr`` target.  The modifier table marks the latter with
                # a negative target weight.  Applying both targets at once
                # doubles the deformation and is not MakeHuman semantics.
                if target_weight < 0:
                    final_weight = max(-value, 0.0)
                else:
                    final_weight = max(value, 0.0) * target_weight
                if abs(final_weight) < 1e-6:
                    continue  # negligible contribution — skip

                self._apply_target(target_path, final_weight)

    def sample_measurements(self) -> dict[str, float]:
        """
        Approximate tape-measure circumferences (mm) by summing Euclidean
        distances between consecutive vertex pairs around each body region.
        Vertex pairs are defined in MEASUREMENT_VERTEX_PAIRS in calibration.py.
        """
        # Deferred import avoids a circular dependency at module load time
        from pipeline.calibration import MEASUREMENT_VERTEX_PAIRS

        result = {}
        for field, pairs in MEASUREMENT_VERTEX_PAIRS.items():
            total = 0.0
            for (i, j) in pairs:
                diff = self._current_verts[i] - self._current_verts[j]
                total += float(np.linalg.norm(diff))
            result[field] = total
        return result

    def get_vertex_array(self) -> np.ndarray:
        """Returns a copy of the current deformed vertex array [N, 3] float32, mm."""
        return self._current_verts.copy()

    def get_face_array(self) -> np.ndarray:
        """Returns the face index array [M, 3] uint32. Topology never changes."""
        return self._faces

    def reset(self) -> None:
        """Discard all morph work and restore the base mesh vertices."""
        self._current_verts = self._base_verts.copy()

    # ── private helpers ───────────────────────────────────────────────────────

    def _apply_target(self, target_path: str, weight: float) -> None:
        """
        Apply a single morph target from the npz archive at the given weight.
        target_path is relative to the data directory, e.g.
        "targets/macrodetails/height/female-young-minheight"
        """
        # npz keys use forward slashes and no extension
        # normalise to match what was stored by compile_targets.py
        key = target_path.replace("\\", "/")
        if key.startswith("targets/"):
            # already fully qualified
            pass
        else:
            key = f"targets/{key}"

        index_key  = key + ".index"
        vector_key = key + ".vector"

        if index_key not in self._npz or vector_key not in self._npz:
            logger.debug(f"Target not in archive: {key} — skipping")
            return

        vert_indices  = self._npz[index_key]            # uint32 array of vertex indices
        # Archive vectors decode to MakeHuman's decimetre units via ``* 1e-3``.
        # This deformer stores vertices in millimetres, so convert dm → mm too:
        # 1e-3 * 100 = 1e-1.
        displacements = self._npz[vector_key] * 1e-1

        # Pure numpy indexed assignment — no Python loop over vertices
        self._current_verts[vert_indices] += displacements * weight

    def _build_modifier_table(
        self, makehuman_data_path: str
    ) -> dict[str, list[tuple[str, float]]]:
        """
        Parse MakeHuman's modifier JSON definitions and build a lookup table:
            modifier_full_name → [(target_path, weight), ...]

        MakeHuman macro modifiers (Gender, Age, Height, Weight, Muscle) blend
        many target files together. For V1 we use a simplified direct mapping:
        each modifier maps to a pair of targets (min/max extremes) and the
        modifier value interpolates between them.

        Universal modifiers (measure/chest-decrease|increase etc.) map to one
        or two targets with straightforward weight application.
        """
        table: dict[str, list[tuple[str, float]]] = {}

        modifier_files = [
            Path(makehuman_data_path) / "modifiers" / "modeling_modifiers.json",
            Path(makehuman_data_path) / "modifiers" / "measurement_modifiers.json",
        ]

        for mfile in modifier_files:
            if not mfile.exists():
                logger.warning(f"Modifier file not found: {mfile}")
                continue

            with open(mfile, "r", encoding="utf-8") as f:
                groups = json.load(f)

            for group in groups:
                group_name = group["group"]
                for mdef in group["modifiers"]:
                    if "macrovar" in mdef:
                        # Macro modifier — resolved via targets module at runtime
                        # Store a sentinel so apply_modifiers knows to use
                        # the macro path rather than direct target lookup
                        full_name = f"{group_name}/{mdef['macrovar']}"
                        table[full_name] = self._resolve_macro_targets(
                            group_name, mdef["macrovar"], makehuman_data_path
                        )
                    elif "target" in mdef:
                        # Universal modifier — maps to one or two target files
                        target_base = f"{group_name}/{mdef['target']}"
                        entries: list[tuple[str, float]] = []

                        min_ext = mdef.get("min")
                        max_ext = mdef.get("max")

                        if min_ext and max_ext:
                            # Bidirectional: apply only the target selected by
                            # the signed modifier value in apply_modifiers().
                            entries.append((f"targets/{target_base}-{min_ext}", -1.0))
                            entries.append((f"targets/{target_base}-{max_ext}", 1.0))
                        else:
                            # Unidirectional: value directly weights this target
                            entries.append((f"targets/{target_base}", 1.0))

                        full_name = (
                            f"{group_name}/{mdef['target']}-{min_ext}|{max_ext}"
                            if min_ext and max_ext
                            else f"{group_name}/{mdef['target']}"
                        )
                        table[full_name] = entries

        logger.info(f"Built modifier table with {len(table)} entries")
        return table

    def _resolve_macro_targets(
        self, group: str, variable: str, data_path: str
    ) -> list[tuple[str, float]]:
        """
        For macro modifiers (Gender, Age, Height, Weight, Muscle), scan the
        targets directory for files whose names contain the relevant tokens and
        return them as (path, 1.0) pairs. The calibration layer controls the
        modifier value; this just enumerates the available targets.

        This is a V1 approximation. A full implementation would use MakeHuman's
        targets.py category system to compute blended weights from all macro
        variable combinations.
        """
        targets_dir = Path(data_path) / "targets" / group
        if not targets_dir.exists():
            return []

        # Map variable names to the token that appears in target file names
        token_map = {
            "Gender":          None,   # gender is implicit in male/female prefix
            "Age":             None,   # age tokens: baby, child, young, old
            "Height":          "height",
            "Weight":          "weight",
            "Muscle":          "muscle",
            "African":         "african",
            "Asian":           "asian",
            "Caucasian":       "caucasian",
            "BodyProportions": "proportions",
        }

        token = token_map.get(variable)
        entries = []

        for target_file in targets_dir.rglob("*.target"):
            fname = target_file.stem.lower()
            if token is None or token in fname:
                # Path relative to data_path, without extension, forward slashes
                rel = target_file.relative_to(Path(data_path))
                rel_str = str(rel.with_suffix("")).replace("\\", "/")
                entries.append((rel_str, 1.0))

        return entries
