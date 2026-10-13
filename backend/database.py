"""SQLite database setup and connection handling for GitMind."""

import os
import shutil
import sqlite3
import json

# The database used to live at backend/gitmind.db — right next to the code.
# That means every time you replace the project folder with an updated copy
# (a new zip, a git pull into a fresh directory, etc.), the new code came
# with no database file, and your previously analyzed repos looked "gone" —
# they weren't lost, they were just sitting in the *old* folder that the new
# code never looks at.
#
# Fix: store the database in a stable, per-user location outside the project
# folder entirely, so replacing the code never touches your data. Override
# with the GITMIND_DB_PATH environment variable if you want it somewhere
# else (e.g. a specific data directory, or the old in-project behavior).
_DEFAULT_DB_DIR = os.path.join(os.path.expanduser("~"), ".gitmind")
_DEFAULT_DB_PATH = os.path.join(_DEFAULT_DB_DIR, "gitmind.db")
DB_PATH = os.environ.get("GITMIND_DB_PATH", _DEFAULT_DB_PATH)

# Where the database used to live, for one-time migration below.
_LEGACY_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "gitmind.db")


def _migrate_legacy_db_if_present() -> None:
    """One-time migration: if a database already exists at the old
    in-project location (from before this fix) and nothing exists yet at
    the new stable location, move it over automatically. This means
    updating to this version of GitMind — as long as you're updating the
    *same* project folder rather than extracting to a brand new one —
    preserves whatever history you already had, and every update after
    this one is safe regardless of where the project folder lives."""
    if os.path.exists(DB_PATH):
        return
    if not os.path.exists(_LEGACY_DB_PATH):
        return
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    shutil.copy2(_LEGACY_DB_PATH, DB_PATH)
    print(f"[GitMind] Migrated existing database from {_LEGACY_DB_PATH} to {DB_PATH}")


def get_connection() -> sqlite3.Connection:
    """Return a new SQLite connection with row access by column name."""
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create the repositories table if it doesn't already exist."""
    _migrate_legacy_db_if_present()
    conn = get_connection()
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS repositories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL,
                name TEXT NOT NULL,
                full_name TEXT NOT NULL UNIQUE,
                description TEXT,
                stars INTEGER NOT NULL DEFAULT 0,
                forks INTEGER NOT NULL DEFAULT 0,
                open_issues INTEGER NOT NULL DEFAULT 0,
                language TEXT,
                url TEXT,
                last_commit_at TEXT,
                open_pr_count INTEGER NOT NULL DEFAULT 0,
                stale_pr_count INTEGER NOT NULL DEFAULT 0,
                health_score INTEGER NOT NULL DEFAULT 0,
                risk_flags TEXT NOT NULL DEFAULT '[]',
                summary TEXT,
                predicted_category TEXT,
                predicted_category_confidence REAL,
                ml_health_label TEXT,
                ml_health_confidence REAL,
                source TEXT NOT NULL DEFAULT 'github',
                branch TEXT,
                contributor_count INTEGER,
                first_commit_at TEXT,
                branches TEXT NOT NULL DEFAULT '[]',
                contributors TEXT NOT NULL DEFAULT '[]',
                languages TEXT NOT NULL DEFAULT '{}',
                commit_activity TEXT NOT NULL DEFAULT '[]',
                health_status TEXT,
                health_breakdown TEXT NOT NULL DEFAULT '{}',
                ci_cd TEXT,
                dependencies TEXT,
                releases TEXT NOT NULL DEFAULT '[]',
                issue_analysis TEXT,
                pr_analysis TEXT,
                contributor_analysis TEXT,
                release_analysis TEXT,
                branch_analysis TEXT,
                testing_analysis TEXT,
                documentation_analysis TEXT,
                license_info TEXT,
                topics TEXT NOT NULL DEFAULT '[]',
                is_favorite INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS repo_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_id INTEGER NOT NULL REFERENCES repositories(id) ON DELETE CASCADE,
                captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                health_score INTEGER,
                security_score INTEGER,
                days_since_last_commit INTEGER,
                open_issues INTEGER,
                open_pr_count INTEGER,
                stars INTEGER,
                contributor_count INTEGER,
                digest TEXT,
                metrics_json TEXT
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_repo_snapshots_repo_id ON repo_snapshots(repo_id)"
        )
        # Legacy cleanup: the local-repo feature (and its hotspot snapshots) was
        # removed, so drop any leftovers from older databases.
        conn.execute("DROP TABLE IF EXISTS hotspot_snapshots")
        conn.execute("DELETE FROM repositories WHERE source = 'local'")
        _ensure_columns(conn)
        _ensure_snapshot_columns(conn)
        conn.commit()
    finally:
        conn.close()


def record_snapshot(
    conn: sqlite3.Connection,
    repo_id: int,
    health_score,
    security_score,
    days_since_last_commit,
    open_issues,
    open_pr_count,
    stars,
    contributor_count,
    digest: str = None,
    metrics: dict = None,
) -> None:
    """Insert a point-in-time snapshot of this repo's key metrics. Called
    once per real analysis (see main.py) — every analyze/re-analyze call
    adds a new row rather than overwriting, so history accumulates
    naturally over repeated real analyses of the same repo. Nothing here is
    synthesized or backfilled: the trend line is exactly as long as the
    number of times you've actually analyzed the repo.

    `digest` is a short, human-readable summary of what changed since the
    *previous* snapshot (see changelog.py) — computed by the caller, who
    has to fetch the previous row anyway, and stored here so the "what
    changed" history never has to be recomputed on read."""
    conn.execute(
        """
        INSERT INTO repo_snapshots
            (repo_id, health_score, security_score, days_since_last_commit,
             open_issues, open_pr_count, stars, contributor_count, digest, metrics_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (repo_id, health_score, security_score, days_since_last_commit,
         open_issues, open_pr_count, stars, contributor_count, digest,
         json.dumps(metrics or {}, separators=(",", ":"))),
    )


def get_latest_snapshot(conn: sqlite3.Connection, repo_id: int) -> dict:
    """Most recent snapshot for a repo, or None if it's never been
    analyzed before (i.e. this is about to be the first snapshot)."""
    row = conn.execute(
        "SELECT * FROM repo_snapshots WHERE repo_id = ? ORDER BY captured_at DESC, id DESC LIMIT 1",
        (repo_id,),
    ).fetchone()
    return dict(row) if row else None


def get_snapshots(conn: sqlite3.Connection, repo_id: int) -> list:
    rows = conn.execute(
        "SELECT * FROM repo_snapshots WHERE repo_id = ? ORDER BY captured_at ASC",
        (repo_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def _ensure_columns(conn: sqlite3.Connection) -> None:
    """Add new columns to a pre-existing gitmind.db from older versions of the app."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(repositories)")}
    migrations = {
        "last_commit_at": "ALTER TABLE repositories ADD COLUMN last_commit_at TEXT",
        "open_pr_count": "ALTER TABLE repositories ADD COLUMN open_pr_count INTEGER NOT NULL DEFAULT 0",
        "stale_pr_count": "ALTER TABLE repositories ADD COLUMN stale_pr_count INTEGER NOT NULL DEFAULT 0",
        "health_score": "ALTER TABLE repositories ADD COLUMN health_score INTEGER NOT NULL DEFAULT 0",
        "risk_flags": "ALTER TABLE repositories ADD COLUMN risk_flags TEXT NOT NULL DEFAULT '[]'",
        "summary": "ALTER TABLE repositories ADD COLUMN summary TEXT",
        "predicted_category": "ALTER TABLE repositories ADD COLUMN predicted_category TEXT",
        "predicted_category_confidence": "ALTER TABLE repositories ADD COLUMN predicted_category_confidence REAL",
        "ml_health_label": "ALTER TABLE repositories ADD COLUMN ml_health_label TEXT",
        "ml_health_confidence": "ALTER TABLE repositories ADD COLUMN ml_health_confidence REAL",
        "source": "ALTER TABLE repositories ADD COLUMN source TEXT NOT NULL DEFAULT 'github'",
        "branch": "ALTER TABLE repositories ADD COLUMN branch TEXT",
        "contributor_count": "ALTER TABLE repositories ADD COLUMN contributor_count INTEGER",
        "first_commit_at": "ALTER TABLE repositories ADD COLUMN first_commit_at TEXT",
        "branches": "ALTER TABLE repositories ADD COLUMN branches TEXT NOT NULL DEFAULT '[]'",
        "contributors": "ALTER TABLE repositories ADD COLUMN contributors TEXT NOT NULL DEFAULT '[]'",
        "languages": "ALTER TABLE repositories ADD COLUMN languages TEXT NOT NULL DEFAULT '{}'",
        "commit_activity": "ALTER TABLE repositories ADD COLUMN commit_activity TEXT NOT NULL DEFAULT '[]'",
        "health_status": "ALTER TABLE repositories ADD COLUMN health_status TEXT",
        "health_breakdown": "ALTER TABLE repositories ADD COLUMN health_breakdown TEXT NOT NULL DEFAULT '{}'",
        "ci_cd": "ALTER TABLE repositories ADD COLUMN ci_cd TEXT",
        "dependencies": "ALTER TABLE repositories ADD COLUMN dependencies TEXT",
        "releases": "ALTER TABLE repositories ADD COLUMN releases TEXT NOT NULL DEFAULT '[]'",
        "issue_analysis": "ALTER TABLE repositories ADD COLUMN issue_analysis TEXT",
        "pr_analysis": "ALTER TABLE repositories ADD COLUMN pr_analysis TEXT",
        "contributor_analysis": "ALTER TABLE repositories ADD COLUMN contributor_analysis TEXT",
        "release_analysis": "ALTER TABLE repositories ADD COLUMN release_analysis TEXT",
        "branch_analysis": "ALTER TABLE repositories ADD COLUMN branch_analysis TEXT",
        "testing_analysis": "ALTER TABLE repositories ADD COLUMN testing_analysis TEXT",
        "documentation_analysis": "ALTER TABLE repositories ADD COLUMN documentation_analysis TEXT",
        "license_info": "ALTER TABLE repositories ADD COLUMN license_info TEXT",
        "topics": "ALTER TABLE repositories ADD COLUMN topics TEXT NOT NULL DEFAULT '[]'",
        "is_favorite": "ALTER TABLE repositories ADD COLUMN is_favorite INTEGER NOT NULL DEFAULT 0",
    }
    for column, ddl in migrations.items():
        if column not in existing:
            conn.execute(ddl)


def _ensure_snapshot_columns(conn: sqlite3.Connection) -> None:
    """Same pattern as _ensure_columns, for the repo_snapshots table."""
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(repo_snapshots)")}
    migrations = {
        "digest": "ALTER TABLE repo_snapshots ADD COLUMN digest TEXT",
        "metrics_json": "ALTER TABLE repo_snapshots ADD COLUMN metrics_json TEXT",
    }
    for column, ddl in migrations.items():
        if column not in existing:
            conn.execute(ddl)
