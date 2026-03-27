# VoxAgent Dashboard — Frontend Report

**Prepared:** 2026-03-11  
**File:** `dashboard/index.html`  
**Backend Base URL:** `http://localhost:8000`

---

## Overview

A fully functional, single-file SPA (Single Page Application) dashboard was built for VoxAgent using vanilla HTML, CSS, and JavaScript — no build step required. The design uses a **dark SaaS aesthetic** (deep charcoal `#0d0f14`) with vibrant blue accents (`#3d6eff`), Inter typeface, and smooth micro-animations.

---

## Pages Implemented

### 1. Dashboard
**Data loaded from:**
| Data | API Endpoint |
|------|-------------|
| `total_calls` | `GET /dashboard/stats` |
| `calls_today` | `GET /dashboard/stats` |
| `average_call_duration` | `GET /dashboard/stats` |
| `active_rooms` | `GET /rooms` |
| `recent_calls` | `GET /dashboard/calls` |

**Features:**
- 4 animated stat cards (Total Calls, Calls Today, Avg Duration, Active Rooms)
- **Calls Per Day bar chart** (Chart.js) — aggregates calls from `/dashboard/calls` by UTC date, gradient fill
- **Recent Calls table** — shows the 8 most recent calls with Call ID, status badge, duration, date
- All stat values are formatted (seconds → `Xm Ys`, ISO timestamps → human-readable)

---

### 2. Knowledge Base
**APIs used:**
| Action | API Endpoint |
|--------|-------------|
| List documents | `GET /knowledge/list` |
| Upload document | `POST /knowledge/upload` (multipart/form-data) |
| Delete document | `DELETE /knowledge/{doc_id}` |

**Features:**
- **Upload button** + **drag-and-drop zone** — accepts `.pdf`, `.txt`, `.md` files
- Real-time **animated progress bar** during upload
- File type validation before sending request
- Document list with per-type emoji icons (📕 PDF, 📃 TXT, 📝 MD)
- Each row shows: icon, filename, upload date, doc_id preview, 🗑️ Delete button
- Delete triggers a confirmation dialog, calls the backend, removes the DOM element with a fade-out animation
- Empty-state illustration when no documents are uploaded

---

### 3. Call History
**APIs used:**
| Action | API Endpoint |
|--------|-------------|
| Load all calls | `GET /dashboard/calls` |

**Features:**
- Full call history table: Call ID, Status badge, Duration, Date
- **Live client-side search** — filters by Call ID or status text as you type
- **Status dropdown filter** — Completed / Canceled / Failed
- Refresh button to re-fetch from API
- Global topbar search also redirects here and applies the search

---

## Design System

| Token | Value |
|-------|-------|
| Background | `#0d0f14` |
| Surface | `#151820` |
| Surface 2 | `#1c2030` |
| Border | `#252a38` |
| Accent | `#3d6eff` |
| Accent Hi | `#5f88ff` |
| Green (Completed) | `#23c882` |
| Red (Canceled) | `#ff445a` |
| Font | Inter (Google Fonts) |

---

## Verification Checklist

| Test | Expected Result |
|------|----------------|
| Dashboard loads stats | 4 stat cards populate with real numbers |
| Calls Per Day chart | Bar chart renders with dates on X-axis |
| Recent calls table | ≤8 recent call rows appear |
| Knowledge base lists docs | Uploaded docs appear with name + date |
| Upload PDF via button | Progress bar animates, doc appears in list |
| Upload via drag-and-drop | Same result as button upload |
| Delete document | Doc removed from list, success toast shown |
| Call history loads | All calls appear in table |
| Search filter | Table narrows as you type |
| Status filter | Only matching status rows show |

---

## Files Created

| File | Purpose |
|------|---------|
| `dashboard/index.html` | Complete SPA frontend (all 3 pages) |
| `dashboard_frontend_report.md` | This report |

---

## APIs Consumed (No Backend Changes)

> [!IMPORTANT]
> No modifications were made to `server.py`, `knowledge_base.py`, or any other backend file.

- `GET /dashboard/stats`
- `GET /dashboard/calls`
- `GET /rooms`
- `GET /knowledge/list`
- `POST /knowledge/upload`
- `DELETE /knowledge/{doc_id}`

---

## How to Run

1. Start the FastAPI backend:
   ```bash
   cd /Users/ahmad/Gemini/antigravity/Callindri/voxagent
   source venv/bin/activate
   python server.py
   ```

2. Open the dashboard:
   ```bash
   open /Users/ahmad/Gemini/antigravity/Callindri/dashboard/index.html
   ```

> [!NOTE]
> CORS is already configured with `allow_origins=["*"]` in the backend, so direct file-open works without a dev server.
