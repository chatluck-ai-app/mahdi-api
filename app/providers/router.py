from typing import AsyncIterator

from .. import config
from .anthropic import AnthropicProvider
from .gemini import GeminiProvider
from .mock import MockProvider
from .openai import OpenAIProvider

_PROVIDERS = {
    "gemini": GeminiProvider,
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "mock": MockProvider,
}


def get_chain():
    chain = []
    for name in config.PROVIDER_PRIORITY:
        cls = _PROVIDERS.get(name)
        if cls is None:
            continue
        provider = cls()
        if provider.available():
            chain.append(provider)
    return chain


def available_providers() -> list[str]:
    return [p.name for p in get_chain()]


async def complete(messages: list[dict], system: str) -> tuple[str, str]:
    """Return (text, provider_name), falling back through the chain."""
    last_err: Exception | None = None
    for provider in get_chain():
        try:
            text = await provider.complete(messages, system)
            return text, provider.name
        except Exception as e:  # noqa: BLE001 - try the next provider
            last_err = e
    raise RuntimeError(f"all providers failed: {last_err}")


async def stream(messages: list[dict], system: str) -> AsyncIterator[dict]:
    """Yield {"text", "provider"} dicts, falling back before the first chunk."""
    last_err: Exception | None = None
    for provider in get_chain():
        try:
            started = False
            async for chunk in provider.stream(messages, system):
                started = True
                yield {"text": chunk, "provider": provider.name}
            return
        except Exception as e:  # noqa: BLE001
            last_err = e
            if started:
                yield {"text": "", "provider": provider.name, "error": str(e)}
                return
    raise RuntimeError(f"all providers failed: {last_err}")
