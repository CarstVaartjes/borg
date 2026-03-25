# Borg

> "Resistance is futile"

Track AI-generated code adoption across a GitHub organization.

## Quick Start

```bash
# First run
./borg fetch --org myorg --since 2026-01-01

# View report
./borg report

# Export to CSV
./borg export --csv commits.csv
```

## Requirements

- `gh` (GitHub CLI, authenticated)
- `jq`
- `sqlite3` (pre-installed on macOS)
- `gum` (`brew install gum`)
