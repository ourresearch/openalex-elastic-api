class TestWorksCombinedSearch:
    """Tests for combining multiple search parameters in one request."""

    def test_combined_scoped_searches(self, client):
        """search.title + search.title_and_abstract returns 200."""
        res = client.get(
            "/works?search.title=analysis&search.title_and_abstract=data"
        )
        json_data = res.get_json()
        assert res.status_code == 200
        assert json_data["meta"]["count"] > 0

    def test_combined_bare_and_scoped_search(self, client):
        """Bare search + search.title returns 200."""
        res = client.get("/works?search=analysis&search.title=data")
        json_data = res.get_json()
        assert res.status_code == 200
        assert json_data["meta"]["count"] > 0

    def test_combined_search_narrows_results(self, client):
        """Adding a second search should return fewer results than one alone."""
        res_single = client.get("/works?search.title=analysis")
        res_combined = client.get(
            "/works?search.title=analysis&search.title_and_abstract=data"
        )
        single_count = res_single.get_json()["meta"]["count"]
        combined_count = res_combined.get_json()["meta"]["count"]
        assert combined_count <= single_count

    def test_same_scope_different_type_rejected(self, client):
        """search.title + search.title.exact on same scope is rejected."""
        res = client.get("/works?search.title=analysis&search.title.exact=data")
        json_data = res.get_json()
        assert res.status_code == 400
        assert "Cannot use both stemmed and exact search" in json_data["message"]

    def test_semantic_combined_rejected(self, client):
        """search.semantic + search.title is rejected."""
        res = client.get(
            "/works?search.semantic=machine+learning&search.title=neural"
        )
        json_data = res.get_json()
        assert res.status_code == 400
        assert "search.semantic cannot be combined" in json_data["message"]

    def test_duplicate_param_rejected(self, client):
        """search.title=X&search.title=Y (duplicate param) is rejected."""
        res = client.get("/works?search.title=X&search.title=Y")
        json_data = res.get_json()
        assert res.status_code == 400
        assert "Duplicate search parameter" in json_data["message"]

    def test_combined_search_with_sort(self, client):
        """Combined search with explicit sort works."""
        res = client.get(
            "/works?search.title=analysis&search.title_and_abstract=data"
            "&sort=cited_by_count:desc"
        )
        json_data = res.get_json()
        assert res.status_code == 200
        # Verify descending sort
        counts = [r["cited_by_count"] for r in json_data["results"]]
        assert counts == sorted(counts, reverse=True)

    def test_combined_search_with_pagination(self, client):
        """Combined search with cursor pagination works."""
        res1 = client.get(
            "/works?search.title=analysis&search.title_and_abstract=data"
            "&per_page=5&cursor=*"
        )
        json1 = res1.get_json()
        assert res1.status_code == 200
        assert len(json1["results"]) == 5

        cursor = json1["meta"]["next_cursor"]
        res2 = client.get(
            f"/works?search.title=analysis&search.title_and_abstract=data"
            f"&per_page=5&cursor={cursor}"
        )
        json2 = res2.get_json()
        assert res2.status_code == 200
        # Page 2 should have different results
        ids_1 = {r["id"] for r in json1["results"]}
        ids_2 = {r["id"] for r in json2["results"]}
        assert ids_1.isdisjoint(ids_2)

    def test_combined_search_with_sample(self, client):
        """Combined search with sample mode works."""
        res = client.get(
            "/works?search.title=analysis&search.title_and_abstract=data"
            "&sample=10&seed=42"
        )
        json_data = res.get_json()
        assert res.status_code == 200
        assert len(json_data["results"]) == 10

    def test_combined_search_with_group_by(self, client):
        """Combined search with group_by uses all search params."""
        res = client.get(
            "/works?search.title=analysis&search.title_and_abstract=data"
            "&group_by=type"
        )
        json_data = res.get_json()
        assert res.status_code == 200
        assert len(json_data["group_by"]) > 0
        # Total across groups should be consistent with non-group_by count
        group_total = sum(g["count"] for g in json_data["group_by"])
        res_plain = client.get(
            "/works?search.title=analysis&search.title_and_abstract=data"
        )
        plain_count = res_plain.get_json()["meta"]["count"]
        # group_by counts may differ slightly due to unknown/overlap, but should be close
        assert group_total > 0
        assert abs(group_total - plain_count) / max(plain_count, 1) < 0.1


class TestWorksSingleSearchRegression:
    """Regression tests to ensure single search types still work."""

    def test_bare_search(self, client):
        """Bare search still works."""
        res = client.get("/works?search=analysis")
        json_data = res.get_json()
        assert res.status_code == 200
        assert json_data["meta"]["count"] > 0

    def test_scoped_search_title(self, client):
        """search.title still works."""
        res = client.get("/works?search.title=analysis")
        json_data = res.get_json()
        assert res.status_code == 200
        assert json_data["meta"]["count"] > 0

    def test_exact_search(self, client):
        """search.exact still works."""
        res = client.get("/works?search.exact=analysis")
        json_data = res.get_json()
        assert res.status_code == 200
        assert json_data["meta"]["count"] > 0

    def test_scoped_exact_search(self, client):
        """search.title.exact still works."""
        res = client.get("/works?search.title.exact=analysis")
        json_data = res.get_json()
        assert res.status_code == 200
        assert json_data["meta"]["count"] > 0

    def test_title_and_abstract_search(self, client):
        """search.title_and_abstract still works."""
        res = client.get("/works?search.title_and_abstract=analysis")
        json_data = res.get_json()
        assert res.status_code == 200
        assert json_data["meta"]["count"] > 0
