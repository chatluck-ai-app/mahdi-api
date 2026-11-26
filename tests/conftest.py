import os
import secrets
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
    # unique X-Forwarded-For per fixture: per-IP throttles must not couple tests
    ip = "10.255." + str(secrets.randbelow(255)) + "." + str(secrets.randbelow(255))
    r = client.post("/v1/devices/register", headers={"X-Forwarded-For": ip})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['device_token']}", "X-Forwarded-For": ip}


@pytest.fixture()
def auth2(client):
    ip = "10.254." + str(secrets.randbelow(255)) + "." + str(secrets.randbelow(255))
    r = client.post("/v1/devices/register", headers={"X-Forwarded-For": ip})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['device_token']}", "X-Forwarded-For": ip}
