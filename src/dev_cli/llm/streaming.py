from __future__ import annotations

from collections.abc import AsyncGenerator

from rich.console import Console
from rich.markdown import Markdown

# Use ANSI-only syntax theme so code blocks have no custom background colour.
# This prevents macOS Terminal's text-selection highlight from blending into
# the code block background and making selected text unreadable.
_CODE_THEME = "ansi_dark"


class StreamingRenderer:
    """Stream LLM tokens to terminal, render as Markdown once complete."""

    def __init__(self, console: Console | None = None) -> None:
        self._console = console or Console()

    async def render(
        self,
        token_stream: AsyncGenerator[str, None],
        render_markdown: bool = True,
    ) -> str:
        """Consume token stream, show spinner while waiting, render when done."""
        buffer = ""

        with self._console.status("[dim]Thinking…[/dim]", spinner="dots"):
            async for token in token_stream:
                buffer += token

        if render_markdown:
            self._console.print(Markdown(buffer, code_theme=_CODE_THEME))
        else:
            self._console.print(buffer, markup=False, highlight=False)

        return buffer
