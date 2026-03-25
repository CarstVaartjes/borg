"""CLI entry point — launches the TUI."""

import typer
from pathlib import Path

app = typer.Typer(add_completion=False)

DEFAULT_DB = Path.home() / ".local" / "share" / "borg" / "tracker.db"


@app.command()
def main(
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Borg — AI commit adoption tracker. Resistance is futile."""
    from borg.ui.app import BorgApp

    tui = BorgApp(db_path=db)
    tui.run()


if __name__ == "__main__":
    app()
