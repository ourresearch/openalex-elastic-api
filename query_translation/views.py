"""
Flask Blueprint for /query endpoint.

Provides bidirectional translation between URL, OQL, and OQO query formats.
"""

from flask import Blueprint, jsonify, request

from query_translation.oqo import OQO, filter_from_dict
from query_translation.url_parser import parse_url_to_oqo
from query_translation.url_renderer import render_oqo_to_url, URLRenderError, can_render_to_url
from query_translation.oql_renderer import render_oqo_to_oql
from query_translation.validator import validate_oqo, ValidationError, ValidationResult


blueprint = Blueprint("query_translation", __name__)


@blueprint.route("/query", methods=["GET"])
def get_query():
    """
    Get query in all formats.
    
    Query params:
    - entity_type: works, authors, etc. (default: works)
    - filter: URL filter string
    - sort: URL sort string  
    - sample: Sample size (integer)
    - oqo: JSON string of OQO object (alternative to filter/sort)
    
    Response:
    {
        "url": {"filter": "...", "sort": "...", "sample": null},
        "oql": "Works where ...",
        "oqo": {...},
        "validation": {"valid": true, "errors": [], "warnings": []}
    }
    """
    entity_type = request.args.get("entity_type", "works")
    filter_string = request.args.get("filter")
    sort_string = request.args.get("sort")
    sample = request.args.get("sample", type=int)
    oqo_json = request.args.get("oqo")
    
    try:
        oqo = None
        parse_error = None
        
        if oqo_json:
            # Parse OQO from JSON query param
            oqo, parse_error = parse_oqo_input(entity_type, oqo_json)
        else:
            # Parse from URL filter/sort params
            oqo, parse_error = parse_url_input(entity_type, {
                "filter": filter_string,
                "sort": sort_string,
                "sample": sample
            })
        
        if parse_error:
            return jsonify({
                "url": None,
                "oql": None,
                "oqo": None,
                "validation": {
                    "valid": False,
                    "errors": [{"type": "parse_error", "message": parse_error}],
                    "warnings": []
                }
            }), 400
        
        validation_result = validate_oqo(oqo)
        
        if not validation_result.valid:
            return jsonify({
                "url": None,
                "oql": None,
                "oqo": oqo.to_dict(),
                "validation": validation_result.to_dict()
            }), 400
        
        response = render_all_formats(oqo, validation_result)
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({
            "url": None,
            "oql": None,
            "oqo": None,
            "validation": {
                "valid": False,
                "errors": [{"type": "internal_error", "message": str(e)}],
                "warnings": []
            }
        }), 500


def parse_url_input(entity_type: str, input_data):
    """Parse URL format input."""
    try:
        if isinstance(input_data, dict):
            # Input is already structured: {"filter": "...", "sort": "..."}
            filter_string = input_data.get("filter")
            sort_string = input_data.get("sort")
            sample = input_data.get("sample")
        else:
            # Input is just the filter string
            filter_string = input_data
            sort_string = None
            sample = None
        
        oqo = parse_url_to_oqo(
            entity_type=entity_type,
            filter_string=filter_string,
            sort_string=sort_string,
            sample=sample
        )
        return oqo, None
    except Exception as e:
        return None, f"Failed to parse URL format: {str(e)}"


def parse_oqo_input(entity_type: str, input_data):
    """Parse OQO format input."""
    try:
        if isinstance(input_data, str):
            import json
            input_data = json.loads(input_data)
        
        # Ensure entity_type matches
        if "get_rows" not in input_data:
            input_data["get_rows"] = entity_type
        
        oqo = OQO.from_dict(input_data)
        return oqo, None
    except Exception as e:
        return None, f"Failed to parse OQO format: {str(e)}"


def render_all_formats(oqo: OQO, validation_result: ValidationResult):
    """Render OQO to all output formats."""
    warnings = list(validation_result.warnings)
    
    # Render to URL
    url_output = None
    try:
        url_output = render_oqo_to_url(oqo)
    except URLRenderError as e:
        warnings.append(ValidationError(
            type="url_not_expressible",
            message=str(e)
        ))
    
    # Render to OQL
    oql_output = render_oqo_to_oql(oqo)
    
    # Build response
    return {
        "url": url_output,
        "oql": oql_output,
        "oqo": oqo.to_dict(),
        "validation": {
            "valid": True,
            "errors": [],
            "warnings": [
                {"type": w.type, "message": w.message, "location": w.location}
                for w in warnings
            ]
        }
    }


