import boto3
from botocore.exceptions import ClientError

from errors import S3_UPLOAD_FAILED, AvatarError


class S3CacheClient:
    def __init__(self, bucket: str, region: str, endpoint_url: str | None): 
        self._bucket = bucket
        self._client = boto3.client(
            "s3",
            region_name=region,
            endpoint_url=endpoint_url, # None means real AWS; a URL means LocalStack
        )

    def exists(self, profile_hash: str) -> bool:
        """
        HEAD s3://{bucket}/avatars/cache/{hash}.glb -> True if 200
        """
        try:
            self._client.head_object(
                Bucket=self._bucket,
                Key=f"avatars/cache/{profile_hash}.glb"
            )
            return True
        except ClientError as e:
            code = e.response["Error"]["Code"]
            if code in ("404", "NoSuchKey"):
                return False
            raise AvatarError(S3_UPLOAD_FAILED, str(e))
    
    def upload(self, profile_hash: str, glb_bytes: bytes) -> str:
        """
        put object with:
            ContentType: model/gltf-binary
            CacheControl: public,
            max-age=31536000, immutable
        Returns the S3 key string
        """
        key = f"avatars/cache/{profile_hash}.glb"
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=glb_bytes,
                ContentType="model/gltf-binary",
                CacheControl="public, max-age=31536000, immutable"
            )
            return key
        except ClientError as e:
            raise AvatarError(S3_UPLOAD_FAILED, str(e))
