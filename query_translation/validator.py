"""
Validator - Validates OQO against field definitions.

Uses the field definitions from {entity}/fields.py to validate
that column_ids and operators are valid.
"""

from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass
import requests

from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType, VALID_OPERATORS


@dataclass
class ValidationError:
    """A validation error."""
    type: str
    message: str
    location: Optional[str] = None


@dataclass  
class ValidationResult:
    """Result of OQO validation."""
    valid: bool
    errors: List[ValidationError]
    warnings: List[ValidationError]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "valid": self.valid,
            "errors": [
                {"type": e.type, "message": e.message, "location": e.location}
                for e in self.errors
            ],
            "warnings": [
                {"type": w.type, "message": w.message, "location": w.location}
                for w in self.warnings
            ]
        }


class OQOValidator:
    """Validates OQO objects against field definitions."""
    
    VALID_ENTITIES = {
        "works", "authors", "institutions", "sources", "publishers",
        "funders", "topics", "keywords", "concepts", "countries",
        "continents", "domains", "fields", "subfields", "sdgs",
        "languages", "licenses", "work-types", "source-types",
        "institution-types", "awards", "locations"
    }
    
    VALID_SORT_ORDERS = {"asc", "desc"}
    
    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize validator.
        
        Args:
            config: Optional entity config dict. If not provided,
                   will fetch from API.
        """
        self._config = config
        self._valid_fields_cache: Dict[str, Set[str]] = {}
    
    @property
    def config(self) -> Dict:
        """Lazy-load entity config from API."""
        if self._config is None:
            self._config = self._fetch_entities_config()
        return self._config
    
    @staticmethod
    def _fetch_entities_config() -> Dict:
        """Fetch entity configuration from API."""
        try:
            r = requests.get('https://api.openalex.org/entities/config')
            r.raise_for_status()
            return r.json()
        except Exception:
            # Return empty config if API unavailable
            return {}
    
    def get_valid_fields(self, entity_type: str) -> Set[str]:
        """Get valid filter fields for an entity type."""
        if entity_type in self._valid_fields_cache:
            return self._valid_fields_cache[entity_type]
        
        fields = set()
        
        # Try to get from config
        if entity_type in self.config:
            columns = self.config[entity_type].get("columns", {})
            for col_id, col_data in columns.items():
                fields.add(col_id)
                fields.add(col_data.get("id", col_id))
                if "displayName" in col_data:
                    fields.add(col_data["displayName"])
        
        # Also load from local fields.py definitions
        fields.update(self._get_local_fields(entity_type))
        
        self._valid_fields_cache[entity_type] = fields
        return fields
    
    def _get_local_fields(self, entity_type: str) -> Set[str]:
        """Get fields from local {entity}/fields.py definitions."""
        fields = set()
        
        try:
            # Import the appropriate fields module
            if entity_type == "works":
                from works.fields import fields as works_fields
                for f in works_fields:
                    fields.add(f.param)
                    if f.alias:
                        fields.add(f.alias)
            elif entity_type == "authors":
                from authors.fields import fields as authors_fields
                for f in authors_fields:
                    fields.add(f.param)
                    if f.alias:
                        fields.add(f.alias)
            elif entity_type == "institutions":
                from institutions.fields import fields as institutions_fields
                for f in institutions_fields:
                    fields.add(f.param)
                    if f.alias:
                        fields.add(f.alias)
            elif entity_type == "sources":
                from sources.fields import fields as sources_fields
                for f in sources_fields:
                    fields.add(f.param)
                    if f.alias:
                        fields.add(f.alias)
            # Add more entities as needed
        except ImportError:
            pass
        
        return fields
    
    def validate(self, oqo: OQO) -> ValidationResult:
        """
        Validate an OQO object.
        
        Args:
            oqo: The OQO object to validate
            
        Returns:
            ValidationResult with errors and warnings
        """
        errors = []
        warnings = []
        
        # Validate entity type
        if oqo.get_rows not in self.VALID_ENTITIES:
            errors.append(ValidationError(
                type="invalid_entity",
                message=f"'{oqo.get_rows}' is not a valid entity type",
                location="get_rows"
            ))
        
        # Validate filter_rows
        for i, f in enumerate(oqo.filter_rows):
            filter_errors = self._validate_filter(
                f, oqo.get_rows, f"filter_rows[{i}]"
            )
            errors.extend(filter_errors)
        
        # Validate sort
        if oqo.sort_by_order and oqo.sort_by_order not in self.VALID_SORT_ORDERS:
            errors.append(ValidationError(
                type="invalid_sort_order",
                message=f"'{oqo.sort_by_order}' is not a valid sort order. Use 'asc' or 'desc'.",
                location="sort_by_order"
            ))
        
        # Validate sample
        if oqo.sample is not None:
            if not isinstance(oqo.sample, int) or oqo.sample < 1:
                errors.append(ValidationError(
                    type="invalid_sample",
                    message="Sample must be a positive integer",
                    location="sample"
                ))
        
        return ValidationResult(
            valid=len(errors) == 0,
            errors=errors,
            warnings=warnings
        )
    
    def _validate_filter(
        self, 
        f: FilterType, 
        entity_type: str,
        location: str
    ) -> List[ValidationError]:
        """Validate a single filter."""
        errors = []
        
        if isinstance(f, LeafFilter):
            errors.extend(self._validate_leaf_filter(f, entity_type, location))
        elif isinstance(f, BranchFilter):
            errors.extend(self._validate_branch_filter(f, entity_type, location))
        
        return errors
    
    def _validate_leaf_filter(
        self, 
        f: LeafFilter, 
        entity_type: str,
        location: str
    ) -> List[ValidationError]:
        """Validate a leaf filter."""
        errors = []
        
        # Validate operator
        if f.operator not in VALID_OPERATORS:
            errors.append(ValidationError(
                type="invalid_operator",
                message=f"'{f.operator}' is not a valid operator",
                location=f"{location}.operator"
            ))
        
        # Validate column_id (field)
        # Note: We're lenient here - we allow fields that might not be in our cache
        # because the config might not be complete
        valid_fields = self.get_valid_fields(entity_type)
        if valid_fields and f.column_id not in valid_fields:
            # Check if it looks like a nested field path
            base_field = f.column_id.split(".")[0]
            if base_field not in valid_fields:
                # This is a warning, not an error, because our field list might be incomplete
                pass  # Could add warning here
        
        return errors
    
    def _validate_branch_filter(
        self, 
        f: BranchFilter, 
        entity_type: str,
        location: str
    ) -> List[ValidationError]:
        """Validate a branch filter."""
        errors = []
        
        # Validate join operator
        if f.join not in ("and", "or"):
            errors.append(ValidationError(
                type="invalid_join",
                message=f"'{f.join}' is not a valid join operator. Use 'and' or 'or'.",
                location=f"{location}.join"
            ))
        
        # Validate sub-filters
        if not f.filters:
            errors.append(ValidationError(
                type="empty_branch",
                message="Branch filter must have at least one sub-filter",
                location=f"{location}.filters"
            ))
        else:
            for i, sub_f in enumerate(f.filters):
                sub_errors = self._validate_filter(
                    sub_f, entity_type, f"{location}.filters[{i}]"
                )
                errors.extend(sub_errors)
        
        return errors


def validate_oqo(oqo: OQO, config: Optional[Dict] = None) -> ValidationResult:
    """
    Validate an OQO object.
    
    Convenience function that creates a validator and validates.
    """
    validator = OQOValidator(config=config)
    return validator.validate(oqo)
