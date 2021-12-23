def test_index(client):
    res = client.get("/")
    assert res.status_code == 200
