"""Endpoint-level tests for the top-level `corpus=` REST param (oxjob #763).

Only the 400 paths — they raise before any ES query is built, so they run
without an Elasticsearch (unlike most of tests/functional). The corpus→filter
mapping itself is unit-tested in tests/unit/test_corpus_param.py.
"""


def test_corpus_invalid_value_400s(client):
    res = client.get("/works?corpus=banana")
    assert res.status_code == 400, res.get_json()
    assert "core, expansion, all" in res.get_json()["message"]


def test_corpus_plus_include_xpac_400s_even_when_agreeing(client):
    # corpus=all and include_xpac=true mean the same thing — still rejected:
    # the two vocabularies never mix.
    res = client.get("/works?corpus=all&include_xpac=true")
    assert res.status_code == 400, res.get_json()
    message = res.get_json()["message"]
    assert "deprecated legacy" in message
    assert "corpus" in message


def test_corpus_plus_include_xpac_hyphen_spelling_400s(client):
    res = client.get("/works?corpus=expansion&include-xpac=true")
    assert res.status_code == 400, res.get_json()


def test_corpus_plus_is_xpac_filter_400s(client):
    res = client.get("/works?corpus=expansion&filter=is_xpac:true")
    assert res.status_code == 400, res.get_json()
    assert "is_xpac" in res.get_json()["message"]


def test_corpus_on_non_works_endpoint_is_generic_unknown_param(client):
    # Works-only param: /authors keeps the stock unknown-param 400, identical
    # in shape to any other unsupported spelling.
    res = client.get("/authors?corpus=all")
    assert res.status_code == 400, res.get_json()
    assert "corpus is not a valid parameter" in res.get_json()["message"]

    bogus = client.get("/authors?someboguparam=1")
    assert bogus.status_code == 400
    assert "not a valid parameter" in bogus.get_json()["message"]


def test_works_unknown_param_message_now_lists_corpus(client):
    res = client.get("/works?someboguparam=1")
    assert res.status_code == 400, res.get_json()
    message = res.get_json()["message"]
    assert "not a valid parameter" in message
    assert "corpus" in message


def test_query_oxurl_translate_carries_corpus(client):
    res = client.get("/query/oxurl/works?corpus=expansion")
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["oqo"]["corpus"] == "expansion"
    assert "corpus=expansion" in body["oxurl"]
    assert "expansion corpus" in body["oql"]


def test_query_oxurl_translate_include_xpac_still_maps_to_all(client):
    res = client.get("/query/oxurl/works?include_xpac=true")
    assert res.status_code == 200, res.get_json()
    body = res.get_json()
    assert body["oqo"]["corpus"] == "all"
    # The canonical URL spelling of the legacy flag is now corpus=all.
    assert "corpus=all" in body["oxurl"]
    assert "include_xpac" not in body["oxurl"]
