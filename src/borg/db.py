"""Database layer for borg tracker.

Wraps sqlite3 with org CRUD, sync metadata, commit operations,
and report queries.
"""

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


class Database:
    """SQLite database wrapper for the borg tracker."""

    def __init__(self, path: Path) -> None:
        """Initialize database, creating parent dirs and schema.

        Args:
            path: Path to the SQLite database file.
        """
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path))
        self.conn.row_factory = sqlite3.Row
        self._create_schema()

    def _create_schema(self) -> None:
        """Create all tables and indexes if they don't exist."""
        self.conn.executescript("""
            PRAGMA journal_mode=WAL;

            CREATE TABLE IF NOT EXISTS orgs (
                name TEXT PRIMARY KEY,
                since_date TEXT NOT NULL,
                added_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS commits (
                sha TEXT PRIMARY KEY,
                org TEXT NOT NULL,
                repo TEXT NOT NULL,
                author TEXT NOT NULL,
                email TEXT NOT NULL,
                date TEXT NOT NULL,
                additions INTEGER,
                deletions INTEGER,
                message TEXT,
                ai_tool TEXT,
                ai_confidence TEXT,
                fetched_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS repo_sync (
                org TEXT NOT NULL,
                repo TEXT NOT NULL,
                last_commit_date TEXT,
                last_synced_at TEXT,
                commit_count INTEGER DEFAULT 0,
                PRIMARY KEY (org, repo)
            );

            CREATE TABLE IF NOT EXISTS sync_meta (
                key TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_commits_org ON commits(org);
            CREATE INDEX IF NOT EXISTS idx_commits_repo ON commits(repo);
            CREATE INDEX IF NOT EXISTS idx_commits_ai_tool ON commits(ai_tool);
            CREATE INDEX IF NOT EXISTS idx_commits_date ON commits(date);
            CREATE INDEX IF NOT EXISTS idx_commits_additions ON commits(additions);
        """)

    @staticmethod
    def _utc_now() -> str:
        """Return current UTC timestamp as ISO string."""
        return datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    @staticmethod
    def _org_filter(org: str | None) -> tuple[str, tuple[str, ...] | tuple[()]]:
        """Build a WHERE clause fragment for optional org filtering.

        Args:
            org: Org name to filter by, or None for all orgs.

        Returns:
            Tuple of (where_clause, params_tuple).
        """
        if org is None:
            return ("1=1", ())
        return ("org = ?", (org,))

    # ── Org CRUD ──────────────────────────────────────────────────────

    def org_add(self, name: str, since_date: str) -> None:
        """Add a new org.

        Args:
            name: Org name (must be unique).
            since_date: Date to start tracking from (YYYY-MM-DD).

        Raises:
            ValueError: If org already exists.
        """
        existing = self.conn.execute(
            "SELECT 1 FROM orgs WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            raise ValueError(f"Org '{name}' already exists")
        self.conn.execute(
            "INSERT INTO orgs (name, since_date, added_at) VALUES (?, ?, ?)",
            (name, since_date, self._utc_now()),
        )
        self.conn.commit()

    def org_remove(self, name: str) -> None:
        """Remove an org and all its associated data.

        Args:
            name: Org name to remove.

        Raises:
            ValueError: If org not found.
        """
        existing = self.conn.execute(
            "SELECT 1 FROM orgs WHERE name = ?", (name,)
        ).fetchone()
        if not existing:
            raise ValueError(f"Org '{name}' not found")
        self.conn.execute("DELETE FROM commits WHERE org = ?", (name,))
        self.conn.execute("DELETE FROM repo_sync WHERE org = ?", (name,))
        self.conn.execute("DELETE FROM orgs WHERE name = ?", (name,))
        self.conn.commit()

    def org_get_all(self) -> list[dict]:
        """Get all orgs sorted by name.

        Returns:
            List of org dicts with name, since_date, added_at.
        """
        rows = self.conn.execute("SELECT * FROM orgs ORDER BY name").fetchall()
        return [dict(r) for r in rows]

    def org_get(self, name: str) -> dict | None:
        """Get a single org by name.

        Args:
            name: Org name to look up.

        Returns:
            Dict with org data, or None if not found.
        """
        row = self.conn.execute("SELECT * FROM orgs WHERE name = ?", (name,)).fetchone()
        return dict(row) if row else None

    def org_list(self) -> list[dict]:
        """Get all orgs with commit counts.

        Returns:
            List of dicts with name, since_date, added_at, commit_count.
        """
        rows = self.conn.execute("""
            SELECT o.name, o.since_date, o.added_at,
                   COUNT(c.sha) AS commit_count
            FROM orgs o
            LEFT JOIN commits c ON o.name = c.org
            GROUP BY o.name
            ORDER BY o.name
        """).fetchall()
        return [dict(r) for r in rows]

    # ── Meta ──────────────────────────────────────────────────────────

    def get_meta(self, key: str) -> str | None:
        """Get a metadata value.

        Args:
            key: Metadata key.

        Returns:
            Value string, or None if not found.
        """
        row = self.conn.execute(
            "SELECT value FROM sync_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        """Set a metadata value (upsert).

        Args:
            key: Metadata key.
            value: Metadata value.
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO sync_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self.conn.commit()

    # ── Report queries ────────────────────────────────────────────────

    def query_summary(self, org: str | None = None) -> dict:
        """Get summary statistics.

        Args:
            org: Optional org filter.

        Returns:
            Dict with total_commits, ai_commits, total_loc, ai_loc.
        """
        where, params = self._org_filter(org)
        row = self.conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_commits,
                SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN 1 ELSE 0 END) AS ai_commits,
                COALESCE(SUM(additions), 0) AS total_loc,
                COALESCE(SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN additions ELSE 0 END), 0) AS ai_loc
            FROM commits
            WHERE {where}
        """,
            params,
        ).fetchone()
        return dict(row)

    def query_by_tool(self, org: str | None = None) -> list[dict]:
        """Get commit counts grouped by AI tool.

        Args:
            org: Optional org filter.

        Returns:
            List of dicts with tool, commits, loc.
        """
        where, params = self._org_filter(org)
        rows = self.conn.execute(
            f"""
            SELECT
                ai_tool AS tool,
                COUNT(*) AS commits,
                COALESCE(SUM(additions), 0) AS loc
            FROM commits
            WHERE ai_tool IS NOT NULL AND ai_tool != '' AND {where}
            GROUP BY ai_tool
            ORDER BY commits DESC
        """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def query_rankings(
        self,
        group_by: str,
        org: str | None = None,
        limit: int = 10,
        min_commits: int = 5,
        order_by: str = "ai_commits",
        ascending: bool = False,
    ) -> list[dict]:
        """Get rankings by author or repo.

        Args:
            group_by: Column to group by ('author' or 'repo').
            org: Optional org filter.
            limit: Max results to return.
            min_commits: Minimum total commits to be included.
            order_by: Column to sort by.
            ascending: Sort ascending if True, descending if False.

        Returns:
            List of ranked dicts.
        """
        # Validate group_by to prevent SQL injection (it's interpolated)
        if group_by not in ("author", "repo"):
            raise ValueError(f"Invalid group_by: {group_by}")
        if order_by not in ("ai_commits", "total_commits", "ai_loc", "total_loc"):
            raise ValueError(f"Invalid order_by: {order_by}")

        where, params = self._org_filter(org)
        direction = "ASC" if ascending else "DESC"
        rows = self.conn.execute(
            f"""
            SELECT
                {group_by},
                COUNT(*) AS total_commits,
                SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN 1 ELSE 0 END) AS ai_commits,
                COALESCE(SUM(additions), 0) AS total_loc,
                COALESCE(SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN additions ELSE 0 END), 0) AS ai_loc
            FROM commits
            WHERE {where}
            GROUP BY {group_by}
            HAVING COUNT(*) >= ?
            ORDER BY {order_by} {direction}
            LIMIT ?
        """,
            (*params, min_commits, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_trends(
        self,
        period: str = "monthly",
        org: str | None = None,
    ) -> list[dict]:
        """Get commit trends over time.

        Args:
            period: 'monthly' or 'weekly'.
            org: Optional org filter.

        Returns:
            List of dicts with period, total, ai, total_loc, ai_loc.
        """
        where, params = self._org_filter(org)
        if period == "weekly":
            period_expr = "strftime('%Y-W%W', date)"
        else:
            period_expr = "strftime('%Y-%m', date)"

        rows = self.conn.execute(
            f"""
            SELECT
                {period_expr} AS period,
                COUNT(*) AS total,
                SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN 1 ELSE 0 END) AS ai,
                COALESCE(SUM(additions), 0) AS total_loc,
                COALESCE(SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN additions ELSE 0 END), 0) AS ai_loc
            FROM commits
            WHERE {where}
            GROUP BY period
            ORDER BY period
        """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def query_skynet_employee(self, org: str | None = None) -> dict | None:
        """Get the author with the most AI commits in the last 7 days.

        Args:
            org: Optional org filter.

        Returns:
            Dict with author and ai_commits, or None.
        """
        where, params = self._org_filter(org)
        row = self.conn.execute(
            f"""
            SELECT
                author,
                COUNT(*) AS ai_commits
            FROM commits
            WHERE ai_tool IS NOT NULL AND ai_tool != ''
              AND date >= date('now', '-7 days')
              AND {where}
            GROUP BY author
            ORDER BY ai_commits DESC
            LIMIT 1
        """,
            params,
        ).fetchone()
        return dict(row) if row else None

    def export_csv(self, path: Path, org: str | None = None) -> int:
        """Export commits to a CSV file.

        Args:
            path: Output file path.
            org: Optional org filter.

        Returns:
            Number of rows exported.
        """
        where, params = self._org_filter(org)
        rows = self.conn.execute(
            f"""
            SELECT * FROM commits WHERE {where} ORDER BY date
        """,
            params,
        ).fetchall()

        if not rows:
            return 0

        columns = rows[0].keys()
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(tuple(row))

        return len(rows)

    # ── Commit operations (for fetch layer) ───────────────────────────

    def insert_commit(
        self,
        sha: str,
        org: str,
        repo: str,
        author: str,
        email: str,
        date: str,
        message: str,
    ) -> bool:
        """Insert a new commit.

        Args:
            sha: Commit SHA hash.
            org: Organization name.
            repo: Repository name.
            author: Author name.
            email: Author email.
            date: Commit date.
            message: Commit message.

        Returns:
            True if inserted (new), False if duplicate.
        """
        try:
            self.conn.execute(
                """INSERT INTO commits
                   (sha, org, repo, author, email, date, message, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (sha, org, repo, author, email, date, message, self._utc_now()),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def update_commit_stats(self, sha: str, additions: int, deletions: int) -> None:
        """Update a commit's line-count statistics.

        Args:
            sha: Commit SHA hash.
            additions: Lines added.
            deletions: Lines deleted.
        """
        self.conn.execute(
            "UPDATE commits SET additions = ?, deletions = ? WHERE sha = ?",
            (additions, deletions, sha),
        )
        self.conn.commit()

    def get_unenriched_commits(self, limit: int = 100) -> list[dict]:
        """Get commits that haven't been enriched with stats.

        Args:
            limit: Max rows to return.

        Returns:
            List of commit dicts without additions data.
        """
        rows = self.conn.execute(
            "SELECT * FROM commits WHERE additions IS NULL ORDER BY date LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_repo_sync(
        self,
        org: str,
        repo: str,
        last_commit_date: str,
        commit_count: int,
    ) -> None:
        """Update or insert repo sync bookmark.

        Args:
            org: Organization name.
            repo: Repository name.
            last_commit_date: Date of last synced commit.
            commit_count: Total commits synced for this repo.
        """
        self.conn.execute(
            """INSERT OR REPLACE INTO repo_sync
               (org, repo, last_commit_date, last_synced_at, commit_count)
               VALUES (?, ?, ?, ?, ?)""",
            (org, repo, last_commit_date, self._utc_now(), commit_count),
        )
        self.conn.commit()

    def get_repo_bookmark(self, org: str, repo: str) -> str | None:
        """Get the last synced commit date for a repo.

        Args:
            org: Organization name.
            repo: Repository name.

        Returns:
            Last commit date string, or None.
        """
        row = self.conn.execute(
            "SELECT last_commit_date FROM repo_sync WHERE org = ? AND repo = ?",
            (org, repo),
        ).fetchone()
        return row["last_commit_date"] if row else None

    def get_repo_commit_count(self, org: str, repo: str) -> int:
        """Get the total synced commit count for a repo.

        Args:
            org: Organization name.
            repo: Repository name.

        Returns:
            Commit count, or 0 if not tracked.
        """
        row = self.conn.execute(
            "SELECT commit_count FROM repo_sync WHERE org = ? AND repo = ?",
            (org, repo),
        ).fetchone()
        return row["commit_count"] if row else 0
