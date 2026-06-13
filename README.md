<div align="center">

# ⚖️ Warrant

**The licensing authority for AI agents.**

[![License: MIT](https://img.shields.io/badge/License-MIT-1c6e46.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-1f4e8c.svg)](https://www.python.org/)
[![Track: Observability](https://img.shields.io/badge/Splunk%20Agentic%20Ops-Observability-9a6b1a.svg)](https://splunk.devpost.com/)
[![MCP](https://img.shields.io/badge/MCP-client%20%2B%20server-b388ff.svg)](#-built-on-splunk)

[![restart_connection_pool](https://warrant-chi.vercel.app/badges/restart_connection_pool.svg)](https://warrant-chi.vercel.app/certificate.html)
[![rollback_deploy](https://warrant-chi.vercel.app/badges/rollback_deploy.svg)](https://warrant-chi.vercel.app/certificate.html)
[![clear_cache](https://warrant-chi.vercel.app/badges/clear_cache.svg)](https://warrant-chi.vercel.app/certificate.html)

*Evals tell you how smart an agent is. Warrant tells production **how much rope to give it** — and takes the rope back the moment a prediction fails or the model changes underneath you.*

[**🌐 Website**](https://warrant-chi.vercel.app) · [**▶ Live demo**](https://warrant-chi.vercel.app/demo.html) · [**📜 Certificate**](https://warrant-chi.vercel.app/certificate.html) · [**📖 Docs**](https://warrant-chi.vercel.app/docs.html)

<img src="web/screenshots/hero.png" alt="Warrant — don't trust your agent, license it" width="100%">

</div>

---

## Contents

- [The problem](#the-problem)
- [The idea](#the-idea)
- [How it works](#how-it-works)
- [What makes a license](#what-makes-a-license)
- [See it run — four acts](#-see-it-run--four-acts)
- [Issued certificates & badges](#-issued-certificates--badges)
- [Built on Splunk](#-built-on-splunk)
- [Quickstart](#-quickstart)
- [Using Warrant in a real environment](#-using-warrant-in-a-real-environment)
- [Configuration](#-configuration)
- [Repository layout](#-repository-layout)
- [Limitations & roadmap](#-limitations--roadmap)
- [License](#-license)

---

## The problem

Every vendor shipping agentic operations today says the same sentence: *"human-led, with the
analyst in control."* It sounds responsible — but it quietly dodges the only question that
decides whether any of this scales: **when is the human allowed to let go?**

In practice, autonomy gets granted the way it always does — *a demo went well, a prompt was
tweaked, someone flipped auto-approve.* No number, no evidence, no way to take it back. That fails
three silent ways: a **lucky streak** mistaken for competence, an agent that is **confidently
wrong**, and the **silent model swap** that invalidates everything you thought you knew about it.

## The idea

> A driver's license doesn't certify that you're smart. It certifies you were tested on the road
> you'll actually drive — and it can be taken away.

Warrant treats AI autonomy exactly like a license. An agent earns a **license per action class**
the way a pilot does: not by crashing real planes, but by passing graded exams in a **proving
ground**. Every exam is judged against the agent's own **falsifiable prediction** — reality, not
the model, decides if it was right. The license is **revoked** when a production prediction is
violated, **invalidated** when the agent's brain changes, and **decays** if it goes unused.

## How it works

The sandbox is live telemetry (a system you can deliberately break and heal). **Splunk Cloud is
the reasoning context, reached entirely through the Splunk MCP Server.** And Warrant itself is an
**MCP server**, so any external agent is gated by the same registry.

<div align="center">
<img src="web/screenshots/architecture.png" alt="Architecture — three planes, joined by MCP" width="100%">
</div>

The control loop runs eight steps — and the keystone is that the **prediction is committed
*before* the action**, so there is nothing to argue about at verification time:

```
1. SENSE      Read live telemetry                          (sandbox metrics)
2. CONTEXT    Pull real Splunk data + AI reasoning         (Splunk MCP: splunk_run_query, saia_*)
3. DIAGNOSE   A brain picks a bounded action + confidence  (heuristic or Gemini)
4. PREDICT    Commit to a FALSIFIABLE forecast band        (a control limit learned from healthy data)
              BEFORE acting   ← the keystone
5. GATE       Reversible + in-blast-radius, and act        (the safety kernel + the license)
              autonomously only with a valid LICENSE
6. ACT        Execute the bounded remediation              (sandbox control API)
7. VERIFY     Compare live metric vs. the forecast band    (read-back; optional late re-check)
8. LEDGER     Record the graded outcome (correct?,         (certification)
              confidence, brain fingerprint) → re-certify the license
```

## What makes a license

A license for an action class is granted only when **all** of these hold:

| Condition       | Why it matters |
| --------------- | -------------- |
| **Confidence**  | Wilson score lower bound on the hit-rate ≥ threshold — one lucky pass can't license an action |
| **Evidence**    | A minimum number of graded outcomes behind it |
| **Calibration** | Brier score ≤ limit — a confidently-wrong agent fails even with a good hit-rate |
| **Fingerprint** | Pinned to the brain (model id + prompt version) — a change forces re-certification |
| **Probation**   | Each *production* failure under the current brain raises the evidence bar (`+2` samples per strike) — a suspended agent can't retry exam suites until one gets lucky |
| **Margin**      | Graduated autonomy: a thin margin over threshold yields **ALLOW_WITH_MONITORING** (act, but page a human); full autonomy needs a comfortable margin |
| **Freshness**   | Evidence is time-weighted (configurable half-life) — a license **decays** to human-in-the-loop unless renewed with fresh outcomes |

**The ledger is tamper-evident:** every outcome is sha256-chained to the one before it
(`Ledger.verify_chain()`, exposed as the `warrant_verify_ledger` MCP tool), and each record is
labelled by *evidence* — `measured` (Warrant read the metric itself) vs `self-reported` (the
agent's word) — so an auditor can see exactly how much of a license rests on what.

## ▶ See it run — four acts

The demo runs Warrant against the live fault-injection sandbox. The kill-shot is **Act II**: a
decoy fools the agent exactly the way it would fool an engineer — and its own falsifiable
prediction catches the mistake, rolls it back, and suspends the license.

<div align="center">
<img src="web/screenshots/demo.png" alt="Warrant live dashboard — agent activity, license registry, control-limit chart" width="100%">
<br/><em>The live dashboard (and its <a href="https://warrant-chi.vercel.app/demo.html">hosted replay</a>): agent activity, the license registry, and error-rate vs. the learned control limit.</em>
</div>

1. **Proving ground** — the agent sits ~15 manufactured incidents in seconds and earns a license
   per action class (`PROVISIONAL → LICENSED`), without touching production.
2. **Production** — a real leak (licensed → acts autonomously, proven right), then a **decoy**
   (obvious fix is wrong → prediction violated → *"I was wrong"* → escalate → rollback recovers →
   license **SUSPENDED**).
3. **Model updated overnight** — the brain's fingerprint changes; every license drops to
   **PROVISIONAL**. Nothing else in ops notices a silent model swap. Warrant does.
4. **Re-certify** — fresh exams re-earn the licenses under the new brain.

## 📜 Issued certificates & badges

Most "AI governance" is a dashboard number. Warrant issues a **document** — an official, printable
certificate for every license, bound to the tamper-evident ledger hash — plus shields-style
**badges** you can embed in any repo (like the live ones at the top of this README).

<div align="center">
<img src="web/screenshots/certificate.png" alt="A Warrant license certificate, bound to the trust-ledger hash" width="78%">
</div>

- **Live:** `GET /certificate/<action_class>` (printable) and `GET /badge/<action_class>.svg`, served from the running dashboard.
- **Static:** the badges above are committed under `web/badges/` and hosted on Vercel — always-up, no backend.

## 🔌 Built on Splunk

Warrant **consumes** the Splunk MCP Server for every read of Splunk data, and **ships its own MCP
server** so the trust gate becomes infrastructure any agent can call.

| Splunk capability        | Role in Warrant                                                        |
| ------------------------ | --------------------------------------------------------------------- |
| **MCP Server (client)**  | The agent's eyes — the CONTEXT step runs `splunk_run_query` over `_internal` |
| **AI Assistant (`saia_*`)** | Hosted-model SPL authoring (`saia_generate_spl`) for the context query |
| **Warrant as an MCP server** | Exposes the trust gate (`warrant_request_action`, `warrant_report_outcome`, `warrant_check_license`, `warrant_list_licenses`, `warrant_verify_ledger`) so *any* agent — a SOAR playbook, Splunk's Triage / Guided-Response agents, a Claude agent — can be licensed over MCP |
| **SPL-native ledger**    | `splunk/trust_ledger.spl` recomputes the Wilson + Brier licensing math as a saved search, so on a real tenant the registry is a Splunk dashboard |

> We prove the gate end-to-end in `warrant.mcp_demo`: an independent agent earns, uses, and loses
> autonomy purely over MCP — and a *second* brain is refused a license it never earned.

## 🚀 Quickstart

**Prerequisites:** Python 3.11+. Splunk is optional for the demo (the loop falls back to a direct
MCP query, and the brain defaults to a deterministic heuristic so every run is reproducible).

```powershell
# 1. install
py -3.11 -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r requirements.txt

# 2. (optional) confirm Splunk connectivity through MCP
python -m warrant.check_connection

# 3. start the sandbox  (terminal A)
python -m uvicorn sandbox.app:app --port 9000

# 4a. the full four-act story in the console  (terminal B)
$env:WARRANT_BRAIN="heuristic"; python -m warrant.demo

# 4b. ...or the live dashboard, then open http://localhost:8050
$env:WARRANT_BRAIN="heuristic"; python -m uvicorn warrant.dashboard:app --port 8050

# 4c. ...or prove the MCP gate (self-contained — starts its own server)
python -m warrant.mcp_demo

# 4d. ...or watch a license rot from disuse (trust decay)
python -m warrant.decay_demo
```

> On macOS/Linux, swap the venv activation for `source .venv/bin/activate` and `$env:X="y"` for `X=y`.

## 🏭 Using Warrant in a real environment

The governance engine and its **MCP interface are real and reusable as-is**; putting Warrant in
front of a real company's agents is *wiring*, not rebuilding. Two connection points:

1. **Your agent calls the gate** — any MCP-speaking agent gains four tool calls; nothing is rewritten.
   ```
   warrant_request_action(action_class="restart_service", agent_fingerprint="<model:prompt id>")
   # → ALLOW · ALLOW_WITH_MONITORING · REQUIRE_APPROVAL
   ```
2. **Point verification at your real metrics** — pass your own endpoint and the committed band; Warrant fetches and grades it *itself*, so the agent can't self-certify.
   ```
   warrant_report_outcome(action_class="restart_service",
                          metric_url="https://your-splunk/.../error_rate", upper_limit=0.01)
   ```

Action *execution* stays in your existing runbooks/SOAR — Warrant governs **whether** to act, not
how. A production deployment would still add MCP authentication, a shared durable ledger (the SPL
version points the way), and operational hardening. See [Limitations & roadmap](#-limitations--roadmap).

## ⚙️ Configuration

All knobs are environment variables (see `.env.example`):

| Variable | Purpose | Default |
| -------- | ------- | ------- |
| `WARRANT_BRAIN` | Diagnosis brain: `heuristic` (reproducible), `gemini`, or `auto` | `auto` |
| `GEMINI_API_KEY` | Enables the Gemini brain (same safety harness either way) | _unset_ |
| `WARRANT_AUTONOMY_THRESHOLD` | Wilson lower bound a license must clear | `0.5` |
| `WARRANT_AUTONOMY_MIN_SAMPLES` | Minimum graded outcomes before licensing | `4` |
| `WARRANT_CALIBRATION_MAX` | Maximum Brier score (confidently-wrong fails here) | `0.4` |
| `WARRANT_PROBATION_EXTRA` | Extra evidence required per production failure | `2` |
| `WARRANT_MONITORING_MARGIN` | Margin below which a license is ALLOW_WITH_MONITORING | `0.10` |
| `WARRANT_TRUST_HALFLIFE_DAYS` | Evidence half-life for trust decay | `30` |
| `SPLUNK_MCP_URL` / `SPLUNK_TOKEN` | Splunk MCP endpoint + encrypted token (audience `mcp`) | see `SETUP.md` |

## 📁 Repository layout

```
warrant/
  sandbox/      Parameterised microservice "flight simulator": severities + 3 reversible controls
  warrant/      loop · proving_ground · certification · ledger · brain · splunk_mcp · mcp_server
                · dashboard · demo · mcp_demo · decay_demo
  splunk/       SPL trust-ledger saved search (Wilson + Brier as a native search)
  web/          The website + static replay + license badges + screenshots (hosted on Vercel)
  tools/        capture_replay.py — regenerate the static replay from a real run
  docs/         architecture_diagram.md · demo-script.md · devpost.md
  SETUP.md      Splunk account + MCP install + connectivity test
```

## ⚠️ Limitations & roadmap

Warrant is honest about what a hackathon proof-of-concept can and cannot prove:

| Limitation | Status / mitigation |
| ---------- | ------------------- |
| "Production" is a sandbox flight-simulator | By design — you don't test a fire alarm by burning a building. The architecture is unchanged against real infrastructure. |
| Exams come from the same generator the agent later faces | Severity/noise are parameterised so no two exams are identical; a real deployment needs a richer scenario library. |
| Exam outcomes are correlated, not i.i.d. | The Wilson bound is therefore optimistic about effective sample size; thresholds are configurable and conservative. |
| Human approval is simulated by default | The loop logs it as **simulated** and exposes `LoopParams.approve` for a real approval queue. |
| Verification reads one metric over a fixed horizon | `LoopParams.recheck` adds a second, later reading; multi-signal verification is roadmap. |
| The local JSON ledger is hash-chained but file-writable | Tamper-*evident*, not tamper-*proof*. The SPL ledger is the production answer: the registry lives in Splunk. |
| Self-reported MCP outcomes can lie | Mitigated: measured mode (`metric_url`) lets Warrant grade outcomes itself; every record is labelled `measured` vs `self-reported`. |
| No auth on the MCP server yet | Fine for a demo; production needs caller authentication. On the roadmap. |
| Thresholds & decay half-life are demo-scaled constants | Real certification wants hundreds of graded outcomes; all knobs are env-configurable. |

## 📄 License

Released under the **MIT License** — see [`LICENSE`](LICENSE).

```
MIT License

Copyright (c) 2026 Warrant contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

<div align="center">
<sub>Built for the <a href="https://splunk.devpost.com/">Splunk Agentic Ops Hackathon</a> · Observability track · 2026</sub>
</div>
