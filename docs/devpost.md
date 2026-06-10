# Warrant — Devpost submission

**Tagline:** An autonomous remediation agent that *earns the right to act* — judged not by how
smart it sounds, but by whether its falsifiable predictions survive contact with reality.

**Track:** Observability
**Tech:** Splunk MCP Server · Splunk AI Assistant (saia) tools · Google Gemini · Python/FastAPI

---

## Inspiration

Every "AI for operations" tool shipping today is a read-only advisor: it reads your logs,
suggests a fix, and then a human does the scary part. Why? Because an LLM that is confidently
wrong while holding write access to production can cause an outage worse than the one it was
fixing. The hard, unsolved problem in *agentic* operations isn't diagnosis — it's **trust**.
How do you let an autonomous agent actually *act*, safely? Warrant is our answer.

## What it does

Warrant runs a closed control loop over a live system and is allowed to act autonomously
**only to the degree its past predictions have proven correct** — the way you'd trust a
surgeon or a pilot.

For every incident it:
1. **Senses** the live telemetry.
2. **Pulls real Splunk context** through the Splunk MCP Server (SPL over `_internal`; it will
   use the AI Assistant hosted model to author that SPL where the tenant exposes it).
3. **Diagnoses** with a real LLM agent (Google Gemini) that proposes one bounded remediation.
4. **Commits to a falsifiable prediction** — a control limit *learned from the system's
   healthy data* — *before* acting. This is the keystone: it states, in advance, exactly what
   would prove it wrong.
5. **Gates** the action to a reversible, bounded blast radius.
6. **Acts**, then **verifies** reality against its own forecast band.
7. If reality diverges, it declares *"I was wrong,"* **escalates**, and self-corrects.
8. **Records the outcome** in a trust ledger. Autonomy is gated on a Wilson confidence lower
   bound plus a minimum sample size, so one lucky success can never grant autonomy.

A live dashboard shows the agent's reasoning, the trust meter graduating to AUTONOMOUS, and a
chart of each incident against the learned control limit.

## How we built it

- **Splunk MCP Server** is the single interface to Splunk — every read of Splunk data and AI
  call goes through it (`splunk_run_query`, `saia_generate_spl`, `saia_ask_splunk_question`).
- **Google Gemini** is the diagnosis brain, constrained to a bounded action allow-list and
  wrapped by Warrant's safety harness. If the model is unavailable, a deterministic heuristic
  takes over so the system never stalls.
- **Forecasting** uses a 4-sigma statistical control limit learned from healthy telemetry —
  the same statistical-process-control idea behind Splunk's own anomaly detection.
- **Trust** is a Wilson score lower bound over each action class's track record.
- **Python + FastAPI** for the agent loop, a toy "flight simulator" sandbox (a system you can
  deliberately break and heal), and a self-contained live dashboard (no external CDNs).

## Challenges we ran into

- Free Splunk Cloud trials don't expose external data ingestion (no HEC, no management port),
  so we adopted a hybrid topology: the sandbox holds live telemetry, and Splunk is the
  reasoning brain reached through MCP over real `_internal` data.
- Corporate TLS interception broke every HTTPS client until we routed Python through the OS
  trust store.
- We hardened the credibility of the "trust" mechanism: a naive hit-rate would grant autonomy
  after a single lucky success, so we moved to a Wilson confidence bound with a minimum
  sample size.

## Accomplishments we're proud of

- A genuinely *agentic* loop where an LLM can act on a live system — and a safety architecture
  that makes that safe: falsifiable predictions, reversible-only actions, and earned,
  revocable autonomy.
- A demo that proves the point most demos avoid: the agent being **wrong**, catching itself,
  and safely recovering.

## What we learned

The bottleneck for autonomous operations is not model intelligence — it's calibrated,
auditable trust. Framing an ops agent as a *Popperian* system that must state how it could be
proven wrong turns "trust" from a leap of faith into a measured quantity.

## What's next

- Telemetry natively in Splunk (HEC) on a non-trial tenant, so SPL drives the decision end to
  end and the trust ledger lives in a Splunk dashboard.
- More action classes and per-environment "Teach AI" context.
- Multi-metric forecasts via the Cisco Deep Time Series hosted model.

## How it uses Splunk

Splunk is Warrant's reasoning substrate, accessed exclusively through the **MCP Server**:
real-data SPL via `splunk_run_query`, and hosted-model SPL authoring / Q&A via the
`saia_*` AI Assistant tools. The agent is decoupled from Splunk internals and speaks only MCP.
