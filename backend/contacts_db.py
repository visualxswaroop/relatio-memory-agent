"""
Contacts & Relationship database layer.
Manages contacts, per-contact memory units, and commitments.
"""

import sqlite3
import json

CONTACTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    company TEXT,
    role TEXT,
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS relationship_memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES contacts(id),
    meeting_id INTEGER REFERENCES meetings(id),
    memory_type TEXT NOT NULL,
    -- Types: interest, preference, concern, objection, goal, pain_point,
    --        decision, requirement, fact, pattern, change
    content TEXT NOT NULL,
    context TEXT,           -- short context/source label (e.g. "Sept 18 meeting")
    is_active INTEGER DEFAULT 1,  -- 0 = superseded by newer memory
    superseded_by INTEGER REFERENCES relationship_memories(id),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS commitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER REFERENCES contacts(id),
    meeting_id INTEGER REFERENCES meetings(id),
    description TEXT NOT NULL,
    owner TEXT,             -- 'me' or contact name
    deadline_text TEXT,
    status TEXT DEFAULT 'pending' CHECK(status IN ('pending','done','cancelled')),
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    UNIQUE(contact_id, description, owner)
);
"""


def init_contacts_db(db_path: str = "data/meetings.db"):
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.executescript(CONTACTS_SCHEMA)
    conn.commit()
    conn.close()


def get_contacts_db(db_path: str = "data/meetings.db") -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.isolation_level = None
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


# ---- Contacts CRUD ----

def create_contact(db, name: str, company: str = None, role: str = None, notes: str = None) -> int:
    cursor = db.execute(
        "INSERT OR IGNORE INTO contacts (name, company, role, notes) VALUES (?, ?, ?, ?)",
        (name, company, role, notes),
    )
    if cursor.lastrowid:
        db.commit()
        return cursor.lastrowid
    # Already exists — return existing id
    row = db.execute("SELECT id FROM contacts WHERE name = ?", (name,)).fetchone()
    return row["id"] if row else None


def get_contact(db, contact_id: int) -> dict:
    row = db.execute("SELECT * FROM contacts WHERE id = ?", (contact_id,)).fetchone()
    return dict(row) if row else None


def get_contact_by_name(db, name: str) -> dict:
    row = db.execute("SELECT * FROM contacts WHERE name = ?", (name,)).fetchone()
    return dict(row) if row else None


def get_all_contacts(db) -> list[dict]:
    rows = db.execute("SELECT * FROM contacts ORDER BY name ASC").fetchall()
    return [dict(r) for r in rows]


def update_contact(db, contact_id: int, company: str = None, role: str = None, notes: str = None):
    db.execute(
        "UPDATE contacts SET company=COALESCE(?,company), role=COALESCE(?,role), notes=COALESCE(?,notes), updated_at=datetime('now') WHERE id=?",
        (company, role, notes, contact_id),
    )
    db.commit()


# ---- Relationship Memories ----

def save_relationship_memory(
    db,
    contact_id: int,
    memory_type: str,
    content: str,
    meeting_id: int = None,
    context: str = None,
) -> int:
    cursor = db.execute(
        """INSERT INTO relationship_memories (contact_id, meeting_id, memory_type, content, context)
           VALUES (?, ?, ?, ?, ?)""",
        (contact_id, meeting_id, memory_type, content, context),
    )
    db.commit()
    return cursor.lastrowid


def get_relationship_memories(db, contact_id: int, memory_type: str = None) -> list[dict]:
    if memory_type:
        rows = db.execute(
            "SELECT * FROM relationship_memories WHERE contact_id=? AND memory_type=? AND is_active=1 ORDER BY created_at DESC",
            (contact_id, memory_type),
        ).fetchall()
    else:
        rows = db.execute(
            "SELECT * FROM relationship_memories WHERE contact_id=? AND is_active=1 ORDER BY memory_type, created_at DESC",
            (contact_id,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_all_memories_for_contact(db, contact_id: int) -> list[dict]:
    rows = db.execute(
        "SELECT * FROM relationship_memories WHERE contact_id=? ORDER BY created_at ASC",
        (contact_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_contact_meetings(db, contact_id: int) -> list[dict]:
    """Return all meetings that have memories for this contact."""
    rows = db.execute(
        """SELECT DISTINCT m.id, m.title, m.date FROM meetings m
           JOIN relationship_memories rm ON rm.meeting_id = m.id
           WHERE rm.contact_id = ?
           ORDER BY m.date ASC""",
        (contact_id,),
    ).fetchall()
    return [dict(r) for r in rows]


# ---- Commitments ----

def save_commitment(
    db,
    description: str,
    contact_id: int = None,
    meeting_id: int = None,
    owner: str = None,
    deadline_text: str = None,
) -> int:
    """Insert a commitment, ignoring if one already exists for this contact+description+owner."""
    cursor = db.execute(
        """INSERT OR IGNORE INTO commitments (contact_id, meeting_id, description, owner, deadline_text)
           VALUES (?, ?, ?, ?, ?)""",
        (contact_id, meeting_id, description, owner, deadline_text),
    )
    db.commit()
    if cursor.lastrowid:
        return cursor.lastrowid
    # Already exists — return existing id
    row = db.execute(
        "SELECT id FROM commitments WHERE contact_id IS ? AND description=? AND owner IS ?",
        (contact_id, description, owner),
    ).fetchone()
    return row["id"] if row else None


def get_commitments(db, contact_id: int = None, status: str = None) -> list[dict]:
    query = "SELECT c.*, co.name as contact_name FROM commitments c LEFT JOIN contacts co ON co.id = c.contact_id WHERE 1=1"
    params = []
    if contact_id:
        query += " AND c.contact_id = ?"
        params.append(contact_id)
    if status:
        query += " AND c.status = ?"
        params.append(status)
    query += " ORDER BY c.created_at DESC"
    rows = db.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_commitment_status(db, commitment_id: int, status: str):
    db.execute(
        "UPDATE commitments SET status=?, updated_at=datetime('now') WHERE id=?",
        (status, commitment_id),
    )
    db.commit()
