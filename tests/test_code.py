def test_run_prints(client, auth):
    r = client.post("/v1/code/run", json={"code": "print(2 + 2)"}, headers=auth)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["stdout"].strip() == "4"
    assert data["exit_code"] == 0
    assert data["timed_out"] is False
    assert data["duration_ms"] >= 0


def test_run_syntax_error(client, auth):
    r = client.post("/v1/code/run", json={"code": "def broken(:"}, headers=auth)
    data = r.json()
    assert data["exit_code"] != 0
    assert "SyntaxError" in data["stderr"]


def test_run_infinite_loop_times_out(client, auth):
    r = client.post("/v1/code/run", json={"code": "while True: pass"}, headers=auth)
    data = r.json()
    assert data["timed_out"] is True
    assert data["exit_code"] == -1


def test_run_memory_bomb_fails_not_crashes(client, auth):
    code = "x = ' ' * (10**9)\nprint(len(x))"
    r = client.post("/v1/code/run", json={"code": code}, headers=auth)
    data = r.json()
    assert r.status_code == 200
    assert data["exit_code"] != 0 or data["timed_out"]


def test_run_output_truncated(client, auth):
    code = "print('A' * (200 * 1024))"
    r = client.post("/v1/code/run", json={"code": code}, headers=auth)
    data = r.json()
    assert len(data["stdout"]) <= 64 * 1024 + 64
    assert "truncated" in data["stdout"]


def test_run_network_isolation_consistent(client, auth):
    health = client.get("/v1/health").json()
    r = client.post(
        "/v1/code/run",
        json={"code": "import socket\nsocket.create_connection(('1.1.1.1', 80), timeout=2)"},
        headers=auth,
    )
    data = r.json()
    assert data["network_isolated"] == health["code_run"]["network_isolated"]
    if data["network_isolated"]:
        assert data["exit_code"] != 0
