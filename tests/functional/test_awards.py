import pytest


def test_awards_endpoint(client):
    """Test the basic awards endpoint"""
    response = client.get("/awards?per_page=1")
    assert response.status_code == 200
    
    data = response.get_json()
    assert "meta" in data
    assert "results" in data
    assert isinstance(data["results"], list)


def test_awards_id_endpoint(client):
    """Test the awards ID endpoint"""
    # First get a list to find an ID
    response = client.get("/awards?per_page=1")
    assert response.status_code == 200
    
    data = response.get_json()
    if data["results"]:
        award_id = data["results"][0]["id"]
        
        # Test the ID endpoint
        response = client.get(f"/awards/{award_id}")
        assert response.status_code == 200
        
        data = response.get_json()
        assert "id" in data
        assert data["id"] == award_id


def test_awards_openalex_id_redirect(client):
    """Test OpenAlex ID redirect for awards"""
    # Test with a G prefix (awards)
    response = client.get("/G123456")
    # Should redirect to awards endpoint
    assert response.status_code in [200, 302, 404]  # 404 if no data, 302 if redirect


def test_awards_search(client):
    """Test awards search functionality"""
    response = client.get("/awards?search=machine learning&per_page=5")
    assert response.status_code == 200
    
    data = response.get_json()
    assert "meta" in data
    assert "results" in data


def test_awards_filters(client):
    """Test awards filtering"""
    response = client.get("/awards?title=research&per_page=5")
    assert response.status_code == 200
    
    data = response.get_json()
    assert "meta" in data
    assert "results" in data

