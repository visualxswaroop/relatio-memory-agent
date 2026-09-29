"""
Relationship intelligence prompts for extracting, retrieving, and reasoning
about per-contact relationship memories.
"""

# ---------------------------------------------------------------------------
# Relationship extraction from a meeting transcript
# ---------------------------------------------------------------------------

RELATIONSHIP_EXTRACTION_PROMPT = """You are a relationship intelligence agent. 
Analyze this meeting transcript/notes between the user and their contact "{contact_name}".

Extract meaningful relationship intelligence as a structured JSON object.

Return ONLY valid JSON with this schema:
{{
  "contact_updates": {{
    "company": "company name if mentioned or null",
    "role": "their job title/role if mentioned or null"
  }},
  "interests": [
    {{"content": "What they expressed interest in", "quote": "exact quote or null"}}
  ],
  "preferences": [
    {{"content": "How they prefer to work/communicate/buy", "quote": "exact quote or null"}}
  ],
  "concerns": [
    {{"content": "Pain point, worry, or concern expressed", "quote": "exact quote or null"}}
  ],
  "objections": [
    {{"content": "Specific objection raised", "quote": "exact quote or null"}}
  ],
  "goals": [
    {{"content": "What they are trying to achieve", "quote": "exact quote or null"}}
  ],
  "decisions": [
    {{"content": "A decision made or agreed upon", "quote": "exact quote or null"}}
  ],
  "requirements": [
    {{"content": "A requirement or non-negotiable they stated", "quote": "exact quote or null"}}
  ],
  "facts": [
    {{"content": "An important fact about this person or their situation", "quote": "exact quote or null"}}
  ],
  "changes": [
    {{"content": "Something that changed since previous discussions (priorities, stance, concern)", "quote": "exact quote or null"}}
  ],
  "commitments": [
    {{
      "description": "What was promised or committed to",
      "owner": "me or {contact_name} or both",
      "deadline_text": "as spoken or null"
    }}
  ],
  "open_issues": [
    {{"content": "Something unresolved that needs follow-up", "quote": "exact quote or null"}}
  ]
}}

Rules:
- Only extract facts that are EXPLICITLY in the transcript. Do NOT invent or hallucinate.
- For each item, include a short quote from the transcript if possible.
- "changes" should only be used when there is clear contrast with something previous (e.g., "before they were worried about X, now it's Y").
- Be specific and concrete, not generic.
- If a field has no items, use an empty list [].
- "owner" in commitments: use "me" for user's own promises, "{contact_name}" for their promises.

Contact name: {contact_name}

Meeting transcript/notes:
{transcript}
"""


# ---------------------------------------------------------------------------
# Personalized meeting brief
# ---------------------------------------------------------------------------

CONTACT_BRIEF_PROMPT = """You are a relationship intelligence agent preparing the user for a meeting with {contact_name}.

Generate a comprehensive, actionable pre-meeting brief using ONLY the retrieved memories and database data provided below.

Structure your response with these exact sections:

## 👤 Contact Context
Who {contact_name} is and relevant background.

## 💬 Previous Discussions
Key topics from previous interactions (cite which meeting if known).

## 🎯 Current Priorities
What {contact_name} currently appears to care most about based on their history.

## ⚠️ Concerns & Objections
Issues {contact_name} has raised. Flag recurring ones clearly.

## 📋 Open Items
Unresolved issues that should be addressed.

## 🤝 Previous Commitments
Promises or follow-ups (both yours and theirs). Flag anything still PENDING.

## 📣 Suggested Agenda
3-5 topics worth discussing in this meeting, based on history.

## 💡 Recommended Talking Points
Specific personalized points based on what you know about {contact_name}.

## 🔁 Things To Follow Up On
Specific pending items that need resolution.

Rules:
- Cite the meeting/source when you reference historical facts (e.g., "In the Sept 18 meeting...")
- Flag anything that is "recurring" or has appeared multiple times
- Say "not recorded" if information is not available
- Be concise and actionable — this is a brief, not an essay
- If there are no memories yet, say so clearly

{objective_section}

--- HINDSIGHT MEMORIES (retrieved from memory bank) ---
{hindsight_memories}

--- HINDSIGHT INSIGHTS (pattern analysis) ---
{hindsight_insights}

--- LOCAL DATABASE: Relationship Memories ---
{local_memories}

--- LOCAL DATABASE: Open Commitments ---
{open_commitments}

--- LOCAL DATABASE: Contact Background ---
{contact_info}
"""

OBJECTIVE_SECTION = """--- MEETING OBJECTIVE ---
The user wants to focus on: {objective}
"""

# ---------------------------------------------------------------------------
# "What do you remember?" query agent
# ---------------------------------------------------------------------------

MEMORY_QUERY_PROMPT = """You are a relationship intelligence agent answering a memory query about {contact_name}.

The user asked: "{query}"

Answer using ONLY the retrieved memories and data below. Structure your response clearly.

If the query is about:
- General knowledge → summarize key facts, preferences, concerns, goals
- Changes/evolution → show the progression across meetings, highlight shifts
- Commitments/promises → list all commitments with status
- Concerns/objections → group and rank by recurrence
- Relationship status → assess the overall relationship trajectory

Rules:
- Be specific and cite sources (e.g., "In the Oct 5 meeting...")
- Show how understanding has evolved when relevant (Earlier: X → Later: Y)
- Highlight patterns and recurring themes
- Say "not recorded" for things not in the data
- Do NOT make up information

--- HINDSIGHT MEMORIES ---
{hindsight_memories}

--- HINDSIGHT INSIGHTS ---
{hindsight_insights}

--- LOCAL RELATIONSHIP MEMORIES ---
{local_memories}

--- COMMITMENTS ---
{commitments}

--- MEETING HISTORY ---
{meeting_history}
"""


# ---------------------------------------------------------------------------
# Relationship evolution summary
# ---------------------------------------------------------------------------

EVOLUTION_PROMPT = """Analyze the evolution of the relationship with {contact_name} across all recorded meetings.

Show:
1. How their priorities/concerns have changed over time
2. Key turning points in the relationship
3. What you've learned about them that wasn't obvious at first
4. Patterns in their behavior or decision-making
5. Current state of the relationship

Be specific. Reference actual meetings and actual changes.

--- ALL RELATIONSHIP MEMORIES (chronological) ---
{all_memories}

--- HINDSIGHT PATTERN INSIGHTS ---
{hindsight_insights}
"""
