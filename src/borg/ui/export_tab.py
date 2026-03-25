"""Export tab for CSV export of commit data."""

from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Input, Static

from borg.db import Database


class ExportTab(Static):
    """Export tab for exporting commits to CSV."""

    def __init__(self, db: Database) -> None:
        """Initialize with database reference.

        Args:
            db: Database instance.
        """
        super().__init__()
        self.db = db

    def compose(self) -> ComposeResult:
        """Build export tab layout."""
        with Vertical():
            yield Input(
                value="borg-export.csv",
                placeholder="Export file path",
                id="export-path",
            )
            yield Button("Export", id="export-btn", variant="primary")
            yield Static("", id="export-result")

    def refresh_data(self, **kwargs) -> None:
        """No-op refresh for export tab.

        Args:
            org: Unused org filter.
        """

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle export button press."""
        if event.button.id == "export-btn":
            path_input = self.query_one("#export-path", Input)
            path = Path(path_input.value)
            try:
                count = self.db.export_csv(path, org=self.app.org_filter)
                result = self.query_one("#export-result", Static)
                result.update(f"Exported {count} rows to {path}")
            except Exception as e:
                result = self.query_one("#export-result", Static)
                result.update(f"Export failed: {e}")
