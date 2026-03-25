#!/usr/bin/env bash
# Database helpers for borg

# Escape single quotes for SQLite string literals
sql_escape() {
    printf '%s' "${1//\'/\'\'}"
}

utc_now() {
    date -u +%Y-%m-%dT%H:%M:%SZ
}

db_init() {
    local db="$1"
    mkdir -p "$(dirname "$db")" || {
        echo "Error: cannot create directory for database at $db" >&2
        exit 1
    }

    sqlite3 "$db" <<'SQL' >/dev/null
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS orgs (
    name TEXT PRIMARY KEY,
    since_date TEXT NOT NULL,
    added_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS commits (
    sha TEXT PRIMARY KEY,
    org TEXT NOT NULL,
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
    org TEXT NOT NULL,
    repo TEXT NOT NULL,
    last_commit_date TEXT,
    last_synced_at TEXT,
    commit_count INTEGER DEFAULT 0,
    PRIMARY KEY (org, repo)
);

CREATE TABLE IF NOT EXISTS sync_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_commits_org ON commits(org);
CREATE INDEX IF NOT EXISTS idx_commits_repo ON commits(repo);
CREATE INDEX IF NOT EXISTS idx_commits_ai_tool ON commits(ai_tool);
CREATE INDEX IF NOT EXISTS idx_commits_date ON commits(date);
CREATE INDEX IF NOT EXISTS idx_commits_additions ON commits(additions);
SQL
}

# Returns empty string if key not found or DB error (logs warning on error)
db_get_meta() {
    local db="$1" key="$2"
    local e_key
    e_key=$(sql_escape "$key")
    local result
    if ! result=$(sqlite3 "$db" "SELECT value FROM sync_meta WHERE key = '$e_key';" 2>&1); then
        echo "Warning: could not read metadata key '$key': $result" >&2
        echo ""
        return
    fi
    echo "$result"
}

db_set_meta() {
    local db="$1" key="$2" value="$3"
    local e_key e_value
    e_key=$(sql_escape "$key")
    e_value=$(sql_escape "$value")
    sqlite3 "$db" "INSERT OR REPLACE INTO sync_meta (key, value) VALUES ('$e_key', '$e_value');"
}

# ---------------------------------------------------------------------------
# Org CRUD
# ---------------------------------------------------------------------------

db_org_add() {
    local db="$1" name="$2" since="$3"
    local e_name e_since
    e_name=$(sql_escape "$name")
    e_since=$(sql_escape "$since")
    local added_at
    added_at=$(utc_now)
    local e_added_at
    e_added_at=$(sql_escape "$added_at")

    # Check if org already exists
    local existing
    existing=$(sqlite3 "$db" "SELECT COUNT(*) FROM orgs WHERE name = '$e_name';")
    if [[ "$existing" -gt 0 ]]; then
        echo "Error: org '$name' already exists." >&2
        return 1
    fi

    sqlite3 "$db" "INSERT INTO orgs (name, since_date, added_at) VALUES ('$e_name', '$e_since', '$e_added_at');"
    echo "Added org '$name' (tracking since $since)."
}

db_org_remove() {
    local db="$1" name="$2"
    local e_name
    e_name=$(sql_escape "$name")

    # Check if org exists
    local existing
    existing=$(sqlite3 "$db" "SELECT COUNT(*) FROM orgs WHERE name = '$e_name';")
    if [[ "$existing" -eq 0 ]]; then
        echo "Error: org '$name' not found." >&2
        return 1
    fi

    sqlite3 "$db" "DELETE FROM commits WHERE org = '$e_name';"
    sqlite3 "$db" "DELETE FROM repo_sync WHERE org = '$e_name';"
    sqlite3 "$db" "DELETE FROM orgs WHERE name = '$e_name';"
    echo "Removed org '$name' and all its data."
}

db_org_list() {
    local db="$1"
    local count
    count=$(sqlite3 "$db" "SELECT COUNT(*) FROM orgs;")

    if [[ "$count" -eq 0 ]]; then
        echo "No orgs configured. Add one with: borg org add <name> --since <date>"
        return
    fi

    printf "%-25s %-15s %10s\n" "ORG" "SINCE" "COMMITS"
    printf "%-25s %-15s %10s\n" "---" "-----" "-------"

    sqlite3 -separator '|' "$db" \
        "SELECT o.name, o.since_date, COALESCE(c.cnt, 0)
         FROM orgs o
         LEFT JOIN (SELECT org, COUNT(*) as cnt FROM commits GROUP BY org) c
           ON o.name = c.org
         ORDER BY o.name;" | \
    while IFS='|' read -r name since commits; do
        printf "%-25s %-15s %10s\n" "$name" "$since" "$commits"
    done
}

db_org_get_all() {
    local db="$1"
    sqlite3 -separator '|' "$db" "SELECT name, since_date FROM orgs ORDER BY name;"
}

db_org_get() {
    local db="$1" name="$2"
    local e_name
    e_name=$(sql_escape "$name")
    sqlite3 -separator '|' "$db" "SELECT name, since_date FROM orgs WHERE name = '$e_name';"
}

# ---------------------------------------------------------------------------
# Status & export
# ---------------------------------------------------------------------------

db_show_status() {
    local db="$1"
    local org_filter="${2:-}"
    local last_run
    last_run=$(db_get_meta "$db" "last_run_at")

    echo "Borg sync status"
    echo "  Last run:   ${last_run:-never}"
    echo ""

    local where="WHERE 1=1"
    if [[ -n "$org_filter" ]]; then
        local e_org_filter
        e_org_filter=$(sql_escape "$org_filter")
        where="$where AND org = '$e_org_filter'"
    fi

    local total enriched detected
    if ! total=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits $where;" 2>&1); then
        echo "Error: could not query database: $total" >&2
        return 1
    fi
    enriched=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits $where AND additions IS NOT NULL;")
    detected=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits $where AND ai_tool IS NOT NULL;")

    echo "  Commits:     $total"
    echo "  Enriched:    $enriched / $total"
    echo "  AI detected: $detected"
    echo ""

    # Build repo_sync where clause (different table, column names same)
    local repo_where="WHERE 1=1"
    if [[ -n "$org_filter" ]]; then
        local e_org_filter2
        e_org_filter2=$(sql_escape "$org_filter")
        repo_where="$repo_where AND org = '$e_org_filter2'"
    fi

    local repo_count
    repo_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM repo_sync $repo_where;")
    echo "  Repos synced: $repo_count"
    sqlite3 -separator '|' "$db" \
        "SELECT org, repo, commit_count, last_commit_date FROM repo_sync $repo_where ORDER BY commit_count DESC LIMIT 20;" | \
    while IFS='|' read -r org repo count last_date; do
        printf "    %-15s %-35s %5d commits  (last: %s)\n" "$org" "$repo" "$count" "$last_date"
    done

    echo ""
    echo "  Orgs:"
    sqlite3 -separator '|' "$db" "SELECT name, since_date FROM orgs ORDER BY name;" | \
    while IFS='|' read -r name since; do
        printf "    %-25s (since %s)\n" "$name" "$since"
    done
}

db_export_csv() {
    local db="$1" csv="$2"
    local org_filter="${3:-}"

    local where="WHERE 1=1"
    if [[ -n "$org_filter" ]]; then
        local e_org_filter
        e_org_filter=$(sql_escape "$org_filter")
        where="$where AND org = '$e_org_filter'"
    fi

    sqlite3 -header -csv "$db" \
        "SELECT sha, org, repo, author, email, date, additions, deletions,
                (COALESCE(additions,0) + COALESCE(deletions,0)) as loc_changed,
                message, ai_tool, ai_confidence
         FROM commits $where ORDER BY date;" > "$csv"
}
