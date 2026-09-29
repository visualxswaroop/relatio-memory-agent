"""
Pipeline: transcribe -> correct -> extract -> retain -> save.
Orchestrates all steps for processing a meeting.
"""

import io
import json
import logging
import math
import os
import re
import tempfile
import time
from datetime import datetime

from dotenv import load_dotenv
from groq import Groq, RateLimitError, APIError
from pydantic import BaseModel, Field, field_validator

from backend import db, memory, prompts

load_dotenv()
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models for validated extraction
# ---------------------------------------------------------------------------

class TaskItem(BaseModel):
    key: str
    description: str
    owner: str | None = None
    deadline_text: str | None = None
    status: str = "new"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    quote: str = ""

    @field_validator("status")
    @classmethod
    def valid_status(cls, v: str) -> str:
        allowed = {"new", "in_progress", "done", "blocked"}
        if v not in allowed:
            return "new"
        return v

    @field_validator("key")
    @classmethod
    def valid_key(cls, v: str) -> str:
        return re.sub(r"[^a-z0-9_]", "_", v.lower().strip())[:80]


class DecisionItem(BaseModel):
    text: str
    quote: str = ""


class IdeaItem(BaseModel):
    text: str


class OpenIssueItem(BaseModel):
    text: str
    quote: str = ""


class ImportantDateItem(BaseModel):
    title: str
    date_text: str
    date: str | None = None


class MeetingExtraction(BaseModel):
    participants: list[str] = []
    tasks: list[TaskItem] = []
    decisions: list[DecisionItem] = []
    ideas: list[IdeaItem] = []
    open_issues: list[OpenIssueItem] = []
    important_dates: list[ImportantDateItem] = []


# ---------------------------------------------------------------------------
# Groq client helpers
# ---------------------------------------------------------------------------

def _get_groq_client(key_env: str = "GROQ_API_KEY_MAIN") -> Groq:
    """Create a Groq client using the specified env var."""
    api_key = os.getenv(key_env)
    if not api_key:
        raise ValueError(f"Missing environment variable: {key_env}")
    return Groq(api_key=api_key)


def _clean_llm_output(text: str) -> str:
    """Strip <think> tags, code fences, and leading/trailing whitespace."""
    # Remove <think>...</think> blocks
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    # Remove code fences
    text = re.sub(r"^```(?:json)?\s*\n?", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n?```\s*$", "", text, flags=re.MULTILINE)
    return text.strip()


def _llm_call(
    messages: list[dict],
    model_env: str,
    key_env: str = "GROQ_API_KEY_MAIN",
    temperature: float = 0.2,
    max_tokens: int = 4096,
    json_mode: bool = False,
    retries: int = 3,
) -> str:
    """Make an LLM call with retry and backoff."""
    client = _get_groq_client(key_env)
    model = os.getenv(model_env)
    if not model:
        raise ValueError(f"Missing environment variable: {model_env}")

    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = client.chat.completions.create(**kwargs)
            raw = resp.choices[0].message.content or ""
            return _clean_llm_output(raw)
        except RateLimitError as e:
            last_err = e
            wait = min(2 ** attempt, 30)
            log.warning("Rate limited (attempt %d/%d), waiting %ds: %s", attempt, retries, wait, e)
            time.sleep(wait)
        except APIError as e:
            last_err = e
            if attempt < retries:
                wait = 2 ** attempt
                log.warning("API error (attempt %d/%d), waiting %ds: %s", attempt, retries, wait, e)
                time.sleep(wait)
            else:
                raise
    raise RuntimeError(f"LLM call failed after {retries} retries: {last_err}")


def _parse_json_with_retries(
    raw: str,
    model_class: type[BaseModel],
    messages: list[dict],
    model_env: str,
    key_env: str = "GROQ_API_KEY_MAIN",
    retries: int = 3,
) -> BaseModel:
    """Parse JSON from LLM output with pydantic validation and retries."""
    last_err = None
    for attempt in range(retries):
        try:
            cleaned = _clean_llm_output(raw)
            data = json.loads(cleaned)
            return model_class.model_validate(data)
        except (json.JSONDecodeError, Exception) as e:
            last_err = e
            log.warning("JSON parse/validation failed (attempt %d/%d): %s", attempt + 1, retries, e)
            if attempt < retries - 1:
                # Ask LLM to fix its output
                fix_msgs = messages + [
                    {"role": "assistant", "content": raw},
                    {"role": "user", "content": f"Your JSON output was invalid: {e}\nPlease output ONLY valid JSON matching the required schema. No explanation."},
                ]
                time.sleep(2 ** attempt)
                raw = _llm_call(fix_msgs, model_env, key_env, json_mode=True)
    raise RuntimeError(f"Failed to get valid JSON after {retries} attempts: {last_err}")


# ---------------------------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------------------------

def transcribe_audio(audio_path: str) -> str:
    """Transcribe audio using Groq Whisper. Splits large files if needed."""
    client = _get_groq_client("GROQ_API_KEY_MAIN")
    model = os.getenv("MODEL_TRANSCRIBE", "whisper-large-v3-turbo")
    max_size = 24 * 1024 * 1024  # 24 MB safety margin (Groq limit is 25MB free)

    file_size = os.path.getsize(audio_path)
    basename = os.path.basename(audio_path)

    if file_size <= max_size:
        with open(audio_path, "rb") as f:
            resp = client.audio.transcriptions.create(
                file=(basename, f.read()),
                model=model,
                response_format="text",
                temperature=0.0,
            )
        return resp if isinstance(resp, str) else resp.text

    # Split large files using pydub
    log.info("Audio file %s is %.1f MB, splitting into chunks", basename, file_size / 1e6)
    try:
        from pydub import AudioSegment
    except ImportError:
        raise RuntimeError(
            "Audio file exceeds 24 MB. Install pydub and ffmpeg to split: pip install pydub"
        )

    audio = AudioSegment.from_file(audio_path)
    chunk_duration_ms = 10 * 60 * 1000  # 10-minute chunks
    chunks = [audio[i:i + chunk_duration_ms] for i in range(0, len(audio), chunk_duration_ms)]

    transcripts = []
    for i, chunk in enumerate(chunks):
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as tmp:
            chunk.export(tmp.name, format="mp3")
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as f:
                resp = client.audio.transcriptions.create(
                    file=(f"chunk_{i}.mp3", f.read()),
                    model=model,
                    response_format="text",
                    temperature=0.0,
                )
            text = resp if isinstance(resp, str) else resp.text
            transcripts.append(text)
        finally:
            os.unlink(tmp_path)

    return "\n".join(transcripts)


def correct_transcript(transcript: str) -> str:
    """Clean up STT output: fix names, jargon, Hinglish errors."""
    prompt = prompts.CORRECTION_PROMPT.format(transcript=transcript)
    return _llm_call(
        messages=[{"role": "user", "content": prompt}],
        model_env="MODEL_CORRECT",
        temperature=0.1,
        max_tokens=8192,
    )


def extract_commitments(
    transcript: str,
    existing_tasks: list[dict] | None = None,
    corrections: list[dict] | None = None,
) -> MeetingExtraction:
    """Extract structured commitments from transcript."""
    # Build existing tasks instruction
    existing_instruction = ""
    if existing_tasks:
        tasks_json = json.dumps(
            [{"key": t["key"], "description": t["description"], "owner": t.get("owner"),
              "status": t.get("status"), "deadline_text": t.get("deadline_text")}
             for t in existing_tasks],
            indent=2,
        )
        existing_instruction = prompts.EXISTING_TASKS_INSTRUCTION.format(tasks_json=tasks_json)

    # Build correction examples
    correction_instruction = ""
    if corrections:
        corr_json = json.dumps(
            [{"field": c["field"], "original": c["original_value"], "corrected": c["corrected_value"]}
             for c in corrections],
            indent=2,
        )
        correction_instruction = prompts.CORRECTION_EXAMPLES_INSTRUCTION.format(corrections_json=corr_json)

    prompt = prompts.EXTRACTION_PROMPT.format(
        transcript=transcript,
        existing_tasks_instruction=existing_instruction,
        correction_examples=correction_instruction,
    )

    messages = [{"role": "user", "content": prompt}]
    raw = _llm_call(messages, "MODEL_EXTRACT", json_mode=True, max_tokens=8192)
    return _parse_json_with_retries(raw, MeetingExtraction, messages, "MODEL_EXTRACT")


def generate_summary(transcript: str, title: str, date: str) -> str:
    """Generate a max-120-word summary using the SECOND Groq key."""
    prompt = prompts.SUMMARY_PROMPT.format(transcript=transcript, title=title, date=date)
    return _llm_call(
        messages=[{"role": "user", "content": prompt}],
        model_env="MODEL_SUMMARY",
        key_env="GROQ_API_KEY_SUMMARY",
        temperature=0.2,
        max_tokens=512,
    )


def generate_brief(
    user_name: str,
    hs_client,
    database,
    use_memory: bool = True,
) -> dict:
    """Generate a pre-meeting brief for a user.

    Returns dict with 'brief' text and 'memory_used' bool.
    If use_memory=False, produces baseline brief (no Hindsight).
    """
    # Get database info
    open_tasks = db.get_open_tasks(database)
    silent_tasks = db.get_silent_tasks(database)
    promise_drift = db.get_promise_drift(database)
    stuck_topics = db.get_stuck_topics(database)
    user_tasks = db.get_tasks_for_person(database, user_name)
    meetings = db.get_all_meetings(database)

    if not use_memory or hs_client is None:
        # Baseline: only latest transcript
        latest = meetings[-1] if meetings else None
        transcript = latest["corrected_transcript"] or latest["transcript"] if latest else "No meetings recorded yet."
        prompt = prompts.BASELINE_BRIEF_PROMPT.format(
            user_name=user_name,
            transcript=transcript,
        )
        brief_text = _llm_call(
            messages=[{"role": "user", "content": prompt}],
            model_env="MODEL_BRIEF",
            max_tokens=2048,
        )
        return {"brief": brief_text, "memory_used": False}

    # Memory-enhanced brief
    recall_facts = []
    reflect_text = ""
    reflect_citations = []

    try:
        recall_facts = memory.recall_facts(
            hs_client,
            query=f"What are the open commitments, decisions, and pending tasks for {user_name}? What deadlines are coming up?",
        )
    except Exception as e:
        log.warning("Recall failed: %s", e)

    try:
        insights = memory.reflect_insights(
            hs_client,
            query=f"Summarize the meeting history: key decisions, recurring issues, tasks that keep getting postponed, and any patterns in {user_name}'s commitments.",
        )
        reflect_text = insights.get("text", "")
        reflect_citations = insights.get("based_on", [])
    except Exception as e:
        log.warning("Reflect failed: %s", e)

    # Format data for prompt
    def _fmt_tasks(tasks):
        if not tasks:
            return "None"
        lines = []
        for t in tasks:
            line = f"- [{t['status']}] {t['description']}"
            if t.get("owner"):
                line += f" (owner: {t['owner']})"
            if t.get("deadline_text"):
                line += f" (deadline: {t['deadline_text']})"
            lines.append(line)
        return "\n".join(lines)

    def _fmt_drift(drifts):
        if not drifts:
            return "None"
        lines = []
        for d in drifts:
            lines.append(f"- {d['description']} — deadline changed {d['change_count']} time(s)")
        return "\n".join(lines)

    def _fmt_stuck(topics):
        if not topics:
            return "None"
        return "\n".join(f"- {t['text']} (appeared in {t['count']} meetings)" for t in topics)

    prompt = prompts.BRIEF_PROMPT.format(
        user_name=user_name,
        recall_facts="\n".join(f"- {f}" for f in recall_facts) if recall_facts else "No facts recalled.",
        reflect_insights=reflect_text or "No insights available.",
        open_tasks=_fmt_tasks(open_tasks),
        silent_tasks=_fmt_tasks(silent_tasks),
        promise_drift=_fmt_drift(promise_drift),
        stuck_topics=_fmt_stuck(stuck_topics),
        user_tasks=_fmt_tasks(user_tasks),
    )

    brief_text = _llm_call(
        messages=[{"role": "user", "content": prompt}],
        model_env="MODEL_BRIEF",
        max_tokens=2048,
    )

    return {
        "brief": brief_text,
        "memory_used": True,
        "recall_count": len(recall_facts),
        "reflect_citations": reflect_citations,
    }


# ---------------------------------------------------------------------------
# Full pipeline
# ---------------------------------------------------------------------------

def process_meeting(
    title: str,
    date: str,
    team: str = "default",
    transcript_text: str | None = None,
    audio_path: str | None = None,
    confirmed_participants: list[str] | None = None,
    db_path: str = "data/meetings.db",
) -> dict:
    """
    Process a meeting through the full pipeline.

    Returns dict with meeting_id, extraction, summary, memory_synced, etc.
    """
    database = db.get_db(db_path)

    # Step 1: Get transcript
    if transcript_text:
        raw_transcript = transcript_text
    elif audio_path:
        try:
            raw_transcript = transcribe_audio(audio_path)
        except Exception as e:
            log.error("Transcription failed: %s", e)
            return {"error": f"Transcription failed: {e}. Please paste the transcript text instead."}
    else:
        return {"error": "No transcript text or audio file provided."}

    # Step 2: Correct transcript
    try:
        corrected = correct_transcript(raw_transcript)
    except Exception as e:
        log.warning("Correction failed, using raw transcript: %s", e)
        corrected = raw_transcript

    # Step 3: Extract commitments
    existing_tasks = db.get_open_tasks(database)
    recent_corrections = db.get_recent_corrections(database)

    try:
        extraction = extract_commitments(
            corrected,
            existing_tasks=existing_tasks,
            corrections=recent_corrections,
        )
    except Exception as e:
        log.error("Extraction failed: %s", e)
        return {"error": f"Extraction failed: {e}"}

    # Override participants if user confirmed them
    if confirmed_participants:
        extraction.participants = confirmed_participants

    # Step 4: Generate summary (second key)
    try:
        summary = generate_summary(corrected, title, date)
    except Exception as e:
        log.warning("Summary generation failed: %s", e)
        summary = "Summary generation failed."

    # Step 5: Save to database
    extraction_dict = extraction.model_dump()
    participants_json = json.dumps(extraction.participants)

    meeting_id = db.save_meeting(
        database,
        title=title,
        date=date,
        team=team,
        transcript=raw_transcript,
        corrected_transcript=corrected,
        summary=summary,
        participants_json=participants_json,
        extraction_json=json.dumps(extraction_dict),
        memory_synced=0,
    )

    # Step 6: Save tasks with history tracking
    db.save_tasks(database, meeting_id, [t.model_dump() for t in extraction.tasks])

    # Step 7: Retain in Hindsight
    memory_synced = False
    try:
        hs_client = memory.init_hindsight()
        if hs_client:
            memory_synced = memory.retain_transcript(
                hs_client,
                meeting_id=str(meeting_id),
                transcript=corrected,
                title=title,
                date=date,
                participants=extraction.participants,
                team=team,
            )
            if memory_synced:
                database.execute("UPDATE meetings SET memory_synced = 1 WHERE id = ?", (meeting_id,))
                database.commit()
    except Exception as e:
        log.warning("Hindsight retain failed (meeting saved locally): %s", e)

    return {
        "meeting_id": meeting_id,
        "title": title,
        "date": date,
        "participants": extraction.participants,
        "extraction": extraction_dict,
        "summary": summary,
        "memory_synced": memory_synced,
        "task_count": len(extraction.tasks),
        "silent_task_count": sum(1 for t in extraction.tasks if t.owner is None),
        "decision_count": len(extraction.decisions),
    }
