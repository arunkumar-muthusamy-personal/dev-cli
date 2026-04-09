"""Tests for the OpenAI-compatible LLM client using respx to mock HTTP."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from dev_cli.llm.client import LLMClient, LLMError


@pytest.fixture
def mock_client() -> LLMClient:
    return LLMClient(
        model="gpt-4o",
        base_url="http://localhost:11434/v1",
        api_key="test-key",
    )


async def test_invoke_returns_text(mock_client: LLMClient) -> None:
    mock_response = MagicMock()
    mock_response.choices = [MagicMock(message=MagicMock(content="Hello, world!"))]
    mock_response.usage = MagicMock(prompt_tokens=10, completion_tokens=5)

    with patch.object(
        mock_client._client.chat.completions,
        "create",
        new=AsyncMock(return_value=mock_response),
    ):
        text, usage = await mock_client.invoke(
            system_prompt="You are a helpful assistant.",
            messages=[{"role": "user", "content": "Say hello"}],
        )

    assert text == "Hello, world!"
    assert usage["input_tokens"] == 10
    assert usage["output_tokens"] == 5


async def test_stream_yields_tokens(mock_client: LLMClient) -> None:
    def make_chunk(text):
        chunk = MagicMock()
        chunk.choices = [MagicMock(delta=MagicMock(content=text))]
        return chunk

    async def fake_stream():
        for token in ["Hello", ",", " world", "!"]:
            yield make_chunk(token)

    with patch.object(
        mock_client._client.chat.completions,
        "create",
        new=AsyncMock(return_value=fake_stream()),
    ):
        tokens = []
        async for token in mock_client.stream(
            system_prompt="You are helpful.",
            messages=[{"role": "user", "content": "Say hello"}],
        ):
            tokens.append(token)

    assert "".join(tokens) == "Hello, world!"


async def test_invoke_raises_llm_error_on_api_error(mock_client: LLMClient) -> None:
    from openai import APIStatusError
    import httpx

    error = APIStatusError(
        "Not found",
        response=httpx.Response(404, request=httpx.Request("POST", "http://localhost")),
        body={"error": {"message": "model not found"}},
    )

    with patch.object(
        mock_client._client.chat.completions,
        "create",
        new=AsyncMock(side_effect=error),
    ):
        with pytest.raises(LLMError, match="LLM API error"):
            await mock_client.invoke(
                system_prompt="sys",
                messages=[{"role": "user", "content": "hi"}],
            )
