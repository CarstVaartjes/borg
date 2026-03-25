"""Integration tests using the anonymized fixture database.

These tests verify the full pipeline (queries, detection, export)
against a realistic dataset rather than hand-crafted minimal data.
"""
import shutil
from pathlib import Path

import pytest

from borg.db import Database
from borg.detect import detect_ai

FIXTURE_DB = Path(__file__).parent / "fixture.db"


@pytest.fixture
def fixture_db(tmp_path: Path) -> Database:
    """Copy the fixture DB to a temp location and return a Database instance."""
    if not FIXTURE_DB.exists():
        pytest.skip("Fixture DB not found — run: uv run python tests/create_fixture.py")
    dest = tmp_path / "fixture.db"
    shutil.copy(FIXTURE_DB, dest)
    return Database(dest)


class TestFixtureIntegrity:
    def test_has_commits(self, fixture_db: Database) -> None:
        total = fixture_db.conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
        assert total >= 100, f"Expected 100+ commits, got {total}"

    def test_has_ai_commits(self, fixture_db: Database) -> None:
        ai = fixture_db.conn.execute(
            "SELECT COUNT(*) FROM commits WHERE ai_tool IS NOT NULL"
        ).fetchone()[0]
        assert ai >= 10, f"Expected 10+ AI commits, got {ai}"

    def test_has_multiple_pr_states(self, fixture_db: Database) -> None:
        states = fixture_db.conn.execute(
            "SELECT DISTINCT pr_state FROM commits WHERE pr_state IS NOT NULL"
        ).fetchall()
        state_values = {r[0] for r in states}
        assert "merged" in state_values
        assert "open" in state_values

    def test_has_org(self, fixture_db: Database) -> None:
        orgs = fixture_db.org_get_all()
        assert len(orgs) >= 1

    def test_has_multiple_authors(self, fixture_db: Database) -> None:
        authors = fixture_db.conn.execute(
            "SELECT DISTINCT email FROM commits"
        ).fetchall()
        assert len(authors) >= 5, f"Expected 5+ authors, got {len(authors)}"

    def test_has_multiple_repos(self, fixture_db: Database) -> None:
        repos = fixture_db.conn.execute(
            "SELECT DISTINCT repo FROM commits"
        ).fetchall()
        assert len(repos) >= 2, f"Expected 2+ repos, got {len(repos)}"


class TestQueryIntegration:
    def test_summary_returns_realistic_data(self, fixture_db: Database) -> None:
        s = fixture_db.query_summary()
        assert s["total_commits"] >= 100
        assert s["ai_commits"] >= 1

    def test_summary_with_org_filter(self, fixture_db: Database) -> None:
        s = fixture_db.query_summary(org="test-org")
        assert s["total_commits"] >= 100

    def test_summary_with_nonexistent_org(self, fixture_db: Database) -> None:
        s = fixture_db.query_summary(org="nonexistent-org")
        assert s["total_commits"] == 0

    def test_by_tool_returns_tools(self, fixture_db: Database) -> None:
        tools = fixture_db.query_by_tool()
        assert len(tools) >= 1
        tool_names = [t["tool"] for t in tools]
        assert "claude" in tool_names

    def test_rankings_author(self, fixture_db: Database) -> None:
        rows = fixture_db.query_rankings("author", min_commits=1)
        assert len(rows) >= 1
        # Verify structure
        row = rows[0]
        assert "author" in row or "name" in row
        assert "ai_commits" in row
        assert "total_commits" in row

    def test_rankings_repo(self, fixture_db: Database) -> None:
        rows = fixture_db.query_rankings("repo", min_commits=1)
        assert len(rows) >= 1

    def test_rankings_sorting(self, fixture_db: Database) -> None:
        desc = fixture_db.query_rankings(
            "author", min_commits=1, order_by="ai_commits", ascending=False
        )
        asc = fixture_db.query_rankings(
            "author", min_commits=1, order_by="ai_commits", ascending=True
        )
        if len(desc) >= 2:
            assert desc[0]["ai_commits"] >= desc[-1]["ai_commits"]
        if len(asc) >= 2:
            assert asc[0]["ai_commits"] <= asc[-1]["ai_commits"]

    def test_trends_monthly(self, fixture_db: Database) -> None:
        trends = fixture_db.query_trends("monthly")
        assert len(trends) >= 1
        row = trends[0]
        assert "period" in row
        assert "total" in row
        assert "ai" in row

    def test_trends_weekly(self, fixture_db: Database) -> None:
        trends = fixture_db.query_trends("weekly")
        assert len(trends) >= 1


class TestDetectionIntegration:
    def test_redetection_is_idempotent(self, fixture_db: Database) -> None:
        """Running detection twice should produce the same results."""
        result1 = detect_ai(fixture_db)
        result2 = detect_ai(fixture_db)
        assert result1 == result2

    def test_detection_finds_claude(self, fixture_db: Database) -> None:
        detect_ai(fixture_db)
        claude = fixture_db.conn.execute(
            "SELECT COUNT(*) FROM commits WHERE ai_tool = 'claude'"
        ).fetchone()[0]
        assert claude >= 1


class TestExportIntegration:
    def test_export_csv(self, fixture_db: Database, tmp_path: Path) -> None:
        csv_path = tmp_path / "export.csv"
        count = fixture_db.export_csv(csv_path)
        assert count >= 100
        content = csv_path.read_text()
        # Check CSV has expected columns
        header = content.split("\n")[0]
        assert "sha" in header
        assert "org" in header
        assert "ai_tool" in header
        assert "in_production" in header

    def test_export_csv_filtered(self, fixture_db: Database, tmp_path: Path) -> None:
        csv_path = tmp_path / "export.csv"
        count = fixture_db.export_csv(csv_path, org="test-org")
        assert count >= 100

    def test_export_csv_empty_filter(self, fixture_db: Database, tmp_path: Path) -> None:
        csv_path = tmp_path / "export.csv"
        count = fixture_db.export_csv(csv_path, org="nonexistent")
        assert count == 0
