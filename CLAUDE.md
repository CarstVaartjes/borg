# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Borg is a Python TUI (Textual) that tracks AI-generated code adoption across multiple GitHub organizations. It fetches commits from pull requests (not the default branch) to preserve `Co-Authored-By` trailers that get stripped by squash merges. Detection uses three confidence levels: high (trailers), medium (structured message style), low (prefix heuristics). All interaction happens inside the TUI — no CLI subcommands.

## Running

```bash
uv sync          # install dependencies
uv run borg      # launch TUI
uv run pytest -v # run tests (99 tests)
```

## Architecture

```
src/borg/
├── cli.py          # Typer entry point → launches TUI
├── db.py           # SQLite layer (Database class)
├── detect.py       # AI detection (data-driven RULES + heuristics)
├── fetch.py        # Async GitHub API fetcher (httpx)
└── ui/
    ├── app.py           # Textual App with 8-tab layout
    ├── overview.py      # Summary stats (commits + LOC %), Skynet Employee, tool chart
    ├── rankings.py      # Reusable sortable DataTable (commits + LOC columns)
    ├── authors.py       # Authors ranking (thin wrapper)
    ├── repos.py         # Repos ranking (thin wrapper)
    ├── trends.py        # Plotext line charts (monthly + weekly)
    ├── fetch_tab.py     # Unified Fetch & Detect tab
    ├── export_tab.py    # CSV export
    ├── identity_tab.py  # Author identity management (auto + manual aliases)
    ├── orgs_tab.py      # Org management (add/remove)
    └── commit_modal.py  # Commit detail popup (opens GitHub on Enter)
```

## Data Flow

```
GitHubFetcher.fetch_all()
  → list repos for each org
  → per repo: collect all PRs (merged + open + closed) updated since last sync
  → per PR: fetch individual commits (preserves Co-Authored-By trailers)
  → INSERT OR IGNORE into commits table (dedup by SHA)
  → skip commits before org floor date
  → if PR targets main/master: promote in_production = 1
  → enrich unenriched commits with additions/deletions (parallel, batches of 100)
  → detect_ai() runs detection rules in transaction
  → rebuild_author_identities() merges authors via union-find + manual aliases
  → UI tabs query SQLite for reports
```

## Database Schema

SQLite with 5 tables + 1 computed:
- `orgs` — registered organizations with floor dates
- `commits` — commit metadata + AI detection + `in_production` flag + `pr_number` + `pr_state`
- `repo_sync` — per-org/repo sync bookmarks with `last_synced_at` for incremental PR fetching
- `sync_meta` — key-value config (last run time)
- `author_aliases` — manual email → canonical_name mappings (persistent)
- `_author_identity` — computed table: email → canonical_name (rebuilt during detection)

## Key Design Patterns

- **PR-based fetching:** Fetches commits from PRs, not the default branch. Preserves `Co-Authored-By` trailers that squash merge strips. All PR states included (merged, open, closed).
- **Three-tier detection:** High (trailers), medium (structured message: summary + blank line + body), low (conventional commit prefixes, Jira tickets, bulk additions). Data-driven RULES list + SQL heuristics.
- **Noise filtering:** `_org_filter()` automatically excludes merge commits, reverts, and conflict resolutions from all queries.
- **Author identity resolution:** Union-find algorithm transitively merges by shared name or email. Manual aliases in `author_aliases` table override and propagate. Fuzzy suggestions detect likely merges via substring/word matching.
- **Production tracking:** `in_production` starts at 0, promoted to 1 when commit appears in PR merged to main/master.
- **Incremental fetching:** Uses `last_synced_at` per repo to only process PRs updated since last fetch. Commits before org floor date skipped at insert time.
- **Enrichment with retry:** Fetches additions/deletions in batches of 100 with adaptive parallelism (8→4→wait). Stops on full batch failure; unenriched commits retry next run.
- **Parameterized queries** everywhere — no string interpolation for SQL
- **Async fetch** with httpx, progress callbacks for TUI via `FetchProgress` dataclass
- **Textual workers** for long-running fetch operations (`@work` decorator)
- **Tab refresh on switch** — each tab's `refresh_data(org)` called on activation

## Conventions

- Python 3.11+ type hints throughout
- Tests in `tests/` with pytest, `tmp_db` fixture for temp databases, `fixture.db` for integration tests
- `uv sync` / `uv run` for all operations
- UI widgets inherit from `Static`, take `Database` in constructor
- GitHub auth: reads token from `gh auth token` at startup
- Fetch & Detect are unified in one tab; detection always runs after fetch
