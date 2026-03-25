"""Detect tab showing AI detection rules and re-run button."""

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, DataTable, Static

from borg.db import Database
from borg.detect import RULES, detect_ai


class DetectTab(Static):
    """Detect tab for viewing and running AI detection rules."""

    def __init__(self, db: Database) -> None:
        """Initialize with database reference.

        Args:
            db: Database instance.
        """
        super().__init__()
        self.db = db

    def compose(self) -> ComposeResult:
        """Build detect tab layout."""
        with Vertical():
            yield DataTable(id="rules-table")
            yield Button("Re-run Detection", id="detect-btn", variant="primary")
            yield Static("", id="detect-result")

    def on_mount(self) -> None:
        """Populate the rules table after mount."""
        table = self.query_one("#rules-table", DataTable)
        table.add_columns("Tool", "Confidence", "Pattern")
        for tool, confidence, pattern in RULES:
            table.add_row(tool, confidence, pattern[:80])

    def refresh_data(self, **kwargs) -> None:
        """No-op refresh for detect tab.

        Args:
            org: Unused org filter.
        """

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle detect button press."""
        if event.button.id == "detect-btn":
            result = detect_ai(self.db)
            result_widget = self.query_one("#detect-result", Static)
            result_widget.update(
                f"Detection complete: {result['total']} AI commits "
                f"({result['high']} high confidence, {result['low']} low confidence)"
            )
