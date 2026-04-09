from __future__ import annotations

from collections.abc import AsyncGenerator

from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.text import Text


class StreamingRenderer:
    """Render streaming LLM tokens to the terminal using Rich Live display."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    async def render(
        self,
        token_stream: AsyncGenerator[str, None],
        render_markdown: bool = True,
    ) -> str:
        """Consume *token_stream*, display tokens live, return full accumulated text."""
        buffer = ""

        with Live(
            Text(""),
            console=self._console,
            refresh_per_second=15,
            vertical_overflow="visible",
        ) as live:
            async for token in token_stream:
                buffer += token
                if render_markdown:
                    live.update(Markdown(buffer))
                else:
                    live.update(Text(buffer))

        return buffer
