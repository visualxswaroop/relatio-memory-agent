# I Built a Meeting Agent That Remembers What Changed

A meeting assistant can produce a spotless transcript, list action items with clean punctuation, and still be useless three weeks later if it treats the next conversation like day one.

Professional relationships are not isolated chat sessions. When you work with a client, partner, or executive over several months, their priorities shift. In meeting one, a stakeholder might push back hard against your pricing model. By meeting two, budget approval has landed, but now they are worried about implementation timelines and cloud vendor lock-in. Meanwhile, their underlying working habits remain steady: they prefer concise updates over Slack and want technical questions answered before commercial terms.

The valuable signal in a relationship is almost never what was said in isolation during the latest call. The valuable signal is **what changed across calls**, what remained consistent, and what promises are still waiting on follow-through.

I built **Relatio** to solve that continuity problem. It is a meeting intelligence agent designed around an architectural thesis: every conversation should make the system better prepared for the next one.

<!-- SCREENSHOT: Relatio main dashboard showing key contacts, active commitments, and memory synchronization status -->

---

## What I Built: Relatio

Relatio is an agentic relationship assistant built with Python (Flask), SQLite, Groq for high-speed inference, and [Hindsight](https://github.com/vectorize-io/hindsight) as the dedicated agent memory engine. 

Instead of treating meeting transcripts as static text archives or dumping vector embeddings into an unmanaged index, Relatio executes an explicit pipeline:

1. **Ingestion**: Accepts meeting transcripts or recorded audio files (transcribed using Whisper via Groq).
2. **Extraction**: Breaks down conversation dynamics into typed relationship intelligence units (preferences, concerns, objections, goals, decisions, facts, and commitments).
3. **Dual Storage**: Stores deterministic operational state (contacts, meeting metadata, commitment statuses) in SQLite, while persisting longitudinal relationship memories into Hindsight.
4. **Memory Recall & Reflection**: Leverages Hindsight's temporal and associative search to reconstruct contact context and synthesize behavioral patterns over time.
5. **Contextual Preparation**: Generates personalized pre-meeting briefs that highlight active priorities, unresolved objections, and explicit talking points.

<!-- SCREENSHOT: Meeting transcript intake and extraction interface showing structured intelligence categories -->

---

## The Architecture: Dual-Layer Persistence

When designing memory for an agent, a common pitfall is trying to force one tool to do everything. Either engineers treat a relational database like a memory bank—stuffing fuzzy conversational context into rigid tables—or they treat an embedding index like an operational database, struggling to update task statuses or maintain relational integrity.

In Relatio, I split application state and relationship memory into two distinct layers:

```text
Meeting Notes / Transcript
           ↓
Groq (LLaMA-3.3 / Qwen-27B)
           ↓
Relationship Intelligence Extraction
     ┌─────┴────────────────────────┐
     ↓                              ↓
SQLite (Operational State)     Hindsight (Long-Term Memory)
- Contacts & metadata          - Evolving preferences & concerns
- Mutual commitments & status  - Objections & goals
- Meeting timestamps & audit   - Strategic decisions & shifts
     └─────┬────────────────────────┘
           ↓
Recall & Reflection Engine
           ↓
Personalized Briefs & Semantic Memory Q&A
```

**SQLite stores what happened; Hindsight remembers what it means.**

If someone says, *"I will send the security compliance checklist by next Tuesday,"* that is a commitment with an owner, a target date, and a binary lifecycle (pending, done, or cancelled). That belongs in SQLite with strict primary keys and foreign constraints. 

However, when that same person mentions that their infrastructure team has grown skeptical of AWS pricing models, that is not a static task row. It is an evolving perspective that needs to inform how future technical discussions are framed. That belongs in [Vectorize agent memory](https://vectorize.io/what-is-agent-memory).

---

## Deciding What Becomes Memory: Discrete Intelligence Units

Simply storing entire 45-minute transcripts as monolithic blobs in a vector database creates noisy retrieval. When an agent queries a large context window for *"What are Rahul's current technical reservations?"*, monolithic chunks force the LLM to filter through greetings, calendar logistics, and tangential banter.

To build meaningful memory, the extraction layer must extract discrete units of relationship intelligence. In `backend/relationship_agent.py`, the system prompts the extraction LLM to parse conversation transcripts into ten structured categories:

```python
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
```

Each extracted unit is paired with the verbatim quote that evidenced it. This provides verifiable provenance: the agent never asserts that a stakeholder cares about something without retaining the source quote.

For instance, consider two meetings spaced two weeks apart:

* **Meeting 1**: Rahul notes that our enterprise tier feels too steep for their current budget. He mentions that his team operates strictly asynchronously on Slack.
* **Meeting 2**: Rahul shares that the enterprise budget was approved by leadership. However, he is now anxious about migration downtime and wants to avoid single-cloud dependency on AWS.

Because these data points are extracted into discrete units, the system does not simply hold two unstructured transcripts. It identifies:
* **Previous Concern**: Pricing (marked as resolved/obsolete).
* **New Concerns**: Deployment downtime and AWS vendor lock-in.
* **Stable Preference**: Asynchronous communication via Slack.

This distinction is what separates simple conversation logging from genuine relationship intelligence.

---

## Using Hindsight for Long-Term Context

To handle long-term memory persistence and temporal reasoning, Relatio integrates [Hindsight](https://hindsight.vectorize.io/). The memory bank is initialized during backend startup:

```python
# backend/relationship_agent.py
def _init_relationship_bank(hs_client):
    if not hs_client:
        return False
    bank_id = _relationship_bank_id()  # defaults to "meeting-intelligence"
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
        return True
```

When meeting notes are ingested, each discrete unit is retained with contact-specific tags and document IDs:

```python
# backend/relationship_agent.py
hs_client.retain(
    bank_id=bank_id,
    content=doc_text,
    timestamp=meeting_dt,
    context=f"{contact_name} - {label} - {meeting_title}",
    document_id=doc_id,
    tags=[contact_tag, f"type:{mem_type}", f"meeting:{meeting_id}"],
    update_mode="replace",
)
```

By tagging memories with `contact:<name>` and `type:<category>`, the system can scope queries precisely, preventing cross-stakeholder memory contamination. If the remote Hindsight service is unavailable, Relatio falls back to its local SQLite memory table, ensuring zero disruption to basic note processing.

<!-- SCREENSHOT: Contact profile showing retained memory units categorized by concerns, interests, and preferences -->

---

## Recall vs. Reflection: Two Ways to Query the Past

A core reason I chose Hindsight rather than a basic vector store is the conceptual difference between **Recall** and **Reflection**.

### 1. Recall
Recall retrieves direct historical facts matching a targeted query. When preparing a brief, Relatio executes:

```python
# backend/relationship_agent.py
response = hs_client.recall(
    bank_id=bank_id,
    query=f"What are {contact_name}'s interests, concerns, objections, goals, and commitments?",
    types=["world", "experience", "observation"],
    max_tokens=1500,
    budget="mid",
    tags=[contact_tag],
    tags_match="all",
    include_entities=True,
)
```
This returns the grounded, discrete evidence: *"Prefers Slack updates," "Concerned about AWS lock-in," "Daughter applying to Stanford."*

### 2. Reflection
Reflection operates at a higher level of abstraction. Rather than simply fetching facts, it prompts the memory engine to synthesize trends, patterns, and contradictions across interactions:

```python
# backend/relationship_agent.py
response = hs_client.reflect(
    bank_id=bank_id,
    query=(
        f"What patterns exist in {contact_name}'s behavior? "
        f"How have their concerns and priorities evolved? "
        f"What recurring issues or themes appear across meetings?"
    ),
    budget="mid",
    tags=[contact_tag],
    include_facts=True,
)
```

Reflection identifies when a topic has been discussed across three consecutive meetings without resolution, or when a stakeholder's sentiment has shifted from skeptical to receptive.

<!-- SCREENSHOT: Relationship evolution view displaying longitudinal pattern analysis and trust trajectory -->

---

## Concrete Behavior: What Happens Across Two Meetings

To see how this works in practice, look at what Relatio produces when generating a pre-meeting brief for Rahul Sharma before Meeting 3:

```text
## Contact Context
Rahul Sharma is VP of Engineering at TechNova (11 meetings recorded).
Personal rapport: daughter is applying to Stanford; avid cricket follower.

## Current Priorities & Shifts
1. Hybrid Cloud Architecture: Top priority. Rahul has consistently favored 
   hybrid infrastructure to mitigate AWS lock-in.
2. Q3 Migration Timeline: Firm commitment to finalize rollout by end of Q3.
3. Pricing Concern Resolved: The initial objection regarding tier pricing 
   from Sept 14 was resolved following executive budget sign-off.

## Previous Commitments
- [PENDING] Deliver security compliance checklist (Owner: Me | Due: Tuesday)
- [PENDING] Send current infrastructure spec (Owner: Rahul | Due: Friday)

## Recommended Talking Points
- Lead with our hybrid cloud deployment topology to directly address his AWS concern.
- Keep status reporting asynchronous via Slack, matching his explicit communication preference.
- Follow up on the infrastructure specification due from his team.
```

Without persistent memory, an LLM generates generic advice: *"Be polite, ask what their goals are, take notes."* With longitudinal memory, the agent instructs you to address their exact architectural hesitation and respect their communication style.

---

## Why SQLite Still Matters: State vs. Memory

It is tempting in modern AI engineering to offload everything to an LLM or an embedding store. But building Relatio reinforced why relational databases remain essential in agent architecture.

Commitments require an explicit lifecycle:

```sql
CREATE TABLE IF NOT EXISTS commitments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER,
    meeting_id INTEGER,
    description TEXT NOT NULL,
    owner TEXT,
    deadline_text TEXT,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (contact_id) REFERENCES contacts(id)
);
```

When a user clicks "Mark Done" on a commitment in the UI, that should be a deterministic SQL `UPDATE commitments SET status = 'done' WHERE id = ?`. You should not ask an LLM to re-evaluate a prompt to guess whether a task is completed. Deterministic states belong in ACID-compliant tables; qualitative insights belong in associative memory.

<!-- SCREENSHOT: Commitments tracking dashboard with status transitions and accountability analytics -->

---

## Engineering Challenges: Token Budgets and Memory Granularity

The most challenging engineering tradeoff was managing token budgets against API constraints.

During early testing with Groq's on-demand models (`qwen/qwen3.8-27b`), repeated meetings with active contacts generated nearly 80 discrete memory units. When all 80 local memories, full Hindsight recall results, and past meeting summaries were packed into the pre-meeting brief prompt, input token volume breached on-demand rate limits (HTTP 413). Furthermore, high output token allocations (`max_tokens=3000`) caused Groq's output-tokens-per-minute throttle (HTTP 429) to trigger.

To fix this, I made two architectural adjustments:

1. **Recall Budget Constraints**: Sliced Hindsight's `recall` parameter to `max_tokens=1500` and capped injected local memories to the 25 most recent relevant units.
2. **Output Right-Sizing**: Constrained briefing and reflection prompts to `max_tokens=800` to guarantee throughput under production quotas.

This maintained response latency under two seconds without losing the critical historical context needed for the brief.

---

## Lessons Learned

1. **Memory is not transcript archival**: Storing full transcripts in vector indexes produces noisy context. High-signal agent memory requires parsing meetings into discrete, typed assertions.
2. **Relationships are longitudinal**: The core value proposition of an assistant is not summarizing what was just said; it is tracking how priorities and objections change across months.
3. **Keep state and memory separate**: Use your relational database for deterministic lifecycles (tasks, dates, contact metadata) and your memory engine for associative knowledge.
4. **Memory requires provenance**: If an agent tells you a client hates weekly meetings, it must be able to cite the exact quote and date that proved it.
5. **The ultimate test is the next interaction**: An agent's memory architecture should be evaluated on one metric: *did having that memory make the subsequent interaction significantly better?*

---

## Conclusion

Stateless AI assistants treat every conversation as an isolated event. By pairing a structured application database with [Hindsight](https://hindsight.vectorize.io/) as a dedicated relationship memory engine, Relatio tracks how professional relationships actually evolve. 

When your tools remember what was promised, what was resolved, and what someone actually cares about, you stop wasting the first fifteen minutes of every meeting catching up—and start every conversation prepared.
