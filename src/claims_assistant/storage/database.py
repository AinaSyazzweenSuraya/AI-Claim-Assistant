import sqlite3
from pathlib import Path
from urllib.parse import urlsplit

import certifi
import psycopg
from psycopg.rows import dict_row

SCHEMA = """
    CREATE TABLE IF NOT EXISTS sessions (
        id TEXT PRIMARY KEY, revision INTEGER NOT NULL, payload TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS session_owners (
        session_id TEXT PRIMARY KEY REFERENCES sessions(id), owner_hash TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS drafts (
        id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id),
        receipt_hash TEXT UNIQUE, receipt_fingerprint TEXT UNIQUE,
        payload TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
"""


class PostgresConnection:
    """Small adapter preserving the repository's parameterized SQL contract."""

    def __init__(self, connection):
        self.connection = connection

    def execute(self, query: str, parameters=()):
        # Queries are fixed application SQL, with no literal question marks.
        return self.connection.execute(query.replace("?", "%s"), parameters)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is None:
            self.connection.commit()
        else:
            self.connection.rollback()
        return False

    def close(self):
        self.connection.close()


def connect(path: Path, database_url: str | None = None, initialize: bool = False):
    if database_url:
        parsed = urlsplit(database_url)
        if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
            raise ValueError("CLAIMS_DATABASE_URL must be a PostgreSQL URL")
        # Hosted connections verify certificates and hostnames. Loopback connections
        # are for local development and integration tests only.
        kwargs = {"connect_timeout": 10, "row_factory": dict_row}
        if parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            kwargs.update(sslmode="verify-full", sslrootcert=certifi.where())
        raw = psycopg.connect(database_url, **kwargs)
        connection = PostgresConnection(raw)
        if initialize:
            try:
                with connection:
                    # Serialize simultaneous cold-start table creation in PostgreSQL.
                    connection.execute("SELECT pg_advisory_xact_lock(734918206)")
                    for statement in SCHEMA.split(";"):
                        if statement.strip():
                            connection.execute(statement)
            except Exception:
                connection.close()
                raise
        return connection
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    if initialize:
        connection.executescript(SCHEMA)
    return connection
