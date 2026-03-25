"""Generate an anonymized demo database for borg.

Creates a realistic but fully synthetic dataset with:
- 2 orgs, 7 repos, 12 authors
- ~300 commits spanning 2026-01-01 to 2026-03-25
- Mix of AI (Claude, Copilot, Cursor) and human commits
- Realistic LOC distributions, PR states, production flags
- Multiple identities per author (for identity resolution demo)
- Generic commit messages (no PII, no real Jira tickets)
"""

import hashlib
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

DEMO_DB_PATH = Path(__file__).parent.parent / "demo" / "demo.db"

# --- Fake data pools ---

ORGS = [
    ("acme-corp", "2026-01-01"),
    ("globex-inc", "2026-01-15"),
]

REPOS = {
    "acme-corp": [
        "web-portal", "api-gateway", "data-pipeline",
        "auth-service", "mobile-app",
    ],
    "globex-inc": [
        "analytics-engine", "config-manager",
    ],
}

# Authors with multiple identities (email variants) for identity resolution demo
AUTHORS = [
    {
        "canonical": "Alice Chen",
        "identities": [
            ("Alice Chen", "alice.chen@example.com"),
            ("alice-chen", "alice.chen@users.noreply.github.com"),
        ],
    },
    {
        "canonical": "Bob Kumar",
        "identities": [
            ("Bob Kumar", "bob.kumar@example.com"),
            ("Bob K", "bkumar@example.com"),
        ],
    },
    {
        "canonical": "Carol Santos",
        "identities": [
            ("Carol Santos", "carol.santos@example.com"),
        ],
    },
    {
        "canonical": "Dave Okafor",
        "identities": [
            ("Dave Okafor", "dave.okafor@example.com"),
            ("dokafor", "dokafor@users.noreply.github.com"),
        ],
    },
    {
        "canonical": "Eve Petrov",
        "identities": [
            ("Eve Petrov", "eve.petrov@example.com"),
        ],
    },
    {
        "canonical": "Frank Müller",
        "identities": [
            ("Frank Müller", "frank.mueller@example.com"),
            ("Frank Mueller", "frank.mueller@example.com"),
        ],
    },
    {
        "canonical": "Grace Kim",
        "identities": [
            ("Grace Kim", "grace.kim@example.com"),
        ],
    },
    {
        "canonical": "Hiro Tanaka",
        "identities": [
            ("Hiro Tanaka", "hiro.tanaka@example.com"),
            ("hiro-t", "hiro.tanaka@users.noreply.github.com"),
        ],
    },
    {
        "canonical": "Ines García",
        "identities": [
            ("Ines García", "ines.garcia@example.com"),
            ("Ines Garcia", "ines.garcia@example.com"),
        ],
    },
    {
        "canonical": "Jake Wilson",
        "identities": [
            ("Jake Wilson", "jake.wilson@example.com"),
        ],
    },
    {
        "canonical": "Carst Vaartjes",
        "identities": [
            ("Carst Vaartjes", "carstvaartjes@example.com"),
            ("Carst Vaartjes", "carstvaartjes@example.com"),
            ("CarstVaartjes", "6408702+CarstVaartjes@users.noreply.github.com"),
        ],
        "weight": 3,  # top contributor
    },
    {
        "canonical": "Leo Rossi",
        "identities": [
            ("Leo Rossi", "leo.rossi@example.com"),
            ("lrossi", "lrossi@users.noreply.github.com"),
        ],
    },
]

# Generic commit message templates
HUMAN_MESSAGES = [
    "Update README with setup instructions",
    "Fix typo in configuration docs",
    "Bump dependency versions",
    "Add .gitignore entries for IDE files",
    "Clean up unused imports",
    "Adjust logging levels for production",
    "Fix flaky test in CI",
    "Update Docker base image",
    "Add health check endpoint",
    "Refactor database connection pool",
    "Fix race condition in worker queue",
    "Update API documentation",
    "Add retry logic for HTTP calls",
    "Fix timezone handling in reports",
    "Optimize database index for search",
    "Add request validation middleware",
    "Fix pagination offset bug",
    "Update error messages for clarity",
    "Add CSV export functionality",
    "Fix memory leak in cache layer",
    "Improve startup time with lazy loading",
    "Add graceful shutdown handler",
    "Fix CORS headers for API",
    "Update CI pipeline configuration",
    "Add input sanitization for forms",
]

AI_MESSAGES_HIGH = [
    # Claude trailer style
    (
        "Implement user notification system\n\n"
        "- Add email and in-app notification channels\n"
        "- Create notification preferences per user\n"
        "- Add rate limiting to prevent spam\n\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>"
    ),
    (
        "Add comprehensive test suite for auth module\n\n"
        "Co-Authored-By: Claude Opus 4.5 <noreply@anthropic.com>"
    ),
    (
        "Refactor data processing pipeline\n\n"
        "- Split monolithic processor into stages\n"
        "- Add checkpointing between stages\n"
        "- Improve error recovery\n\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>"
    ),
    (
        "Fix authentication token refresh logic\n\n"
        "The token refresh was using the wrong expiry check.\n\n"
        "Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
    ),
    (
        "Add API rate limiting with sliding window\n\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>"
    ),
    (
        "Implement search functionality with filters\n\n"
        "- Full-text search on title and description\n"
        "- Filter by date range, status, and category\n"
        "- Pagination with cursor-based navigation\n\n"
        "Co-Authored-By: Claude <noreply@anthropic.com>"
    ),
    # Copilot style
    (
        "Add input validation for API endpoints\n\n"
        "Co-Authored-By: Copilot <noreply@github.com>"
    ),
    (
        "Implement caching layer for frequently accessed data\n\n"
        "Co-Authored-By: Copilot <noreply@github.com>"
    ),
    # Cursor style
    (
        "Generated by Cursor\n\n"
        "Implement dashboard widget for metrics overview"
    ),
]

AI_MESSAGES_MEDIUM = [
    # Structured message style (summary + blank line + body)
    (
        "Implement batch processing for large datasets\n\n"
        "- Process records in configurable chunk sizes\n"
        "- Add progress tracking with ETA estimation\n"
        "- Handle partial failures with dead letter queue\n"
        "- Add metrics for throughput and error rates"
    ),
    (
        "Add role-based access control system\n\n"
        "- Define permission hierarchy with inheritance\n"
        "- Add middleware for route-level authorization\n"
        "- Create admin UI for role management\n"
        "- Add audit logging for permission changes"
    ),
    (
        "Optimize database queries for reporting\n\n"
        "- Add composite indexes for common filter combinations\n"
        "- Rewrite N+1 queries to use JOINs\n"
        "- Add query result caching with TTL\n"
        "- Reduce report generation time by 60%"
    ),
    (
        "Implement webhook delivery system\n\n"
        "- Queue-based delivery with configurable retry\n"
        "- Exponential backoff with jitter\n"
        "- Delivery status tracking and reporting\n"
        "- Signature verification for security"
    ),
]

AI_MESSAGES_LOW = [
    "feat: add user preference settings",
    "fix: resolve null pointer in data export",
    "feat: implement dark mode toggle",
    "fix: correct date formatting in reports",
    "feat: add bulk import functionality",
    "fix: handle edge case in pagination",
    "feat: add email template system",
    "fix: resolve race condition in queue processor",
    "PROJ-101: Add scheduled task runner",
    "PROJ-202: Fix data sync for large accounts",
    "PROJ-303: Implement audit trail",
]

AI_TOOLS = {
    "high": [
        ("claude", "high"),
        ("copilot", "high"),
        ("cursor", "high"),
    ],
    "medium": [("claude", "medium")],
    "low": [("claude", "low")],
}

random.seed(42)  # Reproducible

START_DATE = datetime(2026, 1, 1)
END_DATE = datetime(2026, 3, 25)
DATE_RANGE = (END_DATE - START_DATE).days


def fake_sha(seed: str) -> str:
    """Generate a deterministic fake SHA from a seed string."""
    return hashlib.sha256(seed.encode()).hexdigest()[:40]


def random_date() -> str:
    """Generate a random datetime in the range."""
    delta = timedelta(
        days=random.randint(0, DATE_RANGE),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    dt = START_DATE + delta
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def random_loc(is_ai: bool) -> tuple[int, int]:
    """Generate realistic additions/deletions."""
    if is_ai:
        additions = random.choice([
            random.randint(50, 300),   # typical AI chunk
            random.randint(10, 50),    # small fix
            random.randint(300, 800),  # large feature
        ])
        deletions = random.randint(0, additions // 3)
    else:
        additions = random.choice([
            random.randint(1, 20),     # small human edit
            random.randint(20, 100),   # medium change
            random.randint(5, 15),     # config tweak
        ])
        deletions = random.randint(0, additions // 2)
    return additions, deletions


def generate() -> None:
    """Generate the demo database."""
    DEMO_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    if DEMO_DB_PATH.exists():
        DEMO_DB_PATH.unlink()

    conn = sqlite3.connect(str(DEMO_DB_PATH))
    conn.executescript("""
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
            in_production INTEGER NOT NULL DEFAULT 0,
            pr_number INTEGER,
            pr_state TEXT,
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

        CREATE TABLE IF NOT EXISTS author_aliases (
            email TEXT PRIMARY KEY,
            canonical_name TEXT NOT NULL
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
    """)

    # Insert orgs
    for org_name, since in ORGS:
        conn.execute(
            "INSERT INTO orgs VALUES (?, ?, ?)",
            (org_name, since, "2026-03-25T10:00:00Z"),
        )

    # Generate commits
    commits = []
    pr_counter = {org: {repo: 100 for repo in repos} for org, repos in REPOS.items()}

    # Build weighted author list (higher weight = more commits)
    weighted_authors = []
    for a in AUTHORS:
        w = a.get("weight", 1)
        weighted_authors.extend([a] * w)

    for i in range(300):
        # Pick org and repo
        org_name = random.choice(list(REPOS.keys()))
        repo = random.choice(REPOS[org_name])

        # Pick author identity (weighted)
        author_info = random.choice(weighted_authors)
        identity = random.choice(author_info["identities"])
        name, email = identity

        # Decide AI vs human (roughly 45% AI)
        is_ai = random.random() < 0.45

        if is_ai:
            tier = random.choices(["high", "medium", "low"], weights=[50, 30, 20])[0]
            if tier == "high":
                message = random.choice(AI_MESSAGES_HIGH)
                tool, confidence = random.choice(AI_TOOLS["high"])
            elif tier == "medium":
                message = random.choice(AI_MESSAGES_MEDIUM)
                tool, confidence = AI_TOOLS["medium"][0]
            else:
                message = random.choice(AI_MESSAGES_LOW)
                tool, confidence = AI_TOOLS["low"][0]
        else:
            message = random.choice(HUMAN_MESSAGES)
            tool, confidence = None, None

        additions, deletions = random_loc(is_ai)
        date = random_date()
        sha = fake_sha(f"{i}-{org_name}-{repo}-{name}-{date}")

        # PR info
        pr_num = pr_counter[org_name][repo]
        pr_counter[org_name][repo] += random.randint(0, 1)
        pr_state = random.choices(
            ["merged", "open", "closed"],
            weights=[60, 25, 15],
        )[0]
        in_production = 1 if pr_state == "merged" and random.random() < 0.8 else 0

        commits.append((
            sha, org_name, repo, name, email, date,
            additions, deletions, message, tool, confidence,
            in_production, pr_num, pr_state,
            "2026-03-25T10:00:00Z",
        ))

    conn.executemany(
        "INSERT INTO commits VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        commits,
    )

    # Insert repo_sync entries
    for org_name, repos in REPOS.items():
        for repo in repos:
            conn.execute(
                "INSERT INTO repo_sync VALUES (?, ?, ?, ?, ?)",
                (org_name, repo, "2026-03-25T10:00:00Z",
                 "2026-03-25T10:00:00Z", 0),
            )

    conn.execute(
        "INSERT INTO sync_meta VALUES (?, ?)",
        ("last_run", "2026-03-25T10:00:00Z"),
    )

    conn.commit()
    conn.close()

    # Run identity resolution via borg's Database class
    from borg.db import Database
    db = Database(DEMO_DB_PATH)
    db.rebuild_author_identities()
    identities = db.conn.execute(
        "SELECT COUNT(DISTINCT canonical_name) FROM _author_identity"
    ).fetchone()[0]
    db.conn.close()

    # Reopen for stats
    conn = sqlite3.connect(str(DEMO_DB_PATH))

    # Stats
    total = conn.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
    ai = conn.execute(
        "SELECT COUNT(*) FROM commits WHERE ai_tool IS NOT NULL"
    ).fetchone()[0]
    authors = conn.execute(
        "SELECT COUNT(DISTINCT author) FROM commits"
    ).fetchone()[0]
    repos_count = conn.execute(
        "SELECT COUNT(DISTINCT repo) FROM commits"
    ).fetchone()[0]

    conn.close()

    print(f"Demo database generated: {DEMO_DB_PATH}")
    print(f"  {total} commits ({ai} AI, {total - ai} human)")
    print(f"  {authors} authors, {repos_count} repos")
    print(f"  {len(ORGS)} orgs: {', '.join(o[0] for o in ORGS)}")
    print(f"  {identities} resolved identities")


if __name__ == "__main__":
    generate()
