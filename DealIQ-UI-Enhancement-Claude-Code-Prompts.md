Build an "Activity Intelligence" layer that enriches deal data with automatic activity analysis from CRM data.

1. ACTIVITY CAPTURE from CRM:
   When syncing deals from Zoho, also pull:
   - All emails associated with the deal/contacts (using CRM email integration data)
   - All meetings/events tied to the opportunity
   - All calls logged against the opportunity
   - All tasks (completed and pending)
   - All notes
   
   For Zoho: Use Activities module linked to the Deal

2. ACTIVITY SCORE per deal:
   Calculate an "Engagement Velocity" score based on:
   - Total touchpoints in last 14 days
   - Number of unique contacts engaged (multi-threading score)
   - Response rate (emails sent vs replies received)
   - Meeting frequency (meetings per week trending up or down)
   - Days since last 2-way interaction (not just rep sending emails into void)
   
   Benchmark against won deals:
   "Won deals at this stage average 3.2 meetings/week. This deal has 0.8."

3. ACTIVITY TIMELINE in Deal Detail Panel:
   Add a new section "Activity Feed" showing:
   - Visual timeline of all touchpoints (emails, calls, meetings)
   - Color-coded by type: 📧 blue (email), 📞 green (call), 📅 purple (meeting)
   - Each activity shows: date, type, participants, brief summary
   - Gap detection: Highlight periods of silence >7 days with red warning bands
   - Show "Engagement Trend" sparkline: is activity increasing or decreasing?

4. "GHOST STAKEHOLDER" DETECTION:
   - Track which contacts were active at each deal stage
   - If a contact who was active in Discovery goes silent in Proposal: flag as "Ghost"
   - Alert: "Sarah Chen (VP Engineering) hasn't been in any emails for 18 days. She was active during the technical evaluation."
   - This feeds into the existing Stakeholder Engagement Map

5. REP ACTIVITY BENCHMARKING (Manager View):
   On the dashboard, add a "Team Activity" card showing:
   - Activities per rep per day (emails, calls, meetings)
   - Compare against team average
   - Flag reps with declining activity trends
   - "Activity vs Results" correlation: show if more activity = more wins

Integrate this into the existing health score calculation. 
Activity Velocity should be one of the 12 health signals (replace or supplement an existing signal).