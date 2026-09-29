"""ICS calendar file generator for proposed meeting events."""
import uuid
from datetime import datetime, timedelta


def generate_ics(title: str, date_str: str, description: str = "", duration_hours: int = 1) -> str:
    """Generate an ICS file content string for a single event.
    
    Args:
        title: Event title
        date_str: Date in YYYY-MM-DD format
        description: Event description
        duration_hours: Duration in hours (default 1)
    
    Returns:
        ICS file content as string
    """
    try:
        dt = datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        # Try other common formats
        for fmt in ['%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S']:
            try:
                dt = datetime.strptime(date_str, fmt)
                break
            except ValueError:
                continue
        else:
            # Default to today if unparseable
            dt = datetime.now()
    
    dt_start = dt.replace(hour=10, minute=0)  # Default 10 AM
    dt_end = dt_start + timedelta(hours=duration_hours)
    uid = str(uuid.uuid4())
    
    # Escape special characters in ICS
    desc_escaped = description.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')
    title_escaped = title.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
    
    ics = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//MeetingCommitmentAgent//EN
CALSCALE:GREGORIAN
METHOD:PUBLISH
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}
DTSTART:{dt_start.strftime('%Y%m%dT%H%M%S')}
DTEND:{dt_end.strftime('%Y%m%dT%H%M%S')}
SUMMARY:{title_escaped}
DESCRIPTION:{desc_escaped}
STATUS:TENTATIVE
END:VEVENT
END:VCALENDAR"""
    return ics


def generate_multi_ics(events: list[dict]) -> str:
    """Generate an ICS file with multiple events.
    
    Args:
        events: List of dicts with keys: title, date, description (optional)
    
    Returns:
        ICS file content as string
    """
    lines = [
        'BEGIN:VCALENDAR',
        'VERSION:2.0',
        'PRODID:-//MeetingCommitmentAgent//EN',
        'CALSCALE:GREGORIAN',
        'METHOD:PUBLISH',
    ]
    
    for event in events:
        title = event.get('title', 'Untitled Event')
        date_str = event.get('date', '')
        description = event.get('description', '')
        
        if not date_str:
            continue
            
        try:
            dt = datetime.strptime(date_str, '%Y-%m-%d')
        except ValueError:
            continue
        
        dt_start = dt.replace(hour=10, minute=0)
        dt_end = dt_start + timedelta(hours=1)
        uid = str(uuid.uuid4())
        
        desc_escaped = description.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')
        title_escaped = title.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,')
        
        lines.extend([
            'BEGIN:VEVENT',
            f'UID:{uid}',
            f'DTSTAMP:{datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")}',
            f'DTSTART:{dt_start.strftime("%Y%m%dT%H%M%S")}',
            f'DTEND:{dt_end.strftime("%Y%m%dT%H%M%S")}',
            f'SUMMARY:{title_escaped}',
            f'DESCRIPTION:{desc_escaped}',
            'STATUS:TENTATIVE',
            'END:VEVENT',
        ])
    
    lines.append('END:VCALENDAR')
    return '\r\n'.join(lines)
