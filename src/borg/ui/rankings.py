"""Reusable ranking table widget for author/repo rankings."""

from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from borg.db import Database
from borg.ui.commit_modal import CommitDetailModal

# Map display column names to db query order_by values.
_COLUMN_MAP = {
    "AI": "ai_commits",
    "Total": "total_commits",
    "%": "ai_commits",
    "AI LOC": "ai_loc",
    "Total LOC": "total_loc",
    "LOC %": "ai_loc",
}


class RankingTab(Static):
    """Sortable ranking table for authors or repos."""

    def __init__(self, db: Database, group_by: str, label: str) -> None:
        super().__init__()
        self.db = db
        self.group_by = group_by
        self.label = label
        self._order_by = "ai_commits"
        self._ascending = False

    def compose(self) -> ComposeResult:
        table = DataTable(id="ranking-table")
        table.cursor_type = "row"
        yield table

    def on_mount(self) -> None:
        table = self.query_one("#ranking-table", DataTable)
        table.add_columns(self.label, "AI", "Total", "%", "AI LOC", "Total LOC", "LOC %")

    def refresh_data(self, org: str | None = None) -> None:
        table = self.query_one("#ranking-table", DataTable)
        table.clear()

        rows = self.db.query_rankings(
            group_by=self.group_by,
            org=org,
            limit=50,
            min_commits=1,
            order_by=self._order_by,
            ascending=self._ascending,
        )

        for row in rows:
            total = row["total_commits"]
            ai = row["ai_commits"]
            commit_pct = f"{ai / total * 100:.1f}%" if total > 0 else "0%"
            total_loc = row["total_loc"]
            ai_loc = row["ai_loc"]
            loc_pct = f"{ai_loc / total_loc * 100:.1f}%" if total_loc > 0 else "0%"
            table.add_row(
                row[self.group_by],
                str(ai),
                str(total),
                commit_pct,
                str(ai_loc),
                str(total_loc),
                loc_pct,
            )

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_label = str(event.label)
        db_col = _COLUMN_MAP.get(col_label)
        if db_col is None:
            return
        if self._order_by == db_col:
            self._ascending = not self._ascending
        else:
            self._order_by = db_col
            self._ascending = False
        self.refresh_data(org=self.app.org_filter)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table = self.query_one("#ranking-table", DataTable)
        row = table.get_row_at(event.cursor_row)
        name = str(row[0])
        self.app.push_screen(
            CommitDetailModal(
                db=self.db,
                group_by=self.group_by,
                value=name,
                org=self.app.org_filter,
            )
        )
