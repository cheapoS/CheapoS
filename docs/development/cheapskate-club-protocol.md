# Cheapskate Club: Cryptographic Attestation & Leaderboard Protocol Specification

**Document Version:** 1.0.0  
**Target Audience:** Developer / AI Agent building the private **Cheapskate Club Leaderboard App** (`cheapskate.club`).  
**Client Implementation:** CheapOS Core (`cheapos/club.py`, `cheapos/lifetime_usage.py`, `dist/lifetime_usage.js`).  
**Security Classification:** Public Open-Source Protocol (Client side contains zero static secrets).

---

## 1. Executive Summary & Security Model

The **Cheapskate Club** is a public scoreboard celebrating developers who run AI agent workloads at maximum efficiency and near-zero cost.

### The Security Challenge
- **CheapOS is 100% public open-source software.** Any static API key, client secret, or symmetric signing key embedded in the repository would be compromised immediately.
- Anyone can clone CheapOS, edit local files, or mock local numbers.
- If an operator could report arbitrary token counts, the leaderboard would be ruined by fake scores.

### The Solution: Zero-Secret Dynamic Attestation
1. **Human Identity Binding via X (Twitter) OAuth:**
   Instead of email/passwords or open registration forms, participation is tied to a verified Twitter/X identity. The private Leaderboard Server manages the Twitter OAuth credentials.
2. **Ephemeral Pairing Secret:**
   During the OAuth flow, the Leaderboard Server generates a cryptographically secure pairing secret (`sync_secret`, 256-bit random hex). This secret is shared **only** between the Leaderboard database and the local operator's machine (stored in `club_profile.json`, file permissions `0600`).
3. **Deterministic RFC 8785 Canonical JSON & HMAC-SHA256:**
   All stats sent to `/api/v1/sync` are serialized canonically (keys sorted recursively, no whitespace) and signed with HMAC-SHA256 using the pairing secret.
4. **Merkle Tree Proofs & PRF Spot-Checking:**
   CheapOS builds a deterministic SHA-256 Merkle tree over every individual request record in its lifetime ledger. Rather than uploading confidential prompt details or multi-megabyte log files, CheapOS sends the Merkle root and 5 deterministic pseudo-random audit samples chosen by an HMAC PRF. The server verifies that the claimed token totals correspond to valid, chronologically structured execution leaves.
5. **Monotonic Sequence Numbers:**
   Every sync payload carries a strictly increasing `sequence_number` to prevent replay attacks.

---

## 2. The 5-Step Operator Flow & Handshake

The user experience in CheapOS is dead simple: 2 clicks, no manual secret copying, and total privacy transparency.

```
+-----------------------------------------------------------------------------------+
| 1. CheapOS UI (Usage Modal)                                                      |
|    Operator clicks "Connect X account"                                            |
+----------------------------------------+------------------------------------------+
                                         | Opens browser URL:
                                         v /join?installation_id=...&installation_name=...
+-----------------------------------------------------------------------------------+
| 2. Leaderboard Server (cheapskate.club)                                           |
|    - Redirects to X (Twitter) OAuth 2.0 PKCE / OAuth 1.0a                         |
|    - Operator approves access                                                     |
|    - Server receives verified X identity (@handle, name, avatar)                  |
|    - Server generates CSPRNG sync_secret (32 bytes hex)                           |
|    - Server saves user and installation record in DB                              |
+----------------------------------------+------------------------------------------+
                                         | Redirects browser back to local CheapOS:
                                         v http://127.0.0.1:5173/?action=club&club_handle=...&club_secret=...
+-----------------------------------------------------------------------------------+
| 3. CheapOS UI & Local API                                                        |
|    - CheapOS saves identity and secret to club_profile.json (chmod 0600)          |
|    - Displays linked profile and transparent preview of exact public stats        |
+----------------------------------------+------------------------------------------+
                                         | Operator clicks "Share my stats"
                                         v Calls POST /api/club/sync
+-----------------------------------------------------------------------------------+
| 4. CheapOS Backend Client (cheapos/club.py)                                       |
|    - Computes Merkle root over all lifetime ledger requests                       |
|    - Samples PRF audit receipts using sync_secret                                 |
|    - Canonicalizes JSON payload (RFC 8785)                                        |
|    - Signs canonical bytes with HMAC-SHA256(sync_secret)                          |
|    - POSTs payload + signature to https://cheapskate.club/api/v1/sync             |
+----------------------------------------+------------------------------------------+
                                         | HTTP 200 OK
                                         v
+-----------------------------------------------------------------------------------+
| 5. Leaderboard Public Scoreboard                                                  |
|    - Server verifies HMAC-SHA256 signature and Merkle audit samples               |
|    - Updates operator's public page: https://cheapskate.club/@handle              |
|    - Aggregates multi-machine savings if user connects multiple laptops/desktops  |
+-----------------------------------------------------------------------------------+
```

---

## 3. Leaderboard Server API Endpoints

The Leaderboard App backend must implement the following routes:

### 3.1. `GET /join` (Browser Route: OAuth Initiation)
**Purpose:** Entry point when an operator clicks "Connect X account" from CheapOS.

**Query Parameters:**
- `installation_id` (string, UUIDv4): Persistent identifier of the CheapOS installation.
- `installation_name` (string, URL-encoded): Hostname or nickname of the computer (e.g., `MacBook-Pro`).

**Handler Logic:**
1. Check if user already has an active session on `cheapskate.club`.
   - If not authenticated, redirect to Twitter OAuth:
     - Scope: `users.read`, `tweet.read`.
     - Store `installation_id` and `installation_name` in encrypted OAuth `state` cookie/session.
2. Once Twitter OAuth callback completes successfully:
   - Extract Twitter ID, username (`handle`), display name (`name`), and `profile_image_url` (`avatar_url`).
   - Upsert user in `users` table.
   - Generate a cryptographically secure pairing secret:
     ```python
     sync_secret = secrets.token_hex(32)  # 64 hex characters
     ```
   - Upsert installation in `installations` table linked to this `user_id`.
   - Redirect the operator back to their local CheapOS dashboard:
     ```
     http://127.0.0.1:5173/?action=club&club_handle={handle}&club_name={name}&club_avatar={avatar_url}&club_secret={sync_secret}
     ```
     *(Note: If the operator's CheapOS is running on a non-standard port or machine, provide a "Copy Link Token" fallback modal on the web page).*

---

### 3.2. `POST /api/v1/sync` (API Webhook: Stats Ingestion)
**Purpose:** Ingests cryptographically signed usage stats and updates the leaderboard.

**Request Headers:**
- `Content-Type: application/json`
- `X-Club-Signature: <64-char-hex-hmac>`
- `X-Club-Installation-ID: <uuid-v4>`

**Request Body Structure:**
```json
{
  "payload": {
    "schema_version": 1,
    "installation_id": "a9010e9f-6828-4ef7-b5ba-19ee27b36f01",
    "installation_name": "Carloss-MacBook-Pro",
    "operator": {
      "handle": "carlosa8c",
      "name": "Carlos Cabrera",
      "avatar_url": "https://pbs.twimg.com/profile_images/..."
    },
    "sequence_number": 1,
    "timestamp": "2026-09-15T18:00:00.000000+00:00",
    "metrics": {
      "total_reported_tokens": 35912440,
      "zero_cost_free_tokens": 34480000,
      "zero_cost_percentage": 96,
      "paid_metered_tokens": 1432440,
      "accounted_api_spend_usd": 0.059,
      "estimated_commercial_savings_usd": 107.96
    },
    "breakdown_tokens": {
      "public_free_remote": 34480000,
      "account_included_quota": 0,
      "local_hardware": 0
    },
    "models_used": {
      "deepseek/deepseek-chat": {"tokens": 11200000, "requests": 840, "category": "public_free"},
      "google/gemini-3.1-flash-lite": {"tokens": 8400000, "requests": 620, "category": "public_free"},
      "anthropic/claude-3-haiku": {"tokens": 3100000, "requests": 210, "category": "paid"}
    },
    "completed_work": {
      "interactive_jobs": 42,
      "merged_runs": 18
    },
    "merkle_attestation": {
      "root": "7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069",
      "total_requests": 3403,
      "audit_samples": [
        {
          "index": 142,
          "date": "2026-09-12",
          "model": "deepseek/deepseek-chat",
          "tokens": 4210,
          "category": "public_free",
          "leaf_hash": "a4b2c1..."
        }
      ]
    }
  },
  "signature": "8b512c... (64-char hex HMAC-SHA256)"
}
```

**Leaderboard Server Verification Steps:**
1. **Lookup Installation:** Find installation by `payload.installation_id`. Ensure it exists and retrieve its stored `sync_secret` and linked `user_id`.
2. **Reconstruct Canonical JSON:**
   Serialize `payload` using the RFC 8785 algorithm (keys sorted alphabetically, compact delimiters `,` and `:`, UTF-8 encoded).
3. **Verify HMAC Signature:**
   ```python
   expected_sig = hmac.new(sync_secret.encode('utf-8'), canonical_bytes, hashlib.sha256).hexdigest()
   if not hmac.compare_digest(expected_sig, signature):
       return {"error": "Invalid signature"}, 401
   ```
4. **Sequence Number Guard:**
   Ensure `payload.sequence_number > installation.last_sequence_number`. This rejects replayed old payloads.
5. **Timestamp Freshness:**
   Ensure `payload.timestamp` is within an acceptable skew window (e.g. ±15 minutes of server UTC time).
6. **Merkle PRF Audit Sample Validation:**
   For each sample in `payload.merkle_attestation.audit_samples`:
   - Compute `expected_score = hmac.new(sync_secret, f"sample:{sample.index}", sha256).hexdigest()`.
   - Verify that the leaf indices provided are indeed the lowest-scoring indices for this ledger size (spot-check sampling verification).
   - Recompute the `leaf_hash` from the audit item fields and ensure it matches `sample.leaf_hash`.
7. **Database Storage & Aggregation:**
   - Record the sync event snapshot in `sync_events`.
   - Update `installations.last_synced_at`, `total_tokens`, `savings_usd`, `models_json`.
   - Aggregate all active installations belonging to `user_id` to update the user's aggregate rank and public stats.
8. **Response:**
   Return HTTP 200 JSON:
   ```json
   {
     "status": "synced",
     "user_handle": "carlosa8c",
     "sequence_number": 1,
     "public_url": "https://cheapskate.club/@carlosa8c"
   }
   ```

---

### 3.3. `POST /api/v1/disconnect` (Optional: Remote Unlink)
Allows the operator to unlink an installation either from CheapOS or from the web settings.
- If called from CheapOS: requires HMAC-SHA256 signature of `{"action": "disconnect", "installation_id": "...", "timestamp": "..."}`.
- Sets `installation.active = false` and revokes `sync_secret`.

---

### 3.4. Public Scoreboard Endpoints

#### `GET /api/v1/leaderboard`
Returns the public ranking table.
**Query params:**
- `sort`: `zero_cost_tokens` (default), `savings_usd`, `efficiency_ratio`.
- `period`: `all` (default), `30d`, `7d`.
- `page`, `limit`: Pagination.

**Response Structure:**
```json
{
  "top_cheapskates": [
    {
      "rank": 1,
      "handle": "carlosa8c",
      "name": "Carlos Cabrera",
      "avatar_url": "https://pbs.twimg.com/...",
      "badge": "Grand Cheapskate 🏆",
      "zero_cost_tokens": 34480000,
      "total_tokens": 35912440,
      "efficiency_percentage": 96,
      "commercial_savings_usd": 107.96,
      "active_installations": 1,
      "top_models": ["deepseek-chat", "gemini-3.1-flash-lite"],
      "last_synced_at": "2026-09-15T18:00:00Z"
    }
  ]
}
```

#### `GET /@:handle` (Public Profile Page)
Renders the public profile of the operator:
- Visual avatar, X handle, verified link to Twitter/X profile.
- Verified badge: **"Cryptographically Attested"** (indicates valid Merkle roots & HMAC signatures).
- Trophy card: **Commercial Savings ($107.96)** vs **Actual Spend ($0.059)**.
- Efficiency progress bar (e.g. 96% free share).
- Model distribution chart (DeepSeek vs Gemini vs Claude).
- Machine count (e.g. *"2 CheapOS machines connected"*).

---

## 4. Cryptographic Implementation Details

### 4.1. RFC 8785 Canonical JSON Serialization

To ensure identical hash outputs regardless of language (Python client vs Node/TypeScript server), JSON must be serialized deterministically:
1. Object keys sorted by UTF-16 code units (lexicographical byte order).
2. No whitespace around separators (`,` and `:` with zero spaces).
3. UTF-8 character encoding without escaping unescaped characters.
4. Float serialization standard.

#### TypeScript / Node.js Server Implementation:
```typescript
export function canonicalJson(obj: any): string {
  if (obj === null || typeof obj !== 'object') {
    return JSON.stringify(obj);
  }
  if (Array.isArray(obj)) {
    return '[' + obj.map(canonicalJson).join(',') + ']';
  }
  const sortedKeys = Object.keys(obj).sort();
  const pairs = sortedKeys.map(key => {
    return JSON.stringify(key) + ':' + canonicalJson(obj[key]);
  });
  return '{' + pairs.join(',') + '}';
}
```

#### Verification Function:
```typescript
import * as crypto from 'crypto';

export function verifySyncSignature(
  payload: Record<string, any>,
  receivedSignature: string,
  syncSecret: string
): boolean {
  const canonicalString = canonicalJson(payload);
  const hmac = crypto.createHmac('sha256', syncSecret);
  hmac.update(Buffer.from(canonicalString, 'utf-8'));
  const expectedSignature = hmac.digest('hex');

  const a = Buffer.from(receivedSignature, 'utf-8');
  const b = Buffer.from(expectedSignature, 'utf-8');
  if (a.length !== b.length) return false;
  return crypto.timingSafeEqual(a, b);
}
```

### 4.2. Merkle Tree Leaf Construction
In CheapOS, each request receipt leaf is computed as:
```
raw_leaf = "{request_id}:{task_id}:{requested_model}:{served_model}:{input_tokens}:{output_tokens}:{date}:{category}"
leaf_hash = SHA256(raw_leaf.encode("utf-8"))
```
Parent nodes are combined pairwise:
```
parent_hash = SHA256(left_leaf_bytes + right_leaf_bytes)
```
If an odd number of nodes exists at any level, the last node is duplicated (`left + left`).

### 4.3. PRF Deterministic Audit Sampling
To spot-check leaves without uploading the entire ledger:
For each request index `i` from `0` to `N-1`:
```
score = HMAC_SHA256(sync_secret, "sample:{i}")
```
The client sorts by `score` and provides the lowest 5 indices. The server verifies that the indices presented in `audit_samples` correspond to the lowest PRF scores. This guarantees that the client cannot handpick only convenient historical entries.

---

## 5. Recommended Database Schema for the Leaderboard App

Here is a recommended SQLite / PostgreSQL schema for the Leaderboard backend:

```sql
-- Users authenticated via X (Twitter)
CREATE TABLE users (
    id TEXT PRIMARY KEY,                       -- UUID or Twitter numeric ID
    twitter_id TEXT UNIQUE NOT NULL,
    handle TEXT UNIQUE NOT NULL,               -- e.g. 'carlosa8c'
    name TEXT NOT NULL,                        -- e.g. 'Carlos Cabrera'
    avatar_url TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Individual CheapOS installations (operators can connect laptop + desktop)
CREATE TABLE installations (
    id TEXT PRIMARY KEY,                       -- Installation UUID sent by CheapOS
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,                        -- e.g. 'MacBook Pro'
    sync_secret TEXT NOT NULL,                 -- 64-char hex CSPRNG secret
    is_active BOOLEAN DEFAULT TRUE,
    last_sequence_number INTEGER DEFAULT 0,
    last_synced_at TIMESTAMP WITH TIME ZONE,
    
    -- Cached latest metrics
    total_tokens BIGINT DEFAULT 0,
    zero_cost_tokens BIGINT DEFAULT 0,
    paid_tokens BIGINT DEFAULT 0,
    spend_usd NUMERIC(10, 4) DEFAULT 0.0,
    savings_usd NUMERIC(10, 2) DEFAULT 0.0,
    merkle_root TEXT,
    
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Historical sync log (immutable audit snapshots)
CREATE TABLE sync_events (
    id SERIAL PRIMARY KEY,
    installation_id TEXT NOT NULL REFERENCES installations(id) ON DELETE CASCADE,
    sequence_number INTEGER NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    total_tokens BIGINT NOT NULL,
    zero_cost_tokens BIGINT NOT NULL,
    spend_usd NUMERIC(10, 4) NOT NULL,
    savings_usd NUMERIC(10, 2) NOT NULL,
    merkle_root TEXT NOT NULL,
    raw_payload JSONB NOT NULL,
    signature TEXT NOT NULL,
    received_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (installation_id, sequence_number)
);

-- Aggregated User Leaderboard View / Table
CREATE VIEW leaderboard_view AS
SELECT 
    u.id AS user_id,
    u.handle,
    u.name,
    u.avatar_url,
    COUNT(i.id) AS connected_machines,
    COALESCE(SUM(i.total_tokens), 0) AS aggregate_total_tokens,
    COALESCE(SUM(i.zero_cost_tokens), 0) AS aggregate_zero_cost_tokens,
    COALESCE(SUM(i.spend_usd), 0.0) AS aggregate_spend_usd,
    COALESCE(SUM(i.savings_usd), 0.0) AS aggregate_savings_usd,
    CASE 
        WHEN SUM(i.total_tokens) > 0 
        THEN ROUND((SUM(i.zero_cost_tokens)::NUMERIC / SUM(i.total_tokens)::NUMERIC) * 100, 1)
        ELSE 100.0 
    END AS efficiency_percentage,
    MAX(i.last_synced_at) AS last_active_at
FROM users u
LEFT JOIN installations i ON u.id = i.user_id AND i.is_active = TRUE
GROUP BY u.id, u.handle, u.name, u.avatar_url;
```

---

## 6. Real-World Sample Data & Edge Cases

### Real Baseline Metrics (Reference Ledger: Carlos's CheapOS)
- **Total Reported Tokens:** 35,912,440 (35.9M tokens)
- **Zero-Cost / Public-Free Tokens:** 34,480,000 (96.0% efficiency)
- **Total API Spend:** $0.059 ($0.06)
- **Estimated Commercial Savings:** $107.96 (calculated against commercial API baseline rate of ~$3.00/M tokens)
- **Lifetime Requests:** 3,403 requests across 42 interactive jobs and 18 merged pull requests
- **Top Models:**
  1. `deepseek/deepseek-chat` — 11.2M tokens (public free route)
  2. `google/gemini-3.1-flash-lite` — 8.4M tokens (public free route)
  3. `anthropic/claude-3-haiku` — 3.1M tokens (paid / metered)
  4. `qwen/qwen-2.5-coder-32b` — 383k tokens (local Ollama / free route)

### Handling Disconnects and Re-linking
1. **User Pauses Sharing:** CheapOS sets `sync_enabled: false`. No calls are made to `/api/v1/sync`. The user's last synced stats remain on the leaderboard with an older timestamp.
2. **User Disconnects Installation:** CheapOS deletes `x_identity` and `sync_secret` from `club_profile.json`. Next time the user wants to join, a fresh OAuth flow generates a new `sync_secret`.
3. **Multi-Machine Aggregation:** When Carlos adds his second laptop, it sends a distinct `installation_id`. The server associates both installations under `user_id = 'carlosa8c'`. The public profile displays the sum of savings across both machines.

---

## 7. Next Agent Checklist for Building the Leaderboard App

When the next AI agent builds the leaderboard app repository, follow this sequence:
- [ ] Initialize web project (Next.js / SvelteKit / FastAPI + React).
- [ ] Configure Twitter / X OAuth 2.0 application credentials (`TWITTER_CLIENT_ID`, `TWITTER_CLIENT_SECRET`).
- [ ] Implement `GET /join` endpoint to handle incoming `installation_id` from CheapOS.
- [ ] Implement `POST /api/v1/sync` with canonical JSON serialization and HMAC-SHA256 signature verification.
- [ ] Implement Merkle root and PRF audit sampling spot-checks.
- [ ] Build leaderboard UI (`/` and `/@:handle`) using the pre-existing design system and assets.
- [ ] Test end-to-end sync using a test script that posts signed payloads.
