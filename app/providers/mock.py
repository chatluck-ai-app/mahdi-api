class MockProvider:
    """Deterministic provider for tests and local dev without keys."""

    name = "mock"

    def available(self) -> bool:
        return True

    async def complete(self, messages: list[dict], system: str) -> str:
        return f"رد تجريبي على: {messages[-1]['content']}"

    async def stream(self, messages: list[dict], system: str):
        text = await self.complete(messages, system)
        for word in text.split(" "):
            yield word + " "
