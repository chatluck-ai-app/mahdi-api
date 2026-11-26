"""client_ip derivation unit tests + the TEST-ONLY /v1/diag endpoint.

TRUSTED_EDGE_SECRET is set to "test-edge-secret" in conftest, and the shared
TestClient sends X-Mahdi-Edge: test-edge-secret on every request by default,
emulating Cloudflare's Transform Rule on the real chain.
"""

from types import SimpleNamespace

from app.ratelimit import client_ip

SECRET = "test-edge-secret"


def req(headers, peer="192.0.2.1"):
    lower = {k.lower(): v for k, v in headers.items()}
    return SimpleNamespace(
        headers=SimpleNamespace(get=lambda k, d="": lower.get(k.lower(), d)),
        client=SimpleNamespace(host=peer),
    )


def test_cf_header_wins_over_xff_junk():
    r = req({
        "X-Mahdi-Edge": SECRET,
        "CF-Connecting-IP": "203.0.113.1",
        "X-Forwarded-For": "6.6.6.6, 7.7.7.7",
    })
    assert client_ip(r) == "203.0.113.1"


def test_second_from_right_when_no_cf():
    r = req({"X-Mahdi-Edge": SECRET, "X-Forwarded-For": "1.1.1.1, 203.0.113.2, 198.51.100.9"})
    assert client_ip(r) == "203.0.113.2"


def test_forged_cf_header_without_edge_secret_is_ignored():
    # direct connection bypassing Cloudflare: client can set any header except
    # the secret; nothing client-supplied may be trusted -> peer bucket
    r = req({"X-Mahdi-Edge": "forged", "CF-Connecting-IP": "203.0.113.1",
             "X-Forwarded-For": "203.0.113.1, 198.51.100.9"})
    assert client_ip(r) == "192.0.2.1"


def test_no_secret_no_headers_uses_peer():
    assert client_ip(req({"X-Mahdi-Edge": SECRET})) == "192.0.2.1"


def test_diag_endpoint_flag_and_token(client, monkeypatch):
    # off by default: 404 even with the admin token
    monkeypatch.setattr("app.routers.diag.config.ADMIN_TOKEN", "admintest")
    monkeypatch.delenv("MAHDI_DIAG", raising=False)
    r = client.get("/v1/diag/client-ip", headers={"X-Admin-Token": "admintest"})
    assert r.status_code == 404
    # enabled but no/wrong token: 404
    monkeypatch.setenv("MAHDI_DIAG", "1")
    assert client.get("/v1/diag/client-ip").status_code == 404
    assert client.get("/v1/diag/client-ip", headers={"X-Admin-Token": "nope"}).status_code == 404
    # enabled + token: 200 with the chosen IP and raw headers
    r = client.get(
        "/v1/diag/client-ip",
        headers={
            "X-Admin-Token": "admintest",
            "CF-Connecting-IP": "203.0.113.99",
            "X-Forwarded-For": "1.2.3.4, 203.0.113.99, 198.51.100.1",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["chosen_ip"] == "203.0.113.99"
    assert body["cf_connecting_ip"] == "203.0.113.99"
    assert "1.2.3.4" in body["x_forwarded_for"]
    assert body["peer"]
    # forged edge secret (direct-connection emulation): CF header NOT trusted
    r = client.get(
        "/v1/diag/client-ip",
        headers={"X-Admin-Token": "admintest", "X-Mahdi-Edge": "forged",
                 "CF-Connecting-IP": "203.0.113.77"},
    )
    assert r.status_code == 200
    assert r.json()["chosen_ip"] == r.json()["peer"]
    assert r.json()["chosen_ip"] != "203.0.113.77"
