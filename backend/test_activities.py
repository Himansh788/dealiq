"""
Smoke test for demo activity data — run from backend/ with:
  python test_activities.py
"""
from services.demo_data import get_demo_activity_data

for deal_id in ["sim_001", "sim_002", "sim_004", "sim_999"]:
    data = get_demo_activity_data(deal_id)
    s = data["summary"]
    print(
        f"{deal_id}: emails={s['total_emails']} in={s['emails_inbound']} "
        f"out={s['emails_outbound']} activities={s['total_activities']} "
        f"contacts={s['total_contacts']} last_inbound={s['days_since_last_inbound']}d "
        f"any_activity={s['days_since_any_activity']}d"
    )

print("\nDemo activity data OK")
