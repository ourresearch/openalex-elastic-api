#!/usr/bin/env python3
"""
Test script to verify OpenAI Responses API with tool calling.
Run: python test_openai_responses.py
"""

import os
import json
import requests
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-5"
OPENAI_PROMPT_ID = "pmpt_69549fae727481958ec7aaa4ee976b5a06d01a66a3e9b225"

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


def execute_resolve_entity(entity_type: str, query: str) -> list:
    """Execute a resolve_entity tool call by hitting the OpenAlex API."""
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
        print(f"  Calling OpenAlex API: {entity_type} search='{query}'")
        resp = requests.get(url, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        results = data.get("results", [])
        print(f"  Got {len(results)} results")
        return results
    except Exception as e:
        print(f"  Error: {e}")
        return [{"error": str(e)}]


def test_natural_language_query(query: str):
    """Test the full natural language to OQO flow."""
    print(f"\n{'='*60}")
    print(f"Testing query: '{query}'")
    print('='*60)
    
    if not OPENAI_API_KEY:
        print("ERROR: OPENAI_API_KEY environment variable not set")
        return
    
    client = OpenAI(api_key=OPENAI_API_KEY)
    
    messages = [
        {"role": "user", "content": query}
    ]
    
    # Initial call
    print("\n1. Making initial OpenAI Responses API call...")
    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            instructions=OPENAI_PROMPT_ID,
            input=messages,
            tools=[RESOLVE_ENTITY_TOOL]
        )
        print(f"   Success! Got {len(response.output)} output items")
    except Exception as e:
        print(f"   ERROR: {e}")
        return
    
    # Show output types
    print("\n2. Response output items:")
    for i, item in enumerate(response.output):
        print(f"   [{i}] type={item.type}")
        if hasattr(item, 'name'):
            print(f"       name={item.name}")
        if hasattr(item, 'arguments'):
            print(f"       arguments={item.arguments}")
    
    # Process tool calls
    iteration = 0
    max_iterations = 5
    
    while response.output and any(item.type == "function_call" for item in response.output):
        iteration += 1
        if iteration > max_iterations:
            print("\nERROR: Too many iterations")
            return
        
        tool_calls = [item for item in response.output if item.type == "function_call"]
        print(f"\n3.{iteration} Processing {len(tool_calls)} tool call(s)...")
        
        for tool_call in tool_calls:
            print(f"   Tool call: {tool_call.name}")
            print(f"   call_id: {tool_call.call_id}")
            args = json.loads(tool_call.arguments)
            print(f"   arguments: {args}")
            
            # Execute the tool call
            result = execute_resolve_entity(args.get("entity_type"), args.get("query"))
            
            # Add to messages
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
        
        # Continue conversation
        print(f"\n4.{iteration} Making follow-up OpenAI call...")
        try:
            response = client.responses.create(
                model=OPENAI_MODEL,
                instructions=OPENAI_PROMPT_ID,
                input=messages,
                tools=[RESOLVE_ENTITY_TOOL]
            )
            print(f"   Success! Got {len(response.output)} output items")
            for i, item in enumerate(response.output):
                print(f"   [{i}] type={item.type}")
        except Exception as e:
            print(f"   ERROR: {e}")
            return
    
    # Extract final response
    print("\n5. Extracting final response...")
    for item in response.output:
        if item.type == "message":
            print(f"   Found message with {len(item.content)} content items")
            for content in item.content:
                print(f"   Content type: {content.type}")
                if content.type == "output_text":
                    print(f"\n   OUTPUT TEXT:\n   {content.text[:500]}...")
                    try:
                        result = json.loads(content.text)
                        print(f"\n   PARSED JSON (keys): {list(result.keys())}")
                        return result
                    except json.JSONDecodeError as e:
                        print(f"   JSON parse error: {e}")
                        return None
    
    print("\nERROR: No valid response found")
    print(f"Output types were: {[item.type for item in response.output]}")
    return None


if __name__ == "__main__":
    # Test with a simple query
    result = test_natural_language_query("papers from harvard in 2025 about climate change")
    
    if result:
        print("\n" + "="*60)
        print("FINAL RESULT:")
        print("="*60)
        print(json.dumps(result, indent=2))
