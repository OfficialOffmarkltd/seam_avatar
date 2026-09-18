from dataclasses import dataclass


@dataclass
class BodyMeasurements:
    """
    All fields in float millimetres. None = not provided by user.
    """
    height: float | None             = None
    torso_length_back: float | None  = None
    torso_length_front: float | None = None
    hip_length: float | None         = None
    sleeve_length: float | None      = None
    inseam: float | None             = None
    outseam: float | None            = None
    crotch_depth: float | None       = None
    chest: float | None              = None
    under_bust: float | None         = None
    waist: float | None              = None
    high_hip: float | None           = None
    full_hip: float | None           = None
    neck_circumference: float | None = None
    upper_arm: float | None          = None
    elbow: float | None              = None
    wrist: float | None              = None
    thigh: float | None              = None
    knee: float | None               = None
    calf: float | None               = None
    ankle: float | None              = None
    shoulder_width: float | None     = None
    back_width: float | None         = None
    shoulder_slope: float | None     = None

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
