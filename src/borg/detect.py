"""AI detection for commits using data-driven rules.

Scans commit metadata (message, author, email) to identify
AI-assisted commits and tags them with tool name and confidence.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from borg.db import Database

# Each rule: (tool_name, confidence, SQL WHERE clause).
# Rules are applied in order; first match wins.
RULES: list[tuple[str, str, str]] = [
    (
        "claude",
        "high",
        "message LIKE '%Co-Authored-By:%Claude%' OR message LIKE '%noreply@anthropic.com%'",
    ),
    (
        "copilot",
        "high",
        "message LIKE '%Co-Authored-By:%Copilot%' OR author = 'copilot[bot]' OR email LIKE '%copilot%'",
    ),
    (
        "cursor",
        "high",
        "message LIKE '%Co-Authored-By:%Cursor%' OR message LIKE '%noreply@cursor.com%'",
    ),
    (
        "aider",
        "high",
        "author LIKE '%(aider)%'",
    ),
    (
        "chatgpt",
        "high",
        "message LIKE '%Co-Authored-By:%ChatGPT%' OR message LIKE '%Co-Authored-By:%OpenAI%'",
    ),
    (
        "devin",
        "high",
        "author = 'devin-ai[bot]' OR email LIKE '%devin-ai%' OR message LIKE '%Co-Authored-By:%devin-ai[bot]%'",
    ),
    (
        "cody",
        "high",
        "message LIKE '%Co-Authored-By:%Cody%sourcegraph%' OR message LIKE '%noreply@sourcegraph.com%'",
    ),
    (
        "amazon-q",
        "high",
        "message LIKE '%Co-Authored-By:%Amazon Q%'",
    ),
    (
        "windsurf",
        "high",
        "message LIKE '%Co-Authored-By:%Windsurf%'",
    ),
    (
        "codeium",
        "high",
        "message LIKE '%Co-Authored-By:%Codeium%'",
    ),
    (
        "tabnine",
        "high",
        "message LIKE '%Co-Authored-By:%Tabnine%'",
    ),
]

# Bulk heuristic thresholds.
_BULK_ADDITIONS_MIN = 100
_BULK_DELETIONS_MAX = 10


def detect_ai(db: Database) -> dict[str, int]:
    """Detect AI-assisted commits using data-driven rules.

    Runs in a single transaction. Resets all ai_tool/ai_confidence
    to NULL first, then applies rules in order (first match wins),
    and finally applies the bulk heuristic for remaining unmatched commits.

    Args:
        db: Database instance with active connection.

    Returns:
        Dict with keys 'high', 'low', 'total' indicating match counts.
    """
    conn = db.conn
    try:
        conn.execute("BEGIN")

        # Reset all previous detections.
        conn.execute("UPDATE commits SET ai_tool = NULL, ai_confidence = NULL")

        # Apply rules in order; WHERE ai_tool IS NULL ensures first-match-wins.
        for tool, confidence, where_clause in RULES:
            conn.execute(
                f"UPDATE commits SET ai_tool = ?, ai_confidence = ? "
                f"WHERE ai_tool IS NULL AND ({where_clause})",
                (tool, confidence),
            )

        # AI message style heuristic: summary line + blank line + substantive body.
        # AI tools (especially Claude) produce structured commit messages with a
        # concise title, a blank line, then a detailed explanation (bullets or prose).
        # Humans rarely write this pattern consistently.
        # char(10) is \n in SQLite. We require the blank line separator and
        # enough total length to filter out trivial two-line messages.
        conn.execute(
            "UPDATE commits SET ai_tool = 'ai-assisted', ai_confidence = 'medium' "
            "WHERE ai_tool IS NULL "
            "AND message LIKE '%' || char(10) || char(10) || '_%' "
            "AND length(message) > 100 "
            "AND message NOT LIKE 'Merge %'"
        )

        # Conventional commit prefix heuristic: messages like "fix: do something"
        # or "feat: add feature". AI tools commonly produce these short, clean
        # single-line messages with a conventional prefix.
        conn.execute(
            "UPDATE commits SET ai_tool = 'ai-assisted', ai_confidence = 'low' "
            "WHERE ai_tool IS NULL "
            "AND ("
            "  message LIKE 'fix: %' OR message LIKE 'feat: %' OR message LIKE 'chore: %'"
            "  OR message LIKE 'refactor: %' OR message LIKE 'docs: %' OR message LIKE 'test: %'"
            "  OR message LIKE 'ci: %' OR message LIKE 'perf: %' OR message LIKE 'style: %'"
            "  OR message LIKE 'build: %'"
            ") "
            "AND message NOT LIKE '%' || char(10) || '%' "
            "AND length(message) BETWEEN 15 AND 120 "
            "AND message NOT LIKE 'Merge %'"
        )

        # Bulk heuristic: large additions with few deletions.
        conn.execute(
            "UPDATE commits SET ai_tool = 'unknown', ai_confidence = 'low' "
            "WHERE ai_tool IS NULL AND additions > ? AND deletions < ?",
            (_BULK_ADDITIONS_MIN, _BULK_DELETIONS_MAX),
        )

        # Count results.
        high = conn.execute(
            "SELECT COUNT(*) AS c FROM commits WHERE ai_confidence = 'high'"
        ).fetchone()["c"]
        medium = conn.execute(
            "SELECT COUNT(*) AS c FROM commits WHERE ai_confidence = 'medium'"
        ).fetchone()["c"]
        low = conn.execute(
            "SELECT COUNT(*) AS c FROM commits WHERE ai_confidence = 'low'"
        ).fetchone()["c"]

        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    return {"high": high, "medium": medium, "low": low, "total": high + medium + low}
