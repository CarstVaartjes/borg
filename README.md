# Borg

> "Resistance is futile"

Track AI-generated code adoption across GitHub organizations. Interactive TUI with charts, rankings, and trend analysis.

## Install

```bash
# Requires Python 3.11+, uv, and gh CLI (authenticated)
uv sync
uv run borg
```

Or install globally:

```bash
uv tool install .
borg
```

## Usage

Launch the TUI:

```bash
borg                          # uses default db (~/.local/share/borg/tracker.db)
borg --db path/to/tracker.db  # custom db location
```

Everything happens inside the TUI — no subcommands needed.

### Tabs

| # | Tab | Description |
|---|-----|-------------|
| 1 | **Overview** | Assimilation Progress, Skynet Employee of the Week, tool chart |
| 2 | **Authors** | Sortable ranking table by AI commits and LOC |
| 3 | **Repos** | Sortable ranking table by AI commits and LOC |
| 4 | **Trends** | Monthly and weekly AI adoption % line charts |
| 5 | **Fetch** | Trigger GitHub fetch with real-time progress log |
| 6 | **Detect** | View detection rules, re-run AI detection |
| 7 | **Export** | Export data to CSV |
| 8 | **Orgs** | Add/remove GitHub organizations |

### Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `1-8` | Switch tabs |
| `/` | Focus org filter |
| `q` | Quit |

### Getting Started

1. Launch `borg`
2. Go to **Orgs** tab (press `8`)
3. Add a GitHub organization with a floor date
4. Go to **Fetch** tab (press `5`) and click "Start Fetch"
5. Explore results in Overview, Authors, Repos, and Trends tabs

## How It Works

### Fetching — PR-Based Approach

Borg fetches commits from **pull requests**, not from the default branch. This is critical for organizations that use squash merges, because GitHub's squash merge creates a new commit on main that **strips `Co-Authored-By` trailers** from the original commits. By fetching the individual PR commits, borg recovers the AI tool signatures that would otherwise be lost.

**Fetch flow per repo:**
1. List all PRs (merged, open, and closed) updated since the floor date
2. For each PR, fetch its individual commits via `/pulls/{number}/commits`
3. Insert commits into SQLite (`INSERT OR IGNORE` deduplicates by SHA)
4. After all repos: enrich commits with additions/deletions stats (parallel)
5. Run AI detection on all commits

**All PR states are included** — merged, open, and abandoned (closed without merge) — because this tracks development effort, not just what shipped to production.

### Production Tracking

Each commit has an `in_production` flag:
- **`0` (default)** — commit exists in a PR but hasn't reached main/master
- **`1`** — the PR was merged into main or master

A commit can flow through multiple PRs (feature → uat → preprod → main). It starts at `0` and gets promoted to `1` when any PR targeting main/master is processed. Since squash merges create new SHAs, the original PR commits will typically remain `in_production = 0` in squash-merge workflows — this is expected.

### Author Grouping

Authors are grouped by **email address**, not display name. This automatically merges aliases (e.g. `ctselas7` and `Christos Tselas` using the same email). The most frequently used display name is shown in rankings.

### AI Detection

Detects AI-assisted commits by matching `Co-Authored-By` trailers in commit messages. Runs locally — no API calls. Detection runs inside a transaction so rule changes apply retroactively without data loss.

| Tool | Detection Pattern | Confidence |
|------|------------------|------------|
| Claude | `Co-Authored-By:.*Claude` or `noreply@anthropic.com` | high |
| Copilot | `Co-Authored-By:.*Copilot` or `copilot[bot]` author | high |
| Cursor | `Co-Authored-By:.*Cursor` or `noreply@cursor.com` | high |
| Aider | `(aider)` in author name | high |
| ChatGPT | `Co-Authored-By:.*(ChatGPT\|OpenAI)` | high |
| Devin | `devin-ai[bot]` author/email | high |
| Cody | `Co-Authored-By:.*Cody.*sourcegraph` | high |
| Amazon Q | `Co-Authored-By:.*Amazon Q` | high |
| Windsurf | `Co-Authored-By:.*Windsurf` | high |
| Codeium | `Co-Authored-By:.*Codeium` | high |
| Tabnine | `Co-Authored-By:.*Tabnine` | high |
| Bulk addition | `additions > 100 AND deletions < 10` | low |

### Known Limitations

- **Squash merges hide trailers**: If your org uses squash merges, the individual PR commits have the trailers but the squash commit on main doesn't. Borg fetches PR commits to work around this, but `in_production` tracking is limited since the original SHAs never appear on main.
- **No trailer = no detection**: If a developer uses an AI tool but commits without the `Co-Authored-By` trailer (e.g. manually writing the commit message), borg can't detect it.
- **PR commits endpoint has no `since` filter**: The GitHub `/pulls/{n}/commits` API returns all commits in a PR. For long-lived PRs opened before the floor date, some older commits may be included.

### Rate Limit Handling

GitHub allows 5,000 API calls/hour. Borg monitors usage and adapts:

| Remaining | Behavior |
|-----------|----------|
| > 1,000 | 8 parallel enrichment fetches |
| 200-1,000 | 4 parallel enrichment fetches |
| < 200 | Auto-wait until reset, then resume |

### Data Storage

All data is stored in a local SQLite database. The schema tracks:

| Table | Purpose |
|-------|---------|
| `orgs` | Registered organizations with floor dates |
| `commits` | Commit metadata, AI detection, production status, PR linkage |
| `repo_sync` | Per-org/repo sync bookmarks for incremental fetching |
| `sync_meta` | Key-value config (last run time) |

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [gh](https://cli.github.com/) (GitHub CLI, authenticated)

## Development

```bash
uv sync                    # install dependencies
uv run pytest -v           # run tests (59 tests)
uv run borg                # launch TUI
```

## License

MIT
