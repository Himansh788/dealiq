# DealIQ — Revenue Without Guesswork

> AI-powered deal intelligence platform for B2B SaaS revenue teams
> Full-stack monorepo: React 18 frontend + Python FastAPI backend

---

## What It Does

DealIQ sits between your CRM and your communication stack and answers the question CRMs can't: **is this deal actually progressing, or quietly dying?**

### Core Features

| Feature | Description |
|---------|-------------|
| **Deal Health Score** | 9-signal, 0–100 score per deal (recency, velocity, stakeholder depth, engagement, discount pressure, and more) |
| **Activity Intelligence** | Engagement velocity scoring, ghost stakeholder detection, team activity summary |
| **AI Sales Rep** | Next Best Action → approve → draft email → approve → send. Objection handler included. |
| **Pre-Call Intelligence Brief** | AI-generated call prep: key risks, stakeholder map, suggested questions |
| **Narrative Mismatch Checker** | Compares call transcripts to follow-up emails and flags promise/commitment gaps |
| **Live Email Coach** | Real-time coaching as the rep types an email (debounced, keystroke-driven) |
| **Ask DealIQ** | 4-tab AI Q&A panel: open Q&A chat, MEDDIC analysis, Deal Brief, Follow-up Email generator |
| **Context Engine** | Rules-based rep style analyser + AI transcript pre-processing for all email generation |
| **Deal Autopsy** | AI post-mortem triggered when a deal is killed |
| **Advance / Close / Kill** | Decision-forcing surface for stalled deals with supporting signal evidence |
| **AI Forecast** | Pipeline narrative + at-risk deal rescue recommendations + rep coaching |
| **Smart Trackers** | Buying signal and risk signal detection |
| **Call Coaching** | Real-time coaching panel |
| **Alerts Digest** | Prioritised deal alerts across the pipeline |

---

## Architecture

```
React 18 + TypeScript + Shadcn UI (Vite)
           ↓ REST API
FastAPI (Python) — localhost:8000
     ↓                    ↓
CRM Adapter Layer      Groq API (LLaMA models)
  ├── Zoho CRM         llama-3.3-70b-versatile (quality)
  └── Demo Mode        llama-3.1-8b-instant (speed)
```

### CRM Adapter Layer

The backend uses an abstraction layer so switching CRM providers requires no route changes:

```
CRMFactory.get_adapter(token)
  ├── ZohoAdapter   → real Zoho CRM API (OAuth2)
  └── DemoAdapter   → SIMULATED_DEALS in-memory data
```

---

## Quick Start (Local)

### Step 1 — Clone

```bash
git clone https://github.com/himansh788/dealiq.git
cd dealiq
```

### Step 2 — Backend

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Fill in your keys (see Key Setup below)
uvicorn main:app --reload
```

Backend: `http://localhost:8000`
Swagger docs: `http://localhost:8000/docs`

### Step 3 — Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

### Step 4 — Test without any API keys (Demo Mode)

```bash
# Get a demo session token
curl http://localhost:8000/auth/demo-session

# Use DEMO_MODE as the bearer token for all API calls
# No Zoho account or Groq key required — all data is simulated
```

---

## Key Setup

### 1. Groq API Key (AI inference)

1. Sign up at https://console.groq.com
2. Create an API key
3. Add to `.env`: `GROQ_API_KEY=gsk_...`

### 2. Zoho CRM OAuth2 (optional — demo mode works without it)

> India users: use `zoho.in` domains. Everyone else: `zoho.com`

1. Go to **https://api-console.zoho.in** (or `.com`)
2. Add Client → Server-based Applications
3. Fill in:
   - Homepage URL: `http://localhost:5173`
   - Redirect URI: `http://localhost:8000/auth/callback`
4. Copy Client ID + Secret to `.env`

### .env reference

```env
GROQ_API_KEY=gsk_...

ZOHO_CLIENT_ID=...
ZOHO_CLIENT_SECRET=...
ZOHO_REDIRECT_URI=http://localhost:8000/auth/callback
ZOHO_REGION=in            # or com

FRONTEND_URL=http://localhost:5173

# Optional — only if using DB-backed features (transcript storage, email extractions)
DATABASE_URL=postgresql+asyncpg://...
```

---

## Project Structure

```
dealiq/
├── backend/
│   ├── main.py                          # FastAPI app — registers all routers
│   ├── routers/
│   │   ├── auth.py                      # Zoho OAuth2 + demo session
│   │   ├── deals.py                     # List deals, metrics
│   │   ├── health.py                    # Deal health signals
│   │   ├── analysis.py                  # Mismatch, email-coach, autopsy, ACK, discount
│   │   ├── ai_rep.py                    # NBA, draft-email, objection, call-brief
│   │   ├── activities.py                # Activity feed + team summary
│   │   ├── ask.py                       # Ask DealIQ (auth-required, 7 routes)
│   │   ├── ask_demo.py                  # Ask DealIQ (demo mode, 5 routes)
│   │   ├── forecast.py                  # AI pipeline forecast
│   │   ├── alerts.py                    # Alerts digest
│   │   ├── signals.py                   # Buying signal detection
│   │   ├── trackers.py                  # Smart trackers
│   │   └── coaching.py                  # Call coaching
│   ├── services/
│   │   ├── context_engine.py            # RepStyle + DealContext, rules-based analyser, transcript pre-processing
│   │   ├── email_generator.py           # 2-pass email generation with commitment coverage check
│   │   ├── ai_rep.py                    # NBA, objection, call-brief logic
│   │   ├── ask_dealiq_service.py        # Ask Q&A engine (deal Q&A, MEDDIC, brief, follow-up email)
│   │   ├── ask_dealiq_prompts.py        # All Ask DealIQ AI prompts + PRESET_QUESTIONS
│   │   ├── ask_demo_data.py             # Demo transcript/emails for Ask feature
│   │   ├── ai_router_ask.py             # Groq wrapper for Ask tasks
│   │   ├── activity_intelligence.py     # Engagement velocity scoring + ghost detection
│   │   ├── health_scorer.py             # 9-signal health scorer (score_deal_with_activities)
│   │   ├── deal_autopsy.py              # Post-mortem generation
│   │   ├── email_coach.py               # Real-time email coaching
│   │   ├── claude_client.py             # Mismatch + discount + insights
│   │   ├── deal_timeline.py             # Deal event timeline
│   │   ├── smart_tracker.py             # Smart tracker logic
│   │   ├── signal_detector.py           # Buying/risk signal detection
│   │   ├── transcript_analyzer.py       # Transcript analysis
│   │   ├── email_analyzer.py            # Email thread analysis
│   │   ├── alerts_digest.py             # Alerts digest generation
│   │   ├── ai_forecast_narrative.py     # Forecast narrative generation
│   │   ├── crm_adapter.py               # CRM adapter base interface
│   │   ├── crm_factory.py               # CRM adapter factory (Zoho or Demo)
│   │   ├── crm_errors.py                # Shared CRM error types
│   │   ├── zoho_adapter.py              # Zoho CRM adapter implementation
│   │   ├── demo_adapter.py              # Demo mode adapter implementation
│   │   ├── zoho_client.py               # Raw Zoho API client
│   │   └── demo_data.py                 # SIMULATED_DEALS + SIMULATED_ACTIVITIES + SIMULATED_EMAILS
│   ├── models/
│   │   ├── schemas.py                   # Core Pydantic schemas
│   │   ├── activity_schemas.py          # Activity feed schemas
│   │   ├── coaching_schemas.py          # Coaching schemas
│   │   └── tracker_schemas.py           # Tracker schemas
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Login.tsx                # Zoho OAuth + demo login
│   │   │   ├── Dashboard.tsx            # Pipeline table + filters + deal panel
│   │   │   ├── Home.tsx                 # AI to-dos: greeting + metrics + priority deals
│   │   │   ├── ForecastPage.tsx         # AI forecast + rescue opps + rep coaching
│   │   │   ├── AskDealIQPage.tsx        # Full Ask DealIQ page with deal selector
│   │   │   ├── AlertsPage.tsx           # Alerts digest
│   │   │   ├── TrackersPage.tsx         # Smart trackers
│   │   │   └── TrendsPage.tsx           # (coming soon)
│   │   ├── components/
│   │   │   ├── DealDetailPanel.tsx      # Main slide-out panel (10 accordion sections)
│   │   │   ├── NavBar.tsx               # Shared top nav (alerts bell, Cmd+K, user)
│   │   │   ├── CommandPalette.tsx       # Cmd+K search across deals + navigation
│   │   │   ├── PipelineQABar.tsx        # Pipeline-level Q&A bar
│   │   │   ├── layout/
│   │   │   │   ├── AppLayout.tsx        # Root layout: Sidebar + main content
│   │   │   │   └── Sidebar.tsx          # 60px icon-only sidebar nav
│   │   │   ├── deal/
│   │   │   │   ├── DealTimeline.tsx     # Deal event timeline
│   │   │   │   ├── HealthBreakdown.tsx  # 9-signal health display
│   │   │   │   ├── ActivityFeedPanel.tsx # Engagement velocity + ghost alerts
│   │   │   │   ├── AIRepPanel.tsx       # NBA → approve → email draft → approve
│   │   │   │   ├── CallBriefPanel.tsx   # Pre-call intelligence brief
│   │   │   │   ├── MismatchChecker.tsx  # Narrative check + live email coach
│   │   │   │   ├── TrackerPanel.tsx     # Smart trackers
│   │   │   │   ├── AckSection.tsx       # Advance/Close/Kill + autopsy on kill
│   │   │   │   ├── AutopsyPanel.tsx     # Deal post-mortem
│   │   │   │   ├── AskDealIQPanel.tsx   # 4-tab Ask panel
│   │   │   │   └── CoachingPanel.tsx    # Call coaching
│   │   │   └── email/
│   │   │       └── EmailComposer.tsx    # AI email composer dialog
│   │   └── lib/
│   │       └── api.ts                   # All API calls (typed)
│   └── package.json
├── README.md
└── .gitignore
```

---

## API Reference

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/auth/login` | Get Zoho OAuth2 URL |
| GET | `/auth/callback` | OAuth2 callback handler |
| GET | `/auth/demo-session` | Get demo session token (no Zoho needed) |

### Deals
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/deals/` | List all deals |
| GET | `/deals/metrics` | Pipeline summary metrics |
| GET | `/deals/{id}/health` | 9-signal health breakdown |
| GET | `/deals/{id}/timeline` | Deal event timeline |

### AI Sales Rep
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ai-rep/nba` | Generate Next Best Action |
| POST | `/ai-rep/approve-action` | Log action approval |
| POST | `/ai-rep/draft-email` | Generate email draft |
| POST | `/ai-rep/approve-email` | Log email approval |
| POST | `/ai-rep/handle-objection` | Generate objection response |
| POST | `/ai-rep/call-brief` | Generate pre-call intelligence brief |

### Analysis
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/analysis/mismatch` | Transcript vs email mismatch check |
| POST | `/analysis/email-coach` | Real-time email coaching |
| POST | `/analysis/autopsy` | Deal post-mortem generation |
| GET | `/analysis/ack/{deal_id}` | Advance/Close/Kill recommendation |
| POST | `/analysis/discount` | Email thread discount pressure analysis |

### Activity Intelligence
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/activities/{deal_id}` | Activity feed + engagement score + ghost stakeholders |
| GET | `/activities/team-summary` | Rep activity summary (5-min server cache) |

### Ask DealIQ
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ask/deal` | Ask anything about a specific deal |
| POST | `/ask/meddic` | MEDDIC analysis for a deal |
| POST | `/ask/brief` | Generate deal brief |
| POST | `/ask/follow-up-email` | Generate contextual follow-up email |
| POST | `/ask/pipeline` | Ask across the full pipeline |
| GET | `/ask/presets` | Get preset question library |
| POST | `/ask/demo/*` | Same endpoints, demo mode (no auth) |

### Other
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/forecast` | AI pipeline forecast narrative |
| GET | `/alerts/digest` | Prioritised alerts digest |
| GET | `/signals/{deal_id}` | Buying/risk signal detection |
| GET | `/trackers/{deal_id}` | Smart tracker status |

**All endpoints except `/auth/*` and demo variants require:**
```
Authorization: Bearer <session_token>
```

Use `DEMO_MODE` as the token to activate demo mode with simulated data.

---

## Deal Detail Panel — 10 Sections

The slide-out panel that opens per deal has 10 accordion sections:

| # | Section | Icon | Description |
|---|---------|------|-------------|
| 1 | Deal Timeline | Clock | Chronological deal event history |
| 2 | Health Score Breakdown | Activity | 9 signals with scores and recommendations |
| 3 | Activity Feed | Zap (blue) | Engagement velocity, ghost stakeholder alerts, activity log |
| 4 | AI Sales Rep | Brain | NBA → approve → email draft → approve → send |
| 5 | Pre-Call Intelligence Brief | Phone | AI-generated call prep brief |
| 6 | Narrative Check + Email Coach | GitMerge | Mismatch detection + live email coaching |
| 7 | Smart Trackers | ScanSearch | Buying signal and risk tracker status |
| 8 | Advance / Close / Kill | Layers | Decision surface + autopsy on kill |
| 9 | Call Coaching | GraduationCap (cyan) | Real-time coaching feedback |
| 10 | Ask DealIQ | Sparkles (violet) | 4-tab AI Q&A: chat, MEDDIC, brief, follow-up email |

---

## Health Scoring Model (9 Signals)

| Signal | Max Score | Data Source |
|--------|-----------|-------------|
| Next Step Defined | 15 | CRM description / notes |
| Buyer Response Recency | 15 | Last activity timestamp |
| Stakeholder Depth | 15 | Contact count + economic buyer flag |
| Discount Pattern | 10 | Note/email analysis |
| Stage Velocity | 15 | Stage age vs. benchmark |
| Interaction Quality | 10 | Activity count + recency |
| Engagement Velocity | 5 | Activity trend (accelerating/decelerating) |
| Ghost Stakeholder Risk | 5 | Stakeholder silence detection |
| Multi-thread Score | 10 | Contact breadth across deal |
| **Total** | **100** | |

Score thresholds: **Healthy ≥75** | **At Risk ≥50** | **Critical ≥25** | **Zombie <25**

---

## AI Models

| Task | Model | Reason |
|------|-------|--------|
| Ask Q&A, MEDDIC, Deal Brief | `llama-3.3-70b-versatile` | Quality — needs reasoning depth |
| Email drafting, pipeline questions | `llama-3.1-8b-instant` | Speed — latency-sensitive |
| Email coaching (real-time) | `llama-3.1-8b-instant` | Debounced, must be fast |
| NBA, call brief, objection | `llama-3.3-70b-versatile` | Quality — sales-critical output |

All AI calls use `GROQ_API_KEY` via the Groq API.

---

## Demo Mode

Use token `DEMO_MODE` to run the full app without Zoho or a database.

Demo deals available:
- `sim_001` — Acme Corp (healthy deal)
- `sim_002` — Globex Inc (at risk)
- `sim_003` — Initech (critical)
- `sim_004` — FinanceFlow (zombie — best for autopsy demo)

Demo endpoints also available at `/ask/demo/*`, `/ai-rep/demo-*`, `/analysis/*/demo`.

---

## Demo Walkthrough (5 minutes)

1. Open app → "Try demo without login"
2. Dashboard loads with 4 pre-scored deals across all health states
3. Click into **FinanceFlow** (red/zombie)
   - Health Breakdown: all 9 signals with explanations
   - ACK: "Kill" recommendation with supporting evidence
   - Trigger autopsy → AI post-mortem generates
4. Switch to **Acme Corp** → Narrative Mismatch section
   - Load demo transcript + email draft → "Check Before Sending"
   - 3 mismatch flags: missing discount commitment, timeline, follow-up date
5. Open Activity Feed: engagement velocity score + ghost stakeholder alerts
6. Open Ask DealIQ tab → MEDDIC tab → "Run MEDDIC Analysis"
7. Open AI Sales Rep → generate NBA → approve → draft email → copy

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Shadcn UI |
| Backend | Python, FastAPI, Pydantic v2, SQLAlchemy (async) |
| AI Inference | Groq API (LLaMA 3.1/3.3) |
| CRM | Zoho CRM (OAuth2) + Demo mode |
| Database | PostgreSQL (async via asyncpg) — optional for demo |

---

*DealIQ is in active development. The problem is real. The gap is genuine.*
