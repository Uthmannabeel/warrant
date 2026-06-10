"""Warrant live dashboard — a polished web UI over the same agent loop.

Run the sandbox AND this dashboard, then open http://localhost:8050 and click "Run incidents":

    # terminal A
    python -m uvicorn sandbox.app:app --port 9000
    # terminal B
    python -m uvicorn warrant.dashboard:app --port 8050

Self-contained (no external CDNs) so it works offline / behind a proxy.
"""
from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from .ledger import LEDGER_PATH, Ledger
from .loop import run_once

app = FastAPI(title="Warrant Dashboard")

SEQUENCE = ["leak", "leak", "leak", "leak", "leak", "decoy"]


def _stamp() -> str:
    return datetime.fromtimestamp(time.time(), tz=timezone.utc).isoformat(timespec="seconds")


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(HTML)


@app.get("/run")
async def run() -> StreamingResponse:
    async def gen():
        if Path(LEDGER_PATH).exists():
            Path(LEDGER_PATH).unlink()
        ledger = Ledger()
        queue: asyncio.Queue = asyncio.Queue()

        def emit(msg: str) -> None:
            queue.put_nowait({"type": "log", "msg": msg})

        async def driver():
            for i, fault in enumerate(SEQUENCE, 1):
                queue.put_nowait({"type": "round", "n": i, "total": len(SEQUENCE),
                                  "scenario": fault})
                try:
                    res = await run_once(fault, ledger, _stamp(), emit=emit)
                except Exception as exc:  # noqa: BLE001
                    queue.put_nowait({"type": "log",
                                      "msg": f"[ERROR] {type(exc).__name__}: {exc}"})
                    break
                ac = res.hypothesis.action_class
                queue.put_nowait({"type": "metric", "round": i, "scenario": fault,
                                  "before": res.metrics_before.get("error_rate"),
                                  "after": res.metric_after, "limit": res.prediction.upper,
                                  "correct": res.correct})
                queue.put_nowait({"type": "ledger", "action": ac,
                                  "rate": ledger.hit_rate(ac), "conf": ledger.confidence(ac),
                                  "n": ledger.sample_size(ac),
                                  "autonomous": ledger.may_act_autonomously(ac)})
            queue.put_nowait({"type": "done"})

        task = asyncio.create_task(driver())
        try:
            while True:
                ev = await queue.get()
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("type") == "done":
                    break
        finally:
            await task

    return StreamingResponse(gen(), media_type="text/event-stream")


HTML = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Warrant — an agent that earns the right to act</title>
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
         padding:18px 26px;border-bottom:1px solid var(--line)}
  .brand h1{margin:0;font-size:19px;letter-spacing:.2px}
  .brand p{margin:2px 0 0;color:var(--muted);font-size:13px}
  button{background:linear-gradient(180deg,#2b6fff,#1f5be0);color:#fff;border:0;border-radius:10px;
         padding:11px 18px;font-weight:600;cursor:pointer;box-shadow:0 6px 18px rgba(43,111,255,.35)}
  button:disabled{opacity:.5;cursor:not-allowed;box-shadow:none}
  .wrap{display:grid;grid-template-columns:1.4fr .9fr;gap:18px;padding:18px 26px}
  .card{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);
        border-radius:14px;padding:16px 18px}
  .card h2{margin:0 0 12px;font-size:12px;text-transform:uppercase;letter-spacing:1.4px;color:var(--muted)}
  #log{height:540px;overflow:auto;font-family:ui-monospace,Consolas,monospace;font-size:12.5px}
  .ln{padding:2px 6px;border-radius:6px;white-space:pre-wrap;word-break:break-word}
  .tag{display:inline-block;min-width:96px;color:var(--muted)}
  .round-sep{margin:12px 0 6px;color:#fff;font-weight:700;border-top:1px dashed var(--line);padding-top:10px}
  .t-BRAIN .tag{color:var(--purple)} .t-PREDICT .tag{color:var(--blue)}
  .t-CONTEXT .tag{color:var(--teal)} .t-TRUST .tag{color:var(--amber)}
  .t-APPROVAL .tag{color:var(--amber)} .t-ACT .tag{color:var(--cyan)}
  .t-LEDGER .tag{color:var(--amber)} .t-BASELINE .tag{color:var(--muted)}
  .ok{color:var(--green)} .bad{color:var(--red)} .warn{color:var(--amber)}
  .trust-val{font-size:42px;font-weight:800;letter-spacing:.5px}
  .bar{height:12px;background:#0a1226;border:1px solid var(--line);border-radius:99px;overflow:hidden;margin:10px 0}
  .bar > i{display:block;height:100%;width:0;background:linear-gradient(90deg,#2b6fff,#36d2c4);transition:width .4s}
  .badge{display:inline-block;padding:5px 11px;border-radius:99px;font-weight:700;font-size:12px}
  .badge.auto{background:rgba(34,201,138,.16);color:var(--green);border:1px solid rgba(34,201,138,.4)}
  .badge.human{background:rgba(255,192,77,.14);color:var(--amber);border:1px solid rgba(255,192,77,.4)}
  .sub{color:var(--muted);font-size:12px}
  canvas{width:100%;height:230px;display:block}
  .legend{display:flex;gap:16px;color:var(--muted);font-size:12px;margin-top:8px}
  .dot{display:inline-block;width:9px;height:9px;border-radius:99px;margin-right:5px;vertical-align:middle}
  .foot{padding:6px 26px 22px;color:var(--muted);font-size:12px}
</style>
</head>
<body>
<header>
  <div class="brand">
    <h1>WARRANT <span class="sub">— an agent that earns the right to act</span></h1>
    <p>Falsifiable predictions · earned autonomy · trustworthy when it's wrong</p>
  </div>
  <button id="run">▶ Run incidents</button>
</header>

<div class="wrap">
  <div class="card">
    <h2>Agent activity</h2>
    <div id="log"></div>
  </div>
  <div>
    <div class="card" style="margin-bottom:18px">
      <h2>Trust — restart_connection_pool</h2>
      <div><span id="trustVal" class="trust-val">—</span> <span class="sub">confidence</span></div>
      <div class="bar"><i id="trustBar"></i></div>
      <div><span id="trustBadge" class="badge human">awaiting run</span>
           <span id="trustMeta" class="sub"></span></div>
    </div>
    <div class="card">
      <h2>Error rate vs. learned control limit</h2>
      <canvas id="chart" width="640" height="230"></canvas>
      <div class="legend">
        <span><i class="dot" style="background:var(--red)"></i>before fix</span>
        <span><i class="dot" style="background:var(--green)"></i>after (in band)</span>
        <span><i class="dot" style="background:var(--red)"></i>after (out of band)</span>
        <span><i class="dot" style="background:var(--amber)"></i>control limit</span>
      </div>
    </div>
  </div>
</div>
<div class="foot">Every agent is impressive when it's right. Warrant is trustworthy when it's <b>wrong</b>.</div>

<script>
const logEl = document.getElementById('log');
const btn = document.getElementById('run');
const metrics = [];

function tagOf(msg){ const m = msg.match(/^\[([A-Z]+)\]/); return m ? m[1] : ''; }
function addLine(msg){
  const tag = tagOf(msg);
  const div = document.createElement('div');
  div.className = 'ln t-' + tag;
  let rest = msg.replace(/^\[[A-Z]+\]\s*/,'');
  let cls = '';
  if(/INSIDE|RESOLVED|recovered|HIT/.test(msg)) cls='ok';
  if(/OUTSIDE|WRONG|MISS|still degraded/.test(msg)) cls='bad';
  if(/AUTONOMOUS/.test(msg)) cls='ok';
  if(/HUMAN-IN-THE-LOOP|approval/.test(msg)) cls='warn';
  div.innerHTML = '<span class="tag">'+tag+'</span><span class="'+cls+'">'+
                  rest.replace(/[<>&]/g,c=>({'<':'&lt;','>':'&gt;','&':'&amp;'}[c]))+'</span>';
  logEl.appendChild(div); logEl.scrollTop = logEl.scrollHeight;
}
function roundSep(n,total,scenario){
  const div=document.createElement('div'); div.className='round-sep';
  div.textContent = 'Round '+n+'/'+total+' — '+(scenario==='leak'?'CONNECTION LEAK':'DECOY (obvious fix is wrong)');
  logEl.appendChild(div); logEl.scrollTop=logEl.scrollHeight;
}
function updateTrust(d){
  const pct = Math.round((d.conf||0)*100);
  document.getElementById('trustVal').textContent = pct+'%';
  document.getElementById('trustBar').style.width = Math.min(100,pct)+'%';
  const badge=document.getElementById('trustBadge');
  badge.textContent = d.autonomous ? 'AUTONOMOUS' : 'HUMAN-IN-THE-LOOP';
  badge.className = 'badge ' + (d.autonomous?'auto':'human');
  document.getElementById('trustMeta').textContent =
     ' · ' + Math.round((d.rate||0)*100) + '% over ' + d.n + ' run(s)';
}
function drawChart(){
  const c=document.getElementById('chart'), x=c.getContext('2d');
  const W=c.width,H=c.height,padL=40,padB=24,padT=12;
  x.clearRect(0,0,W,H);
  if(!metrics.length) return;
  let maxV=0; metrics.forEach(m=>{maxV=Math.max(maxV,m.before,m.after,m.limit)});
  maxV=maxV*1.15||0.1;
  const plotH=H-padB-padT, plotW=W-padL-8;
  const y=v=>padT+plotH-(v/maxV)*plotH;
  // axes
  x.strokeStyle='#22304f'; x.lineWidth=1;
  x.beginPath(); x.moveTo(padL,padT); x.lineTo(padL,padT+plotH); x.lineTo(W-4,padT+plotH); x.stroke();
  const n=metrics.length, slot=plotW/n;
  metrics.forEach((m,i)=>{
    const cx=padL+slot*i+slot/2, bw=Math.min(26,slot*0.3);
    // before (red)
    x.fillStyle='rgba(255,92,114,.85)';
    x.fillRect(cx-bw-2, y(m.before), bw, padT+plotH-y(m.before));
    // after (green/red)
    x.fillStyle = m.correct ? 'rgba(34,201,138,.9)' : 'rgba(255,92,114,.9)';
    x.fillRect(cx+2, y(m.after), bw, padT+plotH-y(m.after));
    // round label
    x.fillStyle='#8da2c0'; x.font='11px system-ui'; x.textAlign='center';
    x.fillText('R'+m.round, cx, H-8);
  });
  // control limit line (use latest limit)
  const lim=metrics[metrics.length-1].limit;
  x.strokeStyle='#ffc04d'; x.setLineDash([5,4]); x.beginPath();
  x.moveTo(padL,y(lim)); x.lineTo(W-4,y(lim)); x.stroke(); x.setLineDash([]);
  x.fillStyle='#ffc04d'; x.textAlign='left'; x.font='10px system-ui';
  x.fillText('control limit', padL+4, y(lim)-4);
}
btn.onclick=()=>{
  btn.disabled=true; logEl.innerHTML=''; metrics.length=0; drawChart();
  const es=new EventSource('/run');
  es.onmessage=(e)=>{
    const d=JSON.parse(e.data);
    if(d.type==='round') roundSep(d.n,d.total,d.scenario);
    else if(d.type==='log') addLine(d.msg);
    else if(d.type==='metric'){ metrics.push(d); drawChart(); }
    else if(d.type==='ledger') updateTrust(d);
    else if(d.type==='done'){ es.close(); btn.disabled=false; }
  };
  es.onerror=()=>{ es.close(); btn.disabled=false; };
};
</script>
</body>
</html>
"""
