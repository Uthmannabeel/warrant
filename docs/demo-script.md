# Warrant — 3-minute demo video script (licensing-authority edition)

Target: **under 3:00**, 1080p. Record the **dashboard** at http://127.0.0.1:8050. Start both
servers first (heuristic brain = fully reproducible; drop `WARRANT_BRAIN` to let Gemini drive):

```
python -m uvicorn sandbox.app:app --port 9000
$env:WARRANT_BRAIN="heuristic"; python -m uvicorn warrant.dashboard:app --port 8050
```

Have the four buttons ready: ① Proving ground · ② Production · ③ Model updated overnight · ④ Re-certify.

---

## 0:00–0:25 — The problem (talking head or title slide)

> "Splunk's 2026 roadmap is full of AI agents that *act* — triage, guided response, autonomous
> response. Every one says the same thing: *transparent, auditable, under analyst control.*
> Which quietly admits the unsolved problem — nothing decides **when the human can let go.**
> Warrant does. It's a **licensing authority for AI agents**."

## 0:25–0:45 — The idea (show docs/architecture.md diagram)

> "Evals tell you how smart an agent is. Warrant tells production **how much rope to give it**.
> An agent earns a **license per action class** — but only by passing exams in a proving ground,
> graded against its own **falsifiable predictions**. And it reads everything it knows about the
> environment from **Splunk, through the MCP Server**."

## 0:45–1:25 — ① Proving ground (click ①)

> "Real incidents are too rare to certify on — so Warrant **manufactures** them. Watch: dozens
> of varied faults, at different severities, graded in seconds."

Point at the **exam ticker** and the **License Registry** on the right:

> "Each action class builds a track record. Confidence isn't a raw hit-rate — it's a **Wilson
> lower bound**, so one lucky pass proves nothing. Plus a **calibration** score: be confidently
> wrong and you fail, even with a good hit-rate. Three action classes cross the line and go
> **LICENSED** — earned, from evidence, before touching production."

## 1:25–2:10 — ② Production: right, then wrong (click ②)

> "Now production. A real connection-pool leak. The agent holds a license, so it acts
> **autonomously** — pulls **real Splunk context over MCP**, predicts recovery below the learned
> control limit, acts, and lands inside the band. Resolved."

Slow down for the decoy:

> "Second incident looks identical — high errors, high connections — so it applies its licensed
> pool-restart with high confidence. But watch the chart break **above** its own forecast."

Point at the registry row flipping to red **SUSPENDED**:

> "By its **own definition**, it was wrong — and it says so. It escalates, a rollback recovers
> the system, and the license is **revoked**. Back to human-in-the-loop. It caught its own
> mistake before it became an outage."

## 2:10–2:45 — ③ The kill-shot: drift (click ③)

> "Here's what nothing else in ops does. Overnight, the model gets updated. Same agent? Not
> really. Warrant **fingerprints** the brain — and the instant it changes, **every license** it
> earned drops to **provisional**." (Click ④.) "The new brain has to **re-certify** in the
> proving ground before it's trusted again."

## 2:45–3:00 — Close

> "Falsifiable predictions, earned and revocable licenses, calibration, drift detection — and a
> trust gate any agent can call **over MCP**. Warrant is the trust layer that lets Splunk's
> agentic era actually go autonomous. Safely."

---

## Shot checklist
- [ ] Architecture diagram on screen (0:25–0:45)
- [ ] ① exam ticker running + License Registry graduating to **LICENSED**
- [ ] ② `[CONTEXT]` Splunk-over-MCP line + `[PREDICT]` visible on the leak
- [ ] ② decoy: chart bar above the control limit + registry row → **SUSPENDED**
- [ ] ③ fingerprint change → all rows **PROVISIONAL**; ④ re-certify back to **LICENSED**
- [ ] (optional B-roll) `python -m warrant.mcp_demo` — an external agent gated over MCP
- [ ] Total under 3:00, uploaded public/unlisted to YouTube or Vimeo
