class AvatarError(Exception):
    def __init__(self, code: str, detail: str):
        self.code = code
        self.detail = detail
        super().__init__(f"[{code}] {detail}")


# Error code constants
INVALID_PAYLOAD       = "INVALID_PAYLOAD"
CALIBRATION_FAILED    = "CALIBRATION_FAILED"
DEFORM_FAILED         = "DEFORM_FAILED"
ANCHOR_EXTRACT_FAILED = "ANCHOR_EXTRACT_FAILED"
EXPORT_FAILED         = "EXPORT_FAILED"
S3_UPLOAD_FAILED      = "S3_UPLOAD_FAILED"
