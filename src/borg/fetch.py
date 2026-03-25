"""Async GitHub fetch layer for borg tracker.

Fetches repos, commits, and enrichment stats from the GitHub API
using httpx.AsyncClient, with rate limiting and progress callbacks.
"""

import asyncio
import logging
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Callable

import httpx

from borg.db import Database

logger = logging.getLogger(__name__)

BASE_URL = "https://api.github.com"


@dataclass
class FetchProgress:
    """Progress update from the fetch layer.

    Attributes:
        phase: Current phase — repos, commits, enrich, rate_limit, done.
        org: Organization being processed.
        repo: Repository being processed (if applicable).
        current: Current item index.
        total: Total items to process.
        message: Human-readable status message.
    """

    phase: str  # "repos", "commits", "enrich", "rate_limit", "done"
    org: str
    repo: str = ""
    current: int = 0
    total: int = 0
    message: str = ""


class GitHubFetcher:
    """Async GitHub API client with rate limiting and progress reporting.

    Reads a GitHub token from the gh CLI, then uses httpx.AsyncClient
    for all HTTP calls. Supports progress callbacks for TUI integration.
    """

    def __init__(self, db: Database) -> None:
        """Initialize fetcher, reading token from gh CLI.

        Args:
            db: Database instance for storing fetched data.

        Raises:
            RuntimeError: If gh CLI is not found or not authenticated.
        """
        self._db = db
        self._callback: Callable[[FetchProgress], None] | None = None
        self._token = self._read_token()
        self._client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/vnd.github+json",
            },
            timeout=30.0,
        )

    @staticmethod
    def _read_token() -> str:
        """Read GitHub token from gh CLI.

        Returns:
            The GitHub authentication token.

        Raises:
            RuntimeError: If gh CLI is missing or not authenticated.
        """
        try:
            result = subprocess.run(
                ["gh", "auth", "token"],
                capture_output=True,
                text=True,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "gh CLI not found — install it from https://cli.github.com"
            )

        if result.returncode != 0 or not result.stdout.strip():
            raise RuntimeError("gh CLI not authenticated — run 'gh auth login' first")

        return result.stdout.strip()

    def set_progress_callback(self, callback: Callable[[FetchProgress], None]) -> None:
        """Register a callback to receive progress updates.

        Args:
            callback: Function that accepts a FetchProgress instance.
        """
        self._callback = callback

    def _emit(self, progress: FetchProgress) -> None:
        """Send a progress update to the registered callback.

        Args:
            progress: FetchProgress instance to send.
        """
        if self._callback is not None:
            self._callback(progress)

    async def check_rate_limit(self) -> tuple[int, int]:
        """Check GitHub API rate limit status.

        Returns:
            Tuple of (remaining_requests, reset_epoch_seconds).
        """
        resp = await self._client.get(f"{BASE_URL}/rate_limit")
        resp.raise_for_status()
        data = resp.json()
        core = data["resources"]["core"]
        return core["remaining"], core["reset"]

    async def wait_for_rate_limit(self, min_remaining: int = 200) -> int:
        """Wait until enough rate limit budget is available.

        Args:
            min_remaining: Minimum remaining requests before proceeding.

        Returns:
            Current remaining requests after wait.
        """
        while True:
            remaining, reset_epoch = await self.check_rate_limit()
            if remaining >= min_remaining:
                return remaining

            wait_seconds = max(reset_epoch - int(time.time()), 1)
            self._emit(
                FetchProgress(
                    phase="rate_limit",
                    org="",
                    message=f"Rate limited — waiting {wait_seconds}s ({remaining} remaining)",
                )
            )
            logger.info(
                "Rate limited: %d remaining, waiting %ds", remaining, wait_seconds
            )
            await asyncio.sleep(wait_seconds)

    @staticmethod
    def _parse_next_url(headers: dict) -> str | None:
        """Parse the 'next' URL from a Link header.

        Args:
            headers: Response headers dict.

        Returns:
            Next page URL, or None if no more pages.
        """
        link = headers.get("link", "")
        match = re.search(r'<([^>]+)>;\s*rel="next"', link)
        return match.group(1) if match else None

    async def fetch_repo_list(self, org: str) -> list[str]:
        """Fetch non-archived repositories for an organization.

        Args:
            org: GitHub organization name.

        Returns:
            List of repository names (excluding archived repos).
        """
        repos: list[str] = []
        url = f"{BASE_URL}/orgs/{org}/repos?per_page=100&type=all"

        while url:
            self._emit(
                FetchProgress(
                    phase="repos",
                    org=org,
                    message=f"Fetching repos ({len(repos)} so far)",
                )
            )
            resp = await self._client.get(url)
            resp.raise_for_status()
            data = resp.json()
            for repo in data:
                if not repo.get("archived", False):
                    repos.append(repo["name"])

            url = self._parse_next_url(resp.headers)

        return repos

    async def fetch_repo_commits(self, org: str, repo: str, since: str) -> int:
        """Fetch commits for a repo since a given date.

        Paginates through all commits, inserts new ones into the database,
        and updates the repo_sync bookmark.

        Args:
            org: Organization name.
            repo: Repository name.
            since: ISO date string to fetch commits from.

        Returns:
            Number of new commits inserted.
        """
        # Use bookmark if available, otherwise fall back to since
        bookmark = self._db.get_repo_bookmark(org, repo)
        since_date = bookmark or since

        inserted = 0
        newest_date: str | None = None
        url = f"{BASE_URL}/repos/{org}/{repo}/commits?per_page=100&since={since_date}"

        while url:
            self._emit(
                FetchProgress(
                    phase="commits",
                    org=org,
                    repo=repo,
                    current=inserted,
                    message=f"Fetching commits for {repo}",
                )
            )
            resp = await self._client.get(url)
            resp.raise_for_status()
            commits = resp.json()

            for c in commits:
                commit_data = c["commit"]
                author = commit_data["author"]
                date = author["date"]

                was_new = self._db.insert_commit(
                    sha=c["sha"],
                    org=org,
                    repo=repo,
                    author=author["name"],
                    email=author["email"],
                    date=date,
                    message=commit_data.get("message", ""),
                )
                if was_new:
                    inserted += 1
                    if newest_date is None or date > newest_date:
                        newest_date = date

            url = self._parse_next_url(resp.headers)

        # Update repo sync bookmark
        if newest_date:
            existing_count = self._db.get_repo_commit_count(org, repo)
            self._db.update_repo_sync(org, repo, newest_date, existing_count + inserted)

        return inserted

    async def enrich_commits(self) -> int:
        """Enrich unenriched commits with additions/deletions stats.

        Fetches commit details in parallel using a semaphore to control
        concurrency. Failed enrichments are skipped, not written as 0.

        Returns:
            Number of commits successfully enriched.
        """
        remaining, _ = await self.check_rate_limit()
        max_concurrent = 8 if remaining > 1000 else 4
        sem = asyncio.Semaphore(max_concurrent)

        commits = self._db.get_unenriched_commits(limit=100)
        if not commits:
            return 0

        enriched = 0
        total = len(commits)

        async def _enrich_one(commit: dict) -> bool:
            async with sem:
                try:
                    url = f"{BASE_URL}/repos/{commit['org']}/{commit['repo']}/commits/{commit['sha']}"
                    resp = await self._client.get(url)
                    resp.raise_for_status()
                    data = resp.json()
                    stats = data.get("stats", {})
                    additions = stats.get("additions")
                    deletions = stats.get("deletions")
                    if additions is not None and deletions is not None:
                        self._db.update_commit_stats(
                            commit["sha"], additions, deletions
                        )
                        return True
                except Exception:
                    logger.warning("Failed to enrich commit %s", commit["sha"])
                return False

        tasks = [_enrich_one(c) for c in commits]
        results = await asyncio.gather(*tasks)
        enriched = sum(1 for r in results if r)

        self._emit(
            FetchProgress(
                phase="enrich",
                org="",
                current=enriched,
                total=total,
                message=f"Enriched {enriched}/{total} commits",
            )
        )

        return enriched

    async def fetch_all(self, org_filter: str | None = None) -> None:
        """Run a full fetch cycle: repos, commits, enrichment.

        Args:
            org_filter: If set, only fetch for this organization.
        """
        orgs = self._db.org_get_all()
        if org_filter:
            orgs = [o for o in orgs if o["name"] == org_filter]

        for org_row in orgs:
            org = org_row["name"]
            since = org_row["since_date"]

            self._emit(
                FetchProgress(
                    phase="repos", org=org, message=f"Fetching repos for {org}"
                )
            )
            repos = await self.fetch_repo_list(org)

            for i, repo in enumerate(repos):
                self._emit(
                    FetchProgress(
                        phase="commits",
                        org=org,
                        repo=repo,
                        current=i + 1,
                        total=len(repos),
                        message=f"Fetching {repo} ({i + 1}/{len(repos)})",
                    )
                )
                await self.fetch_repo_commits(org, repo, since)

        # Enrich all unenriched commits
        self._emit(FetchProgress(phase="enrich", org="", message="Enriching commits"))
        await self.enrich_commits()

        # Record completion
        self._db.set_meta("last_run_at", Database._utc_now())
        self._emit(FetchProgress(phase="done", org="", message="Fetch complete"))

    async def close(self) -> None:
        """Close the underlying HTTP client."""
        await self._client.aclose()
