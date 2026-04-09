from __future__ import annotations

from collections.abc import AsyncGenerator

from rich.console import Console
from rich.markdown import Markdown


class StreamingRenderer:
    """Stream LLM tokens to terminal, render as Markdown once complete."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    async def render(
        self,
        token_stream: AsyncGenerator[str, None],
        render_markdown: bool = True,
    ) -> str:
        """Consume token stream, return full accumulated text."""
        buffer = ""

        if render_markdown:
            # Accumulate silently, render once as formatted Markdown
            async for token in token_stream:
                buffer += token
            self._console.print(Markdown(buffer))
        else:
            # Plain text: print tokens as they arrive
            async for token in token_stream:
                buffer += token
                self._console.print(token, end="", markup=False, highlight=False)
            self._console.print()

        return buffer
