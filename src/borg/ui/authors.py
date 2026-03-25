"""Authors tab — ranking table with Skynet Employee avatar."""

from textual import work
from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import DataTable, Static

from borg.db import Database, QueryFilters
from borg.ui.commit_modal import CommitDetailModal
from borg.ui.rankings import RankingTab


class AuthorsTab(Static):
    """Authors ranking with ASCII avatar for top author."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self.db = db
        self._ranking = RankingTab(db, "author", "Author")

    def compose(self) -> ComposeResult:
        with Horizontal(id="authors-layout"):
            yield self._ranking
            yield Static("", id="avatar-panel")

    def refresh_data(self, org: str | None = None, filters: QueryFilters | None = None) -> None:
        f = filters or QueryFilters(org=org)
        self._ranking.refresh_data(filters=f)
        self._update_avatar(f)

    def _update_avatar(self, f: QueryFilters) -> None:
        """Show ASCII avatar for the #1 ranked author."""
        rows = self.db.query_rankings(
            group_by="author", limit=1, min_commits=1,
            order_by=self._ranking._order_by,
            ascending=self._ranking._ascending,
            filters=f,
        )
        if not rows:
            self._set_avatar_text("No data")
            return

        top = rows[0]
        name = top["author"]
        ai = top["ai_commits"]
        total = top["total_commits"]
        pct = f"{ai / total * 100:.1f}%" if total > 0 else "0%"

        header = (
            f"⭐ Skynet Employee\n"
            f"   of the Month\n"
            f"\n"
            f"  {name}\n"
            f"  {ai} AI / {total} total ({pct})\n"
        )
        self._set_avatar_text(header + "\n  Loading avatar...")
        self._fetch_avatar(name, header)

    @work(thread=True)
    def _fetch_avatar(self, name: str, header: str) -> None:
        """Fetch and render avatar in background thread."""
        from borg.avatar import get_ascii_avatar

        # Get emails for this author
        try:
            emails = self.db.conn.execute(
                "SELECT DISTINCT email FROM _author_identity WHERE canonical_name = ?",
                (name,),
            ).fetchall()
            email_list = [r["email"] for r in emails]
        except Exception:
            email_list = [name]

        ascii_art = get_ascii_avatar(email_list, width=28, height=14)
        text = header + "\n" + ascii_art
        self.app.call_from_thread(self._set_avatar_text, text)

    def _set_avatar_text(self, text: str) -> None:
        try:
            self.query_one("#avatar-panel", Static).update(text)
        except Exception:
            pass

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        # Delegate to ranking, then refresh avatar
        self._ranking.on_data_table_header_selected(event)
        self._update_avatar(self.app.query_filters)

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        table = self._ranking.query_one("#ranking-table", DataTable)
        row = table.get_row_at(event.cursor_row)
        name = str(row[0])
        self.app.push_screen(
            CommitDetailModal(
                db=self.db,
                group_by="author",
                value=name,
                org=self.app.org_filter,
            )
        )
