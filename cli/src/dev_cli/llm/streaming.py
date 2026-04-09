from __future__ import annotations

from collections.abc import AsyncGenerator

from rich.console import Console
from rich.markdown import Markdown


class StreamingRenderer:
    """Render streaming LLM tokens to the terminal.

    Tokens are printed directly as they arrive (no re-rendering).
    The full response is rendered as Markdown once the stream ends.
    """

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    async def render(
        self,
        token_stream: AsyncGenerator[str, None],
        render_markdown: bool = True,
    ) -> str:
        """Stream tokens to terminal, return full accumulated text."""
        buffer = ""

        # Print tokens as they arrive — no re-rendering
        async for token in token_stream:
            buffer += token
            self._console.print(token, end="", markup=False, highlight=False)

        # Move to new line after stream ends
        self._console.print()

        # Re-render the full response as Markdown (replaces the raw token output)
        if render_markdown and buffer.strip():
            # Clear the raw streamed output and reprint as formatted markdown
            self._console.print()
            self._console.rule(style="dim")
            self._console.print(Markdown(buffer))
            self._console.rule(style="dim")

        return buffer
