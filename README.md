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

## AI Detection

Detects AI-assisted commits by matching `Co-Authored-By` trailers in commit messages.

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

## Rate Limit Handling

GitHub allows 5,000 API calls/hour. Borg monitors usage and adapts:

| Remaining | Behavior |
|-----------|----------|
| > 500 | 8 parallel fetches |
| 200-500 | 4 parallel fetches |
| < 200 | Auto-wait until reset, then resume |

## Requirements

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)
- [gh](https://cli.github.com/) (GitHub CLI, authenticated)

## Development

```bash
uv sync                    # install dependencies
uv run pytest -v           # run tests
uv run borg                # launch TUI
```

## License

MIT
