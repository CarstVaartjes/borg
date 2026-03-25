#!/usr/bin/env bash
# AI detection for borg — trailer-based pattern matching

detect_ai() {
    local db="$1"
    echo "Detecting AI-assisted commits..."

    # Reset (allows re-detection with updated rules)
    sqlite3 "$db" "UPDATE commits SET ai_tool = NULL, ai_confidence = NULL;"

    # 1. Claude
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'claude', ai_confidence = 'high'
        WHERE ai_tool IS NULL AND (
            message LIKE '%Co-Authored-By:%Claude%'
            OR message LIKE '%Co-authored-by:%Claude%'
            OR message LIKE '%noreply@anthropic.com%'
        );"

    # 2. Copilot
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'copilot', ai_confidence = 'high'
        WHERE ai_tool IS NULL AND (
            message LIKE '%Co-Authored-By:%Copilot%'
            OR message LIKE '%Co-authored-by:%Copilot%'
            OR author = 'copilot[bot]'
            OR email LIKE '%copilot%'
        );"

    # 3. Cursor
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'cursor', ai_confidence = 'high'
        WHERE ai_tool IS NULL AND (
            message LIKE '%Co-Authored-By:%Cursor%'
            OR message LIKE '%Co-authored-by:%Cursor%'
        );"

    # 4. Aider
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'aider', ai_confidence = 'high'
        WHERE ai_tool IS NULL AND (
            author LIKE '%(aider)%'
        );"

    # 5. ChatGPT
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'chatgpt', ai_confidence = 'high'
        WHERE ai_tool IS NULL AND (
            message LIKE '%Co-Authored-By:%ChatGPT%'
            OR message LIKE '%Co-authored-by:%ChatGPT%'
            OR message LIKE '%Co-Authored-By:%OpenAI%'
            OR message LIKE '%Co-authored-by:%OpenAI%'
        );"

    # 6. Devin
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'devin', ai_confidence = 'high'
        WHERE ai_tool IS NULL AND (
            message LIKE '%Co-Authored-By:%Devin%'
            OR message LIKE '%Co-authored-by:%Devin%'
            OR author = 'devin-ai[bot]'
        );"

    # 7. Cody
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'cody', ai_confidence = 'high'
        WHERE ai_tool IS NULL AND (
            message LIKE '%Co-Authored-By:%Cody%'
            OR message LIKE '%Co-authored-by:%Cody%'
        );"

    # 8. Amazon Q
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'amazon-q', ai_confidence = 'high'
        WHERE ai_tool IS NULL AND (
            message LIKE '%Co-Authored-By:%Amazon Q%'
            OR message LIKE '%Co-authored-by:%Amazon Q%'
        );"

    # 9. Windsurf
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'windsurf', ai_confidence = 'high'
        WHERE ai_tool IS NULL AND (
            message LIKE '%Co-Authored-By:%Windsurf%'
            OR message LIKE '%Co-authored-by:%Windsurf%'
        );"

    # 10. Codeium
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'codeium', ai_confidence = 'high'
        WHERE ai_tool IS NULL AND (
            message LIKE '%Co-Authored-By:%Codeium%'
            OR message LIKE '%Co-authored-by:%Codeium%'
        );"

    # 11. Tabnine
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'tabnine', ai_confidence = 'high'
        WHERE ai_tool IS NULL AND (
            message LIKE '%Co-Authored-By:%Tabnine%'
            OR message LIKE '%Co-authored-by:%Tabnine%'
        );"

    # 12. Bulk addition heuristic
    sqlite3 "$db" "UPDATE commits SET ai_tool = 'unknown', ai_confidence = 'low'
        WHERE ai_tool IS NULL
            AND additions > 100
            AND deletions < 10
            AND additions IS NOT NULL;"

    # Report
    local total ai_high ai_low
    total=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits;")
    ai_high=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits WHERE ai_confidence = 'high';")
    ai_low=$(sqlite3 "$db" "SELECT COUNT(*) FROM commits WHERE ai_confidence = 'low';")
    echo "Detection complete: $ai_high high-confidence, $ai_low low-confidence, out of $total total."
}
