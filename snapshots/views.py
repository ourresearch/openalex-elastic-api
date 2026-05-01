import hashlib
import logging

import boto3
from flask import Blueprint, abort, jsonify, request

import settings

blueprint = Blueprint("snapshots", __name__)

logger = logging.getLogger(__name__)

_sts_client = None


def get_sts_client():
    global _sts_client
    if _sts_client is None:
        _sts_client = boto3.client("sts")
    return _sts_client


def _api_key_id(api_key):
    if not api_key:
        return "anonymous"
    return "k_" + hashlib.sha256(api_key.encode()).hexdigest()[:12]


@blueprint.route("/snapshots/credentials", methods=["POST"])
def snapshots_credentials():
    """Return short-lived AWS STS credentials for syncing the full snapshot.

    Output matches AWS CLI credential_process spec:
    https://docs.aws.amazon.com/cli/latest/userguide/cli-configure-sourcing-external.html

    Entitlement gating is enforced upstream in openalex-api-proxy
    (ENTERPRISE_PLANS); this endpoint trusts requests reaching it have been
    pre-authorized.
    """
    if not settings.SNAPSHOTS_CREDENTIALS_ENABLED:
        abort(404)

    api_key = request.args.get("api_key")
    key_id = _api_key_id(api_key)

    resp = get_sts_client().assume_role(
        RoleArn=settings.SNAPSHOTS_READER_ROLE_ARN,
        RoleSessionName=key_id,
        DurationSeconds=settings.SNAPSHOTS_SESSION_DURATION_SECONDS,
    )
    creds = resp["Credentials"]
    expiration = creds["Expiration"].isoformat()

    logger.info(
        "snapshot-credentials-mint key_id=%s source_ip=%s expiration=%s duration=%d",
        key_id,
        request.headers.get("CF-Connecting-IP") or request.remote_addr,
        expiration,
        settings.SNAPSHOTS_SESSION_DURATION_SECONDS,
    )

    body = jsonify({
        "Version": 1,
        "AccessKeyId": creds["AccessKeyId"],
        "SecretAccessKey": creds["SecretAccessKey"],
        "SessionToken": creds["SessionToken"],
        "Expiration": expiration,
    })
    body.headers["Cache-Control"] = "no-store"
    return body
