"""Provider failures must never expose the API key or provider URLs to clients."""
import asyncio

import httpx
import pytest

from app import config
from app.providers import router

FAKE_KEY = "AQ.FAKEKEYFAKEKEYFAKEKEYFAKEKEY1234"


def _patch(monkeypatch, status):
    seen = []

    class T(httpx.AsyncBaseTransport):
        async def handle_async_request(self, req):
            seen.append(str(req.url))
            return httpx.Response(status, json={}, request=req)

    orig = httpx.AsyncClient

    class C(orig):
        def __init__(self, *a, **k):
            k.pop("transport", None)
            super().__init__(*a, transport=T(), **k)

    monkeypatch.setattr(httpx, "AsyncClient", C)
    monkeypatch.setattr(config, "GEMINI_API_KEY", FAKE_KEY)
    monkeypatch.setattr(config, "PROVIDER_PRIORITY", ["gemini"])
    return seen


@pytest.mark.parametrize("status", [429, 500, 403])
def test_error_text_has_no_key_or_url(monkeypatch, status):
    seen = _patch(monkeypatch, status)
    with pytest.raises(RuntimeError) as ei:
        asyncio.run(router.complete([{"role": "user", "content": "x"}], "s"))
    msg = str(ei.value)
    assert FAKE_KEY not in msg
    assert "googleapis" not in msg and "key=" not in msg and "http://" not in msg and "https://" not in msg
    assert all("key=" not in u for u in seen)  # key is never placed in the URL


def test_stream_error_has_no_key_or_url(monkeypatch):
    _patch(monkeypatch, 429)

    async def run():
        out = []
        try:
            async for item in router.stream([{"role": "user", "content": "x"}], "s"):
                out.append(item)
        except RuntimeError as e:
            out.append({"error": str(e)})
        return out

    text = str(asyncio.run(run()))
    assert FAKE_KEY not in text and "googleapis" not in text and "key=" not in text


def test_safe_error_redacts():
    s = router.safe_error(
        "https://x/y?key=AIzaSyABCDEFGHIJKLMNOPQRSTUV&z=1 AQ.Ab8RN6Kzz3zNEeLQZBjKk22l sk-abcdefghijklmnopqrstuvwx"
    )
    assert "AIza" not in s and "AQ.Ab8" not in s and "sk-abc" not in s and "https://" not in s
