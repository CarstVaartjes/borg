# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Borg is a Python TUI (Textual) that tracks AI-generated code adoption across multiple GitHub organizations. It detects AI tool signatures in commit trailers, stores metadata in SQLite, and provides interactive charts and rankings.

## Running

```bash
uv sync          # install dependencies
uv run borg      # launch TUI
uv run pytest -v # run tests
```

## Architecture

```
src/borg/
├── cli.py          # Typer entry point → launches TUI
├── db.py           # SQLite layer (Database class)
├── detect.py       # AI detection (data-driven RULES list)
├── fetch.py        # Async GitHub API fetcher (httpx)
└── ui/
    ├── app.py      # Textual App with 8-tab layout
    ├── overview.py # Summary stats, Skynet Employee, tool chart
    ├── rankings.py # Reusable sortable DataTable widget
    ├── authors.py  # Authors ranking (thin wrapper)
    ├── repos.py    # Repos ranking (thin wrapper)
    ├── trends.py   # Plotext line charts (monthly + weekly)
    ├── fetch_tab.py    # Fetch trigger + progress log
    ├── detect_tab.py   # Detection rules + re-run
    ├── export_tab.py   # CSV export
    └── orgs_tab.py     # Org management (add/remove)
```

**Data flow:** `GitHubFetcher.fetch_all()` → `detect_ai()` → report queries in UI tabs

**Database:** SQLite with 4 tables:
- `orgs` — registered organizations with floor dates
- `commits` — commit metadata + AI detection (org + repo per row)
- `repo_sync` — per-org/repo sync bookmarks (composite PK: org, repo)
- `sync_meta` — key-value config

## Key Design Patterns

- **Parameterized queries** everywhere — no string interpolation for SQL
- **`_org_filter(org)`** helper returns `(where_clause, params_tuple)` for optional org filtering
- **Data-driven detection** — RULES list in detect.py, applied in transaction
- **Async fetch** with httpx, progress callbacks for TUI integration
- **Textual workers** for long-running fetch operations (@work decorator)
- **Tab refresh on switch** — each tab's refresh_data(org) is called on activation

## Conventions

- Python 3.11+ type hints throughout
- Tests in `tests/` with pytest, `tmp_db` fixture for temp databases
- `uv sync` / `uv run` for all operations
- UI widgets inherit from Static, take Database in constructor
