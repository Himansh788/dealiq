# DealIQ — Revenue Without Guesswork

> AI-powered deal clarity system for B2B SaaS revenue teams  
> Hackathon Submission | 2025

---

## What It Does

DealIQ sits between your CRM and your communication stack and answers the question CRMs can't: **is this deal actually progressing, or quietly dying?**

Four features:
1. **Deal Health Score** — 0-100 score per deal based on 6 communication signals
2. **Narrative Mismatch Detection** — AI compares call transcripts to follow-up emails and flags what was promised vs. what was written
3. **Discount Heat Map** — tracks discount pressure across an email thread
4. **Advance / Close / Kill** — decision-forcing surface for stalled deals

---

## Architecture

```
Lovable.dev (React frontend)
        ↓ REST API
FastAPI (Python backend) — Railway / Render
        ↓              ↓
Zoho CRM API      Anthropic Claude API
(OAuth2)          (Haiku model)
```

---

## 🚀 Quick Start (Local)

### Step 1 — Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/dealiq.git
cd dealiq
```

### Step 2 — Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate       # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and fill in your keys (see Key Setup below)
python main.py
```

Backend runs at: `http://localhost:8000`  
Swagger docs at: `http://localhost:8000/docs`

### Step 3 — Test without any API keys (Demo Mode)

Without filling in any env vars, you can test using demo endpoints:

```bash
# Get a demo session token
curl http://localhost:8000/auth/demo-session

# Run the demo mismatch (no auth needed)
curl http://localhost:8000/analysis/mismatch/demo
```

---

## 🔑 Key Setup

### 1. Anthropic API Key (Free $5 credit)
1. Sign up at https://console.anthropic.com
2. Go to API Keys → Create Key
3. Add to `.env`: `ANTHROPIC_API_KEY=sk-ant-...`

### 2. Zoho CRM OAuth2

> **India users:** Use `zoho.in` domains  
> **Everyone else:** Use `zoho.com` domains

1. Go to **https://api-console.zoho.in** (or `.com`)
2. Click **Add Client** → Choose **Server-based Applications**
3. Fill in:
   - Client Name: `DealIQ`
   - Homepage URL: `http://localhost:3000`
   - Authorized Redirect URIs: `http://localhost:8000/auth/callback`
4. Copy Client ID and Client Secret to `.env`
5. **Also update** `zoho_client.py` line 10-11:
   - India: keep `zoho.in` (default)
   - USA/EU: change to `zoho.com`

### 3. Zoho Free CRM Setup (if you don't have deals yet)
1. Sign up at https://www.zoho.com/crm/
2. Free plan supports 3 users and full API access
3. Add a few test deals in the Deals module
4. The OAuth scope in `zoho_client.py` will request read access to Deals, Contacts, Activities

---

## 📁 Project Structure

```
dealiq/
├── backend/
│   ├── main.py                     # FastAPI app entry point
│   ├── routers/
│   │   ├── auth.py                 # Zoho OAuth2 login, callback, demo session
│   │   ├── deals.py                # List deals, health scores, pipeline metrics
│   │   └── analysis.py             # Mismatch, discount, ACK endpoints
│   ├── services/
│   │   ├── zoho_client.py          # Zoho CRM API wrapper
│   │   ├── claude_client.py        # Anthropic Claude API calls
│   │   ├── health_scorer.py        # 6-signal health scoring engine
│   │   └── demo_data.py            # Simulated deals + demo transcript/email
│   ├── models/
│   │   └── schemas.py              # Pydantic schemas
│   ├── requirements.txt
│   └── .env.example
├── README.md
└── .gitignore
```

---

## 🔌 API Reference

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/auth/login` | Get Zoho OAuth2 URL |
| GET | `/auth/callback` | OAuth2 callback handler |
| GET | `/auth/demo-session` | Get demo session (no Zoho needed) |

### Deals
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/deals/` | List all deals with health scores |
| GET | `/deals/metrics` | Pipeline summary metrics |
| GET | `/deals/{id}/health` | Full health breakdown for one deal |

### Analysis
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/analysis/mismatch` | Check transcript vs email for mismatches |
| GET | `/analysis/mismatch/demo` | Demo mismatch (no auth) |
| POST | `/analysis/discount` | Analyse email thread for discount pressure |
| GET | `/analysis/ack/{deal_id}` | Get Advance/Close/Kill recommendation |
| POST | `/analysis/ack/{deal_id}/decide` | Log rep's ACK decision |

**All endpoints except `/auth/*` and `/analysis/mismatch/demo` require:**
```
Authorization: Bearer <base64_session_token>
```

---

## 🎨 Frontend — Lovable.dev Setup

### Step 1 — Create new project at lovable.dev

### Step 2 — Paste this prompt to generate the full UI:

---

**LOVABLE PROMPT — PASTE THIS EXACTLY:**

```
Build a B2B SaaS dashboard called "DealIQ" with the tagline "Revenue without guesswork."

Tech: React, Tailwind CSS, shadcn/ui. Dark theme preferred (slate-900 background, white text).

The app has these pages/views:

---

PAGE 1: Login Screen
- Centered card with DealIQ logo (use a simple bar chart icon in blue)
- Tagline: "Revenue without guesswork."
- One primary button: "Login with Zoho CRM" (blue, full width)
- Smaller text link below: "Try demo without login →"
- On "Login with Zoho CRM": call GET /auth/login, redirect to returned auth_url
- On "Try demo": call GET /auth/demo-session, store session in localStorage, navigate to dashboard
- On page load, check URL for ?session= param (OAuth callback) and store it, then redirect to /dashboard
- Also check for ?error= param and show error toast

---

PAGE 2: Dashboard (main view after login)

Header bar:
- DealIQ logo left
- "Demo Mode" badge (orange pill) if session is demo
- User email/name from session (top right)
- Logout button

Summary cards row (4 cards):
- Total Deals (number)
- Pipeline Value (formatted as $X.XM or $XXK)
- Avg Health Score (number with color: green ≥75, yellow ≥50, red <50)
- Deals Needing Action (red number with warning icon)
Fetch these from GET /deals/metrics

Below: Deals Table
Columns: Deal Name | Company | Stage | Amount | Health Score | Status | Action
- Health Score shown as colored pill: green (healthy), yellow (at_risk), orange (critical), red (zombie)
- Status label matches health_label
- Action button: "Analyse" (opens Deal Detail panel)
- Sort by health score ascending by default (worst first)
Fetch from GET /deals/

---

PAGE 3: Deal Detail Panel (slide-in from right, overlay)

Opens when "Analyse" is clicked on any deal row.

Section 1 — Health Score Breakdown
- Large score number (0-100) with a circular progress indicator colored by health
- Six signal rows, each showing: signal name | score bar | label (good/warn/critical) | detail text
- Recommendation box at bottom (highlighted if action_required)
Fetch from GET /deals/{id}/health

Section 2 — Advance / Close / Kill
- Show recommendation card: "Advance" (green) | "Escalate" (orange) | "Kill" (red)
- Show supporting signals as bullet points
- Three action buttons: [Advance] [Escalate] [Kill] — clicking logs the decision
Fetch from GET /analysis/ack/{deal_id}

Section 3 — Narrative Mismatch Checker
- Two text areas side by side: "Call Transcript" (left) | "Email Draft" (right)
- Each has a "Load Demo" button that pre-fills with sample data
- Big button: "Check Before Sending" (runs POST /analysis/mismatch)
- Results appear below as warning cards:
  - Each card shows: category badge | description text | severity icon | suggested fix
  - Health impact shown as "-X points" in red
  - If clean: green checkmark with "No mismatches found"

---

State management: Use React Context or Zustand for session state.
API base URL: read from environment variable VITE_API_URL (default: http://localhost:8000)
Show loading spinners while fetching. Show error toasts on API failures.
Make it look polished and professional — this is a hackathon demo for judges.
```

---

### Step 3 — Add your API URL in Lovable

After generating, find where environment variables are set and add:
```
VITE_API_URL=http://localhost:8000
```

For production (after deploying backend to Railway):
```
VITE_API_URL=https://your-backend.up.railway.app
```

---

## 🚢 Deployment (Free)

### Backend → Railway.app

```bash
# Install Railway CLI
npm install -g @railway/cli
railway login
cd backend
railway init
railway up
```

Set environment variables in Railway dashboard under Variables:
- `ANTHROPIC_API_KEY`
- `ZOHO_CLIENT_ID`
- `ZOHO_CLIENT_SECRET`
- `ZOHO_REDIRECT_URI` → set to `https://YOUR-BACKEND.up.railway.app/auth/callback`
- `FRONTEND_URL` → set to your Lovable app URL

**Important:** After deploying backend, update your Zoho app's redirect URI to the Railway URL.

### Frontend → Lovable handles this automatically

Just set `VITE_API_URL` to your Railway backend URL in Lovable's settings.

---

## 🎯 Hackathon Demo Walkthrough

**For judges with no Zoho account:**

1. Open the app → click "Try demo without login"
2. Dashboard loads with 6 pre-scored deals (showing all 4 health states)
3. Click "Analyse" on FinanceFlow deal (red/zombie — worst deal)
4. Show health breakdown — all 6 signals with explanations
5. Show ACK recommendation → "Kill" with supporting evidence
6. Switch to Acme Corp deal → click Narrative Mismatch section
7. Click "Load Demo" in both text areas → click "Check Before Sending"
8. Watch 3 mismatch flags appear: missing 12% discount, missing 3-week timeline, missing March 7th call
9. Show health score drop visually
10. Click "Add to email" on each flag

**Total demo time: ~5 minutes**

---

## Health Scoring Model

| Signal | Max Score | Data Source |
|--------|-----------|-------------|
| Next Step Defined | 20 | CRM description / notes |
| Buyer Response Recency | 20 | Last activity timestamp |
| Stakeholder Depth | 20 | Contact count + economic buyer flag |
| Discount Pattern | 15 | Note/email analysis |
| Stage Velocity | 15 | Stage age vs. benchmark |
| Interaction Quality | 10 | Activity count + recency |
| **Total** | **100** | |

Score thresholds: Healthy ≥75 | At Risk ≥50 | Critical ≥25 | Zombie <25

---

## What's Simulated vs. Real

| Feature | In Demo | In Production |
|---------|---------|---------------|
| Deal data | Hardcoded 6 deals | Live Zoho CRM |
| Health scoring | Rules-based (real logic) | Same + more signals |
| Mismatch detection | Live Claude API | Live Claude API |
| Discount analysis | Live Claude API | Live Claude API |
| ACK decisions | Logged locally | Written back to Zoho |
| Auth | Demo bypass + real OAuth | Real OAuth only |

---

## Built With

- **FastAPI** — Python backend
- **Anthropic Claude Haiku** — AI analysis (cheapest, fastest model)
- **Zoho CRM API** — Deal data source
- **Lovable.dev** — Frontend generation
- **Railway** — Backend hosting

---

*DealIQ is an early concept. The problem is real. The gap is genuine. The approach is worth testing.*
