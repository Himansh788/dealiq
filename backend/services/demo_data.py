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
