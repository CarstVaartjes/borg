"""Fetch tab with progress log and async GitHub fetching."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, RichLog, Static
from textual.worker import Worker, WorkerState

from borg.db import Database
from borg.detect import detect_ai
from borg.fetch import FetchProgress, GitHubFetcher


class FetchTab(Static):
    """Fetch tab for running GitHub data synchronization."""

    def __init__(self, db: Database) -> None:
        """Initialize with database reference.

        Args:
            db: Database instance.
        """
        super().__init__()
        self.db = db

    def compose(self) -> ComposeResult:
        """Build fetch tab layout."""
        with Vertical():
            yield Button("Start Fetch", id="fetch-btn", variant="primary")
            yield RichLog(id="fetch-log", highlight=True, markup=True)

    def refresh_data(self, org: str | None = None) -> None:
        """No-op refresh for fetch tab.

        Args:
            org: Unused org filter.
        """

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle fetch button press."""
        if event.button.id == "fetch-btn":
            self._start_fetch()

    def _start_fetch(self) -> None:
        """Start the async fetch process."""
        btn = self.query_one("#fetch-btn", Button)
        btn.disabled = True
        log = self.query_one("#fetch-log", RichLog)
        log.clear()
        log.write("[bold]Starting fetch...[/bold]")
        self.run_worker(self._do_fetch(), exclusive=True)

    def _on_progress(self, progress: FetchProgress) -> None:
        """Handle progress callback from the fetcher.

        Runs in the same async context as the worker, so direct
        widget access is safe.

        Args:
            progress: Progress update from GitHubFetcher.
        """
        try:
            log = self.query_one("#fetch-log", RichLog)
            log.write(f"[{progress.phase}] {progress.message}")
        except Exception:
            pass

    async def _do_fetch(self) -> None:
        """Async fetch worker body."""
        log = self.query_one("#fetch-log", RichLog)
        try:
            fetcher = GitHubFetcher(self.db)
            fetcher.set_progress_callback(self._on_progress)
            await fetcher.fetch_all(org_filter=self.app.org_filter)
            await fetcher.close()

            log.write("[bold green]Fetch complete.[/bold green]")

            # Run AI detection
            log.write("[bold]Running AI detection...[/bold]")
            result = detect_ai(self.db)
            log.write(
                f"[bold green]Detection complete: {result['total']} AI commits "
                f"({result['high']} high, {result['low']} low)[/bold green]"
            )
        except Exception as e:
            log.write(f"[bold red]Error: {e}[/bold red]")
        finally:
            btn = self.query_one("#fetch-btn", Button)
            btn.disabled = False

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Handle worker state changes."""
        if event.state == WorkerState.ERROR:
            try:
                log = self.query_one("#fetch-log", RichLog)
                log.write(f"[bold red]Worker error: {event.worker.error}[/bold red]")
            except Exception:
                pass
