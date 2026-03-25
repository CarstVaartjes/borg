"""Repos tab — thin wrapper around RankingTab."""

from borg.db import Database
from borg.ui.rankings import RankingTab


class ReposTab(RankingTab):
    """Ranking table grouped by repo."""

    def __init__(self, db: Database) -> None:
        """Initialize repos ranking.

        Args:
            db: Database instance.
        """
        super().__init__(db, "repo", "Repo")
