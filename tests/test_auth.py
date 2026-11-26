def test_register_returns_token(client):
    r = client.post("/v1/devices/register", headers={"CF-Connecting-IP": "203.0.113.91", "X-Forwarded-For": "203.0.113.91, 172.68.1.1, 10.0.0.1"})
    assert r.status_code == 200
    assert len(r.json()["device_token"]) >= 32


def test_chat_requires_auth(client):
    assert client.post("/v1/chat", json={"message": "hi"}).status_code in (401, 403)


def test_chat_rejects_bad_token(client):
    r = client.post(
        "/v1/chat",
        json={"message": "hi"},
        headers={"Authorization": "Bearer nope"},
    )
    assert r.status_code == 401


def test_translate_requires_auth(client):
    assert client.post("/v1/translate", json={"text": "hi"}).status_code in (401, 403)


def test_code_run_requires_auth(client):
    assert client.post("/v1/code/run", json={"code": "print(1)"}).status_code in (401, 403)


def test_history_requires_auth(client):
    assert client.get("/v1/history").status_code in (401, 403)
