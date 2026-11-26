def test_translate_single_arabic_msa(client, auth):
    r = client.post(
        "/v1/translate",
        json={"text": "hello world", "target": "ar", "style": "msa"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "hello world" in data["translation"]
    assert data["provider"] == "mock"
    assert data["target"] == "ar"


def test_translate_single_egyptian_and_en(client, auth):
    for target, style in (("ar", "egyptian"), ("en", "msa")):
        r = client.post(
            "/v1/translate",
            json={"text": "test", "target": target, "style": style},
            headers=auth,
        )
        assert r.status_code == 200, (target, style)


def test_translate_empty_422(client, auth):
    assert client.post("/v1/translate", json={"text": " "}, headers=auth).status_code == 422
    assert client.post("/v1/translate", json={"texts": []}, headers=auth).status_code == 422
    assert client.post("/v1/translate", json={}, headers=auth).status_code == 422


def test_translate_batch_returns_same_count(client, auth):
    # Mock replies with one line; count mismatches -> per-line fallback, still same count.
    r = client.post(
        "/v1/translate",
        json={"texts": ["one", "two", "three"], "target": "ar", "style": "msa"},
        headers=auth,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert len(data["translations"]) == 3
    assert all(isinstance(t, str) and t for t in data["translations"])


def test_translate_unsupported_target_422(client, auth):
    r = client.post(
        "/v1/translate", json={"text": "x", "target": "fr"}, headers=auth
    )
    assert r.status_code == 422
