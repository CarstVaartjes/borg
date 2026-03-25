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


def test_ai_style_heuristic_bullets(tmp_db: Path) -> None:
    """Detects AI-style commit messages: summary + blank line + bullet points."""
    db = Database(tmp_db)
    msg = (
        "AI-482: Split test infrastructure — shared tests use local source\n"
        "\n"
        "- DockerfileSharedTest: installs from local source (pip install -e)\n"
        "- DockerfileTest: installs from CodeArtifact (PIP_INDEX_URL)\n"
        "- Shared tests run first (no DB needed), then orchestrator tests"
    )
    _insert_commit(db, "style1", msg, additions=50, deletions=20)
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool, ai_confidence FROM commits WHERE sha = 'style1'").fetchone()
    assert row["ai_tool"] == "ai-assisted"
    assert row["ai_confidence"] == "medium"


def test_ai_style_heuristic_prose(tmp_db: Path) -> None:
    """Detects AI-style commit messages: summary + blank line + descriptive paragraph."""
    db = Database(tmp_db)
    msg = (
        "Simplify marketplace.json and fix plugin source paths\n"
        "\n"
        "Remove redundant metadata fields (version, author, keywords, category) "
        "and correct source paths to include cowork-plugins/ prefix."
    )
    _insert_commit(db, "prose1", msg, additions=30, deletions=15)
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool, ai_confidence FROM commits WHERE sha = 'prose1'").fetchone()
    assert row["ai_tool"] == "ai-assisted"
    assert row["ai_confidence"] == "medium"


def test_ai_style_not_triggered_on_short_messages(tmp_db: Path) -> None:
    """Short messages should not trigger the heuristic."""
    db = Database(tmp_db)
    _insert_commit(db, "short1", "fix\n\n- item1\n- item2", additions=5, deletions=2)
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'short1'").fetchone()
    assert row["ai_tool"] is None


def test_ai_style_not_triggered_without_blank_line(tmp_db: Path) -> None:
    """Body without a blank line separator should not match."""
    db = Database(tmp_db)
    msg = "Some title that is long enough to pass the length check for this heuristic rule and detection\nThis continues without a blank line separator between title and body text"
    _insert_commit(db, "noblanc", msg, additions=50, deletions=20)
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'noblanc'").fetchone()
    assert row["ai_tool"] is None


def test_ai_style_not_triggered_on_merge_commits(tmp_db: Path) -> None:
    """Merge commits should not trigger the heuristic."""
    db = Database(tmp_db)
    msg = (
        "Merge pull request #123 from org/feature-branch\n"
        "\n"
        "This is a detailed merge commit description that is long enough to pass the length threshold."
    )
    _insert_commit(db, "merge1", msg, additions=100, deletions=50)
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'merge1'").fetchone()
    assert row["ai_tool"] is None


def test_conventional_commit_heuristic(tmp_db: Path) -> None:
    """Detects conventional commit prefixes as low-confidence AI."""
    db = Database(tmp_db)
    _insert_commit(db, "conv1", "fix: separate approval steps per region for independent deploys")
    _insert_commit(db, "conv2", "chore: bump vf-trade-promotions version")
    _insert_commit(db, "conv3", "feat: add calendar dimensions to analytics prompt")
    detect_ai(db)
    for sha in ("conv1", "conv2", "conv3"):
        row = db.conn.execute(f"SELECT ai_tool, ai_confidence FROM commits WHERE sha = '{sha}'").fetchone()
        assert row["ai_tool"] == "ai-assisted", f"{sha} should be ai-assisted"
        assert row["ai_confidence"] == "low", f"{sha} should be low confidence"


def test_conventional_commit_not_triggered_on_multiline(tmp_db: Path) -> None:
    """Conventional prefix with multiline body should not match (caught by medium heuristic instead)."""
    db = Database(tmp_db)
    msg = "fix: something important\n\nThis is a detailed explanation that goes on for a while and explains the reasoning."
    _insert_commit(db, "convml", msg)
    detect_ai(db)
    row = db.conn.execute("SELECT ai_confidence FROM commits WHERE sha = 'convml'").fetchone()
    # Should be medium (caught by the structured message heuristic), not low
    assert row["ai_confidence"] == "medium"


def test_conventional_commit_not_triggered_on_too_short(tmp_db: Path) -> None:
    """Very short conventional commits should not match."""
    db = Database(tmp_db)
    _insert_commit(db, "convs", "fix: typo")
    detect_ai(db)
    row = db.conn.execute("SELECT ai_tool FROM commits WHERE sha = 'convs'").fetchone()
    assert row["ai_tool"] is None


def test_detect_returns_counts(tmp_db: Path) -> None:
    """detect_ai returns correct count summary."""
    db = Database(tmp_db)
    _insert_commit(db, "j1", "feat\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    _insert_commit(db, "j2", "feat\n\nCo-Authored-By: Claude <noreply@anthropic.com>")
    _insert_commit(db, "j3", "bulk add", additions=200, deletions=2)
    _insert_commit(db, "j4", "normal", additions=10, deletions=10)
    result = detect_ai(db)
    assert result["high"] == 2
    assert result["medium"] == 0
    assert result["low"] == 1
    assert result["total"] == 3
