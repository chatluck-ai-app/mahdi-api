def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["service"] == "mahdi-api"


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["db"] == "up"
    assert "mock" in data["providers"]
    assert data["code_run"]["timeout_seconds"] > 0
    assert isinstance(data["code_run"]["network_isolated"], bool)
