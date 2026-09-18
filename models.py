from dataclasses import dataclass
from typing import Optional

@dataclass
class BodyMeasurements:
    """
    All fields in float millimetres. None = not provided by user.
    """
    height: Optional[float]             = None
    torso_length_back: Optional[float]  = None
    torso_length_front: Optional[float] = None
    hip_length: Optional[float]         = None
    sleeve_length: Optional[float]      = None
    inseam: Optional[float]             = None
    outseam: Optional[float]            = None
    crotch_depth: Optional[float]       = None
    chest: Optional[float]              = None
    under_bust: Optional[float]         = None
    waist: Optional[float]              = None
    high_hip: Optional[float]           = None
    full_hip: Optional[float]           = None
    neck_circumference: Optional[float] = None
    upper_arm: Optional[float]          = None
    elbow: Optional[float]              = None
    wrist: Optional[float]              = None
    thigh: Optional[float]              = None
    knee: Optional[float]               = None
    calf: Optional[float]               = None
    ankle: Optional[float]              = None
    shoulder_width: Optional[float]     = None
    back_width: Optional[float]         = None
    shoulder_slope: Optional[float]     = None

    @classmethod
    def from_tmm_dict(cls, d: dict) -> "BodyMeasurements":
        kwargs = {}
        for key, value in d.items():
            if key.endswith("_tmm"):
                field_name = key[:-4] # strip the _tmm suffix
                if hasattr(cls, field_name):
                    kwargs[field_name] = int(value) / 10.0
        return cls(**kwargs)

    def to_canonical_dict(self) -> dict:
        import dataclasses
        return dict(
            sorted(dataclasses.asdict(self).items())
        )

@dataclass
class AvatarAnchor:
    name: str
    position: tuple[float, float, float]    # (x, y, z) mm, Y-up

@dataclass
class JobPayload:
    job_id: str
    profile_id: str
    measurements: BodyMeasurements

@dataclass
class JobResult:
    job_id: str
    profile_id: str
    profile_hash: str
    s3_key: str
    anchor_count: int
    duration_ms: int
    cache_hit: bool
    deform_ms: int
    calibration_ms: int
    export_ms: int
    upload_ms: int
