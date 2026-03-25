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
            f"⭐ Skynet Employee of the Month\n"
            f"\n"
            f"  {name}\n"
            f"  {ai} AI / {total} total ({pct})\n"
        )
        # Get emails on main thread (SQLite isn't thread-safe)
        try:
            emails = self.db.conn.execute(
                "SELECT DISTINCT email FROM _author_identity WHERE canonical_name = ?",
                (name,),
            ).fetchall()
            email_list = [r["email"] for r in emails]
        except Exception:
            email_list = []

        self._set_avatar_text(header + "\n  Loading avatar...")
        self._fetch_avatar(header, tuple(email_list))

    @work(thread=True)
    def _fetch_avatar(self, header: str, emails: tuple[str, ...]) -> None:
        """Fetch and render avatar in background thread."""
        from borg.avatar import get_ascii_avatar

        ascii_art = get_ascii_avatar(list(emails), width=56, height=28)
        text = header + "\n" + ascii_art
        self.app.call_from_thread(self._set_avatar_text, text)

    def _set_avatar_text(self, text: str) -> None:
        try:
            self.query_one("#avatar-panel", Static).update(text)
        except Exception:
            pass

    def _show_author_avatar(self, name: str) -> None:
        """Show avatar and stats for a specific author."""
        # Get emails for this author
        try:
            emails = self.db.conn.execute(
                "SELECT DISTINCT email FROM _author_identity WHERE canonical_name = ?",
                (name,),
            ).fetchall()
            email_list = [r["email"] for r in emails]
        except Exception:
            email_list = []

        if not email_list:
            self._set_avatar_text(f"⭐ {name}\n  No data")
            return

        placeholders = ",".join("?" * len(email_list))

        # Basic stats
        row = self.db.conn.execute(
            f"SELECT COUNT(*) as total, "
            f"SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN 1 ELSE 0 END) as ai "
            f"FROM commits WHERE commits.email IN ({placeholders})",
            email_list,
        ).fetchone()
        total, ai = row["total"], row["ai"]
        pct = f"{ai / total * 100:.1f}%" if total > 0 else "0%"

        # Favourite repo
        fav_repo = self.db.conn.execute(
            f"SELECT repo, COUNT(*) as cnt FROM commits "
            f"WHERE commits.email IN ({placeholders}) "
            f"GROUP BY repo ORDER BY cnt DESC LIMIT 1",
            email_list,
        ).fetchone()
        fav = fav_repo["repo"] if fav_repo else "—"

        # Day of week distribution (0=Sun, 6=Sat)
        day_rows = self.db.conn.execute(
            f"SELECT CAST(strftime('%w', date) AS INTEGER) as dow, COUNT(*) as cnt "
            f"FROM commits WHERE commits.email IN ({placeholders}) "
            f"GROUP BY dow ORDER BY dow",
            email_list,
        ).fetchall()
        day_counts = [0] * 7
        for dr in day_rows:
            day_counts[dr["dow"]] = dr["cnt"]

        # Hour distribution
        hour_rows = self.db.conn.execute(
            f"SELECT CAST(strftime('%H', date) AS INTEGER) as hour, COUNT(*) as cnt "
            f"FROM commits WHERE commits.email IN ({placeholders}) "
            f"GROUP BY hour ORDER BY hour",
            email_list,
        ).fetchall()
        hour_counts = [0] * 24
        for hr in hour_rows:
            hour_counts[hr["hour"]] = hr["cnt"]

        # Build text
        header = (
            f"⭐ {name}\n"
            f"  {ai} AI / {total} total ({pct})\n"
            f"  Favourite repo: {fav}\n"
        )
        header += "\n" + self._bar_chart(
            "Day", ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"],
            [day_counts[1], day_counts[2], day_counts[3], day_counts[4],
             day_counts[5], day_counts[6], day_counts[0]],
        )
        header += "\n" + self._bar_chart(
            "Hour",
            [str(h) for h in range(24)],
            hour_counts,
        )

        self._set_avatar_text(header + "\n  Loading avatar...")
        self._fetch_avatar(header, tuple(email_list))

    @staticmethod
    def _bar_chart(title: str, labels: list[str], values: list[int]) -> str:
        """Render a small horizontal bar chart."""
        total = sum(values) or 1
        max_val = max(values) or 1
        bar_width = 20
        lines = [f"  {title}:"]
        for label, val in zip(labels, values):
            pct = val * 100 // total
            fill = val * bar_width // max_val
            bar = "█" * fill + "░" * (bar_width - fill)
            lines.append(f"  {label:>2} {bar} {pct:>2}%")
        return "\n".join(lines)

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        self._ranking.on_data_table_header_selected(event)
        self._update_avatar(self.app.query_filters)

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        """Update avatar when cursor moves to a different row."""
        try:
            table = self._ranking.query_one("#ranking-table", DataTable)
            row = table.get_row_at(event.cursor_row)
            name = str(row[0])
            self._show_author_avatar(name)
        except Exception:
            pass

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Open commit detail modal on Enter."""
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
