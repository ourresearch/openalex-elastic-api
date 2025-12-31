#!/usr/bin/env python3
"""
Test script to verify OpenAI Responses API with stored prompts.
Uses the correct API pattern from OpenAI playground.
Run: python test_openai_responses_v2.py
"""

import os
import json
import requests
from openai import OpenAI

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-5"
OPENAI_PROMPT_ID = "pmpt_69549fae727481958ec7aaa4ee976b5a06d01a66a3e9b225"

# Shared config for API calls
TEXT_CONFIG = {
    "format": {
        "type": "json_schema",
        "name": "OpenAlex_Query_Object",
        "strict": False,
        "schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    "verbosity": "low"
}

REASONING_CONFIG = {"summary": "auto"}


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
    
    # Initial call with stored prompt and variables
    print("\n1. Making initial OpenAI Responses API call...")
    try:
        response = client.responses.create(
            model=OPENAI_MODEL,
            prompt={
                "id": OPENAI_PROMPT_ID,
                "variables": {
                    "query": query
                }
            },
            input=[],
            text=TEXT_CONFIG,
            reasoning=REASONING_CONFIG,
            store=True
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
    
    # Process tool calls in a loop
    iteration = 0
    max_iterations = 5
    
    while response.output and any(item.type == "function_call" for item in response.output):
        iteration += 1
        if iteration > max_iterations:
            print("\nERROR: Too many iterations")
            return
        
        tool_calls = [item for item in response.output if item.type == "function_call"]
        print(f"\n3.{iteration} Processing {len(tool_calls)} tool call(s)...")
        
        # Build input for follow-up: previous output items + tool call outputs
        follow_up_input = []
        
        # Add all items from previous response output
        for item in response.output:
            if item.type == "reasoning":
                follow_up_input.append({
                    "type": "reasoning",
                    "id": item.id,
                    "summary": [{"type": "summary_text", "text": s.text} for s in (item.summary or [])],
                    "encrypted_content": getattr(item, 'encrypted_content', '')
                })
            elif item.type == "function_call":
                follow_up_input.append({
                    "type": "function_call",
                    "id": item.id,
                    "call_id": item.call_id,
                    "name": item.name,
                    "arguments": item.arguments
                })
        
        # Execute tool calls and add outputs
        for tool_call in tool_calls:
            print(f"   Tool call: {tool_call.name}")
            print(f"   call_id: {tool_call.call_id}")
            args = json.loads(tool_call.arguments)
            print(f"   arguments: {args}")
            
            # Execute the tool call
            result = execute_resolve_entity(args.get("entity_type"), args.get("query"))
            
            # Add function_call_output to input
            follow_up_input.append({
                "type": "function_call_output",
                "call_id": tool_call.call_id,
                "output": json.dumps(result)
            })
        
        # Make follow-up call with full conversation
        print(f"\n4.{iteration} Making follow-up OpenAI call...")
        try:
            response = client.responses.create(
                model=OPENAI_MODEL,
                prompt={
                    "id": OPENAI_PROMPT_ID,
                    "version": OPENAI_PROMPT_VERSION,
                    "variables": {
                        "query": query
                    }
                },
                input=follow_up_input,
                text=TEXT_CONFIG,
                reasoning=REASONING_CONFIG,
                store=True
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
                    print(f"\n   OUTPUT TEXT:\n{content.text}")
                    try:
                        result = json.loads(content.text)
                        print(f"\n   PARSED JSON SUCCESS!")
                        return result
                    except json.JSONDecodeError as e:
                        print(f"   JSON parse error: {e}")
                        return None
    
    print("\nERROR: No valid response found")
    print(f"Output types were: {[item.type for item in response.output]}")
    return None


if __name__ == "__main__":
    result = test_natural_language_query("papers from harvard in 2025 about climate change")
    
    if result:
        print("\n" + "="*60)
        print("FINAL RESULT:")
        print("="*60)
        print(json.dumps(result, indent=2))
