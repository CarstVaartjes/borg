# Borg

> *"Resistance is futile."*

Your GitHub org is being assimilated by AI coding tools. Borg tracks how fast.

An interactive terminal dashboard that scans pull requests across your GitHub organizations, detects AI-assisted commits via `Co-Authored-By` trailers and message style heuristics, and shows you who's using what — with charts, rankings, and trends.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│  Borg — Resistance is futile                                [org: all ▾]    │
├──────────────────────────────────────────────────────────────────────────────┤
│ Overview │ Authors │ Repos │ Trends  ·  Fetch │ Export │ Identity │ Orgs    │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Assimilation Progress                                                       │
│    Commits: 881 / 7,020 (12.5%)                                             │
│    LOC:     129,799 / 380,200 (34.1%)                                       │
│                                                                              │
│  ⭐ Skynet Employee of the Week: Alice Chen (42 AI commits)                 │
│                                                                              │
│  claude        ████████████████████████  612                                │
│  ai-assisted   ██████████               189                                 │
│  copilot       ████                      46                                 │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│ 1-8: tabs  /: filter  q: quit                       7,020 commits · 3 orgs │
└──────────────────────────────────────────────────────────────────────────────┘
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
2. **Fetch** tab → pull commit data from all PRs + run detection
3. **Overview** → see your assimilation progress

## Features

| Tab | What it does |
|-----|-------------|
| **Overview** | Assimilation Progress (commits + LOC), Skynet Employee of the Week, tool chart |
| **Authors** | Who's using AI the most? Sortable by commits, LOC, percentage — click a row for commit details |
| **Repos** | Which repos are most AI-assisted? Same drill — click for details, Enter opens GitHub |
| **Trends** | Monthly + weekly adoption curves (plotext charts in your terminal) |
| **Fetch** | Fetch & Detect in one flow, or Re-run Detection Only. Live progress per PR. |
| **Export** | Dump to CSV for spreadsheet warriors |
| **Identity** | Author identity management — auto-resolved groups + manual aliases + fuzzy merge suggestions |
| **Orgs** | Add/remove GitHub organizations |

**Keys:** `1-8` switch tabs, `/` filters by org, `q` quits. Click a row in Authors/Repos to see all commits; press Enter to open in browser.

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

### High Confidence — Trailer-based

| Tool | How |
|------|-----|
| Claude | `Co-Authored-By:.*Claude` or `noreply@anthropic.com` |
| Copilot | `Co-Authored-By:.*Copilot` or `copilot[bot]` author |
| Cursor | `Co-Authored-By:.*Cursor` or `noreply@cursor.com` |
| Aider | `(aider)` in author name |
| ChatGPT | `Co-Authored-By:.*ChatGPT` or `Co-Authored-By:.*OpenAI` |
| Devin | `devin-ai[bot]` author/email |
| Cody | `Co-Authored-By:.*Cody.*sourcegraph` |
| Amazon Q | `Co-Authored-By:.*Amazon Q` |
| Windsurf | `Co-Authored-By:.*Windsurf` |
| Codeium | `Co-Authored-By:.*Codeium` |
| Tabnine | `Co-Authored-By:.*Tabnine` |

### Medium Confidence — Message style heuristic

Structured commit messages: summary line + blank line + substantive body (bullet points or prose, >100 chars). This is the signature Claude/AI style even when trailers are missing.

### Low Confidence — Prefix heuristics

- **Conventional commits:** `fix:`, `feat:`, `chore:`, `refactor:`, `docs:`, `test:`, `ci:`, `perf:`, `style:`, `build:` — single-line, 15-120 chars
- **Jira ticket prefix:** `PROJ-123: Sentence description` — requires colon separator
- **Bulk addition:** `additions > 100 AND deletions < 10`

Detection runs locally in a single SQLite transaction — no API calls, instant, re-runnable.

## Smart Details

**Author identity resolution** — Borg uses a union-find algorithm to transitively merge authors by shared names and emails. `ctselas7` and `Christos Tselas` with the same email? Same person. `alvin` using `lvindotexe@github.com` and `alvin van dijk` using `alvinv@office.local`? Add a manual alias in the Identity tab, and all 8 emails merge into one identity. Fuzzy suggestions auto-detect likely merges (substring/shared-word matching).

**Noise filtering** — Merge commits, reverts, and conflict resolutions are automatically excluded from all statistics. These are GitHub-generated artifacts without meaningful authorship.

**Production tracking** — Each commit has an `in_production` flag tracking whether its PR was merged to `main`/`master`. Commits flow through feature → uat → preprod → main; the flag promotes to `1` when the main-targeting PR is processed.

**All PR states** — Merged, open, and abandoned PRs are all included. This tracks development effort, not just what shipped.

**Incremental fetching** — Only PRs updated since the last fetch are processed. Second fetch is fast.

**Rate limiting** — GitHub gives you 5,000 API calls/hour. Borg monitors usage and adapts parallelism (8→4→wait). Stops enrichment gracefully when rate limit is hit; picks up where it left off next time.

## Known Limitations

- **No trailer = high-confidence detection impossible.** The medium/low heuristics catch many cases, but false positives are possible.
- **Squash SHAs are new.** The original PR commits never appear on main, so `in_production` is based on PR target branch.
- **PR commits API has no `since` filter.** Commits before the org's floor date are filtered at insert time.
- **Author fuzzy matching has false positives.** "Jose Jimenez" and "Jose Romero" share "Jose" but are different people. Review suggestions before applying.

## Requirements

| Tool | Install | Why |
|------|---------|-----|
| Python 3.11+ | system/pyenv | Runtime |
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Package management |
| [gh](https://cli.github.com/) | `brew install gh && gh auth login` | GitHub API access |

## Development

```bash
uv sync                                      # install deps
uv run pytest -v                             # 99 tests
uv run python tests/create_fixture.py        # regenerate test fixture DB
uv run borg                                  # launch TUI
```

## License

MIT
