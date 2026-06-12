# Warrant

**A licensing authority for AI agents.**

Evals tell you how smart an agent is. Warrant tells production **how much rope to give it** —
and takes the rope back the moment a prediction fails or the model changes underneath you.

An agent earns a **license per action class** the way a pilot earns one: not by crashing real
planes, but by passing graded exams in a **proving ground**. Every exam is judged against the
agent's own **falsifiable prediction** — reality, not the model, decides if it was right. A
license is granted only on a Wilson-bounded track record with good **calibration**, is **revoked**
when a production prediction is violated, and is **invalidated** when the agent's brain changes
(model/prompt drift).

> Built for the **Splunk Agentic Ops Hackathon** — theme: *reimagine the future of agentic
> operations using Splunk AI.*

**🌐 Website: https://warrant-chi.vercel.app** · **demo replay: https://warrant-chi.vercel.app/demo.html**

---

## The story in four acts

1. **Proving ground** — the agent sits ~15 manufactured incidents in seconds and earns a license
   per action class (`PROVISIONAL → LICENSED`), without touching production.
2. **Production** — a real leak (it's licensed, so it acts autonomously and is proven right),
   then a **decoy** (the obvious fix is wrong → prediction violated → *"I was wrong"* → escalate
   → rollback recovers → license **SUSPENDED**).
3. **Model updated overnight** — the brain's fingerprint changes; every license drops to
   **PROVISIONAL**. Nothing else in ops notices a silent model swap. Warrant does.
4. **Re-certify** — fresh exams re-earn the licenses under the new brain.

## The control loop

```
1. SENSE        Read live telemetry                      (sandbox metrics)
2. CONTEXT      Pull real Splunk data + AI reasoning      (Splunk MCP: splunk_run_query, saia_*)
3. DIAGNOSE     A brain picks a bounded action + confidence (heuristic or Gemini)
4. PREDICT      Commit to a FALSIFIABLE forecast band      (a control limit learned from healthy data)
                BEFORE acting
5. GATE         Reversible + in-blast-radius, and act      (the safety kernel + the license)
                autonomously only with a valid LICENSE
6. ACT          Execute the bounded remediation            (sandbox control API)
7. VERIFY       Compare live metric vs. forecast band      (read-back)
8. LEDGER       Record the graded outcome (correct?,       (certification)
                confidence, brain fingerprint) -> re-certify the license
```

## What makes a license

| Condition       | Why it matters |
| --------------- | -------------- |
| **Confidence**  | Wilson score lower bound on the hit-rate ≥ threshold — one lucky pass can't license an action |
| **Evidence**    | A minimum number of graded outcomes behind it |
| **Calibration** | Brier score ≤ limit — a confidently-wrong agent fails even with a good hit-rate |
| **Fingerprint** | Pinned to the brain (model id + prompt version) — a change forces re-certification |
| **Probation**   | Each *production* failure under the current brain raises the evidence bar (`+2` samples per strike) — a suspended agent can't retry exam suites until one gets lucky |
| **Margin**      | Graduated autonomy: clearing the bar by a thin margin yields **ALLOW_WITH_MONITORING** (act, but page a human); full autonomy needs a comfortable margin |

**The ledger is tamper-evident:** every outcome is sha256-chained to the one before it
(`Ledger.verify_chain()`, exposed as the `warrant_verify_ledger` MCP tool), and each record is
labelled by *evidence* — `measured` (Warrant read the metric itself) vs `self-reported` (the
agent's word) — so an auditor can see exactly how much of a license rests on what.

## Why each Splunk building block is load-bearing

| Splunk capability        | Role in Warrant                                                        |
| ------------------------ | --------------------------------------------------------------------- |
| **MCP Server (client)**  | The agent's eyes — the CONTEXT step runs `splunk_run_query` over `_internal` |
| **AI Assistant (saia_*)**| Hosted-model SPL authoring (`saia_generate_spl`) for the context query |
| **Warrant as an MCP server** | Exposes the trust gate (`warrant_request_action`, …) so *any* agent — SOAR, Splunk's Triage/Guided-Response agents — can be licensed over MCP |
| **SPL-native ledger**    | `splunk/trust_ledger.spl` recomputes the Wilson + Brier licensing math as a saved search |

## Repo layout

```
warrant/
  sandbox/      Parameterised microservice "flight simulator": severities + 3 reversible controls
  warrant/      loop · proving_ground · certification · ledger · brain · splunk_mcp · mcp_server · dashboard
  splunk/       SPL trust-ledger saved search
  web/          Static replay of the dashboard (hosted on Vercel)
  docs/         Architecture diagram, demo script, Devpost write-up
  SETUP.md      Splunk account + MCP install + connectivity test
```

## Run it

Prerequisites: Python 3.11+, a Splunk Cloud account with the **Splunk MCP Server** app, and a
filled-in `.env` (see `SETUP.md`). The brain defaults to a deterministic heuristic so every run
is reproducible; set `GEMINI_API_KEY` and drop `WARRANT_BRAIN` to let **Gemini** drive diagnosis.

```powershell
# 1. install
py -3.11 -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r requirements.txt

# 2. confirm Splunk connectivity through MCP
python -m warrant.check_connection

# 3. start the sandbox (terminal A)
python -m uvicorn sandbox.app:app --port 9000

# 4a. the full four-act story in the console (terminal B)
$env:WARRANT_BRAIN="heuristic"; python -m warrant.demo

# 4b. ...or the live dashboard (terminal B), then browse http://localhost:8050
$env:WARRANT_BRAIN="heuristic"; python -m uvicorn warrant.dashboard:app --port 8050

# 4c. ...or prove the MCP gate: an external agent earns, uses, and loses autonomy over MCP
python -m warrant.mcp_demo
```

## Status

- ✅ Splunk MCP Server connectivity (live SPL round-trip over `_internal`)
- ✅ **Proving ground** — manufactured, graded exams build a real track record in seconds
- ✅ **Per-action-class licenses** — Wilson confidence + Brier calibration + lifecycle
- ✅ **Drift detection** — licenses pinned to a brain fingerprint; re-certify on change
- ✅ **Warrant MCP server** — the trust gate, callable by any external agent (`warrant.mcp_demo`)
- ✅ **Pluggable brain** — deterministic heuristic or Gemini; identical safety harness either way
- ✅ **Statistical forecast** — a control limit learned from healthy data (not hardcoded)
- ✅ **Live web dashboard** — proving ground · license registry · control-limit chart · drift
- ✅ SPL-native trust ledger (`splunk/trust_ledger.spl`) for a HEC-enabled tenant
- ✅ **Per-agent identity over MCP** — licenses are pinned to the caller's `agent_fingerprint`;
  a different brain cannot spend a license it didn't earn (`warrant.mcp_demo` proves it)
- ✅ **Trust-but-verify outcomes** — `warrant_report_outcome` accepts a `metric_url` so Warrant
  measures the outcome itself; self-reported outcomes are permanently flagged as such
- ✅ **Tamper-evident ledger** — sha256 hash chain + `warrant_verify_ledger` audit tool
- ✅ **Probation** — production failures raise the evidence bar for re-licensing
- ✅ **Graduated autonomy** — thin-margin licenses are ALLOW_WITH_MONITORING, not full autonomy
- ✅ **Late-regression guard** — optional second verification one horizon later
  (`LoopParams.recheck`) so a fix that fails slowly is graded as a MISS
- ◻️ AI Assistant `saia_*` hosted-model tools are integrated but require backend activation on
  the Splunk tenant; the CONTEXT step falls back to a direct MCP query over `_internal`.

## Limitations & roadmap

Warrant is honest about what a demo can and cannot prove — these are the known edges:

| Limitation | Status / mitigation |
| ---------- | ------------------- |
| "Production" is a sandbox flight-simulator | By design for a hackathon — you don't test a fire alarm by burning a building. The architecture is unchanged against real infrastructure. |
| Exams come from the same generator the agent later faces | Severity/noise are parameterised so no two exams are identical; a real deployment needs a richer scenario library. |
| Exam outcomes are correlated, not i.i.d. | The Wilson bound is therefore optimistic about effective sample size; thresholds are configurable and conservative. |
| Human approval is simulated by default | The loop logs it as **simulated** and exposes `LoopParams.approve` for a real approval queue. |
| Verification reads one metric over a fixed horizon | `LoopParams.recheck` adds a second, later reading; multi-signal verification is roadmap. |
| The local JSON ledger is hash-chained but file-writable | Tamper-*evident*, not tamper-*proof*. The SPL ledger (`splunk/trust_ledger.spl`) is the production answer: the registry lives in Splunk. |
| Self-reported MCP outcomes can lie | Mitigated: measured mode (`metric_url`) lets Warrant grade outcomes itself, and every record is labelled `measured` vs `self-reported` for audit. |
| Thresholds (0.5 Wilson, 4 samples) are demo-scaled | Real certification wants hundreds of graded outcomes; all knobs are env-configurable. |

## License

MIT — see `LICENSE`.
