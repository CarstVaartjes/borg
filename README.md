# Borg

> "Resistance is futile"

Track AI-generated code adoption across a GitHub organization. Fetches commit history, detects AI-assisted commits via `Co-Authored-By` trailers, and renders terminal reports with rankings and trends.

## Quick Start

```bash
# First run — fetches all commits since Jan 1
./borg fetch --org myorg --since 2026-01-01

# View report
./borg report

# Incremental update (remembers org and since date)
./borg fetch
```

## Commands

| Command | Description |
|---------|-------------|
| `borg fetch` | Fetch commits from GitHub (incremental, rate-limit aware) |
| `borg report` | Show AI adoption report with rankings and trends |
| `borg export` | Export database to CSV |
| `borg status` | Show sync status |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--org` | remembered after first run | GitHub organization |
| `--since` | remembered after first run | Floor date (YYYY-MM-DD) |
| `--top` | `10` | Number of entries in rankings |
| `--db` | `./data/tracker.db` | Database path |
| `--csv` | stdout | CSV export path |

## How It Works

### Fetch (two phases)

**Phase 1 — List commits** (cheap: ~1 API call per 100 commits)
- Lists all non-archived repos in the org
- Fetches commits since the last sync date (or `--since` on first run)
- Stores commit metadata in SQLite

**Phase 2 — Enrich with stats** (expensive: 1 API call per commit)
- Fetches additions/deletions for each commit
- Adaptive parallelism based on rate limit remaining
- Auto-waits when rate limit is hit, resumes automatically

Both phases are **incremental and resumable**. If interrupted, re-running picks up where it left off.

### AI Detection

Detects AI-assisted commits by matching `Co-Authored-By` trailers in commit messages. Runs locally — no API calls.

| Tool | Detection Pattern | Confidence |
|------|------------------|------------|
| Claude | `Co-Authored-By:.*Claude` or `noreply@anthropic.com` | high |
| Copilot | `Co-Authored-By:.*Copilot` or `copilot[bot]` author | high |
| Cursor | `Co-Authored-By:.*Cursor` | high |
| Aider | `(aider)` in author name | high |
| ChatGPT | `Co-Authored-By:.*(ChatGPT\|OpenAI)` | high |
| Devin | `Co-Authored-By:.*Devin` or `devin-ai[bot]` | high |
| Cody | `Co-Authored-By:.*Cody` | high |
| Amazon Q | `Co-Authored-By:.*Amazon Q` | high |
| Windsurf | `Co-Authored-By:.*Windsurf` | high |
| Codeium | `Co-Authored-By:.*Codeium` | high |
| Tabnine | `Co-Authored-By:.*Tabnine` | high |
| Bulk addition | `additions > 100 AND deletions < 10` | low |

### Report

Shows:
- Summary (total commits, AI-assisted count/percentage, LOC stats)
- Breakdown by AI tool
- Top/bottom N authors by AI commits and by AI LOC
- Top/bottom N repos by AI commits and by AI LOC
- Monthly trend with sparklines

### Rate Limit Handling

GitHub allows 5,000 API calls/hour. Borg monitors usage and adapts:

| Remaining | Behavior |
|-----------|----------|
| > 500 | 8 parallel fetches |
| 200-500 | 4 parallel fetches |
| < 200 | Auto-wait until reset, then resume |

A single `borg fetch` always runs to completion, no matter how many commits.

## Requirements

| Tool | Install |
|------|---------|
| `gh` | `brew install gh` (must be authenticated) |
| `jq` | `brew install jq` |
| `sqlite3` | Pre-installed on macOS |
| `gum` | `brew install gum` |

## Data Storage

All data is stored in a local SQLite database (`./data/tracker.db`). The database tracks:
- All commits with full metadata and AI classification
- Per-repo sync state for incremental fetching
- Configuration (org, since date, last run time)

Export to CSV anytime: `./borg export --csv output.csv`

## License

MIT
