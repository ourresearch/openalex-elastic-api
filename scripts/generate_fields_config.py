#!/usr/bin/env python3
"""
Introspect fields.py files across all entities and generate YAML config.

This script extracts field metadata from the Python Field classes and outputs
a structured YAML config that can serve as a shared source of truth for
both backend validation and frontend UI.

Usage:
    python scripts/generate_fields_config.py [entity_name]
    
    If entity_name is provided, only that entity is processed.
    Otherwise, all entities are processed.
"""

import importlib
import sys
import yaml
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Map of entity names to their module paths
ENTITY_MODULES = {
    'works': 'works.fields',
    'authors': 'authors.fields',
    'sources': 'sources.fields',
    'institutions': 'institutions.fields',
    'concepts': 'concepts.fields',
    'publishers': 'publishers.fields',
    'funders': 'funders.fields',
    'topics': 'topics.fields',
    'keywords': 'keywords.fields',
    'countries': 'countries.fields',
    'continents': 'continents.fields',
    'languages': 'languages.fields',
    'licenses': 'licenses.fields',
    'domains': 'domains.fields',
    'subfields': 'subfields.fields',
    'fields': 'fields.fields',
    'sdgs': 'sdgs.fields',
    'source_types': 'source_types.fields',
    'institution_types': 'institution_types.fields',
    'work_types': 'work_types.fields',
}

# Map Python class names to YAML type values
CLASS_TO_TYPE = {
    'BooleanField': 'boolean',
    'DateField': 'date',
    'DateTimeField': 'datetime',
    'OpenAlexIDField': 'openalex_id',
    'RangeField': 'number',
    'SearchField': 'search',
    'TermField': 'term',
    'PhraseField': 'phrase',
    'ExternalIDField': 'external_id',
}

# Map Python class names to default actions
CLASS_TO_ACTIONS = {
    'BooleanField': ['filter', 'group_by'],
    'DateField': ['filter', 'sort'],
    'DateTimeField': ['filter', 'sort'],
    'OpenAlexIDField': ['filter', 'group_by'],
    'RangeField': ['filter', 'sort'],
    'SearchField': ['filter'],
    'TermField': ['filter', 'group_by'],
    'PhraseField': ['filter'],
    'ExternalIDField': ['filter'],
}


def extract_field_metadata(field_obj):
    """Extract metadata from a Field object."""
    class_name = type(field_obj).__name__
    
    metadata = {
        'id': field_obj.param,
        'type': CLASS_TO_TYPE.get(class_name, 'unknown'),
        'fieldClass': class_name,
        'actions': CLASS_TO_ACTIONS.get(class_name, ['filter']),
    }
    
    # Add optional fields if present
    if field_obj.custom_es_field:
        metadata['esField'] = field_obj.custom_es_field
    
    if field_obj.alias:
        metadata['alias'] = field_obj.alias
    
    if field_obj.docstring:
        metadata['description'] = field_obj.docstring
    
    if field_obj.documentation_link:
        metadata['documentationLink'] = field_obj.documentation_link
    
    if field_obj.alternate_names:
        metadata['alternateNames'] = field_obj.alternate_names
    
    # Check for unique_id (used for special handling)
    if field_obj.unique_id:
        metadata['uniqueId'] = field_obj.unique_id
    
    return metadata


def load_entity_fields(entity_name):
    """Load and introspect fields from an entity module."""
    module_path = ENTITY_MODULES.get(entity_name)
    if not module_path:
        print(f"Unknown entity: {entity_name}")
        return None
    
    try:
        module = importlib.import_module(module_path)
    except ImportError as e:
        print(f"Could not import {module_path}: {e}")
        return None
    
    # Get the fields list or fields_dict
    fields_list = getattr(module, 'fields', None)
    fields_dict = getattr(module, 'fields_dict', None)
    
    if fields_list is None and fields_dict is None:
        print(f"No 'fields' or 'fields_dict' found in {module_path}")
        return None
    
    # Use fields_list if available, otherwise extract from fields_dict
    if fields_list is None:
        fields_list = list(fields_dict.values())
    
    # Extract metadata from each field
    columns = {}
    for field in fields_list:
        metadata = extract_field_metadata(field)
        columns[field.param] = metadata
    
    return {
        'id': entity_name,
        'name': entity_name,
        'columns': columns,
    }


def generate_config(entity_name=None):
    """Generate YAML config for one or all entities."""
    if entity_name:
        entities = [entity_name]
    else:
        entities = list(ENTITY_MODULES.keys())
    
    results = {}
    for entity in entities:
        print(f"Processing {entity}...")
        config = load_entity_fields(entity)
        if config:
            results[entity] = config
            print(f"  Found {len(config['columns'])} fields")
    
    return results


def compare_with_existing_yaml(entity_name, generated_config):
    """Compare generated config with existing YAML config."""
    yaml_path = PROJECT_ROOT / 'config' / f'{entity_name}.yaml'
    
    if not yaml_path.exists():
        print(f"  No existing YAML at {yaml_path}")
        return
    
    with open(yaml_path) as f:
        existing = yaml.safe_load(f)
    
    existing_columns = set(existing.get('columns', {}).keys())
    generated_columns = set(generated_config['columns'].keys())
    
    only_in_yaml = existing_columns - generated_columns
    only_in_python = generated_columns - existing_columns
    in_both = existing_columns & generated_columns
    
    print(f"  Comparison with existing YAML:")
    print(f"    In both: {len(in_both)}")
    print(f"    Only in YAML: {len(only_in_yaml)}")
    if only_in_yaml:
        for col in sorted(only_in_yaml)[:5]:
            print(f"      - {col}")
        if len(only_in_yaml) > 5:
            print(f"      ... and {len(only_in_yaml) - 5} more")
    
    print(f"    Only in Python: {len(only_in_python)}")
    if only_in_python:
        for col in sorted(only_in_python)[:10]:
            print(f"      - {col}")
        if len(only_in_python) > 10:
            print(f"      ... and {len(only_in_python) - 10} more")


def main():
    entity_name = sys.argv[1] if len(sys.argv) > 1 else None
    
    results = generate_config(entity_name)
    
    print("\n" + "="*60)
    print("SUMMARY")
    print("="*60)
    
    for entity, config in results.items():
        print(f"\n{entity}:")
        print(f"  Total fields: {len(config['columns'])}")
        
        # Count by type
        type_counts = {}
        for col in config['columns'].values():
            t = col.get('type', 'unknown')
            type_counts[t] = type_counts.get(t, 0) + 1
        
        for t, count in sorted(type_counts.items()):
            print(f"    {t}: {count}")
        
        # Compare with existing YAML
        compare_with_existing_yaml(entity, config)
    
    # Optionally output YAML
    if entity_name and entity_name in results:
        output_path = PROJECT_ROOT / 'config' / f'{entity_name}_generated.yaml'
        with open(output_path, 'w') as f:
            yaml.dump(results[entity_name], f, default_flow_style=False, sort_keys=False)
        print(f"\nGenerated YAML written to: {output_path}")


if __name__ == '__main__':
    main()
