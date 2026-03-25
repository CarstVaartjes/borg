"""Tests for the GitHub fetch layer."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from borg.db import Database
from borg.fetch import FetchProgress, GitHubFetcher


class TestGitHubFetcherInit:
    def test_init_reads_token(self, tmp_db):
        """GitHubFetcher reads token from gh auth token."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_fake_token_123\n"

        with patch("borg.fetch.subprocess.run", return_value=mock_result):
            db = Database(tmp_db)
            fetcher = GitHubFetcher(db)
            assert fetcher._token == "ghp_fake_token_123"

    def test_init_fails_without_gh(self, tmp_db):
        """GitHubFetcher raises RuntimeError when gh CLI is missing."""
        with patch(
            "borg.fetch.subprocess.run",
            side_effect=FileNotFoundError("gh not found"),
        ):
            db = Database(tmp_db)
            with pytest.raises(RuntimeError, match="gh CLI not found"):
                GitHubFetcher(db)

    def test_init_fails_when_not_authenticated(self, tmp_db):
        """GitHubFetcher raises RuntimeError when gh auth fails."""
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""

        with patch("borg.fetch.subprocess.run", return_value=mock_result):
            db = Database(tmp_db)
            with pytest.raises(RuntimeError, match="not authenticated"):
                GitHubFetcher(db)


class TestFetchProgress:
    def test_defaults(self):
        """FetchProgress has sensible defaults."""
        p = FetchProgress(phase="repos", org="myorg")
        assert p.repo == ""
        assert p.current == 0
        assert p.total == 0
        assert p.message == ""


class TestFetchRepoList:
    @pytest.mark.asyncio
    async def test_fetch_repo_list(self, tmp_db):
        """fetch_repo_list filters out archived repos."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_fake_token\n"

        repos_json = [
            {"name": "active-repo", "archived": False},
            {"name": "old-repo", "archived": True},
            {"name": "another-active", "archived": False},
        ]

        with patch("borg.fetch.subprocess.run", return_value=mock_result):
            db = Database(tmp_db)
            fetcher = GitHubFetcher(db)

        mock_response = MagicMock()
        mock_response.json.return_value = repos_json
        mock_response.status_code = 200
        mock_response.headers = {}
        mock_response.raise_for_status = MagicMock()

        fetcher._client = AsyncMock(spec=httpx.AsyncClient)
        fetcher._client.get = AsyncMock(return_value=mock_response)

        result = await fetcher.fetch_repo_list("myorg")
        assert result == ["active-repo", "another-active"]

    @pytest.mark.asyncio
    async def test_fetch_repo_list_paginates(self, tmp_db):
        """fetch_repo_list follows Link header pagination."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_fake_token\n"

        page1 = [{"name": f"repo-{i}", "archived": False} for i in range(100)]
        page2 = [{"name": "repo-last", "archived": False}]

        with patch("borg.fetch.subprocess.run", return_value=mock_result):
            db = Database(tmp_db)
            fetcher = GitHubFetcher(db)

        resp1 = MagicMock()
        resp1.json.return_value = page1
        resp1.status_code = 200
        resp1.headers = {
            "link": '<https://api.github.com/orgs/myorg/repos?page=2>; rel="next"'
        }
        resp1.raise_for_status = MagicMock()

        resp2 = MagicMock()
        resp2.json.return_value = page2
        resp2.status_code = 200
        resp2.headers = {}
        resp2.raise_for_status = MagicMock()

        fetcher._client = AsyncMock(spec=httpx.AsyncClient)
        fetcher._client.get = AsyncMock(side_effect=[resp1, resp2])

        result = await fetcher.fetch_repo_list("myorg")
        assert len(result) == 101


class TestFetchRepoCommits:
    @pytest.mark.asyncio
    async def test_fetch_repo_commits_inserts(self, tmp_db):
        """fetch_repo_commits inserts commits and updates repo_sync."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_fake_token\n"

        with patch("borg.fetch.subprocess.run", return_value=mock_result):
            db = Database(tmp_db)
            db.org_add("myorg", "2025-01-01")
            fetcher = GitHubFetcher(db)

        # PR list response (one merged PR)
        pr_list_json = [
            {
                "number": 42,
                "merged_at": "2025-06-02T12:00:00Z",
                "updated_at": "2025-06-02T12:00:00Z",
                "state": "closed",
                "base": {"ref": "main"},
            },
        ]

        # PR commits response
        pr_commits_json = [
            {
                "sha": "abc123",
                "commit": {
                    "author": {
                        "name": "Dev One",
                        "email": "dev@example.com",
                        "date": "2025-06-01T10:00:00Z",
                    },
                    "message": "feat: add feature\n\nCo-Authored-By: Claude <noreply@anthropic.com>",
                },
            },
            {
                "sha": "def456",
                "commit": {
                    "author": {
                        "name": "Dev Two",
                        "email": "dev2@example.com",
                        "date": "2025-06-02T10:00:00Z",
                    },
                    "message": "fix: bug fix",
                },
            },
        ]

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            if "/pulls?" in url:
                resp.json.return_value = pr_list_json
            elif "/pulls/42/commits" in url:
                resp.json.return_value = pr_commits_json
            else:
                resp.json.return_value = []
            return resp

        fetcher._client = AsyncMock(spec=httpx.AsyncClient)
        fetcher._client.get = AsyncMock(side_effect=mock_get)

        count = await fetcher.fetch_repo_commits("myorg", "my-repo", "2025-01-01")
        assert count == 2

        # Verify commits are in DB
        rows = db.conn.execute("SELECT * FROM commits ORDER BY date").fetchall()
        assert len(rows) == 2
        assert rows[0]["sha"] == "abc123"


class TestEnrichCommits:
    @pytest.mark.asyncio
    async def test_enrich_commits(self, tmp_db):
        """enrich_commits fetches stats and updates commits."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_fake_token\n"

        with patch("borg.fetch.subprocess.run", return_value=mock_result):
            db = Database(tmp_db)
            db.org_add("myorg", "2025-01-01")
            fetcher = GitHubFetcher(db)

        # Insert an unenriched commit
        db.insert_commit(
            "abc123", "myorg", "my-repo", "Dev", "dev@x.com", "2025-06-01", "msg"
        )

        # Mock the commit detail response
        detail_response = MagicMock()
        detail_response.json.return_value = {
            "stats": {"additions": 42, "deletions": 7},
        }
        detail_response.status_code = 200
        detail_response.raise_for_status = MagicMock()

        # Mock rate limit response
        rate_response = MagicMock()
        rate_response.json.return_value = {
            "resources": {"core": {"remaining": 4000, "reset": 9999999999}},
        }
        rate_response.status_code = 200
        rate_response.raise_for_status = MagicMock()

        fetcher._client = AsyncMock(spec=httpx.AsyncClient)

        async def mock_get(url, **kwargs):
            if "rate_limit" in url:
                return rate_response
            return detail_response

        fetcher._client.get = AsyncMock(side_effect=mock_get)

        enriched = await fetcher.enrich_commits()
        assert enriched == 1

        row = db.conn.execute(
            "SELECT additions, deletions FROM commits WHERE sha = 'abc123'"
        ).fetchone()
        assert row["additions"] == 42
        assert row["deletions"] == 7


class TestCheckRateLimit:
    @pytest.mark.asyncio
    async def test_check_rate_limit(self, tmp_db):
        """check_rate_limit returns remaining and reset."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_fake_token\n"

        with patch("borg.fetch.subprocess.run", return_value=mock_result):
            db = Database(tmp_db)
            fetcher = GitHubFetcher(db)

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "resources": {"core": {"remaining": 4500, "reset": 1700000000}},
        }
        mock_response.status_code = 200
        mock_response.raise_for_status = MagicMock()

        fetcher._client = AsyncMock(spec=httpx.AsyncClient)
        fetcher._client.get = AsyncMock(return_value=mock_response)

        remaining, reset_epoch = await fetcher.check_rate_limit()
        assert remaining == 4500
        assert reset_epoch == 1700000000


class TestProgressCallback:
    def test_emit_calls_callback(self, tmp_db):
        """_emit calls the registered progress callback."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_fake_token\n"

        with patch("borg.fetch.subprocess.run", return_value=mock_result):
            db = Database(tmp_db)
            fetcher = GitHubFetcher(db)

        received = []
        fetcher.set_progress_callback(lambda p: received.append(p))
        fetcher._emit(FetchProgress(phase="repos", org="myorg"))
        assert len(received) == 1
        assert received[0].phase == "repos"

    def test_emit_without_callback_is_safe(self, tmp_db):
        """_emit does nothing when no callback is set."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_fake_token\n"

        with patch("borg.fetch.subprocess.run", return_value=mock_result):
            db = Database(tmp_db)
            fetcher = GitHubFetcher(db)

        # Should not raise
        fetcher._emit(FetchProgress(phase="done", org="myorg"))


class TestFetchPRCommits:
    """Tests for _fetch_pr_commits PR state handling."""

    def _make_fetcher(self, db):
        """Create a GitHubFetcher with mocked subprocess."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_fake_token\n"
        with patch("borg.fetch.subprocess.run", return_value=mock_result):
            return GitHubFetcher(db)

    def _make_pr(self, number, state, merged_at, base_ref, updated_at):
        """Build a PR dict matching GitHub API shape."""
        return {
            "number": number,
            "state": state,
            "merged_at": merged_at,
            "updated_at": updated_at,
            "base": {"ref": base_ref},
            "title": f"PR #{number}",
        }

    def _make_commit(self, sha):
        """Build a commit dict matching GitHub API shape."""
        return {
            "sha": sha,
            "commit": {
                "author": {
                    "name": "Dev",
                    "email": "dev@example.com",
                    "date": "2025-06-01T10:00:00Z",
                },
                "message": "some commit",
            },
        }

    @pytest.mark.asyncio
    async def test_merged_pr_to_main_sets_in_production(self, tmp_db):
        """Commits from PRs merged to main should have in_production=1."""
        db = Database(tmp_db)
        db.org_add("myorg", "2025-01-01")
        fetcher = self._make_fetcher(db)

        pr = self._make_pr(1, "closed", "2025-06-01T12:00:00Z", "main", "2025-06-01T12:00:00Z")
        commit = self._make_commit("aaa111")

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            if "/pulls?" in url:
                resp.json.return_value = [pr]
            elif "/pulls/1/commits" in url:
                resp.json.return_value = [commit]
            else:
                resp.json.return_value = []
            return resp

        fetcher._client = AsyncMock(spec=httpx.AsyncClient)
        fetcher._client.get = AsyncMock(side_effect=mock_get)

        inserted, _ = await fetcher._fetch_pr_commits("myorg", "my-repo", "2025-01-01")
        assert inserted == 1

        row = db.conn.execute("SELECT in_production, pr_state FROM commits WHERE sha = 'aaa111'").fetchone()
        assert row["in_production"] == 1
        assert row["pr_state"] == "merged"

    @pytest.mark.asyncio
    async def test_merged_pr_to_non_main_not_in_production(self, tmp_db):
        """Commits from PRs merged to uat/preprod should have in_production=0."""
        db = Database(tmp_db)
        db.org_add("myorg", "2025-01-01")
        fetcher = self._make_fetcher(db)

        pr = self._make_pr(2, "closed", "2025-06-01T12:00:00Z", "uat", "2025-06-01T12:00:00Z")
        commit = self._make_commit("bbb222")

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            if "/pulls?" in url:
                resp.json.return_value = [pr]
            elif "/pulls/2/commits" in url:
                resp.json.return_value = [commit]
            else:
                resp.json.return_value = []
            return resp

        fetcher._client = AsyncMock(spec=httpx.AsyncClient)
        fetcher._client.get = AsyncMock(side_effect=mock_get)

        inserted, _ = await fetcher._fetch_pr_commits("myorg", "my-repo", "2025-01-01")
        assert inserted == 1

        row = db.conn.execute("SELECT in_production, pr_state FROM commits WHERE sha = 'bbb222'").fetchone()
        assert row["in_production"] == 0
        assert row["pr_state"] == "merged"

    @pytest.mark.asyncio
    async def test_open_pr_state(self, tmp_db):
        """Open PR commits should have pr_state='open'."""
        db = Database(tmp_db)
        db.org_add("myorg", "2025-01-01")
        fetcher = self._make_fetcher(db)

        pr = self._make_pr(3, "open", None, "main", "2025-06-01T12:00:00Z")
        commit = self._make_commit("ccc333")

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            if "/pulls?" in url:
                resp.json.return_value = [pr]
            elif "/pulls/3/commits" in url:
                resp.json.return_value = [commit]
            else:
                resp.json.return_value = []
            return resp

        fetcher._client = AsyncMock(spec=httpx.AsyncClient)
        fetcher._client.get = AsyncMock(side_effect=mock_get)

        inserted, _ = await fetcher._fetch_pr_commits("myorg", "my-repo", "2025-01-01")
        assert inserted == 1

        row = db.conn.execute("SELECT in_production, pr_state FROM commits WHERE sha = 'ccc333'").fetchone()
        assert row["in_production"] == 0
        assert row["pr_state"] == "open"

    @pytest.mark.asyncio
    async def test_closed_unmerged_pr_state(self, tmp_db):
        """Closed but unmerged (abandoned) PR commits should have pr_state='closed'."""
        db = Database(tmp_db)
        db.org_add("myorg", "2025-01-01")
        fetcher = self._make_fetcher(db)

        pr = self._make_pr(4, "closed", None, "main", "2025-06-01T12:00:00Z")
        commit = self._make_commit("ddd444")

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            if "/pulls?" in url:
                resp.json.return_value = [pr]
            elif "/pulls/4/commits" in url:
                resp.json.return_value = [commit]
            else:
                resp.json.return_value = []
            return resp

        fetcher._client = AsyncMock(spec=httpx.AsyncClient)
        fetcher._client.get = AsyncMock(side_effect=mock_get)

        inserted, _ = await fetcher._fetch_pr_commits("myorg", "my-repo", "2025-01-01")
        assert inserted == 1

        row = db.conn.execute("SELECT in_production, pr_state FROM commits WHERE sha = 'ddd444'").fetchone()
        assert row["in_production"] == 0
        assert row["pr_state"] == "closed"

    @pytest.mark.asyncio
    async def test_stops_on_old_prs(self, tmp_db):
        """Should stop paginating when PRs are older than since date."""
        db = Database(tmp_db)
        db.org_add("myorg", "2025-01-01")
        fetcher = self._make_fetcher(db)

        recent_pr = self._make_pr(10, "closed", "2025-06-01T12:00:00Z", "main", "2025-06-01T12:00:00Z")
        old_pr = self._make_pr(11, "closed", "2024-06-01T12:00:00Z", "main", "2024-06-01T12:00:00Z")
        commit_recent = self._make_commit("eee555")
        commit_old = self._make_commit("fff666")

        async def mock_get(url, **kwargs):
            resp = MagicMock()
            resp.headers = {}
            resp.raise_for_status = MagicMock()
            if "/pulls?" in url:
                resp.json.return_value = [recent_pr, old_pr]
            elif "/pulls/10/commits" in url:
                resp.json.return_value = [commit_recent]
            elif "/pulls/11/commits" in url:
                resp.json.return_value = [commit_old]
            else:
                resp.json.return_value = []
            return resp

        fetcher._client = AsyncMock(spec=httpx.AsyncClient)
        fetcher._client.get = AsyncMock(side_effect=mock_get)

        inserted, _ = await fetcher._fetch_pr_commits("myorg", "my-repo", "2025-01-01")
        assert inserted == 1

        rows = db.conn.execute("SELECT sha FROM commits").fetchall()
        shas = [r["sha"] for r in rows]
        assert "eee555" in shas
        assert "fff666" not in shas


class TestFetchAll:
    """Tests for fetch_all orchestration."""

    def _make_fetcher(self, db):
        """Create a GitHubFetcher with mocked subprocess."""
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ghp_fake_token\n"
        with patch("borg.fetch.subprocess.run", return_value=mock_result):
            return GitHubFetcher(db)

    @pytest.mark.asyncio
    async def test_fetch_all_with_org_filter(self, tmp_db):
        """fetch_all with org filter should only fetch that org."""
        db = Database(tmp_db)
        db.org_add("org1", "2025-01-01")
        db.org_add("org2", "2025-01-01")
        fetcher = self._make_fetcher(db)

        fetched_orgs = []

        async def mock_fetch_repo_list(org):
            fetched_orgs.append(org)
            return []

        fetcher.fetch_repo_list = mock_fetch_repo_list

        # Mock rate limit for enrich_commits
        rate_response = MagicMock()
        rate_response.json.return_value = {
            "resources": {"core": {"remaining": 5000, "reset": 9999999999}},
        }
        rate_response.raise_for_status = MagicMock()
        fetcher._client = AsyncMock(spec=httpx.AsyncClient)
        fetcher._client.get = AsyncMock(return_value=rate_response)

        await fetcher.fetch_all(org_filter="org1")
        assert fetched_orgs == ["org1"]

    @pytest.mark.asyncio
    async def test_fetch_all_unknown_org_raises(self, tmp_db):
        """fetch_all with unknown org should raise ValueError."""
        db = Database(tmp_db)
        db.org_add("org1", "2025-01-01")
        fetcher = self._make_fetcher(db)

        with pytest.raises(ValueError, match="not found"):
            await fetcher.fetch_all(org_filter="nonexistent")

    @pytest.mark.asyncio
    async def test_fetch_all_no_orgs_raises(self, tmp_db):
        """fetch_all with no registered orgs should raise ValueError."""
        db = Database(tmp_db)
        fetcher = self._make_fetcher(db)

        with pytest.raises(ValueError, match="No orgs registered"):
            await fetcher.fetch_all()
