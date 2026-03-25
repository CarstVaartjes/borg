#!/usr/bin/env bash
# AI detection for borg — trailer-based pattern matching

detect_ai() {
    local db="$1"
    echo "Detecting AI-assisted commits..."

    # All detection runs as a single transaction. The full reset + re-detect
    # ensures rule changes apply retroactively. If any step fails, the
    # transaction rolls back and prior classifications are preserved.
    sqlite3 "$db" <<'SQL'
BEGIN TRANSACTION;

-- Reset all detection results to re-run from scratch
UPDATE commits SET ai_tool = NULL, ai_confidence = NULL;

-- 1. Claude (LIKE is case-insensitive in SQLite for ASCII)
UPDATE commits SET ai_tool = 'claude', ai_confidence = 'high'
    WHERE ai_tool IS NULL AND (
        message LIKE '%Co-Authored-By:%Claude%'
        OR message LIKE '%noreply@anthropic.com%'
    );

-- 2. Copilot
UPDATE commits SET ai_tool = 'copilot', ai_confidence = 'high'
    WHERE ai_tool IS NULL AND (
        message LIKE '%Co-Authored-By:%Copilot%'
        OR author = 'copilot[bot]'
        OR email LIKE '%copilot%'
    );

-- 3. Cursor
UPDATE commits SET ai_tool = 'cursor', ai_confidence = 'high'
    WHERE ai_tool IS NULL AND (
        message LIKE '%Co-Authored-By:%Cursor%'
        OR message LIKE '%noreply@cursor.com%'
    );

-- 4. Aider
UPDATE commits SET ai_tool = 'aider', ai_confidence = 'high'
    WHERE ai_tool IS NULL AND (
        author LIKE '%(aider)%'
    );

-- 5. ChatGPT / OpenAI
UPDATE commits SET ai_tool = 'chatgpt', ai_confidence = 'high'
    WHERE ai_tool IS NULL AND (
        message LIKE '%Co-Authored-By:%ChatGPT%'
        OR message LIKE '%Co-Authored-By:%OpenAI%'
    );

-- 6. Devin (require bot author or bot email to avoid matching human name)
UPDATE commits SET ai_tool = 'devin', ai_confidence = 'high'
    WHERE ai_tool IS NULL AND (
        author = 'devin-ai[bot]'
        OR email LIKE '%devin-ai%'
        OR message LIKE '%Co-Authored-By:%devin-ai[bot]%'
    );

-- 7. Cody (require Sourcegraph email to avoid matching human name)
UPDATE commits SET ai_tool = 'cody', ai_confidence = 'high'
    WHERE ai_tool IS NULL AND (
        message LIKE '%Co-Authored-By:%Cody%sourcegraph%'
        OR message LIKE '%noreply@sourcegraph.com%'
    );

-- 8. Amazon Q
UPDATE commits SET ai_tool = 'amazon-q', ai_confidence = 'high'
    WHERE ai_tool IS NULL AND (
        message LIKE '%Co-Authored-By:%Amazon Q%'
    );

-- 9. Windsurf
UPDATE commits SET ai_tool = 'windsurf', ai_confidence = 'high'
    WHERE ai_tool IS NULL AND (
        message LIKE '%Co-Authored-By:%Windsurf%'
    );

-- 10. Codeium
UPDATE commits SET ai_tool = 'codeium', ai_confidence = 'high'
    WHERE ai_tool IS NULL AND (
        message LIKE '%Co-Authored-By:%Codeium%'
    );

-- 11. Tabnine
UPDATE commits SET ai_tool = 'tabnine', ai_confidence = 'high'
    WHERE ai_tool IS NULL AND (
        message LIKE '%Co-Authored-By:%Tabnine%'
    );

-- 12. Bulk addition heuristic — large additions with minimal deletions may
-- indicate AI-generated code. Low confidence due to high false-positive rate
-- (scaffolding, vendoring, generated code).
UPDATE commits SET ai_tool = 'unknown', ai_confidence = 'low'
    WHERE ai_tool IS NULL
        AND additions > 100
        AND deletions < 10
        AND additions IS NOT NULL;

COMMIT;
SQL

    local total ai_high ai_low
    total=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits;")
    ai_high=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits WHERE ai_confidence = 'high';")
    ai_low=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits WHERE ai_confidence = 'low';")
    echo "Detection complete: $ai_high high-confidence, $ai_low low-confidence, out of $total total."
}
