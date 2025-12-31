"""
Flask Blueprint for /query endpoint.

Provides bidirectional translation between URL, OQL, and OQO query formats.
"""

import json
import concurrent.futures

import requests
from flask import Blueprint, jsonify, request
from openai import OpenAI

import settings
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


OPENAI_MODEL = "gpt-5"
OPENAI_PROMPT_ID = "pmpt_69549fae727481958ec7aaa4ee976b5a06d01a66a3e9b225"

# Fallback instructions if stored prompt doesn't return JSON
OPENAI_INSTRUCTIONS_SUFFIX = """

CRITICAL: You MUST respond with ONLY a valid JSON object in OQO (OpenAlex Query Object) format. No explanatory text, no markdown, no links - ONLY the JSON object.

Example OQO format:
{
  "get_rows": "works",
  "filter_works": [
    {"column_id": "authorships.institutions.id", "value": "I136199984"},
    {"column_id": "publication_year", "value": 2025}
  ]
}

Use the resolve_entity tool to look up OpenAlex IDs for institutions, authors, topics, etc. Then construct and return ONLY the OQO JSON.
"""

RESOLVE_ENTITY_TOOL = {
    "type": "function",
    "name": "resolve_entity",
    "description": "Look up OpenAlex entity IDs by searching for entities matching a query",
    "parameters": {
        "type": "object",
        "properties": {
            "entity_type": {
                "type": "string",
                "description": "The type of entity to search for (e.g., works, authors, institutions, sources, topics, funders, publishers)"
            },
            "query": {
                "type": "string",
                "description": "The search query to find matching entities"
            }
        },
        "required": ["entity_type", "query"]
    }
}


@blueprint.route("/query/natural-language/<path:natural_language_query>", methods=["GET"])
def get_natural_language_query(natural_language_query: str):
    """
    Convert a natural language query to OQO using OpenAI, then return all formats.
    
    URL path param:
    - natural_language_query: Natural language description of the query
    
    Response: Same format as /query endpoint
    """
    try:
        oqo_dict = convert_natural_language_to_oqo(natural_language_query)
        
        # Check for error response from model
        if "error" in oqo_dict:
            return jsonify({"msg": oqo_dict["error"]}), 400
        
        # Parse the OQO
        entity_type = oqo_dict.get("get_rows", "works")
        oqo, parse_error = parse_oqo_input(entity_type, oqo_dict)
        
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


def convert_natural_language_to_oqo(natural_language_query: str) -> dict:
    """
    Use OpenAI to convert natural language to OQO format.
    Handles function calling for entity resolution with parallel execution.
    """
    client = OpenAI(api_key=settings.OPENAI_API_KEY)
    
    messages = [
        {"role": "user", "content": natural_language_query}
    ]
    
    # Initial call to OpenAI with function calling
    print("Making initial OpenAI request...", flush=True)
    response = client.responses.create(
        model=OPENAI_MODEL,
        instructions=OPENAI_PROMPT_ID,
        input=messages,
        tools=[RESOLVE_ENTITY_TOOL]
    )
    print(f"Got response with {len(response.output)} output items", flush=True)
    
    # Debug: log output types
    for i, item in enumerate(response.output):
        print(f"Output item {i}: type={item.type}", flush=True)
    
    # Process tool calls in a loop until we get a final response
    max_iterations = 5
    iteration = 0
    while response.output and any(item.type == "function_call" for item in response.output):
        iteration += 1
        if iteration > max_iterations:
            return {"error": "Too many tool call iterations"}
        
        tool_calls = [item for item in response.output if item.type == "function_call"]
        print(f"Iteration {iteration}: Processing {len(tool_calls)} tool calls", flush=True)
        
        # Execute all tool calls in parallel
        tool_results = execute_tool_calls_parallel(tool_calls)
        print(f"Tool calls completed", flush=True)
        
        # Build the conversation with tool results
        for tool_call, result in zip(tool_calls, tool_results):
            messages.append({
                "type": "function_call",
                "call_id": tool_call.call_id,
                "name": tool_call.name,
                "arguments": tool_call.arguments
            })
            messages.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": json.dumps(result)
            })
        
        # Continue the conversation
        print("Making follow-up OpenAI request...", flush=True)
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=OPENAI_PROMPT_ID,
            input=messages,
            tools=[RESOLVE_ENTITY_TOOL]
        )
        print(f"Got response with {len(response.output)} output items", flush=True)
        for i, item in enumerate(response.output):
            print(f"Output item {i}: type={item.type}", flush=True)
    
    # Extract the final text response containing OQO JSON
    print("Extracting final response...", flush=True)
    for item in response.output:
        if item.type == "message":
            for content in item.content:
                if content.type == "output_text":
                    print(f"Found output_text: {content.text[:100]}...", flush=True)
                    return json.loads(content.text)
    
    # Debug: show what we actually got
    print(f"No valid response found. Output types: {[item.type for item in response.output]}", flush=True)
    return {"error": "No valid response from model"}


def execute_tool_calls_parallel(tool_calls: list) -> list:
    """Execute multiple tool calls in parallel and return results in order."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(execute_resolve_entity, tool_call)
            for tool_call in tool_calls
        ]
        return [future.result() for future in futures]


def execute_resolve_entity(tool_call) -> list:
    """
    Execute a resolve_entity tool call by hitting the OpenAlex API.
    Returns the results array from the API response.
    """
    args = json.loads(tool_call.arguments)
    entity_type = args.get("entity_type", "works")
    query = args.get("query", "")
    
    url = f"https://api.openalex.org/{entity_type}"
    
    # Select fields vary by entity type - works don't have works_count
    if entity_type == "works":
        select_fields = "id,display_name,relevance_score"
    else:
        select_fields = "id,display_name,relevance_score,works_count"
    
    params = {
        "search": query,
        "select": select_fields,
        "per_page": 5
    }
    
    try:
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])
    except Exception as e:
        return [{"error": str(e)}]
