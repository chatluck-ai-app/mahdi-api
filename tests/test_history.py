def _chat(client, auth, message):
    return client.post("/v1/chat", json={"message": message}, headers=auth).json()


def test_history_lists_conversations(client, auth):
    _chat(client, auth, "محادثة تاريخ واحد")
    _chat(client, auth, "محادثة تاريخ اتنين")
    r = client.get("/v1/history", headers=auth)
    assert r.status_code == 200
    convs = r.json()["conversations"]
    assert len(convs) >= 2
    assert all("last_message" in c and "message_count" in c for c in convs)


def test_history_get_conversation_messages(client, auth):
    cid = _chat(client, auth, "رسالة للسجل")["conversation_id"]
    _chat(client, auth, "لا")  # noise
    r = client.get(f"/v1/history/{cid}", headers=auth)
    assert r.status_code == 200
    data = r.json()
    assert [m["role"] for m in data["messages"]] == ["user", "assistant"]
    assert "رسالة للسجل" in data["messages"][0]["content"]


def test_history_foreign_conversation_404(client, auth, auth2):
    cid = _chat(client, auth, "مش بتاعتك")["conversation_id"]
    assert client.get(f"/v1/history/{cid}", headers=auth2).status_code == 404
    assert client.delete(f"/v1/history/{cid}", headers=auth2).status_code == 404


def test_history_delete(client, auth):
    cid = _chat(client, auth, "هتتمسح")["conversation_id"]
    assert client.delete(f"/v1/history/{cid}", headers=auth).status_code == 200
    assert client.get(f"/v1/history/{cid}", headers=auth).status_code == 404
