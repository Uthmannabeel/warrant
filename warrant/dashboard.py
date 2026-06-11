"""Warrant live dashboard — the licensing authority, on screen.

Run the sandbox AND this dashboard, then open http://localhost:8050:

    # terminal A
    python -m uvicorn sandbox.app:app --port 9000
    # terminal B  (heuristic brain = fully reproducible; drop WARRANT_BRAIN to try Gemini)
    $env:WARRANT_BRAIN="heuristic"; python -m uvicorn warrant.dashboard:app --port 8050

The story is told in four buttons:
  1. Proving ground   — the agent sits manufactured exams and earns a license per action class.
  2. Production       — a real leak (acts autonomously) then a decoy (caught, license suspended).
  3. Model update     — the brain's fingerprint changes; every license drops to PROVISIONAL.
  4. Re-certify       — fresh exams re-earn the licenses under the new brain.

Self-contained (no external CDNs) so it works offline / behind a proxy.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from . import brain
from .certification import certify_all
from .ledger import Ledger
from .loop import LoopParams, Scenario, run_once
from .proving_ground import EXAM_PARAMS, generate_suite

app = FastAPI(title="Warrant Dashboard")

# Production rounds: real horizon (kept short for a live demo), genuine Splunk context.
PROD_PARAMS = LoopParams(horizon_seconds=2, baseline_samples=4, baseline_interval=0.05,
                         do_corrective=True, kind="production", brain_timeout=8, brain_retries=1)


def _stamp() -> str:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(timespec="seconds")


def _licenses_event() -> dict:
    fp = brain.fingerprint()
    items = [{
        "action_class": l.action_class, "status": l.status,
        "confidence": round(l.confidence, 3), "hit_rate": l.hit_rate,
        "calibration": l.calibration, "samples": l.samples,
        "exams": l.exams, "production": l.production, "drifted": l.drifted,
        "reason": l.reason,
    } for l in certify_all(Ledger(), fp)]
    return {"type": "licenses", "fingerprint": fp, "items": items}


async def _sse(driver) -> StreamingResponse:
    """Run `driver(queue)` as a task and stream everything it enqueues as SSE."""
    queue: asyncio.Queue = asyncio.Queue()

    async def run():
        try:
            await driver(queue)
        except Exception as exc:  # noqa: BLE001
            queue.put_nowait({"type": "log", "msg": f"[ERROR] {type(exc).__name__}: {exc}"})
        finally:
            queue.put_nowait({"type": "done"})

    async def gen():
        task = asyncio.create_task(run())
        try:
            while True:
                ev = await queue.get()
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("type") == "done":
                    break
        finally:
            await task

    return StreamingResponse(gen(), media_type="text/event-stream")


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(HTML)


@app.get("/licenses")
def licenses() -> dict:
    return _licenses_event()


@app.get("/exams")
async def exams() -> StreamingResponse:
    """ACT 1 — the proving ground. Fresh ledger, manufactured exams, licenses graduate live."""
    async def driver(q: asyncio.Queue) -> None:
        ledger = Ledger()
        ledger.reset()
        brain.set_brain_version(None)
        q.put_nowait(_licenses_event())
        suite = generate_suite()
        q.put_nowait({"type": "phase", "name": "exams", "title": "PROVING GROUND",
                      "total": len(suite), "fingerprint": brain.fingerprint()})
        for i, scenario in enumerate(suite, 1):
            res = await run_once(scenario, ledger, "exam", params=EXAM_PARAMS)
            q.put_nowait({"type": "exam", "n": i, "total": len(suite),
                          "scenario": scenario.label, "fault": scenario.fault,
                          "chosen": res.hypothesis.action_class,
                          "correct": res.correct, "confidence": res.hypothesis.confidence})
            q.put_nowait(_licenses_event())
    return await _sse(driver)


@app.get("/production")
async def production() -> StreamingResponse:
    """ACT 2 & 3 — a real leak (autonomous), then a decoy (wrong, caught, license suspended)."""
    rounds = [
        ("leak", "restart_connection_pool", "REAL LEAK — agent is licensed, acts autonomously"),
        ("decoy", "rollback_deploy", "DECOY — the obvious fix is wrong; watch Warrant catch it"),
    ]

    async def driver(q: asyncio.Queue) -> None:
        ledger = Ledger()
        for i, (fault, fix, title) in enumerate(rounds, 1):
            q.put_nowait({"type": "round", "n": i, "total": len(rounds),
                          "scenario": fault, "title": title})

            def emit(msg: str) -> None:
                q.put_nowait({"type": "log", "msg": msg})

            res = await run_once(Scenario(fault, correct_action=fix), ledger, _stamp(),
                                 emit=emit, params=PROD_PARAMS)
            q.put_nowait({"type": "metric", "round": i, "scenario": fault,
                          "before": res.metrics_before.get("error_rate"),
                          "after": res.metric_after, "limit": res.prediction.upper,
                          "correct": res.correct})
            q.put_nowait(_licenses_event())
    return await _sse(driver)


@app.get("/drift")
async def drift() -> StreamingResponse:
    """ACT 4 — the brain is 'updated overnight'. Fingerprint changes; licenses drop to PROVISIONAL."""
    async def driver(q: asyncio.Queue) -> None:
        old = brain.fingerprint()
        brain.set_brain_version("2026.06.2-hotfix")
        new = brain.fingerprint()
        q.put_nowait({"type": "log", "msg": f"[DRIFT]      brain updated overnight: {old} -> {new}"})
        q.put_nowait({"type": "log", "msg": "[DRIFT]      every license earned by the old brain "
                                            "is no longer valid — re-certification required"})
        q.put_nowait(_licenses_event())
    return await _sse(driver)


@app.get("/recertify")
async def recertify() -> StreamingResponse:
    """Re-run the proving ground under the NEW brain so the licenses are re-earned."""
    async def driver(q: asyncio.Queue) -> None:
        ledger = Ledger()
        suite = generate_suite(per_fault=4, seed=11)
        q.put_nowait({"type": "phase", "name": "recertify", "title": "RE-CERTIFICATION",
                      "total": len(suite), "fingerprint": brain.fingerprint()})
        for i, scenario in enumerate(suite, 1):
            res = await run_once(scenario, ledger, "exam", params=EXAM_PARAMS)
            q.put_nowait({"type": "exam", "n": i, "total": len(suite),
                          "scenario": scenario.label, "fault": scenario.fault,
                          "chosen": res.hypothesis.action_class,
                          "correct": res.correct, "confidence": res.hypothesis.confidence})
            q.put_nowait(_licenses_event())
    return await _sse(driver)


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Warrant — a licensing authority for AI agents</title>
<style>
  :root{
    --bg:#0b1020; --panel:#121a30; --panel2:#0e1528; --ink:#e8edf7; --muted:#8da2c0;
    --line:#22304f; --green:#22c98a; --red:#ff5c72; --amber:#ffc04d; --blue:#5aa9ff;
    --purple:#b388ff; --teal:#36d2c4; --cyan:#46c6ff;
  }
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(1200px 600px at 70% -10%,#16203c 0,var(--bg) 60%);
       color:var(--ink);font:14px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,Arial}
  header{display:flex;align-items:center;justify-content:space-between;gap:16px;
         padding:16px 24px;border-bottom:1px solid var(--line);flex-wrap:wrap}
  .brand h1{margin:0;font-size:19px;letter-spacing:.2px}
  .brand p{margin:2px 0 0;color:var(--muted);font-size:13px}
  .controls{display:flex;gap:8px;flex-wrap:wrap}
  button{background:linear-gradient(180deg,#2b6fff,#1f5be0);color:#fff;border:0;border-radius:10px;
         padding:10px 14px;font-weight:600;cursor:pointer;box-shadow:0 6px 18px rgba(43,111,255,.3)}
  button.ghost{background:#1a2440;box-shadow:none;border:1px solid var(--line)}
  button.warn{background:linear-gradient(180deg,#ffb84d,#e0941f);color:#241600}
  button:disabled{opacity:.4;cursor:not-allowed;box-shadow:none}
  .wrap{display:grid;grid-template-columns:1.35fr .95fr;gap:16px;padding:16px 24px}
  .card{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);
        border-radius:14px;padding:14px 16px;margin-bottom:16px}
  .card h2{margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:1.3px;color:var(--muted)}
  #log{height:360px;overflow:auto;font-family:ui-monospace,Consolas,monospace;font-size:12px}
  .ln{padding:2px 6px;border-radius:6px;white-space:pre-wrap;word-break:break-word}
  .tag{display:inline-block;min-width:88px;color:var(--muted)}
  .round-sep{margin:10px 0 6px;color:#fff;font-weight:700;border-top:1px dashed var(--line);padding-top:8px}
  .t-BRAIN .tag{color:var(--purple)} .t-PREDICT .tag{color:var(--blue)}
  .t-CONTEXT .tag{color:var(--teal)} .t-TRUST .tag{color:var(--amber)}
  .t-APPROVAL .tag{color:var(--amber)} .t-ACT .tag{color:var(--cyan)}
  .t-LEDGER .tag{color:var(--amber)} .t-BASELINE .tag{color:var(--muted)}
  .t-DRIFT .tag{color:var(--purple)}
  .ok{color:var(--green)} .bad{color:var(--red)} .warn{color:var(--amber)} .pur{color:var(--purple)}
  /* license registry */
  .lic{display:grid;grid-template-columns:1fr auto;gap:6px 10px;align-items:center;
       padding:10px 12px;border:1px solid var(--line);border-radius:11px;margin-bottom:9px;background:#0c142a}
  .lic .name{font-weight:700;font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
  .lic .meta{color:var(--muted);font-size:11.5px;grid-column:1;}
  .pill{justify-self:end;grid-row:1;padding:4px 10px;border-radius:99px;font-weight:800;font-size:11px;letter-spacing:.4px}
  .pill.LICENSED{background:rgba(34,201,138,.16);color:var(--green);border:1px solid rgba(34,201,138,.45)}
  .pill.PROVISIONAL{background:rgba(255,192,77,.14);color:var(--amber);border:1px solid rgba(255,192,77,.42)}
  .pill.SUSPENDED{background:rgba(255,92,114,.16);color:var(--red);border:1px solid rgba(255,92,114,.45)}
  .cbar{grid-column:1 / span 2;height:8px;background:#0a1226;border:1px solid var(--line);border-radius:99px;overflow:hidden}
  .cbar > i{display:block;height:100%;width:0;background:linear-gradient(90deg,#2b6fff,#36d2c4);transition:width .5s}
  .thr{font-size:11px;color:var(--muted);grid-column:1 / span 2;margin-top:-2px}
  .exambar{height:10px;background:#0a1226;border:1px solid var(--line);border-radius:99px;overflow:hidden;margin:4px 0 8px}
  .exambar > i{display:block;height:100%;width:0;background:linear-gradient(90deg,#b388ff,#46c6ff);transition:width .25s}
  .examnow{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:var(--muted);min-height:18px}
  .fp{font-family:ui-monospace,Consolas,monospace;font-size:11px;color:var(--muted)}
  canvas{width:100%;height:180px;display:block}
  .legend{display:flex;gap:14px;color:var(--muted);font-size:11px;margin-top:6px;flex-wrap:wrap}
  .dot{display:inline-block;width:9px;height:9px;border-radius:99px;margin-right:5px;vertical-align:middle}
  .foot{padding:4px 24px 20px;color:var(--muted);font-size:12px}
  .sub{color:var(--muted);font-size:12px}
</style>
</head>
<body>
<header>
  <div class="brand">
    <h1>WARRANT <span class="sub">— a licensing authority for AI agents</span></h1>
    <p>Agents earn the right to act in a proving ground · licenses are revocable · drift is caught</p>
  </div>
  <div class="controls">
    <button id="b-exams">① Proving ground</button>
    <button id="b-prod" class="ghost" disabled>② Production</button>
    <button id="b-drift" class="warn" disabled>③ Model updated overnight</button>
    <button id="b-recert" class="ghost" disabled>④ Re-certify</button>
  </div>
</header>

<div class="wrap">
  <div>
    <div class="card">
      <h2>Proving ground</h2>
      <div class="exambar"><i id="examBar"></i></div>
      <div class="examnow" id="examNow">Press ① to manufacture incidents and grade the agent.</div>
    </div>
    <div class="card">
      <h2>Agent activity</h2>
      <div id="log"></div>
    </div>
    <div class="card">
      <h2>Error rate vs. learned control limit (production)</h2>
      <canvas id="chart" width="640" height="180"></canvas>
      <div class="legend">
        <span><i class="dot" style="background:var(--red)"></i>before fix</span>
        <span><i class="dot" style="background:var(--green)"></i>after (in band)</span>
        <span><i class="dot" style="background:var(--red)"></i>after (out of band)</span>
        <span><i class="dot" style="background:var(--amber)"></i>control limit</span>
      </div>
    </div>
  </div>
  <div>
    <div class="card">
      <h2>License registry</h2>
      <div id="registry"><div class="sub">No action classes certified yet.</div></div>
      <div class="fp" id="fp"></div>
    </div>
    <div class="card">
      <h2>What you're watching</h2>
      <div class="sub" id="explain">
        Warrant issues one <b>license per action class</b>. A license needs three things:
        a Wilson-bounded hit-rate over enough graded outcomes, good <b>calibration</b>
        (confidence that matches reality), and a brain whose <b>fingerprint</b> hasn't changed.
        Licenses are <b>revoked</b> on a violated prediction and invalidated on model drift.
      </div>
    </div>
  </div>
</div>
<div class="foot">Evals tell you how smart an agent is. Warrant tells production <b>how much rope to give it</b> — and takes it back.</div>

<script>
const $ = id => document.getElementById(id);
const logEl=$('log'), regEl=$('registry'), THRESH=0.5;
const metrics=[];
const btns={exams:$('b-exams'),prod:$('b-prod'),drift:$('b-drift'),recert:$('b-recert')};

function tagOf(m){const x=m.match(/^\[([A-Z]+)\]/);return x?x[1]:''}
function addLine(msg){
  const tag=tagOf(msg), d=document.createElement('div'); d.className='ln t-'+tag;
  let rest=msg.replace(/^\[[A-Z]+\]\s*/,''), cls='';
  if(/INSIDE|RESOLVED|recovered|HIT|LICENSED|AUTONOMOUS/.test(msg)) cls='ok';
  if(/OUTSIDE|WRONG|MISS|still degraded|SUSPENDED|revoked/.test(msg)) cls='bad';
  if(/HUMAN-IN-THE-LOOP|approval|PROVISIONAL/.test(msg)) cls='warn';
  if(/DRIFT/.test(msg)) cls='pur';
  d.innerHTML='<span class="tag">'+tag+'</span><span class="'+cls+'">'+
    rest.replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))+'</span>';
  logEl.appendChild(d); logEl.scrollTop=logEl.scrollHeight;
}
function roundSep(t){const d=document.createElement('div');d.className='round-sep';d.textContent=t;
  logEl.appendChild(d);logEl.scrollTop=logEl.scrollHeight;}

function renderRegistry(ev){
  $('fp').textContent='brain fingerprint: '+ev.fingerprint;
  if(!ev.items.length){regEl.innerHTML='<div class="sub">No action classes certified yet.</div>';return;}
  regEl.innerHTML='';
  ev.items.sort((a,b)=>a.action_class.localeCompare(b.action_class)).forEach(l=>{
    const pct=Math.round((l.confidence||0)*100);
    const hit=l.hit_rate==null?'—':Math.round(l.hit_rate*100)+'%';
    const div=document.createElement('div'); div.className='lic';
    div.innerHTML=
      '<div class="name">'+l.action_class+'</div>'+
      '<div class="pill '+l.status+'">'+l.status+'</div>'+
      '<div class="meta">conf '+(l.confidence||0).toFixed(2)+' · hit '+hit+
        ' · calib '+l.calibration+' · n='+l.samples+' ('+l.exams+' exam/'+l.production+' prod)'+
        (l.drifted?' · ⚠ drifted':'')+'</div>'+
      '<div class="cbar"><i style="width:'+Math.min(100,pct)+'%"></i></div>'+
      '<div class="thr">threshold '+Math.round(THRESH*100)+'% &nbsp;'+(l.reason||'')+'</div>';
    regEl.appendChild(div);
  });
}
function drawChart(){
  const c=$('chart'),x=c.getContext('2d'),W=c.width,H=c.height,padL=40,padB=22,padT=10;
  x.clearRect(0,0,W,H); if(!metrics.length)return;
  let mx=0; metrics.forEach(m=>{mx=Math.max(mx,m.before,m.after,m.limit)}); mx=mx*1.15||0.1;
  const pH=H-padB-padT,pW=W-padL-8,y=v=>padT+pH-(v/mx)*pH;
  x.strokeStyle='#22304f';x.beginPath();x.moveTo(padL,padT);x.lineTo(padL,padT+pH);x.lineTo(W-4,padT+pH);x.stroke();
  const slot=pW/metrics.length;
  metrics.forEach((m,i)=>{const cx=padL+slot*i+slot/2,bw=Math.min(24,slot*0.3);
    x.fillStyle='rgba(255,92,114,.85)';x.fillRect(cx-bw-2,y(m.before),bw,padT+pH-y(m.before));
    x.fillStyle=m.correct?'rgba(34,201,138,.9)':'rgba(255,92,114,.9)';x.fillRect(cx+2,y(m.after),bw,padT+pH-y(m.after));
    x.fillStyle='#8da2c0';x.font='11px system-ui';x.textAlign='center';x.fillText('R'+m.round,cx,H-7);});
  const lim=metrics[metrics.length-1].limit;
  x.strokeStyle='#ffc04d';x.setLineDash([5,4]);x.beginPath();x.moveTo(padL,y(lim));x.lineTo(W-4,y(lim));x.stroke();x.setLineDash([]);
  x.fillStyle='#ffc04d';x.textAlign='left';x.font='10px system-ui';x.fillText('control limit',padL+4,y(lim)-4);
}

function stream(url, onEv, onDone){
  Object.values(btns).forEach(b=>b.disabled=true);
  const es=new EventSource(url);
  es.onmessage=e=>{const d=JSON.parse(e.data);
    if(d.type==='done'){es.close(); onDone&&onDone(); return;}
    onEv(d);
  };
  es.onerror=()=>{es.close(); onDone&&onDone();};
}
function setStage(stage){ // which buttons are live
  btns.exams.disabled=false;
  btns.prod.disabled = stage<1;
  btns.drift.disabled = stage<2;
  btns.recert.disabled = stage<3;
}

function handleCommon(d){
  if(d.type==='log') addLine(d.msg);
  else if(d.type==='licenses') renderRegistry(d);
  else if(d.type==='exam'){
    $('examBar').style.width=Math.round(d.n/d.total*100)+'%';
    $('examNow').innerHTML='exam '+d.n+'/'+d.total+' &nbsp; '+d.scenario+
      ' &nbsp;→ chose <b>'+d.chosen+'</b> &nbsp;'+(d.correct?'<span class="ok">HIT</span>':'<span class="bad">MISS</span>');
  }
  else if(d.type==='phase'){ roundSep(d.title+' — '+d.total+' exams'); $('examBar').style.width='0%'; }
  else if(d.type==='round'){ roundSep('Round '+d.n+'/'+d.total+' — '+d.title); }
  else if(d.type==='metric'){ metrics.push(d); drawChart(); }
}

btns.exams.onclick=()=>{ logEl.innerHTML=''; metrics.length=0; drawChart();
  $('examNow').textContent='Manufacturing incidents…';
  stream('/exams',handleCommon,()=>{ $('examNow').innerHTML='Proving ground complete — licenses issued. Now send it to <b>production</b>.'; setStage(1); });
};
btns.prod.onclick=()=>{ stream('/production',handleCommon,()=>setStage(2)); };
btns.drift.onclick=()=>{ stream('/drift',handleCommon,()=>setStage(3)); };
btns.recert.onclick=()=>{ $('examBar').style.width='0%'; stream('/recertify',handleCommon,()=>setStage(3)); };

// initial registry
fetch('/licenses').then(r=>r.json()).then(renderRegistry).catch(()=>{});
</script>
</body>
</html>
"""
