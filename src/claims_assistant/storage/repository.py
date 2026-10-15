import json
import sqlite3
from pathlib import Path

import psycopg

from claims_assistant.agent.state import AgentState
from claims_assistant.storage.database import connect


class ConflictError(ValueError):
    pass


class Repository:
    def __init__(self, path: Path, database_url: str | None = None):
        self.path = path
        self.database_url = database_url
        with connect(path, database_url, initialize=True) as connection:
            connection.execute("SELECT 1")
        connection.close()

    def create(self, owner_hash: str | None = None) -> AgentState:
        state = AgentState()
        connection = connect(self.path, self.database_url)
        try:
            with connection:
                connection.execute(
                    "INSERT INTO sessions VALUES (?, ?, ?)",
                    (state.session_id, state.revision, state.model_dump_json()),
                )
                if owner_hash is not None:
                    connection.execute(
                        "INSERT INTO session_owners (session_id, owner_hash) VALUES (?, ?)",
                        (state.session_id, owner_hash),
                    )
        finally:
            connection.close()
        return state

    def load(self, session_id: str, owner_hash: str | None = None) -> AgentState:
        connection = connect(self.path, self.database_url)
        try:
            query = "SELECT payload FROM sessions WHERE id=?"
            parameters = (session_id,)
            if owner_hash is not None:
                query += (
                    " AND EXISTS (SELECT 1 FROM session_owners"
                    " WHERE session_id=sessions.id AND owner_hash=?)"
                )
                parameters += (owner_hash,)
            row = connection.execute(query, parameters).fetchone()
        finally:
            connection.close()
        if not row:
            raise KeyError("Session not found")
        return AgentState.model_validate_json(row["payload"])

    def receipt_used(self, evidence_hash: str, fingerprint: str) -> bool:
        connection = connect(self.path, self.database_url)
        try:
            return (
                connection.execute(
                    "SELECT 1 FROM drafts WHERE receipt_hash=? OR receipt_fingerprint=?",
                    (evidence_hash, fingerprint),
                ).fetchone()
                is not None
            )
        finally:
            connection.close()

    def commit(self, state: AgentState, expected_revision: int, draft: dict | None = None) -> None:
        connection = connect(self.path, self.database_url)
        next_state = state.model_copy(update={"revision": expected_revision + 1})
        try:
            with connection:
                cursor = connection.execute(
                    "UPDATE sessions SET revision=?, payload=? WHERE id=? AND revision=?",
                    (
                        next_state.revision,
                        next_state.model_dump_json(),
                        state.session_id,
                        expected_revision,
                    ),
                )
                if cursor.rowcount != 1:
                    raise ConflictError("Session changed; reload before retrying")
                if draft:
                    receipt = state.claim.receipt
                    connection.execute(
                        "INSERT INTO drafts "
                        "(id,session_id,receipt_hash,receipt_fingerprint,payload) "
                        "VALUES (?,?,?,?,?)",
                        (
                            draft["id"],
                            state.session_id,
                            receipt.evidence_hash if receipt else None,
                            receipt.fingerprint() if receipt else None,
                            json.dumps(draft),
                        ),
                    )
        except (sqlite3.IntegrityError, psycopg.IntegrityError) as exc:
            raise ConflictError("Duplicate receipt or draft; nothing was saved") from exc
        finally:
            connection.close()
        state.revision = next_state.revision

    def draft(self, draft_id: str, owner_hash: str | None = None) -> dict:
        connection = connect(self.path, self.database_url)
        try:
            query = "SELECT payload FROM drafts WHERE id=?"
            parameters = (draft_id,)
            if owner_hash is not None:
                query += (
                    " AND EXISTS (SELECT 1 FROM session_owners"
                    " WHERE session_id=drafts.session_id AND owner_hash=?)"
                )
                parameters += (owner_hash,)
            row = connection.execute(query, parameters).fetchone()
        finally:
            connection.close()
        if not row:
            raise KeyError("Draft not found")
        return json.loads(row["payload"])
