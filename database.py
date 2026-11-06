"""SQLite connection handling and schema."""

import sqlite3

from flask import current_app, g

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL CHECK (role IN ('tenant', 'staff', 'manager')),
    phone         TEXT,
    unit          TEXT,
    specialty     TEXT,
    active        INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requests (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    tenant_id         INTEGER NOT NULL REFERENCES users(id),
    title             TEXT NOT NULL,
    description       TEXT NOT NULL,
    category          TEXT NOT NULL,
    unit              TEXT,
    urgency           TEXT NOT NULL CHECK (urgency IN ('Low', 'Medium', 'High', 'Critical')),
    predicted_urgency TEXT NOT NULL,
    confidence        REAL,
    urgency_source    TEXT NOT NULL DEFAULT 'model',
    status            TEXT NOT NULL DEFAULT 'Open'
                      CHECK (status IN ('Open', 'Assigned', 'In Progress', 'Resolved')),
    assigned_to       INTEGER REFERENCES users(id),
    sla_hours         INTEGER NOT NULL,
    created_at        TEXT NOT NULL,
    due_at            TEXT NOT NULL,
    assigned_at       TEXT,
    started_at        TEXT,
    resolved_at       TEXT,
    resolution_notes  TEXT
);

CREATE TABLE IF NOT EXISTS status_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    request_id INTEGER NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    status     TEXT NOT NULL,
    note       TEXT,
    actor_id   INTEGER REFERENCES users(id),
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_requests_tenant   ON requests(tenant_id);
CREATE INDEX IF NOT EXISTS idx_requests_assigned ON requests(assigned_to);
CREATE INDEX IF NOT EXISTS idx_requests_status   ON requests(status);
CREATE INDEX IF NOT EXISTS idx_history_request   ON status_history(request_id);
"""


def connect(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        g.db = connect(current_app.config["DATABASE"])
    return g.db


def close_db(_exc=None) -> None:
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(path: str) -> None:
    conn = connect(path)
    try:
        conn.executescript(SCHEMA)
        conn.commit()
    finally:
        conn.close()
