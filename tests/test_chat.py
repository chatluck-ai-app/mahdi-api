def test_chat_reply(client, auth):
    r = client.post("/v1/chat", json={"message": "اهلا"}, headers=auth)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "اهلا" in data["reply"]
    assert data["provider"] == "mock"
    assert data["conversation_id"] > 0


def test_chat_followup_same_conversation(client, auth):
    r1 = client.post("/v1/chat", json={"message": "الاولى"}, headers=auth)
    cid = r1.json()["conversation_id"]
    r2 = client.post(
        "/v1/chat", json={"message": "التانية", "conversation_id": cid}, headers=auth
    )
    assert r2.status_code == 200
    assert r2.json()["conversation_id"] == cid


def test_chat_styles_accepted(client, auth):
    for style in ("egyptian", "fusha"):
        r = client.post("/v1/chat", json={"message": "اختبار", "style": style}, headers=auth)
        assert r.status_code == 200, style


def test_chat_foreign_conversation_404(client, auth, auth2):
    cid = client.post("/v1/chat", json={"message": "خاص"}, headers=auth).json()["conversation_id"]
    r = client.post(
        "/v1/chat", json={"message": "تطفل", "conversation_id": cid}, headers=auth2
    )
    assert r.status_code == 404


def test_chat_empty_message_422(client, auth):
    assert client.post("/v1/chat", json={"message": "  "}, headers=auth).status_code == 422
