def test_translate_fusha(client, auth):
    r = client.post(
        "/v1/translate", json={"text": "hello world", "target": "fusha"}, headers=auth
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "hello world" in data["translation"]
    assert data["target"] == "fusha"
    assert data["provider"] == "mock"


def test_translate_egyptian_and_en(client, auth):
    for target in ("egyptian", "en"):
        r = client.post("/v1/translate", json={"text": "test", "target": target}, headers=auth)
        assert r.status_code == 200, target


def test_translate_empty_422(client, auth):
    assert client.post("/v1/translate", json={"text": " "}, headers=auth).status_code == 422
