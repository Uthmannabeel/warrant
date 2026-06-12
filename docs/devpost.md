# Warrant — Devpost submission

**Tagline:** A licensing authority for AI agents. Evals tell you how smart an agent is — Warrant
tells production *how much rope to give it*, and takes the rope back the moment a prediction
fails or the model changes underneath you.

**Track:** Observability
**Tech:** Splunk MCP Server (client *and* server) · Splunk AI Assistant (saia) tools · Google
Gemini (optional brain) · Python / FastAPI

**Links:**
- 🌐 Website: https://warrant-chi.vercel.app · live demo replay: https://warrant-chi.vercel.app/demo.html
- 💻 Source code: https://github.com/Uthmannabeel/warrant
- 🎬 Demo video: *(add YouTube/Vimeo link here before submitting)*

---

## Inspiration

Splunk's own 2026 roadmap is full of agents that *act* — a Triage Agent, a Guided Response
Agent, an Autonomous Response Agent. Every one of them is marketed the same way: *"transparent,
auditable, and under analyst control."* Which quietly admits the unsolved problem: there is no
mechanism that decides **when the human can let go.** Across the whole industry the answer to
"can this agent act on its own yet?" is a vibe, a policy, or "never, officially."

We think trust shouldn't be a vibe. It should be a *measured quantity*, earned the way a pilot
earns a license — in a simulator, under graded emergencies — not by crashing real planes.
Warrant is that licensing authority.

## What it does

Warrant issues a **license per action class** (e.g. `restart_connection_pool`). An agent earns
one only by passing exams in a **proving ground**, and a license is granted only when three
independent conditions hold:

1. **Confidence** — the Wilson score lower bound on its hit-rate clears a threshold (so one
   lucky success can never license an action).
2. **Evidence** — enough graded outcomes stand behind it.
3. **Calibration** — its **Brier score** is low: when it says it's 90% sure, it had better be
   right about 90% of the time. A confidently-wrong agent fails here even with a decent hit-rate.

Every outcome is graded against the agent's **own falsifiable prediction** — a control limit
*learned from the system's healthy data* — committed *before* it acts. Reality, not the model,
decides if it was right. Licenses are **revoked** when a production prediction is violated, and
**invalidated** when the agent's brain changes (a new model id or prompt), because the agent you
trusted last night may not be the agent running this morning.

The whole story is one screen and four buttons:

- **① Proving ground** — the agent sits ~15 manufactured incidents in seconds and earns a
  license per action class (provisional → licensed), without touching production.
- **② Production** — a real leak arrives; the agent is licensed, so it acts autonomously and is
  proven right. Then a **decoy** arrives: the obvious fix is wrong, its prediction is violated,
  it says *"I was wrong,"* escalates, a human-approved rollback recovers — and the license is
  **suspended**.
- **③ Model updated overnight** — the brain's fingerprint changes; every license drops to
  **provisional**. Nothing else in ops notices a silent model swap. Warrant does.
- **④ Re-certify** — fresh exams re-earn the licenses under the new brain.

## How it uses Splunk

- **Splunk MCP Server — as a client.** Every read of Splunk data and every hosted-model call
  goes through the MCP Server (`splunk_run_query` over `_internal`, `saia_generate_spl` /
  `saia_ask_splunk_question`). The agent is decoupled from Splunk internals and speaks only MCP.
- **Warrant *as* an MCP server.** Warrant exposes its trust gate as MCP tools
  (`warrant_request_action`, `warrant_check_license`, `warrant_report_outcome`,
  `warrant_list_licenses`). Any external agent — a SOAR playbook, Splunk's own Triage / Guided
  Response agents, a bespoke Claude agent — can ask Warrant *"am I allowed to do this?"* and get
  a verdict grounded in that action's real, calibration-checked track record. We ship a working
  proof (`warrant.mcp_demo`) where an independent agent earns, uses, and loses autonomy purely
  over MCP.
- **The trust ledger is SPL-native.** `splunk/trust_ledger.spl` reproduces the exact Wilson +
  Brier licensing math as a saved search, so on a real tenant the license registry is a Splunk
  dashboard the platform owns and audits.

## How we built it

- **Python + FastAPI** for the agent loop, a parameterised "flight simulator" sandbox (a system
  you can break at many severities), the proving ground, a self-contained live dashboard (no
  CDNs), and the Warrant MCP server (FastMCP).
- **Forecasting** uses a 4-sigma statistical control limit learned from healthy telemetry — the
  same statistical-process-control idea behind Splunk's own anomaly detection.
- **Trust** is a Wilson score lower bound per action class; **calibration** is a Brier score;
  **drift** is a fingerprint (model id + prompt version) pinned to each license.
- **The brain is pluggable.** A deterministic heuristic or Google Gemini can drive diagnosis —
  the safety harness is identical either way, which is the whole point: Warrant makes *any*
  fallible brain safe to act. If the LLM is unavailable, the heuristic takes over so the system
  never stalls.

## Challenges we ran into

- Free Splunk Cloud trials don't expose external ingestion (no HEC, no management port), so we
  adopted a hybrid topology: the sandbox holds live telemetry, and Splunk is the reasoning brain
  reached through MCP over real `_internal` data. The SPL trust ledger is ready for a HEC tenant.
- A naive hit-rate would grant autonomy after one lucky success, and a high hit-rate can still
  hide a badly-calibrated agent — so we moved to a Wilson confidence bound *and* a Brier
  calibration gate.
- Corporate TLS interception broke every HTTPS client until we routed Python through the OS
  trust store.

## Accomplishments we're proud of

- A genuinely *agentic* loop where an LLM can act on a live system — wrapped in a safety
  architecture that makes that safe: falsifiable predictions, reversible-only actions, earned
  and revocable per-action licenses, and **drift detection** that no shipping ops tool has.
- A demo that proves the point most demos avoid: the agent being **wrong**, catching itself,
  losing its license, and re-earning it after a model change.

## What we learned

The bottleneck for autonomous operations is not model intelligence — it's calibrated, auditable
*trust*. Framing an ops agent as a Popperian system that must state how it could be proven
wrong, then licensing it the way we license pilots, turns "trust" from a leap of faith into a
number you can put on a dashboard.

## What's next

- Telemetry natively in Splunk (HEC) on a non-trial tenant, so the SPL trust ledger drives a
  real Splunk license-registry dashboard end to end.
- More action classes and per-environment proving-ground scenarios.
- Wiring `warrant_request_action` in front of a Splunk SOAR playbook so a real Splunk agent is
  gated by its own earned license.
