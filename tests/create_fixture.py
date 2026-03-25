"""Create an anonymized test fixture DB from the real database.

Run: uv run python tests/create_fixture.py

Produces tests/fixture.db with ~200 commits sampled from the real data,
with anonymized author names and emails but preserved structure
(AI trailers, PR states, repos, dates).
"""
import hashlib
import re
import sqlite3
from pathlib import Path

from borg.db import Database
from borg.detect import detect_ai

REAL_DB = Path.home() / ".local" / "share" / "borg" / "tracker.db"
FIXTURE_DB = Path(__file__).parent / "fixture.db"

# Anonymization maps
FAKE_NAMES = [
    "Alice Chen", "Bob Martinez", "Carol Williams", "Dave Johnson",
    "Eve Anderson", "Frank Thomas", "Grace Lee", "Henry Wilson",
    "Iris Brown", "Jack Davis", "Kate Miller", "Leo Garcia",
    "Maya Robinson", "Nick Taylor", "Olivia Moore", "Paul Jackson",
    "Quinn White", "Rosa Harris", "Sam Martin", "Tina Thompson",
]

FAKE_REPOS = [
    "platform-api", "frontend-kit", "data-service", "config-hub",
    "auth-gateway", "pipeline-engine", "report-builder",
]


def anonymize_email(email: str, name_map: dict) -> str:
    """Generate a consistent fake email from real email."""
    h = hashlib.md5(email.encode()).hexdigest()[:8]
    fake_name = name_map.get(email, "unknown").lower().replace(" ", ".")
    return f"{fake_name}@example.com"


def anonymize_message(message: str, name_map: dict) -> str:
    """Keep AI trailers intact, anonymize everything else."""
    lines = message.split("\n")
    result = []
    for line in lines:
        # Preserve Co-Authored-By lines (these are the AI signatures)
        if "Co-Authored-By" in line or "Co-authored-by" in line:
            result.append(line)
        # Preserve ticket references pattern but anonymize
        elif re.match(r"^(feat|fix|chore|ci|docs|refactor|test)", line):
            result.append(line[:80])
        else:
            # Keep first line as-is (commit title), truncate rest
            if not result:
                result.append(line[:80])
            else:
                result.append(line[:60] if line.strip() else "")
    return "\n".join(result)


def main():
    if not REAL_DB.exists():
        print(f"Real DB not found at {REAL_DB}")
        return

    # Remove old fixture
    FIXTURE_DB.unlink(missing_ok=True)

    real_conn = sqlite3.connect(str(REAL_DB))
    real_conn.row_factory = sqlite3.Row

    # Sample commits: mix of AI and non-AI, different PR states, multiple repos
    # Get a diverse sample
    queries = [
        # Commits with Claude trailers
        "SELECT * FROM commits WHERE message LIKE '%Co-Authored-By:%Claude%' ORDER BY RANDOM() LIMIT 40",
        # Commits with other AI trailers
        "SELECT * FROM commits WHERE message LIKE '%Co-Authored-By:%Copilot%' ORDER BY RANDOM() LIMIT 10",
        # Open PR commits
        "SELECT * FROM commits WHERE pr_state = 'open' AND message NOT LIKE '%Co-Authored-By%' ORDER BY RANDOM() LIMIT 40",
        # Merged PR commits (no AI)
        "SELECT * FROM commits WHERE pr_state = 'merged' AND message NOT LIKE '%Co-Authored-By%' ORDER BY RANDOM() LIMIT 50",
        # Closed/abandoned PR commits
        "SELECT * FROM commits WHERE pr_state = 'closed' ORDER BY RANDOM() LIMIT 30",
        # Commits with high additions (for bulk heuristic)
        "SELECT * FROM commits WHERE additions > 100 AND deletions < 10 ORDER BY RANDOM() LIMIT 15",
        # Regular small commits
        "SELECT * FROM commits WHERE additions < 50 AND additions IS NOT NULL ORDER BY RANDOM() LIMIT 15",
    ]

    all_commits = []
    seen_shas = set()
    for q in queries:
        try:
            rows = real_conn.execute(q).fetchall()
            for r in rows:
                if r["sha"] not in seen_shas:
                    all_commits.append(dict(r))
                    seen_shas.add(r["sha"])
        except Exception as e:
            print(f"Warning: {e}")

    print(f"Sampled {len(all_commits)} commits")

    # Build name map from unique emails
    emails = sorted(set(c["email"] for c in all_commits))
    name_map = {}
    for i, email in enumerate(emails):
        name_map[email] = FAKE_NAMES[i % len(FAKE_NAMES)]

    # Build repo map
    repos = sorted(set(c["repo"] for c in all_commits))
    repo_map = {}
    for i, repo in enumerate(repos):
        repo_map[repo] = FAKE_REPOS[i % len(FAKE_REPOS)]

    # Create fixture DB
    fixture_db = Database(FIXTURE_DB)

    # Add anonymized org
    fixture_db.org_add("test-org", "2025-01-01")

    # Insert anonymized commits
    for c in all_commits:
        fake_author = name_map.get(c["email"], "Unknown Dev")
        fake_email = anonymize_email(c["email"], name_map)
        fake_repo = repo_map.get(c["repo"], "unknown-repo")
        fake_message = anonymize_message(c["message"] or "", name_map)

        fixture_db.conn.execute(
            """INSERT OR IGNORE INTO commits
               (sha, org, repo, author, email, date, additions, deletions,
                message, ai_tool, ai_confidence, in_production, pr_number,
                pr_state, fetched_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                c["sha"], "test-org", fake_repo, fake_author, fake_email,
                c["date"], c.get("additions"), c.get("deletions"),
                fake_message, None, None,
                c.get("in_production", 0), c.get("pr_number"),
                c.get("pr_state"), c["fetched_at"],
            ),
        )
    fixture_db.conn.commit()

    # Run detection on the fixture
    result = detect_ai(fixture_db)
    print(f"Detection: {result}")

    # Verify
    total = fixture_db.conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
    ai = fixture_db.conn.execute("SELECT COUNT(*) FROM commits WHERE ai_tool IS NOT NULL").fetchone()[0]
    print(f"Fixture DB: {total} commits, {ai} AI-detected")
    print(f"Saved to: {FIXTURE_DB}")


if __name__ == "__main__":
    main()
