"""Modal screen showing commit details for an author or repo."""

import webbrowser

from textual.app import ComposeResult
from textual.binding import Binding
from textual.screen import ModalScreen
from textual.widgets import DataTable, Static

from borg.db import Database


class CommitDetailModal(ModalScreen):
    """Modal popup showing individual commits for a selected author or repo."""

    CSS = """
    CommitDetailModal {
        align: center middle;
    }
    #commit-modal-container {
        width: 95%;
        height: 85%;
        border: thick $accent;
        background: $surface;
        padding: 1 2;
    }
    #commit-modal-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #commit-table {
        height: 1fr;
    }
    #commit-modal-hint {
        height: 1;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    def __init__(
        self,
        db: Database,
        group_by: str,
        value: str,
        org: str | None = None,
    ) -> None:
        super().__init__()
        self._db = db
        self._group_by = group_by
        self._value = value
        self._org = org

    def compose(self) -> ComposeResult:
        with Static(id="commit-modal-container"):
            label = "Author" if self._group_by == "author" else "Repo"
            yield Static(f"{label}: {self._value}", id="commit-modal-title")
            yield DataTable(id="commit-table", zebra_stripes=True)
            yield Static("Enter: open in browser  |  ESC: close", id="commit-modal-hint")

    def on_mount(self) -> None:
        self._urls: list[str] = []
        table = self.query_one("#commit-table", DataTable)
        table.cursor_type = "row"
        table.add_columns("Date", "AI", "+", "-", "Message")

        commits = self._db.query_commits_by(
            self._group_by, self._value, org=self._org
        )

        for c in commits:
            ai = c["ai_tool"] or ""
            url = f"https://github.com/{c['org']}/{c['repo']}/commit/{c['sha']}"
            self._urls.append(url)
            msg = (c["message"] or "").split("\n")[0][:80]
            date = c["date"][:10] if c["date"] else ""
            table.add_row(
                date,
                ai,
                str(c["additions"]),
                str(c["deletions"]),
                msg,
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open the commit URL in the browser."""
        if 0 <= event.cursor_row < len(self._urls):
            webbrowser.open(self._urls[event.cursor_row])
