# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Borg is a Python TUI (Textual) that tracks AI-generated code adoption across multiple GitHub organizations. It fetches commits from pull requests (not the default branch) to preserve `Co-Authored-By` trailers that get stripped by squash merges. All interaction happens inside the TUI — no CLI subcommands.

## Running

```bash
uv sync          # install dependencies
uv run borg      # launch TUI
uv run pytest -v # run tests (59 tests)
```

## Architecture

```
src/borg/
├── cli.py          # Typer entry point → launches TUI
├── db.py           # SQLite layer (Database class)
├── detect.py       # AI detection (data-driven RULES list)
├── fetch.py        # Async GitHub API fetcher (httpx)
└── ui/
    ├── app.py          # Textual App with 8-tab layout
    ├── overview.py     # Summary stats, Skynet Employee, tool chart
    ├── rankings.py     # Reusable sortable DataTable widget
    ├── authors.py      # Authors ranking (thin wrapper)
    ├── repos.py        # Repos ranking (thin wrapper)
    ├── trends.py       # Plotext line charts (monthly + weekly)
    ├── fetch_tab.py    # Fetch trigger + progress log
    ├── detect_tab.py   # Detection rules + re-run
    ├── export_tab.py   # CSV export
    └── orgs_tab.py     # Org management (add/remove)
```

## Data Flow

```
GitHubFetcher.fetch_all()
  → list repos for each org
  → per repo: list all PRs (merged + open + closed)
  → per PR: fetch individual commits (preserves Co-Authored-By trailers)
  → INSERT OR IGNORE into commits table (dedup by SHA)
  → if PR targets main/master: promote in_production = 1
  → enrich unenriched commits with additions/deletions (parallel)
  → detect_ai() runs detection rules in transaction
  → UI tabs query SQLite for reports
```

## Database Schema

SQLite with 4 tables:
- `orgs` — registered organizations with floor dates
- `commits` — commit metadata + AI detection + `in_production` flag + `pr_number` + `pr_state`
- `repo_sync` — per-org/repo sync bookmarks (composite PK: org, repo)
- `sync_meta` — key-value config (last run time)

**Author grouping:** Rankings group by email (not author name) to merge aliases. The most common display name per email is shown.

## Key Design Patterns

- **PR-based fetching:** Fetches commits from PRs, not the default branch. This preserves `Co-Authored-By` trailers that squash merge strips. All PR states included (merged, open, closed).
- **Production tracking:** `in_production` starts at 0, promoted to 1 when a commit appears in a PR merged to main/master. In squash-merge workflows, original PR commits stay at 0 (expected — the squash creates a new SHA).
- **Two-phase fetch:** First collects all PR metadata (for exact progress count), then fetches commits per PR with `x/y` progress.
- **Parameterized queries** everywhere — no string interpolation for SQL
- **`_org_filter(org)`** helper returns `(where_clause, params_tuple)` for optional org filtering
- **Data-driven detection** — RULES list in detect.py, applied in transaction with rollback on error
- **Async fetch** with httpx, progress callbacks for TUI integration via `FetchProgress` dataclass
- **Textual workers** for long-running fetch operations (`@work` decorator)
- **Tab refresh on switch** — each tab's `refresh_data(org)` is called on activation

## Conventions

- Python 3.11+ type hints throughout
- Tests in `tests/` with pytest, `tmp_db` fixture for temp databases
- `uv sync` / `uv run` for all operations
- UI widgets inherit from `Static`, take `Database` in constructor
- GitHub auth: reads token from `gh auth token` at startup (requires `gh` CLI authenticated)
