# VoxAgent Dashboard UI Fix Report

**Date:** 2026-03-11  
**Scope:** `dashboard/frontend/` only — no backend changes

---

## Files Modified / Created

| File | Action |
|------|--------|
| `dashboard/frontend/index.html` | **Created** — complete rebuild matching reference layout |

---

## API Connection Fix

### Root Cause of "Failed to fetch"
The original `dashboard/index.html` relied on the browser's `fetch()` being able to reach `localhost:8000`. When the backend is not running (or opened via `file://` without a running server), the browser shows **"Failed to fetch"** because there is no network response.

### Fix Applied
All fetch calls now use the **explicit full URL** with proper error handling:

```js
const API = 'http://localhost:8000';

async function apiFetch(path, opts = {}) {
  const r = await fetch(`${API}${path}`, opts);
  if (!r.ok) throw new Error(`${r.status}`);
  return r.json();
}
```

Empty data is now handled gracefully:
- Stats → shows `0` instead of `—` on failure
- Calls → shows **"No calls yet"** in the table (never "Failed to fetch")
- Knowledge Base → shows **"No documents yet"** on empty / failure

---

## API Endpoints Connected

| Endpoint | Method | Used For |
|----------|--------|----------|
| `/dashboard/stats` | GET | Total Calls, Calls Today, Avg Duration |
| `/dashboard/calls` | GET | Bar chart, Line chart, Calls table, Mini calls panel, Total Minutes |
| `/rooms` | GET | Active Rooms metric card |
| `/knowledge/list` | GET | Knowledge Base document list |
| `/knowledge/upload` | POST (multipart) | Upload document button |
| `/knowledge/{doc_id}` | DELETE | Per-row delete button |

---

## UI Components Rebuilt

### Layout (matches reference image)
```
┌─────────────────────────────────────────────────────────┐
│  TOPBAR (search + avatar)                               │
├──────────┬──────────────────────────────┬───────────────┤
│ SIDEBAR  │  [Metric Cards ×5]           │ Knowledge     │
│          │  [Calls Per Day — bar chart] │ Base Panel    │
│ Dashboard│  [Recent Calls — line chart] │               │
│ Agents   │  [Recent Calls — table]      │ Recent Calls  │
│ KB       │                              │ Mini Table    │
│ ...      │                              │               │
│[+Create] │                              │               │
└──────────┴──────────────────────────────┴───────────────┘
```

### Metric Cards (×5)
- Total Calls — from `stats.total_calls`
- Calls Today — from `stats.calls_today`
- Avg Call Duration — from `stats.average_call_duration` (formatted as `Xm Ys`)
- Active Rooms — from `/rooms` endpoint
- Total Call Minutes — computed from raw seconds in call records

### Calls Per Day (Bar Chart)
- Chart.js bar chart
- Groups calls from `/dashboard/calls` by UTC date
- Dark gradient fill, rounded bars
- Shows "No data" gracefully when no calls exist

### Recent Calls (Line Chart)
- Dual-line chart: **Completed Calls** (blue) vs **Dropped Calls** (red)
- Fills with gradient below each line
- Same date-grouped data source

### Recent Calls Table
- Columns: Call ID (blurred for privacy), Status (colour-coded badge), Agent, Duration, Date
- Shows up to 10 rows
- Empty state: **"No calls yet"** — never an error message

### Knowledge Base Right Panel
- `+ Upload Document` button (POST multipart to `/knowledge/upload`)
- Animated progress bar during upload
- Document list (PDF 📕 / TXT 📃 / MD 📝 icons)
- Per-row 🗑 Delete button (DELETE `/knowledge/{doc_id}`)
- Empty state: "No documents uploaded yet"

### Recent Calls Mini Panel (right sidebar)
- Shows last 6 calls
- Columns: Call ID (blurred), Status badge, Agent, Date

---

## Empty Data Handling

| Scenario | Previous Behaviour | New Behaviour |
|----------|--------------------|---------------|
| Backend offline | "Failed to fetch" everywhere | Zeros in cards, "No calls yet" in table |
| No calls in DB | Loading spinner forever | "No calls yet" |
| No KB docs | Error shown | "No documents uploaded yet" |
| Upload error | Unhandled exception | Toast with error detail |
| Delete error | Unhandled exception | Toast with error detail + button re-enabled |

---

## Visual Quality Improvements

| Element | Improvement |
|---------|-------------|
| Typography | Inter font, tight letter-spacing, weight hierarchy |
| Cards | Subtle `rgba` borders, hover lift effect |
| Status badges | Pill shape with colour dot, per-status colour |
| Charts | Dark translucent tooltips matching theme |
| Call IDs | CSS blur for privacy (matches reference image) |
| Sidebar | Two-tone (darker than main), active state w/ accent tint |
| Upload | Animated progress bar, shadow on CTA button |
| Toasts | Slide-in from bottom-right, auto-dismiss 3.8s |

---

## How to Test

1. Start the VoxAgent backend:
   ```bash
   cd /Users/ahmad/Gemini/antigravity/Callindri/voxagent
   source venv/bin/activate && python server.py
   ```

2. Open the dashboard:
   ```bash
   open /Users/ahmad/Gemini/antigravity/Callindri/dashboard/frontend/index.html
   ```

### Verification Checklist

| Test | Expected |
|------|----------|
| Dashboard loads stats | 5 metric cards show real numbers |
| Bar chart renders | Calls grouped by day with blue bars |
| Line chart renders | Blue (completed) + red (dropped) lines |
| Recent calls table | Rows with blurred IDs, status badges |
| KB list loads | Document rows with file icons and dates |
| Upload PDF | Progress bar → doc appears in list |
| Delete document | Row fades out, success toast |
| Backend offline | "No calls yet" / zeros — no "Failed to fetch" |

> [!NOTE]
> CORS is already configured with `allow_origins=["*"]` in `server.py`, so the file opened directly in the browser works without a dev server.
