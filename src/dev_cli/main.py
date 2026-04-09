from __future__ import annotations

from typing import Optional

import typer
from rich.console import Console

from src.dev_cli.version import __app_name__, __version__

app = typer.Typer(
    name=__app_name__,
    help="Interactive AI developer assistant powered by your LLM of choice.",
    add_completion=False,
    rich_markup_mode="rich",
)

console = Console()


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"{__app_name__} v{__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: Optional[bool] = typer.Option(
        None,
        "--version",
        "-v",
        callback=_version_callback,
        is_eager=True,
        help="Show version and exit",
    ),
    verbose: bool = typer.Option(False, "--verbose", help="Enable debug logging"),
) -> None:
    if verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)


# --- Register commands ---

from src.dev_cli.commands.init import init_command
from src.dev_cli.commands.chat import chat_command
from src.dev_cli.commands.analyze import analyze_command
from src.dev_cli.commands.context import context_command
from src.dev_cli.commands.status import status_command

app.command("init")(init_command)
app.command("chat")(chat_command)
app.command("analyze")(analyze_command)
app.command("context")(context_command)
app.command("status")(status_command)
