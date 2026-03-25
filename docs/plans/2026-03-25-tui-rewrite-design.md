# Borg TUI Rewrite — Design Document

**Goal:** Rewrite borg from bash to Python as a full interactive TUI using Textual + Plotext. No CLI subcommands — everything happens inside the TUI.

## Entry Point

```bash
borg [--db path]      # launches TUI, that's it
```

Default DB path: `~/.local/share/borg/tracker.db` (XDG convention).

## Architecture

```
borg/
├── pyproject.toml
├── src/borg/
│   ├── __init__.py
│   ├── cli.py            # Typer: just borg [--db] → launches TUI
│   ├── db.py             # SQLite layer (schema, org CRUD, queries)
│   ├── fetch.py          # GitHub API fetching (httpx + gh auth token)
│   ├── detect.py         # AI detection (regex on commit messages)
│   └── ui/
│       ├── __init__.py
│       ├── app.py         # Textual App, tab switching, global filters
│       ├── overview.py    # Overview tab (summary + tool chart)
│       ├── authors.py     # Authors tab (ranking tables)
│       ├── repos.py       # Repos tab (ranking tables)
│       ├── trends.py      # Trends tab (plotext line charts)
│       ├── fetch.py       # Fetch tab (log panel, progress)
│       ├── detect.py      # Detect tab (rules table, re-run)
│       ├── export.py      # Export tab (format, path, trigger)
│       └── orgs.py        # Orgs tab (add/remove/list)
└── tests/
    ├── test_db.py
    ├── test_detect.py
    └── test_fetch.py
```

## Dependencies & Packaging

```toml
[project]
name = "borg-tracker"
requires-python = ">=3.11"
dependencies = [
    "textual>=3.0",
    "textual-plotext>=0.5",
    "typer>=0.15",
    "httpx>=0.28",
]

[project.scripts]
borg = "borg.cli:main"
```

Managed with `uv`:
```bash
uv sync              # install deps
uv run borg          # run during development
uv build             # build wheel
uv tool install .    # global install
```

GitHub auth: read token from `gh auth token` at startup. If it fails, show error screen and exit.

## TUI Layout

```
┌─────────────────────────────────────────────────────────────────┐
│  🟢 Borg — "Resistance is futile"                 [org: all ▾] │
├─────────────────────────────────────────────────────────────────┤
│ Overview │ Authors │ Repos │ Trends  ·  Fetch │ Detect │ Export │ Orgs │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│                     (tab content area)                          │
│                                                                 │
│                                                                 │
├─────────────────────────────────────────────────────────────────┤
│ 1-8: tabs  /: filter  q: quit         342 commits · 3 orgs     │
└─────────────────────────────────────────────────────────────────┘
```

- **Header:** Title + global org filter dropdown
- **Tab bar:** Report views left, action views right, separated by `·`
- **Content area:** Changes per active tab
- **Footer:** Keyboard shortcuts left, stats summary right

### Navigation

- `1-8` or click: switch tabs
- `/`: open org filter
- `q`: quit
- Report tabs re-query SQLite on every tab switch (always fresh)

### Global Org Filter

Dropdown in header, defaults to "all". When filtered, all report tabs scope to that org. Action tabs also respect the filter (fetch only that org, export only that org's data).

## Tab Content: Report Views

### Overview (landing page)

- Styled summary box: "Assimilation Progress: 847 / 2,341 commits (36%)" with LOC stats
- "Skynet Employee of the Week" — author with most AI commits in the last 7 days
- Plotext horizontal bar chart: commits per AI tool
- Quick stats row: orgs tracked, repos scanned, date range

### Authors

- Sortable table: Author | AI Commits | Total | % | AI LOC
- Column headers toggle asc/desc sort
- Minimum 5 commits threshold to reduce noise
- Visual highlight on rows with AI % > 50%

### Repos

- Same layout as Authors, grouped by repo
- Shows org prefix: `myorg/repo-name`

### Trends

- Plotext line chart: AI adoption % monthly
- Second chart: weekly view
- Both respond to org filter

## Tab Content: Action Views

### Fetch

- Log panel showing progress in real-time (scrollable)
- "Start Fetch" button — fetches all orgs (or filtered org)
- Progress: current org, repo count, commit count, rate limit status
- Auto-runs detect after fetch completes

### Detect

- Reference table showing the 12 detection rules
- "Re-run Detection" button
- Results summary after completion

### Export

- Format: CSV
- Path input field with default
- Respects org filter
- "Export" button with row count confirmation

### Orgs

- Table: Name | Since | Added | Commits | Last Fetched
- "Add Org" button → inline form (name + since date)
- Select + "Remove" with confirmation dialog
- Empty state on first launch: "Add your first org" prompt

## Error Handling

- **No orgs:** Opens to Orgs tab, other tabs show "No data — add an org first"
- **Fetch failure:** Error in fetch log panel, app doesn't crash
- **Rate limit:** Progress log shows countdown, resumes automatically
- **Empty filter results:** "No data for [org]" message
- **`gh auth token` failure:** Error screen at startup, exit

## Humor (sprinkled, not overwhelming)

- "Assimilation Progress" instead of "AI Adoption %"
- "Skynet Employee of the Week" for top AI contributor
- "Resistance is futile" tagline in header
- Keep it professional otherwise — the data is real, the labels are fun

## Migration

The bash version stays in git history. The Python rewrite replaces it entirely. Same SQLite schema (orgs, commits, repo_sync, sync_meta tables). The `--db` flag allows pointing at an existing database.
