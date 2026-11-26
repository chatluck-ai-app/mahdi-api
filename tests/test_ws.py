def _register(client):
    r = client.post("/v1/devices/register", headers={"CF-Connecting-IP": "203.0.113.92", "X-Forwarded-For": "203.0.113.92, 172.68.1.1, 10.0.0.1"})
    return r.json()["device_token"]


def test_ws_streams_and_completes(client):
    token = _register(client)
    with client.websocket_connect(f"/v1/chat/ws?token={token}") as ws:
        ws.send_json({"message": "اهلا بالعالم"})
        chunks, done = [], None
        while True:
            msg = ws.receive_json()
            if msg["type"] == "chunk":
                chunks.append(msg["text"])
            elif msg["type"] == "done":
                done = msg
                break
            elif msg["type"] == "error":
                raise AssertionError(msg["detail"])
        text = "".join(chunks)
        assert "اهلا بالعالم" in text
        assert done["provider"] == "mock"
        assert done["conversation_id"] > 0


def test_ws_followup_keeps_conversation(client):
    token = _register(client)
    with client.websocket_connect(f"/v1/chat/ws?token={token}") as ws:
        ws.send_json({"message": "رسالة"})
        cid = None
        while True:
            msg = ws.receive_json()
            if msg["type"] == "done":
                cid = msg["conversation_id"]
                break
        ws.send_json({"message": "تكملة", "conversation_id": cid})
        while True:
            msg = ws.receive_json()
            if msg["type"] == "done":
                assert msg["conversation_id"] == cid
                break


def test_ws_rejects_bad_token(client):
    with client.websocket_connect("/v1/chat/ws?token=nope") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "error"
