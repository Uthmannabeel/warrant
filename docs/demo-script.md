# Warrant — 3-minute demo video script (dashboard edition)

Target: **under 3:00**, 1080p. Record the **dashboard** at http://127.0.0.1:8050 plus a quick
look at the architecture diagram. Start both servers first:

```
python -m uvicorn sandbox.app:app --port 9000
python -m uvicorn warrant.dashboard:app --port 8050
```

---

## 0:00–0:22 — The problem (talking head or title slide)

> "Every AI ops agent shipping today is a read-only advisor — it suggests, a human acts.
> Because an AI that's confidently wrong with write access to production can cause an outage
> worse than the one it's fixing. The real frontier of agentic operations isn't diagnosis.
> It's **trust**. Meet Warrant — an agent that **earns the right to act.**"

## 0:22–0:45 — The idea (show docs/architecture.md diagram)

> "Warrant is built on falsifiability. Before it acts, it commits to a prediction you can
> prove wrong — a control limit **learned from the system's healthy data**. Reality, not the
> model, decides if it was right. A real LLM — Google Gemini — proposes the fix, but it only
> *proposes*: Warrant gates, predicts, verifies, and keeps score. And everything it knows
> about the environment, it reads from **Splunk through the MCP Server.**"

## 0:45–0:55 — Show the dashboard, hit Run

> "Here's the live dashboard. One system, six real incidents. Watch."
Click **▶ Run incidents**.

## 0:55–1:50 — Act 1: it earns autonomy (rounds 1–5)

Narrate over the first round, then let it roll:

> "Errors spike, connections climb. Warrant pulls **real Splunk context over MCP**, Gemini
> diagnoses a connection-pool leak, and — the key move — it **states a falsifiable
> prediction**: error rate returns below the learned control limit, or it was wrong. It's
> unproven, so a human approves. It acts; reality lands inside the band. Resolved."

Point at the **Trust meter** climbing:

> "Notice the trust meter. One success isn't enough — confidence is a statistical lower
> bound, so it has to *earn* it over a track record. Around round four... it crosses the
> line and graduates to **AUTONOMOUS**. It's earned the right to act alone."

## 1:50–2:40 — Act 2: trustworthy when WRONG (round 6, the decoy)

Slow down — this is the point of the whole project.

> "Round six looks identical — high errors, high connections — so, acting autonomously,
> Gemini picks the same obvious fix and Warrant predicts recovery. But watch the chart..."

Point at the bar shooting **above** the control limit, badge flipping red:

> "Reality broke out of its own forecast. By its **own definition**, Warrant is wrong — and
> it says so. It doesn't double down. It **escalates, reverts**, the correct fix recovers the
> system, and its trust score **drops — back to human-in-the-loop**. It caught its own
> mistake before it became an outage."

## 2:40–3:00 — Close

> "Every other agent is impressive when it's right. Warrant is **trustworthy when it's
> wrong** — and that's the only reason you'd ever let one act on production. That's how we
> reimagine agentic operations with Splunk."

---

## Shot checklist
- [ ] Architecture diagram on screen (0:22–0:45)
- [ ] `BRAIN`/Gemini diagnosis + `PREDICT` line visible in round 1
- [ ] Trust meter graduating to **AUTONOMOUS**
- [ ] Round 6: chart bar above the control limit + `WRONG` + badge → human-in-the-loop
- [ ] Total under 3:00, uploaded public/unlisted to YouTube or Vimeo
