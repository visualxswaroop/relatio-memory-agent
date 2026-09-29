"""Cleanup duplicate commitments - deduplicate by (contact_id, description, owner) keeping oldest."""
import sqlite3

conn = sqlite3.connect("data/meetings.db")
conn.isolation_level = None
conn.row_factory = sqlite3.Row

# Drop functional index if exists (SQLite functional indexes need 3.38+)
try:
    conn.execute("DROP INDEX IF EXISTS uq_commitment")
except Exception as e:
    print(f"Drop index: {e}")

total_before = conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0]
print(f"Commitments before dedup: {total_before}")

# Delete duplicates where SAME contact, description, owner — keep min(id)
conn.execute("""
    DELETE FROM commitments
    WHERE id NOT IN (
        SELECT MIN(id)
        FROM commitments
        GROUP BY contact_id, description, owner
    )
""")

total_after = conn.execute("SELECT COUNT(*) FROM commitments").fetchone()[0]
print(f"Commitments after dedup:  {total_after}")
print(f"Deleted: {total_before - total_after} rows")

# Show remaining
rows = conn.execute(
    "SELECT c.id, co.name as contact, c.description, c.owner, c.status, c.meeting_id "
    "FROM commitments c LEFT JOIN contacts co ON co.id = c.contact_id ORDER BY c.id"
).fetchall()
print(f"\nFinal commitments ({len(rows)}):")
for r in rows:
    print(f"  [{r['id']}] contact={r['contact']} | {r['description']} | owner={r['owner']} | meeting={r['meeting_id']}")

conn.close()
print("\nDone.")
