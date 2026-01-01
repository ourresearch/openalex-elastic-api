from flask import Blueprint, jsonify, request, abort

from combined_config import all_entities_config
from core.exceptions import APIQueryParamsError

blueprint = Blueprint("oa_statuses", __name__)

# Static OA status data - these are not stored in Elasticsearch
OA_STATUSES = [
    {
        "id": "https://openalex.org/oa-statuses/closed",
        "display_name": "closed",
        "description": "Not open access. The work is not freely available to read.",
        "works_count": None,
        "cited_by_count": None,
        "works_api_url": "https://api.openalex.org/works?filter=open_access.oa_status:closed",
        "updated_date": None,
        "created_date": None,
    },
    {
        "id": "https://openalex.org/oa-statuses/green",
        "display_name": "green",
        "description": "Published in a toll-access journal, but archived in an open access repository such as ArXiv or an institutional repository. Green OA works may be preprints or published versions, and can have any license or no license.",
        "works_count": None,
        "cited_by_count": None,
        "works_api_url": "https://api.openalex.org/works?filter=open_access.oa_status:green",
        "updated_date": None,
        "created_date": None,
    },
    {
        "id": "https://openalex.org/oa-statuses/bronze",
        "display_name": "bronze",
        "description": "Free to read on the publisher's website, but without a clearly-identified open license. Bronze articles may have a delay between publication and free availability, and publishers can remove access at any time.",
        "works_count": None,
        "cited_by_count": None,
        "works_api_url": "https://api.openalex.org/works?filter=open_access.oa_status:bronze",
        "updated_date": None,
        "created_date": None,
    },
    {
        "id": "https://openalex.org/oa-statuses/hybrid",
        "display_name": "hybrid",
        "description": "Free to read on the publisher's website with an open license, but published in a subscription journal. Hybrid articles are typically published via an article processing charge (APC).",
        "works_count": None,
        "cited_by_count": None,
        "works_api_url": "https://api.openalex.org/works?filter=open_access.oa_status:hybrid",
        "updated_date": None,
        "created_date": None,
    },
    {
        "id": "https://openalex.org/oa-statuses/gold",
        "display_name": "gold",
        "description": "Free to read on the publisher's website with an open license, published in a fully Open Access journal. Gold journals (also called OA journals) publish all articles as open access.",
        "works_count": None,
        "cited_by_count": None,
        "works_api_url": "https://api.openalex.org/works?filter=open_access.oa_status:gold",
        "updated_date": None,
        "created_date": None,
    },
]

# Index by short ID for quick lookup
OA_STATUSES_BY_ID = {s["display_name"]: s for s in OA_STATUSES}


def _check_unsupported_params():
    """Check for filter/group_by params and raise error if present."""
    if request.args.get("filter"):
        raise APIQueryParamsError("Filtering is not supported for the oa-statuses endpoint.")
    if request.args.get("group_by") or request.args.get("group-by"):
        raise APIQueryParamsError("Grouping is not supported for the oa-statuses endpoint.")
    if request.args.get("search"):
        raise APIQueryParamsError("Search is not supported for the oa-statuses endpoint.")
    if request.args.get("sort"):
        raise APIQueryParamsError("Sorting is not supported for the oa-statuses endpoint.")


@blueprint.route("/oa-statuses")
@blueprint.route("/entities/oa-statuses")
def oa_statuses_list():
    """List all OA statuses."""
    _check_unsupported_params()
    
    result = {
        "meta": {
            "count": len(OA_STATUSES),
            "db_response_time_ms": 0,
            "page": 1,
            "per_page": len(OA_STATUSES),
            "groups_count": None,
        },
        "results": OA_STATUSES,
        "group_by": [],
    }
    return jsonify(result)


@blueprint.route("/oa-statuses/<path:oa_status_id>")
@blueprint.route("/entities/oa-statuses/<path:oa_status_id>")
def oa_status_single(oa_status_id):
    """Get a single OA status by ID."""
    # Handle both full URL and short ID formats
    # e.g., "gold", "oa-statuses/gold", or "https://openalex.org/oa-statuses/gold"
    short_id = oa_status_id.lower()
    if "/" in short_id:
        short_id = short_id.split("/")[-1]
    
    if short_id not in OA_STATUSES_BY_ID:
        return jsonify({"error": "Not found", "message": f"OA status '{oa_status_id}' not found."}), 404
    
    return jsonify(OA_STATUSES_BY_ID[short_id])


@blueprint.route("/oa-statuses/filters/<path:params>")
def oa_statuses_filters(params):
    """Filters endpoint - not supported for OA statuses."""
    raise APIQueryParamsError("Filtering is not supported for the oa-statuses endpoint.")


@blueprint.route("/oa-statuses/histogram/<string:param>")
def oa_statuses_histogram(param):
    """Histogram endpoint - not supported for OA statuses."""
    raise APIQueryParamsError("Histograms are not supported for the oa-statuses endpoint.")


@blueprint.route("/oa-statuses/valid_fields")
def oa_statuses_valid_fields():
    """Return valid fields for OA statuses."""
    return jsonify(["id", "display_name", "description", "works_api_url"])


@blueprint.route("/oa-statuses/config")
def oa_statuses_config():
    """Return the entity config for OA statuses."""
    return jsonify(all_entities_config.get("oa-statuses", {}))
