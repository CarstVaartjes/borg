#!/usr/bin/env bash
# GitHub API fetching for borg — rate-limit aware, incremental

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

sql_escape() {
    echo "${1//\'/\'\'}"
}

check_rate_limit() {
    local info
    info=$(gh api rate_limit --jq '.rate | "\(.remaining) \(.reset)"' 2>/dev/null) || echo "5000 0"
    echo "$info"
}

wait_for_rate_limit() {
    local min_remaining="${1:-200}"
    while true; do
        local info remaining reset_epoch
        info=$(check_rate_limit)
        remaining="${info%% *}"
        reset_epoch="${info##* }"

        if [[ "$remaining" -ge "$min_remaining" ]]; then
            echo "$remaining"
            return
        fi

        local now wait_seconds reset_human
        now=$(date +%s)
        wait_seconds=$(( reset_epoch - now + 5 ))
        if [[ "$wait_seconds" -lt 0 ]]; then wait_seconds=5; fi
        reset_human=$(date -r "$reset_epoch" "+%H:%M:%S %Z" 2>/dev/null || echo "soon")
        echo "Rate limit hit. $remaining remaining. Waiting until $reset_human ($wait_seconds sec)..." >&2
        sleep "$wait_seconds"
    done
}

# ---------------------------------------------------------------------------
# Repo listing
# ---------------------------------------------------------------------------

fetch_repo_list() {
    local org="$1"
    gh repo list "$org" --limit 500 --json name,isArchived \
        --jq '.[] | select(.isArchived == false) | .name'
}

# ---------------------------------------------------------------------------
# Phase 1 — list commits per repo
# ---------------------------------------------------------------------------

fetch_repo_commits() {
    local db="$1" org="$2" repo="$3" global_since="$4"

    # Determine the since date: per-repo bookmark or global default
    local since
    since=$(sqlite3 "$db" "SELECT last_commit_date FROM repo_sync WHERE repo = '$(sql_escape "$repo")';" 2>/dev/null)
    if [[ -z "$since" ]]; then
        since="$global_since"
    fi

    # Ensure ISO 8601 format for the API
    local since_iso="$since"
    if [[ "$since_iso" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]]; then
        since_iso="${since_iso}T00:00:00Z"
    fi

    local page=1
    local new_count=0
    local newest_date=""

    while true; do
        local json
        json=$(gh api "repos/$org/$repo/commits?since=$since_iso&per_page=100&page=$page" 2>/dev/null) || break

        # Check if we got an empty array
        local count
        count=$(echo "$json" | jq 'length' 2>/dev/null) || break
        if [[ "$count" -eq 0 ]]; then
            break
        fi

        # Parse and insert each commit
        local entries
        entries=$(echo "$json" | jq -r '.[] | [
            .sha,
            (.commit.author.name // "unknown"),
            (.commit.author.email // "unknown"),
            (.commit.author.date // ""),
            (.commit.message | split("\n")[0] // "")
        ] | @tsv' 2>/dev/null) || break

        while IFS=$'\t' read -r sha author email date message; do
            [[ -z "$sha" ]] && continue

            local e_author e_email e_message e_repo
            e_author=$(sql_escape "$author")
            e_email=$(sql_escape "$email")
            e_message=$(sql_escape "$message")
            e_repo=$(sql_escape "$repo")
            local fetched_at
            fetched_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

            sqlite3 "$db" "INSERT OR IGNORE INTO commits (sha, repo, author, email, date, message, fetched_at)
                VALUES ('$sha', '$e_repo', '$e_author', '$e_email', '$date', '$e_message', '$fetched_at');"

            # Track if this was actually inserted (rowcount via changes())
            local changes
            changes=$(sqlite3 "$db" "SELECT changes();")
            if [[ "$changes" -gt 0 ]]; then
                new_count=$((new_count + 1))
            fi

            # Track newest commit date
            if [[ -z "$newest_date" || "$date" > "$newest_date" ]]; then
                newest_date="$date"
            fi
        done <<< "$entries"

        # If fewer than 100 results, no more pages
        if [[ "$count" -lt 100 ]]; then
            break
        fi

        page=$((page + 1))
    done

    # Update repo_sync with the latest commit date
    if [[ -n "$newest_date" ]]; then
        local e_repo
        e_repo=$(sql_escape "$repo")
        local total_count
        total_count=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits WHERE repo = '$e_repo';")
        sqlite3 "$db" "INSERT OR REPLACE INTO repo_sync (repo, last_commit_date, last_synced_at, commit_count)
            VALUES ('$e_repo', '$newest_date', '$(date -u +%Y-%m-%dT%H:%M:%SZ)', $total_count);"
    elif [[ "$new_count" -eq 0 ]]; then
        # Still update last_synced_at even if no new commits
        local e_repo
        e_repo=$(sql_escape "$repo")
        sqlite3 "$db" "INSERT OR IGNORE INTO repo_sync (repo, last_commit_date, last_synced_at, commit_count)
            VALUES ('$e_repo', NULL, '$(date -u +%Y-%m-%dT%H:%M:%SZ)', 0);"
    fi

    echo "$new_count"
}

# ---------------------------------------------------------------------------
# Phase 2 — enrich commits with additions/deletions stats
# ---------------------------------------------------------------------------

enrich_commits() {
    local db="$1" org="$2"
    local total
    total=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits WHERE additions IS NULL;")

    if [[ "$total" -eq 0 ]]; then
        echo "All commits already enriched."
        return
    fi

    echo "Phase 2: Enriching $total commits with stats..."
    local done_count=0
    local tmpdir
    tmpdir=$(mktemp -d)

    while true; do
        # Get batch of unenriched commits
        local batch
        batch=$(sqlite3 -separator '|' "$db" \
            "SELECT sha, repo FROM commits WHERE additions IS NULL LIMIT 100;")

        if [[ -z "$batch" ]]; then
            break
        fi

        # Check rate limit and determine parallelism
        local remaining
        remaining=$(wait_for_rate_limit 200)
        local parallel=8
        if [[ "$remaining" -lt 500 ]]; then
            parallel=4
        fi

        # Fetch stats in parallel, write results to temp files
        local pids=()
        while IFS='|' read -r sha repo; do
            [[ -z "$sha" ]] && continue
            (
                local result
                result=$(gh api "repos/$org/$repo/commits/$sha" \
                    --jq '"\(.stats.additions // 0)|\(.stats.deletions // 0)"' 2>/dev/null) || result="0|0"
                echo "$sha|$result" > "$tmpdir/$sha"
            ) </dev/null &
            pids+=($!)

            # Limit parallelism
            while [[ ${#pids[@]} -ge $parallel ]]; do
                wait "${pids[0]}" 2>/dev/null || true
                pids=("${pids[@]:1}")
            done
        done <<< "$batch"

        # Wait for all remaining background jobs
        for pid in "${pids[@]}"; do
            wait "$pid" 2>/dev/null || true
        done

        # Batch update DB from temp files (sequential writes)
        for f in "$tmpdir"/*; do
            [[ -f "$f" ]] || continue
            local line sha additions deletions rest
            line=$(cat "$f")
            sha="${line%%|*}"
            rest="${line#*|}"
            additions="${rest%%|*}"
            deletions="${rest##*|}"

            # Sanitise: default to 0 if non-numeric
            [[ "$additions" =~ ^[0-9]+$ ]] || additions=0
            [[ "$deletions" =~ ^[0-9]+$ ]] || deletions=0

            sqlite3 "$db" "UPDATE commits SET additions = $additions, deletions = $deletions WHERE sha = '$sha';"
            rm -f "$f"
            done_count=$((done_count + 1))
            printf "\r  Enriching: %d/%d commits (%d%%)  " "$done_count" "$total" "$((done_count * 100 / total))" >&2
        done
    done

    rm -rf "$tmpdir"
    echo "" >&2
    echo "Phase 2 complete. $done_count commits enriched."
}

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

fetch_commits() {
    local db="$1" org="$2" since="$3"

    echo "Phase 1: Listing commits..."
    local repos
    repos=$(fetch_repo_list "$org")
    local repo_count
    repo_count=$(echo "$repos" | wc -l | tr -d ' ')
    echo "Found $repo_count repos"

    local i=0
    while IFS= read -r repo; do
        [[ -z "$repo" ]] && continue
        i=$((i + 1))
        local count
        count=$(fetch_repo_commits "$db" "$org" "$repo" "$since")
        if [[ "$count" -gt 0 ]]; then
            printf "\r  [%d/%d] %-40s %d new commits\n" "$i" "$repo_count" "$repo" "$count" >&2
        else
            printf "\r  [%d/%d] %-40s                    \r" "$i" "$repo_count" "$repo" >&2
        fi
    done <<< "$repos"
    echo "" >&2

    local total unenriched
    total=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits;")
    unenriched=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits WHERE additions IS NULL;")
    echo "Phase 1 complete. $total total commits, $unenriched need enrichment."

    # Phase 2
    enrich_commits "$db" "$org"

    # Update last_run
    sqlite3 "$db" "INSERT OR REPLACE INTO sync_meta (key, value) VALUES ('last_run_at', '$(date -u +%Y-%m-%dT%H:%M:%SZ)');"

    echo "Fetch complete."
}
