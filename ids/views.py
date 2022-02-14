import random

from elasticsearch_dsl import Q, Search
from flask import Blueprint, abort, redirect, request, url_for

from authors.schemas import AuthorsSchema
from concepts.schemas import ConceptsSchema
from ids.utils import (is_author_openalex_id, is_concept_openalex_id,
                       is_institution_openalex_id, is_openalex_id,
                       is_venue_openalex_id, is_work_openalex_id,
                       normalize_doi, normalize_openalex_id, normalize_orcid)
from institutions.schemas import InstitutionsSchema
from settings import (AUTHORS_INDEX, CONCEPTS_INDEX, INSTITUTIONS_INDEX,
                      VENUES_INDEX, WORKS_INDEX)
from venues.schemas import VenuesSchema
from works.schemas import WorksSchema

blueprint = Blueprint("ids", __name__)


# works


@blueprint.route("/works/RANDOM")
@blueprint.route("/works/random")
def works_random_get():
    s = Search(index=WORKS_INDEX)

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
    works_schema = WorksSchema()
    return works_schema.dump(response[0])


@blueprint.route("/works/<path:id>")
def works_id_get(id):
    s = Search(index=WORKS_INDEX)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("ids.works_id_get", id=clean_id, **request.args))
        clean_id = int(clean_id[1:])
        clean_id = f"https://openalex.org/W{clean_id}"
        query = Q("term", ids__openalex=clean_id)
        s = s.query(query)
    elif id.startswith("mag:"):
        clean_id = id.replace("mag:", "")
        clean_id = f"W{clean_id}"
        return redirect(url_for("ids.works_id_get", id=clean_id, **request.args))
    elif id.startswith("doi:") or ("doi" in id):
        clean_doi = normalize_doi(id, return_none_if_error=True)
        if not clean_doi:
            abort(404)
        clean_doi = f"https://doi.org/{clean_doi}"
        query = Q("term", ids__doi=clean_doi)
        s = s.query(query)
    else:
        abort(404)
    response = s.execute()
    works_schema = WorksSchema()
    return works_schema.dump(response[0])


# Author


@blueprint.route("/authors/RANDOM")
@blueprint.route("/authors/random")
def authors_random_get():
    s = Search(index=AUTHORS_INDEX)

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
    authors_schema = AuthorsSchema()
    return authors_schema.dump(response[0])


@blueprint.route("/authors/<path:id>")
def authors_id_get(id):
    s = Search(index=AUTHORS_INDEX)

    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("ids.authors_id_get", id=clean_id, **request.args))
        author_id = int(clean_id[1:])
        clean_author_id = f"https://openalex.org/A{author_id}"
        query = Q("term", ids__openalex=clean_author_id)
        s = s.query(query)
    elif id.startswith("mag:"):
        clean_id = id.replace("mag:", "")
        clean_id = f"A{clean_id}"
        return redirect(url_for("ids.authors_id_get", id=clean_id, **request.args))
    elif id.startswith("orcid:") or id.startswith("https://orcid.org"):
        clean_orcid = normalize_orcid(id)
        clean_orcid = f"https://orcid.org/{clean_orcid}"
        query = Q("term", ids__orcid=clean_orcid)
        s = s.query(query)
    else:
        abort(404)
    response = s.execute()
    authors_schema = AuthorsSchema()
    return authors_schema.dump(response[0])


# Institution


@blueprint.route("/institutions/RANDOM")
@blueprint.route("/institutions/random")
def institutions_random_get():
    s = Search(index=INSTITUTIONS_INDEX)

    random_query = Q("function_score", functions={"random_score": {}})
    s = s.query(random_query).extra(size=1)
    response = s.execute()
    institutions_schema = InstitutionsSchema()
    return institutions_schema.dump(response[0])


@blueprint.route("/institutions/<path:id>")
def institutions_id_get(id):
    from util import normalize_ror

    obj = None
    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("institutions_id_get", id=clean_id, **request.args))
        clean_id = int(clean_id[1:])
        obj = models.institution_from_id(clean_id)
    elif id.startswith("mag:"):
        clean_id = id.replace("mag:", "")
        clean_id = f"V{clean_id}"
        return redirect(url_for("institutions_id_get", id=clean_id, **request.args))
    elif id.startswith("ror:") or ("ror.org" in id):
        clean_ror = normalize_ror(id)
        openalex_id = models.openalex_id_from_ror(clean_ror)
        if openalex_id:
            return redirect(
                url_for("institutions_id_get", id=openalex_id, **request.args)
            )
    if not obj:
        abort(404)
    response = obj.to_dict()
    return jsonify_fast_no_sort(response)


# Venue


@blueprint.route("/venues/RANDOM")
@blueprint.route("/venues/random")
def venues_random_get():
    s = Search(index=VENUES_INDEX)

    random_query = Q("function_score", functions={"random_score": {}})
    s = s.query(random_query).extra(size=1)
    response = s.execute()
    venues_schema = VenuesSchema()
    return venues_schema.dump(response[0])


@blueprint.route("/venues/<path:id>")
def venues_id_get(id):
    from util import normalize_issn

    obj = None
    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("venues_id_get", id=clean_id, **request.args))
        clean_id = int(clean_id[1:])
        obj = models.journal_from_id(clean_id)
    elif id.startswith("mag:"):
        clean_id = id.replace("mag:", "")
        clean_id = f"V{clean_id}"
        return redirect(url_for("venues_id_get", id=clean_id, **request.args))
    elif id.startswith("issn:"):
        clean_issn = normalize_issn(id)
        openalex_id = models.openalex_id_from_issn(clean_issn)
        if openalex_id:
            return redirect(url_for("venues_id_get", id=openalex_id, **request.args))
    if not obj:
        abort(404)
    response = obj.to_dict()
    return jsonify_fast_no_sort(response)


# Concept


@blueprint.route("/concepts/RANDOM")
@blueprint.route("/concepts/random")
def concepts_random_get():
    s = Search(index=CONCEPTS_INDEX)

    random_query = Q("function_score", functions={"random_score": {}})
    s = s.query(random_query).extra(size=1)
    response = s.execute()
    concepts_schema = ConceptsSchema()
    return concepts_schema.dump(response[0])


@blueprint.route("/concepts/<path:id>")
def concepts_id_get(id):
    from util import normalize_wikidata

    obj = None
    if is_openalex_id(id):
        clean_id = normalize_openalex_id(id)
        if clean_id != id:
            return redirect(url_for("concepts_id_get", id=clean_id, **request.args))
        clean_id = int(clean_id[1:])
        obj = models.concept_from_id(clean_id)
    elif id.startswith("mag:"):
        clean_id = id.replace("mag:", "")
        clean_id = f"V{clean_id}"
        return redirect(url_for("concepts_id_get", id=clean_id, **request.args))
    elif id.startswith("wikidata:") or ("wikidata" in id):
        clean_wikidata = normalize_wikidata(id)
        openalex_id = models.openalex_id_from_wikidata(clean_wikidata)
        if openalex_id:
            return redirect(url_for("concepts_id_get", id=openalex_id, **request.args))
    if not obj:
        abort(404)
    response = obj.to_dict()
    return jsonify_fast_no_sort(response)


@blueprint.route("/concepts/name/<string:name>")
def concepts_name_get(name):
    obj = models.concept_from_name(name)
    if not obj:
        abort(404)
    return jsonify_fast_no_sort(obj.to_dict())


# Universal


@blueprint.route("/<path:openalex_id>")
def universal_get(openalex_id):
    if not openalex_id:
        return {"message": "Don't panic"}, 404

    if not is_openalex_id(openalex_id):
        return {"message": "OpenAlex ID format not recognized"}, 404

    openalex_id = normalize_openalex_id(openalex_id)
    if is_work_openalex_id(openalex_id):
        return redirect(url_for("works_id_get", id=openalex_id, **request.args))
    elif is_author_openalex_id(openalex_id):
        return redirect(url_for("authors_id_get", id=openalex_id, **request.args))
    elif is_venue_openalex_id(openalex_id):
        return redirect(url_for("venues_id_get", id=openalex_id, **request.args))
    elif is_institution_openalex_id(openalex_id):
        return redirect(url_for("institutions_id_get", id=openalex_id, **request.args))
    elif is_concept_openalex_id(openalex_id):
        return redirect(url_for("concepts_id_get", id=openalex_id, **request.args))
    return {"message": "OpenAlex ID format not recognized"}, 404


# @blueprint.route('/RANDOM')
# @blueprint.route('/random')
# def records_random_get():
#     from models import Record
#     obj = db.session.query(Record).order_by(func.random()).first()
#     if not obj:
#         abort(404)
#     return jsonify_fast_no_sort({"n": len(obj.siblings), "siblings": obj.siblings})
#
#
#
# @blueprint.route('/records/<id>')
# def records_id_get(id):
#     from models import Record
#     obj = Record.query.get(id)
#     return jsonify_fast_no_sort({"n": len(obj.siblings), "siblings": obj.siblings})
