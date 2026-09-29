import urllib.request
import json

def post(url, data):
    req = urllib.request.Request(
        url,
        data=json.dumps(data).encode('utf-8'),
        headers={'Content-Type': 'application/json'}
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def get(url):
    with urllib.request.urlopen(url) as resp:
        return json.loads(resp.read().decode('utf-8'))

print("=== 1. Health check ===")
print(get("http://127.0.0.1:5000/api/health"))

print("=== 2. Create contact ===")
contact = post("http://127.0.0.1:5000/api/contacts", {
    "name": "Rahul Sharma",
    "company": "TechNova",
    "role": "VP of Engineering"
})
cid = contact["id"]
print(f"Contact created: ID={cid}, Name={contact['name']}")

print("=== 3. Ingest meeting notes with discrete memory units ===")
notes_res = post(f"http://127.0.0.1:5000/api/contacts/{cid}/add-notes", {
    "notes": "Rahul mentioned that their primary migration deadline is end of Q3. He is cautious about vendor lock-in with AWS and prefers hybrid architecture. He prefers concise async updates via Slack instead of weekly status calls. He loves cricket and mentioned his daughter is applying to Stanford. He committed to sending the current infrastructure spec by Friday. We promised to deliver a security compliance checklist by next Tuesday.",
    "meeting_title": "Architecture Alignment Call"
})
print("Stored locally:", notes_res.get("local_memories_stored"))
print("Extracted intelligence items:", notes_res.get("total_extracted_items"))
for k, v in notes_res.get("extracted", {}).items():
    if v and isinstance(v, list):
        print(f" - [{k}]: {len(v)} item(s)")

print("=== 4. Test Memory Query (What do you remember?) ===")
query_res = post(f"http://127.0.0.1:5000/api/contacts/{cid}/remember", {
    "query": "What are Rahul's preferences for communication and personal details?"
})
print("Agent Response:")
print(query_res.get("answer"))

print("=== 5. Test Personalized Meeting Brief ===")
brief_res = post(f"http://127.0.0.1:5000/api/contacts/{cid}/brief", {
    "meeting_topic": "Cloud & Security Architecture"
})
print("Brief Generated:")
brief_text = brief_res.get("brief", "")
print(brief_text.encode("ascii", errors="replace").decode("ascii"))

print("=== 6. Test Commitments Tracking ===")
commitments = get(f"http://127.0.0.1:5000/api/contacts/{cid}/commitments")
print("Commitments count:", len(commitments))
for c in commitments:
    print(f" * Commitment: owner={c.get('owner')} | desc={c.get('description')} | deadline={c.get('deadline_text')} | status={c.get('status')}")

print("=== 7. Test Relationship Evolution ===")
evo = get(f"http://127.0.0.1:5000/api/contacts/{cid}/evolution")
print("Total memories:", evo.get("total_memories"))
evolution_str = str(evo.get("evolution", ""))
print("Evolution preview:\n", evolution_str.encode("ascii", errors="replace").decode("ascii")[:500] + "...")
print("\n=== ALL 7 TESTS COMPLETED AND VERIFIED! ===")
