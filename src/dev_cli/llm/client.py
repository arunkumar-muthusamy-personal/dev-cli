"""OpenAI-compatible LLM client.

Works with any API that speaks the OpenAI Chat Completions protocol:
  - OpenAI (gpt-4o, gpt-4-turbo, ...)
  - Anthropic via openai-compat layer (claude-3-5-sonnet, ...)
  - Azure OpenAI
  - Ollama (llama3, mistral, ...) — point LLM_BASE_URL at http://localhost:11434/v1
  - LM Studio, vLLM, Together AI, Groq, etc.

Configuration (env vars or .env):
  DEV_CLI_LLM_BASE_URL   = https://api.openai.com/v1
  DEV_CLI_LLM_API_KEY    = sk-...
  DEV_CLI_LLM_MODEL      = gpt-4o
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from openai import AsyncOpenAI, APIError, APIConnectionError, APIStatusError

from dev_cli.config import get_settings


class LLMError(Exception):
    pass


class LLMClient:
    """Async OpenAI-compatible LLM client."""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        # Only load (and validate) settings when a value isn't supplied directly.
        # This allows tests and callers that pass all three args to skip validation.
        if model is None or base_url is None or api_key is None:
            settings = get_settings()
            model    = model    or settings.llm_model
            base_url = base_url or settings.llm_base_url
            api_key  = api_key  or settings.llm_api_key

        self._model = model
        self._client = AsyncOpenAI(
            api_key=api_key or "ollama",  # Ollama ignores the key
            base_url=base_url,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def stream(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> AsyncGenerator[str, None]:
        """Yield response text tokens as they arrive from the LLM."""
        settings = get_settings()
        full_messages = [{"role": "system", "content": system_prompt}, *messages]

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=full_messages,  # type: ignore[arg-type]
                max_tokens=max_tokens or settings.llm_max_tokens,
                temperature=temperature or settings.llm_temperature,
                stream=True,
            )
            async for chunk in response:
                text = chunk.choices[0].delta.content if chunk.choices else None
                if text:
                    yield text

        except APIConnectionError as e:
            raise LLMError(
                f"Cannot reach LLM endpoint ({settings.llm_base_url}): {e}"
            ) from e
        except APIStatusError as e:
            raise LLMError(
                f"LLM API error [{e.status_code}]: {e.message}"
            ) from e
        except APIError as e:
            raise LLMError(f"LLM error: {e}") from e

    async def invoke(
        self,
        system_prompt: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> tuple[str, dict[str, int]]:
        """Invoke the LLM and return (full_text, usage_dict)."""
        settings = get_settings()
        full_messages = [{"role": "system", "content": system_prompt}, *messages]

        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=full_messages,  # type: ignore[arg-type]
                max_tokens=max_tokens or settings.llm_max_tokens,
                temperature=temperature or settings.llm_temperature,
                stream=False,
            )
        except APIConnectionError as e:
            raise LLMError(
                f"Cannot reach LLM endpoint ({settings.llm_base_url}): {e}"
            ) from e
        except APIStatusError as e:
            raise LLMError(
                f"LLM API error [{e.status_code}]: {e.message}"
            ) from e
        except APIError as e:
            raise LLMError(f"LLM error: {e}") from e

        text = response.choices[0].message.content or ""
        usage = {}
        if response.usage:
            usage = {
                "input_tokens": response.usage.prompt_tokens,
                "output_tokens": response.usage.completion_tokens,
            }
        return text, usage
