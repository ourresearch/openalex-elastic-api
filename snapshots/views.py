import re

from flask import Blueprint, jsonify, redirect, request

import settings
from core.exceptions import APIQueryParamsError
from snapshots.s3 import generate_presigned_url, get_available_dates, get_manifest

blueprint = Blueprint("snapshots", __name__)

VALID_FORMATS = {"jsonl", "parquet"}


def _pass_api_key(url):
    """Append the caller's api_key to a URL if present."""
    api_key = request.args.get("api_key")
    if api_key:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}api_key={api_key}"
    return url


@blueprint.route("/snapshots/daily")
def daily_snapshots():
    date = request.args.get("date")
    fmt = request.args.get("format")

    if date and fmt:
        return _list_files(date, fmt)
    return _list_dates()


def _list_dates():
    """Return available snapshot dates with format links."""
    dates = get_available_dates()
    base = settings.SNAPSHOTS_BASE_URL

    results = []
    for d in dates:
        results.append({
            "date": d,
            "formats": {
                "jsonl": _pass_api_key(f"{base}/snapshots/daily?date={d}&format=jsonl"),
                "parquet": _pass_api_key(f"{base}/snapshots/daily?date={d}&format=parquet"),
            },
        })

    return jsonify({
        "meta": {"count": len(results)},
        "results": results,
    })


def _list_files(date, fmt):
    """Return entity file listing for a given date and format."""
    if fmt not in VALID_FORMATS:
        raise APIQueryParamsError(
            f"Invalid format '{fmt}'. Must be one of: {', '.join(sorted(VALID_FORMATS))}"
        )

    manifest = get_manifest(date, fmt)
    if manifest is None:
        raise APIQueryParamsError(
            f"No snapshot found for date={date}, format={fmt}"
        )

    entity_filter = request.args.get("entity")
    base = settings.SNAPSHOTS_BASE_URL
    entities = manifest.get("entities", [])

    results = []
    for ent in entities:
        entity_name = ent["entity"]
        if entity_filter and entity_name != entity_filter:
            continue

        entry = {
            "entity": entity_name,
            "record_count": ent.get("record_count"),
            "content_length": ent.get("content_length"),
            "filename": None,
            "download_url": None,
        }

        manifest_files = ent.get("files", [])
        if not manifest_files:
            continue

        f = manifest_files[0]
        s3_uri = f["url"]
        filename = s3_uri.rsplit("/", 1)[-1]
        entry["filename"] = filename
        entry["download_url"] = _pass_api_key(
            f"{base}/snapshots/daily/download?date={date}&format={fmt}"
            f"&entity={entity_name}&file={filename}"
        )

        results.append(entry)

    results.sort(key=lambda e: e["entity"])

    return jsonify({
        "meta": {
            "date": manifest.get("date"),
            "format": manifest.get("format"),
            "record_count": manifest.get("meta", {}).get("record_count"),
            "content_length": manifest.get("meta", {}).get("content_length"),
        },
        "results": results,
    })


@blueprint.route("/snapshots/daily/download")
def daily_snapshot_download():
    date = request.args.get("date")
    fmt = request.args.get("format")
    entity = request.args.get("entity")
    filename = request.args.get("file")

    if not all([date, fmt, entity, filename]):
        raise APIQueryParamsError(
            "Missing required parameters. Need: date, format, entity, file"
        )

    if fmt not in VALID_FORMATS:
        raise APIQueryParamsError(
            f"Invalid format '{fmt}'. Must be one of: {', '.join(sorted(VALID_FORMATS))}"
        )

    # Validate filename: no path traversal
    if "/" in filename or "\\" in filename or ".." in filename:
        raise APIQueryParamsError("Invalid filename")

    # Validate filename matches expected pattern: {entity}_{date}.{ext}
    if not re.match(r"^[a-z_]+_\d{4}-\d{2}-\d{2}\.\w+(\.\w+)?$", filename):
        raise APIQueryParamsError("Invalid filename format")

    key = f"daily/{date}/{fmt}/{filename}"
    presigned_url = generate_presigned_url(key)
    return redirect(presigned_url, code=302)
