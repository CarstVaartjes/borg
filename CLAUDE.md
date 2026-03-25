# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Borg is a Bash CLI tool that tracks AI-generated code adoption across GitHub organizations. It detects AI tool signatures in commit trailers (Co-Authored-By patterns), stores metadata in SQLite, and renders terminal reports with rankings and trends.

## Running

```bash
./borg fetch --org <org> --since YYYY-MM-DD   # Fetch commits from GitHub
./borg report [--top N]                        # Terminal report with rankings/trends
./borg export --csv output.csv                 # CSV export
./borg status                                  # Show sync metadata
```

No build step, no package manager, no test suite. Pure Bash.

## Requirements

- `gh` (GitHub CLI, must be authenticated)
- `jq`
- `sqlite3`
- `gum` (optional, for styled terminal output)

## Architecture

Three-phase pipeline: **Fetch → Detect → Report**

```
borg (CLI dispatcher)
├── lib/db.sh       – SQLite layer (WAL mode, schema, CRUD)
├── lib/fetch.sh    – GitHub API fetching (two phases: list commits, then enrich with stats)
├── lib/detect.sh   – AI tool detection via regex on commit messages (12 tools)
├── lib/report.sh   – Terminal report rendering (rankings, trends, sparklines)
└── deps/spark      – Vendored sparkline utility
```

**Data flow:** `fetch_commits()` → `enrich_commits()` → `detect_ai()` → `report_show()`

**Database:** SQLite in `data/tracker.db` with three tables:
- `commits` – commit metadata + AI detection results
- `repo_sync` – per-repo sync bookmarks for incremental fetching
- `sync_meta` – key-value config (org, since date, last run)

## Key Design Patterns

- **Incremental sync:** Per-repo bookmarks in `repo_sync` allow resumable fetching; `INSERT OR IGNORE` ensures idempotency
- **Rate limiting:** Adaptive parallelism (8 → 4 → wait) based on GitHub API rate limit headers
- **AI detection:** Runs in a single transaction; resets + re-detects so rule changes apply retroactively. First-match-wins via `WHERE ai_tool IS NULL`
- **Parallel enrichment:** Uses temp files + batch DB update to avoid concurrent SQLite write issues. Failed enrichments leave rows as NULL for retry on next run
- **SQL safety:** `sql_escape()` in `db.sh` (shared across all modules) for string interpolation; input validation for `--top`, `--since` in CLI
- **Error handling:** API failures log warnings to stderr instead of silently returning fake data

## Conventions

- All scripts use `set -euo pipefail`
- Functions follow `module_action` naming (e.g., `db_init`, `fetch_commits`, `detect_ai`)
- Database path passed via `DB` variable (defaults to `data/tracker.db`)
