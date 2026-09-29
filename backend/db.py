import sqlite3
import json

SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    date TEXT NOT NULL,
    team TEXT DEFAULT 'default',
    transcript TEXT,
    corrected_transcript TEXT,
    summary TEXT,
    participants TEXT,  -- JSON array
    extraction_json TEXT,  -- full extraction result
    memory_synced INTEGER DEFAULT 0,  -- 1 if retained in Hindsight
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT NOT NULL UNIQUE,  -- snake_case slug e.g. 'update_dashboard'
    description TEXT NOT NULL,
    owner TEXT,  -- null means 'silent task'
    deadline_text TEXT,
    deadline_date TEXT,  -- ISO date if parseable
    status TEXT DEFAULT 'new' CHECK(status IN ('new','in_progress','done','blocked')),
    confidence REAL DEFAULT 1.0,
    quote TEXT,
    meeting_id INTEGER REFERENCES meetings(id),
    first_meeting_id INTEGER,  -- meeting where first seen
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS task_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_key TEXT NOT NULL,
    meeting_id INTEGER REFERENCES meetings(id),
    field_changed TEXT NOT NULL,  -- 'owner', 'status', 'deadline_text', 'deadline_date'
    old_value TEXT,
    new_value TEXT,
    changed_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS corrections (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id INTEGER REFERENCES meetings(id),
    task_key TEXT,
    field TEXT,
    original_value TEXT,
    corrected_value TEXT,
    correction_type TEXT DEFAULT 'task',  -- 'task', 'decision', 'participant'
    created_at TEXT DEFAULT (datetime('now'))
);
"""

def init_db(db_path='data/meetings.db'):
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.executescript(SCHEMA)
    conn.commit()
    conn.close()

def get_db(db_path='data/meetings.db') -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.isolation_level = None
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL;')
    return conn

def save_meeting(db, title, date, team, transcript, corrected_transcript, summary, participants_json, extraction_json, memory_synced) -> int:
    cursor = db.execute('''
        INSERT INTO meetings (title, date, team, transcript, corrected_transcript, summary, participants, extraction_json, memory_synced)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (title, date, team, transcript, corrected_transcript, summary, participants_json, extraction_json, memory_synced))
    db.commit()
    return cursor.lastrowid

def save_tasks(db, meeting_id, tasks_list):
    for task in tasks_list:
        key = task.get('key')
        if not key:
            continue
            
        cursor = db.execute('SELECT * FROM tasks WHERE key = ?', (key,))
        existing_task = cursor.fetchone()
        
        if existing_task:
            fields_to_check = ['owner', 'status', 'deadline_text', 'deadline_date', 'description', 'quote']
            for field in fields_to_check:
                new_val = str(task.get(field)) if task.get(field) is not None else None
                old_val = str(existing_task[field]) if existing_task[field] is not None else None
                
                if task.get(field) is not None and new_val != old_val:
                    db.execute('''
                        INSERT INTO task_history (task_key, meeting_id, field_changed, old_value, new_value)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (key, meeting_id, field, old_val, new_val))
                    
                    db.execute(f'''
                        UPDATE tasks SET {field} = ?, updated_at = datetime('now')
                        WHERE key = ?
                    ''', (task.get(field), key))
            
            db.execute('''
                UPDATE tasks SET meeting_id = ?, updated_at = datetime('now')
                WHERE key = ?
            ''', (meeting_id, key))
            
        else:
            db.execute('''
                INSERT INTO tasks (key, description, owner, deadline_text, deadline_date, status, confidence, quote, meeting_id, first_meeting_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                key,
                task.get('description', ''),
                task.get('owner'),
                task.get('deadline_text'),
                task.get('deadline_date'),
                task.get('status', 'new'),
                task.get('confidence', 1.0),
                task.get('quote'),
                meeting_id,
                meeting_id
            ))
    db.commit()

def get_meeting(db, meeting_id) -> dict:
    cursor = db.execute('SELECT * FROM meetings WHERE id = ?', (meeting_id,))
    row = cursor.fetchone()
    return dict(row) if row else None

def get_all_meetings(db) -> list[dict]:
    cursor = db.execute('SELECT * FROM meetings ORDER BY date DESC')
    return [dict(row) for row in cursor.fetchall()]

def get_tasks(db, status=None, owner=None) -> list[dict]:
    query = 'SELECT * FROM tasks WHERE 1=1'
    params = []
    if status:
        query += ' AND status = ?'
        params.append(status)
    if owner:
        query += ' AND owner = ?'
        params.append(owner)
        
    cursor = db.execute(query, params)
    return [dict(row) for row in cursor.fetchall()]

def get_silent_tasks(db) -> list[dict]:
    cursor = db.execute('SELECT * FROM tasks WHERE owner IS NULL')
    return [dict(row) for row in cursor.fetchall()]

def get_task_history(db, task_key) -> list[dict]:
    cursor = db.execute('SELECT * FROM task_history WHERE task_key = ? ORDER BY changed_at DESC', (task_key,))
    return [dict(row) for row in cursor.fetchall()]

def get_follow_through(db) -> list[dict]:
    cursor = db.execute('SELECT * FROM tasks WHERE owner IS NOT NULL')
    tasks = cursor.fetchall()
    
    cursor = db.execute("SELECT * FROM task_history WHERE field_changed IN ('deadline_text', 'deadline_date')")
    history = cursor.fetchall()
    
    stats = {}
    
    for task in tasks:
        owner = task['owner']
        if owner not in stats:
            stats[owner] = {
                'total_tasks': 0,
                'done_tasks': 0,
                'tasks_with_deadlines': 0,
                'tasks_done_on_time': 0,
                'deadline_postponements': 0
            }
            
        stats[owner]['total_tasks'] += 1
        is_done = task['status'] == 'done'
        if is_done:
            stats[owner]['done_tasks'] += 1
            
        if task['deadline_date']:
            stats[owner]['tasks_with_deadlines'] += 1
            if is_done:
                stats[owner]['tasks_done_on_time'] += 1
                
    for h in history:
        cursor = db.execute('SELECT owner FROM tasks WHERE key = ?', (h['task_key'],))
        row = cursor.fetchone()
        if row and row['owner']:
            owner = row['owner']
            if owner in stats:
                stats[owner]['deadline_postponements'] += 1

    result = []
    for owner, data in stats.items():
        total = data['total_tasks']
        done = data['done_tasks']
        with_deadline = data['tasks_with_deadlines']
        done_on_time = data['tasks_done_on_time']
        
        comp_pct = (done / total) * 100 if total > 0 else 0.0
        on_time_pct = (done_on_time / with_deadline) * 100 if with_deadline > 0 else 0.0
        
        result.append({
            'owner': owner,
            'completion_pct': comp_pct,
            'on_time_pct': on_time_pct,
            'deadline_postponements': data['deadline_postponements'],
            'total_tasks': total,
            'done_tasks': done,
            'tasks_with_deadlines': with_deadline
        })
        
    return result

def get_stuck_topics(db) -> list[dict]:
    cursor = db.execute('SELECT extraction_json FROM meetings WHERE extraction_json IS NOT NULL')
    rows = cursor.fetchall()
    
    topic_counts = {}
    for row in rows:
        try:
            ext = json.loads(row['extraction_json'])
            issues = ext.get('open_issues', [])
            for issue in issues:
                issue_text = issue if isinstance(issue, str) else issue.get('text', str(issue))
                topic_counts[issue_text] = topic_counts.get(issue_text, 0) + 1
        except Exception:
            continue
            
    stuck = [{'text': k, 'count': v} for k, v in topic_counts.items() if v >= 3]
    return sorted(stuck, key=lambda x: x['count'], reverse=True)

def get_promise_drift(db) -> list[dict]:
    cursor = db.execute('''
        SELECT task_key, COUNT(*) as change_count 
        FROM task_history 
        WHERE field_changed LIKE 'deadline%' 
        GROUP BY task_key 
        HAVING change_count > 0
    ''')
    drifts = cursor.fetchall()
    
    result = []
    for row in drifts:
        task_key = row['task_key']
        
        t_cur = db.execute('SELECT description FROM tasks WHERE key = ?', (task_key,))
        t_row = t_cur.fetchone()
        desc = t_row['description'] if t_row else ''
        
        h_cur = db.execute('''
            SELECT field_changed, old_value, new_value, changed_at 
            FROM task_history 
            WHERE task_key = ? AND field_changed LIKE 'deadline%'
            ORDER BY changed_at ASC
        ''', (task_key,))
        history = [dict(h) for h in h_cur.fetchall()]
        
        result.append({
            'task_key': task_key,
            'description': desc,
            'change_count': row['change_count'],
            'history': history
        })
        
    return sorted(result, key=lambda x: x['change_count'], reverse=True)

def save_correction(db, meeting_id, task_key, field, original_value, corrected_value, correction_type='task'):
    db.execute('''
        INSERT INTO corrections (meeting_id, task_key, field, original_value, corrected_value, correction_type)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (meeting_id, task_key, field, original_value, corrected_value, correction_type))
    db.commit()

def get_recent_corrections(db, limit=10) -> list[dict]:
    cursor = db.execute('SELECT * FROM corrections ORDER BY created_at DESC LIMIT ?', (limit,))
    return [dict(row) for row in cursor.fetchall()]

def get_open_tasks(db) -> list[dict]:
    cursor = db.execute("SELECT * FROM tasks WHERE status NOT IN ('done')")
    return [dict(row) for row in cursor.fetchall()]

def get_tasks_for_person(db, owner) -> list[dict]:
    cursor = db.execute("SELECT * FROM tasks WHERE owner = ?", (owner,))
    return [dict(row) for row in cursor.fetchall()]
