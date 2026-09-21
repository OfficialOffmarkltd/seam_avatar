import hashlib
import json

from models import BodyMeasurements


def compute_profile_hash(measurements: BodyMeasurements) -> str:
    """
    Produces a stable 64-character hex SHA-256 hash of a BodyMeasurements instance.

    Canonical form: keys sorted alphabetically, no whitespace, None values included.
    Two BodyMeasurements instances with identical field values always produce the
    same hash, regardless of construction order or field insertion order.
    """
    as_dict = measurements.to_canonical_dict()
    canonical = json.dumps(as_dict, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
