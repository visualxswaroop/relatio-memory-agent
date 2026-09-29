import os
import logging
from datetime import datetime
from dotenv import load_dotenv
import asyncio
import hindsight_client.hindsight_client as _hc
from hindsight_client import Hindsight

logger = logging.getLogger(__name__)

# Python 3.12 compatibility fix: asyncio.timeout requires an active Task
_orig_run_async = getattr(_hc, "_run_async", None)
if _orig_run_async:
    def _py312_run_async(coro):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        task = loop.create_task(coro)
        return loop.run_until_complete(task)
    _hc._run_async = _py312_run_async

load_dotenv()

def init_hindsight():
    """Initializes Hindsight client and creates the bank."""
    url = os.getenv("HINDSIGHT_URL", "https://api.hindsight.vectorize.io")
    api_key = os.getenv("HINDSIGHT_API_KEY")
    bank_id = os.getenv("BANK_ID")
    
    if not api_key:
        logger.error("HINDSIGHT_API_KEY is not set.")
        return None
    if not bank_id:
        logger.error("BANK_ID is not set.")
        return None
        
    try:
        client = Hindsight(base_url=url, api_key=api_key, timeout=300.0)
        mission = 'Track commitments, owners, deadlines and decisions across business meetings; prefer literal, evidence-backed facts'
        
        try:
            client.create_bank(
                bank_id=bank_id,
                name="Meeting Memory Bank",
                retain_mission=mission,
                reflect_mission=mission,
                retain_extraction_mode='verbose',
                enable_observations=True,
                enable_temporal_retrieval=True
            )
        except Exception as bank_err:
            logger.info(f"Bank '{bank_id}' already exists or create_bank returned: {bank_err}")

        return client
    except Exception as e:
        logger.error(f"Failed to initialize Hindsight: {e}")
        return None

def retain_transcript(client, meeting_id: str, transcript: str, title: str, date: str, participants: list[str], team: str = 'default'):
    """Retains a meeting transcript."""
    if not client:
        return False
        
    bank_id = os.getenv("BANK_ID")
    doc_id = f"meeting-{meeting_id}"
    
    try:
        timestamp = datetime.fromisoformat(date.replace('Z', '+00:00')) if date else None
    except ValueError:
        logger.warning(f"Failed to parse date: {date}")
        timestamp = None

    tags = [f"team:{team}"] + [f"participant:{p}" for p in participants]
    
    try:
        client.retain(
            bank_id=bank_id,
            content=transcript,
            timestamp=timestamp,
            context=title,
            document_id=doc_id,
            tags=tags,
            update_mode='replace'
        )
        return True
    except Exception as e:
        logger.error(f"Failed to retain transcript for meeting {meeting_id}: {e}")
        return False

def recall_facts(client, query: str, tags: list[str] | None = None) -> list[str]:
    """Recalls facts from Hindsight."""
    if not client:
        return []
        
    bank_id = os.getenv("BANK_ID")
    
    try:
        response = client.recall(
            bank_id=bank_id,
            query=query,
            types=['world', 'experience', 'observation'],
            max_tokens=8192,
            budget='mid',
            tags=tags,
            tags_match='any',
            include_entities=True
        )
        if hasattr(response, 'results'):
            return [result.text for result in response.results]
        return []
    except Exception as e:
        logger.error(f"Failed to recall facts for query '{query}': {e}")
        return []

def reflect_insights(client, query: str, tags: list[str] | None = None) -> dict:
    """Reflects insights from Hindsight."""
    if not client:
        return {"text": "", "based_on": []}
        
    bank_id = os.getenv("BANK_ID")
    
    try:
        response = client.reflect(
            bank_id=bank_id,
            query=query,
            budget='mid',
            tags=tags,
            include_facts=True
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
            "based_on": based_on
        }
    except Exception as e:
        logger.error(f"Failed to reflect insights for query '{query}': {e}")
        return {"text": "", "based_on": []}

def setup_mental_models(client):
    """Sets up default mental models in Hindsight."""
    if not client:
        return
        
    bank_id = os.getenv("BANK_ID")
    
    models = [
        {
            "id": "task-slip-patterns",
            "name": "Task Slip Patterns",
            "source_query": "Which owners tasks tend to slip or get postponed across meetings? What patterns exist in deadline changes?",
            "trigger": {"refresh_after_consolidation": True}
        },
        {
            "id": "decision-reversal-tracker",
            "name": "Decision Reversal Tracker",
            "source_query": "Which decisions were made and later reversed or contradicted in subsequent meetings?",
            "trigger": {"refresh_after_consolidation": True}
        }
    ]
    
    for m in models:
        try:
            client.create_mental_model(
                bank_id=bank_id,
                name=m["name"],
                source_query=m["source_query"],
                trigger=m["trigger"],
                id=m["id"]
            )
        except Exception as e:
            # Catch "already exists" errors silently or general creation errors
            logger.debug(f"Mental model {m['id']} might already exist or failed to create: {e}")

def get_mental_model_content(client, model_id: str) -> str | None:
    """Gets the content of a mental model."""
    if not client:
        return None
        
    bank_id = os.getenv("BANK_ID")
    
    try:
        response = client.get_mental_model(
            bank_id=bank_id,
            mental_model_id=model_id,
            detail='content'
        )
        if hasattr(response, 'content'):
            return response.content
        elif hasattr(response, 'text'):
             return response.text
        return str(response)
    except Exception as e:
        logger.error(f"Failed to get mental model content for '{model_id}': {e}")
        return None
