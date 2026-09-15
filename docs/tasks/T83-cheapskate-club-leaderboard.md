# T83 — Cheapskate Club: Leaderboard Opt-In & Extended Profile Integration

Status: Proposed — saved for future implementation  
Depends on: T81 (lifetime usage accounting and commercial savings baseline)  
Size: M  
Evidence: Operator design direction (September 15, 2026):
> *"The flow would be:*  
> *1. In CheapOS’s Usage panel: 'Join the Cheapskate Club.'*  
> *2. Open the browser to connect their X account.*  
> *3. Associate that CheapOS installation with their X identity.*  
> *4. Back in CheapOS, preview exactly which stats will become public.*  
> *5. 'Share my stats' enables syncing and creates their leaderboard entry.*  
> *Connecting X identifies the person; opting in authorizes sharing. No separate leaderboard password or signup form needed.*  
> *The public website’s Join the club button would open CheapOS—or show installation instructions. Someone using CheapOS on multiple computers could link them to the same X account, with controls to disconnect each installation.*  
> *That makes the website the public scoreboard, and CheapOS the place where you join and control participation."*

---

## 1. Outcome & User Experience

A seamless, passwordless bridge between CheapOS and the public **Cheapskate Club** leaderboard website. CheapOS remains the privacy perimeter and control center where operators inspect their exact public profile before publishing.

### Step-by-Step Flow:
1. **Discovery in CheapOS:**
   - In the **Usage & savings** modal, a prominent section invites the operator: **"Join the Cheapskate Club"**.
   - Shows value proposition: *"Claim your spot on the public scoreboard. Connect your X account — no passwords or separate signups required."*
2. **Browser X Authentication:**
   - Operator clicks **"Connect X account"**.
   - CheapOS passes a persistent, anonymous `installation_id` to the browser auth URL (e.g. `https://cheapskate.club/join?installation_id=...`).
   - Operator logs into X (Twitter OAuth); the leaderboard service associates their verified X identity (`@handle`, name, avatar) with that `installation_id`.
3. **Deep-Link Return to CheapOS:**
   - The browser redirects back to CheapOS (or deep link `cheapos://cheapskate-club?token=...` / localhost callback).
   - CheapOS records the linked X profile in `club_profile.json`.
4. **Transparent Public Stats Preview:**
   - CheapOS displays an explicit, interactive preview of what will be shared:
     - **Identity:** Avatar, display name, `@handle`.
     - **Headline Metrics:** Total reported tokens, zero-cost tokens & percentage (e.g., 96%), accounted API spend ($0.059), and estimated commercial savings ($107.96).
     - **Extended Profile (Model Breakdown):** Verified counts for top models used (e.g., DeepSeek Chat 11M, Gemini 3.1 Flash Lite 8M, Claude Haiku 3.1M, Qwen 2.5 Coder 383k).
     - **Outcomes:** Accepted jobs and merged runs.
     - **Privacy Guarantee:** *"Prompts, file paths, repository code, and task titles are NEVER collected or shared. Only verified numerical token counters and model names."*
5. **Operator Authorizes Sharing:**
   - Clicking **"Share my stats"** enables syncing and creates/updates their leaderboard entry.
   - Status updates to **Active on Leaderboard** with a link to their public profile (`cheapskate.club/@handle`).
   - Controls available: **"Sync now"**, **"Pause sharing"**, and **"Disconnect this installation"**.
6. **Multi-Installation Management:**
   - An operator using CheapOS across multiple computers (e.g. laptop and desktop) connects both to the same X account.
   - The leaderboard aggregates their cumulative verified savings.
   - Each computer retains an independent control to disconnect or pause without affecting other devices.

---

## 2. Technical Architecture

### Backend (`cheapos/`)
- **Model Usage Aggregation:**
  In `cheapos/lifetime_usage.py`, expose the `models` dictionary in `summary()` (model identifier, tokens, requests, category).
- **Persistent Club Profile Storage (`cheapos/club.py`):**
  Store installation association in `club_profile.json`:
  ```json
  {
    "schema_version": 1,
    "installation_id": "uuid-v4",
    "installation_name": "MacBook Pro",
    "x_identity": {
      "handle": "carlosa8c",
      "name": "Carlos Cabrera",
      "avatar_url": "https://pbs.twimg.com/...",
      "linked_at": "2026-09-15T16:00:00Z"
    },
    "sync_enabled": false,
    "last_synced_at": null,
    "leaderboard_url": "https://cheapskate.club"
  }
  ```
- **Local HTTP Endpoints (`cheapos/server.py`):**
  - `GET /api/club/status`: Link status, X profile, installation ID, sync state, and exact public preview payload.
  - `POST /api/club/link`: Associates installation with X profile token returned from auth flow.
  - `POST /api/club/sync`: Toggles `sync_enabled` and pushes signed/verified stats to the leaderboard API.
  - `POST /api/club/disconnect`: Unlinks the installation and disables sync.

### Frontend UI (`dist/`)
- In `dist/lifetime_usage.js` & `dist/lifetime_usage.css`:
  - Component states:
    1. *Unlinked:* "Join the Cheapskate Club" card with Connect button.
    2. *Linked (Preview):* Displays connected X identity, full public preview (tokens, savings, model breakdown), "Share my stats" button, and "Disconnect".
    3. *Active Sharing:* Live sync indicator, last sync timestamp, "Sync now", "Pause sharing", and "Disconnect".
- In `dist/app.js`:
  - Handle deep-link / URL parameter query (`?club_token=...` or `?action=club`) to automatically open the Usage modal on return from OAuth.

---

## 3. Verification Plan
- Unit tests in `tests/test_club.py` testing installation ID generation, linking, payload generation, and disconnect.
- UI unit tests in `tests/test_lifetime_usage_ui.js` covering unlinked, preview, and sharing states.
- End-to-end browser walkthrough testing the full link, preview, and sync flow.
