"""
Flask application for Meeting Commitment Agent.
"""

import io
import json
import logging
import os

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_file, send_from_directory
from flask_cors import CORS

from backend import db, memory, pipeline, ics, contacts_db, relationship_agent

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__, static_folder="../frontend", static_url_path="")
CORS(app)

DB_PATH = os.path.join("data", "meetings.db")
UPLOAD_DIR = "uploads"
os.makedirs("data", exist_ok=True)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Initialize databases
db.init_db(DB_PATH)
contacts_db.init_contacts_db(DB_PATH)

# ---- Hindsight client (lazy init) ----
_hs_client = None


def _get_hs():
    global _hs_client
    if _hs_client is None:
        _hs_client = memory.init_hindsight()
        if _hs_client:
            memory.setup_mental_models(_hs_client)
    return _hs_client


# ---- Serve frontend ----
@app.route("/")
def index():
    return send_from_directory(app.static_folder, "index.html")


# ---- Meeting processing ----
@app.route("/api/process", methods=["POST"])
def process_meeting():
    """Process a meeting from transcript text or audio upload."""
    title = request.form.get("title", "Untitled Meeting")
    date = request.form.get("date", "")
    team = request.form.get("team", "default")
    transcript_text = request.form.get("transcript", "")

    audio_path = None
    if "audio" in request.files:
        f = request.files["audio"]
        if f.filename:
            audio_path = os.path.join(UPLOAD_DIR, f.filename)
            f.save(audio_path)

    if not transcript_text and not audio_path:
        return jsonify({"error": "Please provide either a transcript or audio file."}), 400

    result = pipeline.process_meeting(
        title=title,
        date=date,
        team=team,
        transcript_text=transcript_text if transcript_text else None,
        audio_path=audio_path,
        db_path=DB_PATH,
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


@app.route("/api/meetings/<int:meeting_id>/confirm-participants", methods=["POST"])
def confirm_participants(meeting_id):
    """Confirm/edit participants for a meeting and re-save."""
    data = request.get_json()
    participants = data.get("participants", [])
    
    database = db.get_db(DB_PATH)
    meeting = db.get_meeting(database, meeting_id)
    if not meeting:
        return jsonify({"error": "Meeting not found"}), 404

    # Update participants in the meeting record
    database.execute(
        "UPDATE meetings SET participants = ? WHERE id = ?",
        (json.dumps(participants), meeting_id),
    )
    
    # Also update extraction_json with new participants
    try:
        extraction = json.loads(meeting["extraction_json"]) if meeting["extraction_json"] else {}
        extraction["participants"] = participants
        database.execute(
            "UPDATE meetings SET extraction_json = ? WHERE id = ?",
            (json.dumps(extraction), meeting_id),
        )
    except Exception:
        pass
    
    database.commit()
    return jsonify({"success": True, "participants": participants})


# ---- Meetings CRUD ----
@app.route("/api/meetings")
def list_meetings():
    database = db.get_db(DB_PATH)
    meetings = db.get_all_meetings(database)
    # Strip large fields for listing
    for m in meetings:
        m.pop("transcript", None)
        m.pop("corrected_transcript", None)
        m.pop("extraction_json", None)
    return jsonify(meetings)


@app.route("/api/meetings/<int:meeting_id>")
def get_meeting(meeting_id):
    database = db.get_db(DB_PATH)
    meeting = db.get_meeting(database, meeting_id)
    if not meeting:
        return jsonify({"error": "Not found"}), 404
    # Parse JSON fields
    if meeting.get("extraction_json"):
        try:
            meeting["extraction"] = json.loads(meeting["extraction_json"])
        except Exception:
            meeting["extraction"] = {}
    if meeting.get("participants"):
        try:
            meeting["participants_list"] = json.loads(meeting["participants"])
        except Exception:
            meeting["participants_list"] = []
    return jsonify(meeting)


# ---- Tasks ----
@app.route("/api/tasks")
def list_tasks():
    database = db.get_db(DB_PATH)
    status = request.args.get("status")
    owner = request.args.get("owner")
    tasks = db.get_tasks(database, status=status, owner=owner)
    return jsonify(tasks)


@app.route("/api/tasks/silent")
def silent_tasks():
    database = db.get_db(DB_PATH)
    return jsonify(db.get_silent_tasks(database))


@app.route("/api/tasks/open")
def open_tasks():
    database = db.get_db(DB_PATH)
    return jsonify(db.get_open_tasks(database))


@app.route("/api/tasks/<task_key>/history")
def task_history(task_key):
    database = db.get_db(DB_PATH)
    return jsonify(db.get_task_history(database, task_key))


@app.route("/api/tasks/<task_key>/status", methods=["PUT"])
def update_task_status(task_key):
    data = request.get_json()
    new_status = data.get("status")
    if new_status not in ("new", "in_progress", "done", "blocked"):
        return jsonify({"error": "Invalid status"}), 400
    database = db.get_db(DB_PATH)
    database.execute(
        "UPDATE tasks SET status = ?, updated_at = datetime('now') WHERE key = ?",
        (new_status, task_key),
    )
    database.commit()
    return jsonify({"success": True})


# ---- Analytics ----
@app.route("/api/follow-through")
def follow_through():
    database = db.get_db(DB_PATH)
    return jsonify(db.get_follow_through(database))


@app.route("/api/stuck-topics")
def stuck_topics():
    database = db.get_db(DB_PATH)
    return jsonify(db.get_stuck_topics(database))


@app.route("/api/promise-drift")
def promise_drift():
    database = db.get_db(DB_PATH)
    return jsonify(db.get_promise_drift(database))


# ---- Brief ----
@app.route("/api/brief", methods=["POST"])
def generate_brief():
    """Generate pre-meeting brief. Returns both memory-on and memory-off versions."""
    data = request.get_json()
    user_name = data.get("user_name", "User")
    database = db.get_db(DB_PATH)

    # Memory OFF (baseline)
    baseline = pipeline.generate_brief(
        user_name=user_name,
        hs_client=None,
        database=database,
        use_memory=False,
    )

    # Memory ON
    hs = _get_hs()
    enhanced = pipeline.generate_brief(
        user_name=user_name,
        hs_client=hs,
        database=database,
        use_memory=True,
    )

    return jsonify({
        "user_name": user_name,
        "baseline": baseline,
        "enhanced": enhanced,
    })


# ---- Corrections (human-in-the-loop) ----
@app.route("/api/corrections", methods=["POST"])
def save_correction():
    data = request.get_json()
    database = db.get_db(DB_PATH)
    db.save_correction(
        database,
        meeting_id=data.get("meeting_id"),
        task_key=data.get("task_key"),
        field=data.get("field"),
        original_value=data.get("original_value"),
        corrected_value=data.get("corrected_value"),
        correction_type=data.get("correction_type", "task"),
    )
    return jsonify({"success": True})


# ---- Calendar / ICS ----
@app.route("/api/calendar/propose", methods=["POST"])
def propose_events():
    """Return proposed calendar events from a meeting's important_dates."""
    data = request.get_json()
    meeting_id = data.get("meeting_id")
    database = db.get_db(DB_PATH)
    meeting = db.get_meeting(database, meeting_id)
    if not meeting:
        return jsonify({"error": "Meeting not found"}), 404

    extraction = {}
    if meeting.get("extraction_json"):
        try:
            extraction = json.loads(meeting["extraction_json"])
        except Exception:
            pass

    dates = extraction.get("important_dates", [])
    proposals = []
    for d in dates:
        if d.get("date"):
            proposals.append({
                "title": d.get("title", "Event"),
                "date": d["date"],
                "date_text": d.get("date_text", ""),
                "confirmed": False,
            })
    return jsonify(proposals)


@app.route("/api/calendar/download", methods=["POST"])
def download_ics():
    """Download .ics file for confirmed events."""
    data = request.get_json()
    events = data.get("events", [])
    if not events:
        return jsonify({"error": "No events to export"}), 400

    ics_content = ics.generate_multi_ics(events)
    buf = io.BytesIO(ics_content.encode("utf-8"))
    buf.seek(0)
    return send_file(
        buf,
        mimetype="text/calendar",
        as_attachment=True,
        download_name="meeting_events.ics",
    )


# ---- Exports ----
@app.route("/api/export/tasks/<fmt>")
def export_tasks(fmt):
    """Export open tasks as markdown or CSV."""
    database = db.get_db(DB_PATH)
    tasks = db.get_open_tasks(database)

    if fmt == "markdown" or fmt == "md":
        lines = ["# Open Tasks\n"]
        for t in tasks:
            owner = t.get("owner") or "Unassigned"
            status = t.get("status", "new")
            line = f"- **[{status}]** {t['description']} — Owner: {owner}"
            if t.get("deadline_text"):
                line += f" — Deadline: {t['deadline_text']}"
            lines.append(line)
        content = "\n".join(lines)
        buf = io.BytesIO(content.encode("utf-8"))
        buf.seek(0)
        return send_file(buf, mimetype="text/markdown", as_attachment=True, download_name="open_tasks.md")

    elif fmt == "csv":
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Key", "Description", "Owner", "Status", "Deadline", "Confidence", "Quote"])
        for t in tasks:
            writer.writerow([
                t.get("key", ""),
                t.get("description", ""),
                t.get("owner", ""),
                t.get("status", ""),
                t.get("deadline_text", ""),
                t.get("confidence", ""),
                t.get("quote", ""),
            ])
        buf = io.BytesIO(output.getvalue().encode("utf-8"))
        buf.seek(0)
        return send_file(buf, mimetype="text/csv", as_attachment=True, download_name="open_tasks.csv")

    return jsonify({"error": "Unsupported format. Use 'markdown' or 'csv'."}), 400


@app.route("/api/export/issues/<fmt>")
def export_issues(fmt):
    """Export open issues as markdown or CSV."""
    database = db.get_db(DB_PATH)
    meetings = db.get_all_meetings(database)
    
    all_issues = []
    for m in meetings:
        if m.get("extraction_json"):
            try:
                ext = json.loads(m["extraction_json"])
                for issue in ext.get("open_issues", []):
                    all_issues.append({
                        "text": issue.get("text", str(issue)),
                        "quote": issue.get("quote", ""),
                        "meeting": m.get("title", ""),
                        "date": m.get("date", ""),
                    })
            except Exception:
                pass

    if fmt == "markdown" or fmt == "md":
        lines = ["# Open Issues\n"]
        for issue in all_issues:
            lines.append(f"- {issue['text']} (from: {issue['meeting']}, {issue['date']})")
        content = "\n".join(lines)
        buf = io.BytesIO(content.encode("utf-8"))
        buf.seek(0)
        return send_file(buf, mimetype="text/markdown", as_attachment=True, download_name="open_issues.md")

    elif fmt == "csv":
        import csv
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Issue", "Quote", "Meeting", "Date"])
        for issue in all_issues:
            writer.writerow([issue["text"], issue["quote"], issue["meeting"], issue["date"]])
        buf = io.BytesIO(output.getvalue().encode("utf-8"))
        buf.seek(0)
        return send_file(buf, mimetype="text/csv", as_attachment=True, download_name="open_issues.csv")

    return jsonify({"error": "Unsupported format. Use 'markdown' or 'csv'."}), 400


# ---- Mental Models ----
@app.route("/api/mental-models")
def get_mental_models():
    hs = _get_hs()
    results = {}
    for model_id in ["task-slip-patterns", "decision-reversal-tracker"]:
        content = memory.get_mental_model_content(hs, model_id) if hs else None
        results[model_id] = content
    return jsonify(results)


# ---- Health check ----
@app.route("/api/health")
@app.route("/health")
def health():
    hs = _get_hs()
    return jsonify({
        "status": "ok",
        "hindsight_connected": hs is not None,
        "bank_id": os.getenv("BANK_ID", ""),
    })


# ============================================================
# ---- RELATIONSHIP INTELLIGENCE ROUTES ----
# ============================================================

# ---- Contacts ----
@app.route("/api/contacts", methods=["GET"])
def list_contacts():
    database = contacts_db.get_contacts_db(DB_PATH)
    contacts = contacts_db.get_all_contacts(database)
    # Enrich with memory counts
    for c in contacts:
        memories = contacts_db.get_relationship_memories(database, c["id"])
        c["memory_count"] = len(memories)
        meetings = contacts_db.get_contact_meetings(database, c["id"])
        c["meeting_count"] = len(meetings)
        commitments = contacts_db.get_commitments(database, contact_id=c["id"], status="pending")
        c["pending_commitments"] = len(commitments)
    return jsonify(contacts)


@app.route("/api/contacts", methods=["POST"])
def create_contact():
    data = request.get_json()
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"error": "Contact name is required"}), 400
    database = contacts_db.get_contacts_db(DB_PATH)
    contact_id = contacts_db.create_contact(
        database,
        name=name,
        company=data.get("company"),
        role=data.get("role"),
        notes=data.get("notes"),
    )
    contact = contacts_db.get_contact(database, contact_id)
    return jsonify(contact)


@app.route("/api/contacts/<int:contact_id>", methods=["GET"])
def get_contact(contact_id):
    database = contacts_db.get_contacts_db(DB_PATH)
    contact = contacts_db.get_contact(database, contact_id)
    if not contact:
        return jsonify({"error": "Contact not found"}), 404
    contact["memories"] = contacts_db.get_relationship_memories(database, contact_id)
    contact["commitments"] = contacts_db.get_commitments(database, contact_id=contact_id)
    contact["meetings"] = contacts_db.get_contact_meetings(database, contact_id)
    return jsonify(contact)


@app.route("/api/contacts/<int:contact_id>", methods=["PUT"])
def update_contact(contact_id):
    data = request.get_json()
    database = contacts_db.get_contacts_db(DB_PATH)
    contacts_db.update_contact(
        database, contact_id,
        company=data.get("company"),
        role=data.get("role"),
        notes=data.get("notes"),
    )
    return jsonify(contacts_db.get_contact(database, contact_id))


# ---- Process meeting WITH contact intelligence ----
@app.route("/api/contacts/<int:contact_id>/process-meeting", methods=["POST"])
def process_meeting_for_contact(contact_id):
    """
    Process a meeting transcript and extract relationship intelligence for a contact.
    This is the core Hindsight-integrated relationship learning endpoint.
    """
    data = request.get_json()
    meeting_id = data.get("meeting_id")  # existing meeting already in DB
    transcript = data.get("transcript", "")
    meeting_title = data.get("meeting_title", "Meeting")
    meeting_date = data.get("meeting_date", "")

    if not transcript:
        return jsonify({"error": "Transcript is required"}), 400

    database = contacts_db.get_contacts_db(DB_PATH)
    contact = contacts_db.get_contact(database, contact_id)
    if not contact:
        return jsonify({"error": "Contact not found"}), 404

    hs = _get_hs()
    result = relationship_agent.process_meeting_for_contact(
        meeting_id=meeting_id,
        contact_name=contact["name"],
        transcript=transcript,
        meeting_title=meeting_title,
        meeting_date=meeting_date,
        db=database,
        hs_client=hs,
        contact_id=contact_id,
    )

    if "error" in result:
        return jsonify(result), 400
    return jsonify(result)


# ---- Quick add meeting notes for a contact (no separate meeting record needed) ----
@app.route("/api/contacts/<int:contact_id>/add-notes", methods=["POST"])
def add_contact_meeting_notes(contact_id):
    """
    Quick endpoint: add meeting notes for a contact directly.
    Creates a meeting record and processes relationship intelligence in one step.
    """
    data = request.get_json()
    notes = data.get("notes", "").strip()
    meeting_title = data.get("title", "Meeting Notes")
    meeting_date = data.get("date", "")

    if not notes:
        return jsonify({"error": "Notes are required"}), 400

    database = contacts_db.get_contacts_db(DB_PATH)
    contact = contacts_db.get_contact(database, contact_id)
    if not contact:
        return jsonify({"error": "Contact not found"}), 404

    # Save minimal meeting record
    meeting_id = db.save_meeting(
        database,
        title=meeting_title,
        date=meeting_date,
        team=contact["name"],
        transcript=notes,
        corrected_transcript=notes,
        summary="",
        participants_json=json.dumps([contact["name"]]),
        extraction_json=json.dumps({}),
        memory_synced=0,
    )

    hs = _get_hs()
    result = relationship_agent.process_meeting_for_contact(
        meeting_id=meeting_id,
        contact_name=contact["name"],
        transcript=notes,
        meeting_title=meeting_title,
        meeting_date=meeting_date,
        db=database,
        hs_client=hs,
        contact_id=contact_id,
    )

    result["meeting_id"] = meeting_id
    return jsonify(result)


# ---- Personalized meeting brief for a contact ----
@app.route("/api/contacts/<int:contact_id>/brief", methods=["POST"])
def contact_brief(contact_id):
    """Generate a personalized pre-meeting brief for a contact using Hindsight memories."""
    data = request.get_json() or {}
    objective = data.get("objective", "")

    database = contacts_db.get_contacts_db(DB_PATH)
    contact = contacts_db.get_contact(database, contact_id)
    if not contact:
        return jsonify({"error": "Contact not found"}), 404

    hs = _get_hs()
    result = relationship_agent.generate_contact_brief(
        contact_name=contact["name"],
        db=database,
        hs_client=hs,
        objective=objective if objective else None,
    )
    return jsonify(result)


# ---- "What do you remember?" query ----
@app.route("/api/contacts/<int:contact_id>/remember", methods=["POST"])
def contact_memory_query(contact_id):
    """Answer a natural-language memory query about a contact."""
    data = request.get_json()
    query = data.get("query", "").strip()
    if not query:
        return jsonify({"error": "Query is required"}), 400

    database = contacts_db.get_contacts_db(DB_PATH)
    contact = contacts_db.get_contact(database, contact_id)
    if not contact:
        return jsonify({"error": "Contact not found"}), 404

    hs = _get_hs()
    result = relationship_agent.answer_memory_query(
        contact_name=contact["name"],
        query=query,
        db=database,
        hs_client=hs,
    )
    return jsonify(result)


# ---- Relationship evolution ----
@app.route("/api/contacts/<int:contact_id>/evolution", methods=["GET"])
def contact_evolution(contact_id):
    """Generate a relationship evolution summary."""
    database = contacts_db.get_contacts_db(DB_PATH)
    contact = contacts_db.get_contact(database, contact_id)
    if not contact:
        return jsonify({"error": "Contact not found"}), 404

    hs = _get_hs()
    result = relationship_agent.generate_relationship_evolution(
        contact_name=contact["name"],
        db=database,
        hs_client=hs,
    )
    return jsonify(result)


# ---- Commitments ----
@app.route("/api/commitments")
def list_all_commitments():
    database = contacts_db.get_contacts_db(DB_PATH)
    status = request.args.get("status")
    commitments = contacts_db.get_commitments(database, status=status)
    return jsonify(commitments)


@app.route("/api/contacts/<int:contact_id>/commitments")
def list_contact_commitments(contact_id):
    database = contacts_db.get_contacts_db(DB_PATH)
    status = request.args.get("status")
    commitments = contacts_db.get_commitments(database, contact_id=contact_id, status=status)
    return jsonify(commitments)


@app.route("/api/commitments/<int:commitment_id>/status", methods=["PUT"])
def update_commitment_status(commitment_id):
    data = request.get_json()
    status = data.get("status")
    if status not in ("pending", "done", "cancelled"):
        return jsonify({"error": "Invalid status"}), 400
    database = contacts_db.get_contacts_db(DB_PATH)
    contacts_db.update_commitment_status(database, commitment_id, status)
    return jsonify({"success": True})


# ---- Contact memories ----
@app.route("/api/contacts/<int:contact_id>/memories")
def contact_memories(contact_id):
    database = contacts_db.get_contacts_db(DB_PATH)
    memory_type = request.args.get("type")
    memories = contacts_db.get_relationship_memories(database, contact_id, memory_type=memory_type)
    return jsonify(memories)


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False, threaded=False, host="0.0.0.0", port=5000)
