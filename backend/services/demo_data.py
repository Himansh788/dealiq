"""
Simulated deal data for hackathon demo.
Used when: (1) no Zoho account connected, (2) demo mode requested, (3) Zoho API fails.
"""

from datetime import datetime, timedelta, timezone


def _days_ago(n: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=n)
    return dt.isoformat()


SIMULATED_DEALS = [
    {
        "id": "sim_001",
        "name": "Acme Corp — Enterprise Plan",
        "stage": "Negotiation/Review",
        "amount": 84000,
        "closing_date": (datetime.now(timezone.utc) + timedelta(days=12)).strftime("%Y-%m-%d"),
        "account_name": "Acme Corporation",
        "owner": "Sarah Chen",
        "last_activity_time": _days_ago(3),
        "created_time": _days_ago(45),
        "probability": 75,
        "next_step": "Send revised contract by Thursday, March 6",
        "contact_count": 3,
        "economic_buyer_engaged": True,
        "discount_mention_count": 2,
        "activity_count_30d": 7,
        "description": "Send revised contract by Thursday, March 6",
    },
    {
        "id": "sim_002",
        "name": "TechStart Inc — Growth Tier",
        "stage": "Proposal/Price Quote",
        "amount": 36000,
        "closing_date": (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%d"),
        "account_name": "TechStart Inc",
        "owner": "James Okafor",
        "last_activity_time": _days_ago(19),
        "created_time": _days_ago(40),
        "probability": 60,
        "next_step": None,
        "contact_count": 1,
        "economic_buyer_engaged": False,
        "discount_mention_count": 0,
        "activity_count_30d": 2,
        "description": None,
    },
    {
        "id": "sim_003",
        "name": "GlobalRetail — Starter Pack",
        "stage": "Needs Analysis",
        "amount": 12000,
        "closing_date": (datetime.now(timezone.utc) + timedelta(days=45)).strftime("%Y-%m-%d"),
        "account_name": "GlobalRetail Ltd",
        "owner": "Maya Patel",
        "last_activity_time": _days_ago(2),
        "created_time": _days_ago(8),
        "probability": 40,
        "next_step": "Discovery call scheduled for March 5, 2PM IST",
        "contact_count": 2,
        "economic_buyer_engaged": False,
        "discount_mention_count": 0,
        "activity_count_30d": 4,
        "description": "Discovery call scheduled for March 5, 2PM IST",
    },
    {
        "id": "sim_004",
        "name": "FinanceFlow — Platform License",
        "stage": "Negotiation/Review",
        "amount": 120000,
        "closing_date": (datetime.now(timezone.utc) - timedelta(days=5)).strftime("%Y-%m-%d"),
        "account_name": "FinanceFlow Corp",
        "owner": "Sarah Chen",
        "last_activity_time": _days_ago(34),
        "created_time": _days_ago(90),
        "probability": 50,
        "next_step": None,
        "contact_count": 1,
        "economic_buyer_engaged": False,
        "discount_mention_count": 5,
        "activity_count_30d": 0,
        "description": None,
    },
    {
        "id": "sim_005",
        "name": "HealthTech Solutions — Annual",
        "stage": "Value Proposition",
        "amount": 28000,
        "closing_date": (datetime.now(timezone.utc) + timedelta(days=20)).strftime("%Y-%m-%d"),
        "account_name": "HealthTech Solutions",
        "owner": "James Okafor",
        "last_activity_time": _days_ago(1),
        "created_time": _days_ago(12),
        "probability": 65,
        "next_step": "Send ROI calculator and case study by EOD Friday",
        "contact_count": 4,
        "economic_buyer_engaged": True,
        "discount_mention_count": 0,
        "activity_count_30d": 8,
        "description": "Send ROI calculator and case study by EOD Friday",
    },
    {
        "id": "sim_006",
        "name": "LogiCo — Teams License",
        "stage": "Proposal/Price Quote",
        "amount": 18000,
        "closing_date": (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%d"),
        "account_name": "LogiCo Inc",
        "owner": "Maya Patel",
        "last_activity_time": _days_ago(11),
        "created_time": _days_ago(28),
        "probability": 45,
        "next_step": "Follow up on proposal",
        "contact_count": 2,
        "economic_buyer_engaged": False,
        "discount_mention_count": 3,
        "activity_count_30d": 3,
        "description": "Follow up on proposal",
    },
]

# ── Simulated Email Threads (per deal) ────────────────────────────────────────

def _date_str(days_ago: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.strftime("%Y-%m-%d")


SIMULATED_EMAILS = {
    "sim_001": [  # Acme Corp — late-stage, 3 days stalled
        {
            "direction": "received",
            "from": "david.kim@acmecorp.com",
            "subject": "Re: Revised Contract — Acme Enterprise",
            "content": "Sarah, thanks for sending this over. I've shared it with our legal team. They have a few redlines around liability cap and auto-renewal terms. Should have their feedback to you by Friday. Also — procurement is asking whether you offer a multi-year lock-in discount. Is that something we can discuss?",
            "sent_time": _date_str(3),
        },
        {
            "direction": "sent",
            "from": "sarah.chen@dealiq.com",
            "subject": "Revised Contract — Acme Enterprise",
            "content": "Hi David, please find the revised agreement attached reflecting the 12% early-commit discount we discussed. I've also included the implementation timeline doc for your IT team — 3 weeks from signature to full go-live, with dedicated onboarding support. Let me know if the March 7th review call still works? Looking forward to getting this across the line.",
            "sent_time": _date_str(5),
        },
        {
            "direction": "received",
            "from": "david.kim@acmecorp.com",
            "subject": "Re: Contract timeline",
            "content": "We're still interested but legal review is taking longer than expected. Our procurement process requires a 2-week review minimum. Can you hold the March 31 pricing deadline? We don't want to lose the discount because of internal process.",
            "sent_time": _date_str(10),
        },
        {
            "direction": "sent",
            "from": "sarah.chen@dealiq.com",
            "subject": "Contract timeline",
            "content": "David, totally understand. I've flagged this internally and can hold the pricing until April 7th — that gives your team a full two weeks. After that date I'll need to revert to standard pricing. Would it help if I joined a call with your legal team directly to answer any questions and speed up the review?",
            "sent_time": _date_str(12),
        },
        {
            "direction": "received",
            "from": "david.kim@acmecorp.com",
            "subject": "Quick question before we proceed",
            "content": "One more thing — our CTO wants to understand the data residency model. We're in a regulated industry. Is data stored in India? Can we get a data processing agreement (DPA) as part of the contract package?",
            "sent_time": _date_str(18),
        },
    ],

    "sim_002": [  # TechStart — proposal sent, 19 days no response
        {
            "direction": "sent",
            "from": "james.okafor@dealiq.com",
            "subject": "Following up — TechStart Growth Tier Proposal",
            "content": "Hi Priya, just checking in on the proposal I sent last week. Happy to answer any questions or walk you through the numbers on a quick call. Would Thursday work?",
            "sent_time": _date_str(5),
        },
        {
            "direction": "sent",
            "from": "james.okafor@dealiq.com",
            "subject": "Re: TechStart Growth Proposal",
            "content": "Priya, hope all is well. I wanted to follow up on the Growth Tier proposal from last week. Is there anything I can clarify or adjust to make this easier for your team to evaluate?",
            "sent_time": _date_str(11),
        },
        {
            "direction": "sent",
            "from": "james.okafor@dealiq.com",
            "subject": "TechStart — Growth Tier Proposal",
            "content": "Hi Priya, attaching the DealIQ Growth Tier proposal for 5 seats at $36K/year. This includes full API access, dedicated onboarding, and the reporting suite your team asked about. Happy to jump on a call to walk through it.",
            "sent_time": _date_str(19),
        },
        {
            "direction": "received",
            "from": "priya.sharma@techstart.io",
            "subject": "Re: DealIQ demo follow-up",
            "content": "James, thanks for the great demo last week! The team was impressed. We're currently evaluating two other vendors as well. I'll review your proposal and get back to you by end of next week.",
            "sent_time": _date_str(22),
        },
    ],

    "sim_003": [  # GlobalRetail — early stage, active
        {
            "direction": "received",
            "from": "rahul.mehta@globalretail.com",
            "subject": "Re: Discovery call confirmed",
            "content": "Maya, confirmed for March 5th at 2PM IST. I'll have our Head of Operations and the IT manager on the call as well. Could you send an agenda beforehand? We want to make sure we cover our specific reporting pain points.",
            "sent_time": _date_str(1),
        },
        {
            "direction": "sent",
            "from": "maya.patel@dealiq.com",
            "subject": "Discovery call confirmed — agenda inside",
            "content": "Hi Rahul, great — looking forward to meeting the team! I've attached a brief agenda. We'll focus on your current reporting workflow, the manual bottlenecks your team mentioned, and how DealIQ's analytics layer could automate the weekly reports. See you Thursday at 2PM IST.",
            "sent_time": _date_str(2),
        },
        {
            "direction": "received",
            "from": "rahul.mehta@globalretail.com",
            "subject": "Initial inquiry — DealIQ",
            "content": "Hi Maya, we're a 200-person retail chain looking to get better visibility into our sales pipeline. Currently we do everything manually in Excel — it takes our team 3 full days every week to produce the management report. A colleague recommended DealIQ. Can we set up a discovery call?",
            "sent_time": _date_str(6),
        },
    ],

    "sim_004": [  # FinanceFlow — zombie, 34 days silent
        {
            "direction": "sent",
            "from": "sarah.chen@dealiq.com",
            "subject": "FinanceFlow — checking in",
            "content": "Hi Amir, hope you're doing well. I wanted to check in on the Platform License proposal we discussed last month. Has there been any movement on your end? Happy to jump on a quick call.",
            "sent_time": _date_str(7),
        },
        {
            "direction": "sent",
            "from": "sarah.chen@dealiq.com",
            "subject": "Re: FinanceFlow Platform — next steps?",
            "content": "Amir, following up again on the proposal. We're coming up on the end of the quarter and I want to make sure we have the right conversation before then. Is there anything blocking progress internally? Happy to talk through any concerns.",
            "sent_time": _date_str(14),
        },
        {
            "direction": "sent",
            "from": "sarah.chen@dealiq.com",
            "subject": "FinanceFlow Platform License",
            "content": "Amir, I know you're busy. I wanted to revisit the pricing structure — I can offer a 15% discount if we can finalise by end of month. Let me know your thoughts.",
            "sent_time": _date_str(22),
        },
        {
            "direction": "received",
            "from": "amir.hassan@financeflow.com",
            "subject": "Re: Platform License discussion",
            "content": "Sarah, thanks for the revised numbers. We're still internally evaluating whether this is the right time to invest. Budget committee meets next month. I'll be in touch once we have more clarity.",
            "sent_time": _date_str(34),
        },
        {
            "direction": "sent",
            "from": "sarah.chen@dealiq.com",
            "subject": "FinanceFlow — Platform License discussion",
            "content": "Hi Amir, following up on our last conversation about the Platform License. We've made some adjustments to the pricing based on your feedback. Would love to reconnect and walk you through the updated proposal when you have 20 minutes.",
            "sent_time": _date_str(38),
        },
    ],

    "sim_005": [  # HealthTech — active, strong signals
        {
            "direction": "received",
            "from": "neha.joshi@healthtech.com",
            "subject": "Re: ROI calculator — really helpful",
            "content": "James, the ROI calculator you sent was exactly what our CFO needed. She was impressed — the payback period calculation really resonated. She's asked me to move forward with getting a formal proposal. Can you put together something for a 3-year enterprise agreement? We'd also want to explore the analytics add-on.",
            "sent_time": _date_str(1),
        },
        {
            "direction": "sent",
            "from": "james.okafor@dealiq.com",
            "subject": "ROI Calculator + Case Study — HealthTech",
            "content": "Hi Neha, as promised — attaching the ROI calculator pre-filled with your numbers (based on 12 reps, current manual process = 8hrs/week each). Also including the MedDevice Co case study — similar use case, they reduced reporting time by 78% in the first quarter. Happy to walk your CFO through the numbers directly if that would help.",
            "sent_time": _date_str(2),
        },
        {
            "direction": "received",
            "from": "neha.joshi@healthtech.com",
            "subject": "Quick question before our call tomorrow",
            "content": "James, quick one before tomorrow's call — does your platform integrate with Epic (our patient management system)? That's a potential blocker for our IT team. Also, are there any healthcare-specific compliance certifications (HIPAA)?",
            "sent_time": _date_str(4),
        },
    ],

    "sim_006": [  # LogiCo — stalled proposal, 11 days
        {
            "direction": "sent",
            "from": "maya.patel@dealiq.com",
            "subject": "Re: LogiCo Teams License",
            "content": "Hi Vikram, following up on the proposal I sent last week. Just wanted to make sure you received it and see if you had any questions. Happy to jump on a call to discuss.",
            "sent_time": _date_str(4),
        },
        {
            "direction": "sent",
            "from": "maya.patel@dealiq.com",
            "subject": "LogiCo — Teams License Proposal",
            "content": "Hi Vikram, attaching the updated Teams License proposal for 8 users at $18K/year. I've included the 10% volume discount we discussed. The proposal is valid for 30 days. Let me know if you want to schedule a review call.",
            "sent_time": _date_str(11),
        },
        {
            "direction": "received",
            "from": "vikram.singh@logico.com",
            "subject": "Re: DealIQ demo",
            "content": "Maya, the demo was solid. My main concern is price — we're a 50-person company and $18K feels steep. Is there a startup plan or can you do better on the per-seat cost? Also, how does pricing compare to your competitor Salesforce Starter?",
            "sent_time": _date_str(15),
        },
    ],
}


# Demo transcript and email for the mismatch feature
DEMO_TRANSCRIPT = """
[Call with Acme Corp - March 1, 2025 - 11:00 AM]

Sarah: Thanks for jumping on a call today, David. I wanted to walk you through the revised proposal.

David (Acme): Sure. Before we get into it, we've been looking at your competitor again. Their pricing is significantly lower.

Sarah: I understand. I want to be transparent — if you can commit to signing before March 31st, I can do 12% off the annual price. That brings it down to around $74,000 for the year.

David: That's more workable. What about the implementation timeline? Our IT team is asking.

Sarah: Absolutely. For enterprise accounts like yours, we can have you fully onboarded within three weeks of contract signature. Our implementation team is very efficient.

David: And the API integration with our internal CRM?

Sarah: Yes — that's included in the enterprise tier. Our team will handle the custom integration. Typically takes about five business days once onboarding starts.

David: Great. What are our next steps?

Sarah: I'll send a revised contract today reflecting the 12% discount valid until March 31st. And I'll include the implementation timeline in writing so your IT team has it confirmed. Let's schedule a final review call for March 7th at 2PM if that works?

David: Works for me. Looking forward to the contract.
"""

DEMO_EMAIL = """
Subject: Next Steps — Acme Corp Enterprise Agreement

Hi David,

Really enjoyed our conversation today. Thanks for taking the time to go through the details with me.

As discussed, I'm attaching the updated enterprise proposal for your review. I believe the platform is a strong fit for Acme's needs and I'm excited about the potential here.

Please do share this with your IT and finance teams for their input. I'm happy to set up calls with any of them if that would help move things along.

Looking forward to getting this across the line. Let me know if you have any questions.

Best,
Sarah
"""


# ── Smart Tracker demo transcript ─────────────────────────────────────────────
# Embeds all 6 default tracker concepts naturally in a single sales call.
# discount_pressure, competitor_mention, timeline_urgency, budget_objection,
# decision_maker_absent, next_steps_vague

# ── Coaching / Transcript Analysis demo transcript ────────────────────────────
# Two clearly labeled speakers. Designed to surface:
#   - Talk ratio issue: Rep ~62% (above 43% ideal)
#   - Monologue issue: opening pitch ~280s (above 76s ideal)
#   - Filler words: ~28 total in ~19 min rep speaking time (~1.5/min — below threshold, positive note)
#   - Question count: Rep 8 (below 11-14 ideal), Prospect 6
#   - Key moments: competitor mention, budget objection, pricing discussion, commitment
#   - Good pattern: strong discovery questions once rep slows down

COACHING_DEMO_TRANSCRIPT = """
[B2B SaaS Sales Call — DealIQ Platform Demo | March 6, 2026 | 10:00 AM IST]
[Rep: James Okafor, Account Executive — DealIQ]
[Prospect: Neha Joshi, VP of Sales — HealthScale Inc. | ~37 minutes]

Rep: Hi Neha, thanks so much for making time today, really appreciate it. Um, so I thought
I'd start by giving you a quick overview of what DealIQ does and then we can get into
your specific situation. Does that work?

Prospect: Sure, go ahead.

Rep: Great. So basically, DealIQ is a deal intelligence platform built specifically for
B2B SaaS revenue teams. What we do is connect directly to your CRM — whether that's
Salesforce, HubSpot, or Zoho — and we pull in all of your deal data and run it through
our AI health scoring engine. The engine looks at, uh, twelve different signals across
each deal — things like days in stage, last activity date, contact coverage, whether
discounts have been mentioned in emails, email sentiment from the buyer — and it scores
each deal from zero to a hundred. And the reason that's actually really powerful is
because you can, like, immediately see which deals are healthy, which are at risk, and
which ones are basically dead and just eating up your reps' attention.

We also have what we call the AI Sales Rep Clone, which is — right — it's essentially
a second brain for your reps. Before every call they get a personalized pre-call brief
that tells them exactly what to say, what risks to address, and what the buyer's likely
concerns are going to be. And then after the call, they can run our Narrative Check
feature, which basically compares what was said on the call versus what was written in
the follow-up email — you know — to make sure everything's consistent. We've found that
reps often miss committing things in writing that they verbally promised, and that creates
trust issues further down the funnel.

Then there's our Advance/Close/Kill recommendation engine — for every stalled deal, it
tells managers whether to push it forward, get a final decision, or kill it to clean
the pipeline. And actually we just launched Smart Trackers, which is concept-based call
analysis — kind of like what Giata does for trackers but uh more focused on deal-level
intelligence rather than just surface-level keyword matching. So the platform is pretty
comprehensive. I know that was a lot — does that give you a sense of the surface area?

Prospect: Yeah, it does. Um, what does pricing look like?

Rep: Right, so pricing is per seat and varies by tier. Basically for a team your size —
you said you have around twenty reps — you'd be on our Growth tier, which is around $850
per seat per year. So roughly $17,000 annually. We also have an Enterprise tier at $1,200
per seat that includes white-glove onboarding, dedicated success management, custom
integrations, and the full analytics suite. Most teams your size start on Growth and
upgrade after the first renewal once they see the ROI.

Prospect: Okay. We're currently using Giata for call analysis. It's pretty deeply embedded
in how we run coaching. Why would we add or replace that with you?

Rep: That's a fair question. So Giata is great for call recording and rep-level conversation
intelligence — coaching individual reps on what they said. What DealIQ does differently
is deal-level intelligence across your entire pipeline. Instead of looking at what happened
on a single call, we're looking at the health of every deal simultaneously and giving
managers a system-wide view of where the risk is. They're honestly not competing products.
A lot of our customers actually use both — Giata for rep coaching at the call level and
DealIQ for pipeline intelligence at the manager and CRO level. Does that distinction make
sense?

Prospect: Yeah, that does make sense. So DealIQ is more for me and our VP of Revenue
than for the reps day to day?

Rep: Exactly, though reps benefit from the pre-call briefs and email coaching. Can I ask —
what does your current pipeline review process look like? How are you assessing deal
health week to week?

Prospect: Honestly, it's pretty manual. Our RevOps team exports from Salesforce every
Monday and builds a spreadsheet. Takes about three hours and it's always a bit out of
date by the time we review it.

Rep: And what decisions does that spreadsheet drive when you do the review?

Prospect: We go through each rep's deals with the sales managers, flag the ones that look
stuck, and decide where to focus coaching. But we're heavily dependent on the rep's own
read on the deal, which is often overly optimistic.

Rep: Right, rep-reported probability versus actual deal health signals — that's exactly
the problem we solve. I'm curious, in your last pipeline review, how many deals would you
say the managers were genuinely uncertain about?

Prospect: Easily ten to fifteen. We have around eighty active deals at any given time.

Rep: That's a significant percentage. What's the cost when one of those goes wrong — say
a deal that looks healthy goes dark two weeks before quarter end?

Prospect: It's big. Last quarter we had three deals we were confident about that basically
fell apart in the last two weeks. Probably cost us around $350,000 in expected ARR.

Rep: That's a real number. That's the scenario DealIQ is built to catch sixty to ninety
days out rather than two weeks. Is that the kind of problem that would get budget
attention from your CRO if we could quantify it?

Prospect: Potentially. But I have to be honest — budget is tight. We just went through a
planning cycle where every discretionary line item got scrutinised. I'd need to build a
strong ROI case before taking this to Sarah, our CRO.

Rep: Makes sense. We have an ROI calculator and customer case studies that make that case
pretty compellingly. What would a strong ROI case need to show for Sarah specifically?

Prospect: She cares about pipeline predictability and quota attainment. If you can show
that teams using DealIQ have meaningfully better forecast accuracy, that would land well.

Rep: Perfect, we have exactly that data. Last question — if the ROI case lands and Sarah
is on board, what does your buying process look like from there?

Prospect: It would be me, Sarah, and our Head of RevOps, Priya. Legal reviews any contract.
Usually takes us about three weeks from decision to signature.

Rep: That's a clean process. What's your timeline — is there a planning deadline or
quarter-end driving urgency on your side?

Prospect: We'd want something in place before Q3 starts in July. So realistically we need
to be moving in the next six weeks.

Rep: Very doable. Here's what I'd like to do — I'll send you our ROI calculator pre-filled
with your numbers, plus two or three case studies from companies in a similar situation.
Then we schedule a thirty-minute call with you and Sarah to walk through the business
case together. Does that work?

Prospect: Yes, that works. Can you get the materials to me by end of this week?

Rep: Absolutely, I'll have everything in your inbox by Thursday. And for the Sarah call —
would the week of the 16th work?

Prospect: Let me check with her and come back to you. I'll email you by Friday.

Rep: Perfect. Thanks so much Neha, this was a genuinely useful conversation. Really
appreciate you being so candid about the pipeline situation.

Prospect: Thanks James, looking forward to the materials.

[End of call — 37:22]
"""



# ── Simulated Activity Feed (per deal) ────────────────────────────────────────

SIMULATED_ACTIVITIES = {
    "sim_001": {  # Acme Corp — active, Negotiation/Review
        "contacts": [
            {"name": "David Kim", "role": "VP Procurement", "email": "david.kim@acmecorp.com"},
            {"name": "Lisa Park", "role": "CTO", "email": "lisa.park@acmecorp.com"},
        ],
        "activities": [
            {
                "id": "a001_1", "type": "email", "direction": "inbound",
                "date": _days_ago(3),
                "subject": "Re: Revised Contract — Acme Enterprise",
                "participants": ["david.kim@acmecorp.com"],
                "content": "Legal has the redlines. Should have feedback by Friday.",
            },
            {
                "id": "a001_2", "type": "email", "direction": "outbound",
                "date": _days_ago(5),
                "subject": "Revised Contract — Acme Enterprise",
                "participants": ["david.kim@acmecorp.com"],
                "content": "Revised agreement attached with 12% early-commit discount.",
            },
            {
                "id": "a001_3", "type": "meeting", "direction": "internal",
                "date": _days_ago(7),
                "subject": "Contract review call",
                "participants": ["david.kim@acmecorp.com", "lisa.park@acmecorp.com"],
                "content": "Discussed contract terms and implementation timeline.",
                "duration_minutes": 45,
            },
            {
                "id": "a001_4", "type": "call", "direction": "outbound",
                "date": _days_ago(8),
                "subject": "Follow-up on legal review",
                "participants": ["david.kim@acmecorp.com"],
                "content": "Called to check in on legal review progress.",
                "duration_minutes": 15,
            },
            {
                "id": "a001_5", "type": "email", "direction": "inbound",
                "date": _days_ago(10),
                "subject": "Re: Contract timeline",
                "participants": ["david.kim@acmecorp.com"],
                "content": "Procurement needs 2-week review minimum. Can you hold pricing?",
            },
            {
                "id": "a001_6", "type": "meeting", "direction": "internal",
                "date": _days_ago(12),
                "subject": "Negotiation strategy sync",
                "participants": ["lisa.park@acmecorp.com"],
                "content": "CTO aligned on timeline and pricing structure.",
                "duration_minutes": 30,
            },
        ],
    },

    "sim_002": {  # TechStart — at risk, VP Engineering silent 19d
        "contacts": [
            {"name": "Priya Sharma", "role": "Head of Engineering", "email": "priya.sharma@techstart.io"},
            {"name": "Raj Patel", "role": "VP Engineering", "email": "raj.patel@techstart.io"},
        ],
        "activities": [
            {
                "id": "a002_1", "type": "email", "direction": "outbound",
                "date": _days_ago(5),
                "subject": "Following up — TechStart Growth Tier Proposal",
                "participants": ["priya.sharma@techstart.io"],
                "content": "Just checking in on the proposal I sent last week.",
            },
            {
                "id": "a002_2", "type": "email", "direction": "inbound",
                "date": _days_ago(22),
                "subject": "Re: DealIQ demo follow-up",
                "participants": ["priya.sharma@techstart.io"],
                "content": "Team was impressed. Evaluating two other vendors as well.",
            },
            {
                "id": "a002_3", "type": "meeting", "direction": "internal",
                "date": _days_ago(22),
                "subject": "Product demo",
                "participants": ["priya.sharma@techstart.io", "raj.patel@techstart.io"],
                "content": "Full demo delivered. Both contacts attended.",
                "duration_minutes": 60,
            },
        ],
    },

    "sim_003": {  # GlobalRetail — increasing trend, early stage
        "contacts": [
            {"name": "Rahul Mehta", "role": "Head of Operations", "email": "rahul.mehta@globalretail.com"},
            {"name": "Anita Singh", "role": "IT Manager", "email": "anita.singh@globalretail.com"},
        ],
        "activities": [
            {
                "id": "a003_1", "type": "email", "direction": "inbound",
                "date": _days_ago(1),
                "subject": "Re: Discovery call confirmed",
                "participants": ["rahul.mehta@globalretail.com"],
                "content": "Confirmed for March 5th. Will have IT manager on the call.",
            },
            {
                "id": "a003_2", "type": "email", "direction": "outbound",
                "date": _days_ago(2),
                "subject": "Discovery call confirmed — agenda inside",
                "participants": ["rahul.mehta@globalretail.com"],
                "content": "Looking forward to meeting the team.",
            },
            {
                "id": "a003_3", "type": "meeting", "direction": "outbound",
                "date": _days_ago(3),
                "subject": "Intro call",
                "participants": ["rahul.mehta@globalretail.com"],
                "content": "Initial discovery — covered pain points and use case.",
                "duration_minutes": 30,
            },
            {
                "id": "a003_4", "type": "call", "direction": "outbound",
                "date": _days_ago(5),
                "subject": "Qualification call",
                "participants": ["rahul.mehta@globalretail.com", "anita.singh@globalretail.com"],
                "content": "Both contacts joined. Strong interest expressed.",
                "duration_minutes": 20,
            },
            {
                "id": "a003_5", "type": "email", "direction": "inbound",
                "date": _days_ago(6),
                "subject": "Initial inquiry — DealIQ",
                "participants": ["rahul.mehta@globalretail.com"],
                "content": "Colleague recommended DealIQ. Can we set up a discovery call?",
            },
        ],
    },

    "sim_004": {  # FinanceFlow — zombie, 0 activities in 30d
        "contacts": [
            {"name": "Amir Hassan", "role": "CFO", "email": "amir.hassan@financeflow.com"},
            {"name": "Diane Torres", "role": "VP Finance", "email": "diane.torres@financeflow.com"},
        ],
        "activities": [
            {
                "id": "a004_1", "type": "email", "direction": "outbound",
                "date": _days_ago(34),
                "subject": "FinanceFlow — checking in",
                "participants": ["amir.hassan@financeflow.com"],
                "content": "Wanted to check in on the Platform License proposal.",
            },
            {
                "id": "a004_2", "type": "email", "direction": "inbound",
                "date": _days_ago(34),
                "subject": "Re: Platform License discussion",
                "participants": ["amir.hassan@financeflow.com"],
                "content": "Still internally evaluating. Budget committee meets next month.",
            },
            {
                "id": "a004_3", "type": "email", "direction": "outbound",
                "date": _days_ago(45),
                "subject": "FinanceFlow Platform License",
                "participants": ["amir.hassan@financeflow.com"],
                "content": "Can offer 15% discount if finalised by end of month.",
            },
        ],
    },

    "sim_005": {  # HealthTech — active, CFO engaged, high score
        "contacts": [
            {"name": "Neha Joshi", "role": "VP of Sales", "email": "neha.joshi@healthtech.com"},
            {"name": "Priya CFO", "role": "CFO", "email": "priya.cfo@healthtech.com"},
            {"name": "IT Head", "role": "Head of IT", "email": "it@healthtech.com"},
        ],
        "activities": [
            {
                "id": "a005_1", "type": "email", "direction": "inbound",
                "date": _days_ago(1),
                "subject": "Re: ROI calculator — really helpful",
                "participants": ["neha.joshi@healthtech.com"],
                "content": "CFO was impressed. Move forward with formal proposal.",
            },
            {
                "id": "a005_2", "type": "meeting", "direction": "outbound",
                "date": _days_ago(2),
                "subject": "CFO alignment call",
                "participants": ["neha.joshi@healthtech.com", "priya.cfo@healthtech.com"],
                "content": "Presented ROI model. CFO green-lit the proposal process.",
                "duration_minutes": 30,
            },
            {
                "id": "a005_3", "type": "email", "direction": "outbound",
                "date": _days_ago(2),
                "subject": "ROI Calculator + Case Study — HealthTech",
                "participants": ["neha.joshi@healthtech.com"],
                "content": "ROI calculator pre-filled with your numbers attached.",
            },
            {
                "id": "a005_4", "type": "email", "direction": "inbound",
                "date": _days_ago(4),
                "subject": "Quick question before our call tomorrow",
                "participants": ["neha.joshi@healthtech.com"],
                "content": "Does platform integrate with Epic? HIPAA compliance needed.",
            },
            {
                "id": "a005_5", "type": "call", "direction": "outbound",
                "date": _days_ago(5),
                "subject": "Technical deep-dive",
                "participants": ["it@healthtech.com", "neha.joshi@healthtech.com"],
                "content": "Covered Epic integration and HIPAA compliance.",
                "duration_minutes": 45,
            },
            {
                "id": "a005_6", "type": "meeting", "direction": "outbound",
                "date": _days_ago(7),
                "subject": "Product demo",
                "participants": ["neha.joshi@healthtech.com", "priya.cfo@healthtech.com"],
                "content": "Full platform demo for VP Sales and CFO.",
                "duration_minutes": 60,
            },
            {
                "id": "a005_7", "type": "email", "direction": "outbound",
                "date": _days_ago(9),
                "subject": "HealthTech — DealIQ proposal",
                "participants": ["neha.joshi@healthtech.com"],
                "content": "Initial proposal for 3-year enterprise agreement.",
            },
        ],
    },

    "sim_006": {  # LogiCo — stalled, 11d since two-way
        "contacts": [
            {"name": "Vikram Singh", "role": "Head of Operations", "email": "vikram.singh@logico.com"},
        ],
        "activities": [
            {
                "id": "a006_1", "type": "email", "direction": "outbound",
                "date": _days_ago(4),
                "subject": "Re: LogiCo Teams License",
                "participants": ["vikram.singh@logico.com"],
                "content": "Following up on the proposal I sent last week.",
            },
            {
                "id": "a006_2", "type": "email", "direction": "outbound",
                "date": _days_ago(11),
                "subject": "LogiCo — Teams License Proposal",
                "participants": ["vikram.singh@logico.com"],
                "content": "Updated Teams License proposal for 8 users at $18K/year.",
            },
            {
                "id": "a006_3", "type": "email", "direction": "inbound",
                "date": _days_ago(15),
                "subject": "Re: DealIQ demo",
                "participants": ["vikram.singh@logico.com"],
                "content": "Demo was solid. Main concern is price — $18K feels steep.",
            },
            {
                "id": "a006_4", "type": "meeting", "direction": "outbound",
                "date": _days_ago(18),
                "subject": "Product demo",
                "participants": ["vikram.singh@logico.com"],
                "content": "Demo delivered. Strong interest but price objection raised.",
                "duration_minutes": 45,
            },
        ],
    },
}


def get_demo_activity_data(deal_id: str) -> dict:
    """
    Returns an activity bundle matching get_all_activity_for_deal structure, using demo data.
    Used by the health endpoint and activity feed in demo mode.
    """
    now = datetime.now(timezone.utc)

    def _days_since(date_str: str) -> int:
        if not date_str:
            return 999
        try:
            dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return (now - dt).days
        except Exception:
            return 999

    # Get activity entry and emails
    activity_entry = SIMULATED_ACTIVITIES.get(deal_id, {"activities": [], "contacts": []})
    raw_activities = activity_entry.get("activities", [])
    contacts = activity_entry.get("contacts", [])

    # Split emails vs non-email activities
    email_items = [a for a in raw_activities if a.get("type") == "email"]
    non_email_items = [a for a in raw_activities if a.get("type") != "email"]

    # Also include SIMULATED_EMAILS for this deal (deduplicate by subject+direction)
    sim_emails_raw = SIMULATED_EMAILS.get(deal_id, [])
    # Merge: SIMULATED_EMAILS uses 'direction': 'received'/'sent'
    # Normalise direction to inbound/outbound
    merged_emails = list(email_items)  # start with activity-type emails
    seen_subjects: set = {(e.get("subject", ""), e.get("direction", "")) for e in email_items}
    for e in sim_emails_raw:
        direction = "inbound" if e.get("direction") == "received" else "outbound"
        key = (e.get("subject", ""), direction)
        if key not in seen_subjects:
            seen_subjects.add(key)
            merged_emails.append({
                "id": f"se_{deal_id}_{len(merged_emails)}",
                "type": "email",
                "direction": direction,
                "date": e.get("sent_time", ""),
                "subject": e.get("subject", ""),
                "participants": [e.get("from", "")],
                "content": e.get("content", ""),
                "sent_time": e.get("sent_time", ""),
            })

    # Sort emails newest first
    merged_emails.sort(key=lambda e: e.get("date") or e.get("sent_time", ""), reverse=True)

    # Summary stats
    def _is_inbound(e: dict) -> bool:
        d = (e.get("direction") or "").lower()
        return d in ("inbound", "received", "incoming")

    inbound_emails = [e for e in merged_emails if _is_inbound(e)]
    outbound_emails = [e for e in merged_emails if not _is_inbound(e)]

    last_email_date = merged_emails[0].get("date") or merged_emails[0].get("sent_time") if merged_emails else None
    last_inbound_date = (inbound_emails[0].get("date") or inbound_emails[0].get("sent_time")) if inbound_emails else None

    # Most recent non-email activity date
    act_dates = [
        a.get("date", "") for a in non_email_items if a.get("date")
    ]
    last_activity_date = max(act_dates) if act_dates else None

    days_since_inbound = _days_since(last_inbound_date) if last_inbound_date else 999
    days_since_any = _days_since(last_email_date or last_activity_date)

    return {
        "deal_id": deal_id,
        "contacts": contacts,
        "emails": merged_emails,
        "activities": non_email_items,
        "notes": [],
        "summary": {
            "total_emails": len(merged_emails),
            "total_activities": len(non_email_items),
            "total_contacts": len(contacts),
            "emails_inbound": len(inbound_emails),
            "emails_outbound": len(outbound_emails),
            "last_email_date": last_email_date,
            "last_inbound_email_date": last_inbound_date,
            "last_activity_date": last_activity_date,
            "days_since_last_inbound": days_since_inbound,
            "days_since_any_activity": days_since_any,
        },
    }


# ── Demo: Today's Actions (for /actions/today in DEMO_MODE) ──────────────────

DEMO_TODAY_ACTIONS = [
    {
        "id": "act_001",
        "type": "overdue_close",
        "deal_id": "sim_004",
        "deal_name": "FinanceFlow — Platform License",
        "company": "FinanceFlow Corp",
        "amount": 120000,
        "stage": "Negotiation/Review",
        "urgency_score": 95,
        "context": "Close date passed 5 days ago. No activity for 34 days. Deal at risk of being lost.",
        "suggested_action": "Send a direct re-engagement with a revised close timeline. Ask for a decision by EOW.",
        "draft": "Hi Amir, I wanted to reach out directly — I noticed we've been quiet for a few weeks and the close date has passed. I understand budget timelines shift. I'd like to propose a brief 15-minute call this week to understand where things stand and whether there's a path forward that works for your team. Happy to adjust the terms if that helps. Would Thursday or Friday work?",
    },
    {
        "id": "act_002",
        "type": "silent_deal",
        "deal_id": "sim_002",
        "deal_name": "TechStart Inc — Growth Tier",
        "company": "TechStart Inc",
        "amount": 36000,
        "stage": "Proposal/Price Quote",
        "urgency_score": 80,
        "context": "No response in 19 days. You've sent 3 follow-ups. Prospect evaluated 2 competitors.",
        "suggested_action": "Change the approach — stop following up on the proposal. Reframe around their business outcome.",
        "draft": "Hi Priya, I'll keep this brief — I know you've had the proposal for a while. Rather than ask if you've reviewed it, I wanted to share one thing: one of our customers in a similar stage-count situation saw a 3-week reduction in their forecast cycle within 30 days of going live. Worth 20 minutes if pipeline predictability is still on your radar. Completely understand if the timing isn't right.",
    },
    {
        "id": "act_003",
        "type": "missed_followup",
        "deal_id": "sim_001",
        "deal_name": "Acme Corp — Enterprise Plan",
        "company": "Acme Corporation",
        "amount": 84000,
        "stage": "Negotiation/Review",
        "urgency_score": 75,
        "context": "You committed to sending revised contract Thursday March 6. Pricing deadline is April 7.",
        "suggested_action": "Send the revised contract with DPA addendum. Reference the April 7 pricing deadline.",
        "draft": "Hi David, as promised — attaching the revised contract with the 12% early-commit discount locked in until April 7th. I've also included a Data Processing Agreement (DPA) as a standalone addendum addressing the data residency question from your CTO. All data is processed and stored in India by default, with EU/US region options available on Enterprise. Would it help to set up a quick call with our legal team and yours to clear the remaining redlines? We can usually turn those around in 48 hours.",
    },
    {
        "id": "act_004",
        "type": "no_next_step",
        "deal_id": "sim_006",
        "deal_name": "LogiCo — Teams License",
        "company": "LogiCo Inc",
        "amount": 18000,
        "stage": "Proposal/Price Quote",
        "urgency_score": 60,
        "context": "Proposal sent 11 days ago. Prospect raised price objection. No next step defined.",
        "suggested_action": "Acknowledge the price concern. Offer a revised number for annual commit and propose a call with the CFO.",
        "draft": "Hi Vikram, I've been thinking about your feedback on the pricing — you're right that $18K is a stretch for a 50-person team. I can offer $14,400/year (20% off) for an annual commitment signed before March 31st. That's our best startup rate and would give you the full platform. Would it make sense to jump on a quick call with you and Priya to walk through the ROI numbers? I can usually make that case in 15 minutes. Let me know what works.",
    },
    {
        "id": "act_005",
        "type": "opportunity",
        "deal_id": "sim_005",
        "deal_name": "HealthTech Solutions — Annual",
        "company": "HealthTech Solutions",
        "amount": 28000,
        "stage": "Value Proposition",
        "urgency_score": 50,
        "context": "CFO engaged and requested formal proposal. Buyer asked about Epic integration and HIPAA. High-momentum deal.",
        "suggested_action": "Send 3-year enterprise proposal with HIPAA and Epic integration details before end of week.",
        "draft": "Hi Neha, following up on our conversation — excited to put together the 3-year enterprise proposal for you. On your two questions: (1) Epic integration — yes, we support Epic via HL7 FHIR API. Our team handles the setup end-to-end, typically 5 business days post-onboarding. (2) HIPAA — we are HIPAA compliant and will include a Business Associate Agreement (BAA) with the contract. I'll have the full proposal with 3-year pricing and ROI projections in your inbox by Thursday. Would week of the 16th work for the Sarah call?",
    },
    {
        "id": "act_006",
        "type": "silent_deal",
        "deal_id": "sim_003",
        "deal_name": "GlobalRetail — Starter Pack",
        "company": "GlobalRetail Ltd",
        "amount": 12000,
        "stage": "Needs Analysis",
        "urgency_score": 30,
        "context": "Discovery call scheduled for today. Two stakeholders confirmed. Strong early signals.",
        "suggested_action": "Prep call agenda. Focus on manual reporting pain and IT integration concerns.",
        "draft": "",
    },
]


# ── Demo: Pending CRM Updates (for /meeting/pending-updates in DEMO_MODE) ─────

DEMO_PENDING_UPDATES = [
    {
        "id": "upd_001",
        "deal_id": "sim_001",
        "deal_name": "Acme Corp — Enterprise Plan",
        "field_name": "Stage",
        "old_value": "Negotiation/Review",
        "new_value": "Contract Sent",
        "confidence": "medium",
        "source": "meeting",
        "created_at": _days_ago(1),
        "context": "AI inferred from meeting notes: contract was sent. Confidence medium — no explicit stage change stated.",
    },
    {
        "id": "upd_002",
        "deal_id": "sim_001",
        "deal_name": "Acme Corp — Enterprise Plan",
        "field_name": "Next_Step",
        "old_value": "Send revised contract by Thursday, March 6",
        "new_value": "Await legal review feedback by March 15. Follow up if no response.",
        "confidence": "medium",
        "source": "meeting",
        "created_at": _days_ago(1),
        "context": "AI extracted from post-meeting notes. David mentioned legal review underway.",
    },
]


# ── Demo: Meeting History (for /meeting/history/{deal_id} in DEMO_MODE) ───────

DEMO_MEETING_HISTORY = {
    "sim_001": [
        {
            "id": "mtg_001",
            "sentiment": "ok",
            "ai_summary": "Contract review call with David Kim (VP Procurement) and Lisa Park (CTO). Legal team has raised redlines around liability cap and auto-renewal. Procurement requires 2-week minimum review period. Pricing deadline extended to April 7th.",
            "action_items": [
                "Send revised contract with DPA addendum",
                "Offer joint call with legal teams to accelerate review",
                "Confirm April 7 as hard pricing deadline in writing",
            ],
            "topics_confirmed": ["Contract redlines", "Pricing deadline", "Data residency", "DPA requirement"],
            "duration_minutes": 45,
            "created_at": _days_ago(7),
        }
    ],
    "sim_005": [
        {
            "id": "mtg_002",
            "sentiment": "great",
            "ai_summary": "CFO alignment call — Priya (CFO) and Neha (VP Sales) both attended. ROI model well received. Payback period resonated. Buyer requested formal 3-year enterprise proposal and confirmed she would champion with CRO Sarah. Epic + HIPAA are the two remaining blockers.",
            "action_items": [
                "Send 3-year enterprise proposal by Thursday",
                "Include HIPAA BAA and Epic integration spec sheet",
                "Schedule Sarah (CRO) call for week of March 16",
            ],
            "topics_confirmed": ["ROI model", "3-year pricing", "Epic integration", "HIPAA compliance"],
            "duration_minutes": 30,
            "created_at": _days_ago(2),
        }
    ],
}


TRACKER_DEMO_TRANSCRIPT = """
[Discovery & Proposal Call — LogiCo Supply Chain | March 4, 2026 | 10:00 AM IST]
[Rep: Maya Patel (DealIQ) | Buyer: Vikram Singh, Head of Operations | 38 minutes]

[00:01:12]
Maya: Vikram, thanks for joining. Before I get into the updated numbers, how are you feeling
about things since the demo last week?

Vikram: Honestly, pretty good. The demo covered most of what we need. My main hesitation
is the price point. We're a 50-person logistics company — $18K a year is a stretch.
That's a significant chunk of our tooling budget for the year.

[00:03:45]
Maya: I hear you. Can I ask — what budget were you expecting to spend on pipeline tooling?

Vikram: We had set aside maybe $10–12K. So we're already above that range. I'll need to
go back to our CFO, Priya, to see if she can free up additional budget. She wasn't on
this call unfortunately — I'd need her sign-off before we can commit to anything at this
level. She's very conservative with new SaaS spend.

[00:06:21]
Maya: That makes sense. Is Priya someone we could include on a follow-up call?

Vikram: Potentially, yes. Though her calendar is extremely tight — she has the board review
on March 15th and is basically unavailable until after that. The board is asking for a
cost reduction roadmap, which makes this a harder conversation right now. If we're going
to do anything, it probably needs to happen before that board meeting or wait until April.

[00:09:55]
Maya: Understood. On the pricing side — is that your best price, or is there any flexibility?
We've seen similar tools like Clari and Salesforce Starter offer lower per-seat costs for
companies our size. I'm not trying to be difficult, I just want to make sure I'm comparing
apples to apples before I take this to Priya.

[00:11:03]
Maya: That's a fair question. I can look at what we can do for a 12-month commit — we do
have some flexibility for annual contracts signed before quarter-end. I'd need to check
with my team, but there may be room.

Vikram: That would help a lot. Also, on the competitor question — we've done a trial with
HubSpot Sales Hub. Their deal tracking isn't as deep as yours, but their price is
significantly lower. If we go with you, I need to be able to justify the premium clearly.

[00:14:40]
Maya: Absolutely — I'll put together a side-by-side comparison. One thing worth noting is
that our pipeline health scoring isn't something HubSpot offers at this tier.

Vikram: That's true. Look, I think there's a deal here. But I genuinely need two things:
a better number to take to Priya, and something that shows ROI within six months.
Our current quarter ends March 31st and if we're going to get budget approved, it has
to happen before then.

[00:27:15]
Maya: Totally. I'll work on a revised proposal and ROI case. Let me ask — if the numbers
work out, what would the sign-off process look like on your side?

Vikram: It would go through Priya for budget sign-off. And then our legal team would need
to review the contract — that usually takes a week. I wouldn't be making the final call
on this one.

[00:35:50]
Maya: Makes sense. I'll get that to you soon and we'll figure out next steps from there.
Thanks again, Vikram — really appreciate the time.

Vikram: Sure, thanks Maya. Talk soon.

[End of call — 38:04]
"""

# ── Demo Timeline Data (Zoho v9 Timelines API shape) ──────────────────────────
# Used when demo mode is active or when deal_id.startswith("sim_")
# Mirrors the real Zoho v9 /Deals/{id}/timelines response structure.

def _ts(days_ago_val: int, hour: int = 10) -> str:
    from datetime import datetime, timedelta, timezone
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago_val)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat()


DEMO_TIMELINE = {
    "timeline": [
        # ── Stage: Qualification → Demo Scheduled (forward) ──────────────
        {
            "action": "updated",
            "audited_time": _ts(38),
            "source": "crm_ui",
            "done_by": {"name": "Sarah Chen", "profile": {"name": "Sales Rep"}, "type__s": "user"},
            "record": {"name": "Acme Corp — Enterprise Plan", "module": {"api_name": "Deals"}},
            "field_history": [
                {
                    "api_name": "Stage",
                    "field_label": "Stage",
                    "data_type": "picklist",
                    "_value": {"old": "Qualification", "new": "Demo Scheduled"},
                    "actual_value": {"old": "Qualification", "new": "Demo Scheduled"},
                    "enable_colour_code": True,
                    "pick_list_values": [
                        {"display_value": "Qualification",   "actual_value": "Qualification",   "colour_code": "#5c6bc0", "sequence_number": 1},
                        {"display_value": "Demo Scheduled",  "actual_value": "Demo Scheduled",  "colour_code": "#26a69a", "sequence_number": 2},
                        {"display_value": "Demo Done",       "actual_value": "Demo Done",       "colour_code": "#ffa726", "sequence_number": 3},
                        {"display_value": "Proposal/Price Quote", "actual_value": "Proposal/Price Quote", "colour_code": "#ef5350", "sequence_number": 4},
                        {"display_value": "Negotiation/Review",   "actual_value": "Negotiation/Review",   "colour_code": "#ab47bc", "sequence_number": 5},
                    ],
                }
            ],
        },
        # ── Email sent (human) ───────────────────────────────────────────
        {
            "action": "sent",
            "audited_time": _ts(32),
            "source": "crm_ui",
            "done_by": {"name": "Sarah Chen", "profile": {"name": "Sales Rep"}, "type__s": "user"},
            "record": {"name": "Demo confirmation + agenda — Acme Corp", "module": {"api_name": "Emails"}},
            "field_history": [],
        },
        # ── Stage: Demo Scheduled → Demo Done (forward) ──────────────────
        {
            "action": "updated",
            "audited_time": _ts(25),
            "source": "crm_ui",
            "done_by": {"name": "Sarah Chen", "profile": {"name": "Sales Rep"}, "type__s": "user"},
            "record": {"name": "Acme Corp — Enterprise Plan", "module": {"api_name": "Deals"}},
            "field_history": [
                {
                    "api_name": "Stage",
                    "field_label": "Stage",
                    "data_type": "picklist",
                    "_value": {"old": "Demo Scheduled", "new": "Demo Done"},
                    "actual_value": {"old": "Demo Scheduled", "new": "Demo Done"},
                    "enable_colour_code": True,
                    "pick_list_values": [
                        {"display_value": "Qualification",   "actual_value": "Qualification",   "colour_code": "#5c6bc0", "sequence_number": 1},
                        {"display_value": "Demo Scheduled",  "actual_value": "Demo Scheduled",  "colour_code": "#26a69a", "sequence_number": 2},
                        {"display_value": "Demo Done",       "actual_value": "Demo Done",       "colour_code": "#ffa726", "sequence_number": 3},
                        {"display_value": "Proposal/Price Quote", "actual_value": "Proposal/Price Quote", "colour_code": "#ef5350", "sequence_number": 4},
                        {"display_value": "Negotiation/Review",   "actual_value": "Negotiation/Review",   "colour_code": "#ab47bc", "sequence_number": 5},
                    ],
                }
            ],
        },
        # ── Revenue updated (up) ─────────────────────────────────────────
        {
            "action": "updated",
            "audited_time": _ts(20),
            "source": "crm_ui",
            "done_by": {"name": "James Okafor", "profile": {"name": "Sales Manager"}, "type__s": "user"},
            "record": {"name": "Acme Corp — Enterprise Plan", "module": {"api_name": "Deals"}},
            "field_history": [
                {
                    "api_name": "Expected_Revenue",
                    "field_label": "Expected Revenue",
                    "data_type": "currency",
                    "_value": {"old": "$60,000", "new": "$84,000"},
                    "actual_value": {"old": "60000", "new": "84000"},
                }
            ],
        },
        # ── Workflow automation email ─────────────────────────────────────
        {
            "action": "email_notification_sent",
            "audited_time": _ts(18),
            "source": "workflow",
            "done_by": {"name": "Zoho Workflow", "profile": {"name": "System"}, "type__s": "admin"},
            "record": {"name": "Proposal follow-up (auto)", "module": {"api_name": "Emails"}},
            "field_history": [],
        },
        # ── Task added ───────────────────────────────────────────────────
        {
            "action": "added",
            "audited_time": _ts(14),
            "source": "crm_ui",
            "done_by": {"name": "Sarah Chen", "profile": {"name": "Sales Rep"}, "type__s": "user"},
            "record": {"name": "Follow up on contract review", "module": {"api_name": "Tasks"}},
            "field_history": [],
        },
        # ── Stage: Demo Done → Proposal/Price Quote (forward) ────────────
        {
            "action": "updated",
            "audited_time": _ts(12),
            "source": "crm_ui",
            "done_by": {"name": "Sarah Chen", "profile": {"name": "Sales Rep"}, "type__s": "user"},
            "record": {"name": "Acme Corp — Enterprise Plan", "module": {"api_name": "Deals"}},
            "field_history": [
                {
                    "api_name": "Stage",
                    "field_label": "Stage",
                    "data_type": "picklist",
                    "_value": {"old": "Demo Done", "new": "Proposal/Price Quote"},
                    "actual_value": {"old": "Demo Done", "new": "Proposal/Price Quote"},
                    "enable_colour_code": True,
                    "pick_list_values": [
                        {"display_value": "Qualification",   "actual_value": "Qualification",   "colour_code": "#5c6bc0", "sequence_number": 1},
                        {"display_value": "Demo Scheduled",  "actual_value": "Demo Scheduled",  "colour_code": "#26a69a", "sequence_number": 2},
                        {"display_value": "Demo Done",       "actual_value": "Demo Done",       "colour_code": "#ffa726", "sequence_number": 3},
                        {"display_value": "Proposal/Price Quote", "actual_value": "Proposal/Price Quote", "colour_code": "#ef5350", "sequence_number": 4},
                        {"display_value": "Negotiation/Review",   "actual_value": "Negotiation/Review",   "colour_code": "#ab47bc", "sequence_number": 5},
                    ],
                }
            ],
        },
        # ── Email sent (human, most recent) ──────────────────────────────
        {
            "action": "sent",
            "audited_time": _ts(3),
            "source": "crm_ui",
            "done_by": {"name": "Sarah Chen", "profile": {"name": "Sales Rep"}, "type__s": "user"},
            "record": {"name": "Revised contract for Acme Corp", "module": {"api_name": "Emails"}},
            "field_history": [],
        },
    ]
}


def get_demo_timeline(deal_id: str) -> dict:
    """Return demo timeline data for any simulated deal."""
    return DEMO_TIMELINE
