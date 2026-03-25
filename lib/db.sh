#!/usr/bin/env bash
# Database helpers for borg

db_init() {
    local db="$1"
    mkdir -p "$(dirname "$db")"

    sqlite3 "$db" <<'SQL' >/dev/null
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS commits (
    sha TEXT PRIMARY KEY,
    repo TEXT NOT NULL,
    author TEXT NOT NULL,
    email TEXT NOT NULL,
    date TEXT NOT NULL,
    additions INTEGER,
    deletions INTEGER,
    message TEXT,
    ai_tool TEXT,
    ai_confidence TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS repo_sync (
    repo TEXT PRIMARY KEY,
    last_commit_date TEXT,
    last_synced_at TEXT,
    commit_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_commits_repo ON commits(repo);
CREATE INDEX IF NOT EXISTS idx_commits_ai_tool ON commits(ai_tool);
CREATE INDEX IF NOT EXISTS idx_commits_date ON commits(date);
CREATE INDEX IF NOT EXISTS idx_commits_additions ON commits(additions);
SQL
}

db_get_meta() {
    local db="$1" key="$2"
    sqlite3 "$db" "SELECT value FROM sync_meta WHERE key = '$key';" 2>/dev/null || echo ""
}

db_set_meta() {
    local db="$1" key="$2" value="$3"
    sqlite3 "$db" "INSERT OR REPLACE INTO sync_meta (key, value) VALUES ('$key', '$value');"
}

db_export_csv() {
    local db="$1" csv="$2"
    sqlite3 -header -csv "$db" \
        "SELECT sha, repo, author, email, date, additions, deletions,
                (COALESCE(additions,0) + COALESCE(deletions,0)) as loc_changed,
                message, ai_tool, ai_confidence
         FROM commits ORDER BY date;" > "$csv"
}

db_show_status() {
    local db="$1"
    local org since last_run
    org=$(db_get_meta "$db" "org")
    since=$(db_get_meta "$db" "default_since")
    last_run=$(db_get_meta "$db" "last_run_at")

    echo "Borg sync status"
    echo "  Org:        ${org:-not set}"
    echo "  Since:      ${since:-not set}"
    echo "  Last run:   ${last_run:-never}"
    echo ""

    local total enriched detected
    total=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits;" 2>/dev/null || echo 0)
    enriched=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits WHERE additions IS NOT NULL;" 2>/dev/null || echo 0)
    detected=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits WHERE ai_tool IS NOT NULL;" 2>/dev/null || echo 0)

    echo "  Commits:     $total"
    echo "  Enriched:    $enriched / $total"
    echo "  AI detected: $detected"
    echo ""

    local repo_count
    repo_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM repo_sync;" 2>/dev/null || echo 0)
    echo "  Repos synced: $repo_count"
    sqlite3 -separator '|' "$db" \
        "SELECT repo, commit_count, last_commit_date FROM repo_sync ORDER BY commit_count DESC LIMIT 20;" 2>/dev/null | \
    while IFS='|' read -r repo count last_date; do
        printf "    %-35s %5d commits  (last: %s)\n" "$repo" "$count" "$last_date"
    done
}
