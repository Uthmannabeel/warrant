# Warrant — 3-minute demo video script

**Target:** under **3:00**, 1080p, uploaded public/unlisted to YouTube or Vimeo.

There are two ways to record. **Version A (recommended)** needs zero setup — you record the live
website. **Version B** records the live dashboard for a "it's really running" feel.

---

## How to record (Windows, no extra software)

- Press **Win + Alt + R** to start/stop recording the current window (Xbox Game Bar), or use any
  screen recorder you like.
- Record at **1080p**, browser **full-screen** (press **F11** in the browser).
- Speak the narration below as you go — or record the clicks first and add voiceover after.
- Keep the browser in **light mode** (the document look reads as more serious on camera).
- **The demo replay auto-plays (~60 seconds) the moment you open the Demo page.** Narrate the
  four acts as the on-screen **ACT** banners appear. If your narration runs longer than the
  replay, just finish over the final registry (all LICENSED) — or press **▶ Replay** to restart it.
- **Load the home page fresh (Ctrl+R) right before recording** so the two certificate stamps
  animate in on screen during the opening line.

---

# 🅰️ VERSION A — record the website (recommended)

Open **https://warrant-chi.vercel.app** full-screen. Beats are timed; the **bold** lines are what
you say, the *italics* are what you do on screen.

### 0:00–0:18 · Home — the hook
*Land on the homepage. The two license certificates stamp "LICENSED" / "SUSPENDED".*

> **"Every company is racing to let AI agents *act* — restart services, roll back deploys, fix
> incidents at 3am. And they're all stuck on one question: when is it safe to let the agent act
> without a human watching? Warrant answers it. Don't trust your agent — license it."**

### 0:18–0:35 · Home — the idea
*Slowly scroll down through the problem section and the three pillars.*

> **"Today, autonomy gets granted when a demo goes well and someone flips a switch. Warrant makes
> an agent *earn* it — a revocable license per action, backed by evidence, not vibes."**

### 0:35–0:42 · Open the demo
*Click "Demo" in the nav. The replay auto-plays (~60s) — narrate the four acts as the on-screen
ACT banners appear; the registry on the right updates live.*

> **"Here's a real run, in four acts."**

### 0:42–1:05 · Act 1 — the proving ground
*The exam ticker runs; the License Registry on the right graduates rows to LICENSED.*

> **"First, the proving ground. Real incidents are too rare to certify on — so Warrant
> manufactures them. Dozens of faults, graded in seconds against the agent's own falsifiable
> predictions. Confidence is a Wilson lower bound, so one lucky pass proves nothing. Three actions
> earn a license — before touching production."**

### 1:05–1:40 · Act 2 — right, then wrong (the kill-shot)
*Watch the activity log; point at the chart and the registry row flipping to red SUSPENDED.*

> **"Now production. A real leak — the agent is licensed, so it acts on its own, pulling live
> Splunk context over MCP, and it's right. Then a decoy: the obvious fix looks identical, so it
> acts with confidence — and misses its own forecast. By its own definition, it was wrong. It
> says so, rolls back, escalates — and the license is revoked. It caught its own mistake before
> it became an outage."**

### 1:40–2:00 · Acts 3 & 4 — drift and re-certification
*The registry drops to PROVISIONAL, then re-earns LICENSED.*

> **"Then the part nothing else does. Overnight, the model is updated. Warrant fingerprints the
> brain — the moment it changes, every license drops to provisional. The new brain has to
> re-earn trust from scratch."**

### 2:00–2:18 · The certificate
*Open "Certificate" (or the certificate link). Show the stamped certificate and the badges row.*

> **"And trust here isn't a dashboard number — it's a document. Every license is an auditable
> certificate, bound to a tamper-evident ledger, with badges any repo can show."**

### 2:18–2:35 · Built on Splunk / MCP
*Go to "How it works" and show the architecture diagram + the MCP code block.*

> **"Warrant reads Splunk through the MCP Server — and ships its own, so any agent can ask: am I
> allowed to act? It even measures the outcome itself, so an agent can't lie its way to a
> license."**

### 2:35–3:00 · Close
*Scroll to the closing line, or back to the hero.*

> **"Falsifiable predictions. Earned, revocable, decaying licenses. Drift detection. Calibration.
> A trust gate any agent can call over MCP. Evals tell you how smart an agent is — Warrant tells
> production how much rope to give it, and takes it back. That's how the agentic era goes
> autonomous, safely."**

---

# 🅱️ VERSION B — record the live dashboard (optional, "it's really running")

Start both servers first (heuristic brain = fully reproducible):

```
python -m uvicorn sandbox.app:app --port 9000
$env:WARRANT_BRAIN="heuristic"; python -m uvicorn warrant.dashboard:app --port 8050
```

Open **http://localhost:8050**. Use the same narration as Version A, but instead of the replay,
click the four buttons live: **① Proving ground → ② Production → ③ Model updated overnight →
④ Re-certify**. Optionally show the issued certificate at **http://localhost:8050/certificates**,
and B-roll `python -m warrant.mcp_demo` (an external agent gated, and a *second* agent refused).

---

## Shot checklist

- [ ] Home hero with the stamping certificates (0:00)
- [ ] Replay Act 1: exam ticker + registry graduating to **LICENSED**
- [ ] Replay Act 2: chart bar above the control limit + a row flipping to **SUSPENDED**
- [ ] Replay Acts 3–4: all rows **PROVISIONAL**, then back to **LICENSED**
- [ ] Certificate page (stamped certificate + license badges)
- [ ] How-it-works architecture diagram + MCP code block
- [ ] Total under **3:00**, light mode, 1080p, uploaded public/unlisted
