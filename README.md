# Warrant

**An autonomous remediation agent that earns the right to act.**

Warrant is built on one idea: an AI ops agent shouldn't be trusted because it *sounds*
smart — it should be trusted because it has a **track record**, the same way we trust a
surgeon or a pilot. Before Warrant touches anything, it commits to a **falsifiable
prediction** of what should happen. Reality — not the model — decides whether it was right.
It is permitted to act autonomously only where its past predictions have survived contact
with reality.

> Built for the **Splunk Agentic Ops Hackathon** — theme: *reimagine the future of
> agentic operations using Splunk AI.*

**🌐 Live demo (replay of a real run): https://warrant-chi.vercel.app**

---

## The control loop

```
1. SENSE        Read live telemetry                     (sandbox metrics)
2. CONTEXT      Pull real Splunk data + AI reasoning     (Splunk MCP: splunk_run_query, saia_*)
3. HYPOTHESIZE  LLM agent picks a bounded remediation    (Gemini; heuristic fallback)
4. PREDICT      Commit to a FALSIFIABLE forecast band    (Warrant)  ← keystone
                BEFORE acting
5. GATE         Enforce blast-radius + reversibility     (Warrant safety kernel)
6. ACT          Execute the bounded remediation          (sandbox control API)
7. VERIFY       Compare live metric vs. forecast band    (read-back)
8. DECIDE       In-band  -> resolve
                Out-of-band -> "I was wrong" -> escalate + corrective rollback
                then LEDGER the outcome -> update the per-action-class trust score
```

**The trust gate:** an action class runs fully autonomously only while its ledger hit-rate
stays at or above a threshold. Below it, Warrant drops to human-in-the-loop and asks. It
*graduates* from supervised to autonomous by earning it, action class by action class.

## Why each Splunk building block is load-bearing

| Splunk capability        | Role in Warrant                                              |
| ------------------------ | ----------------------------------------------------------- |
| **MCP Server**           | The agent's eyes + verification — every SENSE/VERIFY runs through it |
| **Cisco Deep Time Series** | Generates the falsifiable forecast band (PREDICT)         |
| **Foundation-sec**       | Security-track root-cause reasoning (HYPOTHESIZE)           |
| **AI Assistant (saia_*)**| Natural-language SPL generation for ad-hoc investigation    |

## Repo layout

```
warrant/
  sandbox/      Toy microservice "flight simulator": fault injection + control API
  warrant/      The control loop: sense, hypothesize, predict, gate, act, verify, ledger
  splunk/       MCP client, SPL queries, dashboard + saved searches
  docs/         Architecture diagram, demo script
  SETUP.md      Step-by-step Splunk account + MCP install + connectivity test
  README.md     You are here
```

## Architecture

Warrant runs a **hybrid** topology: a sandbox "flight simulator" holds the live telemetry
(a system you can deliberately break), and **Splunk Cloud is the reasoning brain**, reached
entirely through the **Splunk MCP Server**. See [`docs/architecture.md`](docs/architecture.md)
for the full diagram and data flow.

## Run the demo

Prerequisites: Python 3.11+, a Splunk Cloud account with the **Splunk MCP Server** app, and a
filled-in `.env` (see `SETUP.md`).

```powershell
# 1. install
py -3.11 -m venv .venv ; .\.venv\Scripts\Activate.ps1 ; pip install -r requirements.txt

# 2. confirm Splunk connectivity through MCP
python -m warrant.check_connection

# 3. start the sandbox (terminal A)
python -m uvicorn sandbox.app:app --port 9000

# 4a. run the agent in the console (terminal B)
python -m warrant.demo

# 4b. ...or open the live dashboard (terminal B), then browse http://localhost:8050
python -m uvicorn warrant.dashboard:app --port 8050
```

The demo runs six incidents: five connection-leak incidents the agent diagnoses correctly —
**earning autonomy** only once its Wilson-confidence track record clears the bar — then a
**decoy** where the obvious fix is wrong. Acting autonomously, the agent's prediction fails,
it detects its own error, escalates, self-corrects, and its trust score **drops back to
human-in-the-loop**.

### Optional: the LLM agent brain
Set `GEMINI_API_KEY` in `.env` (free key from Google AI Studio) to have **Gemini** drive the
diagnosis. The model only *proposes* a bounded action — Warrant still gates, predicts,
verifies, and ledgers every decision. Without a key, it falls back to a local heuristic, so
the demo always runs.

## Status

- ✅ Splunk MCP Server connectivity (live SPL round-trip over `_internal`)
- ✅ Sandbox flight-simulator (fault injection + reversible control API)
- ✅ **LLM agent brain** (Gemini) proposing bounded remediations, heuristic fallback
- ✅ Full control loop: sense → context → hypothesize → predict → gate → act → verify → decide
- ✅ **Statistical forecast** — a control limit learned from healthy data (not hardcoded)
- ✅ **Earned trust** — Wilson confidence lower bound + minimum sample size gate autonomy
- ✅ **Live web dashboard** (`warrant.dashboard`) with trust meter + control-limit chart
- ✅ End-to-end demo narrative (console and dashboard)
- ◻️ AI Assistant `saia_*` hosted-model tools are integrated but require backend activation
  on the Splunk tenant; the CONTEXT step falls back to a direct MCP query over `_internal`.

## License

MIT — see `LICENSE`.
