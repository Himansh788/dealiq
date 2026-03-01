"""
Ask DealIQ — Demo Data
======================
Realistic demo transcript, emails, and deal used by /ask/demo/* endpoints.
No Zoho account or database required to test the Ask DealIQ feature.
"""

DEMO_TRANSCRIPT = """[00:00] Rep: Hi Sarah, thanks for joining. I wanted to follow up on our initial conversation
about streamlining your revenue operations.

[00:15] Sarah (VP Sales, Acme Corp): Hi! Yes, we've been thinking about this a lot. Our main
challenge right now is that our reps are spending about 60% of their time on admin work —
updating Salesforce, writing follow-up emails, preparing for calls. We need to get that down
to under 30%.

[01:02] Rep: That's a significant number. What's the business impact of that?

[01:08] Sarah: We estimate we're losing about $2M in potential pipeline because reps simply
don't have enough selling time. Our quota attainment is at 68% across the team.

[01:45] Rep: Who else is involved in evaluating solutions like this?

[01:50] Sarah: Our CRO, Michael Chen, has final sign-off. He's the one who approved this
evaluation. I'm leading the technical assessment, and our RevOps lead James will handle
the integration side.

[02:30] Rep: What does your decision process look like?

[02:35] Sarah: We need to complete our evaluation by end of March. We're looking at two
other vendors as well. Key criteria for us are: accuracy of AI insights, integration with
Salesforce, and time-to-value. We need something that shows ROI within 60 days.

[03:15] Rep: Understood. On pricing, what budget range are you working with?

[03:20] Sarah: Michael has approved up to $75K annually for this. But honestly, if we can
prove the ROI on reduced admin time, there's flexibility. He mentioned he could go up to
$100K if the business case is strong.

[04:00] Rep: I'd love to schedule a technical deep-dive with James next week. Can we do
Thursday at 2pm?

[04:05] Sarah: Thursday works. I'll loop James in. Can you also send over the security
questionnaire? Our InfoSec team needs to review before we go further.

[04:20] Rep: Absolutely. I'll send that today along with a summary of what we discussed.
Let me also set up a brief call with Michael before end of month — I think hearing how
other CROs have seen ROI would help build the business case.

[04:40] Sarah: That would be great. Let's plan for that in the week of March 10th.
"""

DEMO_EMAILS = [
    {
        "from": "rep@ourcompany.com",
        "to": "sarah@acme.com",
        "subject": "Follow-up: Revenue Operations Discussion",
        "content": (
            "Hi Sarah, Great speaking with you today. As discussed, I'm attaching the security "
            "questionnaire for your InfoSec team. Key next steps: 1) Technical deep-dive with "
            "James — Thursday 2pm 2) CRO call with Michael — week of March 10th. "
            "Looking forward to moving this forward."
        ),
        "sent_time": "2025-02-20",
        "direction": "outgoing",
    },
    {
        "from": "sarah@acme.com",
        "to": "rep@ourcompany.com",
        "subject": "Re: Follow-up: Revenue Operations Discussion",
        "content": (
            "Thanks for sending this over quickly. James confirmed Thursday 2pm works. "
            "One question — do you offer a pilot program? Michael asked if we could test "
            "with a subset of reps before full rollout. Also, what's the typical "
            "implementation timeline?"
        ),
        "sent_time": "2025-02-21",
        "direction": "incoming",
    },
    {
        "from": "rep@ourcompany.com",
        "to": "sarah@acme.com",
        "subject": "Re: Re: Follow-up: Revenue Operations Discussion",
        "content": (
            "Great question. Yes, we offer a 30-day pilot with up to 10 users at no cost. "
            "Typical implementation is 2-3 weeks. I can walk James through the technical "
            "setup on Thursday. For the pilot, we'd just need API access to your Salesforce "
            "instance and email system. I'll bring a detailed implementation plan to our "
            "Thursday session."
        ),
        "sent_time": "2025-02-22",
        "direction": "outgoing",
    },
]

DEMO_DEAL = {
    "id": "demo_1",
    "name": "Acme Corp — Revenue Operations Platform",
    "company": "Acme Corp",
    "stage": "Technical Evaluation",
    "amount": 75000,
    "closing_date": "2025-03-31",
    "owner": "Demo Rep",
    "contacts": [
        {"name": "Sarah Johnson", "role": "VP Sales", "email": "sarah@acme.com"},
        {"name": "Michael Chen", "role": "CRO", "email": "michael@acme.com"},
        {"name": "James Park", "role": "RevOps Lead", "email": "james@acme.com"},
    ],
    "health_score": 72,
    "health_label": "at_risk",
    "last_activity_time": "2025-02-22",
    "next_step": "Technical deep-dive with James — Thursday 2pm",
    "probability": 60,
    "discount_mention_count": 1,
    "economic_buyer_engaged": True,
    "activity_count_30d": 5,
}

# ── Hardcoded fallback responses (no AI key needed) ───────────────────────────

FALLBACK_QA_RESPONSE = {
    "answer": (
        "Based on the demo transcript and emails:\n\n"
        "• **Pain points**: Reps spending 60% of time on admin work (from call transcript). "
        "Quota attainment at 68%, estimated $2M lost pipeline due to insufficient selling time.\n"
        "• **Budget**: $75K approved annually, flexibility up to $100K with strong ROI case "
        "(from call transcript, Feb 20).\n"
        "• **Key stakeholders**: Sarah Johnson (VP Sales, evaluation lead), Michael Chen (CRO, "
        "final sign-off), James Park (RevOps, integration).\n\n"
        "⚠️ Two other vendors in evaluation — decision by end of March.\n\n"
        "**Suggested next step**: Send security questionnaire today and confirm Thursday 2pm "
        "technical session with James."
    ),
    "sources_used": ["transcript_2025-02-20", "email_2025-02-20", "email_2025-02-21"],
    "confidence": "high",
    "deal_risks_detected": ["Competitive evaluation — 2 other vendors", "Decision deadline end of March"],
    "suggested_next_step": "Send security questionnaire and prepare ROI business case for CRO call (week of March 10th).",
}

FALLBACK_MEDDIC_RESPONSE = {
    "metrics": {
        "status": "strong",
        "detail": "Reps spend 60% of time on admin vs target of 30%. $2M pipeline lost. 68% quota attainment.",
        "evidence": "'We estimate we're losing about $2M in potential pipeline because reps simply don't have enough selling time.'",
    },
    "economic_buyer": {
        "status": "strong",
        "identified": True,
        "name": "Michael Chen",
        "detail": "CRO with final sign-off authority. Has approved budget up to $75K, flexible to $100K.",
        "evidence": "'Our CRO, Michael Chen, has final sign-off. He's the one who approved this evaluation.'",
    },
    "decision_criteria": {
        "status": "strong",
        "criteria_list": [
            "Accuracy of AI insights",
            "Salesforce integration",
            "Time-to-value (ROI within 60 days)",
        ],
        "detail": "Three explicit criteria stated by Sarah.",
        "evidence": "'Key criteria for us are: accuracy of AI insights, integration with Salesforce, and time-to-value.'",
    },
    "decision_process": {
        "status": "strong",
        "steps_identified": [
            "Technical assessment led by Sarah",
            "Integration review by James (RevOps)",
            "InfoSec security questionnaire review",
            "Final sign-off by Michael Chen (CRO)",
        ],
        "timeline": "Evaluation complete by end of March 2025",
        "detail": "Parallel tracks: technical + security + CRO buy-in.",
        "evidence": "'We need to complete our evaluation by end of March.'",
    },
    "identify_pain": {
        "status": "strong",
        "pain_points": [
            "60% rep time on admin work",
            "$2M lost pipeline from insufficient selling time",
            "68% quota attainment (below target)",
        ],
        "detail": "Quantified pain with clear business impact. Strong compelling event.",
        "evidence": "'Our main challenge right now is that our reps are spending about 60% of their time on admin work.'",
    },
    "champion": {
        "status": "partial",
        "identified": True,
        "name": "Sarah Johnson",
        "detail": "Sarah is the evaluation lead and internally advocating for the project. Not confirmed she will actively champion with Michael.",
        "evidence": "Sarah is leading the technical assessment and arranged the call. She referenced Michael's flexibility on budget.",
    },
    "overall_score": "strong",
    "gaps": [
        "Champion commitment not fully confirmed — needs explicit sponsorship conversation with Sarah",
        "Competitive differentiation not discussed — 2 other vendors in play",
    ],
    "recommended_questions_for_next_call": [
        "Sarah, what would make you feel confident recommending us to Michael over the other vendors?",
        "What does the InfoSec review timeline look like — who owns that process?",
        "Can you walk me through what a successful 30-day pilot would look like for your team?",
    ],
}

FALLBACK_BRIEF_RESPONSE = {
    "snapshot": "Acme Corp — Revenue Operations Platform | Technical Evaluation | $75K ACV | Health: At Risk (72/100)",
    "timeline": [
        {"date": "2025-02-20", "event": "Discovery call — pain quantified ($2M lost pipeline, 68% attainment). Budget confirmed ($75K, flex to $100K). Three evaluators identified.", "source": "transcript"},
        {"date": "2025-02-20", "event": "Follow-up email sent with security questionnaire. Next steps confirmed: James deep-dive Thursday, CRO call week of March 10.", "source": "email"},
        {"date": "2025-02-21", "event": "Sarah confirmed Thursday 2pm with James. Requested pilot program details and implementation timeline.", "source": "email"},
        {"date": "2025-02-22", "event": "Pilot offer confirmed (30-day, 10 users, no cost). Implementation timeline 2-3 weeks. Technical plan promised for Thursday.", "source": "email"},
    ],
    "current_status": "In technical evaluation stage. Security questionnaire sent, pending InfoSec review. Technical deep-dive with RevOps lead James scheduled. CRO alignment call planned for week of March 10. Two other vendors in competitive evaluation.",
    "stakeholders": [
        {"name": "Sarah Johnson", "role": "VP Sales / Evaluation Lead", "engagement": "active", "last_contact": "2025-02-21"},
        {"name": "Michael Chen", "role": "CRO / Economic Buyer", "engagement": "quiet", "last_contact": "Not yet contacted directly"},
        {"name": "James Park", "role": "RevOps Lead / Technical Evaluator", "engagement": "quiet", "last_contact": "Not yet contacted directly"},
    ],
    "risks": [
        {"risk": "Competitive evaluation with 2 other vendors", "severity": "high", "evidence": "'We're looking at two other vendors as well' (transcript, Feb 20)"},
        {"risk": "CRO not yet engaged directly — all communication through Sarah", "severity": "medium", "evidence": "Michael Chen has sign-off authority but no direct touchpoint yet"},
        {"risk": "InfoSec review is a potential blocker — timeline unknown", "severity": "medium", "evidence": "Sarah: 'Our InfoSec team needs to review before we go further' (transcript, Feb 20)"},
    ],
    "actions": [
        {"priority": 1, "action": "Prepare a quantified ROI model showing $2M pipeline recovery before CRO call (March 10 week)", "reason": "Michael's budget flexibility is tied to ROI strength. This is the primary closing lever."},
        {"priority": 2, "action": "Run Thursday's technical deep-dive focused on Salesforce integration and pilot setup with James", "reason": "James owns integration — his sign-off unlocks technical approval track."},
        {"priority": 3, "action": "Follow up on InfoSec questionnaire status 48 hours after sending", "reason": "InfoSec delays are common blockers. Get ahead of this now."},
    ],
}
