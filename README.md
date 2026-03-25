# Borg

> *"Resistance is futile."*

Your GitHub org is being assimilated by AI coding tools. Borg tracks how fast.

An interactive terminal dashboard that scans pull requests across your GitHub organizations, detects AI-assisted commits via `Co-Authored-By` trailers, and shows you who's using what — with charts, rankings, and trends.

```
┌─────────────────────────────────────────────────────────────────────┐
│  Borg — Resistance is futile                       [org: all ▾]    │
├─────────────────────────────────────────────────────────────────────┤
│ Overview │ Authors │ Repos │ Trends  ·  Fetch │ Detect │ Export │ Orgs │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  Assimilation Progress: 847 / 2,341 commits (36%)                  │
│  LOC: 124,500 / 380,200 (33%)                                      │
│                                                                     │
│  ⭐ Skynet Employee of the Week: Alice Chen (42 AI commits)        │
│                                                                     │
│  claude   ████████████████████████  612                             │
│  copilot  ██████████               189                              │
│  cursor   ████                      46                              │
│                                                                     │
├─────────────────────────────────────────────────────────────────────┤
│ 1-8: tabs  /: filter  q: quit              2,341 commits · 3 orgs  │
└─────────────────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Requires: Python 3.11+, uv, gh (authenticated)
git clone https://github.com/CarstVaartjes/borg.git && cd borg
uv sync
uv run borg
```

That's it. Everything happens in the TUI:

1. **Orgs** tab → add your GitHub org
2. **Fetch** tab → pull commit data from all PRs
3. **Overview** → see your assimilation progress

## Features

| Tab | What it does |
|-----|-------------|
| **Overview** | Assimilation Progress, Skynet Employee of the Week, AI tool breakdown chart |
| **Authors** | Who's using AI the most? Sortable by commits, LOC, percentage |
| **Repos** | Which repos are most AI-assisted? Same drill |
| **Trends** | Monthly + weekly adoption curves (plotext charts in your terminal) |
| **Fetch** | Pull fresh data with live progress: `PR 42/127: #36588 [merged] Fix auth (3 commits, 2 new)` |
| **Detect** | See all 11 detection rules, re-run detection anytime |
| **Export** | Dump to CSV for spreadsheet warriors |
| **Orgs** | Add/remove GitHub organizations |

**Keys:** `1-8` switch tabs, `/` filters by org, `q` quits.

## Why PR-Based Fetching?

Most teams use **squash merges**. When GitHub squash-merges a PR, it creates a new commit on main and **strips the `Co-Authored-By` trailers** from the original commits. If you only look at main, you miss all the AI signatures.

Borg solves this by fetching commits directly from each PR — merged, open, and even abandoned. The original commits still have their trailers intact, regardless of how the PR was merged.

```
Feature branch:  abc123  "feat: add auth" Co-Authored-By: Claude <noreply@anthropic.com>
                 def456  "test: auth tests" Co-Authored-By: Claude <noreply@anthropic.com>
                    ↓ squash merge
Main branch:     789xyz  "feat: add auth (#42)"  ← trailer GONE

Borg fetches:    abc123 ✓  def456 ✓  (trailers preserved)
```

## What It Detects

| Tool | How | Confidence |
|------|-----|------------|
| Claude | `Co-Authored-By:.*Claude` or `noreply@anthropic.com` | high |
| Copilot | `Co-Authored-By:.*Copilot` or `copilot[bot]` author | high |
| Cursor | `Co-Authored-By:.*Cursor` or `noreply@cursor.com` | high |
| Aider | `(aider)` in author name | high |
| ChatGPT | `Co-Authored-By:.*ChatGPT` or `Co-Authored-By:.*OpenAI` | high |
| Devin | `devin-ai[bot]` author/email | high |
| Cody | `Co-Authored-By:.*Cody.*sourcegraph` | high |
| Amazon Q | `Co-Authored-By:.*Amazon Q` | high |
| Windsurf | `Co-Authored-By:.*Windsurf` | high |
| Codeium | `Co-Authored-By:.*Codeium` | high |
| Tabnine | `Co-Authored-By:.*Tabnine` | high |

Detection runs locally in a single SQLite transaction — no API calls, instant, re-runnable.

## Smart Details

**Author grouping by email** — `ctselas7` and `Christos Tselas` with the same email? Same person. Borg groups by email and shows the most common display name.

**Production tracking** — each commit tracks whether its PR was merged to `main`/`master` (`in_production` flag). Commits flow through feature → uat → preprod → main; the flag promotes to `1` when the main-targeting PR is processed.

**All PR states** — merged, open, and abandoned PRs are all included. This tracks development effort, not just what shipped.

**Rate limiting** — GitHub gives you 5,000 API calls/hour. Borg monitors usage and adapts parallelism (8→4→wait). A fetch always runs to completion.

## Known Limitations

- **No trailer = no detection.** If someone uses Claude but commits without `Co-Authored-By`, borg can't see it.
- **Squash SHAs are new.** The original PR commits never appear on main, so `in_production` is based on PR target branch, not commit presence on main.
- **PR commits API has no `since` filter.** Long-lived PRs may include some older commits before the floor date.

## Requirements

| Tool | Install | Why |
|------|---------|-----|
| Python 3.11+ | system/pyenv | Runtime |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Package management |
| [gh](https://cli.github.com/) | `brew install gh && gh auth login` | GitHub API access |

## Development

```bash
uv sync                                      # install deps
uv run pytest -v                             # 89 tests
uv run python tests/create_fixture.py        # regenerate test fixture DB
uv run borg                                  # launch TUI
```

## License

MIT
