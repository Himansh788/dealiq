

# DealIQ — "Revenue without guesswork."

A polished B2B SaaS deal intelligence dashboard with dark slate theme, built with React, Tailwind CSS, and shadcn/ui.

---

## Foundation & Theme
- Dark theme with slate-900 background, white text, and subtle blue/purple accent gradients throughout
- Session management via React Context backed by localStorage (`dealiq_session` key)
- API service layer reading from `VITE_API_URL` (default `http://localhost:8000`), all requests using `Authorization: Bearer {access_token}` header
- Skeleton loaders on all data fetches, error toasts on API failures

---

## Page 1: Login Screen (`/`)
- Full-screen dark background with centered card
- DealIQ logo using a bar-chart icon with blue/purple gradient styling
- Tagline: "Revenue without guesswork." + subtitle about AI-powered deal clarity
- **"Login with Zoho CRM"** button (blue, full-width) — fetches `GET /auth/login`, redirects to returned `auth_url`
- **"Try demo without login →"** link — fetches `GET /auth/demo-session`, stores session, navigates to `/dashboard`
- On page load: detects `?session=` URL param (OAuth callback) to store and redirect, or `?error=` param to show error toast

## Page 2: Dashboard (`/dashboard`)
### Header Bar
- DealIQ logo + name on the left
- Orange "DEMO MODE" pill badge when `access_token === "DEMO_MODE"`
- User display name and email on the right, with a Logout button

### Summary Cards (4-card row)
- **Total Deals** — simple count
- **Pipeline Value** — formatted as $84K or $1.2M
- **Avg Health Score** — color-coded number (green ≥75, yellow ≥50, red <50)
- **Needs Action** — red number with alert icon
- Fetched from `GET /deals/metrics`

### Deals Table
- Columns: Deal Name, Company, Stage, Amount, Health Score, Status, Action
- Health Score shown as colored pill badges (green=healthy, yellow=at_risk, orange=critical, red=zombie)
- Default sort: worst health score first
- "Analyse →" button per row opens the Deal Detail panel
- Fetched from `GET /deals/`

## Page 3: Deal Detail Panel (slide-in overlay from right)
Opens when "Analyse →" is clicked on any deal row. Three collapsible sections:

### Section 1 — Health Score Breakdown
- Large circular progress indicator (0–100) colored by health label
- Six signal rows with: signal name, mini progress bar, label chip (good/warn/critical), detail text
- Recommendation box in a highlighted card at the bottom
- Fetched from `GET /deals/{id}/health`

### Section 2 — Advance / Close / Kill
- Recommendation card styled by type: green (Advance), orange (Escalate), red (Kill)
- Days stalled count, reasoning paragraph, supporting signals as bullet list
- Three action buttons: Advance, Escalate, Kill — posts decision to `POST /analysis/ack/{deal_id}/decide`
- Fetched from `GET /analysis/ack/{deal_id}`

### Section 3 — Narrative Mismatch Checker
- Two side-by-side textareas: "Call Transcript" (left) and "Email Draft" (right)
- "Load Demo Data" button above each to pre-fill with sample content
- "Check Before Sending" button → `POST /analysis/mismatch`
- Results as warning cards: category badge, description, severity icon, suggested fix, health impact as "-X pts" in red
- Clean state: green success card "No mismatches found. Safe to send."

