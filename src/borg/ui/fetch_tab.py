"""Fetch & Detect tab — unified data sync and AI detection."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, RichLog, Static
from textual.worker import Worker, WorkerState

from borg.db import Database
from borg.detect import RULES, detect_ai
from borg.fetch import FetchProgress, GitHubFetcher


class FetchTab(Static):
    """Unified Fetch & Detect tab."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db

    def compose(self) -> ComposeResult:
        with Vertical():
            with Horizontal(id="fetch-buttons"):
                yield Button("Fetch & Detect", id="fetch-btn", variant="primary")
                yield Button("Re-run Detection Only", id="detect-btn", variant="default")
            yield RichLog(id="fetch-log", highlight=True, markup=True)
            yield Static("Detection Rules", id="rules-title")
            yield DataTable(id="rules-table")

    def on_mount(self) -> None:
        table = self.query_one("#rules-table", DataTable)
        table.add_columns("Tool", "Confidence", "Pattern")
        for tool, confidence, pattern in RULES:
            table.add_row(tool, confidence, pattern[:80])

    def refresh_data(self, org: str | None = None) -> None:
        pass

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "fetch-btn":
            self._start_fetch_and_detect()
        elif event.button.id == "detect-btn":
            self._run_detect_only()

    def _start_fetch_and_detect(self) -> None:
        self.query_one("#fetch-btn", Button).disabled = True
        self.query_one("#detect-btn", Button).disabled = True
        log = self.query_one("#fetch-log", RichLog)
        log.clear()
        log.write("[bold]Starting fetch...[/bold]")
        self.run_worker(self._do_fetch_and_detect(), exclusive=True)

    def _run_detect_only(self) -> None:
        self.query_one("#fetch-btn", Button).disabled = True
        self.query_one("#detect-btn", Button).disabled = True
        log = self.query_one("#fetch-log", RichLog)
        log.clear()
        log.write("[bold]Running AI detection...[/bold]")
        result = detect_ai(self.db)
        log.write(
            f"[bold green]Detection complete: {result['high']} high, "
            f"{result['medium']} medium, {result['low']} low, "
            f"{result['total']} total[/bold green]"
        )
        self.query_one("#fetch-btn", Button).disabled = False
        self.query_one("#detect-btn", Button).disabled = False

    def _on_progress(self, progress: FetchProgress) -> None:
        try:
            log = self.query_one("#fetch-log", RichLog)
            log.write(f"  {progress.message}")
        except Exception:
            pass

    async def _do_fetch_and_detect(self) -> None:
        log = self.query_one("#fetch-log", RichLog)
        try:
            fetcher = GitHubFetcher(self.db)
            fetcher.set_progress_callback(self._on_progress)
            await fetcher.fetch_all(org_filter=self.app.org_filter)
            await fetcher.close()
            log.write("[bold green]Fetch complete.[/bold green]")

            log.write("[bold]Running AI detection...[/bold]")
            result = detect_ai(self.db)
            log.write(
                f"[bold green]Detection complete: {result['high']} high, "
                f"{result['low']} low, {result['total']} total[/bold green]"
            )
        except Exception as e:
            log.write(f"[bold red]Error: {e}[/bold red]")
        finally:
            self.query_one("#fetch-btn", Button).disabled = False
            self.query_one("#detect-btn", Button).disabled = False

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == WorkerState.ERROR:
            try:
                log = self.query_one("#fetch-log", RichLog)
                log.write(f"[bold red]Worker error: {event.worker.error}[/bold red]")
            except Exception:
                pass
