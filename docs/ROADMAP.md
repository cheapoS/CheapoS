# cheapoS Roadmap: Empowering Smaller Models & Durable Workflows

**North Star:**
> Give cheapoS a task, have a natural conversation when needed, and receive reviewed work ready for your approval — without having to understand or repair its internal machinery.

---

## Core Milestones

### 1. Reliable small changes (Current Milestone)
* **What we strengthen:** Editing tools, actionable errors, retained task intent.
* **What “done” looks like:** A README edit or small bug fix finishes without repeated reads, placement questions, or manual rescue.
* **Key capabilities:**
  - `append_text` tool for straightforward end-of-file additions.
  - Actionable `replace_text` errors returning exact match counts and line numbers.
  - Interactive implementation intent recognized so workers do not prematurely surrender to conversational answers.
  - Standalone affirmative prompts ("sure", "ok") continuing the original goal rather than replacing it.

### 2. A conversation that carries work forward
* **What we strengthen:** Distinguish new requests, corrections, questions, and “continue.” Preserve the objective through pauses and handoffs.
* **What “done” looks like:** “Use a different separator,” “what happened?” and “continue” each produce the appropriate behavior in the same task.
* **Key capabilities:**
  - Robust classification of follow-up intent (steer vs clarification vs query).
  - Preserving working approach and open findings across turns.

### 3. A dependable finish line
* **What we strengthen:** Connect implementation → checks → independent review → operator approval → commit. Bind evidence to the actual changes.
* **What “done” looks like:** Completed work reaches your review automatically. Asking for changes returns it to implementation, and unchanged passing checks remain reusable.
* **Key capabilities:**
  - Clean automatic transitions from passing checks into review without extra chat turns.
  - Reusable check digests across edits that touch only comments or whitespace.

### 4. Recovery that earns its keep
* **What we strengthen:** Separate provider failures, tool errors, failing tests, and genuine missing information. Give each a specific recovery path.
* **What “done” looks like:** A temporary failure resumes from saved progress. When cheapoS needs you, it explains the exact decision required and offers useful actions.
* **Key capabilities:**
  - Differentiated error categories with dedicated recovery procedures.
  - Bounded coordinator assistance for stalled workers without consuming excessive turns.

### 5. Predictable model routing
* **What we strengthen:** Provider-wide cooldowns, transport preferences, practical model suitability, and context-preserving handoffs.
* **What “done” looks like:** A failing provider yields to an eligible alternative promptly, without repeated probing or changes to your spending authorization.
* **Key capabilities:**
  - Route health tracking that distinguishes model errors from transient network issues.
  - Preserving conversation state across automatic model handoffs.

### 6. Unattended work you can trust
* **What we strengthen:** Carry a finite plan through implementation, repair, review, and branch completion.
* **What “done” looks like:** Several representative tasks finish without operator intervention. Interrupted runs recover correctly, and every intervention is recorded when one is needed.
* **Key capabilities:**
  - Bounded item loops with deterministic escalation.
  - Structured blocker reporting with evidence capture.

### 7. An app that explains itself
* **What we strengthen:** Onboarding, persisted configuration, visible progress, readable review, and clear completion.
* **What “done” looks like:** A new user can connect providers, finish a small task, understand any interruption, and approve the result without outside help.
* **Key capabilities:**
  - Clear visual distinction between live streaming, tool exploration, and final answers.
  - Intuitive approval controls and permission scopes.
  - Explicit **This chat / Project defaults / New chat defaults** settings, with
    shared connections kept separate. [Design](design/settings-system.md) and
    [implementation task T91](tasks/T91-settings-system.md) are ready for implementation.

### 8. Measured efficiency
* **What we strengthen:** Compare model combinations, context size, review churn, latency, and free/paid usage.
* **What “done” looks like:** We can show which configuration completes comparable work with fewer requests and less paid usage—not merely consumes lots of free tokens.
* **Key capabilities:**
  - Lifetime metrics and token provenance reporting.
  - Real-world efficiency benchmarking across free and paid model tiers.

---

## Complementary High-Value Milestones

Based on cheapoS's architecture and the challenges smaller models face, two additional milestones should follow:

### 9. Context & Prompt Budget Discipline (Small-Model Context Hygiene)
* **What we strengthen:** Compacting stale tool outputs, pruning duplicate file readings, and keeping prompt token overhead compact.
* **What “done” looks like:** Smaller models (e.g. 7B–14B models) do not degrade in performance after 5+ turns because context remains lean and focused.

### 10. Local-First & Multi-Provider Resilience (Ollama & OmniRoute Queueing)
* **What we strengthen:** Managing local GPU memory, shared inference slots, and smooth failover between local models and free cloud routes.
* **What “done” looks like:** An interrupted local Ollama run or full inference slot queues gracefully without dropping user requests or requiring app restarts.

---

## Iteration Protocol

For each milestone:
1. **Define** concrete behaviors and acceptance checks.
2. **Implement** changes on a scoped feature branch.
3. **Validate** with fast, focused unit and integration tests.
4. **Run** a small real-world trial in cheapoS.
5. **Record** results: what finished, what failed, and where user intervention occurred.
