"""SQLite data layer. All SQL lives here behind a small domain API (``Store``).

One connection, serialized with a lock (traffic is a handful of managers + their reports,
so this is plenty). JSON-ish columns are stored as TEXT and (de)serialized at the edge.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any

from .security import generate_token

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE interviews (
    id INTEGER PRIMARY KEY,
    slug TEXT UNIQUE NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    material TEXT NOT NULL DEFAULT '',
    takes TEXT NOT NULL DEFAULT '',
    rubric TEXT NOT NULL DEFAULT '',
    always_probe TEXT NOT NULL DEFAULT '',
    conduct_instructions TEXT,
    seed_questions TEXT,
    pass_threshold INTEGER NOT NULL DEFAULT 7,
    num_questions INTEGER NOT NULL DEFAULT 10,
    status TEXT NOT NULL DEFAULT 'draft',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE people (
    id INTEGER PRIMARY KEY,
    token TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    email TEXT,
    profile_note TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE attempts (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(id),
    interview_id INTEGER NOT NULL REFERENCES interviews(id),
    started_at TEXT NOT NULL,
    submitted_at TEXT,
    score REAL,
    max_score REAL,
    passed INTEGER,
    per_question TEXT,
    summary TEXT,
    time_spent_seconds INTEGER,
    created_at TEXT NOT NULL
);

CREATE TABLE events (
    id INTEGER PRIMARY KEY,
    person_id INTEGER,
    interview_id INTEGER,
    type TEXT NOT NULL,
    ts TEXT NOT NULL,
    meta TEXT
);

CREATE INDEX idx_attempts_person ON attempts(person_id);
CREATE INDEX idx_attempts_interview ON attempts(interview_id);
CREATE INDEX idx_events_ts ON events(ts);
CREATE INDEX idx_events_person ON events(person_id);
"""

# v2: participant pushback/feedback for the owner to review later. Additive — applied on top
# of v1 so the live prod DB upgrades without touching existing rows.
_SCHEMA_V2 = """
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY,
    person_id INTEGER NOT NULL REFERENCES people(id),
    interview_id INTEGER NOT NULL REFERENCES interviews(id),
    body TEXT NOT NULL,
    context TEXT,
    reviewed INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE INDEX idx_feedback_reviewed ON feedback(reviewed);
CREATE INDEX idx_feedback_interview ON feedback(interview_id);
CREATE INDEX idx_feedback_person ON feedback(person_id);
"""

_INTERVIEW_JSON = ("seed_questions",)
_ATTEMPT_JSON = ("per_question", "summary")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        if db_path != ":memory:":
            parent = os.path.dirname(os.path.abspath(db_path))
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self._migrate()

    # --- schema -----------------------------------------------------------------------
    def _migrate(self) -> None:
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            version = self._conn.execute("PRAGMA user_version").fetchone()[0]
            if version < 1:
                self._conn.executescript(_SCHEMA)
                version = 1
            if version < 2:
                self._conn.executescript(_SCHEMA_V2)
                version = 2
            self._conn.execute(f"PRAGMA user_version={version}")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- interviews -------------------------------------------------------------------
    def create_interview(self, **fields: Any) -> dict:
        slug = _slugify(fields.get("slug") or fields["title"])
        ts = now_iso()
        cols = {
            "slug": _unique_slug(self, slug),
            "title": fields["title"],
            "description": fields.get("description", ""),
            "material": fields.get("material", ""),
            "takes": fields.get("takes", ""),
            "rubric": fields.get("rubric", ""),
            "always_probe": fields.get("always_probe", ""),
            "conduct_instructions": fields.get("conduct_instructions"),
            "seed_questions": _dump(fields.get("seed_questions")),
            "pass_threshold": int(fields.get("pass_threshold", 7)),
            "num_questions": int(fields.get("num_questions", 10)),
            "status": fields.get("status", "draft"),
            "created_at": ts,
            "updated_at": ts,
        }
        with self._lock:
            cur = self._conn.execute(
                f"INSERT INTO interviews ({','.join(cols)}) "
                f"VALUES ({','.join(':' + k for k in cols)})",
                cols,
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM interviews WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        return _interview(row)

    def update_interview(self, slug: str, **fields: Any) -> dict | None:
        allowed = {
            "title", "description", "material", "takes", "rubric", "always_probe",
            "conduct_instructions", "pass_threshold", "num_questions", "status",
        }
        sets = {k: v for k, v in fields.items() if k in allowed and v is not None}
        if "seed_questions" in fields:
            sets["seed_questions"] = _dump(fields["seed_questions"])
        if not sets:
            return self.get_interview(slug)
        sets["updated_at"] = now_iso()
        assignments = ",".join(f"{k}=:{k}" for k in sets)
        with self._lock:
            cur = self._conn.execute(
                f"UPDATE interviews SET {assignments} WHERE slug=:slug",
                {**sets, "slug": slug},
            )
            self._conn.commit()
            if cur.rowcount == 0:
                return None
            row = self._conn.execute(
                "SELECT * FROM interviews WHERE slug=?", (slug,)
            ).fetchone()
        return _interview(row)

    def get_interview(self, slug: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM interviews WHERE slug=?", (slug,)
            ).fetchone()
        return _interview(row) if row else None

    def list_interviews(self, status: str | None = None) -> list[dict]:
        with self._lock:
            if status:
                rows = self._conn.execute(
                    "SELECT * FROM interviews WHERE status=? ORDER BY updated_at DESC",
                    (status,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM interviews ORDER BY updated_at DESC"
                ).fetchall()
        return [_interview(r) for r in rows]

    # --- people -----------------------------------------------------------------------
    def add_person(self, name: str, email: str | None = None) -> dict:
        token = generate_token()
        ts = now_iso()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO people (token, name, email, active, created_at) "
                "VALUES (?,?,?,1,?)",
                (token, name, email, ts),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM people WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        return _person(row)

    def get_person_by_token(self, token: str) -> dict | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM people WHERE token=?", (token,)
            ).fetchone()
        return _person(row) if row else None

    def list_people(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM people ORDER BY created_at DESC"
            ).fetchall()
        return [_person(r) for r in rows]

    def set_person_active(self, person_id: int, active: bool) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE people SET active=? WHERE id=?", (1 if active else 0, person_id)
            )
            self._conn.commit()

    def update_profile_note(self, person_id: int, note: str) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE people SET profile_note=? WHERE id=?", (note, person_id)
            )
            self._conn.commit()

    # --- attempts ---------------------------------------------------------------------
    def start_attempt(self, person_id: int, interview_id: int) -> dict:
        ts = now_iso()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO attempts (person_id, interview_id, started_at, created_at) "
                "VALUES (?,?,?,?)",
                (person_id, interview_id, ts, ts),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM attempts WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        return _attempt(row)

    def open_attempt(self, person_id: int, interview_id: int) -> dict | None:
        """Most recent not-yet-submitted attempt for this person+interview."""
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM attempts WHERE person_id=? AND interview_id=? "
                "AND submitted_at IS NULL ORDER BY started_at DESC LIMIT 1",
                (person_id, interview_id),
            ).fetchone()
        return _attempt(row) if row else None

    def submit_attempt(
        self,
        attempt_id: int,
        *,
        score: float,
        max_score: float,
        passed: bool,
        per_question: Any,
        summary: Any,
    ) -> dict:
        with self._lock:
            started = self._conn.execute(
                "SELECT started_at FROM attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            submitted = now_iso()
            elapsed = _elapsed_seconds(started["started_at"], submitted) if started else None
            self._conn.execute(
                "UPDATE attempts SET submitted_at=?, score=?, max_score=?, passed=?, "
                "per_question=?, summary=?, time_spent_seconds=? WHERE id=?",
                (
                    submitted, score, max_score, 1 if passed else 0,
                    _dump(per_question), _dump(summary), elapsed, attempt_id,
                ),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM attempts WHERE id=?", (attempt_id,)
            ).fetchone()
        return _attempt(row)

    def recent_attempts(self, person_id: int, interview_id: int, limit: int = 3) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM attempts WHERE person_id=? AND interview_id=? "
                "AND submitted_at IS NOT NULL ORDER BY submitted_at DESC LIMIT ?",
                (person_id, interview_id, limit),
            ).fetchall()
        return [_attempt(r) for r in rows]

    def has_passed(self, person_id: int, interview_id: int) -> bool:
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM attempts WHERE person_id=? AND interview_id=? AND passed=1 "
                "LIMIT 1",
                (person_id, interview_id),
            ).fetchone()
        return row is not None

    def attempts_for_interview(self, interview_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM attempts WHERE interview_id=? ORDER BY started_at DESC",
                (interview_id,),
            ).fetchall()
        return [_attempt(r) for r in rows]

    def attempts_for_person(self, person_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM attempts WHERE person_id=? ORDER BY started_at DESC",
                (person_id,),
            ).fetchall()
        return [_attempt(r) for r in rows]

    # --- events -----------------------------------------------------------------------
    def log_event(
        self,
        type: str,
        *,
        person_id: int | None = None,
        interview_id: int | None = None,
        meta: Any = None,
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO events (person_id, interview_id, type, ts, meta) "
                "VALUES (?,?,?,?,?)",
                (person_id, interview_id, type, now_iso(), _dump(meta)),
            )
            self._conn.commit()

    # --- feedback ---------------------------------------------------------------------
    def add_feedback(self, person_id: int, interview_id: int, body: str, context: str | None) -> dict:
        ts = now_iso()
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO feedback (person_id, interview_id, body, context, created_at) "
                "VALUES (?,?,?,?,?)",
                (person_id, interview_id, body, context, ts),
            )
            self._conn.commit()
            row = self._conn.execute(
                "SELECT * FROM feedback WHERE id=?", (cur.lastrowid,)
            ).fetchone()
        return _feedback(row)

    def list_feedback(self, reviewed: bool | None = None) -> list[dict]:
        """Feedback joined with person name + interview title/slug, unreviewed first, newest first."""
        sql = (
            "SELECT f.*, p.name AS person_name, i.title AS interview_title, i.slug AS interview_slug "
            "FROM feedback f "
            "JOIN people p ON p.id = f.person_id "
            "JOIN interviews i ON i.id = f.interview_id"
        )
        params: tuple = ()
        if reviewed is not None:
            sql += " WHERE f.reviewed=?"
            params = (1 if reviewed else 0,)
        sql += " ORDER BY f.reviewed ASC, f.created_at DESC"
        with self._lock:
            rows = self._conn.execute(sql, params).fetchall()
        return [_feedback(r) for r in rows]

    def set_feedback_reviewed(self, feedback_id: int, reviewed: bool) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE feedback SET reviewed=? WHERE id=?", (1 if reviewed else 0, feedback_id)
            )
            self._conn.commit()

    def unreviewed_feedback_count(self) -> int:
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) FROM feedback WHERE reviewed=0"
            ).fetchone()
        return int(row[0])


# --- row -> dict converters -----------------------------------------------------------
def _interview(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for k in _INTERVIEW_JSON:
        d[k] = _load(d.get(k))
    return d


def _person(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["active"] = bool(d["active"])
    return d


def _feedback(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["reviewed"] = bool(d["reviewed"])
    return d


def _attempt(row: sqlite3.Row) -> dict:
    d = dict(row)
    for k in _ATTEMPT_JSON:
        d[k] = _load(d.get(k))
    if d.get("passed") is not None:
        d["passed"] = bool(d["passed"])
    return d


# --- helpers --------------------------------------------------------------------------
def _dump(value: Any) -> str | None:
    return None if value is None else json.dumps(value)


def _load(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except (ValueError, TypeError):
        return value


def _slugify(text: str) -> str:
    out = "".join(c if c.isalnum() else "-" for c in text.lower()).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out[:64] or "interview"


def _unique_slug(store: "Store", base: str) -> str:
    slug, n = base, 2
    while store.get_interview(slug) is not None:
        slug = f"{base}-{n}"
        n += 1
    return slug


def _elapsed_seconds(start_iso: str, end_iso: str) -> int | None:
    try:
        start = datetime.fromisoformat(start_iso)
        end = datetime.fromisoformat(end_iso)
        return max(0, int((end - start).total_seconds()))
    except (ValueError, TypeError):
        return None
