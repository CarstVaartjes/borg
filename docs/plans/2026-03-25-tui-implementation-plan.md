# Borg TUI Rewrite — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Rewrite borg from bash to Python as a full interactive TUI using Textual + Plotext, with all functionality (org management, fetching, detection, reporting) inside the TUI.

**Architecture:** Python package with `typer` entry point launching a `textual` app. SQLite via stdlib `sqlite3`, GitHub API via `httpx` reading auth from `gh auth token`. Same schema as the bash version. TDD with pytest.

**Tech Stack:** Python 3.11+, textual, textual-plotext, typer, httpx, uv

---

### Task 1: Project scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `src/borg/__init__.py`
- Create: `src/borg/cli.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Step 1: Create pyproject.toml**

```toml
[project]
name = "borg-tracker"
version = "0.1.0"
description = "AI commit adoption tracker — Resistance is futile"
requires-python = ">=3.11"
dependencies = [
    "textual>=3.0",
    "textual-plotext>=0.5",
    "typer>=0.15",
    "httpx>=0.28",
]

[project.scripts]
borg = "borg.cli:main"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/borg"]

[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"

[dependency-groups]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.25",
]
```

**Step 2: Create src/borg/__init__.py**

```python
"""Borg — AI commit adoption tracker."""
```

**Step 3: Create minimal cli.py entry point**

```python
"""CLI entry point — launches the TUI."""
import typer
from pathlib import Path

app = typer.Typer(add_completion=False)

DEFAULT_DB = Path.home() / ".local" / "share" / "borg" / "tracker.db"


@app.command()
def main(
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Borg — AI commit adoption tracker. Resistance is futile."""
    # TUI launch will go here
    print(f"Borg TUI starting with db: {db}")


if __name__ == "__main__":
    app()
```

**Step 4: Create test scaffolding**

`tests/__init__.py`: empty file

`tests/conftest.py`:
```python
"""Shared test fixtures."""
import sqlite3
import tempfile
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Provide a temporary database path."""
    return tmp_path / "test.db"
```

**Step 5: Install and verify**

Run: `uv sync && uv run borg --help`
Expected: Shows help with `--db` option

Run: `uv run pytest -v`
Expected: No tests collected (0 collected), no errors

**Step 6: Commit**

```bash
git add pyproject.toml src/ tests/ uv.lock
git commit -m "Project scaffolding with uv, typer, and test setup"
```

---

### Task 2: Database layer

**Files:**
- Create: `src/borg/db.py`
- Create: `tests/test_db.py`

**Step 1: Write failing tests for db layer**

```python
"""Tests for the database layer."""
import sqlite3
from pathlib import Path

from borg.db import Database


class TestDatabaseInit:
    def test_creates_db_file(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        assert tmp_db.exists()

    def test_creates_tables(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        conn = sqlite3.connect(tmp_db)
        tables = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;"
        ).fetchall()
        table_names = [t[0] for t in tables]
        assert "orgs" in table_names
        assert "commits" in table_names
        assert "repo_sync" in table_names
        assert "sync_meta" in table_names
        conn.close()

    def test_creates_parent_directory(self, tmp_path: Path) -> None:
        db_path = tmp_path / "subdir" / "deep" / "test.db"
        db = Database(db_path)
        assert db_path.exists()


class TestOrgCRUD:
    def test_add_org(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("myorg", "2026-01-01")
        orgs = db.org_list()
        assert len(orgs) == 1
        assert orgs[0]["name"] == "myorg"
        assert orgs[0]["since_date"] == "2026-01-01"

    def test_add_duplicate_org_raises(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("myorg", "2026-01-01")
        with pytest.raises(ValueError, match="already exists"):
            db.org_add("myorg", "2026-02-01")

    def test_remove_org(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("myorg", "2026-01-01")
        db.org_remove("myorg")
        assert db.org_list() == []

    def test_remove_nonexistent_org_raises(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        with pytest.raises(ValueError, match="not found"):
            db.org_remove("ghost")

    def test_remove_org_deletes_commits_and_sync(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("myorg", "2026-01-01")
        # Insert a commit and repo_sync row directly
        db._conn.execute(
            "INSERT INTO commits (sha, org, repo, author, email, date, fetched_at) "
            "VALUES ('abc123', 'myorg', 'repo1', 'author', 'e@mail', '2026-01-15', '2026-01-16')"
        )
        db._conn.execute(
            "INSERT INTO repo_sync (org, repo, commit_count) "
            "VALUES ('myorg', 'repo1', 1)"
        )
        db._conn.commit()
        db.org_remove("myorg")
        count = db._conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        assert count == 0

    def test_org_get_all(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("alpha", "2026-01-01")
        db.org_add("beta", "2026-02-01")
        orgs = db.org_get_all()
        assert len(orgs) == 2
        assert orgs[0]["name"] == "alpha"
        assert orgs[1]["name"] == "beta"

    def test_org_get(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("myorg", "2026-01-01")
        org = db.org_get("myorg")
        assert org is not None
        assert org["name"] == "myorg"

    def test_org_get_missing_returns_none(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        assert db.org_get("ghost") is None

    def test_org_list_empty(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        assert db.org_list() == []


class TestMeta:
    def test_set_and_get_meta(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.set_meta("last_run", "2026-03-25T10:00:00Z")
        assert db.get_meta("last_run") == "2026-03-25T10:00:00Z"

    def test_get_missing_meta_returns_none(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        assert db.get_meta("nonexistent") is None

    def test_set_meta_overwrites(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.set_meta("key", "old")
        db.set_meta("key", "new")
        assert db.get_meta("key") == "new"


class TestReportQueries:
    def _seed_commits(self, db: Database) -> None:
        """Insert test commits for report queries."""
        commits = [
            ("sha1", "org1", "repo1", "alice", "a@e", "2026-01-15T10:00:00Z", 100, 10, "msg", "claude", "high"),
            ("sha2", "org1", "repo1", "alice", "a@e", "2026-01-20T10:00:00Z", 50, 5, "msg", None, None),
            ("sha3", "org1", "repo2", "bob", "b@e", "2026-02-10T10:00:00Z", 200, 20, "msg", "copilot", "high"),
            ("sha4", "org2", "repo3", "carol", "c@e", "2026-02-15T10:00:00Z", 300, 30, "msg", "claude", "high"),
        ]
        for c in commits:
            db._conn.execute(
                "INSERT INTO commits (sha, org, repo, author, email, date, additions, deletions, message, ai_tool, ai_confidence, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '2026-03-01')",
                c,
            )
        db._conn.commit()

    def test_summary_all_orgs(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        self._seed_commits(db)
        s = db.query_summary()
        assert s["total_commits"] == 4
        assert s["ai_commits"] == 3
        assert s["total_loc"] == 715  # (100+10)+(50+5)+(200+20)+(300+30)
        assert s["ai_loc"] == 660    # (100+10)+(200+20)+(300+30)

    def test_summary_filtered_by_org(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        self._seed_commits(db)
        s = db.query_summary(org="org1")
        assert s["total_commits"] == 3
        assert s["ai_commits"] == 2

    def test_tool_breakdown(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        self._seed_commits(db)
        tools = db.query_by_tool()
        tool_names = [t["tool"] for t in tools]
        assert "claude" in tool_names
        assert "copilot" in tool_names

    def test_rankings(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        self._seed_commits(db)
        rows = db.query_rankings("author", limit=10, min_commits=0)
        assert len(rows) > 0
        assert "name" in rows[0]
        assert "ai_commits" in rows[0]

    def test_trends(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        self._seed_commits(db)
        rows = db.query_trends("monthly")
        assert len(rows) >= 1
        assert "period" in rows[0]
        assert "total" in rows[0]
        assert "ai" in rows[0]

    def test_export_csv(self, tmp_db: Path, tmp_path: Path) -> None:
        db = Database(tmp_db)
        self._seed_commits(db)
        csv_path = tmp_path / "export.csv"
        db.export_csv(csv_path)
        content = csv_path.read_text()
        assert "sha1" in content
        assert "org" in content  # header includes org column
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -v`
Expected: All FAIL (ImportError — borg.db doesn't exist)

**Step 3: Implement db.py**

```python
"""SQLite database layer for borg."""
from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Database:
    """SQLite database for tracking AI commit adoption."""

    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript("""
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

    def close(self) -> None:
        self._conn.close()

    def _utc_now(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # --- Org CRUD ---

    def org_add(self, name: str, since_date: str) -> None:
        existing = self._conn.execute(
            "SELECT 1 FROM orgs WHERE name = ?", (name,)
        ).fetchone()
        if existing:
            raise ValueError(f"Org '{name}' already exists")
        self._conn.execute(
            "INSERT INTO orgs (name, since_date, added_at) VALUES (?, ?, ?)",
            (name, since_date, self._utc_now()),
        )
        self._conn.commit()

    def org_remove(self, name: str) -> None:
        existing = self._conn.execute(
            "SELECT 1 FROM orgs WHERE name = ?", (name,)
        ).fetchone()
        if not existing:
            raise ValueError(f"Org '{name}' not found")
        self._conn.execute("DELETE FROM commits WHERE org = ?", (name,))
        self._conn.execute("DELETE FROM repo_sync WHERE org = ?", (name,))
        self._conn.execute("DELETE FROM orgs WHERE name = ?", (name,))
        self._conn.commit()

    def org_list(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT o.name, o.since_date, o.added_at, "
            "COALESCE((SELECT COUNT(*) FROM commits c WHERE c.org = o.name), 0) as commit_count "
            "FROM orgs o ORDER BY o.name"
        ).fetchall()
        return [dict(r) for r in rows]

    def org_get_all(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT name, since_date FROM orgs ORDER BY name"
        ).fetchall()
        return [dict(r) for r in rows]

    def org_get(self, name: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT name, since_date FROM orgs WHERE name = ?", (name,)
        ).fetchone()
        return dict(row) if row else None

    # --- Meta ---

    def get_meta(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT value FROM sync_meta WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO sync_meta (key, value) VALUES (?, ?)",
            (key, value),
        )
        self._conn.commit()

    # --- Report Queries ---

    def _org_filter(self, org: str | None) -> tuple[str, tuple]:
        if org:
            return "org = ?", (org,)
        return "1=1", ()

    def query_summary(self, org: str | None = None) -> dict[str, int]:
        where, params = self._org_filter(org)
        loc = "COALESCE(additions,0) + COALESCE(deletions,0)"
        row = self._conn.execute(
            f"SELECT COUNT(*) as total_commits, "
            f"SUM(CASE WHEN ai_confidence = 'high' THEN 1 ELSE 0 END) as ai_commits, "
            f"COALESCE(SUM({loc}), 0) as total_loc, "
            f"COALESCE(SUM(CASE WHEN ai_confidence = 'high' THEN {loc} ELSE 0 END), 0) as ai_loc "
            f"FROM commits WHERE {where}",
            params,
        ).fetchone()
        return dict(row)

    def query_by_tool(self, org: str | None = None) -> list[dict[str, Any]]:
        where, params = self._org_filter(org)
        loc = "COALESCE(additions,0) + COALESCE(deletions,0)"
        rows = self._conn.execute(
            f"SELECT ai_tool as tool, COUNT(*) as commits, "
            f"SUM({loc}) as loc "
            f"FROM commits WHERE {where} AND ai_confidence = 'high' "
            f"GROUP BY ai_tool ORDER BY commits DESC",
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
    ) -> list[dict[str, Any]]:
        where, params = self._org_filter(org)
        loc = "COALESCE(additions,0) + COALESCE(deletions,0)"
        direction = "ASC" if ascending else "DESC"
        rows = self._conn.execute(
            f"SELECT {group_by} as name, "
            f"SUM(CASE WHEN ai_confidence = 'high' THEN 1 ELSE 0 END) as ai_commits, "
            f"COUNT(*) as total_commits, "
            f"SUM(CASE WHEN ai_confidence = 'high' THEN {loc} ELSE 0 END) as ai_loc, "
            f"SUM({loc}) as total_loc "
            f"FROM commits WHERE {where} "
            f"GROUP BY {group_by} HAVING COUNT(*) > ? "
            f"ORDER BY {order_by} {direction} LIMIT ?",
            (*params, min_commits, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    def query_trends(
        self, period: str = "monthly", org: str | None = None
    ) -> list[dict[str, Any]]:
        where, params = self._org_filter(org)
        loc = "COALESCE(additions,0) + COALESCE(deletions,0)"
        fmt = "%Y-%m" if period == "monthly" else "%Y-W%W"
        rows = self._conn.execute(
            f"SELECT strftime('{fmt}', date) as period, "
            f"COUNT(*) as total, "
            f"SUM(CASE WHEN ai_confidence = 'high' THEN 1 ELSE 0 END) as ai, "
            f"SUM({loc}) as total_loc, "
            f"SUM(CASE WHEN ai_confidence = 'high' THEN {loc} ELSE 0 END) as ai_loc "
            f"FROM commits WHERE {where} "
            f"GROUP BY period ORDER BY period",
            params,
        ).fetchall()
        return [dict(r) for r in rows]

    def query_skynet_employee(self, org: str | None = None) -> dict[str, Any] | None:
        """Author with most AI commits in the last 7 days."""
        where, params = self._org_filter(org)
        row = self._conn.execute(
            f"SELECT author as name, COUNT(*) as ai_commits "
            f"FROM commits "
            f"WHERE {where} AND ai_confidence = 'high' "
            f"AND date >= datetime('now', '-7 days') "
            f"GROUP BY author ORDER BY ai_commits DESC LIMIT 1",
            params,
        ).fetchone()
        return dict(row) if row else None

    def export_csv(self, path: Path, org: str | None = None) -> int:
        where, params = self._org_filter(org)
        loc = "COALESCE(additions,0) + COALESCE(deletions,0)"
        rows = self._conn.execute(
            f"SELECT sha, org, repo, author, email, date, additions, deletions, "
            f"({loc}) as loc_changed, message, ai_tool, ai_confidence "
            f"FROM commits WHERE {where} ORDER BY date",
            params,
        ).fetchall()
        with open(path, "w", newline="") as f:
            writer = csv.writer(f)
            if rows:
                writer.writerow(rows[0].keys())
                writer.writerows(rows)
        return len(rows)

    # --- Commit insertion (used by fetch) ---

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
        """Insert a commit. Returns True if new (not duplicate)."""
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO commits "
                "(sha, org, repo, author, email, date, message, fetched_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (sha, org, repo, author, email, date, message, self._utc_now()),
            )
            inserted = self._conn.execute("SELECT changes()").fetchone()[0]
            self._conn.commit()
            return inserted > 0
        except sqlite3.Error:
            return False

    def update_commit_stats(self, sha: str, additions: int, deletions: int) -> None:
        self._conn.execute(
            "UPDATE commits SET additions = ?, deletions = ? WHERE sha = ?",
            (additions, deletions, sha),
        )
        self._conn.commit()

    def get_unenriched_commits(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT sha, org, repo FROM commits WHERE additions IS NULL LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    def update_repo_sync(
        self, org: str, repo: str, last_commit_date: str | None, commit_count: int
    ) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO repo_sync (org, repo, last_commit_date, last_synced_at, commit_count) "
            "VALUES (?, ?, ?, ?, ?)",
            (org, repo, last_commit_date, self._utc_now(), commit_count),
        )
        self._conn.commit()

    def get_repo_bookmark(self, org: str, repo: str) -> str | None:
        row = self._conn.execute(
            "SELECT last_commit_date FROM repo_sync WHERE org = ? AND repo = ?",
            (org, repo),
        ).fetchone()
        return row["last_commit_date"] if row else None

    def get_repo_commit_count(self, org: str, repo: str) -> int:
        row = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM commits WHERE org = ? AND repo = ?",
            (org, repo),
        ).fetchone()
        return row["cnt"]
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_db.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/borg/db.py tests/test_db.py
git commit -m "Implement database layer with org CRUD and report queries"
```

---

### Task 3: AI detection

**Files:**
- Create: `src/borg/detect.py`
- Create: `tests/test_detect.py`

**Step 1: Write failing tests**

```python
"""Tests for AI detection."""
from pathlib import Path

from borg.db import Database
from borg.detect import detect_ai


def _insert_commit(db: Database, sha: str, message: str, author: str = "dev", email: str = "d@e") -> None:
    db._conn.execute(
        "INSERT INTO commits (sha, org, repo, author, email, date, message, additions, deletions, fetched_at) "
        "VALUES (?, 'org1', 'repo1', ?, ?, '2026-01-15', ?, 100, 10, '2026-01-16')",
        (sha, author, email, message),
    )
    db._conn.commit()


class TestDetection:
    def test_detects_claude(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        _insert_commit(db, "sha1", "feat: add feature\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
        detect_ai(db)
        row = db._conn.execute("SELECT ai_tool, ai_confidence FROM commits WHERE sha = 'sha1'").fetchone()
        assert row["ai_tool"] == "claude"
        assert row["ai_confidence"] == "high"

    def test_detects_copilot_bot(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        _insert_commit(db, "sha2", "feat: stuff", author="copilot[bot]")
        detect_ai(db)
        row = db._conn.execute("SELECT ai_tool FROM commits WHERE sha = 'sha2'").fetchone()
        assert row["ai_tool"] == "copilot"

    def test_detects_aider(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        _insert_commit(db, "sha3", "feat: stuff", author="dev (aider)")
        detect_ai(db)
        row = db._conn.execute("SELECT ai_tool FROM commits WHERE sha = 'sha3'").fetchone()
        assert row["ai_tool"] == "aider"

    def test_no_detection_for_normal_commit(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        _insert_commit(db, "sha4", "feat: normal commit by human")
        detect_ai(db)
        row = db._conn.execute("SELECT ai_tool FROM commits WHERE sha = 'sha4'").fetchone()
        assert row["ai_tool"] is None

    def test_bulk_heuristic(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db._conn.execute(
            "INSERT INTO commits (sha, org, repo, author, email, date, message, additions, deletions, fetched_at) "
            "VALUES ('sha5', 'org1', 'repo1', 'dev', 'd@e', '2026-01-15', 'add big file', 500, 2, '2026-01-16')"
        )
        db._conn.commit()
        detect_ai(db)
        row = db._conn.execute("SELECT ai_tool, ai_confidence FROM commits WHERE sha = 'sha5'").fetchone()
        assert row["ai_tool"] == "unknown"
        assert row["ai_confidence"] == "low"

    def test_redetection_clears_old_results(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        _insert_commit(db, "sha6", "feat: stuff")
        db._conn.execute("UPDATE commits SET ai_tool = 'old', ai_confidence = 'high' WHERE sha = 'sha6'")
        db._conn.commit()
        detect_ai(db)
        row = db._conn.execute("SELECT ai_tool FROM commits WHERE sha = 'sha6'").fetchone()
        assert row["ai_tool"] is None  # normal commit, no detection

    def test_devin_requires_bot_author(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        _insert_commit(db, "sha7", "Co-Authored-By: Devin Smith <devin@company.com>")
        detect_ai(db)
        row = db._conn.execute("SELECT ai_tool FROM commits WHERE sha = 'sha7'").fetchone()
        assert row["ai_tool"] is None  # human named Devin, not the AI
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_detect.py -v`
Expected: All FAIL

**Step 3: Implement detect.py**

```python
"""AI detection for borg — trailer-based pattern matching."""
from __future__ import annotations

from borg.db import Database

# Detection rules: (tool_name, confidence, SQL WHERE clause)
# Order matters — first match wins via WHERE ai_tool IS NULL
RULES: list[tuple[str, str, str]] = [
    ("claude", "high",
     "message LIKE '%Co-Authored-By:%Claude%' OR message LIKE '%noreply@anthropic.com%'"),
    ("copilot", "high",
     "message LIKE '%Co-Authored-By:%Copilot%' OR author = 'copilot[bot]' OR email LIKE '%copilot%'"),
    ("cursor", "high",
     "message LIKE '%Co-Authored-By:%Cursor%' OR message LIKE '%noreply@cursor.com%'"),
    ("aider", "high",
     "author LIKE '%(aider)%'"),
    ("chatgpt", "high",
     "message LIKE '%Co-Authored-By:%ChatGPT%' OR message LIKE '%Co-Authored-By:%OpenAI%'"),
    ("devin", "high",
     "author = 'devin-ai[bot]' OR email LIKE '%devin-ai%' OR message LIKE '%Co-Authored-By:%devin-ai[bot]%'"),
    ("cody", "high",
     "message LIKE '%Co-Authored-By:%Cody%sourcegraph%' OR message LIKE '%noreply@sourcegraph.com%'"),
    ("amazon-q", "high",
     "message LIKE '%Co-Authored-By:%Amazon Q%'"),
    ("windsurf", "high",
     "message LIKE '%Co-Authored-By:%Windsurf%'"),
    ("codeium", "high",
     "message LIKE '%Co-Authored-By:%Codeium%'"),
    ("tabnine", "high",
     "message LIKE '%Co-Authored-By:%Tabnine%'"),
]

BULK_HEURISTIC = (
    "unknown", "low",
    "additions > 100 AND deletions < 10 AND additions IS NOT NULL"
)


def detect_ai(db: Database) -> dict[str, int]:
    """Run AI detection on all commits. Returns counts by confidence level."""
    conn = db._conn
    conn.execute("BEGIN TRANSACTION")
    try:
        # Reset all detection
        conn.execute("UPDATE commits SET ai_tool = NULL, ai_confidence = NULL")

        # Apply rules in order (first match wins)
        for tool, confidence, where in RULES:
            conn.execute(
                f"UPDATE commits SET ai_tool = ?, ai_confidence = ? "
                f"WHERE ai_tool IS NULL AND ({where})",
                (tool, confidence),
            )

        # Bulk heuristic last
        tool, confidence, where = BULK_HEURISTIC
        conn.execute(
            f"UPDATE commits SET ai_tool = ?, ai_confidence = ? "
            f"WHERE ai_tool IS NULL AND ({where})",
            (tool, confidence),
        )

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    high = conn.execute("SELECT COUNT(*) FROM commits WHERE ai_confidence = 'high'").fetchone()[0]
    low = conn.execute("SELECT COUNT(*) FROM commits WHERE ai_confidence = 'low'").fetchone()[0]
    total = conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
    return {"high": high, "low": low, "total": total}
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_detect.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/borg/detect.py tests/test_detect.py
git commit -m "Implement AI detection with data-driven rules"
```

---

### Task 4: GitHub fetch layer

**Files:**
- Create: `src/borg/fetch.py`
- Create: `tests/test_fetch.py`

**Step 1: Write tests (mocked HTTP)**

```python
"""Tests for the GitHub fetch layer."""
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

from borg.db import Database
from borg.fetch import GitHubFetcher


class TestGitHubFetcher:
    def test_init_reads_token(self, tmp_db: Path) -> None:
        with patch("borg.fetch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="ghp_test123\n", returncode=0)
            db = Database(tmp_db)
            fetcher = GitHubFetcher(db)
            assert fetcher._token == "ghp_test123"

    def test_init_fails_without_gh(self, tmp_db: Path) -> None:
        with patch("borg.fetch.subprocess.run") as mock_run:
            mock_run.side_effect = FileNotFoundError
            db = Database(tmp_db)
            with pytest.raises(RuntimeError, match="GitHub CLI"):
                GitHubFetcher(db)

    @pytest.mark.asyncio
    async def test_fetch_repo_list(self, tmp_db: Path) -> None:
        with patch("borg.fetch.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(stdout="token\n", returncode=0)
            db = Database(tmp_db)
            fetcher = GitHubFetcher(db)

            mock_response = AsyncMock()
            mock_response.json = AsyncMock(return_value=[
                {"name": "repo1", "archived": False},
                {"name": "repo2", "archived": True},
                {"name": "repo3", "archived": False},
            ])
            mock_response.raise_for_status = MagicMock()

            with patch.object(fetcher, "_client") as mock_client:
                mock_client.get = AsyncMock(return_value=mock_response)
                repos = await fetcher.fetch_repo_list("myorg")
                assert repos == ["repo1", "repo3"]
```

**Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_fetch.py -v`
Expected: All FAIL

**Step 3: Implement fetch.py**

```python
"""GitHub API fetching for borg — async, rate-limit aware."""
from __future__ import annotations

import asyncio
import subprocess
from dataclasses import dataclass
from typing import Any, Callable

import httpx

from borg.db import Database

API_BASE = "https://api.github.com"


@dataclass
class FetchProgress:
    """Progress update from fetch operation."""
    phase: str  # "repos", "commits", "enrich"
    org: str
    repo: str = ""
    current: int = 0
    total: int = 0
    message: str = ""


class GitHubFetcher:
    """Async GitHub API fetcher with rate limiting."""

    def __init__(self, db: Database) -> None:
        self._db = db
        self._token = self._get_token()
        self._client = httpx.AsyncClient(
            base_url=API_BASE,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )
        self._on_progress: Callable[[FetchProgress], None] | None = None

    @staticmethod
    def _get_token() -> str:
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
                check=True,
            )
            return result.stdout.strip()
        except FileNotFoundError:
            raise RuntimeError(
                "GitHub CLI (gh) not found. Install with: brew install gh"
            )
        except subprocess.CalledProcessError:
            raise RuntimeError(
                "GitHub CLI not authenticated. Run: gh auth login"
            )

    def set_progress_callback(self, callback: Callable[[FetchProgress], None]) -> None:
        self._on_progress = callback

    def _emit(self, progress: FetchProgress) -> None:
        if self._on_progress:
            self._on_progress(progress)

    async def check_rate_limit(self) -> tuple[int, int]:
        """Returns (remaining, reset_epoch)."""
        try:
            resp = await self._client.get("/rate_limit")
            data = resp.json()
            rate = data["rate"]
            return rate["remaining"], rate["reset"]
        except Exception:
            return 100, 0

    async def wait_for_rate_limit(self, min_remaining: int = 200) -> int:
        while True:
            remaining, reset_epoch = await self.check_rate_limit()
            if remaining >= min_remaining:
                return remaining
            import time
            now = int(time.time())
            wait = max(reset_epoch - now + 5, 5)
            self._emit(FetchProgress(
                phase="rate_limit", org="",
                message=f"Rate limit low ({remaining} left). Waiting {wait}s...",
            ))
            await asyncio.sleep(wait)

    async def fetch_repo_list(self, org: str) -> list[str]:
        repos = []
        page = 1
        while True:
            resp = await self._client.get(
                f"/orgs/{org}/repos",
                params={"per_page": 100, "page": page, "type": "all"},
            )
            resp.raise_for_status()
            data = resp.json()
            if not data:
                break
            repos.extend(r["name"] for r in data if not r.get("archived", False))
            if len(data) < 100:
                break
            page += 1
        return repos

    async def fetch_repo_commits(
        self, org: str, repo: str, since: str
    ) -> int:
        """Fetch commits for one repo. Returns count of new commits."""
        bookmark = self._db.get_repo_bookmark(org, repo)
        since_iso = bookmark or since
        if len(since_iso) == 10:  # YYYY-MM-DD
            since_iso += "T00:00:00Z"

        new_count = 0
        newest_date = ""
        page = 1

        while True:
            try:
                resp = await self._client.get(
                    f"/repos/{org}/{repo}/commits",
                    params={"since": since_iso, "per_page": 100, "page": page},
                )
                resp.raise_for_status()
            except httpx.HTTPError as e:
                self._emit(FetchProgress(
                    phase="commits", org=org, repo=repo,
                    message=f"Warning: failed to fetch {repo}: {e}",
                ))
                break

            commits = resp.json()
            if not commits:
                break

            for c in commits:
                sha = c.get("sha", "")
                if not sha:
                    continue
                commit_data = c.get("commit", {})
                author_data = commit_data.get("author", {})
                inserted = self._db.insert_commit(
                    sha=sha,
                    org=org,
                    repo=repo,
                    author=author_data.get("name", "unknown"),
                    email=author_data.get("email", "unknown"),
                    date=author_data.get("date", ""),
                    message=commit_data.get("message", ""),
                )
                if inserted:
                    new_count += 1
                date = author_data.get("date", "")
                if date and (not newest_date or date > newest_date):
                    newest_date = date

            if len(commits) < 100:
                break
            page += 1

        total_count = self._db.get_repo_commit_count(org, repo)
        self._db.update_repo_sync(org, repo, newest_date or None, total_count)
        return new_count

    async def enrich_commits(self) -> int:
        """Enrich unenriched commits with additions/deletions. Returns count enriched."""
        enriched = 0
        while True:
            batch = self._db.get_unenriched_commits(100)
            if not batch:
                break

            remaining = await self.wait_for_rate_limit(200)
            parallel = 8 if remaining > 500 else 4

            sem = asyncio.Semaphore(parallel)

            async def enrich_one(commit: dict) -> bool:
                async with sem:
                    try:
                        resp = await self._client.get(
                            f"/repos/{commit['org']}/{commit['repo']}/commits/{commit['sha']}"
                        )
                        resp.raise_for_status()
                        data = resp.json()
                        stats = data.get("stats", {})
                        self._db.update_commit_stats(
                            commit["sha"],
                            stats.get("additions", 0),
                            stats.get("deletions", 0),
                        )
                        return True
                    except Exception as e:
                        self._emit(FetchProgress(
                            phase="enrich", org=commit["org"], repo=commit["repo"],
                            message=f"Warning: failed to enrich {commit['sha'][:8]}: {e}",
                        ))
                        return False

            results = await asyncio.gather(
                *[enrich_one(c) for c in batch]
            )
            batch_enriched = sum(1 for r in results if r)
            enriched += batch_enriched
            self._emit(FetchProgress(
                phase="enrich", org="", current=enriched,
                message=f"Enriched {enriched} commits...",
            ))

        return enriched

    async def fetch_all(self, org_filter: str | None = None) -> None:
        """Main fetch entry point — fetches all orgs or one."""
        if org_filter:
            org_data = self._db.org_get(org_filter)
            if not org_data:
                raise ValueError(f"Org '{org_filter}' not registered")
            orgs = [org_data]
        else:
            orgs = self._db.org_get_all()
            if not orgs:
                raise ValueError("No orgs registered")

        for org_info in orgs:
            org = org_info["name"]
            since = org_info["since_date"]
            self._emit(FetchProgress(
                phase="repos", org=org,
                message=f"Fetching repos for {org}...",
            ))

            try:
                repos = await self.fetch_repo_list(org)
            except httpx.HTTPError as e:
                self._emit(FetchProgress(
                    phase="repos", org=org,
                    message=f"Error listing repos for {org}: {e}",
                ))
                continue

            self._emit(FetchProgress(
                phase="repos", org=org, total=len(repos),
                message=f"Found {len(repos)} repos in {org}",
            ))

            for i, repo in enumerate(repos, 1):
                count = await self.fetch_repo_commits(org, repo, since)
                self._emit(FetchProgress(
                    phase="commits", org=org, repo=repo,
                    current=i, total=len(repos),
                    message=f"[{i}/{len(repos)}] {repo}: {count} new",
                ))

        # Enrich
        unenriched = len(self._db.get_unenriched_commits(1))
        if unenriched:
            self._emit(FetchProgress(
                phase="enrich", org="",
                message=f"Enriching {unenriched} commits...",
            ))
            await self.enrich_commits()

        self._db.set_meta("last_run_at", self._db._utc_now())
        self._emit(FetchProgress(phase="done", org="", message="Fetch complete."))

    async def close(self) -> None:
        await self._client.aclose()
```

**Step 4: Run tests**

Run: `uv run pytest tests/test_fetch.py -v`
Expected: All PASS

**Step 5: Commit**

```bash
git add src/borg/fetch.py tests/test_fetch.py
git commit -m "Implement async GitHub fetch layer with rate limiting"
```

---

### Task 5: TUI shell — app, tabs, navigation

**Files:**
- Create: `src/borg/ui/__init__.py`
- Create: `src/borg/ui/app.py`
- Modify: `src/borg/cli.py`

**Step 1: Create ui package**

`src/borg/ui/__init__.py`: empty file

**Step 2: Implement app shell with tabs**

```python
"""Borg TUI application."""
from __future__ import annotations

from pathlib import Path

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import (
    Footer,
    Header,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
)

from borg.db import Database


class BorgApp(App):
    """Borg — AI commit adoption tracker TUI."""

    TITLE = "Borg"
    SUB_TITLE = "Resistance is futile"

    CSS = """
    #org-filter {
        dock: top;
        height: 3;
        padding: 0 2;
        background: $surface;
    }
    #org-filter Select {
        width: 30;
    }
    .tab-placeholder {
        padding: 2 4;
        color: $text-muted;
    }
    """

    BINDINGS = [
        Binding("1", "show_tab('overview')", "Overview", show=True),
        Binding("2", "show_tab('authors')", "Authors", show=True),
        Binding("3", "show_tab('repos')", "Repos", show=True),
        Binding("4", "show_tab('trends')", "Trends", show=True),
        Binding("5", "show_tab('fetch')", "Fetch", show=True),
        Binding("6", "show_tab('detect')", "Detect", show=True),
        Binding("7", "show_tab('export')", "Export", show=True),
        Binding("8", "show_tab('orgs')", "Orgs", show=True),
        Binding("slash", "focus_filter", "Filter org"),
        Binding("q", "quit", "Quit"),
    ]

    def __init__(self, db_path: Path) -> None:
        super().__init__()
        self.db = Database(db_path)
        self.org_filter: str | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="org-filter"):
            yield Label("Org: ")
            yield Select(
                [("All orgs", None)],
                value=None,
                id="org-select",
                allow_blank=False,
            )
        with TabbedContent(initial="overview"):
            with TabPane("Overview", id="overview"):
                yield Label("Overview content", classes="tab-placeholder")
            with TabPane("Authors", id="authors"):
                yield Label("Authors content", classes="tab-placeholder")
            with TabPane("Repos", id="repos"):
                yield Label("Repos content", classes="tab-placeholder")
            with TabPane("Trends", id="trends"):
                yield Label("Trends content", classes="tab-placeholder")
            with TabPane("Fetch", id="fetch"):
                yield Label("Fetch content", classes="tab-placeholder")
            with TabPane("Detect", id="detect"):
                yield Label("Detect content", classes="tab-placeholder")
            with TabPane("Export", id="export"):
                yield Label("Export content", classes="tab-placeholder")
            with TabPane("Orgs", id="orgs"):
                yield Label("Orgs content", classes="tab-placeholder")
        yield Footer()

    def on_mount(self) -> None:
        self._refresh_org_filter()
        # If no orgs registered, switch to Orgs tab
        if not self.db.org_get_all():
            self.query_one(TabbedContent).active = "orgs"

    def _refresh_org_filter(self) -> None:
        """Update the org filter dropdown with current orgs."""
        select = self.query_one("#org-select", Select)
        orgs = self.db.org_get_all()
        options = [("All orgs", None)] + [(o["name"], o["name"]) for o in orgs]
        select.set_options(options)

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "org-select":
            self.org_filter = event.value

    def action_show_tab(self, tab_id: str) -> None:
        self.query_one(TabbedContent).active = tab_id

    def action_focus_filter(self) -> None:
        self.query_one("#org-select", Select).focus()
```

**Step 3: Update cli.py to launch TUI**

```python
"""CLI entry point — launches the TUI."""
import typer
from pathlib import Path

app = typer.Typer(add_completion=False)

DEFAULT_DB = Path.home() / ".local" / "share" / "borg" / "tracker.db"


@app.command()
def main(
    db: Path = typer.Option(DEFAULT_DB, "--db", help="Database path"),
) -> None:
    """Borg — AI commit adoption tracker. Resistance is futile."""
    from borg.ui.app import BorgApp

    tui = BorgApp(db_path=db)
    tui.run()


if __name__ == "__main__":
    app()
```

**Step 4: Verify it launches**

Run: `uv run borg --db data/test.db`
Expected: TUI opens with 8 tabs, org filter dropdown, placeholder content. Press `q` to quit.

**Step 5: Commit**

```bash
git add src/borg/ui/ src/borg/cli.py
git commit -m "Implement TUI shell with tabs and org filter"
```

---

### Task 6: Overview tab

**Files:**
- Create: `src/borg/ui/overview.py`
- Modify: `src/borg/ui/app.py`

**Step 1: Implement overview widget**

```python
"""Overview tab — summary, Skynet Employee, tool chart."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Static
from textual_plotext import PlotextPlot

from borg.db import Database


class OverviewTab(Static):
    """Overview dashboard with summary stats and tool chart."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

    def compose(self) -> ComposeResult:
        with Vertical():
            yield Static(id="summary-box")
            yield Static(id="skynet-employee")
            yield PlotextPlot(id="tool-chart")

    def refresh_data(self, org: str | None = None) -> None:
        s = self._db.query_summary(org)
        total = s["total_commits"]
        ai = s["ai_commits"]
        pct = (ai * 100 // total) if total > 0 else 0
        loc_total = s["total_loc"]
        loc_ai = s["ai_loc"]
        loc_pct = (loc_ai * 100 // loc_total) if loc_total > 0 else 0

        summary = self.query_one("#summary-box", Static)
        summary.update(
            f"Assimilation Progress: {ai:,} / {total:,} commits ({pct}%)\n"
            f"LOC: {loc_ai:,} / {loc_total:,} ({loc_pct}%)"
        )

        # Skynet Employee of the Week
        emp = self._db.query_skynet_employee(org)
        skynet = self.query_one("#skynet-employee", Static)
        if emp:
            skynet.update(
                f"⭐ Skynet Employee of the Week: {emp['name']} "
                f"({emp['ai_commits']} AI commits this week)"
            )
        else:
            skynet.update("⭐ Skynet Employee of the Week: No activity this week")

        # Tool chart
        tools = self._db.query_by_tool(org)
        plot_widget = self.query_one("#tool-chart", PlotextPlot)
        plt = plot_widget.plt
        plt.clear_figure()
        if tools:
            names = [t["tool"] for t in tools]
            counts = [t["commits"] for t in tools]
            plt.bar(names, counts)
            plt.title("Commits by AI Tool")
        else:
            plt.title("No AI commits detected")
        plot_widget.refresh()
```

**Step 2: Wire into app.py**

Replace the Overview TabPane placeholder in `app.py` with:

```python
with TabPane("Overview", id="overview"):
    yield OverviewTab(self.db)
```

Add to `on_mount` and tab change handler to call `refresh_data`:

```python
def on_tabbed_content_tab_activated(self, event: TabbedContent.TabActivated) -> None:
    """Refresh data when switching tabs."""
    pane_id = event.pane.id
    if pane_id == "overview":
        self.query_one(OverviewTab).refresh_data(self.org_filter)
```

**Step 3: Test manually**

Run: `uv run borg --db data/test.db`
Expected: Overview shows summary stats, Skynet Employee, and bar chart (empty if no data)

**Step 4: Commit**

```bash
git add src/borg/ui/overview.py src/borg/ui/app.py
git commit -m "Implement Overview tab with summary, Skynet Employee, and tool chart"
```

---

### Task 7: Authors and Repos tabs

**Files:**
- Create: `src/borg/ui/authors.py`
- Create: `src/borg/ui/repos.py`
- Modify: `src/borg/ui/app.py`

**Step 1: Implement ranking table widget (shared)**

Since Authors and Repos have the same layout, create one reusable widget:

`src/borg/ui/rankings.py`:
```python
"""Reusable ranking table widget for Authors and Repos tabs."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import DataTable, Static

from borg.db import Database


class RankingTab(Static):
    """Sortable ranking table for authors or repos."""

    def __init__(self, db: Database, group_by: str, label: str) -> None:
        super().__init__()
        self._db = db
        self._group_by = group_by
        self._label = label
        self._sort_column = "ai_commits"
        self._ascending = False

    def compose(self) -> ComposeResult:
        yield DataTable(id=f"{self._group_by}-table", zebra_stripes=True)

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_column(self._label, key="name")
        table.add_column("AI", key="ai_commits")
        table.add_column("Total", key="total_commits")
        table.add_column("%", key="pct")
        table.add_column("AI LOC", key="ai_loc")

    def refresh_data(self, org: str | None = None) -> None:
        table = self.query_one(DataTable)
        table.clear()
        rows = self._db.query_rankings(
            self._group_by,
            org=org,
            limit=50,
            order_by=self._sort_column,
            ascending=self._ascending,
        )
        for r in rows:
            total = r["total_commits"]
            pct = (r["ai_commits"] * 100 // total) if total > 0 else 0
            table.add_row(
                r["name"],
                f"{r['ai_commits']:,}",
                f"{total:,}",
                f"{pct}%",
                f"{r['ai_loc']:,}",
            )

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        col_key = str(event.column_key)
        col_map = {
            "name": "name",
            "ai_commits": "ai_commits",
            "total_commits": "total_commits",
            "ai_loc": "ai_loc",
        }
        if col_key in col_map:
            if self._sort_column == col_map[col_key]:
                self._ascending = not self._ascending
            else:
                self._sort_column = col_map[col_key]
                self._ascending = False
            self.refresh_data(self.app.org_filter)
```

**Step 2: Create thin wrappers**

`src/borg/ui/authors.py`:
```python
"""Authors tab."""
from borg.db import Database
from borg.ui.rankings import RankingTab


class AuthorsTab(RankingTab):
    def __init__(self, db: Database) -> None:
        super().__init__(db, group_by="author", label="Author")
```

`src/borg/ui/repos.py`:
```python
"""Repos tab."""
from borg.db import Database
from borg.ui.rankings import RankingTab


class ReposTab(RankingTab):
    def __init__(self, db: Database) -> None:
        super().__init__(db, group_by="repo", label="Repo")
```

**Step 3: Wire into app.py**

Replace Authors/Repos TabPane placeholders. Add refresh calls in `on_tabbed_content_tab_activated`.

**Step 4: Test manually**

Run: `uv run borg --db data/test.db`
Expected: Authors and Repos tabs show sortable tables. Click headers to sort.

**Step 5: Commit**

```bash
git add src/borg/ui/rankings.py src/borg/ui/authors.py src/borg/ui/repos.py src/borg/ui/app.py
git commit -m "Implement Authors and Repos tabs with sortable ranking tables"
```

---

### Task 8: Trends tab

**Files:**
- Create: `src/borg/ui/trends.py`
- Modify: `src/borg/ui/app.py`

**Step 1: Implement trends widget**

```python
"""Trends tab — monthly and weekly line charts."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Static
from textual_plotext import PlotextPlot

from borg.db import Database


class TrendsTab(Static):
    """Monthly and weekly trend charts."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

    def compose(self) -> ComposeResult:
        yield PlotextPlot(id="monthly-chart")
        yield PlotextPlot(id="weekly-chart")

    def _render_chart(self, widget_id: str, data: list[dict], title: str) -> None:
        plot_widget = self.query_one(f"#{widget_id}", PlotextPlot)
        plt = plot_widget.plt
        plt.clear_figure()
        if not data:
            plt.title(f"{title} — No data")
            plot_widget.refresh()
            return

        periods = [d["period"] for d in data]
        totals = [d["total"] for d in data]
        ai_counts = [d["ai"] for d in data]
        pcts = [(a * 100 // t) if t > 0 else 0 for a, t in zip(ai_counts, totals)]

        plt.plot(list(range(len(periods))), pcts, marker="braille")
        plt.xticks(list(range(len(periods))), periods)
        plt.ylim(0, 100)
        plt.ylabel("AI %")
        plt.title(title)
        plot_widget.refresh()

    def refresh_data(self, org: str | None = None) -> None:
        monthly = self._db.query_trends("monthly", org)
        self._render_chart("monthly-chart", monthly, "Monthly AI Adoption %")

        weekly = self._db.query_trends("weekly", org)
        self._render_chart("weekly-chart", weekly, "Weekly AI Adoption %")
```

**Step 2: Wire into app.py, test manually, commit**

```bash
git add src/borg/ui/trends.py src/borg/ui/app.py
git commit -m "Implement Trends tab with monthly and weekly line charts"
```

---

### Task 9: Fetch tab

**Files:**
- Create: `src/borg/ui/fetch_tab.py`
- Modify: `src/borg/ui/app.py`

**Step 1: Implement fetch tab with log panel**

```python
"""Fetch tab — trigger fetch with real-time log output."""
from __future__ import annotations

from textual import work
from textual.app import ComposeResult
from textual.widgets import Button, RichLog, Static

from borg.db import Database
from borg.detect import detect_ai
from borg.fetch import FetchProgress, GitHubFetcher


class FetchTab(Static):
    """Fetch action tab with progress log."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

    def compose(self) -> ComposeResult:
        yield Button("Start Fetch", id="fetch-btn", variant="primary")
        yield RichLog(id="fetch-log", highlight=True, markup=True)

    def _log(self, message: str) -> None:
        log = self.query_one("#fetch-log", RichLog)
        log.write(message)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "fetch-btn":
            event.button.disabled = True
            self._log("[bold]Starting fetch...[/bold]")
            self.run_fetch()

    @work(exclusive=True)
    async def run_fetch(self) -> None:
        try:
            fetcher = GitHubFetcher(self._db)
            fetcher.set_progress_callback(
                lambda p: self.app.call_from_thread(self._log, p.message) if p.message else None
            )
            org_filter = self.app.org_filter
            await fetcher.fetch_all(org_filter)

            self.app.call_from_thread(self._log, "[bold]Running AI detection...[/bold]")
            result = detect_ai(self._db)
            self.app.call_from_thread(
                self._log,
                f"Detection complete: {result['high']} high, {result['low']} low, {result['total']} total.",
            )
            self.app.call_from_thread(self._log, "[bold green]Done![/bold green]")
            await fetcher.close()
        except Exception as e:
            self.app.call_from_thread(self._log, f"[bold red]Error: {e}[/bold red]")
        finally:
            btn = self.query_one("#fetch-btn", Button)
            self.app.call_from_thread(setattr, btn, "disabled", False)
```

**Step 2: Wire into app.py, test manually, commit**

```bash
git add src/borg/ui/fetch_tab.py src/borg/ui/app.py
git commit -m "Implement Fetch tab with real-time log and auto-detect"
```

---

### Task 10: Detect tab

**Files:**
- Create: `src/borg/ui/detect_tab.py`
- Modify: `src/borg/ui/app.py`

**Step 1: Implement detect tab**

```python
"""Detect tab — detection rules reference and re-run."""
from __future__ import annotations

from textual.app import ComposeResult
from textual.widgets import Button, DataTable, Static

from borg.db import Database
from borg.detect import RULES, detect_ai


class DetectTab(Static):
    """Detection rules reference and re-run button."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

    def compose(self) -> ComposeResult:
        yield Static("AI Detection Rules", classes="section-title")
        yield DataTable(id="rules-table", zebra_stripes=True)
        yield Button("Re-run Detection", id="detect-btn", variant="primary")
        yield Static("", id="detect-result")

    def on_mount(self) -> None:
        table = self.query_one("#rules-table", DataTable)
        table.add_column("Tool")
        table.add_column("Confidence")
        table.add_column("Pattern")
        for tool, confidence, pattern in RULES:
            # Truncate long patterns for display
            display_pattern = pattern[:80] + "..." if len(pattern) > 80 else pattern
            table.add_row(tool, confidence, display_pattern)
        table.add_row("unknown", "low", "additions > 100 AND deletions < 10")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "detect-btn":
            result = detect_ai(self._db)
            self.query_one("#detect-result", Static).update(
                f"Detection complete: {result['high']} high-confidence, "
                f"{result['low']} low-confidence, {result['total']} total."
            )
```

**Step 2: Wire into app.py, test manually, commit**

```bash
git add src/borg/ui/detect_tab.py src/borg/ui/app.py
git commit -m "Implement Detect tab with rules table and re-run"
```

---

### Task 11: Export tab

**Files:**
- Create: `src/borg/ui/export_tab.py`
- Modify: `src/borg/ui/app.py`

**Step 1: Implement export tab**

```python
"""Export tab — CSV export with path input."""
from __future__ import annotations

from pathlib import Path

from textual.app import ComposeResult
from textual.widgets import Button, Input, Static

from borg.db import Database


class ExportTab(Static):
    """Export data to CSV."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

    def compose(self) -> ComposeResult:
        yield Static("Export to CSV")
        yield Input(
            placeholder="Output path...",
            value="borg-export.csv",
            id="export-path",
        )
        yield Button("Export", id="export-btn", variant="primary")
        yield Static("", id="export-result")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "export-btn":
            path_str = self.query_one("#export-path", Input).value
            path = Path(path_str).expanduser()
            try:
                org_filter = self.app.org_filter
                count = self._db.export_csv(path, org_filter)
                self.query_one("#export-result", Static).update(
                    f"Exported {count} commits to {path}"
                )
            except Exception as e:
                self.query_one("#export-result", Static).update(
                    f"Error: {e}"
                )
```

**Step 2: Wire into app.py, test manually, commit**

```bash
git add src/borg/ui/export_tab.py src/borg/ui/app.py
git commit -m "Implement Export tab with CSV output"
```

---

### Task 12: Orgs tab

**Files:**
- Create: `src/borg/ui/orgs_tab.py`
- Modify: `src/borg/ui/app.py`

**Step 1: Implement orgs tab**

```python
"""Orgs tab — add, remove, and list organizations."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.widgets import Button, DataTable, Input, Static

from borg.db import Database


class OrgsTab(Static):
    """Organization management."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db

    def compose(self) -> ComposeResult:
        yield Static("Registered Organizations")
        yield DataTable(id="orgs-table", zebra_stripes=True)
        yield Static("")
        yield Static("Add Organization")
        with Horizontal():
            yield Input(placeholder="org name", id="org-name-input")
            yield Input(
                placeholder="since (YYYY-MM-DD)",
                value=(datetime.now(timezone.utc) - timedelta(days=90)).strftime("%Y-%m-%d"),
                id="org-since-input",
            )
            yield Button("Add", id="add-org-btn", variant="primary")
        yield Button("Remove Selected", id="remove-org-btn", variant="error")
        yield Static("", id="org-result")

    def on_mount(self) -> None:
        table = self.query_one("#orgs-table", DataTable)
        table.add_column("Name", key="name")
        table.add_column("Since", key="since")
        table.add_column("Added", key="added")
        table.add_column("Commits", key="commits")
        table.cursor_type = "row"
        self.refresh_data()

    def refresh_data(self) -> None:
        table = self.query_one("#orgs-table", DataTable)
        table.clear()
        orgs = self._db.org_list()
        if not orgs:
            self.query_one("#org-result", Static).update(
                "No orgs configured. Add your first org above."
            )
            return
        self.query_one("#org-result", Static).update("")
        for o in orgs:
            table.add_row(
                o["name"],
                o["since_date"],
                o["added_at"][:10],
                str(o["commit_count"]),
                key=o["name"],
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "add-org-btn":
            name = self.query_one("#org-name-input", Input).value.strip()
            since = self.query_one("#org-since-input", Input).value.strip()
            if not name:
                self.query_one("#org-result", Static).update("Error: org name required")
                return
            try:
                self._db.org_add(name, since)
                self.query_one("#org-name-input", Input).value = ""
                self.refresh_data()
                self.app._refresh_org_filter()
            except ValueError as e:
                self.query_one("#org-result", Static).update(f"Error: {e}")

        elif event.button.id == "remove-org-btn":
            table = self.query_one("#orgs-table", DataTable)
            if table.cursor_row is not None:
                row_key = table.get_row_at(table.cursor_row)
                org_name = row_key[0]  # first column is the name
                try:
                    self._db.org_remove(org_name)
                    self.refresh_data()
                    self.app._refresh_org_filter()
                except ValueError as e:
                    self.query_one("#org-result", Static).update(f"Error: {e}")
```

**Step 2: Wire into app.py, test manually, commit**

```bash
git add src/borg/ui/orgs_tab.py src/borg/ui/app.py
git commit -m "Implement Orgs tab with add/remove functionality"
```

---

### Task 13: Wire up complete app.py and polish

**Files:**
- Modify: `src/borg/ui/app.py`

**Step 1: Complete app.py with all tabs wired**

Update app.py to import all tab widgets, replace placeholders, and add the tab-activated handler that refreshes data. Also handle the org filter change to refresh the current tab.

Key additions:
- Import all tab classes
- Replace Label placeholders with actual tab widgets in compose()
- `on_tabbed_content_tab_activated` refreshes the active tab's data
- `on_select_changed` for org filter also refreshes current tab
- First launch with no orgs → auto-switch to Orgs tab

**Step 2: Test the full app end-to-end**

```bash
rm -f ~/.local/share/borg/tracker.db
uv run borg
```

Expected:
1. Opens to Orgs tab (no orgs registered)
2. Add an org → appears in table and dropdown
3. Switch to Fetch → Start Fetch → see progress
4. Switch to Overview → see stats and chart
5. Switch to Authors/Repos → see ranking tables
6. Switch to Trends → see line charts
7. Filter by org in dropdown → all views update
8. `q` to quit

**Step 3: Commit**

```bash
git add src/borg/ui/app.py
git commit -m "Wire up all tabs and polish app integration"
```

---

### Task 14: Delete bash version and update docs

**Files:**
- Delete: `borg` (bash script)
- Delete: `lib/db.sh`, `lib/fetch.sh`, `lib/detect.sh`, `lib/report.sh`
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `.gitignore`

**Step 1: Remove bash files**

```bash
rm -f borg lib/db.sh lib/fetch.sh lib/detect.sh lib/report.sh
rmdir lib/
```

**Step 2: Update .gitignore**

Add Python patterns:
```
__pycache__/
*.pyc
.venv/
dist/
*.egg-info/
```

**Step 3: Update README.md**

Rewrite for the TUI version:
- Install: `uv tool install .`
- Run: `borg` or `borg --db path`
- Screenshot of the TUI (add later)
- Same AI detection table
- Same rate limit table

**Step 4: Update CLAUDE.md**

Update architecture to reflect Python package structure, uv workflow, textual app.

**Step 5: Commit**

```bash
git add -A
git commit -m "Replace bash CLI with Python TUI"
```

---

### Task 15: Final verification

**Step 1: Clean install test**

```bash
rm -rf .venv
uv sync
uv run pytest -v
uv run borg --db /tmp/borg-test.db
```

**Step 2: Test full workflow**

1. Launch borg
2. Go to Orgs → add an org
3. Go to Fetch → run fetch
4. Go to Overview → verify stats
5. Go to Authors → sort columns
6. Go to Trends → check charts
7. Go to Export → export CSV
8. Filter by org → verify all tabs update
9. Go to Detect → re-run detection
10. Go to Orgs → remove org → verify data cleared

**Step 3: Final commit if any fixes needed**
