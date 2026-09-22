# The cheapos Club: Cryptographic Attestation & Client Sync Protocol

**Document Version:** 1.0.0  
**Scope:** CheapOS Open-Source Client Implementation
**Module Reference:** [`cheapos/club.py`](../../cheapos/club.py), [`cheapos/lifetime_usage.py`](../../cheapos/lifetime_usage.py), [`dist/lifetime_usage.js`](../../dist/lifetime_usage.js)

---

## 1. Executive Summary & Security Model

**The cheapos Club** is a community scoreboard celebrating developers who run AI coding workloads at near-zero cost using free-tier routes and local models.

### Open-Source Security Principles
1. **Zero Hardcoded Secrets:** CheapOS is open source; no static private keys, master signing keys, or server API secrets exist in this repository.
2. **Ephemeral Pairing Secret:** When an operator connects their X account, the community server issues a runtime pairing secret (`sync_secret`, 256-bit CSPRNG hex string) sent only to the operator's local instance. This secret is stored locally in `club_profile.json` with file permissions `0600`.
3. **Deterministic Canonical JSON:** All sync payloads use deterministic RFC 8785 canonical serialization (lexicographically sorted dictionary keys, no whitespace around separators) to guarantee identical cross-language cryptographic signatures between Python and TypeScript.
4. **Merkle Tree Proofs & PRF Sampling:** Rather than uploading multi-megabyte audit files or raw task transcripts, CheapOS computes a deterministic SHA-256 Merkle root across all chronological request receipts in the lifetime ledger. The payload includes 5 deterministic pseudo-random audit sample leaves selected via an HMAC PRF.
5. **Replay Protection:** A strictly increasing `sequence_number` in each signed payload prevents replay attacks.
6. **Strict Privacy Perimeter:** Prompts, task titles, code snippets, project paths, and API keys are **never** collected or shared. Only verified numerical token counters, model identifiers, and completion counts are transmitted.

---

## 2. Operator Flow & Handshake

```
+-----------------------------------------------------------------------------------+
| 1. CheapOS UI (Usage & Savings Modal)                                             |
|    Operator clicks "Connect X account"                                            |
+----------------------------------------+------------------------------------------+
                                         | Opens browser:
                                         v /join?installation_id=...&installation_name=...
+-----------------------------------------------------------------------------------+
| 2. Community Leaderboard Server                                                   |
|    - Authenticates operator's X (Twitter) identity via OAuth 2.0 PKCE             |
|    - Generates 256-bit pairing secret (sync_secret)                               |
|    - Records installation_id <-> user mapping in server database                  |
+----------------------------------------+------------------------------------------+
                                         | Redirects browser back to local CheapOS:
                                         v http://127.0.0.1:5173/?action=club&club_handle=...&club_secret=...
+-----------------------------------------------------------------------------------+
| 3. Local CheapOS Core & UI                                                        |
|    - Stores pairing secret securely in club_profile.json (chmod 0600)             |
|    - Displays linked profile and transparent preview of exact public stats        |
+----------------------------------------+------------------------------------------+
                                         | Operator clicks "Share my stats"
                                         v (Calls local POST /api/club/sync)
+-----------------------------------------------------------------------------------+
| 4. CheapOS Sync Client (cheapos/club.py)                                          |
|    - Builds Merkle root from lifetime request receipts                            |
|    - Deterministically samples 5 PRF audit leaves                                 |
|    - Canonicalizes JSON payload (RFC 8785)                                        |
|    - Signs canonical payload using HMAC-SHA256(sync_secret)                       |
|    - Pushes signed payload to community ingest endpoint                           |
+-----------------------------------------------------------------------------------+
```

---

## 3. Cryptographic Algorithms

### 3.1. Canonical JSON Serialization (RFC 8785)
All payload serialization sorts dictionary keys lexicographically at every depth, eliminates all whitespace between delimiters, and uses UTF-8 encoding:

```python
def canonical_json(data):
    def sort_keys(obj):
        if isinstance(obj, dict):
            return {k: sort_keys(v) for k, v in sorted(obj.items())}
        if isinstance(obj, list):
            return [sort_keys(v) for v in obj]
        return obj

    return json.dumps(sort_keys(data), separators=(',', ':'), ensure_ascii=False, allow_nan=False)
```

### 3.2. Merkle Tree Leaf Generation
For each recorded request in the lifetime ledger, the leaf hash is computed as:
```
leaf = SHA256("{request_id}:{task_id}:{requested_model}:{served_model}:{input_tokens}:{output_tokens}:{date}:{category}")
```
Tree levels are iteratively hashed pairwise until a single 32-byte Merkle root is formed:
```
parent = SHA256(left_leaf_bytes + right_leaf_bytes)
```
If an odd number of leaves exists at any level, the final leaf is duplicated (`left + left`).

### 3.3. Deterministic PRF Audit Sampling
To spot-check leaves without disclosing full user history:
```python
score = hmac.new(sync_secret.encode('utf-8'), f"sample:{index}".encode('utf-8'), hashlib.sha256).hexdigest()
```
The client sorts all ledger indices by their PRF score and selects the 5 lowest-scoring indices to include in the payload. The server validates that the submitted samples correspond to the expected deterministic PRF scores.

---

## 4. Signed Sync Payload Schema

When syncing, CheapOS transmits an HTTP POST to the leaderboard server:

**Headers:**
- `Content-Type: application/json`
- `X-Club-Signature: <64-char-hex-hmac>`
- `X-Club-Installation-ID: <uuid-v4>`

**Payload Body (`payload`):**
```json
{
  "schema_version": 1,
  "installation_id": "11111111-2222-3333-4444-555555555555",
  "installation_name": "Workstation-1",
  "operator": {
    "handle": "operator",
    "name": "Operator Name",
    "avatar_url": "https://example.com/avatar.jpg"
  },
  "sequence_number": 1,
  "timestamp": "2026-09-15T18:00:00.000000+00:00",
  "metrics": {
    "total_reported_tokens": 15420000,
    "zero_cost_free_tokens": 15000000,
    "zero_cost_percentage": 97,
    "paid_metered_tokens": 420000,
    "accounted_api_spend_usd": 0.12,
    "estimated_commercial_savings_usd": 45.00
  },
  "breakdown_tokens": {
    "public_free_remote": 14500000,
    "account_included_quota": 0,
    "local_hardware": 500000
  },
  "models_used": {
    "deepseek/deepseek-chat": {"tokens": 10000000, "requests": 750, "category": "public_free"},
    "google/gemini-3.1-flash-lite": {"tokens": 4500000, "requests": 320, "category": "public_free"},
    "qwen/qwen-2.5-coder-32b": {"tokens": 500000, "requests": 80, "category": "local"}
  },
  "completed_work": {
    "interactive_jobs": 25,
    "merged_runs": 12
  },
  "merkle_attestation": {
    "root": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "total_requests": 1150,
    "audit_samples": [
      {
        "index": 42,
        "date": "2026-09-12",
        "model": "deepseek/deepseek-chat",
        "tokens": 3200,
        "category": "public_free",
        "leaf_hash": "a1b2c3d4e5f6..."
      }
    ]
  }
}
```

---

## 5. Local CheapOS HTTP API

CheapOS exposes the following local endpoints:

- `GET /api/club/status`: Returns linking status, connected X profile, installation ID, sync state, and exact public preview payload. (Also embedded into `GET /api/lifetime-usage` for single-fetch UI rendering).
- `POST /api/club/link`: Stores operator X identity and runtime pairing secret.
- `POST /api/club/sync`: Toggles `sync_enabled` and pushes signed attestation to the configured leaderboard endpoint.
- `POST /api/club/disconnect`: Clears local credentials and resets profile to unlinked state.
