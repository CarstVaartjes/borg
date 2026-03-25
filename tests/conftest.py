"""Shared test fixtures."""
from pathlib import Path

import pytest


@pytest.fixture
def tmp_db(tmp_path: Path) -> Path:
    """Provide a temporary database path."""
    return tmp_path / "test.db"
