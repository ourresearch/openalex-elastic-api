import pytest

from app import create_app


@pytest.fixture
def client():
    app = create_app("tests.settings")

    yield app.test_client()
