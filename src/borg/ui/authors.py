"""Authors tab — thin wrapper around RankingTab."""

from borg.db import Database
from borg.ui.rankings import RankingTab


class AuthorsTab(RankingTab):
    """Ranking table grouped by author."""

    def __init__(self, db: Database) -> None:
        """Initialize authors ranking.

        Args:
            db: Database instance.
        """
        super().__init__(db, "author", "Author")
