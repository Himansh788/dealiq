# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## Memory Files (Auto-Loaded)
| File | Purpose |
|------|---------|
| `.claude/rules/memory-profile.md` | Who I am, my stack, my projects |
| `.claude/rules/memory-preferences.md` | How I like things done |
| `.claude/rules/memory-decisions.md` | Past architectural/tech decisions |
| `.claude/rules/memory-sessions.md` | Rolling log of recent work |

---

## Commands

### Backend (FastAPI)
```bash
cd backend
# Activate venv first (Windows)
venv\Scripts\activate

pip install -r requirements.txt
uvicorn main:app --reload --port 8000

# DB setup (run once)
python database/create_db.py
```

### Frontend (React + Vite)
```bash
cd frontend
npm install
npm run dev        # dev server on :5173
npm run build      # production build
npm run lint       # ESLint
npm run test       # vitest (single run)
npm run test:watch # vitest watch mode
```

---

## Architecture

### Monorepo Layout
```
dealiq/
  backend/          # FastAPI app
    main.py         # app factory, all routers registered here, startup event (DB + APScheduler)
    routers/        # one file per feature domain
    services/       # business logic; routers are thin, services do the work
    database/
      connection.py # async SQLAlchemy engine; degrades gracefully when DATABASE_URL is absent
      models.py     # SQLAlchemy ORM models
      init_db.py    # create_tables() called on startup
    models/         # Pydantic request/response schemas
  frontend/         # React 18 + Vite + Tailwind + Shadcn UI
    src/
      components/   # shared + feature components
      pages/        # route-level components
      lib/api.ts    # single file for ALL backend API calls
```

### Backend Patterns
- **Auth**: routers decode the session token directly via `_decode_session(authorization)` + `Header(...)`. Do NOT use `Depends(get_current_user)` — that pattern is not used.
- **Demo mode**: check `session.get("access_token") == "DEMO_MODE"` at the top of each handler; return data from `services/demo_data.py`.
- **AI calls**: all use Groq (`GROQ_API_KEY`). Quality tasks → `llama-3.3-70b-versatile`; speed tasks → `llama-3.1-8b-instant`.
- **DB is optional**: `get_db()` yields `None` when `DATABASE_URL` is unset. Every handler that touches the DB must guard with `if db:` and fall back to demo data.
- **Zoho CRM**: `services/zoho_client.py` is the only place that talks to Zoho. Write ops require `ZohoCRM.modules.deals.UPDATE` scope.

### Frontend Patterns
- All API calls go through `src/lib/api.ts` — never `fetch`/`axios` directly in components.
- State: React Query for server state; no global store.
- UI: Shadcn components (Radix primitives + Tailwind). Use `cn()` (`clsx` + `tailwind-merge`) for conditional classes.
- Notifications: `sonner` toast only — no `alert()`.
- Icons: `lucide-react` only — no emoji in UI code.
- `DealDetailPanel.tsx` is the main slide-out panel with 11 accordion sections. Adding a new section means adding it to this file.

### Key Environment Variables
```
GROQ_API_KEY          # required for all AI features
DATABASE_URL          # mysql+aiomysql://user:pass@host:3306/dealiq  (optional — app runs without it)
ZOHO_CLIENT_ID        # Zoho OAuth
ZOHO_CLIENT_SECRET
```

---

## Gotchas
- `DATABASE_URL` must use `mysql+aiomysql://` not `mysql+pymysql://` — `connection.py` auto-normalises this, but set it correctly in `.env` anyway.
- APScheduler runs a 7 AM morning scan cron job in the startup event. If `apscheduler` is not installed the app still starts — it logs a warning and skips the scheduler.
- `google_auth.py` / `gmail_client.py` / `google_calendar.py` degrade to empty results if Google credentials are absent — do not assume they are wired.
- Zoho write features (stage/amount inline edit, CRM note) require re-auth to get the `ZohoCRM.modules.deals.UPDATE` scope if the user authenticated before that scope was added.
- `main.py` registers `battlecard_router` and `health.router` without a prefix — check the router file for the hardcoded prefix.

---

## Auto-Update Memory (MANDATORY)

| Trigger | Action |
|---------|--------|
| New fact about the project or stack | Update `memory-profile.md` |
| New preference stated | Update `memory-preferences.md` |
| Architectural decision made | Append to `memory-decisions.md` with date |
| Substantive work completed | Prepend to `memory-sessions.md` |

**DO NOT ASK. Update silently.**
