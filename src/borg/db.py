"""Database layer for borg tracker.

Wraps sqlite3 with org CRUD, sync metadata, commit operations,
and report queries.
"""

import csv
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class QueryFilters:
    """Filters applied to report queries."""

    org: str | None = None
    repo: str | None = None
    author: str | None = None
    month: str | None = None  # "2026-03"
    week: str | None = None   # "2026-W12"
    loc_mode: str = "both"    # "both" = additions+deletions, "added" = additions only


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
                in_production INTEGER NOT NULL DEFAULT 0,
                pr_number INTEGER,
                pr_state TEXT,
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

            CREATE TABLE IF NOT EXISTS author_aliases (
                email TEXT PRIMARY KEY,
                canonical_name TEXT NOT NULL
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

    def resolve_author_identities(self) -> dict[str, str]:
        """Resolve author identities by transitively merging by name and email.

        If two emails share a name, they're the same person. If two names share
        an email, they're the same person. This is applied recursively until
        stable. Returns a mapping of email → canonical display name (the most
        frequently used name in the group).
        """
        # Get all unique (author, email) pairs with counts
        rows = self.conn.execute(
            "SELECT author, email, COUNT(*) as cnt FROM commits GROUP BY author, email"
        ).fetchall()

        # Union-Find
        parent: dict[str, str] = {}

        def find(x: str) -> str:
            while parent.get(x, x) != x:
                parent[x] = parent.get(parent[x], parent[x])
                x = parent[x]
            return x

        def union(a: str, b: str) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        # Collect all emails and names
        all_keys: set[str] = set()
        name_to_emails: dict[str, list[str]] = {}
        email_to_names: dict[str, list[str]] = {}

        for r in rows:
            name, email = r["author"], r["email"]
            key_name = f"name:{name}"
            key_email = f"email:{email}"
            all_keys.add(key_name)
            all_keys.add(key_email)
            # Same name → merge their emails
            name_to_emails.setdefault(name, []).append(email)
            # Same email → merge their names
            email_to_names.setdefault(email, []).append(name)
            # Union the name and email nodes
            union(key_name, key_email)

        # Now, for each name with multiple emails, union those emails
        for name, emails in name_to_emails.items():
            for email in emails[1:]:
                union(f"email:{emails[0]}", f"email:{email}")

        # For each email with multiple names, union those names
        for email, names in email_to_names.items():
            for name in names[1:]:
                union(f"name:{names[0]}", f"name:{name}")

        # Group emails by their root
        groups: dict[str, list[str]] = {}
        for r in rows:
            email = r["email"]
            root = find(f"email:{email}")
            groups.setdefault(root, []).append(email)

        # Deduplicate emails per group
        unique_groups: dict[str, set[str]] = {}
        for root, emails in groups.items():
            unique_groups.setdefault(root, set()).update(emails)

        # For each group, find the most common display name
        email_to_canonical: dict[str, str] = {}
        for root, emails in unique_groups.items():
            # Count name usage across all emails in the group
            name_counts: dict[str, int] = {}
            for r in rows:
                if r["email"] in emails:
                    name_counts[r["author"]] = name_counts.get(r["author"], 0) + r["cnt"]
            # Pick the most common name
            canonical = max(name_counts, key=lambda n: name_counts[n]) if name_counts else "unknown"
            for email in emails:
                email_to_canonical[email] = canonical

        return email_to_canonical

    def _populate_author_identity_table(self, identity_map: dict[str, str]) -> None:
        """Populate the _author_identity table with resolved identities.

        Creates or replaces the table with email → canonical_name mapping.
        """
        self.conn.execute("DROP TABLE IF EXISTS _author_identity")
        self.conn.execute(
            "CREATE TABLE _author_identity (email TEXT PRIMARY KEY, canonical_name TEXT NOT NULL)"
        )
        self.conn.executemany(
            "INSERT INTO _author_identity (email, canonical_name) VALUES (?, ?)",
            list(identity_map.items()),
        )
        self.conn.commit()

    def rebuild_author_identities(self) -> int:
        """Resolve and store author identity mapping.

        Merges automatic resolution (transitive by name+email) with manual
        aliases from the author_aliases table. Manual aliases take precedence.

        Returns the number of unique author identities.
        """
        # Step 1: Automatic resolution
        identity_map = self.resolve_author_identities()

        # Step 2: Apply manual aliases on top (these override automatic)
        manual = self.conn.execute(
            "SELECT email, canonical_name FROM author_aliases"
        ).fetchall()
        manual_names = {r["email"]: r["canonical_name"] for r in manual}

        # For each manual alias, update that email AND all emails that were
        # in the same auto-resolved group
        for email, canonical in manual_names.items():
            # Find the auto-resolved name for this email
            auto_name = identity_map.get(email)
            if auto_name:
                # Override all emails that shared this auto name
                for e, n in identity_map.items():
                    if n == auto_name:
                        identity_map[e] = canonical
            identity_map[email] = canonical

        self._populate_author_identity_table(identity_map)
        unique_names = len(set(identity_map.values()))
        return unique_names

    # --- Author alias management ---

    def get_author_aliases(self) -> list[dict]:
        """Get all manual author aliases.

        Returns:
            List of dicts with email and canonical_name.
        """
        rows = self.conn.execute(
            "SELECT email, canonical_name FROM author_aliases ORDER BY canonical_name, email"
        ).fetchall()
        return [dict(r) for r in rows]

    def set_author_alias(self, email: str, canonical_name: str) -> None:
        """Set or update a manual author alias.

        Args:
            email: The email to alias.
            canonical_name: The canonical display name.
        """
        self.conn.execute(
            "INSERT OR REPLACE INTO author_aliases (email, canonical_name) VALUES (?, ?)",
            (email, canonical_name),
        )
        self.conn.commit()

    def remove_author_alias(self, email: str) -> None:
        """Remove a manual author alias.

        Args:
            email: The email to remove the alias for.
        """
        self.conn.execute("DELETE FROM author_aliases WHERE email = ?", (email,))
        self.conn.commit()

    def suggest_alias_merges(self) -> list[dict]:
        """Suggest identity groups that might be the same person.

        Uses fuzzy matching: one name is a substring of another, or they
        share a word (first/last name). Only suggests across groups that
        aren't already merged.

        Returns:
            List of dicts with 'name_a', 'emails_a', 'name_b', 'emails_b'.
        """
        groups = self.get_identity_groups()
        suggestions: list[dict] = []
        seen: set[tuple[str, str]] = set()

        for i, a in enumerate(groups):
            for b in groups[i + 1:]:
                na = a["canonical_name"].lower()
                nb = b["canonical_name"].lower()
                key = (min(na, nb), max(na, nb))
                if key in seen:
                    continue

                # Check: one name contains the other
                match = na in nb or nb in na
                # Check: share a word (at least 3 chars to avoid 'a', 'de', etc.)
                if not match:
                    words_a = {w for w in na.split() if len(w) >= 3}
                    words_b = {w for w in nb.split() if len(w) >= 3}
                    match = bool(words_a & words_b)

                if match:
                    seen.add(key)
                    # Suggest merging smaller group into larger
                    if len(a["emails"]) >= len(b["emails"]):
                        target, source = a, b
                    else:
                        target, source = b, a
                    suggestions.append({
                        "target_name": target["canonical_name"],
                        "target_emails": target["emails"],
                        "source_name": source["canonical_name"],
                        "source_emails": source["emails"],
                    })

        return suggestions

    def apply_suggested_merges(self, suggestions: list[dict]) -> int:
        """Apply a list of merge suggestions as manual aliases.

        Args:
            suggestions: List from suggest_alias_merges.

        Returns:
            Number of aliases created.
        """
        count = 0
        for s in suggestions:
            target_name = s["target_name"]
            for email in s["source_emails"]:
                self.set_author_alias(email, target_name)
                count += 1
        return count

    def get_identity_groups(self) -> list[dict]:
        """Get the current author identity groups for display.

        Returns a list of groups, each with canonical_name and list of emails.
        Uses _author_identity if available, falls back to resolve.
        """
        try:
            rows = self.conn.execute(
                "SELECT email, canonical_name FROM _author_identity ORDER BY canonical_name, email"
            ).fetchall()
        except Exception:
            identity_map = self.resolve_author_identities()
            rows = [{"email": e, "canonical_name": n} for e, n in identity_map.items()]

        from collections import defaultdict
        groups: dict[str, list[str]] = defaultdict(list)
        for r in rows:
            groups[r["canonical_name"]].append(r["email"])

        return [
            {"canonical_name": name, "emails": sorted(emails)}
            for name, emails in sorted(groups.items())
        ]

    @staticmethod
    def loc_expr(mode: str = "both") -> str:
        """SQL expression for lines of code based on mode.

        Args:
            mode: "added" for additions only, "both" for additions + deletions.
        """
        if mode == "added":
            return "COALESCE(additions, 0)"
        return "COALESCE(additions, 0) + COALESCE(deletions, 0)"

    def _build_filter(
        self,
        org: str | None = None,
        repo: str | None = None,
        author: str | None = None,
        month: str | None = None,
        week: str | None = None,
    ) -> tuple[str, tuple]:
        """Build a WHERE clause with optional filters.

        Always excludes merge commits, reverts, and conflict resolutions.
        """
        clauses = [
            "message NOT LIKE 'Merge %'",
            "message NOT LIKE 'Revert %'",
            "message NOT LIKE 'Resolve conflict%'",
            "message NOT LIKE '%merge conflict%'",
        ]
        params: list = []

        if org:
            clauses.append("org = ?")
            params.append(org)
        if repo:
            clauses.append("repo = ?")
            params.append(repo)
        if author:
            try:
                self.conn.execute("SELECT 1 FROM _author_identity LIMIT 1")
                clauses.append(
                    "commits.email IN (SELECT email FROM _author_identity WHERE canonical_name = ?)"
                )
            except Exception:
                clauses.append(
                    "commits.email IN (SELECT DISTINCT email FROM commits c2 WHERE c2.author = ?)"
                )
            params.append(author)
        if month:
            clauses.append("strftime('%Y-%m', date) = ?")
            params.append(month)
        if week:
            clauses.append("strftime('%Y-W%W', date) = ?")
            params.append(week)

        return (" AND ".join(clauses), tuple(params))

    # Keep backward-compatible shortcut
    def _org_filter(self, org: str | None = None) -> tuple[str, tuple]:
        """Shortcut for _build_filter with just org."""
        return self._build_filter(org=org)

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

    def query_summary(self, org: str | None = None, filters: QueryFilters | None = None) -> dict:
        """Get summary statistics."""
        f = filters or QueryFilters(org=org)
        where, params = self._build_filter(org=f.org, repo=f.repo, author=f.author, month=f.month, week=f.week)
        loc = self.loc_expr(f.loc_mode)
        row = self.conn.execute(
            f"""
            SELECT
                COUNT(*) AS total_commits,
                SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN 1 ELSE 0 END) AS ai_commits,
                COALESCE(SUM({loc}), 0) AS total_loc,
                COALESCE(SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN {loc} ELSE 0 END), 0) AS ai_loc
            FROM commits
            WHERE {where}
        """,
            params,
        ).fetchone()
        return dict(row)

    def query_by_tool(self, org: str | None = None, filters: QueryFilters | None = None) -> list[dict]:
        """Get commit counts grouped by AI tool."""
        f = filters or QueryFilters(org=org)
        where, params = self._build_filter(org=f.org, repo=f.repo, author=f.author, month=f.month, week=f.week)
        loc = self.loc_expr(f.loc_mode)
        rows = self.conn.execute(
            f"""
            SELECT
                ai_tool AS tool,
                COUNT(*) AS commits,
                COALESCE(SUM({loc}), 0) AS loc
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
        filters: QueryFilters | None = None,
    ) -> list[dict]:
        """Get rankings by author or repo."""
        if group_by not in ("author", "repo"):
            raise ValueError(f"Invalid group_by: {group_by}")
        if order_by not in ("ai_commits", "total_commits", "ai_loc", "total_loc"):
            raise ValueError(f"Invalid order_by: {order_by}")

        f = filters or QueryFilters(org=org)
        where, params = self._build_filter(org=f.org, repo=f.repo, author=f.author, month=f.month, week=f.week)
        loc = self.loc_expr(f.loc_mode)
        direction = "ASC" if ascending else "DESC"

        if group_by == "author":
            # Use the pre-computed _author_identity table from detection step.
            # Falls back to email grouping if table doesn't exist yet.
            try:
                self.conn.execute("SELECT 1 FROM _author_identity LIMIT 1")
                has_identity = True
            except Exception:
                has_identity = False

            if has_identity:
                name_expr = "COALESCE(aid.canonical_name, commits.author) AS author"
                from_clause = "FROM commits LEFT JOIN _author_identity aid ON commits.email = aid.email"
                group_col = "COALESCE(aid.canonical_name, commits.author)"
            else:
                name_expr = "commits.author AS author"
                from_clause = "FROM commits"
                group_col = "commits.email"
        else:
            name_expr = group_by
            from_clause = "FROM commits"
            group_col = group_by

        rows = self.conn.execute(
            f"""
            SELECT
                {name_expr},
                COUNT(*) AS total_commits,
                SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN 1 ELSE 0 END) AS ai_commits,
                COALESCE(SUM({loc}), 0) AS total_loc,
                COALESCE(SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN {loc} ELSE 0 END), 0) AS ai_loc
            {from_clause}
            WHERE {where}
            GROUP BY {group_col}
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
        filters: QueryFilters | None = None,
    ) -> list[dict]:
        """Get commit trends over time."""
        f = filters or QueryFilters(org=org)
        where, params = self._build_filter(org=f.org, repo=f.repo, author=f.author, month=f.month, week=f.week)
        loc = self.loc_expr(f.loc_mode)
        period_expr = "strftime('%Y-W%W', date)" if period == "weekly" else "strftime('%Y-%m', date)"

        rows = self.conn.execute(
            f"""
            SELECT
                {period_expr} AS period,
                COUNT(*) AS total,
                SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN 1 ELSE 0 END) AS ai,
                COALESCE(SUM({loc}), 0) AS total_loc,
                COALESCE(SUM(CASE WHEN ai_tool IS NOT NULL AND ai_tool != '' THEN {loc} ELSE 0 END), 0) AS ai_loc
            FROM commits
            WHERE {where}
            GROUP BY period
            ORDER BY period
        """,
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def query_skynet_employee(self, org: str | None = None, filters: QueryFilters | None = None) -> dict | None:
        """Get the author with the most AI commits in the last 7 days."""
        f = filters or QueryFilters(org=org)
        where, params = self._build_filter(org=f.org, repo=f.repo, author=f.author, month=f.month, week=f.week)
        try:
            self.conn.execute("SELECT 1 FROM _author_identity LIMIT 1")
            name_expr = "COALESCE(aid.canonical_name, commits.author)"
            join = "LEFT JOIN _author_identity aid ON commits.email = aid.email"
            group = "COALESCE(aid.canonical_name, commits.author)"
        except Exception:
            name_expr = "commits.author"
            join = ""
            group = "commits.email"

        row = self.conn.execute(
            f"""
            SELECT
                {name_expr} AS author,
                COUNT(*) AS ai_commits
            FROM commits {join}
            WHERE ai_tool IS NOT NULL AND ai_tool != ''
              AND date >= date('now', '-7 days')
              AND {where}
            GROUP BY {group}
            ORDER BY ai_commits DESC
            LIMIT 1
        """,
            params,
        ).fetchone()
        return dict(row) if row else None

    def query_commits_by(
        self,
        group_by: str,
        value: str,
        org: str | None = None,
        limit: int = 5000,
    ) -> list[dict]:
        """Get individual commits for a specific author (by email) or repo.

        Args:
            group_by: "author" or "repo".
            value: The author name or repo name to filter by.
            org: Optional org filter.
            limit: Max results.

        Returns:
            List of commit dicts with url, message excerpt, stats, ai info.
        """
        org_where, org_params = self._org_filter(org)

        if group_by == "author":
            # Value is the canonical name — look up all emails in the identity group
            try:
                self.conn.execute("SELECT 1 FROM _author_identity LIMIT 1")
                filter_clause = (
                    "email IN (SELECT email FROM _author_identity WHERE canonical_name = ?)"
                )
            except Exception:
                filter_clause = (
                    "email IN (SELECT DISTINCT email FROM commits WHERE author = ?)"
                )
            filter_params = (value,)
        elif group_by == "repo":
            filter_clause = "repo = ?"
            filter_params = (value,)
        else:
            return []

        rows = self.conn.execute(
            f"""
            SELECT sha, org, repo, author, email, date,
                   COALESCE(additions, 0) as additions,
                   COALESCE(deletions, 0) as deletions,
                   substr(message, 1, 120) as message,
                   ai_tool, pr_number
            FROM commits
            WHERE {org_where} AND {filter_clause}
            ORDER BY date DESC
            LIMIT ?
            """,
            (*org_params, *filter_params, limit),
        ).fetchall()
        return [dict(r) for r in rows]

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
        in_production: bool = False,
        pr_number: int | None = None,
        pr_state: str | None = None,
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
            in_production: True if the PR was merged to production.
            pr_number: PR number this commit belongs to.
            pr_state: PR state — "merged", "open", or "closed".

        Returns:
            True if inserted (new), False if duplicate.
        """
        try:
            self.conn.execute(
                """INSERT INTO commits
                   (sha, org, repo, author, email, date, message,
                    in_production, pr_number, pr_state, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sha, org, repo, author, email, date, message,
                    1 if in_production else 0, pr_number, pr_state,
                    self._utc_now(),
                ),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            # Commit already exists — but if this PR is merged to main,
            # promote in_production to 1 (a commit can flow through
            # uat → preprod → main across multiple PRs)
            if in_production:
                self.conn.execute(
                    "UPDATE commits SET in_production = 1 WHERE sha = ?",
                    (sha,),
                )
                self.conn.commit()
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
        """Get commits that need enrichment (no additions data yet).

        Skips merge/revert/conflict commits since they're excluded from stats.
        """
        rows = self.conn.execute(
            "SELECT sha, org, repo FROM commits "
            "WHERE additions IS NULL "
            "AND message NOT LIKE 'Merge %' "
            "AND message NOT LIKE 'Revert %' "
            "AND message NOT LIKE 'Resolve conflict%' "
            "AND message NOT LIKE '%merge conflict%' "
            "ORDER BY date LIMIT ?",
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

    def get_repo_last_synced(self, org: str, repo: str) -> str | None:
        """Get the timestamp of when this repo was last fetched.

        Args:
            org: Organization name.
            repo: Repository name.

        Returns:
            Last synced timestamp, or None.
        """
        row = self.conn.execute(
            "SELECT last_synced_at FROM repo_sync WHERE org = ? AND repo = ?",
            (org, repo),
        ).fetchone()
        return row["last_synced_at"] if row else None

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
