"""Tests for the database layer."""

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from borg.db import Database


class TestDatabaseInit:
    """Test database initialization."""

    def test_creates_db_file(self, tmp_db: Path) -> None:
        Database(tmp_db)
        assert tmp_db.exists()

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        db_path = tmp_path / "nested" / "deep" / "test.db"
        Database(db_path)
        assert db_path.exists()

    def test_creates_orgs_table(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='orgs'"
        ).fetchone()
        assert tables is not None

    def test_creates_commits_table(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='commits'"
        ).fetchone()
        assert tables is not None

    def test_creates_repo_sync_table(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='repo_sync'"
        ).fetchone()
        assert tables is not None

    def test_creates_sync_meta_table(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        tables = db.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sync_meta'"
        ).fetchone()
        assert tables is not None

    def test_idempotent_init(self, tmp_db: Path) -> None:
        """Creating Database twice should not raise."""
        Database(tmp_db)
        Database(tmp_db)


class TestOrgCRUD:
    """Test org create/read/delete operations."""

    def test_add_org(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        result = db.org_get("acme-corp")
        assert result is not None
        assert result["name"] == "acme-corp"
        assert result["since_date"] == "2024-01-01"

    def test_add_duplicate_raises(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        with pytest.raises(ValueError, match="already exists"):
            db.org_add("acme-corp", "2024-06-01")

    def test_remove_org(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        db.org_remove("acme-corp")
        assert db.org_get("acme-corp") is None

    def test_remove_nonexistent_raises(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        with pytest.raises(ValueError, match="not found"):
            db.org_remove("ghost-org")

    def test_remove_deletes_commits_and_repo_sync(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        db.insert_commit(
            "abc123", "acme-corp", "repo1", "Alice", "a@x.com", "2024-03-01", "msg"
        )
        db.update_repo_sync("acme-corp", "repo1", "2024-03-01", 1)

        db.org_remove("acme-corp")

        commits = db.conn.execute(
            "SELECT * FROM commits WHERE org = ?", ("acme-corp",)
        ).fetchall()
        syncs = db.conn.execute(
            "SELECT * FROM repo_sync WHERE org = ?", ("acme-corp",)
        ).fetchall()
        assert len(commits) == 0
        assert len(syncs) == 0

    def test_org_get_all_sorted(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("zebra-inc", "2024-01-01")
        db.org_add("alpha-co", "2024-01-01")
        db.org_add("middle-org", "2024-01-01")
        result = db.org_get_all()
        names = [r["name"] for r in result]
        assert names == ["alpha-co", "middle-org", "zebra-inc"]

    def test_org_get_returns_dict(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        result = db.org_get("acme-corp")
        assert isinstance(result, dict)
        assert "name" in result
        assert "since_date" in result

    def test_org_get_missing_returns_none(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        assert db.org_get("nonexistent") is None

    def test_org_list_with_commit_count(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        db.org_add("empty-org", "2024-01-01")
        db.insert_commit(
            "sha1", "acme-corp", "repo1", "Alice", "a@x.com", "2024-03-01", "msg"
        )
        db.insert_commit(
            "sha2", "acme-corp", "repo1", "Bob", "b@x.com", "2024-03-02", "msg"
        )

        result = db.org_list()
        by_name = {r["name"]: r for r in result}
        assert by_name["acme-corp"]["commit_count"] == 2
        assert by_name["empty-org"]["commit_count"] == 0


class TestMeta:
    """Test sync_meta key-value operations."""

    def test_set_and_get_meta(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.set_meta("last_sync", "2024-03-01T10:00:00Z")
        assert db.get_meta("last_sync") == "2024-03-01T10:00:00Z"

    def test_get_missing_returns_none(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        assert db.get_meta("nonexistent") is None

    def test_set_overwrites(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.set_meta("key", "value1")
        db.set_meta("key", "value2")
        assert db.get_meta("key") == "value2"


@pytest.fixture
def seeded_db(tmp_db: Path) -> Database:
    """Create a database seeded with test data for report queries."""
    db = Database(tmp_db)
    db.org_add("acme-corp", "2024-01-01")
    db.org_add("beta-inc", "2024-01-01")

    now = datetime.now(tz=timezone.utc)
    today = now.strftime("%Y-%m-%d")
    yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    last_month = (now - timedelta(days=35)).strftime("%Y-%m-%d")

    # Commit 1: acme, AI (copilot), recent
    db.insert_commit(
        "sha1", "acme-corp", "repo1", "Alice", "a@x.com", today, "feat: stuff"
    )
    db.update_commit_stats("sha1", 100, 20)
    db.conn.execute(
        "UPDATE commits SET ai_tool = 'copilot', ai_confidence = 'high' WHERE sha = 'sha1'"
    )

    # Commit 2: acme, AI (claude), recent
    db.insert_commit(
        "sha2", "acme-corp", "repo1", "Alice", "a@x.com", yesterday, "fix: thing"
    )
    db.update_commit_stats("sha2", 50, 10)
    db.conn.execute(
        "UPDATE commits SET ai_tool = 'claude', ai_confidence = 'high' WHERE sha = 'sha2'"
    )

    # Commit 3: beta, no AI, last month
    db.insert_commit(
        "sha3", "beta-inc", "repo2", "Bob", "b@x.com", last_month, "docs: update"
    )
    db.update_commit_stats("sha3", 30, 5)

    # Commit 4: beta, AI (copilot), recent
    db.insert_commit(
        "sha4", "beta-inc", "repo2", "Charlie", "c@x.com", today, "feat: new"
    )
    db.update_commit_stats("sha4", 200, 50)
    db.conn.execute(
        "UPDATE commits SET ai_tool = 'copilot', ai_confidence = 'medium' WHERE sha = 'sha4'"
    )

    db.conn.commit()
    return db


class TestReportQueries:
    """Test report query methods."""

    def test_query_summary_all(self, seeded_db: Database) -> None:
        result = seeded_db.query_summary()
        assert result["total_commits"] == 4
        assert result["ai_commits"] == 3
        # Default LOC mode = added only
        assert result["total_loc"] == 380  # 100+50+30+200
        assert result["ai_loc"] == 350  # 100+50+200

    def test_query_summary_filtered(self, seeded_db: Database) -> None:
        result = seeded_db.query_summary(org="acme-corp")
        assert result["total_commits"] == 2
        assert result["ai_commits"] == 2
        assert result["total_loc"] == 150  # 100+50

    def test_query_by_tool(self, seeded_db: Database) -> None:
        result = seeded_db.query_by_tool()
        by_tool = {r["tool"]: r for r in result}
        assert "copilot" in by_tool
        assert by_tool["copilot"]["commits"] == 2
        assert "claude" in by_tool
        assert by_tool["claude"]["commits"] == 1

    def test_query_by_tool_filtered(self, seeded_db: Database) -> None:
        result = seeded_db.query_by_tool(org="acme-corp")
        by_tool = {r["tool"]: r for r in result}
        assert by_tool["copilot"]["commits"] == 1

    def test_query_rankings(self, seeded_db: Database) -> None:
        # Use min_commits=1 since test data is small
        result = seeded_db.query_rankings("author", min_commits=1)
        assert len(result) > 0
        # Should be sorted by ai_commits desc by default
        assert result[0]["ai_commits"] >= result[-1]["ai_commits"]

    def test_query_rankings_by_repo(self, seeded_db: Database) -> None:
        result = seeded_db.query_rankings("repo", min_commits=1)
        assert len(result) > 0

    def test_query_trends_monthly(self, seeded_db: Database) -> None:
        result = seeded_db.query_trends(period="monthly")
        assert len(result) > 0
        assert "period" in result[0]
        assert "total" in result[0]
        assert "ai" in result[0]

    def test_query_trends_weekly(self, seeded_db: Database) -> None:
        result = seeded_db.query_trends(period="weekly")
        assert len(result) > 0

    def test_query_skynet_employee(self, seeded_db: Database) -> None:
        result = seeded_db.query_skynet_employee()
        assert result is not None
        assert "author" in result
        assert "ai_commits" in result

    def test_query_skynet_employee_filtered(self, seeded_db: Database) -> None:
        result = seeded_db.query_skynet_employee(org="beta-inc")
        # Charlie has 1 AI commit in beta-inc recently
        assert result is not None

    def test_export_csv(self, seeded_db: Database, tmp_path: Path) -> None:
        csv_path = tmp_path / "export.csv"
        count = seeded_db.export_csv(csv_path)
        assert count == 4
        assert csv_path.exists()
        with open(csv_path) as f:
            reader = csv.reader(f)
            header = next(reader)
            assert "sha" in header
            rows = list(reader)
            assert len(rows) == 4

    def test_export_csv_filtered(self, seeded_db: Database, tmp_path: Path) -> None:
        csv_path = tmp_path / "export_filtered.csv"
        count = seeded_db.export_csv(csv_path, org="acme-corp")
        assert count == 2


class TestCommitInsertion:
    """Test commit insertion and enrichment operations."""

    def test_insert_commit_returns_true_for_new(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        assert (
            db.insert_commit(
                "sha1", "acme-corp", "repo1", "Alice", "a@x.com", "2024-03-01", "msg"
            )
            is True
        )

    def test_insert_commit_returns_false_for_dup(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        db.insert_commit(
            "sha1", "acme-corp", "repo1", "Alice", "a@x.com", "2024-03-01", "msg"
        )
        assert (
            db.insert_commit(
                "sha1", "acme-corp", "repo1", "Alice", "a@x.com", "2024-03-01", "msg"
            )
            is False
        )

    def test_update_commit_stats(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        db.insert_commit(
            "sha1", "acme-corp", "repo1", "Alice", "a@x.com", "2024-03-01", "msg"
        )
        db.update_commit_stats("sha1", 42, 7)
        row = db.conn.execute(
            "SELECT additions, deletions FROM commits WHERE sha = 'sha1'"
        ).fetchone()
        assert row["additions"] == 42
        assert row["deletions"] == 7

    def test_get_unenriched_commits(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        db.insert_commit(
            "sha1", "acme-corp", "repo1", "Alice", "a@x.com", "2024-03-01", "msg"
        )
        db.insert_commit(
            "sha2", "acme-corp", "repo1", "Bob", "b@x.com", "2024-03-02", "msg2"
        )
        # Enrich sha1
        db.update_commit_stats("sha1", 10, 2)
        # sha2 should still be unenriched
        result = db.get_unenriched_commits()
        shas = [r["sha"] for r in result]
        assert "sha2" in shas
        assert "sha1" not in shas

    def test_update_repo_sync(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        db.update_repo_sync("acme-corp", "repo1", "2024-03-01", 10)
        row = db.conn.execute(
            "SELECT * FROM repo_sync WHERE org = ? AND repo = ?",
            ("acme-corp", "repo1"),
        ).fetchone()
        assert row is not None
        assert row["commit_count"] == 10

    def test_get_repo_bookmark(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        assert db.get_repo_bookmark("acme-corp", "repo1") is None
        db.update_repo_sync("acme-corp", "repo1", "2024-03-01", 5)
        assert db.get_repo_bookmark("acme-corp", "repo1") == "2024-03-01"

    def test_get_repo_commit_count(self, tmp_db: Path) -> None:
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")
        assert db.get_repo_commit_count("acme-corp", "repo1") == 0
        db.update_repo_sync("acme-corp", "repo1", "2024-03-01", 15)
        assert db.get_repo_commit_count("acme-corp", "repo1") == 15


class TestInProductionPromotion:
    """Test that in_production gets promoted on duplicate insert."""

    def test_duplicate_insert_promotes_in_production(self, tmp_db: Path) -> None:
        """When a commit already exists with in_production=0, a duplicate insert
        with in_production=True should promote it to 1."""
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")

        # Insert commit with in_production=False
        result1 = db.insert_commit(
            "sha1", "acme-corp", "repo1", "Alice", "a@x.com", "2024-03-01", "msg",
            in_production=False,
        )
        assert result1 is True

        # Insert same SHA again with in_production=True (returns False = dup)
        result2 = db.insert_commit(
            "sha1", "acme-corp", "repo1", "Alice", "a@x.com", "2024-03-01", "msg",
            in_production=True,
        )
        assert result2 is False

        # Verify: in_production is now 1
        row = db.conn.execute(
            "SELECT in_production FROM commits WHERE sha = 'sha1'"
        ).fetchone()
        assert row["in_production"] == 1

    def test_duplicate_insert_without_production_does_not_change(self, tmp_db: Path) -> None:
        """Duplicate insert without in_production should not change existing value."""
        db = Database(tmp_db)
        db.org_add("acme-corp", "2024-01-01")

        # Insert commit with in_production=False
        db.insert_commit(
            "sha1", "acme-corp", "repo1", "Alice", "a@x.com", "2024-03-01", "msg",
            in_production=False,
        )

        # Insert same SHA again with in_production=False
        db.insert_commit(
            "sha1", "acme-corp", "repo1", "Alice", "a@x.com", "2024-03-01", "msg",
            in_production=False,
        )

        # Verify: in_production still 0
        row = db.conn.execute(
            "SELECT in_production FROM commits WHERE sha = 'sha1'"
        ).fetchone()
        assert row["in_production"] == 0
