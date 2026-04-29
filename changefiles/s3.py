import json

import boto3
from botocore.exceptions import ClientError

import settings

_s3_client = None


def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client("s3")
    return _s3_client


def get_available_dates():
    """Read daily/latest.json from S3 and return the available_dates list."""
    client = get_s3_client()
    try:
        resp = client.get_object(
            Bucket=settings.SNAPSHOTS_S3_BUCKET, Key="daily/latest.json"
        )
        data = json.loads(resp["Body"].read())
        return data.get("available_dates", [])
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return []
        raise


def get_manifest(date, fmt):
    """Read daily/{date}/{fmt}/manifest.json from S3 and return parsed JSON."""
    client = get_s3_client()
    key = f"daily/{date}/{fmt}/manifest.json"
    try:
        resp = client.get_object(
            Bucket=settings.SNAPSHOTS_S3_BUCKET, Key=key
        )
        return json.loads(resp["Body"].read())
    except ClientError as e:
        if e.response["Error"]["Code"] == "NoSuchKey":
            return None
        raise


def generate_presigned_url(key, expiry=3600):
    """Generate a pre-signed GET URL for an S3 object."""
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.SNAPSHOTS_S3_BUCKET, "Key": key},
        ExpiresIn=expiry,
    )
