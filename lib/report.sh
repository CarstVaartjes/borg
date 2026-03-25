#!/usr/bin/env bash
# Terminal report rendering for borg

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# SQL expression for total lines changed, used across queries
LOC_EXPR="COALESCE(additions,0) + COALESCE(deletions,0)"

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
# Header and tool breakdown
# ---------------------------------------------------------------------------

report_header() {
    local db="$1" org="$2" since="$3"

    local total_commits ai_commits total_loc ai_loc

    total_commits=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits;")
    ai_commits=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits WHERE ai_confidence = 'high';")
    total_loc=$(sqlite3 "$db" "SELECT COALESCE(SUM($LOC_EXPR),0) FROM commits;")
    ai_loc=$(sqlite3 "$db" "SELECT COALESCE(SUM($LOC_EXPR),0) FROM commits WHERE ai_confidence = 'high';")

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
        "SELECT ai_tool, COUNT(*), SUM($LOC_EXPR)
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
# Rankings — parameterized for authors and repos
# ---------------------------------------------------------------------------

# Renders top/bottom rankings by AI commits and AI LOC
# $1=db $2=top $3=group_col ("author" or "repo") $4=label ("Author" or "Repo")
report_rankings() {
    local db="$1" top="$2" group_col="$3" label="$4"

    # Exclude entries with 5 or fewer commits to reduce noise
    local sql_base
    sql_base="SELECT $group_col,
       SUM(CASE WHEN ai_confidence = 'high' THEN 1 ELSE 0 END) as ai_commits,
       COUNT(*) as total_commits,
       SUM(CASE WHEN ai_confidence = 'high' THEN $LOC_EXPR ELSE 0 END) as ai_loc,
       SUM($LOC_EXPR) as total_loc
     FROM commits
     GROUP BY $group_col
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

    print_ranking "Top $top ${label}s by AI commits:" "$label" "$top_by_commits"
    print_ranking "Bottom $top ${label}s by AI commits:" "$label" "$bottom_by_commits"
    print_ranking "Top $top ${label}s by AI LOC:" "$label" "$top_by_loc"
    print_ranking "Bottom $top ${label}s by AI LOC:" "$label" "$bottom_by_loc"
}

# ---------------------------------------------------------------------------
# Trend — parameterized for monthly and weekly
# ---------------------------------------------------------------------------

# Renders a time-based trend report
# $1=db $2=strftime_fmt $3=col_alias $4=section_title
report_time_trend() {
    local db="$1" strftime_fmt="$2" col_alias="$3" title="$4"

    local rows
    rows=$(sqlite3 -separator '|' "$db" \
        "SELECT strftime('$strftime_fmt', date) as $col_alias,
                COUNT(*) as total,
                SUM(CASE WHEN ai_confidence = 'high' THEN 1 ELSE 0 END) as ai,
                SUM($LOC_EXPR) as total_loc,
                SUM(CASE WHEN ai_confidence = 'high' THEN $LOC_EXPR ELSE 0 END) as ai_loc
         FROM commits
         GROUP BY $col_alias
         ORDER BY $col_alias;")

    [[ -z "$rows" ]] && return

    section_header "$title"

    local -a pcts=()

    while IFS='|' read -r period total ai total_loc ai_loc; do
        [[ -z "$period" ]] && continue
        local commit_pct loc_pct
        commit_pct=$(pct "$ai" "$total")
        loc_pct=$(pct "$ai_loc" "$total_loc")
        pcts+=("$commit_pct")

        printf "  %s  %7s/%7s  %3s%%  |  %12s/%12s LOC  %3s%%\n" \
            "$period" \
            "$(format_number "$ai")" \
            "$(format_number "$total")" \
            "$commit_pct" \
            "$(format_number "$ai_loc")" \
            "$(format_number "$total_loc")" \
            "$loc_pct"
    done <<< "$rows"

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
    report_rankings "$db" "$top" "author" "Author"
    report_rankings "$db" "$top" "repo" "Repo"
    report_time_trend "$db" '%Y-%m' "month" "Monthly trend:"
    report_time_trend "$db" '%Y-W%W' "week" "Weekly trend:"
    echo ""
}
