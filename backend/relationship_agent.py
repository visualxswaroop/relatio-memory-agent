"""
Relationship Intelligence Agent Pipeline.

Handles:
- Extracting relationship memories from meeting transcripts
- Storing per-contact memories in Hindsight (as discrete memory units)
- Retrieving memories for meeting prep
- Generating personalized meeting briefs
- Answering "What do you remember?" queries
- Tracking relationship evolution
"""

import json
import logging
import os
from datetime import datetime

from backend import contacts_db, relationship_prompts
from backend.pipeline import _llm_call, _clean_llm_output

log = logging.getLogger(__name__)

DB_PATH = os.path.join("data", "meetings.db")


# ---------------------------------------------------------------------------
# Hindsight bank ID for relationship memories (separate from meeting bank)
# ---------------------------------------------------------------------------

def _relationship_bank_id() -> str:
    """Bank ID for relationship/contact memories."""
    return os.getenv("RELATIONSHIP_BANK_ID", os.getenv("BANK_ID", "meeting-intelligence"))


def _init_relationship_bank(hs_client):
    """Create relationship memory bank if it doesn't exist."""
    if not hs_client:
        return False
    bank_id = _relationship_bank_id()
    try:
        hs_client.create_bank(
            bank_id=bank_id,
            name="Relationship Intelligence Bank",
            retain_mission=(
                "Track individual relationship histories: preferences, concerns, goals, "
                "objections, commitments, and how each person's priorities evolve over time. "
                "Prefer specific, concrete, evidence-backed facts over generalizations."
            ),
            reflect_mission=(
                "Identify patterns in relationships: recurring concerns, changing priorities, "
                "communication preferences, and relationship trajectory over time."
            ),
            retain_extraction_mode="verbose",
            enable_observations=True,
            enable_temporal_retrieval=True,
        )
        return True
    except Exception as e:
        log.debug("Relationship bank create/exists: %s", e)
        return True  # Bank likely already exists


# ---------------------------------------------------------------------------
# Step 1: Extract relationship intelligence from a transcript
# ---------------------------------------------------------------------------

def extract_relationship_intelligence(
    transcript: str,
    contact_name: str,
) -> dict:
    """
    Call LLM to extract structured relationship intelligence from a transcript.
    Returns the parsed dict (interests, concerns, commitments, etc.)
    """
    prompt = relationship_prompts.RELATIONSHIP_EXTRACTION_PROMPT.format(
        contact_name=contact_name,
        transcript=transcript,
    )
    try:
        raw = _llm_call(
            messages=[{"role": "user", "content": prompt}],
            model_env="MODEL_EXTRACT",
            json_mode=True,
            max_tokens=4096,
        )
        data = json.loads(_clean_llm_output(raw))
        return data
    except Exception as e:
        log.error("Relationship extraction failed: %s", e)
        return {}


# ---------------------------------------------------------------------------
# Step 2: Store memories in Hindsight (as discrete memory units per contact)
# ---------------------------------------------------------------------------

def store_relationship_memories_in_hindsight(
    hs_client,
    contact_name: str,
    meeting_id: int,
    meeting_date: str,
    meeting_title: str,
    extracted: dict,
) -> int:
    """
    Store each type of extracted intelligence as a separate Hindsight document.
    This is the core Hindsight integration — NOT a single blob, but discrete memory units.
    Returns count of memories stored.
    """
    if not hs_client:
        return 0

    bank_id = _relationship_bank_id()
    _init_relationship_bank(hs_client)

    stored_count = 0
    try:
        meeting_dt = datetime.fromisoformat(meeting_date.replace("Z", "+00:00")) if meeting_date else None
    except ValueError:
        meeting_dt = None

    contact_tag = f"contact:{contact_name.lower().replace(' ', '_')}"

    # Map of extraction field → memory description
    memory_types = [
        ("interests", "interest", "Interest"),
        ("preferences", "preference", "Preference"),
        ("concerns", "concern", "Concern"),
        ("objections", "objection", "Objection"),
        ("goals", "goal", "Goal"),
        ("requirements", "requirement", "Requirement"),
        ("decisions", "decision", "Decision"),
        ("facts", "fact", "Fact"),
        ("changes", "change", "Priority/Concern Change"),
        ("open_issues", "open_issue", "Open Issue"),
    ]

    for field, mem_type, label in memory_types:
        items = extracted.get(field, [])
        for i, item in enumerate(items):
            content = item.get("content", "") if isinstance(item, dict) else str(item)
            quote = item.get("quote", "") if isinstance(item, dict) else ""
            if not content:
                continue

            doc_text = f"[{label}] {contact_name}: {content}"
            if quote:
                doc_text += f'\n\nEvidence: "{quote}"'
            doc_text += f"\n\nSource: {meeting_title} ({meeting_date})"

            doc_id = f"rel-{contact_name.lower().replace(' ', '-')}-{mem_type}-{meeting_id}-{i}"

            try:
                hs_client.retain(
                    bank_id=bank_id,
                    content=doc_text,
                    timestamp=meeting_dt,
                    context=f"{contact_name} - {label} - {meeting_title}",
                    document_id=doc_id,
                    tags=[contact_tag, f"type:{mem_type}", f"meeting:{meeting_id}"],
                    update_mode="replace",
                )
                stored_count += 1
            except Exception as e:
                log.warning("Failed to store %s memory for %s: %s", mem_type, contact_name, e)

    # Store commitments separately
    for i, commitment in enumerate(extracted.get("commitments", [])):
        desc = commitment.get("description", "")
        owner = commitment.get("owner", "")
        deadline = commitment.get("deadline_text", "")
        if not desc:
            continue

        doc_text = f"[Commitment] {contact_name}: {desc}"
        if owner:
            doc_text += f"\nOwner: {owner}"
        if deadline:
            doc_text += f"\nDeadline: {deadline}"
        doc_text += f"\nSource: {meeting_title} ({meeting_date})"

        doc_id = f"rel-{contact_name.lower().replace(' ', '-')}-commitment-{meeting_id}-{i}"
        try:
            hs_client.retain(
                bank_id=bank_id,
                content=doc_text,
                timestamp=meeting_dt,
                context=f"{contact_name} - Commitment - {meeting_title}",
                document_id=doc_id,
                tags=[contact_tag, "type:commitment", f"meeting:{meeting_id}"],
                update_mode="replace",
            )
            stored_count += 1
        except Exception as e:
            log.warning("Failed to store commitment for %s: %s", contact_name, e)

    log.info("Stored %d relationship memory units in Hindsight for %s", stored_count, contact_name)
    return stored_count


# ---------------------------------------------------------------------------
# Step 3: Store memories locally in SQLite too
# ---------------------------------------------------------------------------

def store_relationship_memories_locally(
    db,
    contact_id: int,
    meeting_id: int,
    meeting_title: str,
    meeting_date: str,
    extracted: dict,
) -> int:
    """Store extracted relationship memories in local DB for fast retrieval."""
    context = f"{meeting_title} ({meeting_date})"
    count = 0

    type_map = [
        ("interests", "interest"),
        ("preferences", "preference"),
        ("concerns", "concern"),
        ("objections", "objection"),
        ("goals", "goal"),
        ("requirements", "requirement"),
        ("decisions", "decision"),
        ("facts", "fact"),
        ("changes", "change"),
        ("open_issues", "open_issue"),
    ]

    for field, mem_type in type_map:
        for item in extracted.get(field, []):
            content = item.get("content", "") if isinstance(item, dict) else str(item)
            quote = item.get("quote", "") if isinstance(item, dict) else ""
            if not content:
                continue
            full_content = content
            if quote:
                full_content += f' | Evidence: "{quote}"'
            contacts_db.save_relationship_memory(
                db, contact_id, mem_type, full_content, meeting_id, context
            )
            count += 1

    # Store commitments
    for c in extracted.get("commitments", []):
        desc = c.get("description", "")
        if not desc:
            continue
        contacts_db.save_commitment(
            db,
            description=desc,
            contact_id=contact_id,
            meeting_id=meeting_id,
            owner=c.get("owner"),
            deadline_text=c.get("deadline_text"),
        )

    log.info("Stored %d relationship memories locally for contact_id=%d", count, contact_id)
    return count


# ---------------------------------------------------------------------------
# Step 4: Retrieve memories from Hindsight for a contact
# ---------------------------------------------------------------------------

def recall_contact_memories(hs_client, contact_name: str, query: str) -> list[str]:
    """Recall contact-specific memories from Hindsight."""
    if not hs_client:
        return []

    bank_id = _relationship_bank_id()
    contact_tag = f"contact:{contact_name.lower().replace(' ', '_')}"

    try:
        response = hs_client.recall(
            bank_id=bank_id,
            query=query,
            types=["world", "experience", "observation"],
            max_tokens=1500,
            budget="mid",
            tags=[contact_tag],
            tags_match="all",
            include_entities=True,
        )
        if hasattr(response, "results"):
            return [r.text for r in response.results if hasattr(r, "text")]
        return []
    except Exception as e:
        log.warning("Hindsight recall for %s failed: %s", contact_name, e)
        return []


def reflect_contact_insights(hs_client, contact_name: str, query: str) -> dict:
    """Reflect on patterns for a contact from Hindsight."""
    if not hs_client:
        return {"text": "", "based_on": []}

    bank_id = _relationship_bank_id()
    contact_tag = f"contact:{contact_name.lower().replace(' ', '_')}"

    try:
        response = hs_client.reflect(
            bank_id=bank_id,
            query=query,
            budget="mid",
            tags=[contact_tag],
            include_facts=True,
        )
        raw_based_on = getattr(response, "based_on", []) or []
        based_on = []
        for b in raw_based_on:
            if hasattr(b, "model_dump"):
                based_on.append(b.model_dump())
            elif hasattr(b, "dict"):
                based_on.append(b.dict())
            elif hasattr(b, "__dict__"):
                based_on.append(vars(b))
            else:
                based_on.append(str(b))
        return {
            "text": getattr(response, "text", ""),
            "based_on": based_on,
        }
    except Exception as e:
        log.warning("Hindsight reflect for %s failed: %s", contact_name, e)
        return {"text": "", "based_on": []}


# ---------------------------------------------------------------------------
# Step 5: Generate personalized meeting brief
# ---------------------------------------------------------------------------

def generate_contact_brief(
    contact_name: str,
    db,
    hs_client,
    objective: str = None,
) -> dict:
    """
    Generate a personalized meeting brief for a contact.
    Uses Hindsight memories + local DB data.
    """
    contact = contacts_db.get_contact_by_name(db, contact_name)
    contact_id = contact["id"] if contact else None

    # Local DB data
    local_memories = contacts_db.get_relationship_memories(db, contact_id) if contact_id else []
    open_commitments = contacts_db.get_commitments(db, contact_id=contact_id, status="pending") if contact_id else []
    contact_meetings = contacts_db.get_contact_meetings(db, contact_id) if contact_id else []

    # Hindsight retrieval
    hindsight_facts = []
    hindsight_insights = {"text": "", "based_on": []}

    if hs_client and contact_id:
        query = (
            f"What are {contact_name}'s interests, concerns, objections, goals, requirements, "
            f"open issues, commitments, and how have their priorities changed over time?"
        )
        hindsight_facts = recall_contact_memories(hs_client, contact_name, query)

        insights_query = (
            f"What patterns exist in {contact_name}'s behavior? "
            f"How have their concerns and priorities evolved? "
            f"What recurring issues or themes appear across meetings?"
        )
        hindsight_insights = reflect_contact_insights(hs_client, contact_name, insights_query)

    # Format local memories (limit to recent 25 to prevent exceeding LLM input token limits)
    def _fmt_memories(mems):
        if not mems:
            return "None recorded."
        mems = mems[-25:] if len(mems) > 25 else mems
        grouped = {}
        for m in mems:
            t = m.get("memory_type", "fact")
            grouped.setdefault(t, []).append(f"  - {m['content']} [{m.get('context', '')}]")
        lines = []
        for t, items in grouped.items():
            lines.append(f"{t.upper()}S:")
            lines.extend(items)
        return "\n".join(lines)

    def _fmt_commitments(commitments):
        if not commitments:
            return "None recorded."
        return "\n".join(
            f"  - [{c['status'].upper()}] {c['description']} "
            f"(owner: {c.get('owner', 'unknown')}"
            f"{', deadline: ' + c['deadline_text'] if c.get('deadline_text') else ''})"
            for c in commitments
        )

    def _fmt_contact(c):
        if not c:
            return "No contact record found."
        parts = [f"Name: {c['name']}"]
        if c.get("company"):
            parts.append(f"Company: {c['company']}")
        if c.get("role"):
            parts.append(f"Role: {c['role']}")
        if c.get("notes"):
            parts.append(f"Notes: {c['notes']}")
        parts.append(f"Meeting history: {len(contact_meetings)} meeting(s) recorded")
        if contact_meetings:
            parts.append("Meetings: " + ", ".join(f"{m['title']} ({m['date']})" for m in contact_meetings))
        return "\n".join(parts)

    objective_section = (
        relationship_prompts.OBJECTIVE_SECTION.format(objective=objective)
        if objective
        else ""
    )

    prompt = relationship_prompts.CONTACT_BRIEF_PROMPT.format(
        contact_name=contact_name,
        objective_section=objective_section,
        hindsight_memories="\n".join(f"- {f}" for f in hindsight_facts[:10]) if hindsight_facts else "No memories recalled from Hindsight yet.",
        hindsight_insights=hindsight_insights.get("text") or "No pattern insights yet.",
        local_memories=_fmt_memories(local_memories),
        open_commitments=_fmt_commitments(open_commitments),
        contact_info=_fmt_contact(contact),
    )

    try:
        brief_text = _llm_call(
            messages=[{"role": "user", "content": prompt}],
            model_env="MODEL_BRIEF",
            max_tokens=3000,
        )
    except Exception as e:
        log.error("Brief generation failed: %s", e)
        brief_text = f"Brief generation failed: {e}"

    return {
        "contact_name": contact_name,
        "brief": brief_text,
        "memory_count": len(hindsight_facts),
        "local_memory_count": len(local_memories),
        "open_commitments_count": len(open_commitments),
        "citations": hindsight_insights.get("based_on", []),
        "meeting_count": len(contact_meetings),
    }


# ---------------------------------------------------------------------------
# Step 6: Answer "What do you remember?" queries
# ---------------------------------------------------------------------------

def answer_memory_query(
    contact_name: str,
    query: str,
    db,
    hs_client,
) -> dict:
    """Answer a natural-language memory query about a contact."""
    contact = contacts_db.get_contact_by_name(db, contact_name)
    contact_id = contact["id"] if contact else None

    local_memories = contacts_db.get_relationship_memories(db, contact_id) if contact_id else []
    commitments = contacts_db.get_commitments(db, contact_id=contact_id) if contact_id else []
    meeting_history = contacts_db.get_contact_meetings(db, contact_id) if contact_id else []

    hindsight_facts = []
    hindsight_insights = {"text": "", "based_on": []}

    if hs_client and contact_id:
        hindsight_facts = recall_contact_memories(hs_client, contact_name, query)
        hindsight_insights = reflect_contact_insights(hs_client, contact_name, query)

    def _fmt_memories(mems):
        if not mems:
            return "None recorded."
        mems = mems[-25:] if len(mems) > 25 else mems
        return "\n".join(
            f"  [{m['memory_type']}] {m['content']} ({m.get('context', '')})"
            for m in mems
        )

    def _fmt_commitments(comms):
        if not comms:
            return "None recorded."
        return "\n".join(
            f"  [{c['status']}] {c['description']} (owner: {c.get('owner', '?')})"
            for c in comms
        )

    def _fmt_meetings(meetings):
        if not meetings:
            return "No meetings recorded."
        return "\n".join(f"  - {m['title']} ({m['date']})" for m in meetings)

    prompt = relationship_prompts.MEMORY_QUERY_PROMPT.format(
        contact_name=contact_name,
        query=query,
        hindsight_memories="\n".join(f"- {f}" for f in hindsight_facts[:10]) if hindsight_facts else "No Hindsight memories retrieved.",
        hindsight_insights=hindsight_insights.get("text") or "No insights available.",
        local_memories=_fmt_memories(local_memories),
        commitments=_fmt_commitments(commitments),
        meeting_history=_fmt_meetings(meeting_history),
    )

    try:
        answer = _llm_call(
            messages=[{"role": "user", "content": prompt}],
            model_env="MODEL_BRIEF",
            max_tokens=2000,
        )
    except Exception as e:
        log.error("Memory query failed: %s", e)
        answer = f"Query failed: {e}"

    return {
        "contact_name": contact_name,
        "query": query,
        "answer": answer,
        "memory_count": len(hindsight_facts),
        "local_memory_count": len(local_memories),
        "citations": hindsight_insights.get("based_on", []),
    }


# ---------------------------------------------------------------------------
# Step 7: Relationship evolution summary
# ---------------------------------------------------------------------------

def generate_relationship_evolution(
    contact_name: str,
    db,
    hs_client,
) -> dict:
    """Generate a relationship evolution summary showing how understanding has grown."""
    contact = contacts_db.get_contact_by_name(db, contact_name)
    contact_id = contact["id"] if contact else None

    all_memories = contacts_db.get_all_memories_for_contact(db, contact_id) if contact_id else []

    insights_query = (
        f"How has {contact_name}'s relationship evolved over time? "
        f"What were their early concerns vs current concerns? "
        f"How have their priorities changed? "
        f"What patterns in their behavior have become clear?"
    )

    hindsight_insights = {"text": "", "based_on": []}
    if hs_client and contact_id:
        hindsight_insights = reflect_contact_insights(hs_client, contact_name, insights_query)

    def _fmt_all_memories(mems):
        if not mems:
            return "No memories recorded yet."
        mems = mems[-35:] if len(mems) > 35 else mems
        return "\n".join(
            f"[{m['created_at'][:10]}] [{m['memory_type']}] {m['content']}"
            for m in mems
        )

    prompt = relationship_prompts.EVOLUTION_PROMPT.format(
        contact_name=contact_name,
        all_memories=_fmt_all_memories(all_memories),
        hindsight_insights=hindsight_insights.get("text") or "Not available yet.",
    )

    try:
        evolution_text = _llm_call(
            messages=[{"role": "user", "content": prompt}],
            model_env="MODEL_BRIEF",
            max_tokens=2000,
        )
    except Exception as e:
        log.error("Evolution generation failed: %s", e)
        evolution_text = f"Evolution summary failed: {e}"

    return {
        "contact_name": contact_name,
        "evolution": evolution_text,
        "total_memories": len(all_memories),
        "citations": hindsight_insights.get("based_on", []),
    }


# ---------------------------------------------------------------------------
# Main pipeline: Process a meeting with a contact
# ---------------------------------------------------------------------------

def process_meeting_for_contact(
    meeting_id: int,
    contact_name: str,
    transcript: str,
    meeting_title: str,
    meeting_date: str,
    db,
    hs_client,
    contact_id: int = None,
) -> dict:
    """
    Full relationship intelligence pipeline for a meeting with a specific contact.

    Steps:
    1. Get/create contact
    2. Extract relationship intelligence via LLM
    3. Store memories locally (SQLite)
    4. Store discrete memory units in Hindsight
    5. Return result summary
    """
    # Step 1: Get or create contact
    if not contact_id:
        contact_id = contacts_db.create_contact(db, name=contact_name)
    if not contact_id:
        return {"error": f"Could not create contact: {contact_name}"}

    # Step 2: Extract relationship intelligence
    extracted = extract_relationship_intelligence(transcript, contact_name)

    # Update contact if new company/role found
    updates = extracted.get("contact_updates", {})
    if updates.get("company") or updates.get("role"):
        contacts_db.update_contact(
            db, contact_id,
            company=updates.get("company"),
            role=updates.get("role"),
        )

    # Step 3: Store locally
    local_count = store_relationship_memories_locally(
        db, contact_id, meeting_id, meeting_title, meeting_date, extracted
    )

    # Step 4: Store in Hindsight
    hindsight_count = 0
    if hs_client:
        hindsight_count = store_relationship_memories_in_hindsight(
            hs_client, contact_name, meeting_id, meeting_date, meeting_title, extracted
        )

    # Count extracted items
    total_items = sum(
        len(extracted.get(k, []))
        for k in ["interests", "preferences", "concerns", "objections", "goals",
                  "decisions", "requirements", "facts", "changes", "commitments", "open_issues"]
    )

    return {
        "contact_name": contact_name,
        "contact_id": contact_id,
        "local_memories_stored": local_count,
        "hindsight_memories_stored": hindsight_count,
        "total_extracted_items": total_items,
        "extracted": extracted,
    }
