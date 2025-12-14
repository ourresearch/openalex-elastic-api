#!/usr/bin/env python3
"""
Download 10 random sample objects for each OpenAlex entity type.
Saves results to local_data/ folder as JSON files.
"""

import json
import os
import requests

# API base URL
BASE_URL = "https://api.openalex.org"

# All entity types to download
ENTITIES = [
    "works",
    "authors", 
    "sources",
    "institutions",
    "topics",
    "keywords",
    "publishers",
    "funders",
    "awards",
    "concepts",
]

# Output directory
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "local_data")


def download_samples(entity: str, count: int = 10) -> dict:
    """Download random samples for an entity type."""
    url = f"{BASE_URL}/{entity}?sample={count}&api_key=02ca6ea638728c4be41187bba9704c3b"
    print(f"Downloading {count} samples of {entity}...")
    
    response = requests.get(url)
    response.raise_for_status()
    return response.json()


def main():
    # Ensure output directory exists
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    for entity in ENTITIES:
        try:
            data = download_samples(entity)
            output_file = os.path.join(OUTPUT_DIR, f"{entity}.json")
            
            with open(output_file, "w") as f:
                json.dump(data, f, indent=2)
            
            result_count = len(data.get("results", []))
            print(f"  ✓ Saved {result_count} {entity} to {entity}.json")
            
        except requests.exceptions.RequestException as e:
            print(f"  ✗ Error downloading {entity}: {e}")
        except Exception as e:
            print(f"  ✗ Unexpected error for {entity}: {e}")
    
    print("\nDone!")


if __name__ == "__main__":
    main()
