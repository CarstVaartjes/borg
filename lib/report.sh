#!/usr/bin/env bash
# Terminal report rendering for borg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

format_number() {
    printf "%'d" "$1" 2>/dev/null || printf "%d" "$1"
}

pct() {
    local num="$1" den="$2"
    if [[ "$den" -eq 0 ]]; then
        echo "0"
    else
        echo $(( num * 100 / den ))
    fi
}

# styled_box: render text inside a gum box, fall back to plain output
styled_box() {
    local text="$1"
    if command -v gum &>/dev/null; then
        echo "$text" | gum style --border double --padding "0 2" --border-foreground 212
    else
        echo "═══════════════════════════════════════════════════════════════"
        echo "$text"
        echo "═══════════════════════════════════════════════════════════════"
    fi
}

section_header() {
    local title="$1"
    echo ""
    if command -v gum &>/dev/null; then
        gum style --bold --foreground 212 "$title"
    else
        echo "$title"
    fi
}

# ---------------------------------------------------------------------------
# print_ranking — reusable table formatter
#   $1 = title
#   $2 = label for the name column ("Author" or "Repo")
#   $3 = pipe-separated rows: name|ai_count|total_count|ai_loc|total_loc
# ---------------------------------------------------------------------------
print_ranking() {
    local title="$1" label="$2" rows="$3"

    [[ -z "$rows" ]] && return

    section_header "$title"
    printf "  %-30s %7s %8s %5s %12s\n" "$label" "AI" "Total" "%" "AI LOC"
    printf "  ────────────────────────────────────────────────────────────────\n"

    while IFS='|' read -r name ai_count total_count ai_loc _total_loc; do
        [[ -z "$name" ]] && continue
        local p
        p=$(pct "$ai_count" "$total_count")
        printf "  %-30s %7s %8s %4s%% %12s\n" \
            "$name" \
            "$(format_number "$ai_count")" \
            "$(format_number "$total_count")" \
            "$p" \
            "$(format_number "$ai_loc")"
    done <<< "$rows"
}

# ---------------------------------------------------------------------------
# Task 6: report_header + report_by_tool
# ---------------------------------------------------------------------------

report_header() {
    local db="$1" org="$2" since="$3"

    local total_commits ai_commits total_loc ai_loc

    total_commits=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits;")
    ai_commits=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits WHERE ai_confidence = 'high';")
    total_loc=$(sqlite3 "$db" "SELECT COALESCE(SUM(COALESCE(additions,0) + COALESCE(deletions,0)),0) FROM commits;")
    ai_loc=$(sqlite3 "$db" "SELECT COALESCE(SUM(COALESCE(additions,0) + COALESCE(deletions,0)),0) FROM commits WHERE ai_confidence = 'high';")

    local commit_pct loc_pct
    commit_pct=$(pct "$ai_commits" "$total_commits")
    loc_pct=$(pct "$ai_loc" "$total_loc")

    local header
    header=$(printf "Borg — AI Commit Adoption — %s — since %s\n" "$org" "$since")
    header+=$(printf "\nCommits: %s AI-assisted / %s total  (%s%%)" \
        "$(format_number "$ai_commits")" \
        "$(format_number "$total_commits")" \
        "$commit_pct")
    header+=$(printf "\nLOC:     %s AI-assisted / %s total  (%s%%)" \
        "$(format_number "$ai_loc")" \
        "$(format_number "$total_loc")" \
        "$loc_pct")

    echo ""
    styled_box "$header"
}

report_by_tool() {
    local db="$1"

    local rows
    rows=$(sqlite3 -separator '|' "$db" \
        "SELECT ai_tool, COUNT(*), SUM(COALESCE(additions,0) + COALESCE(deletions,0))
         FROM commits
         WHERE ai_confidence = 'high'
         GROUP BY ai_tool
         ORDER BY COUNT(*) DESC;")

    [[ -z "$rows" ]] && return

    section_header "By tool:"
    while IFS='|' read -r tool count loc; do
        [[ -z "$tool" ]] && continue
        printf "  %-14s %8s commits %12s LOC\n" \
            "$tool" \
            "$(format_number "$count")" \
            "$(format_number "$loc")"
    done <<< "$rows"
}

# ---------------------------------------------------------------------------
# Task 7: report_authors + report_repos
# ---------------------------------------------------------------------------

report_authors() {
    local db="$1" top="$2"

    local sql_base
    sql_base="SELECT author,
       SUM(CASE WHEN ai_confidence = 'high' THEN 1 ELSE 0 END) as ai_commits,
       COUNT(*) as total_commits,
       SUM(CASE WHEN ai_confidence = 'high' THEN COALESCE(additions,0) + COALESCE(deletions,0) ELSE 0 END) as ai_loc,
       SUM(COALESCE(additions,0) + COALESCE(deletions,0)) as total_loc
     FROM commits
     GROUP BY author
     HAVING COUNT(*) > 5"

    local top_by_commits bottom_by_commits top_by_loc bottom_by_loc

    top_by_commits=$(sqlite3 -separator '|' "$db" \
        "$sql_base ORDER BY ai_commits DESC LIMIT $top;")
    bottom_by_commits=$(sqlite3 -separator '|' "$db" \
        "$sql_base ORDER BY ai_commits ASC LIMIT $top;")
    top_by_loc=$(sqlite3 -separator '|' "$db" \
        "$sql_base ORDER BY ai_loc DESC LIMIT $top;")
    bottom_by_loc=$(sqlite3 -separator '|' "$db" \
        "$sql_base ORDER BY ai_loc ASC LIMIT $top;")

    print_ranking "Top $top authors by AI commits:" "Author" "$top_by_commits"
    print_ranking "Bottom $top authors by AI commits:" "Author" "$bottom_by_commits"
    print_ranking "Top $top authors by AI LOC:" "Author" "$top_by_loc"
    print_ranking "Bottom $top authors by AI LOC:" "Author" "$bottom_by_loc"
}

report_repos() {
    local db="$1" top="$2"

    local sql_base
    sql_base="SELECT repo,
       SUM(CASE WHEN ai_confidence = 'high' THEN 1 ELSE 0 END) as ai_commits,
       COUNT(*) as total_commits,
       SUM(CASE WHEN ai_confidence = 'high' THEN COALESCE(additions,0) + COALESCE(deletions,0) ELSE 0 END) as ai_loc,
       SUM(COALESCE(additions,0) + COALESCE(deletions,0)) as total_loc
     FROM commits
     GROUP BY repo
     HAVING COUNT(*) > 5"

    local top_by_commits bottom_by_commits top_by_loc bottom_by_loc

    top_by_commits=$(sqlite3 -separator '|' "$db" \
        "$sql_base ORDER BY ai_commits DESC LIMIT $top;")
    bottom_by_commits=$(sqlite3 -separator '|' "$db" \
        "$sql_base ORDER BY ai_commits ASC LIMIT $top;")
    top_by_loc=$(sqlite3 -separator '|' "$db" \
        "$sql_base ORDER BY ai_loc DESC LIMIT $top;")
    bottom_by_loc=$(sqlite3 -separator '|' "$db" \
        "$sql_base ORDER BY ai_loc ASC LIMIT $top;")

    print_ranking "Top $top repos by AI commits:" "Repo" "$top_by_commits"
    print_ranking "Bottom $top repos by AI commits:" "Repo" "$bottom_by_commits"
    print_ranking "Top $top repos by AI LOC:" "Repo" "$top_by_loc"
    print_ranking "Bottom $top repos by AI LOC:" "Repo" "$bottom_by_loc"
}

# ---------------------------------------------------------------------------
# Task 8: report_trend
# ---------------------------------------------------------------------------

report_trend() {
    local db="$1"

    local rows
    rows=$(sqlite3 -separator '|' "$db" \
        "SELECT strftime('%Y-%m', date) as month,
                COUNT(*) as total,
                SUM(CASE WHEN ai_confidence = 'high' THEN 1 ELSE 0 END) as ai,
                SUM(COALESCE(additions,0) + COALESCE(deletions,0)) as total_loc,
                SUM(CASE WHEN ai_confidence = 'high' THEN COALESCE(additions,0) + COALESCE(deletions,0) ELSE 0 END) as ai_loc
         FROM commits
         GROUP BY month
         ORDER BY month;")

    [[ -z "$rows" ]] && return

    section_header "Monthly trend:"

    local -a pcts=()

    while IFS='|' read -r month total ai total_loc ai_loc; do
        [[ -z "$month" ]] && continue
        local commit_pct loc_pct
        commit_pct=$(pct "$ai" "$total")
        loc_pct=$(pct "$ai_loc" "$total_loc")
        pcts+=("$commit_pct")

        printf "  %s  %7s/%7s  %3s%%  |  %12s/%12s LOC  %3s%%\n" \
            "$month" \
            "$(format_number "$ai")" \
            "$(format_number "$total")" \
            "$commit_pct" \
            "$(format_number "$ai_loc")" \
            "$(format_number "$total_loc")" \
            "$loc_pct"
    done <<< "$rows"

    # Sparkline
    if [[ ${#pcts[@]} -gt 0 && -x "$SCRIPT_DIR/deps/spark" ]]; then
        local sparkline
        sparkline=$("$SCRIPT_DIR/deps/spark" "${pcts[@]}")
        echo "  Trend: $sparkline"
    fi
}

# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

report_show() {
    local db="$1" org="$2" since="$3" top="$4"
    report_header "$db" "$org" "$since"
    report_by_tool "$db"
    report_authors "$db" "$top"
    report_repos "$db" "$top"
    report_trend "$db"
    echo ""
}
