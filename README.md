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
| **Health Score Trends** | Improving / declining / stable arrows — backed by persisted score history in MySQL |
| **Cache Freshness System** | Serve deals from DB in ~50ms; background Zoho sync when >30% stale |
| **Activity Intelligence** | Engagement velocity scoring, ghost stakeholder detection, team activity summary |
| **AI Sales Rep** | Next Best Action → approve → draft email → approve → send. Objection handler included. |
| **Pre-Call Intelligence Brief** | AI-generated call prep: key risks, stakeholder map, suggested questions |
| **Narrative Mismatch Checker** | Compares call transcripts to follow-up emails and flags promise/commitment gaps |
| **Live Email Coach** | Real-time coaching as the rep types an email (debounced, keystroke-driven) |
| **Ask DealIQ** | 4-tab AI Q&A panel: open Q&A chat, MEDDIC analysis, Deal Brief, Follow-up Email generator |
| **Context Engine** | Rules-based rep style analyser + AI transcript pre-processing for all email generation. Recovers buyer replies from quoted email chains when Zoho doesn't store them separately. |
| **Deal Autopsy** | AI post-mortem triggered when a deal is killed — persisted to DB |
| **Advance / Close / Kill** | Decision-forcing surface for stalled deals — decisions stored with full history |
| **AI Forecast Board** | Pipeline narrative + at-risk deal rescue recommendations + rep coaching |
| **Win/Loss Intelligence** | Auto-detects closed deals from Zoho, runs AI pattern analysis, surfaces win/loss themes |
| **Battle Card** | AI-generated competitive positioning card per deal |
| **Email Timeline** | Full email thread history with AI analysis — direction-aware (handles Zoho's outbound-only API by parsing quoted reply chains) |
| **Smart Trackers** | Buying signal and risk signal detection |
| **Alerts Digest** | Prioritised deal alerts across the pipeline |
| **Light / Dark Theme** | CSS-variable-based theme system with localStorage persistence |

---

## Architecture

```
React 18 + TypeScript + Shadcn UI (Vite)
           ↓ REST API
FastAPI (Python) — localhost:8000
     ↓                         ↓
MySQL (cache + history)    Groq API (LLM inference)
  ├── deals (5-min TTL)    llama-3.3-70b-versatile (quality)
  ├── health_scores        llama-3.1-8b-instant (speed)
  ├── decisions
  └── email_analyses            ↓
                           Zoho CRM (OAuth2)
                           or Demo Mode (in-memory)
```

### Cache Freshness Flow

```
GET /deals/ — first request:
  DB empty → blocking Zoho fetch → save 100+ deals → return (~3s one-time)

GET /deals/ — within 5 minutes:
  DB fresh → return immediately (~50ms)

GET /deals/ — after 5 minutes:
  DB stale → return stale data immediately + trigger background Zoho sync
  User sees data in ~50ms; DB refreshed behind the scenes
```

---

## Quick Start (Local)

### Step 1 — Clone

```bash
git clone https://github.com/himansh788/dealiq.git
cd dealiq
```

### Step 2 — Database (MySQL)

```bash
# Create the database (requires MySQL running locally)
cd backend
python create_db.py
# Output: [OK] Database 'dealiq' ready
```

Tables are created automatically on first backend start via `create_tables()`.

### Step 3 — Backend

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

### Step 4 — Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

### Step 5 — Test without any API keys (Demo Mode)

```bash
# Get a demo session token
curl http://localhost:8000/auth/demo-session

# Use DEMO_MODE as the bearer token for all API calls
# No Zoho, no Groq key, no database required — all data is simulated
```

---

## Key Setup

### 1. Groq API Key (AI inference)

1. Sign up at [console.groq.com](https://console.groq.com)
2. Create an API key
3. Add to `.env`: `GROQ_API_KEY=gsk_...`

### 2. MySQL Database (optional — demo mode works without it)

1. Install MySQL 8+ locally or use a cloud instance
2. Run `python create_db.py` to create the `dealiq` schema
3. Add to `.env`: `DATABASE_URL=mysql+aiomysql://user:password@localhost:3306/dealiq`

Tables and columns are created/migrated automatically on startup — no manual migrations needed.

### 3. Zoho CRM OAuth2 (optional — demo mode works without it)

> India users: use `zoho.in` domains. Everyone else: `zoho.com`

1. Go to **https://api-console.zoho.in** (or `.com`)
2. Add Client → Server-based Applications
3. Fill in:
   - Homepage URL: `http://localhost:5173`
   - Redirect URI: `http://localhost:8000/auth/callback`
4. Copy Client ID + Secret to `.env`

> **Note:** Inline CRM editing (stage, amount) and CRM note saving require the `ZohoCRM.modules.deals.UPDATE` scope. If you authenticated before this scope was added, re-auth to enable write features.

### .env reference

```env
GROQ_API_KEY=gsk_...

ZOHO_CLIENT_ID=...
ZOHO_CLIENT_SECRET=...
ZOHO_REDIRECT_URI=http://localhost:8000/auth/callback
ZOHO_REGION=in            # or com

FRONTEND_URL=http://localhost:5173

# Optional — enables deal caching, score history, decision persistence
DATABASE_URL=mysql+aiomysql://root:password@localhost:3306/dealiq
```

---

## Project Structure

```
dealiq/
├── backend/
│   ├── main.py                          # FastAPI app — registers all routers
│   ├── create_db.py                     # One-time MySQL schema setup script
│   ├── database/
│   │   ├── connection.py                # Async engine + get_db() dependency
│   │   ├── models.py                    # SQLAlchemy ORM models
│   │   └── init_db.py                   # create_all + column migrations on startup
│   ├── routers/
│   │   ├── auth.py                      # Zoho OAuth2 + demo session
│   │   ├── deals.py                     # List deals, metrics, health, timeline, inline edit
│   │   ├── analysis.py                  # Mismatch, email-coach, autopsy, ACK, discount
│   │   ├── ai_rep.py                    # NBA, draft-email, objection, call-brief
│   │   ├── activities.py                # Activity feed + team summary
│   │   ├── ask.py                       # Ask DealIQ (auth-required, 7 routes)
│   │   ├── ask_demo.py                  # Ask DealIQ (demo mode, 5 routes)
│   │   ├── email_intel.py               # Email thread fetch + AI analysis + body normalisation
│   │   ├── winloss.py                   # Win/Loss analysis + board
│   │   ├── battlecard.py                # AI battle card generation
│   │   ├── forecast.py                  # AI pipeline forecast
│   │   └── alerts.py                    # Alerts digest
│   ├── services/
│   │   ├── zoho_client.py               # Zoho API client (emails, contacts, deals, write ops)
│   │   ├── health_scorer.py             # 9-signal scorer (score_deal_with_activities)
│   │   ├── context_engine.py            # RepStyle + DealContext + quoted-chain email recovery
│   │   ├── email_generator.py           # 2-pass email generation with commitment coverage
│   │   ├── email_cache.py               # DB-backed email body cache (24hr TTL)
│   │   ├── email_analyzer.py            # AI thread analysis (sentiment, flags, next step)
│   │   ├── ai_rep.py                    # NBA, objection, call-brief logic
│   │   ├── ask_dealiq_service.py        # Ask Q&A engine (deal Q&A, MEDDIC, brief, follow-up)
│   │   ├── ask_dealiq_prompts.py        # All Ask DealIQ AI prompts + PRESET_QUESTIONS
│   │   ├── activity_intelligence.py     # Engagement velocity scoring + ghost detection
│   │   ├── deal_autopsy.py              # Post-mortem generation
│   │   ├── email_coach.py               # Real-time email coaching
│   │   ├── deal_health_ai.py            # AI-enhanced health reasoning
│   │   └── demo_data.py                 # SIMULATED_DEALS + activities + emails
│   ├── models/
│   │   ├── schemas.py                   # Core Pydantic schemas
│   │   └── activity_schemas.py          # Activity feed schemas
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── contexts/
│   │   │   └── ThemeContext.tsx         # Light/dark theme provider (localStorage)
│   │   ├── pages/
│   │   │   ├── Login.tsx                # Zoho OAuth + demo login
│   │   │   ├── Dashboard.tsx            # Pipeline table + filters + inline stage/amount edit
│   │   │   ├── Home.tsx                 # AI to-dos: greeting + metrics + priority deals
│   │   │   ├── ForecastBoard.tsx        # AI forecast board + health bars
│   │   │   ├── WinLossPage.tsx          # Win/Loss intelligence + recharts breakdown
│   │   │   ├── EmailTimelinePage.tsx    # Full email thread history with AI analysis
│   │   │   ├── AskDealIQPage.tsx        # Full Ask DealIQ page with deal selector
│   │   │   └── AlertsPage.tsx           # Alerts digest
│   │   ├── components/
│   │   │   ├── DealDetailPanel.tsx      # Main slide-out panel (11 accordion sections)
│   │   │   ├── ThemeToggle.tsx          # Light/dark toggle (compact + full variants)
│   │   │   ├── layout/
│   │   │   │   ├── AppLayout.tsx        # Root layout: Sidebar + main content
│   │   │   │   └── Sidebar.tsx          # 60px icon-only sidebar nav
│   │   │   ├── email/
│   │   │   │   └── EmailThreadView.tsx  # Gmail-style thread renderer + chain parser
│   │   │   └── deal/
│   │   │       ├── DealTimeline.tsx
│   │   │       ├── HealthBreakdown.tsx
│   │   │       ├── ActivityFeedPanel.tsx
│   │   │       ├── AIRepPanel.tsx
│   │   │       ├── CallBriefPanel.tsx
│   │   │       ├── MismatchChecker.tsx
│   │   │       ├── AckSection.tsx
│   │   │       ├── AutopsyPanel.tsx
│   │   │       ├── BattleCardPanel.tsx
│   │   │       ├── AskDealIQPanel.tsx
│   │   │       └── CoachingPanel.tsx
│   │   └── lib/
│   │       └── api.ts                   # All API calls (typed)
│   └── package.json
├── README.md
└── .gitignore
```

---

## Database Schema

| Table | Purpose | TTL |
|-------|---------|-----|
| `deals` | Zoho deal cache — avoids API on every page load | 5 min |
| `health_scores` | Score history per deal — powers trend arrows | 15 min |
| `decisions` | ACK decisions (advance/close/kill) with full history | permanent |
| `api_cache` | Generic API response cache (incl. email bodies) | per-entry |
| `email_analyses` | Mismatch / discount analysis results | 24 hr |
| `transcripts` | Call transcripts | permanent |
| `transcript_summaries` | Pre-processed call intelligence | permanent |
| `email_extractions` | Extracted next-steps / commitments per email | permanent |
| `meeting_log` | Meeting timeline with AI summary and action items | — |
| `pending_crm_update` | Async Zoho write-back queue | — |
| `audit_log` | User action log | permanent |

All tables are created and column migrations applied automatically on startup.

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
| GET | `/deals/` | List deals (cache-first, includes `cache_meta`) |
| GET | `/deals/metrics` | Pipeline summary metrics |
| GET | `/deals/{id}/health` | 9-signal health breakdown |
| GET | `/deals/{id}/timeline` | Deal event timeline |
| PUT | `/deals/{id}/update` | Inline CRM field update (stage, amount, close date) |

### AI Sales Rep
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ai-rep/nba` | Generate Next Best Action |
| POST | `/ai-rep/draft-email` | Generate email draft |
| POST | `/ai-rep/handle-objection` | Generate objection response |
| POST | `/ai-rep/call-brief` | Generate pre-call intelligence brief |

### Analysis
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/analysis/mismatch` | Transcript vs email mismatch check |
| POST | `/analysis/email-coach` | Real-time email coaching |
| POST | `/analysis/autopsy` | Deal post-mortem generation |
| GET | `/analysis/ack/{deal_id}` | Advance/Close/Kill recommendation |

### Email Intelligence
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/email-intel/threads/{deal_id}` | Full email threads with bodies + AI analysis |
| POST | `/email-intel/analyse/{deal_id}` | Force re-analyse email threads |
| POST | `/email-intel/sync` | Fresh pull from Zoho + Outlook |
| GET | `/email-intel/debug/{deal_id}` | Diagnose raw Zoho email API response |

### Ask DealIQ
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/ask/deal` | Ask anything about a specific deal |
| POST | `/ask/meddic` | MEDDIC analysis for a deal |
| POST | `/ask/brief` | Generate deal brief |
| POST | `/ask/deal/follow-up-email` | Generate contextual follow-up email (with email history + chain recovery) |
| POST | `/ask/pipeline` | Ask across the full pipeline |

### Other
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/forecast/board` | AI forecast board with bucketed deals |
| GET | `/alerts/digest` | Prioritised alerts digest |
| GET | `/winloss/board` | Win/Loss analysis board |
| POST | `/winloss/analyze` | Run AI win/loss analysis for a deal |
| GET | `/activities/{deal_id}` | Activity feed + engagement score + ghost stakeholders |

**All endpoints except `/auth/*` and demo variants require:**
```
Authorization: Bearer <session_token>
```

Use `DEMO_MODE` as the token to activate demo mode with simulated data.

---

## Deal Detail Panel — 11 Sections

| # | Section | Description |
|---|---------|-------------|
| 1 | Deal Timeline | Chronological deal event history |
| 2 | Health Score Breakdown | 9 signals with scores and recommendations |
| 3 | Activity Feed | Engagement velocity, ghost stakeholder alerts, activity log |
| 4 | AI Sales Rep | NBA → approve → email draft → approve → send |
| 5 | Pre-Call Intelligence Brief | AI-generated call prep brief |
| 6 | Narrative Check + Email Coach | Mismatch detection + live email coaching |
| 7 | Battle Card | AI competitive positioning card |
| 8 | Smart Trackers | Buying signal and risk tracker status |
| 9 | Advance / Close / Kill | Decision surface + autopsy on kill |
| 10 | Call Coaching | Real-time coaching feedback |
| 11 | Ask DealIQ | 4-tab AI Q&A: chat, MEDDIC, brief, follow-up email |

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

Score trends (from DB history): **↗ improving** | **→ stable** | **↘ declining**

---

## AI Models

| Task | Model | Reason |
|------|-------|--------|
| Ask Q&A, MEDDIC, Deal Brief, Win/Loss | `llama-3.3-70b-versatile` | Reasoning depth |
| Email drafting, pipeline questions, Battle Card | `llama-3.3-70b-versatile` | Quality output |
| Email coaching (real-time), timeline | `llama-3.1-8b-instant` | Debounced, must be fast |
| NBA, call brief, objection | `llama-3.3-70b-versatile` | Sales-critical output |

All AI calls use `GROQ_API_KEY` via the Groq API.

---

## Email Timeline — How Direction Works

Zoho CRM's email API only returns **outbound emails** (sent from the CRM). Buyer replies are not stored as separate records — they exist only as **quoted text** inside `body_full` of subsequent sent emails.

DealIQ handles this in two places:

1. **`_normalise_zoho_email()`** — computes direction from the `from` email domain (`@vervotech.com` = sent) instead of relying on Zoho's `direction` field (which returns `"sent"` for all emails).

2. **`ContextEngine._extract_quoted_replies()`** — parses Outlook/Gmail-style quoted headers from `body_full` to surface `[← BUYER]` messages for the follow-up email AI context.

3. **`getChainStats()` (frontend)** — parses the quoted chain from the richest email's `body_full` to compute an accurate `receivedCount` and reply rate for the Insights panel.

---

## Cache Freshness System

Every API response that uses the DB cache includes a `cache_meta` block:

```json
{
  "cached": true,
  "fresh": true,
  "source": "cache",
  "age_seconds": 47,
  "ttl_seconds": 300,
  "expires_in_seconds": 253,
  "needs_background_sync": false
}
```

The dashboard shows a live status indicator:
- 🟢 **Live** — data is fresh, served from DB
- 🟡 **Syncing in background…** — stale data served instantly, Zoho sync running
- 🔵 **Just updated from Zoho** — first load or forced refresh

---

## Demo Mode

Use token `DEMO_MODE` to run the full app without Zoho, Groq, or a database.

Demo deals:
- `sim_001` — Acme Corp (healthy)
- `sim_002` — Globex Inc (at risk)
- `sim_003` — Initech (critical)
- `sim_004` — FinanceFlow (zombie — best for autopsy demo)

Demo endpoints: `/ask/demo/*`, `/ai-rep/demo-*`, `/analysis/*/demo`

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Shadcn UI (Radix) |
| Backend | Python, FastAPI, Pydantic v2, SQLAlchemy (async) |
| AI Inference | Groq API (Llama 3.3 70B + Llama 3.1 8B) |
| CRM | Zoho CRM (OAuth2) + Demo mode |
| Database | MySQL 8+ (async via aiomysql) — optional, degrades gracefully |
| Email body cache | DB-backed with 24hr TTL + sentinel for known-empty responses |

---

*DealIQ is in active development. The problem is real. The gap is genuine.*
