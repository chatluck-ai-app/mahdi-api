import os
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///" + os.path.join(tempfile.mkdtemp(), "test.db")
os.environ["AI_PROVIDER_PRIORITY"] = "mock"

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def auth(client):
    r = client.post("/v1/devices/register")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['device_token']}"}


@pytest.fixture()
def auth2(client):
    r = client.post("/v1/devices/register")
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['device_token']}"}
