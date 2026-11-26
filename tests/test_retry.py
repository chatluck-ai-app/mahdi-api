import asyncio

import pytest

from app.providers import router as provider_router
from app.providers.mock import FlakyProvider


@pytest.fixture(autouse=True)
def reset_flaky():
    FlakyProvider._failures = 0
    yield
    FlakyProvider._failures = 0


def test_complete_retries_once_then_succeeds(monkeypatch):
    monkeypatch.setattr(provider_router.config, "PROVIDER_PRIORITY", ["flaky"])
    text, provider = asyncio.run(
        provider_router.complete([{"role": "user", "content": "اختبار"}], "system")
    )
    assert text == "رد بعد إعادة المحاولة"
    assert provider == "flaky"


def test_stream_falls_back_to_next_provider_after_pre_chunk_failure(monkeypatch):
    monkeypatch.setattr(provider_router.config, "PROVIDER_PRIORITY", ["flaky", "mock"])

    async def collect():
        return [item async for item in provider_router.stream(
            [{"role": "user", "content": "اختبار"}], "system")]

    items = asyncio.run(collect())
    assert items, "expected chunks from the fallback provider"
    assert all(item["provider"] == "mock" for item in items)
    assert "رد تجريبي" in "".join(item["text"] for item in items)
