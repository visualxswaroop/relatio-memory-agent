"""
Evaluation: compare three approaches for task recall at meeting 4.

(A) Plain LLM — only the latest transcript (meeting 4)
(B) All-context LLM — all 4 transcripts stuffed into one prompt
(C) Hindsight agent — recall + reflect from Hindsight memory + DB

Measures recall of 15 ground-truth tasks and 3 silent tasks.
Outputs a results table and bar chart PNG.
"""

import json
import os
import sys
import re
import time

# Add parent directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from dotenv import load_dotenv
load_dotenv()

from backend.pipeline import _llm_call, _clean_llm_output, MeetingExtraction, _parse_json_with_retries
from backend import memory, db
from backend.prompts import EXTRACTION_PROMPT

DATA_DIR = os.path.join("data", "sample_meetings")
RESULTS_DIR = os.path.join("backend", "eval", "results")


def load_ground_truth():
    with open(os.path.join(DATA_DIR, "ground_truth.json")) as f:
        return json.load(f)


def load_transcripts():
    with open(os.path.join(DATA_DIR, "meetings_meta.json")) as f:
        meta = json.load(f)
    transcripts = []
    for m in meta:
        with open(os.path.join(DATA_DIR, m["filename"]), encoding="utf-8") as f:
            transcripts.append({"title": m["title"], "date": m["date"], "text": f.read()})
    return transcripts


def extract_tasks_from_response(text: str) -> list[str]:
    """Extract task descriptions from LLM response, lowercased for matching."""
    try:
        data = json.loads(_clean_llm_output(text))
        tasks = data.get("tasks", [])
        return [t.get("description", "").lower().strip() for t in tasks if t.get("description")]
    except Exception:
        # Try to find task-like phrases
        lines = text.lower().split("\n")
        return [l.strip("- •*").strip() for l in lines if len(l.strip()) > 10]


def compute_recall(found_tasks: list[str], ground_truth_tasks: list[dict]) -> dict:
    """Compute recall: what fraction of ground truth tasks were found."""
    gt_descriptions = [t["description"].lower() for t in ground_truth_tasks]
    matched = 0
    matches = []
    for gt in gt_descriptions:
        for found in found_tasks:
            # Fuzzy match: check if key words overlap
            gt_words = set(gt.split())
            found_words = set(found.split())
            overlap = len(gt_words & found_words) / max(len(gt_words), 1)
            if overlap >= 0.4 or gt in found or found in gt:
                matched += 1
                matches.append(gt)
                break
    return {
        "total": len(gt_descriptions),
        "found": matched,
        "recall": matched / len(gt_descriptions) if gt_descriptions else 0,
        "matches": matches,
        "missed": [g for g in gt_descriptions if g not in matches],
    }


def approach_a_plain_llm(latest_transcript: str) -> list[str]:
    """(A) Plain LLM with only the latest transcript."""
    prompt = EXTRACTION_PROMPT.format(
        transcript=latest_transcript,
        existing_tasks_instruction="",
        correction_examples="",
    )
    messages = [{"role": "user", "content": prompt}]
    raw = _llm_call(messages, "MODEL_EXTRACT", json_mode=True, max_tokens=8192)
    return extract_tasks_from_response(raw)


def approach_b_all_context(all_transcripts: list[dict]) -> list[str]:
    """(B) LLM with all transcripts stuffed into context."""
    combined = "\n\n---\n\n".join(
        f"Meeting: {t['title']} ({t['date']})\n{t['text']}" for t in all_transcripts
    )
    prompt = f"""Extract ALL tasks mentioned across these meeting transcripts. 
Return only valid JSON with a "tasks" array, each task having "description", "owner" (null if unassigned), and "status".
Include tasks that were discussed but never assigned (silent tasks).

{combined}"""
    messages = [{"role": "user", "content": prompt}]
    raw = _llm_call(messages, "MODEL_EXTRACT", json_mode=True, max_tokens=8192)
    return extract_tasks_from_response(raw)


def approach_c_hindsight(hs_client, database) -> list[str]:
    """(C) Hindsight agent with recall + reflect + DB."""
    # Recall from Hindsight
    recall_results = memory.recall_facts(
        hs_client,
        query="List all tasks, commitments, and action items from all meetings. Include tasks that were discussed but never assigned.",
    )

    # Also get from DB
    open_tasks = db.get_open_tasks(database)
    all_tasks = db.get_tasks(database)
    silent = db.get_silent_tasks(database)

    # Combine
    task_descriptions = []
    for t in all_tasks:
        task_descriptions.append(t["description"].lower().strip())
    for t in silent:
        desc = t["description"].lower().strip()
        if desc not in task_descriptions:
            task_descriptions.append(desc)
    for fact in recall_results:
        # Try to extract task mentions from recall facts
        if any(kw in fact.lower() for kw in ["task", "assign", "will", "need to", "should", "deadline"]):
            task_descriptions.append(fact.lower().strip()[:200])

    return task_descriptions


def run_evaluation():
    """Run the full evaluation and output results."""
    os.makedirs(RESULTS_DIR, exist_ok=True)

    gt = load_ground_truth()
    transcripts = load_transcripts()

    all_gt_tasks = gt["tasks"] + gt["silent_tasks"]
    gt_tasks_only = gt["tasks"]
    gt_silent_only = gt["silent_tasks"]

    print("=" * 60)
    print("EVALUATION: Task Recall Comparison")
    print("=" * 60)
    print(f"Ground truth: {len(all_gt_tasks)} total tasks ({len(gt_silent_only)} silent)")
    print()

    results = {}

    # (A) Plain LLM - latest transcript only
    print("Running (A) Plain LLM (latest transcript only)...")
    try:
        tasks_a = approach_a_plain_llm(transcripts[-1]["text"])
        recall_a_all = compute_recall(tasks_a, all_gt_tasks)
        recall_a_silent = compute_recall(tasks_a, gt_silent_only)
        results["A"] = {"name": "Plain LLM", "all_recall": recall_a_all, "silent_recall": recall_a_silent, "task_count": len(tasks_a)}
        print(f"  Found {len(tasks_a)} tasks, recall: {recall_a_all['recall']:.1%}")
    except Exception as e:
        print(f"  ERROR: {e}")
        results["A"] = {"name": "Plain LLM", "all_recall": {"recall": 0, "found": 0, "total": len(all_gt_tasks)}, "silent_recall": {"recall": 0, "found": 0, "total": len(gt_silent_only)}, "task_count": 0}

    time.sleep(3)  # Rate limit spacing

    # (B) All-context LLM
    print("Running (B) All-context LLM (all transcripts)...")
    try:
        tasks_b = approach_b_all_context(transcripts)
        recall_b_all = compute_recall(tasks_b, all_gt_tasks)
        recall_b_silent = compute_recall(tasks_b, gt_silent_only)
        results["B"] = {"name": "All-Context LLM", "all_recall": recall_b_all, "silent_recall": recall_b_silent, "task_count": len(tasks_b)}
        print(f"  Found {len(tasks_b)} tasks, recall: {recall_b_all['recall']:.1%}")
    except Exception as e:
        print(f"  ERROR: {e}")
        results["B"] = {"name": "All-Context LLM", "all_recall": {"recall": 0, "found": 0, "total": len(all_gt_tasks)}, "silent_recall": {"recall": 0, "found": 0, "total": len(gt_silent_only)}, "task_count": 0}

    # (C) Hindsight agent
    print("Running (C) Hindsight Agent (memory + DB)...")
    try:
        hs_client = memory.init_hindsight()
        database = db.get_db("data/meetings.db")
        if hs_client:
            tasks_c = approach_c_hindsight(hs_client, database)
            recall_c_all = compute_recall(tasks_c, all_gt_tasks)
            recall_c_silent = compute_recall(tasks_c, gt_silent_only)
            results["C"] = {"name": "Hindsight Agent", "all_recall": recall_c_all, "silent_recall": recall_c_silent, "task_count": len(tasks_c)}
            print(f"  Found {len(tasks_c)} tasks, recall: {recall_c_all['recall']:.1%}")
        else:
            print("  Hindsight not available, skipping")
            results["C"] = {"name": "Hindsight Agent", "all_recall": {"recall": 0, "found": 0, "total": len(all_gt_tasks)}, "silent_recall": {"recall": 0, "found": 0, "total": len(gt_silent_only)}, "task_count": 0, "note": "Hindsight not available"}
    except Exception as e:
        print(f"  ERROR: {e}")
        results["C"] = {"name": "Hindsight Agent", "all_recall": {"recall": 0, "found": 0, "total": len(all_gt_tasks)}, "silent_recall": {"recall": 0, "found": 0, "total": len(gt_silent_only)}, "task_count": 0}

    # Print results table
    print("\n" + "=" * 60)
    print(f"{'Approach':<25} {'All Tasks':>12} {'Silent Tasks':>14} {'Tasks Found':>12}")
    print("-" * 60)
    for key in ["A", "B", "C"]:
        r = results[key]
        all_r = r["all_recall"]["recall"]
        sil_r = r["silent_recall"]["recall"]
        print(f"{r['name']:<25} {all_r:>11.1%} {sil_r:>13.1%} {r['task_count']:>12}")
    print("=" * 60)

    # Print missed tasks for each approach
    for key in ["A", "B", "C"]:
        r = results[key]
        missed = r["all_recall"].get("missed", [])
        if missed:
            print(f"\n{r['name']} missed: {', '.join(missed[:5])}")

    # Save results
    results_path = os.path.join(RESULTS_DIR, "eval_results.json")
    with open(results_path, "w") as f:
        # Make serializable
        clean_results = {}
        for k, v in results.items():
            clean_results[k] = {
                "name": v["name"],
                "all_task_recall": v["all_recall"]["recall"],
                "all_task_found": v["all_recall"]["found"],
                "all_task_total": v["all_recall"]["total"],
                "silent_task_recall": v["silent_recall"]["recall"],
                "silent_task_found": v["silent_recall"]["found"],
                "silent_task_total": v["silent_recall"]["total"],
                "tasks_extracted": v["task_count"],
            }
        json.dump(clean_results, f, indent=2)
    print(f"\nResults saved to {results_path}")

    # Generate bar chart
    try:
        generate_chart(results)
    except ImportError:
        print("matplotlib not installed, skipping chart generation")
        print("Install with: pip install matplotlib")

    return results


def generate_chart(results: dict):
    """Generate a bar chart PNG comparing the three approaches."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np

    labels = [results[k]["name"] for k in ["A", "B", "C"]]
    all_recall = [results[k]["all_recall"]["recall"] * 100 for k in ["A", "B", "C"]]
    silent_recall = [results[k]["silent_recall"]["recall"] * 100 for k in ["A", "B", "C"]]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(10, 6))
    bars1 = ax.bar(x - width/2, all_recall, width, label="All Tasks Recall (%)", color=["#ef4444", "#f59e0b", "#22c55e"])
    bars2 = ax.bar(x + width/2, silent_recall, width, label="Silent Tasks Recall (%)", color=["#fca5a5", "#fcd34d", "#86efac"])

    ax.set_ylabel("Recall (%)")
    ax.set_title("Task Recall: Plain LLM vs All-Context vs Hindsight Agent")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.set_ylim(0, 110)

    # Add value labels
    for bar in bars1:
        height = bar.get_height()
        ax.annotate(f"{height:.0f}%", xy=(bar.get_x() + bar.get_width() / 2, height),
                     xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=10)
    for bar in bars2:
        height = bar.get_height()
        ax.annotate(f"{height:.0f}%", xy=(bar.get_x() + bar.get_width() / 2, height),
                     xytext=(0, 3), textcoords="offset points", ha="center", va="bottom", fontsize=10)

    chart_path = os.path.join(RESULTS_DIR, "eval_chart.png")
    plt.tight_layout()
    plt.savefig(chart_path, dpi=150)
    plt.close()
    print(f"Chart saved to {chart_path}")


if __name__ == "__main__":
    run_evaluation()
