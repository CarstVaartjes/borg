# Borg

> "Resistance is futile"

Track AI-generated code adoption across GitHub organizations. Fetches commit history, detects AI-assisted commits via `Co-Authored-By` trailers, and renders terminal reports with rankings and trends.

## Quick Start

```bash
# Register an org
./borg org add myorg --since 2026-01-01

# Fetch commits
./borg fetch

# View report
./borg report

# Add more orgs
./borg org add anotherorg --since 2026-02-01

# Fetch all orgs, or just one
./borg fetch
./borg fetch --org myorg
```

## Commands

| Command | Description |
|---------|-------------|
| `borg org add <name> [--since]` | Register a GitHub org (default: 90 days ago) |
| `borg org remove <name> [--force]` | Unregister org and delete its data |
| `borg org list` | Show registered organizations |
| `borg fetch [--org]` | Fetch commits (all orgs, or one) |
| `borg report [--org] [--top]` | Show AI adoption report with rankings and trends |
| `borg export [--org] [--csv]` | Export database to CSV |
| `borg status [--org]` | Show sync status |

### Options

| Flag | Default | Description |
|------|---------|-------------|
| `--org` | all registered orgs | Filter to a specific organization |
| `--since` | 90 days ago | Floor date YYYY-MM-DD (for `org add`) |
| `--top` | `10` | Number of entries in rankings |
| `--db` | `<script_dir>/data/tracker.db` | Database path |
| `--csv` | stdout | CSV export path |
| `--force` | | Skip confirmation on destructive operations |

## How It Works

### Fetch (two phases)

**Phase 1 — List commits** (cheap: ~1 API call per 100 commits)
- Lists all non-archived repos in each registered org
- Fetches commits since the last sync date (or `--since` from org registration)
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
| Devin | `devin-ai[bot]` author/email or trailer | high |
| Cody | `Co-Authored-By:.*Cody.*sourcegraph` or `noreply@sourcegraph.com` | high |
| Amazon Q | `Co-Authored-By:.*Amazon Q` | high |
| Windsurf | `Co-Authored-By:.*Windsurf` | high |
| Codeium | `Co-Authored-By:.*Codeium` | high |
| Tabnine | `Co-Authored-By:.*Tabnine` | high |
| Bulk addition | `additions > 100 AND deletions < 10` | low |

### Report

Shows (combined across all orgs, or filtered with `--org`):
- Summary (total commits, AI-assisted count/percentage, LOC stats)
- Breakdown by AI tool
- Top/bottom N authors by AI commits and by AI LOC
- Top/bottom N repos by AI commits and by AI LOC
- Monthly trend with sparklines
- Weekly trend with sparklines

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
| `gum` | `brew install gum` (optional, for styled output) |

## Data Storage

All data is stored in a local SQLite database (`./data/tracker.db`). The database tracks:
- Multiple GitHub organizations with per-org floor dates
- All commits with full metadata and AI classification
- Per-repo sync state for incremental fetching

Export to CSV anytime: `./borg export --csv output.csv`

## License

MIT
