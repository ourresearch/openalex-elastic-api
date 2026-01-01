"""
OQL Renderer - Converts OQO format to OQL (human-readable query language).

Generates human-readable OQL strings like:
  Works where it's Open Access and Country is Canada [countries/ca] and year >= 2020; sort by citations desc

See docs/oql-spec.md for the full specification.
"""

from typing import Optional, Dict, Any, Callable
import requests

from query_translation.oqo import OQO, LeafFilter, BranchFilter, FilterType


# Column ID to display name mapping
# Maps technical column_id to human-readable display name
COLUMN_DISPLAY_NAMES: Dict[str, str] = {
    "publication_year": "year",
    "cited_by_count": "citations",
    "fwci": "FWCI",
    "type": "type",
    "open_access.is_oa": "Open Access",
    "authorships.institutions.lineage": "institution",
    "authorships.author.id": "author",
    "authorships.countries": "Country",
    "authorships.institutions.continent": "Continent",
    "primary_location.source.id": "source",
    "primary_location.source.type": "source type",
    "primary_location.source.publisher_lineage": "publisher",
    "primary_topic.id": "topic",
    "primary_topic.subfield.id": "subfield",
    "primary_topic.field.id": "field",
    "primary_topic.domain.id": "domain",
    "grants.funder": "funder",
    "awards.funder.id": "funder",
    "sustainable_development_goals.id": "Sustainable Development Goals",
    "title_and_abstract.search": "title & abstract",
    "display_name.search": "title",
    "default.search": "fulltext",
    "raw_affiliation_strings.search": "raw affiliation string",
    "language": "language",
    "is_retracted": "retracted",
    "has_doi": "has a DOI",
    "has_abstract": "has an abstract",
    "institutions.is_global_south": "from Global South",
    "authorships.institutions.is_global_south": "from Global South",
    "keywords.id": "keyword",
    "concepts.id": "concept",
    "open_access.oa_status": "OA status",
    "best_oa_location.license": "license",
}

# Boolean columns that use "it's [not] {displayName}" format
BOOLEAN_COLUMNS: Dict[str, str] = {
    "open_access.is_oa": "Open Access",
    "is_retracted": "retracted",
    "has_doi": "has a DOI",
    "has_abstract": "has an abstract",
    "institutions.is_global_south": "from Global South",
    "authorships.institutions.is_global_south": "from Global South",
    "primary_location.source.is_in_doaj": "indexed by DOAJ",
    "primary_location.source.is_oa": "in an OA source",
    "open_access.any_repository_has_fulltext": "has repository fulltext",
}

# Sort column display names
SORT_DISPLAY_NAMES: Dict[str, str] = {
    "cited_by_count": "citations",
    "publication_year": "year",
    "publication_date": "date",
    "fwci": "FWCI",
    "display_name": "title",
    "relevance_score": "relevance",
}


class OQLRenderer:
    """
    Renders OQO objects to human-readable OQL strings.
    
    Supports display name resolution for columns and entity values.
    """
    
    def __init__(self, entity_resolver: Optional[Callable[[str], Optional[str]]] = None):
        """
        Initialize the renderer.
        
        Args:
            entity_resolver: Optional function that takes an entity ID (e.g., "countries/ca")
                           and returns its display name (e.g., "Canada"). If None, 
                           a default resolver using the OpenAlex API will be used.
        """
        self._entity_resolver = entity_resolver
        self._entity_cache: Dict[str, str] = {}
    
    def render(self, oqo: OQO) -> str:
        """
        Render an OQO object to OQL format.
        
        Args:
            oqo: The OQO object to render
        
        Returns:
            Human-readable OQL string
        """
        parts = []
        
        # Entity name (capitalized)
        entity_name = oqo.get_rows.replace("-", " ").title()
        parts.append(entity_name)
        
        # Filters
        if oqo.filter_rows:
            parts.append(" where ")
            filter_clauses = []
            for f in oqo.filter_rows:
                clause = self._render_filter(f)
                if clause:
                    filter_clauses.append(clause)
            parts.append(" and ".join(filter_clauses))
        
        # Sort
        if oqo.sort_by_column:
            order = oqo.sort_by_order or "desc"
            sort_display = SORT_DISPLAY_NAMES.get(oqo.sort_by_column, oqo.sort_by_column)
            parts.append(f"; sort by {sort_display} {order}")
        
        # Sample
        if oqo.sample:
            parts.append(f"; sample {oqo.sample}")
        
        return "".join(parts)
    
    def _render_filter(self, f: FilterType) -> str:
        """Render a single filter to OQL."""
        if isinstance(f, LeafFilter):
            return self._render_leaf_filter(f)
        elif isinstance(f, BranchFilter):
            return self._render_branch_filter(f)
        return ""
    
    def _render_leaf_filter(self, f: LeafFilter) -> str:
        """
        Render a leaf filter to human-readable OQL.
        
        Examples:
        - it's Open Access
        - Country is Canada [countries/ca]
        - year >= 2020
        - title & abstract contains "machine learning"
        """
        column_id = f.column_id
        value = f.value
        operator = f.operator
        
        # Check for boolean filter with special "it's" format
        if column_id in BOOLEAN_COLUMNS and isinstance(value, bool):
            return self._render_boolean_filter(column_id, value, operator)
        
        # Get display name for column
        column_display = COLUMN_DISPLAY_NAMES.get(column_id, column_id)
        
        # Format value based on type
        value_str = self._format_value(value, column_id)
        
        # Format based on operator
        if operator == "is":
            return f"{column_display} is {value_str}"
        elif operator == "is not":
            return f"{column_display} is not {value_str}"
        elif operator == ">=":
            return f"{column_display} >= {value_str}"
        elif operator == "<=":
            return f"{column_display} <= {value_str}"
        elif operator == ">":
            return f"{column_display} > {value_str}"
        elif operator == "<":
            return f"{column_display} < {value_str}"
        elif operator == "contains":
            return f"{column_display} contains {value_str}"
        elif operator == "does not contain":
            return f"{column_display} does not contain {value_str}"
        else:
            return f"{column_display} {operator} {value_str}"
    
    def _render_boolean_filter(self, column_id: str, value: bool, operator: str) -> str:
        """
        Render a boolean filter using "it's [not] {displayName}" format.
        
        Examples:
        - it's Open Access
        - it's not retracted
        - it's from Global South
        """
        display_name = BOOLEAN_COLUMNS.get(column_id, column_id)
        
        # Determine if negated
        is_negated = (value is False) or (operator == "is not" and value is True)
        
        if is_negated:
            return f"it's not {display_name}"
        else:
            return f"it's {display_name}"
    
    def _format_value(self, value: Any, column_id: str) -> str:
        """
        Format a filter value for OQL output.
        
        For entity IDs, includes display name before bracketed ID.
        """
        if value is None:
            return "unknown"
        
        if isinstance(value, bool):
            return str(value).lower()
        
        if isinstance(value, str):
            # Check if this looks like an entity ID (contains /)
            if "/" in value and not value.startswith('"'):
                return self._format_entity_value(value)
            
            # Quote strings that contain spaces or special characters
            if " " in value or "," in value:
                return f'"{value}"'
            return value
        
        return str(value)
    
    def _format_entity_value(self, entity_id: str) -> str:
        """
        Format an entity ID with its display name, using short ID format.
        
        Example: "countries/ca" -> "Canada [ca]"
        Example: "sdgs/2" -> "Zero Hunger [2]"
        Example: "institutions/I136199984" -> "[I136199984]" (no display name available)
        """
        display_name = self._resolve_entity_display_name(entity_id)
        
        # Extract the short ID (part after the slash)
        short_id = entity_id.split("/", 1)[1] if "/" in entity_id else entity_id
        
        if display_name:
            return f"{display_name} [{short_id}]"
        else:
            # Fallback: just bracket the short ID
            return f"[{short_id}]"
    
    def _resolve_entity_display_name(self, entity_id: str) -> Optional[str]:
        """
        Resolve an entity ID to its display name.
        
        Uses cache and custom resolver if provided.
        """
        # Check cache first
        if entity_id in self._entity_cache:
            return self._entity_cache[entity_id]
        
        # Use custom resolver if provided
        if self._entity_resolver:
            display_name = self._entity_resolver(entity_id)
            if display_name:
                self._entity_cache[entity_id] = display_name
                return display_name
        
        # Try default resolution
        display_name = self._default_entity_resolver(entity_id)
        if display_name:
            self._entity_cache[entity_id] = display_name
        
        return display_name
    
    def _default_entity_resolver(self, entity_id: str) -> Optional[str]:
        """
        Default entity resolver using OpenAlex API.
        
        Falls back to extracting readable name from ID for non-native entities.
        """
        # For non-native entities, we can derive display name from ID
        if "/" in entity_id:
            entity_type, short_id = entity_id.split("/", 1)
            
            # Simple mappings for well-known non-native entities
            if entity_type == "types":
                # article -> Article, book-chapter -> Book Chapter
                return short_id.replace("-", " ").title()
            
            if entity_type == "oa-statuses":
                return short_id.title()
            
            if entity_type == "languages":
                # Try to resolve language code to name
                return self._resolve_language(short_id)
            
            if entity_type == "countries":
                return self._resolve_country(short_id)
            
            if entity_type == "continents":
                return self._resolve_continent(short_id)
            
            if entity_type == "sdgs":
                return self._resolve_sdg(short_id)
            
            # For native entities (institutions, authors, etc.), 
            # would need API call - return None for now
            # API resolution can be added later
        
        return None
    
    def _resolve_language(self, code: str) -> Optional[str]:
        """Resolve language code to name."""
        languages = {
            "en": "English",
            "zh": "Chinese",
            "es": "Spanish",
            "fr": "French",
            "de": "German",
            "ja": "Japanese",
            "pt": "Portuguese",
            "ru": "Russian",
            "ko": "Korean",
            "it": "Italian",
            "ar": "Arabic",
            "nl": "Dutch",
            "pl": "Polish",
            "tr": "Turkish",
            "id": "Indonesian",
            "cs": "Czech",
            "sv": "Swedish",
            "fa": "Persian",
            "uk": "Ukrainian",
            "vi": "Vietnamese",
        }
        return languages.get(code.lower())
    
    def _resolve_country(self, code: str) -> Optional[str]:
        """Resolve country code to name."""
        countries = {
            "us": "United States",
            "gb": "United Kingdom",
            "cn": "China",
            "de": "Germany",
            "fr": "France",
            "jp": "Japan",
            "ca": "Canada",
            "au": "Australia",
            "in": "India",
            "br": "Brazil",
            "it": "Italy",
            "es": "Spain",
            "kr": "South Korea",
            "nl": "Netherlands",
            "ru": "Russia",
            "ch": "Switzerland",
            "se": "Sweden",
            "pl": "Poland",
            "be": "Belgium",
            "at": "Austria",
            "dk": "Denmark",
            "no": "Norway",
            "fi": "Finland",
            "mx": "Mexico",
            "sg": "Singapore",
            "ie": "Ireland",
            "nz": "New Zealand",
            "pt": "Portugal",
            "za": "South Africa",
            "il": "Israel",
        }
        return countries.get(code.lower())
    
    def _resolve_continent(self, code: str) -> Optional[str]:
        """Resolve continent code to name."""
        continents = {
            "q15": "Africa",
            "q18": "South America",
            "q46": "Europe",
            "q48": "Asia",
            "q49": "North America",
            "q55643": "Oceania",
            "q51": "Antarctica",
            "africa": "Africa",
            "south america": "South America",
            "europe": "Europe",
            "asia": "Asia",
            "north america": "North America",
            "oceania": "Oceania",
            "antarctica": "Antarctica",
        }
        return continents.get(code.lower())
    
    def _resolve_sdg(self, sdg_id: str) -> Optional[str]:
        """Resolve SDG number to name."""
        sdgs = {
            "1": "No Poverty",
            "2": "Zero Hunger",
            "3": "Good Health and Well-being",
            "4": "Quality Education",
            "5": "Gender Equality",
            "6": "Clean Water and Sanitation",
            "7": "Affordable and Clean Energy",
            "8": "Decent Work and Economic Growth",
            "9": "Industry, Innovation and Infrastructure",
            "10": "Reduced Inequalities",
            "11": "Sustainable Cities and Communities",
            "12": "Responsible Consumption and Production",
            "13": "Climate Action",
            "14": "Life Below Water",
            "15": "Life on Land",
            "16": "Peace, Justice, and Strong Institutions",
            "17": "Partnerships for the Goals",
        }
        return sdgs.get(sdg_id)
    
    def _render_branch_filter(self, f: BranchFilter) -> str:
        """
        Render a branch filter to OQL.
        
        Example: (type is article [types/article] or type is book [types/book])
        """
        if not f.filters:
            return ""
        
        sub_clauses = []
        for sub_f in f.filters:
            clause = self._render_filter(sub_f)
            if clause:
                sub_clauses.append(clause)
        
        if not sub_clauses:
            return ""
        
        if len(sub_clauses) == 1:
            return sub_clauses[0]
        
        join_word = f" {f.join} "
        joined = join_word.join(sub_clauses)
        
        # Wrap in parentheses for clarity
        return f"({joined})"


# Convenience function for backward compatibility
def render_oqo_to_oql(oqo: OQO, entity_resolver: Optional[Callable[[str], Optional[str]]] = None) -> str:
    """
    Render an OQO object to OQL format.
    
    Args:
        oqo: The OQO object to render
        entity_resolver: Optional function to resolve entity IDs to display names
    
    Returns:
        Human-readable OQL string
    """
    renderer = OQLRenderer(entity_resolver=entity_resolver)
    return renderer.render(oqo)
