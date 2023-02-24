class TestSampleBasic:
    def test_sample_low_number(self, client):
        res = client.get("/works?sample=1")
        json_data = res.get_json()
        results = json_data["results"]
        assert len(results) == 1

    def test_sample_records_different(self, client):
        res1 = client.get("/works?sample=1")
        json_data1 = res1.get_json()
        res2 = client.get("/works?sample=1")
        json_data2 = res2.get_json()
        assert json_data1["results"][0]["id"] != json_data2["results"][0]["id"]

    def test_sample_seed(self, client):
        res1 = client.get("/works?sample=1&sample_seed=1")
        json_data1 = res1.get_json()
        res2 = client.get("/works?sample=1&sample_seed=1")
        json_data2 = res2.get_json()
        assert json_data1["results"][0]["id"] == json_data2["results"][0]["id"]

    def test_sample_seed_different(self, client):
        res1 = client.get("/concepts?sample=1&sample_seed=1")
        json_data1 = res1.get_json()
        res2 = client.get("/concepts?sample=1&sample_seed=2")
        json_data2 = res2.get_json()
        assert json_data1["results"][0]["id"] != json_data2["results"][0]["id"]


class TestSamplePaginate:
    def test_sample_paginate(self, client):
        res = client.get("/works?sample=50")
        json_data = res.get_json()
        results = json_data["results"]
        meta = json_data["meta"]
        assert meta["count"] == 50
        assert len(results) == 25
