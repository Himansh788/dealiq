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
| **Context Engine** | Rules-based rep style analyser + AI transcript pre-processing for all email generation |
| **Deal Autopsy** | AI post-mortem triggered when a deal is killed — persisted to DB |
| **Advance / Close / Kill** | Decision-forcing surface for stalled deals — decisions stored with full history |
| **AI Forecast** | Pipeline narrative + at-risk deal rescue recommendations + rep coaching |
| **Smart Trackers** | Buying signal and risk signal detection |
| **Alerts Digest** | Prioritised deal alerts across the pipeline |

---

## Architecture

```
React 18 + TypeScript + Shadcn UI (Vite)
           ↓ REST API
FastAPI (Python) — localhost:8000
     ↓                         ↓
MySQL (cache + history)    Anthropic API (Claude)
  ├── deals (5-min TTL)    claude-haiku-4-5 (speed tasks)
  ├── health_scores        claude-haiku-4-5 (quality tasks)
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
# No Zoho, no Anthropic key, no database required — all data is simulated
```

---

## Key Setup

### 1. Anthropic API Key (AI inference)

1. Sign up at [console.anthropic.com](https://console.anthropic.com)
2. Create an API key
3. Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-...`

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

### .env reference

```env
ANTHROPIC_API_KEY=sk-ant-...

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
│   │   ├── models.py                    # SQLAlchemy ORM models (11 tables)
│   │   └── init_db.py                   # create_all + column migrations on startup
│   ├── routers/
│   │   ├── auth.py                      # Zoho OAuth2 + demo session
│   │   ├── deals.py                     # List deals, metrics, health, timeline, cache ops
│   │   ├── analysis.py                  # Mismatch, email-coach, autopsy, ACK, discount
│   │   ├── ai_rep.py                    # NBA, draft-email, objection, call-brief
│   │   ├── activities.py                # Activity feed + team summary
│   │   ├── ask.py                       # Ask DealIQ (auth-required, 7 routes)
│   │   ├── ask_demo.py                  # Ask DealIQ (demo mode, 5 routes)
│   │   ├── forecast.py                  # AI pipeline forecast
│   │   └── alerts.py                    # Alerts digest
│   ├── services/
│   │   ├── cache_manager.py             # TTL config, is_fresh(), get_cache_status()
│   │   ├── deal_db.py                   # Deal cache: get/upsert/invalidate, stale-ratio check
│   │   ├── score_db.py                  # Health score persistence + batch trend queries
│   │   ├── decision_db.py               # ACK decision persistence + history
│   │   ├── health_scorer.py             # 9-signal scorer (score_deal_with_activities)
│   │   ├── context_engine.py            # RepStyle + DealContext, transcript pre-processing
│   │   ├── email_generator.py           # 2-pass email generation with commitment coverage
│   │   ├── ai_rep.py                    # NBA, objection, call-brief logic
│   │   ├── ask_dealiq_service.py        # Ask Q&A engine (deal Q&A, MEDDIC, brief, follow-up)
│   │   ├── ask_dealiq_prompts.py        # All Ask DealIQ AI prompts + PRESET_QUESTIONS
│   │   ├── activity_intelligence.py     # Engagement velocity scoring + ghost detection
│   │   ├── deal_autopsy.py              # Post-mortem generation
│   │   ├── email_coach.py               # Real-time email coaching
│   │   ├── zoho_client.py               # Raw Zoho API client
│   │   └── demo_data.py                 # SIMULATED_DEALS + activities + emails
│   ├── models/
│   │   ├── schemas.py                   # Core Pydantic schemas (incl. cache_meta in DealList)
│   │   └── activity_schemas.py          # Activity feed schemas
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   │   ├── Login.tsx                # Zoho OAuth + demo login
│   │   │   ├── Dashboard.tsx            # Pipeline table + filters + cache indicator
│   │   │   ├── Home.tsx                 # AI to-dos: greeting + metrics + priority deals
│   │   │   ├── ForecastPage.tsx         # AI forecast + rescue opps + rep coaching
│   │   │   ├── AskDealIQPage.tsx        # Full Ask DealIQ page with deal selector
│   │   │   └── AlertsPage.tsx           # Alerts digest
│   │   ├── components/
│   │   │   ├── DealDetailPanel.tsx      # Main slide-out panel (10 accordion sections)
│   │   │   ├── NavBar.tsx               # Shared top nav (alerts bell, Cmd+K, user)
│   │   │   ├── CommandPalette.tsx       # Cmd+K search across deals + navigation
│   │   │   ├── layout/
│   │   │   │   ├── AppLayout.tsx        # Root layout: Sidebar + main content
│   │   │   │   └── Sidebar.tsx          # 60px icon-only sidebar nav
│   │   │   └── deal/
│   │   │       ├── DealTimeline.tsx     # Deal event timeline
│   │   │       ├── HealthBreakdown.tsx  # 9-signal health display
│   │   │       ├── ActivityFeedPanel.tsx # Engagement velocity + ghost alerts
│   │   │       ├── AIRepPanel.tsx       # NBA → approve → email draft → approve
│   │   │       ├── CallBriefPanel.tsx   # Pre-call intelligence brief
│   │   │       ├── MismatchChecker.tsx  # Narrative check + live email coach
│   │   │       ├── AckSection.tsx       # Advance/Close/Kill + autopsy on kill
│   │   │       ├── AutopsyPanel.tsx     # Deal post-mortem
│   │   │       ├── AskDealIQPanel.tsx   # 4-tab Ask panel
│   │   │       └── CoachingPanel.tsx    # Call coaching
│   │   └── lib/
│   │       └── api.ts                   # All API calls (typed)
│   └── package.json
├── README.md
└── .gitignore
```

---

## Database Schema (11 Tables)

| Table | Purpose | TTL |
|-------|---------|-----|
| `deals` | Zoho deal cache — avoids API on every page load | 5 min |
| `health_scores` | Score history per deal — powers trend arrows | 15 min |
| `decisions` | ACK decisions (advance/close/kill) with full history | permanent |
| `emails` | Email thread cache | 10 min |
| `email_analyses` | Mismatch / discount analysis results — avoid re-running Claude | 24 hr |
| `transcripts` | Call transcripts | permanent |
| `transcript_summaries` | Pre-processed call intelligence | permanent |
| `email_extractions` | Extracted next-steps / commitments per email | permanent |
| `meeting_log` | Meeting timeline with AI summary and action items | 1 hr |
| `pending_crm_update` | Async Zoho write-back queue (pending/approved/rejected) | — |
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
| GET | `/deals/{id}/score-history` | Health score history (default 30 days) |
| GET | `/deals/{id}/decisions` | ACK decision history |
| POST | `/deals/{id}/refresh` | Force re-fetch single deal from Zoho |
| POST | `/deals/sync` | Force full Zoho sync for all deals |

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
| POST | `/analysis/ack/{deal_id}/decide` | Log ACK decision (persisted to DB) |
| POST | `/analysis/discount` | Email thread discount pressure analysis |

### Activity Intelligence
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/activities/{deal_id}` | Activity feed + engagement score + ghost stakeholders |
| GET | `/activities/team-summary` | Rep activity summary |

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
| GET | `/health/db` | MySQL connectivity check |

**All endpoints except `/auth/*` and demo variants require:**
```
Authorization: Bearer <session_token>
```

Use `DEMO_MODE` as the token to activate demo mode with simulated data.

---

## Deal Detail Panel — 10 Sections

| # | Section | Description |
|---|---------|-------------|
| 1 | Deal Timeline | Chronological deal event history |
| 2 | Health Score Breakdown | 9 signals with scores and recommendations |
| 3 | Activity Feed | Engagement velocity, ghost stakeholder alerts, activity log |
| 4 | AI Sales Rep | NBA → approve → email draft → approve → send |
| 5 | Pre-Call Intelligence Brief | AI-generated call prep brief |
| 6 | Narrative Check + Email Coach | Mismatch detection + live email coaching |
| 7 | Smart Trackers | Buying signal and risk tracker status |
| 8 | Advance / Close / Kill | Decision surface + autopsy on kill |
| 9 | Call Coaching | Real-time coaching feedback |
| 10 | Ask DealIQ | 4-tab AI Q&A: chat, MEDDIC, brief, follow-up email |

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
| Ask Q&A, MEDDIC, Deal Brief | `claude-haiku-4-5-20251001` | Reasoning depth |
| Email drafting, pipeline questions | `claude-haiku-4-5-20251001` | Speed + quality |
| Email coaching (real-time) | `claude-haiku-4-5-20251001` | Debounced, must be fast |
| NBA, call brief, objection | `claude-haiku-4-5-20251001` | Sales-critical output |

All AI calls use `ANTHROPIC_API_KEY` via the Anthropic API.

---

## Cache Freshness System

Every API response that uses the DB cache includes a `_cache` / `cache_meta` block:

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

Use token `DEMO_MODE` to run the full app without Zoho, Anthropic, or a database.

Demo deals:
- `sim_001` — Acme Corp (healthy)
- `sim_002` — Globex Inc (at risk)
- `sim_003` — Initech (critical)
- `sim_004` — FinanceFlow (zombie — best for autopsy demo)

Demo endpoints: `/ask/demo/*`, `/ai-rep/demo-*`, `/analysis/*/demo`

---

## Demo Walkthrough (5 minutes)

1. Open app → "Try demo without login"
2. Dashboard loads with 4 pre-scored deals across all health states
3. Click into **FinanceFlow** (zombie)
   - Health Breakdown: all 9 signals with explanations
   - ACK: "Kill" recommendation with supporting evidence → trigger autopsy
4. Switch to **Acme Corp** → Narrative Mismatch section
   - Load demo transcript + email draft → "Check Before Sending"
   - Flags: missing discount commitment, timeline mismatch, follow-up date
5. Open Activity Feed → engagement velocity score + ghost stakeholder alerts
6. Open Ask DealIQ → MEDDIC tab → "Run MEDDIC Analysis"
7. Open AI Sales Rep → generate NBA → approve → draft email → copy

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, TypeScript, Vite, Tailwind CSS, Shadcn UI |
| Backend | Python, FastAPI, Pydantic v2, SQLAlchemy (async) |
| AI Inference | Anthropic API (Claude Haiku) |
| CRM | Zoho CRM (OAuth2) + Demo mode |
| Database | MySQL 8+ (async via aiomysql) — optional, degrades gracefully |

---

*DealIQ is in active development. The problem is real. The gap is genuine.*
