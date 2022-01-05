def test_index(client):
    res = client.get("/")
    json_data = res.get_json()
    assert json_data["msg"] == "Don't panic"
    assert res.status_code == 200
