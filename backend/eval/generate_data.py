"""
Generate 4 synthetic Hinglish business meetings + ground truth for evaluation.

Scenario: Acme Tech product team (Priya, Rahul, Ananya, Vikram, Deepak)
- 15 tasks total, 3 never assigned (silent tasks)
- One deadline that slips across meetings (dashboard migration)
- One decision reversed later (microservices vs monolith)
"""

import json
import os

MEETINGS = [
    {
        "filename": "meeting_01_product_kickoff.txt",
        "title": "Q4 Product Kickoff",
        "date": "2024-09-02",
        "transcript": """Priya: Okay team, let's kick off Q4 planning. We have a lot on our plate this quarter.

Rahul: Haan, so the big thing is the dashboard migration. We need to move from the old Angular dashboard to React. I think we can finish this by end of September.

Priya: September end? That's tight. Rahul, you'll own the dashboard migration, right?

Rahul: Yes, I'll handle it. September 30 deadline works for me.

Ananya: I wanted to bring up the mobile app redesign. We've been getting a lot of complaints about the onboarding flow. 

Priya: Good point. Ananya, can you take that? Let's target mid-October for the first prototype.

Ananya: Sure, I'll own the mobile onboarding redesign. October 15 for the prototype.

Vikram: What about the API rate limiting? We had 3 outages last month because of that.

Priya: Haan, that's critical. Vikram, please implement rate limiting on the payment endpoints by September 15.

Vikram: Done. I'll also set up monitoring dashboards for it.

Priya: Perfect. Vikram, you'll also handle the monitoring setup then.

Deepak: I've been looking into the recommendation engine. We should explore ML-based recommendations for the marketplace.

Priya: Interesting idea. Let's explore that. Who wants to own it?

[silence]

Priya: Okay, we'll come back to that. Also, we need to update the API documentation. It's really outdated.

Rahul: Haan, someone should definitely do that.

Priya: Let's discuss that next time. Moving on — we need to set up the staging environment for Q4 testing.

Vikram: I can help with that but I'm already stretched with the rate limiting work.

Priya: Let's see, dekhte hain who can take it.

Ananya: One more thing — the customer feedback portal. We promised it in Q3 but never delivered. 

Priya: Right. That's still open. We need to address that.

Priya: Also, the architecture discussion — I think we should move to microservices. The monolith is getting too complex. Let's make that our Q4 direction.

Rahul: Makes sense. Microservices it is.

Priya: Decision made. Microservices architecture for new services starting Q4.

Deepak: For the data pipeline, I'll set up the ETL jobs for the new analytics module. Target is October 5.

Priya: Great. Deepak, the ETL pipeline setup is yours by October 5.

Priya: Rahul, can you also handle the CI/CD pipeline upgrade? We need to move to GitHub Actions.

Rahul: Sure, I'll look into it. Maybe by end of October.

Priya: Okay. Let's also plan the Q4 all-hands presentation. The date is October 20.

Priya: And the security audit is coming up on September 25. Everyone needs to be prepared.

Vikram: I'll prepare the security documentation for the audit.

Priya: Thanks. Let's wrap up. We have a lot to do this quarter."""
    },
    {
        "filename": "meeting_02_sprint_review.txt",
        "title": "Sprint 1 Review",
        "date": "2024-09-16",
        "transcript": """Priya: Okay, two weeks in. Let's review progress. Rahul, dashboard migration?

Rahul: So, the migration is going slower than expected. I've hit some issues with the legacy data layer. I think we need to push the deadline to October 15.

Priya: October 15? That's two weeks late. Is there anything blocking you?

Rahul: Mainly the legacy API compatibility. I need to refactor the data models first.

Priya: Okay, let's update the deadline to October 15. Rahul, please make sure you flag issues earlier next time.

Ananya: Mobile onboarding redesign is on track. I've completed the wireframes and started the implementation.

Priya: Great, Ananya. Keep it up.

Vikram: Rate limiting is done. Deployed to staging yesterday. Monitoring dashboards are also set up.

Priya: Excellent. Vikram, mark those as done.

Deepak: ETL pipeline is in progress. I should be done by October 3, slightly ahead of schedule.

Priya: Nice. What about the recommendation engine idea from last time?

[silence]

Priya: Nobody took that? It was discussed but nobody owns it. Let's make sure we assign it soon.

Rahul: CI/CD pipeline upgrade — I haven't started yet. Dashboard migration is taking priority.

Priya: Okay. Let's keep CI/CD for later in the quarter.

Priya: The staging environment — did anyone set it up?

Vikram: I did a basic setup but it's not fully configured yet.

Priya: Okay, who's going to finish the staging environment setup? 

[silence]

Priya: Dekhte hain, we'll figure it out.

Ananya: The customer feedback portal — any updates?

Priya: Still open. We haven't assigned it yet.

Priya: One more thing — the security audit is next week, September 25. Everyone ready?

Vikram: Security docs are prepared. We should be fine.

Priya: Good. Remember, Q4 all-hands is October 20. Rahul, can you prepare a demo of the new dashboard?

Rahul: If the migration is going well by then, sure. October 20, noted.

Priya: Alright, let's wrap up. Key concern is the dashboard deadline slip."""
    },
    {
        "filename": "meeting_03_mid_quarter.txt",
        "title": "Mid-Quarter Check-in",
        "date": "2024-10-07",
        "transcript": """Priya: Mid-quarter check. Let's go through everything. Rahul, dashboard?

Rahul: So... I need more time. The data migration is more complex than we thought. I'm now looking at end of October, maybe November 1.

Priya: November 1? That's a full month late from the original September 30 deadline. This is concerning.

Rahul: I know, I know. But the legacy system has so many edge cases. I'm making progress though.

Priya: Let's set the deadline to October 31 and see. No more slips please.

Ananya: Mobile onboarding prototype is ready. I demoed it to the design team and they approved it. Now I need to do user testing.

Priya: Awesome. Ananya, start the user testing phase. Let's target October 25 for the testing results.

Ananya: Got it.

Deepak: ETL pipeline is done. Deployed and running in production.

Priya: Great work Deepak. Mark it done.

Priya: Now, about the architecture decision — I've been rethinking. After talking with the CTO, microservices might be overkill for our current scale. Let's actually stick with the monolith but modularize it better. We're reversing the microservices decision.

Rahul: Wait, we already started planning some services with microservices in mind.

Priya: I understand, but the CTO made a good point about operational complexity. Decision changed — modular monolith, not microservices.

Vikram: What about the API documentation? That's been open since the first meeting.

Priya: Haan, someone should really take that up. It's important.

[silence]

Priya: Okay, adding it to the list again. 

Priya: The recommendation engine — still no owner?

Deepak: I can look into it now that ETL is done. But I'll need to do some research first. Dekhte hain.

Priya: Deepak, let's say you'll do a feasibility study by October 20?

Deepak: I'll try. Let me see.

Priya: Customer feedback portal — this has been open for three meetings now. We need to address this.

Ananya: I can take it after the mobile testing is done. Maybe mid-November?

Priya: Let's not commit right now. It's still open.

Priya: Security audit went well, by the way. Vikram, great job on the documentation.

Vikram: Thanks. I also found some vulnerabilities that we should fix. I'll create tickets for those.

Priya: Please do. Create the vulnerability fix tickets.

Priya: Q4 all-hands reminder — October 20. Rahul, dashboard demo is expected."""
    },
    {
        "filename": "meeting_04_final_review.txt",
        "title": "Q4 Final Sprint Planning",
        "date": "2024-10-21",
        "transcript": """Priya: Okay team, we're past the all-hands. Let's plan the final sprint. Rahul, dashboard status?

Rahul: Finally making good progress. The core migration is done, just need to do testing and bug fixes. I'm confident we'll hit October 31.

Priya: Good. Let's make sure. That deadline has moved 3 times now — September 30, October 15, October 31.

Ananya: User testing for mobile onboarding is complete. 85% positive feedback. I'm now doing final tweaks based on the feedback.

Priya: Excellent. When will the final version be ready?

Ananya: End of this week, October 25.

Priya: Great. Ananya, finalize the mobile onboarding by October 25.

Deepak: Recommendation engine feasibility study is done. I think we can build a basic version using collaborative filtering. I'll start implementation.

Priya: Good. Deepak, own the recommendation engine implementation. Target date?

Deepak: November 15.

Priya: November 15 for the recommendation engine MVP.

Vikram: I fixed 2 of the 4 security vulnerabilities. The other 2 need backend changes that depend on Rahul's dashboard migration.

Priya: Okay. Vikram, finish the remaining security fixes after dashboard migration is complete.

Priya: CI/CD pipeline upgrade — Rahul, any progress?

Rahul: I've been completely focused on dashboard. Haven't touched CI/CD at all.

Priya: Hmm. We need this done. Can someone else take it?

[silence]

Priya: Another task with no owner. Let's discuss next time.

Priya: Customer feedback portal — this has been discussed in EVERY meeting and nobody owns it. Four meetings now.

Ananya: I said I might take it but only after November.

Priya: Let's be clear — this is still unassigned and open.

Priya: API documentation — same story. Open since meeting one. Nobody assigned.

Priya: Staging environment — Vikram, did you finish it?

Vikram: It's working but needs some polish. I'll finish it by October 28.

Priya: Good. Vikram, complete staging environment by October 28.

Priya: Reminder about the board presentation on November 10. I need everyone's quarterly highlights by November 5.

Priya: Let's finish strong this quarter."""
    },
]

GROUND_TRUTH = {
    "total_tasks": 15,
    "tasks": [
        {"key": "dashboard_migration", "description": "Migrate Angular dashboard to React", "owner": "Rahul", "deadline_original": "2024-09-30", "deadline_drifts": ["2024-10-15", "2024-10-31"], "meetings": [1, 2, 3, 4]},
        {"key": "mobile_onboarding_redesign", "description": "Redesign mobile app onboarding flow", "owner": "Ananya", "deadline": "2024-10-15", "meetings": [1, 2, 3, 4]},
        {"key": "api_rate_limiting", "description": "Implement rate limiting on payment endpoints", "owner": "Vikram", "deadline": "2024-09-15", "status_final": "done", "meetings": [1, 2]},
        {"key": "monitoring_dashboards", "description": "Set up monitoring dashboards for rate limiting", "owner": "Vikram", "meetings": [1, 2]},
        {"key": "etl_pipeline_setup", "description": "Set up ETL jobs for analytics module", "owner": "Deepak", "deadline": "2024-10-05", "status_final": "done", "meetings": [1, 2, 3]},
        {"key": "cicd_pipeline_upgrade", "description": "Upgrade CI/CD to GitHub Actions", "owner": "Rahul", "meetings": [1, 2, 4], "note": "never started"},
        {"key": "security_documentation", "description": "Prepare security docs for audit", "owner": "Vikram", "status_final": "done", "meetings": [1, 2, 3]},
        {"key": "mobile_user_testing", "description": "Conduct user testing for mobile onboarding", "owner": "Ananya", "meetings": [3, 4]},
        {"key": "vulnerability_fixes", "description": "Fix security vulnerabilities found in audit", "owner": "Vikram", "meetings": [3, 4]},
        {"key": "recommendation_engine_feasibility", "description": "Feasibility study for ML recommendations", "owner": "Deepak", "meetings": [3, 4]},
        {"key": "recommendation_engine_implementation", "description": "Build recommendation engine MVP", "owner": "Deepak", "deadline": "2024-11-15", "meetings": [4]},
        {"key": "staging_environment_setup", "description": "Complete staging environment for Q4", "owner": "Vikram", "deadline": "2024-10-28", "meetings": [1, 2, 3, 4]},
    ],
    "silent_tasks": [
        {"key": "recommendation_engine_exploration", "description": "Explore ML-based recommendations (initially unassigned)", "meetings": [1, 2, 3]},
        {"key": "api_documentation_update", "description": "Update outdated API documentation", "meetings": [1, 3, 4]},
        {"key": "cicd_pipeline_reassign", "description": "CI/CD pipeline needs new owner after Rahul couldn't do it", "meetings": [4]},
    ],
    "total_silent_tasks": 3,
    "deadline_drifts": [
        {"task": "dashboard_migration", "changes": ["2024-09-30 → 2024-10-15", "2024-10-15 → 2024-10-31"], "count": 2}
    ],
    "decision_reversed": {
        "original": "Microservices architecture for new services (Meeting 1)",
        "reversed": "Modular monolith instead of microservices (Meeting 3)",
        "reason": "CTO concern about operational complexity"
    },
    "stuck_topics": [
        {"text": "Customer feedback portal — discussed in 4 meetings, never assigned", "meetings": [1, 2, 3, 4]},
        {"text": "API documentation update — discussed in 3 meetings, never assigned", "meetings": [1, 3, 4]},
    ],
    "important_dates": [
        {"title": "Security Audit", "date": "2024-09-25"},
        {"title": "Q4 All-Hands Presentation", "date": "2024-10-20"},
        {"title": "Board Presentation", "date": "2024-11-10"},
        {"title": "Quarterly Highlights Due", "date": "2024-11-05"},
    ],
    "participants": ["Priya", "Rahul", "Ananya", "Vikram", "Deepak"]
}


def generate():
    """Generate sample meetings and ground truth."""
    out_dir = os.path.join("data", "sample_meetings")
    os.makedirs(out_dir, exist_ok=True)

    for meeting in MEETINGS:
        path = os.path.join(out_dir, meeting["filename"])
        with open(path, "w", encoding="utf-8") as f:
            f.write(meeting["transcript"].strip())
        print(f"  Written: {path}")

    gt_path = os.path.join(out_dir, "ground_truth.json")
    with open(gt_path, "w", encoding="utf-8") as f:
        json.dump(GROUND_TRUTH, f, indent=2)
    print(f"  Written: {gt_path}")

    # Also save meeting metadata
    meta_path = os.path.join(out_dir, "meetings_meta.json")
    meta = [{"filename": m["filename"], "title": m["title"], "date": m["date"]} for m in MEETINGS]
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    print(f"  Written: {meta_path}")

    print(f"\nGenerated {len(MEETINGS)} synthetic meetings with {GROUND_TRUTH['total_tasks']} tasks "
          f"({GROUND_TRUTH['total_silent_tasks']} silent)")


if __name__ == "__main__":
    generate()
