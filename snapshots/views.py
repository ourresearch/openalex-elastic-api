from flask import Blueprint, jsonify, redirect, request

import settings
from core.exceptions import APIQueryParamsError
from snapshots.s3 import generate_presigned_url, get_available_dates, get_manifest

blueprint = Blueprint("snapshots", __name__)

VALID_FORMATS = {"jsonl", "parquet"}


def _human_size(size_bytes):
    """Convert bytes to human-readable string."""
    if size_bytes is None:
        return None
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size_bytes) < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"


def _pass_api_key(url):
    """Append the caller's api_key to a URL if present."""
    api_key = request.args.get("api_key")
    if api_key:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}api_key={api_key}"
    return url


@blueprint.route("/changefiles")
def changefiles():
    """List available dates."""
    dates = get_available_dates()
    base = settings.SNAPSHOTS_BASE_URL

    results = []
    for d in dates:
        results.append({
            "date": d,
            "url": _pass_api_key(f"{base}/changefiles/{d}"),
        })

    return jsonify({
        "meta": {"count": len(results)},
        "results": results,
    })


@blueprint.route("/changefiles/<date>")
def changefile_entities(date):
    """List entities for a given date with download URLs for each format."""
    base = settings.SNAPSHOTS_BASE_URL

    # Load both manifests
    manifests = {}
    for fmt in sorted(VALID_FORMATS):
        manifest = get_manifest(date, fmt)
        if manifest is not None:
            manifests[fmt] = manifest

    if not manifests:
        raise APIQueryParamsError(f"No changefile found for date={date}")

    entity_map = {}
    for fmt, manifest in manifests.items():
        for ent in manifest.get("entities", []):
            entity_name = ent["entity"]
            manifest_files = ent.get("files", [])

            if not manifest_files:
                continue

            if entity_name not in entity_map:
                meta = manifest_files[0].get("meta", {})
                entity_map[entity_name] = {
                    "entity": entity_name,
                    "records": meta.get("record_count"),
                    "formats": {},
                }

            f = manifest_files[0]
            meta = f.get("meta", {})
            filename = f["url"].rsplit("/", 1)[-1]
            size = meta.get("content_length")
            entity_map[entity_name]["formats"][fmt] = {
                "size_bytes": size,
                "size_display": _human_size(size),
                "url": _pass_api_key(
                    f"{base}/changefiles/{date}/{filename}"
                ),
            }

    results = [entity_map[name] for name in sorted(entity_map)]

    return jsonify({
        "meta": {"count": len(results), "date": date},
        "results": results,
    })


@blueprint.route("/changefiles/<date>/<filename>")
def changefile_download(date, filename):
    """Redirect to pre-signed S3 URL."""
    # Determine format from filename
    if filename.endswith(".jsonl.gz"):
        fmt = "jsonl"
    elif filename.endswith(".parquet"):
        fmt = "parquet"
    else:
        raise APIQueryParamsError(
            "Filename must end with .jsonl.gz or .parquet"
        )

    manifest = get_manifest(date, fmt)
    if manifest is None:
        raise APIQueryParamsError(
            f"No changefile found for date={date}, format={fmt}"
        )

    for ent in manifest.get("entities", []):
        for f in ent.get("files", []):
            if f["url"].endswith(f"/{filename}"):
                s3_key = f["url"].split(f"s3://{settings.SNAPSHOTS_S3_BUCKET}/", 1)[-1]
                presigned_url = generate_presigned_url(s3_key)
                return redirect(presigned_url, code=302)

    raise APIQueryParamsError(f"File '{filename}' not found")
