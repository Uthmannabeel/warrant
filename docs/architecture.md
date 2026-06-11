# Warrant — Architecture

Warrant is a **licensing authority for AI agents**. Evals tell you how smart an agent is;
Warrant tells production *how much rope to give it* — and takes the rope back. An agent earns a
**license per action class** by passing exams in a proving ground, graded against its own
**falsifiable predictions**. Licenses are revocable on a failure and invalidated when the
agent's brain changes underneath you (model/prompt drift).

## Topology (hybrid)

The sandbox holds the **live telemetry** (a system you can deliberately break and heal).
**Splunk Cloud is the reasoning brain**, reached entirely through the **Splunk MCP Server**.
And Warrant **exposes its own MCP server**, so the trust gate becomes infrastructure any other
agent can call.

```mermaid
flowchart LR
    subgraph LOCAL["Local / your laptop"]
        SB["Sandbox flight-simulator<br/>(FastAPI)<br/>parameterised fault injection"]
        PG["Proving Ground<br/>manufacture exams · grade vs. prediction"]
        W["Warrant control loop<br/>sense · context · diagnose · predict<br/>gate · act · verify · ledger"]
        CERT["Certification<br/>License per action class<br/>Wilson bound · Brier calibration · drift"]
        L[("Trust ledger<br/>graded outcomes")]
    end

    subgraph SPLUNK["Splunk Cloud"]
        MCP["Splunk MCP Server"]
        Q["splunk_run_query<br/>(SPL over _internal)"]
        AI["AI Assistant hosted models<br/>saia_generate_spl / saia_ask_splunk_question"]
        IDX[("Splunk indexes")]
    end

    subgraph EXT["Any external agent"]
        A2["SOAR playbook ·<br/>Splunk Triage/Guided-Response ·<br/>a Claude agent"]
    end

    PG -- "accelerated exams" --> W
    W -- "SENSE / ACT / VERIFY" --> SB
    W -- "CONTEXT via MCP" --> MCP
    MCP --> Q --> IDX
    MCP --> AI
    W -- "record graded outcome" --> L
    L --> CERT
    CERT -- "license: may act autonomously?" --> W
    A2 -- "warrant_request_action (MCP)" --> CERT
    CERT -- "ALLOW / REQUIRE_APPROVAL" --> A2
```

## Three problems Warrant solves that nobody else does

1. **The cold-start paradox** — an agent can't earn trust without acting, and can't be allowed
   to act without trust. **The Proving Ground** manufactures incidents and grades the agent
   *before* it touches production, so trust starts from evidence, not a leap of faith.
2. **The statistical-power problem** — real incidents are too rare to certify on; five
   production successes is an anecdote. The proving ground produces *dozens* of graded outcomes
   in seconds, so the Wilson confidence bound is built on a real sample.
3. **Silent model drift** — your agent's model gets updated overnight and every trust
   assumption is now stale. Warrant **fingerprints** the brain (model id + prompt version) and
   pins each license to it; when the fingerprint changes, the license drops to PROVISIONAL and
   the new brain must re-certify.

## The control loop, step by step

| # | Step | What happens | Splunk / AI touchpoint |
|---|------|--------------|------------------------|
| 1 | **SENSE** | Read live metrics (`error_rate`, `db_connections`, `p95_latency_ms`) | — |
| 2 | **CONTEXT** | Pull real operational context | **MCP `splunk_run_query`** over `_internal`; prefers **`saia_generate_spl`** hosted model to author the SPL |
| 3 | **DIAGNOSE** | A brain (heuristic or LLM) proposes one bounded remediation **and a confidence** | optional Google Gemini |
| 4 | **PREDICT** | Commit to a **falsifiable** forecast band *before* acting — a control limit learned from healthy data | — |
| 5 | **GATE** | Allow only reversible, in-blast-radius actions; act autonomously only with a valid **license** | certification |
| 6 | **ACT** | Execute the bounded remediation | sandbox control API |
| 7 | **VERIFY** | Compare the live metric against the forecast band | — |
| 8 | **LEDGER** | Record the graded outcome (correct?, stated confidence, brain fingerprint); re-certify the license | certification |

## What makes a license

A license for an action class is granted only when **three independent conditions** hold:

- **Confidence** — the Wilson score lower bound on the hit-rate clears the threshold, so one
  lucky pass can never license an action.
- **Evidence** — there is a minimum body of graded outcomes behind it.
- **Calibration** — the **Brier score** (mean squared error between stated confidence and
  reality) is low enough. An agent that is *confidently wrong* fails calibration even if its raw
  hit-rate looks acceptable — so trust cannot be bought with bravado.

States: `PROVISIONAL` (training / re-certifying) → `LICENSED` (autonomous) → `SUSPENDED`
(was licensed, a failure revoked it). A fingerprint change forces any license back to
PROVISIONAL.

## Why the Splunk pieces are load-bearing

- **Splunk MCP Server is the single interface to Splunk** — every read of Splunk data and every
  hosted-model call goes through it (Best MCP Server Use), keeping the agent decoupled from
  Splunk internals.
- **Warrant as an MCP server** turns the trust gate into ecosystem infrastructure: Splunk's own
  agentic roadmap ships agents that *act* but offers no measure of *when* a human can let go —
  `warrant_request_action` is that measure, callable by any of them.
- **The trust ledger is SPL-native**: the same Wilson computation runs as a saved search inside
  Splunk (see `splunk/trust_ledger.spl`), so on a real tenant the license registry lives in a
  Splunk dashboard.
