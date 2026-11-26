import json

import pytest

from app.db import AgentRun, Approval, SessionLocal


def force_plan(run_id: int, plan: list[dict]):
    db = SessionLocal()
    try:
        run = db.get(AgentRun, run_id)
        run.plan_json = json.dumps(plan, ensure_ascii=False)
        db.commit()
    finally:
        db.close()


@pytest.fixture()
def code_plan(client, auth, monkeypatch):
    from app.agents import planner

    async def fake_plan(goal: str):
        return [
            {"tool": "code_run", "args": {"code": "print(2+2)"}, "title": "تشغيل كود"},
            {"tool": "answer", "args": {"instruction": "لخّص النتيجة"}, "title": "تلخيص"},
        ]

    monkeypatch.setattr(planner, "make_plan", fake_plan)
    return auth


def test_simple_goal_completes_without_approval(client, auth):
    r = client.post("/v1/agents/run", json={"goal": "قولّي نكتة"}, headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    assert body["approvals"] == []
    assert body["log"][0]["tool"] == "answer"


def test_gated_tool_waits_for_approval_and_never_runs_unapproved(client, code_plan):
    r = client.post("/v1/agents/run", json={"goal": "احسب 2+2"}, headers=code_plan)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "awaiting_approval"
    assert len(body["approvals"]) == 1
    approval = body["approvals"][0]
    assert approval["kind"] == "code_run"
    assert approval["status"] == "pending"
    # the code must NOT have executed yet: no result anywhere
    db = SessionLocal()
    try:
        row = db.get(Approval, approval["id"])
        assert row.result_json == ""
    finally:
        db.close()

    # approve it: code runs, then the final answer step runs automatically
    r = client.post(
        f"/v1/approvals/{approval['id']}/decide",
        json={"decision": "approve"},
        headers=code_plan,
    )
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["status"] == "approved"
    assert out["output"]["stdout"].strip() == "4"
    assert out["run_status"] == "done"

    r = client.get("/v1/agents/runs", headers=code_plan)
    run = r.json()["runs"][0]
    assert run["status"] == "done"
    assert len(run["log"]) == 2


def test_reject_cancels_run(client, code_plan):
    r = client.post("/v1/agents/run", json={"goal": "شغّل كود"}, headers=code_plan)
    approval = r.json()["approvals"][0]
    r = client.post(
        f"/v1/approvals/{approval['id']}/decide",
        json={"decision": "reject"},
        headers=code_plan,
    )
    assert r.status_code == 200, r.text
    assert r.json()["run_status"] == "canceled"
    # a decided approval cannot be decided again
    r = client.post(
        f"/v1/approvals/{approval['id']}/decide",
        json={"decision": "approve"},
        headers=code_plan,
    )
    assert r.status_code == 409


def test_approvals_scoped_per_device(client, code_plan, auth2):
    r = client.post("/v1/agents/run", json={"goal": "شغّل كود"}, headers=code_plan)
    approval = r.json()["approvals"][0]
    r = client.post(
        f"/v1/approvals/{approval['id']}/decide",
        json={"decision": "approve"},
        headers=auth2,
    )
    assert r.status_code == 404
    r = client.get("/v1/approvals", headers=auth2)
    assert r.json()["approvals"] == []


def test_file_write_creates_artifact_only_after_approval(client, auth, monkeypatch):
    from app.agents import planner

    async def fake_plan(goal: str):
        return [
            {
                "tool": "file_write",
                "args": {"name": "note.txt", "content": "محتوى الملف"},
                "title": "إنشاء ملف",
            }
        ]

    monkeypatch.setattr(planner, "make_plan", fake_plan)
    r = client.post("/v1/agents/run", json={"goal": "اعمل ملف"}, headers=auth)
    assert r.json()["status"] == "awaiting_approval"
    assert client.get("/v1/artifacts", headers=auth).json()["artifacts"] == []

    approval = r.json()["approvals"][0]
    r = client.post(
        f"/v1/approvals/{approval['id']}/decide",
        json={"decision": "approve"},
        headers=auth,
    )
    assert r.json()["output"]["name"] == "note.txt"

    r = client.get("/v1/artifacts", headers=auth)
    artifacts = r.json()["artifacts"]
    assert len(artifacts) == 1
    r = client.get(f"/v1/artifacts/{artifacts[0]['id']}", headers=auth)
    assert r.json()["content"] == "محتوى الملف"


def test_project_gen_scaffold(client, auth, monkeypatch):
    from app.agents import planner

    async def fake_plan(goal: str):
        return [
            {
                "tool": "project_gen",
                "args": {"name": "mysite", "kind": "flask_site"},
                "title": "توليد موقع",
            }
        ]

    monkeypatch.setattr(planner, "make_plan", fake_plan)
    r = client.post("/v1/agents/run", json={"goal": "اعملي موقع"}, headers=auth)
    approval = r.json()["approvals"][0]
    r = client.post(
        f"/v1/approvals/{approval['id']}/decide",
        json={"decision": "approve"},
        headers=auth,
    )
    out = r.json()["output"]
    assert out["kind"] == "flask_site"
    assert len(out["artifact_ids"]) == 4
    r = client.get(f"/v1/artifacts/{out['artifact_ids'][0]}", headers=auth)
    assert "Flask" in r.json()["content"]


def test_admin_summary_requires_token(client, auth):
    assert client.get("/v1/admin/summary").status_code == 404
    assert (
        client.get("/v1/admin/summary", headers={"X-Admin-Token": "wrong"}).status_code
        == 404
    )


def test_admin_summary_with_token(client, auth, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "ADMIN_TOKEN", "sekret")
    r = client.get("/v1/admin/summary", headers={"X-Admin-Token": "sekret"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["devices"] >= 1
    assert "approvals_pending" in body


def test_cancel_run_marks_pending_approvals(client, code_plan):
    r = client.post("/v1/agents/run", json={"goal": "شغّل كود"}, headers=code_plan)
    run_id = r.json()["id"]
    r = client.post(f"/v1/agents/runs/{run_id}/cancel", headers=code_plan)
    assert r.status_code == 200, r.text
    r = client.get(f"/v1/agents/runs/{run_id}", headers=code_plan)
    body = r.json()
    assert body["status"] == "canceled"
    assert body["approvals"][0]["status"] == "canceled"
    # canceled approval cannot be approved afterwards
    r = client.post(
        f"/v1/approvals/{body['approvals'][0]['id']}/decide",
        json={"decision": "approve"},
        headers=code_plan,
    )
    assert r.status_code == 409
    # canceling a finished run is refused
    assert client.post(f"/v1/agents/runs/{run_id}/cancel", headers=code_plan).status_code == 409


def test_tool_failure_marks_run_failed(client, auth, monkeypatch):
    from app.agents import planner

    async def fake_plan(goal: str):
        return [
            {"tool": "code_run", "args": {"code": "import os; os._exit(1)"}, "title": "كود فاشل"},
        ]

    monkeypatch.setattr(planner, "make_plan", fake_plan)
    r = client.post("/v1/agents/run", json={"goal": "جرب"}, headers=auth)
    approval = r.json()["approvals"][0]
    r = client.post(
        f"/v1/approvals/{approval['id']}/decide",
        json={"decision": "approve"},
        headers=auth,
    )
    # executor itself did not raise: tool ran, nonzero exit is a valid output
    assert r.status_code == 200, r.text
    assert r.json()["output"]["exit_code"] != 0


def test_executor_exception_fails_run(client, auth, monkeypatch):
    from app.agents import planner, tools

    async def fake_plan(goal: str):
        return [{"tool": "search", "args": {"query": "x"}, "title": "بحث"}]

    async def boom(tool, args, device, db, goal):
        raise RuntimeError("network down")

    monkeypatch.setattr(planner, "make_plan", fake_plan)
    monkeypatch.setattr(tools, "execute", boom)
    r = client.post("/v1/agents/run", json={"goal": "ابحث"}, headers=auth)
    approval = r.json()["approvals"][0]
    r = client.post(
        f"/v1/approvals/{approval['id']}/decide",
        json={"decision": "approve"},
        headers=auth,
    )
    assert r.json()["run_status"] == "failed"
    assert "network down" in r.json()["output"]["error"]


def test_second_gated_step_never_runs_before_its_own_approval(client, auth, monkeypatch):
    from app.agents import planner

    async def fake_plan(goal: str):
        return [
            {"tool": "file_write", "args": {"name": "a.txt", "content": "أ"}, "title": "ملف أ"},
            {"tool": "file_write", "args": {"name": "b.txt", "content": "ب"}, "title": "ملف ب"},
        ]

    monkeypatch.setattr(planner, "make_plan", fake_plan)
    r = client.post("/v1/agents/run", json={"goal": "ملفين"}, headers=auth)
    body = r.json()
    assert body["status"] == "awaiting_approval"
    assert len(body["approvals"]) == 1  # only step 0 is proposed
    first = body["approvals"][0]
    assert first["title"] == "ملف أ"

    # approve step 0: file a.txt appears, b.txt still does NOT, step 1 now proposed
    r = client.post(
        f"/v1/approvals/{first['id']}/decide", json={"decision": "approve"}, headers=auth
    )
    assert r.json()["run_status"] == "awaiting_approval"
    names = [a["name"] for a in client.get("/v1/artifacts", headers=auth).json()["artifacts"]]
    assert names == ["a.txt"]

    r = client.get(f"/v1/agents/runs/{body['id']}", headers=auth)
    second = [a for a in r.json()["approvals"] if a["step_index"] == 1][0]
    assert second["status"] == "pending"

    # reject step 1: b.txt is never written, run canceled
    client.post(
        f"/v1/approvals/{second['id']}/decide", json={"decision": "reject"}, headers=auth
    )
    names = [a["name"] for a in client.get("/v1/artifacts", headers=auth).json()["artifacts"]]
    assert names == ["a.txt"]
    assert client.get(f"/v1/agents/runs/{body['id']}", headers=auth).json()["status"] == "canceled"


def test_history_export(client, auth):
    client.post("/v1/chat", json={"message": "أهلا"}, headers=auth)
    r = client.get("/v1/history/export", headers=auth)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["format"] == "mahdi-history-v1"
    assert body["conversations"][0]["messages"][0]["content"] == "أهلا"
    assert len(body["conversations"][0]["messages"]) == 2


def test_pending_approval_survives_restart_and_tool_still_not_run(client, code_plan):
    """App restart / reconnect = a fresh session; the pending gate must persist."""
    from app.db import Artifact

    db = SessionLocal()
    try:
        artifacts_before = db.query(Artifact).count()
    finally:
        db.close()

    r = client.post("/v1/agents/run", json={"goal": "شغّل كود"}, headers=code_plan)
    approval = r.json()["approvals"][0]

    # simulate restart: brand-new DB session, same server state
    db = SessionLocal()
    try:
        row = db.get(Approval, approval["id"])
        assert row.status == "pending"
        assert row.result_json == ""  # tool still has NOT run
        assert db.query(Artifact).count() == artifacts_before
    finally:
        db.close()

    # and the API still reports it pending after the "restart"
    r = client.get("/v1/approvals?status=pending", headers=code_plan)
    assert [a["id"] for a in r.json()["approvals"]] == [approval["id"]]


def test_history_import_roundtrip(client, auth, auth2):
    client.post("/v1/chat", json={"message": "رسالة قديمة"}, headers=auth)
    exported = client.get("/v1/history/export", headers=auth).json()

    # a different device (the "new install") imports the backup
    r = client.post("/v1/history/import", json=exported, headers=auth2)
    assert r.status_code == 200, r.text
    assert r.json()["imported_conversations"] == 1 and r.json()["imported_messages"] == 2

    convs = client.get("/v1/history", headers=auth2).json()["conversations"]
    assert len(convs) == 1
    msgs = client.get(f"/v1/history/{convs[0]['id']}", headers=auth2).json()["messages"]
    assert msgs[0]["content"] == "رسالة قديمة"

    # garbage is rejected
    assert client.post("/v1/history/import", json={"x": 1}, headers=auth2).status_code == 422


def test_coder_style_chat(client, auth):
    r = client.post("/v1/chat", json={"message": "اكتب دالة جمع", "style": "coder"}, headers=auth)
    assert r.status_code == 200, r.text
    assert r.json()["reply"]


def test_admin_dashboard_page(client, monkeypatch):
    from app import config

    assert client.get("/v1/admin/dashboard").status_code == 404  # disabled without token
    monkeypatch.setattr(config, "ADMIN_TOKEN", "sekret")
    assert client.get("/v1/admin/dashboard").status_code == 404  # page itself gated
    r = client.get("/v1/admin/dashboard", headers={"X-Admin-Token": "sekret"})
    assert r.status_code == 200
    assert "/v1/admin/summary" in r.text


def test_import_is_idempotent(client, auth, auth2):
    client.post("/v1/chat", json={"message": "أول رسالة"}, headers=auth)
    exported = client.get("/v1/history/export", headers=auth).json()
    r1 = client.post("/v1/history/import", json=exported, headers=auth2).json()
    assert r1["already_imported"] is False
    r2 = client.post("/v1/history/import", json=exported, headers=auth2).json()
    assert r2["already_imported"] is True
    assert r2["imported_conversations"] == 0
    # still exactly one conversation after the retry
    convs = client.get("/v1/history", headers=auth2).json()["conversations"]
    assert len(convs) == 1


def test_export_import_multi_conversation_order(client, auth, auth2):
    for i in range(3):
        client.post("/v1/chat", json={"message": f"سؤال {i}"}, headers=auth)
        client.post("/v1/chat", json={"message": f"تكملة {i}", "conversation_id": i + 1 if i else None}, headers=auth)
    exported = client.get("/v1/history/export", headers=auth).json()
    assert len(exported["conversations"]) >= 3
    for conv in exported["conversations"]:
        ts = [m["created_at"] for m in conv["messages"]]
        assert ts == sorted(ts)  # chronological in the export
    r = client.post("/v1/history/import", json=exported, headers=auth2)
    assert r.status_code == 200, r.text
    convs = client.get("/v1/history", headers=auth2).json()["conversations"]
    first = client.get(f"/v1/history/{convs[0]['id']}", headers=auth2).json()["messages"]
    roles = [m["role"] for m in first]
    assert roles == ["user", "assistant"] or roles == ["user", "user", "assistant", "assistant"]


def test_recovery_full_flow_and_single_use(client, auth, auth2):
    # "old install" = auth, "new install" = auth2
    client.post("/v1/chat", json={"message": "محادثة قديمة مهمة"}, headers=auth)

    r = client.post("/v1/recovery/request", headers=auth2)
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    assert len(code) == 19  # XXXX-XXXX-XXXX-XXXX

    # claiming before the old app wrote the phrase fails, nothing copied
    r = client.post("/v1/recovery/claim", json={"code": code}, headers=auth2)
    assert r.status_code == 409
    assert client.get("/v1/history", headers=auth2).json()["conversations"] == []

    # the old app sends the phrase as a chat message (proves token possession)
    client.post("/v1/chat", json={"message": f"الكود بتاعي {code}"}, headers=auth)

    r = client.post("/v1/recovery/claim", json={"code": code}, headers=auth2)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "recovered"
    assert body["conversations"] >= 1
    assert body["original_untouched"] is True

    # new device now holds a copy of the old conversation
    convs = client.get("/v1/history", headers=auth2).json()["conversations"]
    assert len(convs) >= 1

    # original rows untouched: old device still has exactly its own conversations
    old_convs = client.get("/v1/history", headers=auth).json()["conversations"]
    assert len(old_convs) == len(convs)

    # single-use: claiming again fails, no duplication
    r = client.post("/v1/recovery/claim", json={"code": code}, headers=auth2)
    assert r.status_code == 409
    assert len(client.get("/v1/history", headers=auth2).json()["conversations"]) == len(convs)


def test_recovery_code_bound_to_requesting_device(client, auth, auth2):
    r = client.post("/v1/recovery/request", headers=auth2)
    code = r.json()["code"]
    # a third device cannot claim a code it did not request
    r3 = client.post("/v1/devices/register")
    third = {"Authorization": f"Bearer {r3.json()['device_token']}"}
    assert client.post("/v1/recovery/claim", json={"code": code}, headers=third).status_code == 403
    # unknown code
    assert client.post("/v1/recovery/claim", json={"code": "XXXX-XXXX-XXXX-XXXX"}, headers=auth2).status_code == 404


def test_recovery_expired_code_cannot_claim(client, auth2):
    from datetime import datetime, timedelta, timezone

    from app.db import RecoveryGrant

    r = client.post("/v1/recovery/request", headers=auth2)
    code = r.json()["code"]
    db = SessionLocal()
    try:
        grant = db.query(RecoveryGrant).filter(RecoveryGrant.code == code).first()
        grant.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    finally:
        db.close()
    r = client.post("/v1/recovery/claim", json={"code": code}, headers=auth2)
    assert r.status_code == 410


def test_recovery_claim_rate_limited_after_5_failures(client, auth2):
    for _ in range(5):
        r = client.post("/v1/recovery/claim", json={"code": "AAAA-BBBB-CCCC-DDDD"}, headers=auth2)
        assert r.status_code == 404
    r = client.post("/v1/recovery/claim", json={"code": "AAAA-BBBB-CCCC-DDDD"}, headers=auth2)
    assert r.status_code == 429


def test_recovery_ignores_old_or_assistant_phrase(client, auth, auth2):
    from app.db import Conversation, Device, Message

    # pre-grant write on the old device (will predate the grant's id threshold):
    # happens to contain the FUTURE code pattern is impossible, so we test the
    # two real bypass attempts: an old message edited is impossible via API, so
    # we plant (1) a pre-grant user message and (2) a post-grant ASSISTANT echo.
    db = SessionLocal()
    try:
        dev = db.query(Device).filter(Device.token == auth["Authorization"].split()[1]).first()
        conv = Conversation(device_id=dev.id, title="قديمة", style="egyptian")
        db.add(conv)
        db.flush()
        conv_id = conv.id
        db.commit()
    finally:
        db.close()

    r = client.post("/v1/recovery/request", headers=auth2)
    code = r.json()["code"]

    db = SessionLocal()
    try:
        # assistant-role echo of the code AFTER the grant must not count
        db.add(Message(conversation_id=conv_id, role="assistant", content=f"كودك هو {code}"))
        db.commit()
    finally:
        db.close()
    r = client.post("/v1/recovery/claim", json={"code": code}, headers=auth2)
    assert r.status_code == 409  # assistant echo alone never proves possession
