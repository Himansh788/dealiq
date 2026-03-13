"""
Anthropic SDK compatibility shim.
Provides an AsyncGroq-compatible interface backed by Anthropic's API.
Usage: from services.ai_client import AsyncAnthropicCompat as AsyncGroq
"""
import os
from anthropic import AsyncAnthropic

MODEL_COMPLEX = "claude-sonnet-4-6"
MODEL_FAST = "claude-haiku-4-5-20251001"

# Map old Groq model names to Anthropic equivalents
_MODEL_MAP = {
    "llama-3.3-70b-versatile": MODEL_COMPLEX,
    "llama-3.1-8b-instant": MODEL_FAST,
}


class _Message:
    def __init__(self, content: str):
        self.content = content


class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)


class _Response:
    def __init__(self, content: str):
        self.choices = [_Choice(content)]


class _Completions:
    def __init__(self, client: AsyncAnthropic):
        self._client = client

    async def create(self, model: str, messages: list, max_tokens: int = 1024,
                     temperature: float = 0.3, response_format=None, **kwargs):
        # Remap Groq model names if needed
        model = _MODEL_MAP.get(model, model)

        # Extract system message from messages list
        system = None
        user_messages = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                user_messages.append({"role": msg["role"], "content": msg["content"]})

        create_kwargs = {
            "model": model,
            "max_tokens": max_tokens,
            "messages": user_messages,
        }
        if system:
            create_kwargs["system"] = system
        if temperature is not None:
            create_kwargs["temperature"] = temperature

        resp = await self._client.messages.create(**create_kwargs)
        return _Response(resp.content[0].text)


class _Chat:
    def __init__(self, client: AsyncAnthropic):
        self.completions = _Completions(client)


class AsyncAnthropicCompat:
    """Drop-in replacement for AsyncGroq using Anthropic's API."""

    def __init__(self, api_key: str = None):
        self._client = AsyncAnthropic(
            api_key=api_key or os.getenv("ANTHROPIC_API_KEY"),
            timeout=60.0,  # 60s max per call — Sonnet needs more time for quality responses
        )
        self.chat = _Chat(self._client)
