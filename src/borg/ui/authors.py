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
        self._show_author_avatar(rows[0]["author"], is_top=True)

    @work(thread=True)
    def _fetch_avatar(self, title: str, stats: str, emails: tuple[str, ...]) -> None:
        """Fetch and render avatar in background thread."""
        from borg.avatar import get_ascii_avatar

        ascii_art = get_ascii_avatar(list(emails), width=28, height=14)
        text = title + "\n" + ascii_art + "\n" + stats
        self.app.call_from_thread(self._set_avatar_text, text)

    def _set_avatar_text(self, text: str) -> None:
        try:
            self.query_one("#avatar-panel", Static).update(text)
        except Exception:
            pass

    def _show_author_avatar(self, name: str, is_top: bool = False) -> None:
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

        # Favourite word
        msg_rows = self.db.conn.execute(
            f"SELECT message FROM commits WHERE commits.email IN ({placeholders}) "
            f"AND message IS NOT NULL",
            email_list,
        ).fetchall()
        fav_word = self._favourite_word([r["message"] for r in msg_rows])

        # Build text: name first, then avatar, then stats below
        title = (
            f"⭐ Skynet Employee of the Month\n\n"
            f"  {name}\n"
            f"  {ai} AI / {total} total ({pct})\n"
        )

        day_chart = self._bar_chart(
            "Day", ["M", "T", "W", "T", "F", "S", "S"],
            [day_counts[1], day_counts[2], day_counts[3], day_counts[4],
             day_counts[5], day_counts[6], day_counts[0]],
            bar_height=5, col_width=1,
        )
        # Group hours into 3h blocks for compact display
        hour_3h = [sum(hour_counts[i:i+3]) for i in range(0, 24, 3)]
        hour_chart = self._bar_chart(
            "Hour",
            ["0", "3", "6", "9", "12", "15", "18", "21"],
            hour_3h,
            bar_height=5, col_width=2,
        )

        stats = f"\n  Favourite repo: {fav}\n  Favourite word: {fav_word}\n\n"
        stats += self._side_by_side(day_chart, hour_chart, gap=2)

        self._set_avatar_text(title + "\n  Loading avatar...")
        self._fetch_avatar(title, stats, tuple(email_list))

    @staticmethod
    def _favourite_word(messages: list[str]) -> str:
        """Find the most common meaningful word across commit messages."""
        import re

        stop_words = {
            "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
            "for", "of", "with", "by", "from", "is", "it", "as", "be",
            "was", "are", "been", "this", "that", "not", "no", "if", "so",
            "we", "all", "do", "up", "out", "into", "when", "than", "then",
            "co", "authored", "noreply", "com", "anthropic", "github",
            "merge", "fix", "feat", "chore", "docs", "test", "ci", "refactor",
            "add", "update", "remove", "use", "set", "get", "new", "change",
            "make", "move", "run", "pr", "branch", "master", "main",
            "also", "now", "just", "only", "more", "each", "via", "per",
            "should", "can", "will", "has", "had", "have", "did", "does",
            "its", "after", "before", "instead", "without", "about",
            "which", "where", "some", "other", "using", "used",
            "claude", "copilot", "cursor", "aider", "openai", "opus",
            "visualfabriq", "pull", "request", "uat", "prod", "production",
            "preprod", "deploy", "release", "version", "bump", "config",
        }

        counts: dict[str, int] = {}
        for msg in messages:
            # Remove Jira tickets (PROJ-123) and URLs before extracting words
            cleaned = re.sub(r"[A-Z]{2,}-\d+", "", msg)
            cleaned = re.sub(r"https?://\S+", "", cleaned)
            words = re.findall(r"[a-z]{3,}", cleaned.lower())
            for word in words:
                if word not in stop_words:
                    counts[word] = counts.get(word, 0) + 1

        if not counts:
            return "—"

        top = sorted(counts.items(), key=lambda x: -x[1])[:1]
        return top[0][0]

    @staticmethod
    def _side_by_side(left: str, right: str, gap: int = 3) -> str:
        """Place two text blocks side by side."""
        left_lines = left.split("\n")
        right_lines = right.split("\n")
        max_left = max((len(l) for l in left_lines), default=0)
        height = max(len(left_lines), len(right_lines))
        lines = []
        for i in range(height):
            l = left_lines[i] if i < len(left_lines) else ""
            r = right_lines[i] if i < len(right_lines) else ""
            lines.append(f"{l:<{max_left}}{' ' * gap}{r}")
        return "\n".join(lines)

    @staticmethod
    def _bar_chart(
        title: str, labels: list[str], values: list[int],
        bar_height: int = 8, col_width: int = 1,
    ) -> str:
        """Render vertical bar chart. col_width controls bar + gap width."""
        max_val = max(values) or 1

        columns: list[list[str]] = []
        for val in values:
            fill = val * bar_height // max_val
            col = [" "] * (bar_height - fill) + ["█"] * fill
            columns.append(col)

        bar_char = "█" * col_width
        space_char = " " * col_width

        lines = [f"  {title}:"]
        for row in range(bar_height):
            line = "  "
            for col in columns:
                line += (bar_char if col[row] == "█" else space_char) + " "
            lines.append(line)

        label_line = "  "
        for label in labels:
            label_line += label[:col_width + 1].ljust(col_width + 1)
        lines.append(label_line)

        return "\n".join(lines)

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        # The event already bubbled to RankingTab which handled the sort toggle.
        # We just need to update the avatar for the new #1.
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
