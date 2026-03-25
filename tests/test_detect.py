"""Tests for AI detection logic."""

from pathlib import Path

from borg.db import Database
from borg.detect import detect_ai


def _insert_commit(
    db: Database,
    sha: str,
    message: str,
    author: str = "dev",
    email: str = "d@e",
    additions: int = 100,
    deletions: int = 10,
) -> None:
    db.conn.execute(
        "INSERT INTO commits (sha, org, repo, author, email, date, message, additions, deletions, fetched_at) "
        "VALUES (?, 'org1', 'repo1', ?, ?, '2026-01-15', ?, ?, ?, '2026-01-16')",
        (sha, author, email, message, additions, deletions),
    )
    db.conn.commit()


def test_detect_claude_co_authored(tmp_db: Path) -> None:
    """Detects Claude via Co-Authored-By trailer."""
    db = Database(tmp_db)
    _insert_commit(
        db, "aaa", "feat: add thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
    )
    result = detect_ai(db)
    row = db.conn.execute(
        "SELECT ai_tool, ai_confidence FROM commits WHERE sha = 'aaa'"
    ).fetchone()
    assert row["ai_tool"] == "claude"
    assert row["ai_confidence"] == "high"
    assert result["high"] >= 1


def test_detect_claude_anthropic_email(tmp_db: Path) -> None:
    """Detects Claude via noreply@anthropic.com in message."""
    db = Database(tmp_db)
    _insert_commit(
        db, "bbb", "fix: stuff\n\nCo-Authored-By: bot <noreply@anthropic.com>"
    )
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'bbb'").fetchone()
    assert row["ai_tool"] == "claude"


def test_detect_copilot_bot_author(tmp_db: Path) -> None:
    """Detects Copilot via copilot[bot] author."""
    db = Database(tmp_db)
    _insert_commit(
        db, "ccc", "auto commit", author="copilot[bot]", email="copilot@github.com"
    )
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'ccc'").fetchone()
    assert row["ai_tool"] == "copilot"


def test_detect_aider_author(tmp_db: Path) -> None:
    """Detects aider via (aider) in author."""
    db = Database(tmp_db)
    _insert_commit(db, "ddd", "refactor code", author="John (aider)")
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'ddd'").fetchone()
    assert row["ai_tool"] == "aider"


def test_no_detection_human_commit(tmp_db: Path) -> None:
    """Normal human commit is not flagged as AI (no bulk heuristic trigger)."""
    db = Database(tmp_db)
    _insert_commit(db, "eee", "normal commit", additions=50, deletions=30)
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'eee'").fetchone()
    assert row["ai_tool"] is None


def test_bulk_heuristic(tmp_db: Path) -> None:
    """Bulk heuristic flags large additions with few deletions."""
    db = Database(tmp_db)
    _insert_commit(db, "fff", "add generated code", additions=200, deletions=5)
    result = detect_ai(db)
    row = db.conn.execute(
        "SELECT ai_tool, ai_confidence FROM commits WHERE sha = 'fff'"
    ).fetchone()
    assert row["ai_tool"] == "unknown"
    assert row["ai_confidence"] == "low"
    assert result["low"] >= 1


def test_redetection_clears_old(tmp_db: Path) -> None:
    """Running detect_ai again clears previous results before re-detecting."""
    db = Database(tmp_db)
    _insert_commit(
        db, "ggg", "feat: add thing\n\nCo-Authored-By: Claude <noreply@anthropic.com>"
    )
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'ggg'").fetchone()
    assert row["ai_tool"] == "claude"
    # Update message to remove AI signature
    db.conn.execute(
        "UPDATE commits SET message = 'plain commit', additions = 50, deletions = 30 WHERE sha = 'ggg'"
    )
    db.conn.commit()
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'ggg'").fetchone()
    assert row["ai_tool"] is None


def test_devin_requires_bot_author(tmp_db: Path) -> None:
    """A human named Devin should NOT be flagged as devin AI tool."""
    db = Database(tmp_db)
    _insert_commit(
        db, "hhh", "fix bug", author="Devin Smith", email="devin@company.com"
    )
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'hhh'").fetchone()
    assert row["ai_tool"] is None


def test_devin_bot_detected(tmp_db: Path) -> None:
    """The actual devin-ai bot should be detected."""
    db = Database(tmp_db)
    _insert_commit(
        db,
        "iii",
        "implement feature",
        author="devin-ai[bot]",
        email="devin-ai@users.noreply.github.com",
    )
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'iii'").fetchone()
    assert row["ai_tool"] == "devin"


def test_detect_returns_counts(tmp_db: Path) -> None:
    """detect_ai returns correct count summary."""
    db = Database(tmp_db)
    _insert_commit(db, "j1", "feat\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    _insert_commit(db, "j2", "feat\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    _insert_commit(db, "j3", "bulk add", additions=200, deletions=2)
    _insert_commit(db, "j4", "normal", additions=10, deletions=10)
    result = detect_ai(db)
    assert result["high"] == 2
    assert result["low"] == 1
    assert result["total"] == 3
