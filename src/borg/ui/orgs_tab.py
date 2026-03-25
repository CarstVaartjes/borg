"""Orgs tab for managing tracked organizations."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, DataTable, Input, Static

from borg.db import Database


class OrgsTab(Static):
    """Orgs tab for adding and removing tracked organizations."""

    def __init__(self, db: Database) -> None:
        """Initialize with database reference.

        Args:
            db: Database instance.
        """
        super().__init__()
        self.db = db

    def compose(self) -> ComposeResult:
        """Build orgs tab layout."""
        default_since = "2026-01-01"

        with Vertical():
            yield DataTable(id="orgs-table")
            with Horizontal():
                yield Input(
                    placeholder="Org name",
                    id="org-name-input",
                )
                yield Input(
                    value=default_since,
                    placeholder="Since date (YYYY-MM-DD)",
                    id="org-since-input",
                )
                yield Button("Add", id="add-org-btn", variant="primary")
            yield Button("Remove Selected", id="remove-org-btn", variant="error")
            yield Static("", id="org-result")

    def on_mount(self) -> None:
        """Set up the orgs table after mount."""
        table = self.query_one("#orgs-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Name", "Since", "Commits", "Added")
        self._refresh_table()

    def refresh_data(self, org: str | None = None) -> None:
        """Refresh the orgs table.

        Args:
            org: Unused org filter.
        """
        self._refresh_table()

    def _refresh_table(self) -> None:
        """Reload the orgs table from the database."""
        table = self.query_one("#orgs-table", DataTable)
        table.clear()
        orgs = self.db.org_list()
        for org in orgs:
            table.add_row(
                org["name"],
                org["since_date"],
                str(org["commit_count"]),
                org["added_at"][:10],
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle add/remove button presses."""
        if event.button.id == "add-org-btn":
            self._add_org()
        elif event.button.id == "remove-org-btn":
            self._remove_org()

    def _add_org(self) -> None:
        """Add a new org from input fields."""
        name_input = self.query_one("#org-name-input", Input)
        since_input = self.query_one("#org-since-input", Input)
        result = self.query_one("#org-result", Static)

        name = name_input.value.strip()
        since = since_input.value.strip()

        if not name:
            result.update("Please enter an org name")
            return

        try:
            self.db.org_add(name, since)
            result.update(f"Added org: {name}")
            name_input.value = ""
            self._refresh_table()
            self.app.refresh_org_dropdown()
        except ValueError as e:
            result.update(str(e))

    def _remove_org(self) -> None:
        """Remove the selected org from the table."""
        table = self.query_one("#orgs-table", DataTable)
        result = self.query_one("#org-result", Static)

        if table.cursor_row is None or table.row_count == 0:
            result.update("No org selected")
            return

        try:
            row = table.get_row_at(table.cursor_row)
            name = str(row[0])
            self.db.org_remove(name)
            result.update(f"Removed org: {name}")
            self._refresh_table()
            self.app.refresh_org_dropdown()
        except (ValueError, Exception) as e:
            result.update(str(e))
