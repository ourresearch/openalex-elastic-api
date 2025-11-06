from flask import Blueprint, jsonify, request
from elasticsearch_dsl import Search, Q

from core.export import export_group_by, is_group_by_export
from core.shared_view import shared_view
from core.utils import get_flattened_fields, get_valid_fields, is_cached, process_only_fields
from core.params import parse_params
from core.preference import clean_preference
from extensions import cache

blueprint = Blueprint("funder_search", __name__)

# Import after blueprint definition to avoid circular imports
from funder_search.fields import fields_dict
from funder_search.schemas import FunderSearchSchema, MessageSchema

INDEX_NAME = "funder-search"

import re, csv, io

def parse_span(search_terms: str):
    m = re.match(r'^\s*SPAN\s*\((.*)\)\s*$', search_terms, re.IGNORECASE)
    if not m:
        return None
    inner = m.group(1)

    # split the 3 arguments, respecting quotes & spaces
    parts = next(csv.reader(io.StringIO(inner), skipinitialspace=True))
    if len(parts) != 3:
        return None

    def strip_quotes(s):
        s = s.strip()
        if len(s) >= 2 and s[0] in "\"'“”‘’" and s[-1] in "\"'“”‘’":
            return s[1:-1]
        return s

    phrase1 = strip_quotes(parts[0])
    phrase2 = strip_quotes(parts[1])
    distance = int(strip_quotes(parts[2]))
    return phrase1, phrase2, distance

def analyze_text(text):
    """Use Elasticsearch's _analyze API to stem text using kstem stemmer and remove stop words."""
    from elasticsearch_dsl import connections

    es = connections.get_connection('default')

    try:
        # Use the same analyzer as the fulltext field (with stop words and kstem)
        response = es.indices.analyze(
            body={
                "tokenizer": "standard",
                "filter": ["lowercase", "stop", "kstem"],
                "text": text
            }
        )
        tokens = [token['token'] for token in response['tokens']]
        print(f"Analyzed '{text}' -> {tokens}")
        return tokens
    except Exception as e:
        print(f"Analyzer failed: {e}")
        # Fallback to lowercased words if analyze fails
        return text.lower().split()


def build_fulltext_query(search_terms, index_name):
    parsed = parse_span(search_terms)
    if parsed:
        phrase1, phrase2, distance = parsed

        def build_span_clause(text):
            toks = analyze_text(text)
            if len(toks) == 1:
                return {"span_term": {"fulltext": toks[0]}}
            # allow gaps for removed stopwords/punctuation
            inner_slop = max(1, len(toks) - 1)
            return {
                "span_near": {
                    "clauses": [{"span_term": {"fulltext": t}} for t in toks],
                    "slop": inner_slop,
                    "in_order": True
                }
            }

        return Q(
            "span_near",
            clauses=[build_span_clause(phrase1), build_span_clause(phrase2)],
            slop=distance,
            in_order=True
        )

    # Check for proximity search
    has_proximity = '~' in search_terms and '"' in search_terms
    has_wildcard = '*' in search_terms or '?' in search_terms
    has_phrase = search_terms.count('"') >= 2

    # Check for boolean operators
    boolean_words = [" AND ", " OR ", " NOT "]
    has_boolean = any(word in search_terms for word in boolean_words)

    if has_proximity or has_wildcard or has_boolean or has_phrase:
        # Use query_string for advanced query support
        return Q(
            "query_string",
            query=search_terms,
            default_field="fulltext",
            default_operator="AND",
        )
    else:
        # Simple match query with phrase boost
        return Q(
            "match",
            fulltext={"query": search_terms, "operator": "and"}
        ) | Q(
            "match_phrase",
            fulltext={"query": search_terms, "boost": 2}
        )


@blueprint.route("/funder-search")
def funder_search():
    # Search works index on default connection
    import settings
    from core.shared_view import construct_query, execute_search, format_response

    connection = 'default'
    index_name = settings.WORKS_INDEX
    default_sort = ["_score", "publication_date", "id"]

    params = parse_params(request)

    # Build query using shared_view's construct_query, but override search behavior
    s = construct_query(params, fields_dict, index_name, default_sort, connection)

    # If there's a search param, we need to rebuild the query to only search fulltext
    if params["search"] and params["search"] != '""':
        # Create a new search object from scratch
        s = Search(index=index_name, using=connection)

        # Exclude large fields from source
        s = s.source(
            excludes=[
                "abstract",
                "embeddings",
                "fulltext",
                "authorships_full",
                "vector_embedding",
            ]
        )

        # Set size
        if params["group_by"]:
            s = s.extra(size=0)
        else:
            s = s.extra(size=params["per_page"])

        # Add cursor pagination
        if not params["group_by"]:
            from core.cursor import handle_cursor
            s = handle_cursor(params["cursor"], params["page"], s)

        # Add fulltext-only search query
        search_query = build_fulltext_query(params["search"], index_name)
        if params["sample"]:
            s = s.filter(search_query)
        else:
            s = s.query(search_query)
        s = s.params(preference=clean_preference(params["search"]))

        # Apply filters
        if params["filters"]:
            from core.filter import filter_records
            from core.preference import set_preference_for_filter_search
            s = filter_records(fields_dict, params["filters"], s, params["sample"])
            s = set_preference_for_filter_search(params["filters"], s)

        # Apply sorting
        from core.sort import get_sort_fields, sort_with_cursor, sort_with_sample
        from core.search import check_is_search_query

        is_search_query = check_is_search_query(params["filters"], params["search"])

        if params["sort"] and params["cursor"]:
            s = sort_with_cursor(
                default_sort, fields_dict, params["group_by"], s, params["sort"]
            )
        elif params["sample"]:
            s = sort_with_sample(s, params["seed"])
        elif params["sort"]:
            sort_fields = get_sort_fields(fields_dict, params["group_by"], params["sort"])
            s = s.sort(*sort_fields)
        elif is_search_query and not params["sort"]:
            s = s.sort("_score", "publication_date", "id")
        elif not params["group_by"]:
            s = s.sort(*default_sort)

        # Apply grouping
        if params["group_by"]:
            from core.group_by.utils import parse_group_by
            from core.group_by.buckets import create_group_by_buckets, add_meta_sums
            group_by, include_unknown = parse_group_by(params["group_by"])
            s = create_group_by_buckets(fields_dict, group_by, include_unknown, s, params)
        elif params["group_bys"]:
            from core.group_by.utils import parse_group_by
            from core.group_by.buckets import create_group_by_buckets
            for group_by_item in params["group_bys"]:
                group_by, include_unknown = parse_group_by(group_by_item)
                s = create_group_by_buckets(
                    fields_dict, group_by, include_unknown, s, params
                )

        # Filter group with q
        if params["group_by"] and params["q"] and params["q"] != "''":
            from core.group_by.utils import parse_group_by
            from core.group_by.filter import filter_group_by
            from core.utils import get_field
            group_by, _ = parse_group_by(params["group_by"])
            field = get_field(fields_dict, group_by)
            s = filter_group_by(field, group_by, params["q"], s)

        # Add meta sums
        from core.group_by.buckets import add_meta_sums
        s = add_meta_sums(params, index_name, s)

        # Add highlighting for fulltext field
        s = s.highlight(
            'fulltext',
            fragment_size=300,
            number_of_fragments=5,
            type='unified'
        )

        # Execute and format response
        response = execute_search(s, params)
        result = format_response(response, params, index_name, fields_dict, s, connection)

        if settings.DEBUG:
            print(s.to_dict())
    else:
        # No search param, use standard shared_view
        response = execute_search(s, params)
        result = format_response(response, params, index_name, fields_dict, s, connection)

        if settings.DEBUG:
            print(s.to_dict())

    only_fields = process_only_fields(request, FunderSearchSchema)

    # export option
    if is_group_by_export(request):
        return export_group_by(result, request)

    message_schema = MessageSchema(only=only_fields)
    return message_schema.dump(result)
