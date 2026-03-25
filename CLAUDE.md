# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Borg is a Bash CLI tool that tracks AI-generated code adoption across multiple GitHub organizations. It detects AI tool signatures in commit trailers (Co-Authored-By patterns), stores metadata in SQLite, and renders terminal reports with rankings and trends.

## Running

```bash
./borg org add <org> --since YYYY-MM-DD  # Register an org
./borg org list                           # Show registered orgs
./borg fetch [--org <name>]              # Fetch all orgs (or one)
./borg report [--org <name>] [--top N]   # Terminal report
./borg export [--org <name>] --csv out   # CSV export
./borg status [--org <name>]             # Show sync metadata
```

No build step, no package manager, no test suite. Pure Bash.

## Requirements

- `gh` (GitHub CLI, must be authenticated)
- `jq`
- `sqlite3`
- `gum` (optional, for styled terminal output and confirmations)

## Architecture

Three-phase pipeline: **Fetch → Detect → Report**

```
borg (CLI dispatcher)
├── lib/db.sh       – SQLite layer (WAL mode, schema, org CRUD)
├── lib/fetch.sh    – GitHub API fetching (two phases: list commits, then enrich with stats)
├── lib/detect.sh   – AI tool detection via regex on commit messages (12 tools)
├── lib/report.sh   – Terminal report rendering (rankings, trends, sparklines)
└── deps/spark      – Vendored sparkline utility
```

**Data flow:** `fetch_commits()` → `enrich_commits()` → `detect_ai()` → `report_show()`

**Database:** SQLite in `data/tracker.db` with four tables:
- `orgs` – registered organizations with floor dates
- `commits` – commit metadata + AI detection results (org + repo per row)
- `repo_sync` – per-org/repo sync bookmarks for incremental fetching (composite PK: org, repo)
- `sync_meta` – key-value config (last run time)

## Key Design Patterns

- **Multi-org:** Orgs registered via `borg org add`, all commands support `--org` filter. `fetch` loops all orgs by default.
- **Incremental sync:** Per-repo bookmarks in `repo_sync` allow resumable fetching; `INSERT OR IGNORE` ensures idempotency
- **Rate limiting:** Adaptive parallelism (8 → 4 → wait) based on GitHub API rate limit headers
- **AI detection:** Runs in a single transaction; resets + re-detects so rule changes apply retroactively. First-match-wins via `WHERE ai_tool IS NULL`
- **Parallel enrichment:** Uses temp files + batch DB update to avoid concurrent SQLite write issues. Failed enrichments leave rows as NULL for retry on next run
- **SQL safety:** `sql_escape()` in `db.sh` (shared across all modules) for string interpolation; input validation for `--top`, `--since` in CLI
- **Error handling:** API failures log warnings to stderr instead of silently returning fake data
- **Report filtering:** All queries use `WHERE $org_where` pattern (`1=1` for all, `org = '...'` for filtered)

## Conventions

- All scripts use `set -euo pipefail`
- Functions follow `module_action` naming (e.g., `db_init`, `fetch_commits`, `detect_ai`)
- Database path passed via `DB` variable (defaults to `data/tracker.db`)
- Shared helpers (`sql_escape`, `utc_now`) live in `db.sh` since it's sourced first
