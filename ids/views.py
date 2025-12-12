import json
import random

from databricks import sql
from elasticsearch_dsl import Q, Search
from flask import Blueprint, abort, redirect, request, url_for, jsonify

import settings
from core.utils import get_data_version_connection
from authors.schemas import AuthorsSchema
from awards.schemas import AwardsSchema
from concepts.schemas import ConceptsSchema
from continents.schemas import ContinentsSchema
from countries.schemas import CountriesSchema
from domains.schemas import DomainsSchema
from fields.schemas import FieldsSchema
from funders.schemas import FundersSchema
from ids.ui_format import format_as_ui, is_ui_format
from ids.utils import (
    get_merged_id,
    is_author_openalex_id,
    is_award_openalex_id,
    is_concept_openalex_id,
    is_funder_openalex_id,
    is_institution_openalex_id,
    is_openalex_id,
    is_publisher_openalex_id,
    is_source_openalex_id,
    is_topic_openalex_id,
    is_work_openalex_id,
    normalize_doi,
    normalize_issn,
    normalize_openalex_id,
    normalize_orcid,
    normalize_pmid,
    normalize_pmcid,
    normalize_ror,
    normalize_scopus_id,
    normalize_wikidata,
    process_id_only_fields,
)
from institution_types.schemas import InstitutionTypesSchema
from institutions.schemas import InstitutionsSchema
from keywords.schemas import KeywordsSchema
from languages.schemas import LanguagesSchema
from licenses.schemas import LicensesSchema
from locations.schemas import LocationsSchema
from publishers.schemas import PublishersSchema
from sources.schemas import SourcesSchema
from source_types.schemas import SourceTypesSchema
from sdgs.schemas import SdgsSchema
from subfields.schemas import SubfieldsSchema
from topics.schemas import TopicsSchema
from work_types.schemas import TypesSchema
from works.schemas import WorksSchema

blueprint = Blueprint("ids", __name__)


# works


@blueprint.route("/works/RANDOM")
@blueprint.route("/works/random")
def works_random_get():
    s = Search(index=settings.WORKS_INDEX_LEGACY)
    only_fields = process_id_only_fields(request, WorksSchema)

    # divide queries into year groups to limit how much work the random function_score has to do
    year_groups = [
        Q("range", publication_year={"lt": 1965}),
        Q("range", publication_year={"gte": 1965, "lte": 1985}),
        Q("range", publication_year={"gte": 1986, "lte": 1990}),
        Q("range", publication_year={"gte": 1991, "lte": 1995}),
        Q("range", publication_year={"gte": 1996, "lte": 2000}),
        Q("range", publication_year={"gte": 2001, "lte": 2004}),
        Q("range", publication_year={"gte": 2005, "lte": 2006}),
        Q("range", publication_year={"gte": 2007, "lte": 2010}),
        Q("range", publication_year={"gte": 2011, "lte": 2014}),
        Q("range", publication_year={"gte": 2015, "lte": 2018}),
        Q("range", publication_year={"gte": 2019, "lte": 2020}),
        Q("range", publication_year={"gt": 2020}),
    ]
    random_query = Q(
        "function_score",
        functions={"random_score": {}},
        query=random.choice(year_groups),
    )
    s = s.query(random_query).extra(size=1)
    response = s.execute()
    works_schema = WorksSchema(context={"display_relevance": False}, only=only_fields)
    return works_schema.dump(response[0])


@blueprint.route("/works/<path:id>")
@blueprint.route("/entities/works/<path:id>")
def works_id_get(id):
    connection = get_data_version_connection(request)
    index_name = settings.WORKS_INDEX_WALDEN if connection == 'walden' else settings.WORKS_INDEX_LEGACY

    s = Search(index=index_name, using=connection)
    only_fields = process_id_only_fields(request, WorksSchema)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("ids.works_id_get", id=clean_id, **request.args))
        clean_id = int(clean_id[1:])
        full_openalex_id = f"https://openalex.org/W{clean_id}"

        query = Q("term", ids__openalex=full_openalex_id)
        s = s.filter(query)
        if s.count() == 0:
            # check if document is merged
            merged_id = get_merged_id("merge-works", full_openalex_id)
            if merged_id:
                return redirect(
                    url_for("ids.works_id_get", id=merged_id, **request.args), code=301
                )
    elif id.startswith("mag:"):
        clean_id = id.replace("mag:", "")
        clean_id = f"W{clean_id}"
        return redirect(url_for("ids.works_id_get", id=clean_id, **request.args))
    elif id.startswith("pmid:"):
        id = id.replace("pmid:", "")
        clean_pmid = normalize_pmid(id)
        full_pmid = f"https://pubmed.ncbi.nlm.nih.gov/{clean_pmid}"
        query = Q("term", ids__pmid=full_pmid)
        s = s.filter(query)
    elif id.startswith("pmcid:"):
        id = id.replace("pmcid:", "")
        clean_pmcid = normalize_pmcid(id)
        full_pmcid = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{clean_pmcid}"
        query = Q("term", ids__pmcid=full_pmcid)
        s = s.filter(query)
    elif id.startswith("doi:") or ("doi" in id):
        clean_doi = normalize_doi(id, return_none_if_error=True)
        if not clean_doi:
            abort(404)
        full_doi = f"https://doi.org/{clean_doi}"
        query = Q("term", ids__doi=full_doi)
        s = s.filter(query)
    else:
        abort(404)

    response = s.execute()
        
    if not response:
        abort(404)
    works_schema = WorksSchema(
        context={"display_relevance": False, "single_record": True}, only=only_fields
    )
    if is_ui_format():
        json_output = json.dumps(dict(works_schema.dump(response[0])))
        ui_format = format_as_ui("works", json_output)
        return jsonify(
            {
                "meta": {
                    "count": 1,
                    "page": 1,
                    "per_page": 1,
                },
                "props": ui_format,
            }
        )
    return works_schema.dump(response[0])


@blueprint.route("/v2/works/<path:id>")
def works_v2_id_get(id):
    s = Search(index=settings.WORKS_INDEX_WALDEN, using="walden")
    only_fields = process_id_only_fields(request, WorksSchema)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("ids.works_v2_id_get", id=clean_id, **request.args))
        clean_id = int(clean_id[1:])
        full_openalex_id = f"https://openalex.org/W{clean_id}"
        query = Q("term", id=full_openalex_id)
        s = s.filter(query)
    elif id.startswith("mag:"):
        clean_id = id.replace("mag:", "")
        clean_id = f"W{clean_id}"
        return redirect(url_for("ids.works_id_get", id=clean_id, **request.args))
    elif id.startswith("pmid:"):
        id = id.replace("pmid:", "")
        clean_pmid = normalize_pmid(id)
        full_pmid = f"https://pubmed.ncbi.nlm.nih.gov/{clean_pmid}"
        query = Q("term", ids__pmid=full_pmid)
        s = s.filter(query)
    elif id.startswith("pmcid:"):
        id = id.replace("pmcid:", "")
        clean_pmcid = normalize_pmcid(id)
        full_pmcid = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{clean_pmcid}"
        query = Q("term", ids__pmcid=full_pmcid)
        s = s.filter(query)
    elif id.startswith("doi:") or ("doi" in id):
        clean_doi = normalize_doi(id, return_none_if_error=True)
        if not clean_doi:
            abort(404)
        full_doi = f"https://doi.org/{clean_doi}"
        query = Q("term", ids__doi=full_doi)
        s = s.filter(query)
    else:
        abort(404)
    response = s.execute()
    if not response:
        abort(404)
    works_schema = WorksSchema(
        context={"display_relevance": False, "single_record": True}, only=only_fields
    )
    return works_schema.dump(response[0])


@blueprint.route("/v2/works-batch", methods=["POST"])
def works_v2_batch_get():
    request_data = request.get_json()

    if not request_data or not isinstance(request_data, dict) or "ids" not in request_data:
        return jsonify({"error": "Request must include 'ids' field"}), 400

    ids = request_data.get("ids", [])

    if not isinstance(ids, list):
        return jsonify({"error": "'ids' must be a list"}), 400

    if len(ids) > 100:
        return jsonify({"error": "Maximum of 100 IDs allowed per request"}), 400

    if len(ids) == 0:
        return jsonify([])

    normalized_ids = []
    for id in ids:
        if is_openalex_id(id):
            clean_id = normalize_openalex_id(id)
            clean_id = int(clean_id[1:])
            full_openalex_id = f"https://openalex.org/W{clean_id}"
            normalized_ids.append(full_openalex_id)
        else:
            # Skip invalid IDs or return error based on your preference
            continue

    if not normalized_ids:
        return jsonify({"error": "No valid IDs provided"}), 400

    # Connect to database and fetch results
    results = []
    with sql.connect(
            server_hostname=settings.DATABRICKS_HOST,
            http_path=settings.DATABRICKS_HTTP_PATH,
            access_token=settings.DATABRICKS_TOKEN,
    ) as connection:
        with connection.cursor() as cursor:
            # Use parameterized query with IN clause
            placeholders = ", ".join(["%s"] * len(normalized_ids))
            query = f"SELECT id, json_str FROM openalex.works.openalex_works_json WHERE id IN ({placeholders})"
            cursor.execute(query, normalized_ids)

            rows = cursor.fetchall()

            # Process results
            id_to_result = {}
            for row in rows:
                db_id, json_str = row
                result = json.loads(json_str)
                id_to_result[db_id] = result

            # Preserve original order from request
            for full_id in normalized_ids:
                if full_id in id_to_result:
                    results.append(id_to_result[full_id])
                else:
                    results.append(None)
    return jsonify(results)


# Author


@blueprint.route("/authors/RANDOM")
@blueprint.route("/authors/random")
@blueprint.route("/people/random")
def authors_random_get():
    connection = get_data_version_connection(request)
    index_name = settings.AUTHORS_INDEX_WALDEN if connection == 'walden' else settings.AUTHORS_INDEX_LEGACY
    s = Search(index=index_name, using=connection)
    only_fields = process_id_only_fields(request, AuthorsSchema)

    # divide queries into year groups to limit how much work the random function_score has to do
    cited_by_groups = [
        Q("term", cited_by_count=0),
        Q("range", cited_by_count={"gt": 1}),
    ]
    random_query = Q(
        "function_score",
        functions={"random_score": {}},
        query=random.choice(cited_by_groups),
    )
    s = s.query(random_query).extra(size=1)
    response = s.execute()
    authors_schema = AuthorsSchema(
        context={"display_relevance": False}, only=only_fields
    )
    return authors_schema.dump(response[0])


@blueprint.route("/authors/<path:id>")
@blueprint.route("/people/<path:id>")
@blueprint.route("/entities/authors/<path:id>")
def authors_id_get(id):
    connection = get_data_version_connection(request)
    index_name = settings.AUTHORS_INDEX_WALDEN if connection == 'walden' else settings.AUTHORS_INDEX_LEGACY

    s = Search(index=index_name, using=connection)
    only_fields = process_id_only_fields(request, AuthorsSchema)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("ids.authors_id_get", id=clean_id, **request.args))
        author_id = int(clean_id[1:])
        full_author_id = f"https://openalex.org/A{author_id}"
        query = Q("term", ids__openalex=full_author_id)
        s = s.filter(query)
        if s.count() == 0:
            # check if document is merged
            merged_id = get_merged_id("merge-authors-v1", full_author_id)
            if merged_id:
                return redirect(
                    url_for("ids.authors_id_get", id=merged_id, **request.args),
                    code=301,
                )
    elif id.startswith("mag:"):
        clean_id = id.replace("mag:", "")
        clean_id = f"A{clean_id}"
        return redirect(url_for("ids.authors_id_get", id=clean_id, **request.args))
    elif id.startswith("orcid:") or id.startswith("https://orcid.org"):
        clean_orcid = normalize_orcid(id)
        if not clean_orcid:
            return abort(404)
        full_orcid = f"https://orcid.org/{clean_orcid}"
        query = Q("term", ids__orcid=full_orcid)
        s = s.filter(query)
    elif id.startswith("scopus:") or id.startswith("https://www.scopus.com"):
        scopus_id = id.replace("scopus:", "")
        clean_scopus = normalize_scopus_id(scopus_id)
        if not clean_scopus:
            return abort(404)
        query = Q("term", ids__scopus__keyword=clean_scopus)
        s = s.filter(query)
    else:
        abort(404)
    response = s.execute()
    if not response:
        abort(404)
    authors_schema = AuthorsSchema(
        context={"display_relevance": False}, only=only_fields
    )
    if is_ui_format():
        json_output = json.dumps(dict(authors_schema.dump(response[0])))
        ui_format = format_as_ui("authors", json_output)
        return jsonify(
            {
                "meta": {
                    "count": 1,
                    "page": 1,
                    "per_page": 1,
                },
                "props": ui_format,
            }
        )
    return authors_schema.dump(response[0])


# Institution


@blueprint.route("/institutions/RANDOM")
@blueprint.route("/institutions/random")
def institutions_random_get():
    s = Search(index=settings.INSTITUTIONS_INDEX)
    only_fields = process_id_only_fields(request, InstitutionsSchema)

    random_query = Q("function_score", functions={"random_score": {}})
    s = s.query(random_query).extra(size=1)
    response = s.execute()
    institutions_schema = InstitutionsSchema(
        context={"display_relevance": False}, only=only_fields
    )
    return institutions_schema.dump(response[0])


@blueprint.route("/institutions/<path:id>")
@blueprint.route("/entities/institutions/<path:id>")
def institutions_id_get(id):
    connection = get_data_version_connection(request)

    s = Search(index=settings.INSTITUTIONS_INDEX, using=connection)
    only_fields = process_id_only_fields(request, InstitutionsSchema)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(
                url_for("ids.institutions_id_get", id=clean_id, **request.args)
            )
        clean_id = int(clean_id[1:])
        full_openalex_id = f"https://openalex.org/I{clean_id}"
        query = Q("term", ids__openalex=full_openalex_id)
        s = s.filter(query)

        # Execute search and check if document exists
        response = s.execute()
        if not response.hits:  # Check if any hits were returned
            # check if document is merged
            merged_id = get_merged_id("merge-institutions", full_openalex_id)
            if merged_id:
                return redirect(
                    url_for("ids.institutions_id_get", id=merged_id, **request.args),
                    code=301,
                )
            abort(404)

    elif id.startswith("mag:"):
        clean_id = id.replace("mag:", "")
        clean_id = f"I{clean_id}"
        return redirect(url_for("ids.institutions_id_get", id=clean_id, **request.args))
    elif id.startswith("ror:") or ("ror.org" in id):
        clean_ror = normalize_ror(id)
        if not clean_ror:
            abort(404)
        full_ror = f"https://ror.org/{clean_ror}"
        query = Q("term", ror=full_ror)
        s = s.filter(query)
        response = s.execute()
    elif id.startswith("wikidata:") or ("wikidata" in id):
        clean_wikidata = normalize_wikidata(id)
        if not clean_wikidata:
            abort(404)
        full_wikidata = f"https://www.wikidata.org/wiki/{clean_wikidata}"
        query = Q("term", ids__wikidata=full_wikidata)
        s = s.filter(query)
        response = s.execute()
    else:
        abort(404)

    # Remove the duplicate response execution since we handle it above
    if not response.hits:  # Use response.hits instead of just response
        abort(404)

    institutions_schema = InstitutionsSchema(
        context={"display_relevance": False}, only=only_fields
    )
    if is_ui_format():
        json_output = json.dumps(dict(institutions_schema.dump(response[0])))
        ui_format = format_as_ui("institutions", json_output)
        return jsonify(
            {
                "meta": {
                    "count": 1,
                    "page": 1,
                    "per_page": 1,
                },
                "props": ui_format,
            }
        )
    return institutions_schema.dump(response[0])


# Concept


@blueprint.route("/concepts/RANDOM")
@blueprint.route("/concepts/random")
def concepts_random_get():
    s = Search(index=settings.CONCEPTS_INDEX)
    only_fields = process_id_only_fields(request, ConceptsSchema)

    random_query = Q("function_score", functions={"random_score": {}})
    s = s.query(random_query).extra(size=1)
    response = s.execute()
    concepts_schema = ConceptsSchema(
        context={"display_relevance": False}, only=only_fields
    )
    return concepts_schema.dump(response[0])


@blueprint.route("/concepts/<path:id>")
@blueprint.route("/entities/concepts/<path:id>")
def concepts_id_get(id):
    connection = get_data_version_connection(request)

    s = Search(index=settings.CONCEPTS_INDEX, using=connection)
    only_fields = process_id_only_fields(request, ConceptsSchema)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("ids.concepts_id_get", id=clean_id, **request.args))
        clean_id = int(clean_id[1:])
        full_openalex_id = f"https://openalex.org/C{clean_id}"
        query = Q("term", ids__openalex=full_openalex_id)
        s = s.filter(query)
        if s.count() == 0:
            # check if document is merged
            merged_id = get_merged_id("merge-concepts", full_openalex_id)
            if merged_id:
                return redirect(
                    url_for("ids.concepts_id_get", id=merged_id, **request.args),
                    code=301,
                )
    elif id.startswith("mag:"):
        clean_id = id.replace("mag:", "")
        clean_id = f"C{clean_id}"
        return redirect(url_for("ids.concepts_id_get", id=clean_id, **request.args))
    elif id.startswith("wikidata:") or ("wikidata" in id):
        clean_wikidata = normalize_wikidata(id)
        if not clean_wikidata:
            abort(404)
        full_wikidata = f"https://www.wikidata.org/wiki/{clean_wikidata}"
        query = Q("term", wikidata=full_wikidata)
        s = s.filter(query)
    else:
        abort(404)
    response = s.execute()
    if not response:
        abort(404)
    concepts_schema = ConceptsSchema(
        context={"display_relevance": False}, only=only_fields
    )
    if is_ui_format():
        json_output = json.dumps(dict(concepts_schema.dump(response[0])))
        ui_format = format_as_ui("concepts", json_output)
        return jsonify(
            {
                "meta": {
                    "count": 1,
                    "page": 1,
                    "per_page": 1,
                },
                "props": ui_format,
            }
        )
    return concepts_schema.dump(response[0])


@blueprint.route("/concepts/name/<string:name>")
def concepts_name_get(name):
    s = Search(index=settings.CONCEPTS_INDEX)

    query = Q("match_phrase_prefix", display_name=name)
    s = s.query(query)
    response = s.execute()
    if not response:
        abort(404)
    concepts_schema = ConceptsSchema(context={"display_relevance": False})
    return concepts_schema.dump(response[0])


# Funder


@blueprint.route("/funders/RANDOM")
@blueprint.route("/funders/random")
def funders_random_get():
    s = Search(index=settings.FUNDERS_INDEX)
    only_fields = process_id_only_fields(request, FundersSchema)

    random_query = Q("function_score", functions={"random_score": {}})
    s = s.query(random_query).extra(size=1)
    response = s.execute()
    funders_schema = FundersSchema(
        context={"display_relevance": False}, only=only_fields
    )
    return funders_schema.dump(response[0])


@blueprint.route("/funders/<path:id>")
@blueprint.route("/entities/funders/<path:id>")
def funders_id_get(id):
    connection = get_data_version_connection(request)

    s = Search(index=settings.FUNDERS_INDEX, using=connection)
    only_fields = process_id_only_fields(request, FundersSchema)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("ids.funders_id_get", id=clean_id, **request.args))
        clean_id = int(clean_id[1:])
        full_openalex_id = f"https://openalex.org/F{clean_id}"
        query = Q("term", ids__openalex=full_openalex_id)
        s = s.filter(query)
        if s.count() == 0:
            # check if document is merged
            merged_id = get_merged_id("merge-funders", full_openalex_id)
            if merged_id:
                return redirect(
                    url_for("ids.funders_id_get", id=merged_id, **request.args),
                    code=301,
                )
    elif id.startswith("ror:") or ("ror.org" in id):
        clean_ror = normalize_ror(id)
        if not clean_ror:
            abort(404)
        full_ror = f"https://ror.org/{clean_ror}"
        query = Q("term", ids__ror=full_ror)
        s = s.filter(query)

    elif id.startswith("wikidata:") or ("wikidata" in id):
        clean_wikidata = normalize_wikidata(id)
        if not clean_wikidata:
            abort(404)
        full_wikidata = f"https://www.wikidata.org/entity/{clean_wikidata}"
        query = Q("term", ids__wikidata=full_wikidata)
        s = s.filter(query)
    else:
        abort(404)
    response = s.execute()
    if not response:
        abort(404)
    funders_schema = FundersSchema(
        context={"display_relevance": False}, only=only_fields
    )
    if is_ui_format():
        json_output = json.dumps(dict(funders_schema.dump(response[0])))
        ui_format = format_as_ui("funders", json_output)
        return jsonify(
            {
                "meta": {
                    "count": 1,
                    "page": 1,
                    "per_page": 1,
                },
                "props": ui_format,
            }
        )
    return funders_schema.dump(response[0])


# Publisher


@blueprint.route("/publishers/<path:id>")
@blueprint.route("/entities/publishers/<path:id>")
def publishers_id_get(id):
    connection = get_data_version_connection(request)

    s = Search(index=settings.PUBLISHERS_INDEX, using=connection)
    only_fields = process_id_only_fields(request, PublishersSchema)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(
                url_for("ids.publishers_id_get", id=clean_id, **request.args)
            )
        clean_id = int(clean_id[1:])
        full_openalex_id = f"https://openalex.org/P{clean_id}"

        # Use different field name for v2
        if connection == 'walden':
            query = Q("term", id=full_openalex_id)
        else:
            query = Q("term", ids__openalex=full_openalex_id)
        s = s.filter(query)
        if s.count() == 0:
            # check if document is merged
            merged_id = get_merged_id("merge-publishers", full_openalex_id)
            if merged_id:
                return redirect(
                    url_for("ids.publishers_id_get", id=merged_id, **request.args),
                    code=301,
                )
    elif id.startswith("ror:") or ("ror.org" in id):
        clean_ror = normalize_ror(id)
        if not clean_ror:
            abort(404)
        full_ror = f"https://ror.org/{clean_ror}"
        query = Q("term", ids__ror=full_ror)
        s = s.filter(query)
    else:
        abort(404)
        
    response = s.execute()
        
    if not response:
        abort(404)
    publishers_schema = PublishersSchema(
        context={"display_relevance": False}, only=only_fields
    )
    if is_ui_format():
        json_output = json.dumps(dict(publishers_schema.dump(response[0])))
        ui_format = format_as_ui("publishers", json_output)
        return jsonify(
            {
                "meta": {
                    "count": 1,
                    "page": 1,
                    "per_page": 1,
                },
                "props": ui_format,
            }
        )
    return publishers_schema.dump(response[0])


@blueprint.route("/publishers/RANDOM")
@blueprint.route("/publishers/random")
def publishers_random_get():
    s = Search(index=settings.PUBLISHERS_INDEX)
    only_fields = process_id_only_fields(request, PublishersSchema)

    random_query = Q("function_score", functions={"random_score": {}})
    s = s.query(random_query).extra(size=1)
    response = s.execute()
    publishers_schema = PublishersSchema(
        context={"display_relevance": False}, only=only_fields
    )
    return publishers_schema.dump(response[0])


# Source


@blueprint.route("/sources/RANDOM")
@blueprint.route("/sources/random")
@blueprint.route("/journals/random")
def sources_random_get():
    s = Search(index=settings.SOURCES_INDEX)
    only_fields = process_id_only_fields(request, SourcesSchema)

    random_query = Q("function_score", functions={"random_score": {}})
    s = s.query(random_query).extra(size=1)
    response = s.execute()
    sources_schema = SourcesSchema(
        context={"display_relevance": False}, only=only_fields
    )
    return sources_schema.dump(response[0])


@blueprint.route("/sources/<path:id>")
@blueprint.route("/journals/<path:id>", endpoint="journals_id_get")
@blueprint.route("/entities/sources/<path:id>")
def sources_id_get(id):
    connection = get_data_version_connection(request)

    s = Search(index=settings.SOURCES_INDEX, using=connection)
    only_fields = process_id_only_fields(request, SourcesSchema)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("ids.sources_id_get", id=clean_id, **request.args))
        clean_id = int(clean_id[1:])
        full_openalex_id = f"https://openalex.org/S{clean_id}"

        # Use different field name for v2
        if connection == 'walden':
            query = Q("term", id=full_openalex_id)
        else:
            query = Q("term", ids__openalex=full_openalex_id)
        s = s.filter(query)
        # Check if document exists
        if s.count() == 0:
            # check if document is merged
            merged_id = get_merged_id("merge-sources", full_openalex_id)
            if merged_id:
                return redirect(
                    url_for("ids.sources_id_get", id=merged_id, **request.args),
                    code=301,
                )

    elif id.startswith("mag:"):
        clean_id = id.replace("mag:", "")
        clean_id = f"S{clean_id}"
        return redirect(url_for("ids.sources_id_get", id=clean_id, **request.args))
    elif id.startswith("issn:"):
        clean_issn = normalize_issn(id)
        if not clean_issn:
            abort(404)
        query = Q("term", ids__issn__lower=clean_issn)
        s = s.filter(query)
        response = s.execute()
        if response:
            record_id = response[0].id
            clean_id = normalize_openalex_id(record_id)
            return redirect(url_for("ids.sources_id_get", id=clean_id, **request.args))
        else:
            abort(404)
    elif id.startswith("issn_l:"):
        clean_issn = normalize_issn(id)
        if not clean_issn:
            abort(404)
        query = Q("term", ids__issn_l__lower=clean_issn)
        s = s.filter(query)
        response = s.execute()
        if response:
            record_id = response[0].id
            clean_id = normalize_openalex_id(record_id)
            return redirect(url_for("ids.sources_id_get", id=clean_id, **request.args))
        else:
            abort(404)
    else:
        abort(404)
        
    response = s.execute()
        
    if not response:
        abort(404)
    sources_schema = SourcesSchema(
        context={"display_relevance": False}, only=only_fields
    )
    if is_ui_format():
        json_output = json.dumps(dict(sources_schema.dump(response[0])))
        ui_format = format_as_ui("sources", json_output)
        return jsonify(
            {
                "meta": {
                    "count": 1,
                    "page": 1,
                    "per_page": 1,
                },
                "props": ui_format,
            }
        )
    return sources_schema.dump(response[0])


# Topic


@blueprint.route("/topics/RANDOM")
@blueprint.route("/topics/random")
def topics_random_get():
    s = Search(index=settings.TOPICS_INDEX)
    only_fields = process_id_only_fields(request, TopicsSchema)

    random_query = Q("function_score", functions={"random_score": {}})
    s = s.query(random_query).extra(size=1)
    response = s.execute()
    topics_schema = TopicsSchema(context={"display_relevance": False}, only=only_fields)
    return topics_schema.dump(response[0])


@blueprint.route("/topics/<path:id>")
@blueprint.route("/entities/topics/<path:id>")
def topics_id_get(id):
    connection = get_data_version_connection(request)

    s = Search(index=settings.TOPICS_INDEX, using=connection)
    only_fields = process_id_only_fields(request, TopicsSchema)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("ids.topics_id_get", id=clean_id, **request.args))
        clean_id = int(clean_id[1:])
        full_openalex_id = f"https://openalex.org/T{clean_id}"
        query = Q("term", id=full_openalex_id)
        s = s.filter(query)
    else:
        abort(404)
    response = s.execute()
    if not response:
        abort(404)
    topics_schema = TopicsSchema(context={"display_relevance": False}, only=only_fields)
    if is_ui_format():
        json_output = json.dumps(dict(topics_schema.dump(response[0])))
        ui_format = format_as_ui("topics", json_output)
        return jsonify(
            {
                "meta": {
                    "count": 1,
                    "page": 1,
                    "per_page": 1,
                },
                "props": ui_format,
            }
        )
    return topics_schema.dump(response[0])


@blueprint.route("/awards/<path:id>")
def awards_id_get(id):
    # Awards data only exists in WALDEN connection, not in default/prod
    connection = 'walden'

    s = Search(index=settings.AWARDS_INDEX, using=connection)
    only_fields = process_id_only_fields(request, AwardsSchema)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("ids.awards_id_get", id=clean_id, **request.args))
        clean_id = int(clean_id[1:])
        full_openalex_id = f"https://openalex.org/G{clean_id}"
        query = Q("term", id=full_openalex_id)
        s = s.filter(query)
    else:
        abort(404)
    response = s.execute()
    if not response:
        abort(404)
    awards_schema = AwardsSchema(context={"display_relevance": False}, only=only_fields)
    if is_ui_format():
        json_output = json.dumps(dict(awards_schema.dump(response[0])))
        ui_format = format_as_ui("awards", json_output)
        return jsonify(
            {
                "meta": {
                    "count": 1,
                    "page": 1,
                    "per_page": 1,
                },
                "props": ui_format,
            }
        )
    return awards_schema.dump(response[0])


def get_by_openalex_external_id(index, schema, id):
    connection = get_data_version_connection(request)

    s = Search(index=index, using=connection)
    only_fields = process_id_only_fields(request, schema)

    if index.startswith("institution-types"):
        entity_name = endpoint_name = "institution-types"
    elif index.startswith("source-types"):
        entity_name = endpoint_name = "source-types"
    elif index.startswith("work-types"):
        entity_name = "work-types"
        endpoint_name = "types"
    else:
        entity_name = endpoint_name = index.split("-")[0]

    clean_id = str(id).lower()
    formatted_id = f"https://openalex.org/{endpoint_name}/{clean_id}"

    query = Q("term", id__lower=formatted_id)
    response = s.filter(query).execute()

    if not response:
        abort(404, description=f"No {endpoint_name} found matching the ID.")

    schema_instance = schema(context={"display_relevance": False}, only=only_fields)
    if is_ui_format():
        json_output = json.dumps(dict(schema_instance.dump(response[0])))
        ui_format = format_as_ui(entity_name, json_output)
        return jsonify(
            {
                "meta": {
                    "count": 1,
                    "page": 1,
                    "per_page": 1,
                },
                "props": ui_format,
            }
        )
    return schema_instance.dump(response[0])


@blueprint.route("/sdgs/<path:id>")
@blueprint.route("/entities/sdgs/<path:id>")
def sdgs_id_get(id):
    return get_by_openalex_external_id(settings.SDGS_INDEX, SdgsSchema, id)


@blueprint.route("/continents/<path:id>")
@blueprint.route("/entities/continents/<path:id>")
def continents_id_get(id):
    return get_by_openalex_external_id(settings.CONTINENTS_INDEX, ContinentsSchema, id)


@blueprint.route("/countries/<path:id>")
@blueprint.route("/entities/countries/<path:id>")
def countries_id_get(id):
    return get_by_openalex_external_id(settings.COUNTRIES_INDEX, CountriesSchema, id)


@blueprint.route("/institution-types/<path:id>")
@blueprint.route("/entities/institution-types/<path:id>")
def institution_types_id_get(id):
    return get_by_openalex_external_id(
        settings.INSTITUTION_TYPES_INDEX, InstitutionTypesSchema, id
    )


@blueprint.route("/languages/<path:id>")
@blueprint.route("/entities/languages/<path:id>")
def languages_id_get(id):
    return get_by_openalex_external_id(settings.LANGUAGES_INDEX, LanguagesSchema, id)


@blueprint.route("/types/<path:id>")
@blueprint.route("/work-types/<path:id>")
@blueprint.route("/entities/work-types/<path:id>")
def types_id_get(id):
    return get_by_openalex_external_id(settings.WORK_TYPES_INDEX, TypesSchema, id)


@blueprint.route("/source-types/<path:id>")
@blueprint.route("/entities/source-types/<path:id>")
def source_types_id_get(id):
    return get_by_openalex_external_id(
        settings.SOURCE_TYPES_INDEX, SourceTypesSchema, id
    )


@blueprint.route("/domains/<path:id>")
@blueprint.route("/entities/domains/<path:id>")
def domains_id_get(id):
    return get_by_openalex_external_id(settings.DOMAINS_INDEX, DomainsSchema, id)


@blueprint.route("/fields/<path:id>")
@blueprint.route("/entities/fields/<path:id>")
def fields_id_get(id):
    return get_by_openalex_external_id(settings.FIELDS_INDEX, FieldsSchema, id)


@blueprint.route("/subfields/<path:id>")
@blueprint.route("/entities/subfields/<path:id>")
def subfields_id_get(id):
    return get_by_openalex_external_id(settings.SUBFIELDS_INDEX, SubfieldsSchema, id)


@blueprint.route("/keywords/<path:id>")
@blueprint.route("/entities/keywords/<path:id>")
def keywords_id_get(id):
    connection = get_data_version_connection(request)

    s = Search(index=settings.KEYWORDS_INDEX, using=connection)
    only_fields = process_id_only_fields(request, KeywordsSchema)

    clean_id = str(id).lower()
    formatted_id = f"https://openalex.org/keywords/{clean_id}"

    query = Q("term", id__lower=formatted_id)
    response = s.filter(query).execute()
        
    if not response:
        abort(404)
        
    keywords_schema = KeywordsSchema(context={"display_relevance": False}, only=only_fields)
    if is_ui_format():
        json_output = json.dumps(dict(keywords_schema.dump(response[0])))
        ui_format = format_as_ui("keywords", json_output)
        return jsonify(
            {
                "meta": {
                    "count": 1,
                    "page": 1,
                    "per_page": 1,
                },
                "props": ui_format,
            }
        )
    return keywords_schema.dump(response[0])


@blueprint.route("/v2/keywords/<path:id>")
def keywords_v2_id_get(id):
    s = Search(index="keywords-v1", using="walden")
    only_fields = process_id_only_fields(request, KeywordsSchema)

    clean_id = str(id).lower()
    formatted_id = f"https://openalex.org/keywords/{clean_id}"
    query = Q("term", id=formatted_id)
    s = s.filter(query)

    response = s.execute()
        
    if not response:
        abort(404)
        
    keywords_schema = KeywordsSchema(context={"display_relevance": False}, only=only_fields)
    return keywords_schema.dump(response[0])


@blueprint.route("/licenses/<path:id>")
@blueprint.route("/entities/licenses/<path:id>")
def licenses_id_get(id):
    return get_by_openalex_external_id(settings.LICENSES_INDEX, LicensesSchema, id)


# Location

@blueprint.route("/locations/<path:id>")
@blueprint.route("/v2/locations/<path:id>")
def locations_id_get(id):
    s = Search(index="locations-v1", using="walden")
    only_fields = process_id_only_fields(request, LocationsSchema)

    query = Q("term", id=id)
    s = s.filter(query)

    response = s.execute()
    
    if not response:
        abort(404)
    
    locations_schema = LocationsSchema(
        context={"display_relevance": False}, only=only_fields
    )
    return locations_schema.dump(response[0])

# Universal


@blueprint.route("/<path:openalex_id>")
def universal_get(openalex_id):
    if not openalex_id:
        return {"message": "Don't panic"}, 404

    # Skip if this is an entities route (e.g., /entities/works)
    if openalex_id.startswith("entities/"):
        abort(404)

    if not is_openalex_id(openalex_id):
        return {"message": "OpenAlex ID format not recognized"}, 404

    openalex_id = normalize_openalex_id(openalex_id)
    
    # Check awards first since it's a new entity type
    if is_award_openalex_id(openalex_id):
        return redirect(url_for("ids.awards_id_get", id=openalex_id, **request.args))
    elif is_work_openalex_id(openalex_id):
        return redirect(url_for("ids.works_id_get", id=openalex_id, **request.args))
    elif is_author_openalex_id(openalex_id):
        return redirect(url_for("ids.authors_id_get", id=openalex_id, **request.args))
    elif is_institution_openalex_id(openalex_id):
        return redirect(
            url_for("ids.institutions_id_get", id=openalex_id, **request.args)
        )
    elif is_concept_openalex_id(openalex_id):
        return redirect(url_for("ids.concepts_id_get", id=openalex_id, **request.args))
    elif is_funder_openalex_id(openalex_id):
        return redirect(url_for("ids.funders_id_get", id=openalex_id, **request.args))
    elif is_publisher_openalex_id(openalex_id):
        return redirect(
            url_for("ids.publishers_id_get", id=openalex_id, **request.args)
        )
    elif is_source_openalex_id(openalex_id):
        return redirect(url_for("ids.sources_id_get", id=openalex_id, **request.args))
    elif is_topic_openalex_id(openalex_id):
        return redirect(url_for("ids.topics_id_get", id=openalex_id, **request.args))
    return {"message": "OpenAlex ID format not recognized"}, 404
