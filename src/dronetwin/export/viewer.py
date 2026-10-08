"""Self-contained HTML line viewer: animated process blocks driven by the event log, plus the report."""
from __future__ import annotations

import json
from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
from plotly.offline import get_plotlyjs

KEEP = ["RELEASE", "PRINT_START", "PAINT_START", "PBS_IN", "LOAD", "STATE", "ELEMENT_START", "TORQUE_NOK",
        "LINE_STOP", "LINE_RESUME", "MOVE", "INSPECT_OK", "INSPECT_NOK", "SHIP", "REPAIR",
        "TRANSFER", "BELT_IN", "PICK"]
FRAME_COLOURS = {"BLK": "#26262b", "RED": "#c8191e", "YEL": "#f5c814", "SLV": "#bec3cd"}
SERIES = {"baseline": "#2a78d6", "consolidated": "#eb6834", "growth_8pos": "#1baf7a", "growth_6pos": "#eda100"}
INK, MUTED, GRID, AXIS = "#0b0b0b", "#898781", "#e1e0d9", "#c3c2b7"


def _index(values) -> tuple[list, dict]:
    uniq = sorted({v for v in values if isinstance(v, str)})
    return uniq, {v: i for i, v in enumerate(uniq)}


def scenario_payload(result, report, reps) -> dict:
    cfg = result.cfg
    ev = result.events[result.events.event.isin(KEEP)]
    assets = list(cfg.assets)
    a_ix = {a: i for i, a in enumerate(assets)}
    serials, s_ix = _index(ev.serial)
    skus, k_ix = _index(ev.sku)
    pns, p_ix = _index(ev.pn)
    states, st_ix = _index(ev.state)
    e_ix = {e: i for i, e in enumerate(KEEP)}
    pitch = cfg.pitch_m
    rows = []
    for t, a, e, st, pn, se, sk, x, y, v in ev[["t", "asset_id", "event", "state", "pn", "serial", "sku", "x", "y", "value"]].itertuples(index=False, name=None):
        if e == "MOVE":
            v = int(round(x / pitch)) if abs(y) < 1e-6 else -1
        elif v != v:  # NaN
            v = None
        rows.append([round(float(t), 1), e_ix[e], a_ix[a], s_ix.get(se, -1), k_ix.get(sk, -1),
                     p_ix.get(pn, -1), st_ix.get(st, -1), None if v is None else round(float(v), 1)])
    stations = [{"id": s.asset_id, "name": s.name.replace("_", " "), "total": sum(n for _, n in s.elements),
                 "inspect": s.inspect} for s in cfg.stations]
    sc = cfg.scenario
    return {
        "name": sc["name"], "takt": sc["takt_s"], "index": sc["index_s"], "t0": result.t0, "t1": result.t1,
        "clock": sc["shift_start_clock"], "target": int(round((result.t1 - result.t0) / sc["takt_s"])),
        "stations": stations, "assets": assets, "events": KEEP, "serials": serials, "skus": skus, "pns": pns,
        "states": states, "rows": rows, "summary": report.summary,
        "pull": sc.get("pull"), "printers": sc["upstream"]["printers"],
        "reps": reps.to_dict(orient="list"),
    }


def _layout(title: str, height: int = 320, **kw) -> dict:
    base = dict(title=dict(text=title, font=dict(size=14, color=INK), x=0, xanchor="left"), height=height,
                margin=dict(l=56, r=16, t=48, b=48), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(family="system-ui, -apple-system, Segoe UI, sans-serif", size=12, color="#52514e"),
                xaxis=dict(gridcolor=GRID, linecolor=AXIS, zeroline=False),
                yaxis=dict(gridcolor=GRID, linecolor=AXIS, zeroline=False), bargap=0.35,
                legend=dict(orientation="h", y=1.12, x=1, xanchor="right"))
    base.update(kw)
    return base


def report_figures(payloads: list[dict]) -> list[dict]:
    figs = []
    for p in payloads:
        s = p["summary"]
        ids = list(s["work_content_mean_s"])
        avail = p["takt"] - p["index"]
        f = go.Figure(go.Bar(x=ids, y=[s["work_content_mean_s"][i] for i in ids], marker_color=SERIES.get(p["name"], "#4a3aa7"),
                             marker_line_width=0, name="Mean work content",
                             hovertemplate="%{x}: %{y:.0f} s<extra></extra>"))
        f.add_hline(y=avail, line_dash="dash", line_color=MUTED, line_width=1.5,
                    annotation_text=f"available per takt {avail:.0f} s", annotation_position="top left",
                    annotation_font_color=MUTED)
        f.update_layout(**_layout(f"Line balance · {p['name']} · {len(ids)} stations",
                                  yaxis=dict(title="seconds per drone", gridcolor=GRID, range=[0, p["takt"] * 1.05])))
        figs.append(f)
    f = go.Figure()
    for p in payloads:
        r = p["reps"]
        f.add_trace(go.Scatter(x=r["day"], y=r["torque_nok"], mode="lines+markers", name=p["name"],
                               line=dict(color=SERIES.get(p["name"], "#4a3aa7"), width=2), marker=dict(size=8),
                               hovertemplate=p["name"] + " · day %{x}: %{y} NOK<extra></extra>"))
    f.update_layout(**_layout("Torque NOK re-hits per day (20 replications)",
                              xaxis=dict(title="simulated day", gridcolor=GRID, dtick=2),
                              yaxis=dict(title="re-hits per day", gridcolor=GRID, rangemode="tozero")))
    figs.append(f)
    f = go.Figure()
    for p in payloads:
        r = p["reps"]
        f.add_trace(go.Bar(x=r["day"], y=r["colour_mismatch_detected"], name=p["name"], marker_line_width=0,
                           marker_color=SERIES.get(p["name"], "#4a3aa7"),
                           hovertemplate=p["name"] + " · day %{x}: %{y} caught<extra></extra>"))
    f.update_layout(**_layout("Wrong-colour controllers caught at final inspection, per day",
                              barmode="group", xaxis=dict(title="simulated day", gridcolor=GRID, dtick=2),
                              yaxis=dict(title="drones sent to repair", gridcolor=GRID, dtick=1, rangemode="tozero")))
    figs.append(f)
    base = payloads[0]["summary"]
    skus = sorted(set(base["mix_in"]) | set(base["mix_out"]))
    f = go.Figure([go.Bar(x=skus, y=[base["mix_in"].get(k, 0) for k in skus], name="released", marker_color="#2a78d6",
                          marker_line_width=0, hovertemplate="%{x} released: %{y}<extra></extra>"),
                   go.Bar(x=skus, y=[base["mix_out"].get(k, 0) for k in skus], name="shipped", marker_color="#1baf7a",
                          marker_line_width=0, hovertemplate="%{x} shipped: %{y}<extra></extra>")])
    f.update_layout(**_layout("SKU mix, released vs shipped (baseline, one day)", barmode="group",
                              yaxis=dict(title="drones", gridcolor=GRID)))
    figs.append(f)
    return [json.loads(pio.to_json(x)) for x in figs]


def write_viewer(payloads: list[dict], path) -> None:
    data = {"scenarios": payloads, "figures": report_figures(payloads), "frameColours": FRAME_COLOURS,
            "series": SERIES}
    blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    plotly_js = get_plotlyjs()
    html = TEMPLATE.replace("__DATA__", blob).replace("__PLOTLY__", plotly_js)
    Path(path).write_text(html, encoding="utf-8")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Drone GA Line Viewer</title>
<style>
:root{--surface:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--ring:rgba(11,11,11,.10);--good:#0ca30c;--warn:#fab219;--crit:#d03b3b;--crit-text:#b42318;--idle:#c3c2b7;--accent:#2a78d6}
@media (prefers-color-scheme: dark){:root:where(:not([data-theme="light"])){--surface:#1a1a19;--plane:#0d0d0d;--ink:#fff;
--ink2:#c3c2b7;--muted:#898781;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--idle:#383835;--accent:#3987e5;--crit-text:#ff7a70}}
*{box-sizing:border-box}body{margin:0;background:var(--plane);color:var(--ink);font:13px system-ui,-apple-system,"Segoe UI",sans-serif}
header{display:flex;align-items:center;gap:16px;padding:12px 20px;border-bottom:1px solid var(--ring);background:var(--surface);flex-wrap:wrap}
h1{font-size:16px;margin:0;font-weight:600}.tabs button,.ctl button,.ctl select{font:inherit;border:1px solid var(--ring);background:var(--surface);
color:var(--ink);border-radius:6px;padding:5px 10px;cursor:pointer}.tabs button.on{background:var(--ink);color:var(--surface)}
.ctl{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.ctl input[type=range]{width:min(520px,60vw)}
main{padding:16px 20px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:10px;margin-bottom:12px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:8px;padding:8px 12px}.card .k{color:var(--ink2);font-size:12px}
.card .v{font-size:20px;font-weight:600;margin-top:2px}.panel{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:8px;overflow-x:auto}
svg text{fill:var(--ink);font:12px system-ui,-apple-system,"Segoe UI",sans-serif}svg .sub{fill:var(--ink2);font-size:11px}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--ink2);font-size:12px;margin:8px 2px}.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:-1px}
#report .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(460px,1fr));gap:12px}table{border-collapse:collapse;width:100%;font-variant-numeric:tabular-nums}
th,td{text-align:right;padding:5px 10px;border-bottom:1px solid var(--grid)}th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:500}
.marks{position:relative;height:8px;width:min(520px,60vw);margin-top:2px}.marks i{position:absolute;top:0;width:2px;height:8px;border-radius:1px}
.hidden{display:none}h3{font-size:14px;margin:6px 4px 4px}.note{color:var(--ink2);font-size:12px;margin:0 4px 8px}.over{color:var(--crit-text);font-weight:600}.scrubwrap{position:relative}#tip{position:absolute;top:-22px;transform:translateX(-50%);background:var(--ink);color:var(--surface);font-size:11px;padding:2px 6px;border-radius:4px;pointer-events:none;white-space:nowrap}
.tools{display:flex;gap:8px;align-items:center;margin:0 4px 8px;flex-wrap:wrap}.tools button,.tools select{font:inherit;font-size:12px;border:1px solid var(--ring);background:var(--surface);color:var(--ink);border-radius:6px;padding:3px 8px;cursor:pointer}tfoot td{color:var(--ink2);border-top:1px solid var(--axis)}
</style></head><body>
<header>
 <h1>Drone GA line · live viewer</h1>
 <div class="tabs"><button id="tabLive" class="on">Live line</button> <button id="tabReport">Report</button></div>
 <div class="ctl"><label>Scenario <select id="scen"></select></label></div>
</header>
<main>
<section id="live">
 <div class="ctl" style="margin-bottom:10px">
  <button id="play">▶ Play</button>
  <label>Speed <select id="speed"><option>1</option><option>10</option><option selected>60</option><option>120</option><option>300</option><option>600</option></select>×</label>
  <div class="scrubwrap"><span id="tip" class="hidden"></span><input id="scrub" type="range" min="0" step="1"><div class="marks" id="marks"></div></div>
  <span id="clock" style="font-weight:600;font-variant-numeric:tabular-nums"></span>
 </div>
 <div class="cards" id="cards"></div>
 <div class="panel"><svg id="line" role="img" aria-label="Animated GA line process blocks"></svg></div>
 <div class="legend">
  <span><i class="sw" style="background:var(--good)"></i>working</span><span><i class="sw" style="background:var(--idle)"></i>done, waiting for index</span>
  <span><i class="sw" style="background:var(--crit)"></i>stopped (andon, over takt)</span><span><i class="sw" style="background:var(--warn)"></i>torque NOK re-hit</span>
  <span><i class="sw" style="background:var(--accent)"></i>kanban card in use (order printing → frame picked)</span>
  <span>Chip = drone in its order colour:</span><span id="colourKey"></span>
 </div>
</section>
<section id="report" class="hidden">
 <div class="panel" style="margin-bottom:12px"><div class="tools"><button data-csv="kpiTable">Download CSV</button></div><table id="kpiTable"></table></div>
 <div class="panel" style="margin-bottom:12px"><h3 id="dayTitle"></h3><p class="note">Takt load = work ÷ time available per takt (plan; above 100 % the station cannot make takt and stops the line). Utilization = busy time ÷ actual elapsed time (capped at 100 %).</p><div class="tools"><button data-csv="dayTable">Download CSV</button></div><div style="overflow-x:auto"><table id="dayTable"></table></div></div>
 <div class="panel" style="margin-bottom:12px"><h3>Station takt load · utilization, per simulated day</h3><div class="tools"><label>Station <select id="stFilter"><option value="">all</option></select></label><button data-csv="stationTable">Download CSV</button></div><div style="overflow-x:auto"><table id="stationTable"></table></div></div>
 <div class="grid" id="figs"></div>
</section>
</main>
<script type="application/json" id="data">__DATA__</script>
<script>__PLOTLY__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const $ = id => document.getElementById(id);
let S, st, simT = 0, playing = false, lastWall = null, ptr = 0;
const W = 112, G = 22, H = 150, Y0 = 40;

function fmtClock(t){ const [h,m] = S.clock.split(':').map(Number); let s = Math.round(h*3600 + m*60 + (t - S.t0)); s = ((s % 86400) + 86400) % 86400;
  return String(Math.floor(s/3600)).padStart(2,'0') + ':' + String(Math.floor(s/60)%60).padStart(2,'0') + ':' + String(s%60).padStart(2,'0'); }
function colourOf(skuIdx){ if (skuIdx < 0) return '#888'; const c = S.skus[skuIdx].split('-')[1]; return D.frameColours[c] || '#888'; }

function reset(){
  st = {stations: S.stations.map(s => ({state:'EMPTY', serial:-1, sku:-1, done:0, el:'', flash:0})), skillet:{}, pbs:[], printing:new Map(), transfer:null,
        belt:new Map(), painting:new Map(), kanban:new Set(),
        shipped:0, shippedAll:0, shipChips:[], repair:null, repairs:0, stops:0, stopS:0, nok:0, catches:0, released:0};
  ptr = 0;
}
function apply(r){
  const [t, e, a, se, sk, pn, sv, v] = r, ev = S.events[e], aid = S.assets[a], inWin = t >= S.t0;
  const si = S.stations.findIndex(s => s.id === aid), s = si >= 0 ? st.stations[si] : null;
  switch(ev){
    case 'STATE': { const state = S.states[sv]; if (state === 'WORKING'){ Object.assign(s, {state, serial:se, sku:sk, done:0, el:''}); }
      else if (state === 'EMPTY'){ Object.assign(s, {state, serial:-1, sku:-1, done:0, el:''}); } else { s.state = state; s.done = S.stations[si].total; s.el = ''; } break; }
    case 'ELEMENT_START': s.done += 1; s.el = S.pns[pn].replaceAll('_',' '); break;
    case 'TORQUE_NOK': if (playing) s.flash = performance.now() + 700; if (inWin) st.nok++; break;
    case 'LINE_STOP': s.state = 'STOPPED'; break;
    case 'LINE_RESUME': if (inWin){ st.stops++; st.stopS += v; } break;
    case 'MOVE': st.skillet[aid] = {pos:v, serial:se, sku:sk}; break;
    case 'PRINT_START': st.printing.set(se, sk); st.kanban.add(se); break;
    case 'TRANSFER': st.printing.delete(se); st.transfer = {serial:se, sku:sk}; break;
    case 'BELT_IN': if (st.transfer && st.transfer.serial === se) st.transfer = null; st.belt.set(se, sk); break;
    case 'PAINT_START': st.printing.delete(se); st.belt.delete(se); st.painting.set(se, sk); break;
    case 'PBS_IN': st.painting.delete(se); st.pbs.push({serial:se, sku:sk}); break;
    case 'PICK': st.pbs = st.pbs.filter(p => p.serial !== se); st.kanban.delete(se); break;
    case 'LOAD': st.pbs = st.pbs.filter(p => p.serial !== se); st.kanban.delete(se); break;
    case 'SHIP': st.shippedAll++; if (inWin) st.shipped++; st.shipChips.push(sk); if (st.shipChips.length > 12) st.shipChips.shift(); if (st.repair && st.repair.serial === se) st.repair = null; break;
    case 'REPAIR': st.repair = {serial:se, sku:sk}; if (inWin) st.repairs++; break;
    case 'INSPECT_NOK': if (inWin) st.catches++; break;
    case 'RELEASE': if (inWin) st.released++; break;
  }
}
function advanceTo(t){
  if (t < simT - 1e-9){ reset(); }
  while (ptr < S.rows.length && S.rows[ptr][0] <= t){ apply(S.rows[ptr]); ptr++; }
  simT = t;
}

function el(tag, attrs, parent, text){ const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]); if (text !== undefined) n.textContent = text; parent.appendChild(n); return n; }
function chip(g, x, y, sku, size=12){ el('rect', {x, y, width:size, height:size, rx:3, fill: colourOf(sku), stroke:'var(--ring)'}, g); }
function serialTxt(i){ return i >= 0 ? S.serials[i] : ''; }

function draw(){
  const svg = $('line'); svg.innerHTML = '';
  const nodes = ['PRINTER01','PAINT01','PBS', ...S.stations.map(s => s.id), 'SHIP'];
  const width = 20 + nodes.length*(W+G), height = 320; svg.setAttribute('viewBox', `0 0 ${width} ${height}`); svg.setAttribute('width', width); svg.setAttribute('height', height);
  const X = i => 20 + i*(W+G);
  el('text', {x:X(0), y:22, class:'sub'}, svg, S.pull ? `PULL · order triggers print · kanban ${S.pull.wip_cap}` : 'OUTSIDE ANALYSED SYSTEM · fixed times');
  el('text', {x:X(3), y:22, class:'sub'}, svg, `GA PACED LINE · takt ${S.takt} s · ${S.stations.length} positions`);
  el('line', {x1:X(3)-G/2, y1:12, x2:X(3)-G/2, y2:300, stroke:'var(--axis)', 'stroke-dasharray':'4 4'}, svg);
  for (let i = 0; i < nodes.length - 1; i++) el('path', {d:`M${X(i)+W} ${Y0+H/2} H${X(i+1)-3}`, stroke:'var(--axis)', 'stroke-width':1.5, fill:'none', 'marker-end':'url(#ah)'}, svg);
  const defs = el('defs', {}, svg); const m = el('marker', {id:'ah', viewBox:'0 0 10 10', refX:8, refY:5, markerWidth:6, markerHeight:6, orient:'auto'}, defs);
  el('path', {d:'M2 1L8 5L2 9', fill:'none', stroke:'var(--axis)', 'stroke-width':1.5}, m);
  const box = (i, title, sub, fill) => { const g = el('g', {}, svg); el('rect', {x:X(i), y:Y0, width:W, height:H, rx:8, fill:'var(--surface)', stroke:'var(--ring)'}, g);
    if (fill) el('rect', {x:X(i), y:Y0, width:6, height:H, rx:3, fill}, g); el('text', {x:X(i)+12, y:Y0+18, 'font-weight':600}, g, title); el('text', {x:X(i)+12, y:Y0+33, class:'sub'}, g, sub); return g; };
  // upstream
  const white = (g, x, y) => el('rect', {x, y, width:12, height:12, rx:3, fill:'#ebebe6', stroke:'var(--ring)'}, g);
  let g = box(0, S.pull ? 'Printers' : 'Printer', `${st.printing.size} of ${S.printers || 1} printing`, st.printing.size ? 'var(--good)' : 'var(--idle)');
  [...st.printing.keys()].forEach((se, k) => { white(g, X(0)+12, Y0+48 + k*18); el('text', {x:X(0)+30, y:Y0+58 + k*18}, g, serialTxt(se)); });
  if (st.transfer) el('text', {x:X(0)+12, y:Y0+128, class:'sub'}, g, 'KUKA2 → belt ' + serialTxt(st.transfer.serial));
  g = box(1, S.pull ? 'Paint conveyor' : 'Paint', S.pull ? `${st.belt.size} on belt · ${st.painting.size} in booth` : 'colour per order', st.painting.size ? 'var(--good)' : 'var(--idle)');
  [...st.belt.keys()].forEach((se, k) => white(g, X(1)+12 + k*15, Y0+48));
  [...st.painting.entries()].forEach(([se, sk], k) => { chip(g, X(1)+12, Y0+68 + k*18, sk); el('text', {x:X(1)+30, y:Y0+78 + k*18}, g, serialTxt(se)); });
  const cap = S.pull ? S.pull.wip_cap : 0;
  g = box(2, S.pull ? 'Buffer' : 'PBS', S.pull ? `${st.pbs.length} / ${cap} slots` : `${st.pbs.length} painted bodies`, 'var(--idle)');
  st.pbs.slice(0, 24).forEach((p, k) => chip(g, X(2)+12 + (k%6)*15, Y0+48 + Math.floor(k/6)*15, p.sku));
  if (S.pull){                                     // kanban cards: in use from PRINT_START until KUKA1 picks the frame
    el('text', {x:X(0), y:Y0+H+20, class:'sub'}, svg, `kanban cards ${st.kanban.size} / ${cap} in use`);
    for (let k = 0; k < cap; k++) el('rect', {x:X(0) + k*((3*(W+G)-G)/cap), y:Y0+H+28, width:(3*(W+G)-G)/cap - 4, height:14, rx:3,
      fill: k < st.kanban.size ? 'var(--accent)' : 'none', stroke:'var(--axis)'}, svg);
  }
  // stations
  const now = performance.now();
  S.stations.forEach((s, k) => { const ss = st.stations[k], i = 3 + k;
    const fill = ss.state === 'WORKING' ? 'var(--good)' : ss.state === 'STOPPED' ? 'var(--crit)' : 'var(--idle)';
    g = box(i, s.id, s.name, fill);
    if (ss.flash > now) el('rect', {x:X(i)-2, y:Y0-2, width:W+4, height:H+4, rx:10, fill:'none', stroke:'var(--warn)', 'stroke-width':3}, g);
    if (ss.serial >= 0){ chip(g, X(i)+12, Y0+46, ss.sku, 14); el('text', {x:X(i)+32, y:Y0+57}, g, serialTxt(ss.serial));
      el('text', {x:X(i)+12, y:Y0+78, class:'sub'}, g, S.skus[ss.sku]);
      const frac = Math.min(1, ss.done / s.total); el('rect', {x:X(i)+12, y:Y0+90, width:W-24, height:6, rx:3, fill:'var(--grid)'}, g);
      el('rect', {x:X(i)+12, y:Y0+90, width:(W-24)*frac, height:6, rx:3, fill}, g);
      el('text', {x:X(i)+12, y:Y0+112, class:'sub'}, g, `${ss.done}/${s.total} elements`);
      el('text', {x:X(i)+12, y:Y0+128, class:'sub'}, g, ss.el.slice(0, 18));
    } else el('text', {x:X(i)+12, y:Y0+58, class:'sub'}, g, 'no drone');
    if (s.inspect) el('text', {x:X(i)+12, y:Y0+142, class:'sub'}, g, `colour catches ${st.catches}`);
  });
  g = box(nodes.length - 1, 'Ship', `${st.shipped} / ${S.target} this shift`, 'var(--idle)');
  st.shipChips.forEach((c, k) => chip(g, X(nodes.length-1)+12 + (k%6)*15, Y0+48 + Math.floor(k/6)*15, c));
  // skillets on the line and the return lane
  el('rect', {x:X(3), y:250, width:(S.stations.length)*(W+G)-G, height:26, rx:13, fill:'none', stroke:'var(--grid)'}, svg);
  el('text', {x:X(3)+8, y:244, class:'sub'}, svg, 'skillet return lane');
  let free = 0;
  for (const [sid, p] of Object.entries(st.skillet)){
    if (p.pos >= 0){ const x = X(3 + p.pos) + W/2 - 18; el('rect', {x, y:Y0+H+6, width:36, height:10, rx:3, fill:'var(--ink2)'}, svg); el('text', {x:x+6, y:Y0+H+30, class:'sub'}, svg, sid); }
    else { el('rect', {x:X(3)+14 + free*44, y:257, width:36, height:12, rx:3, fill:'var(--axis)'}, svg); el('text', {x:X(3)+16 + free*44, y:266, class:'sub', 'font-size':9}, svg, sid); free++; }
  }
  // repair bay
  const rx = X(nodes.length - 2), ry = 250; el('rect', {x:rx, y:ry, width:W, height:46, rx:8, fill:'var(--surface)', stroke:'var(--ring)'}, svg);
  el('text', {x:rx+10, y:ry+18, 'font-weight':600}, svg, 'Repair bay'); el('text', {x:rx+10, y:ry+34, class:'sub'}, svg, st.repair ? serialTxt(st.repair.serial) : `${st.repairs} repaired`);
  // cards
  const hrs = Math.max(1e-9, (simT - S.t0) / 3600), win = simT >= S.t0;
  const cards = [['Shift clock', win ? fmtClock(simT) : 'warm-up'], ['Shipped / target', `${st.shipped} / ${S.target}`],
    ['JPH (this shift)', win && hrs > 0.05 ? (st.shipped / hrs).toFixed(1) : '–'], ['On the line', st.stations.filter(x => x.serial >= 0).length],
    ['Line stops', `${st.stops} · ${Math.round(st.stopS)} s`], ['Torque re-hits', st.nok], ['Colour catches', st.catches],
    S.pull ? ['Buffer · kanban', `${st.pbs.length} · ${st.kanban.size}/${S.pull.wip_cap}`] : ['PBS bodies', st.pbs.length]];
  $('cards').innerHTML = cards.map(([k, v]) => `<div class="card"><div class="k">${k}</div><div class="v">${v}</div></div>`).join('');
  $('clock').textContent = (win ? fmtClock(simT) : 'warm-up ' + Math.round(simT) + ' s');
  $('scrub').value = Math.round(simT);
}

function loop(ts){
  if (scrubTo !== null){ advanceTo(scrubTo); scrubTo = null; draw(); }
  if (playing){ if (lastWall !== null){ const dt = (ts - lastWall) / 1000 * Number($('speed').value); advanceTo(Math.min(S.t1, simT + dt)); if (simT >= S.t1) togglePlay(false); } lastWall = ts; draw(); }
  requestAnimationFrame(loop);
}
function togglePlay(on){ playing = on === undefined ? !playing : on; lastWall = null; $('play').textContent = playing ? '❚❚ Pause' : '▶ Play'; }

function loadScenario(i){
  S = D.scenarios[i]; reset(); simT = 0; advanceTo(S.t0);
  $('scrub').max = S.t1; $('scrub').value = S.t0;
  const marks = $('marks'); marks.innerHTML = ''; const span = S.t1;
  S.rows.forEach(r => { const ev = S.events[r[1]]; if (ev === 'LINE_STOP' || ev === 'INSPECT_NOK'){ const m = document.createElement('i');
    m.style.left = (r[0] / span * 100) + '%'; m.style.background = ev === 'LINE_STOP' ? 'var(--crit)' : 'var(--accent)'; m.title = ev + ' @ ' + fmtClock(r[0]); marks.appendChild(m); } });
  draw(); buildReport(); buildDayTables();
}
function buildReport(){
  const rows = [['Stations (positions)', s => s.summary.stations], ['Shipped per day (mean of 20)', s => mean(s.reps.shipped).toFixed(1)],
    ['JPH', s => mean(s.reps.jph).toFixed(2)], ['Takt attainment', s => (100*mean(s.reps.takt_attainment)).toFixed(1) + ' %'],
    ['Balance loss', s => (100*mean(s.reps.balance_loss)).toFixed(1) + ' %'], ['Heaviest station takt load (plan)', s => pct(maxStation(s, 'load_'))], ['Heaviest station utilization (actual)', s => pct(maxStation(s, 'util_'))],
    ['Line stop per day', s => mean(s.reps.line_stop_s).toFixed(0) + ' s'], ['Torque re-hits per day', s => mean(s.reps.torque_nok).toFixed(1) + ' ± ' + sd(s.reps.torque_nok).toFixed(1)],
    ['Colour catches per day', s => mean(s.reps.colour_mismatch_detected).toFixed(2)]];
  $('kpiTable').innerHTML = '<tr><th>KPI (20 simulated days)</th>' + D.scenarios.map(s => `<th><i class="sw" style="background:${D.series[s.name]}"></i>${s.name}</th>`).join('') + '</tr>' +
    rows.map(([k, f]) => '<tr><td>' + k + '</td>' + D.scenarios.map(s => '<td>' + f(s) + '</td>').join('') + '</tr>').join('');
}
const mean = a => a.reduce((x, y) => x + y, 0) / a.length;
const pct = v => (100 * v).toFixed(0) + ' %';
function maxStation(s, prefix){ return Math.max(...s.stations.map(x => mean(s.reps[prefix + x.id]))); }
function buildDayTables(){
  const r = S.reps, n = r.day.length;
  $('dayTitle').textContent = `Per simulated day · ${S.name} (${n} days, seeds ${r.seed[0]}–${r.seed[n-1]})`;
  const cols = [['Day', i => r.day[i]], ['Seed', i => r.seed[i]], ['Shipped', i => r.shipped[i]], ['JPH', i => r.jph[i].toFixed(2)],
    ['Takt attainment', i => pct(r.takt_attainment[i])], ['Line stop (s)', i => Math.round(r.line_stop_s[i])], ['Balance loss', i => pct(r.balance_loss[i])],
    ['Torque re-hits', i => r.torque_nok[i]], ['Colour catches', i => r.colour_mismatch_detected[i]], ['Repairs', i => r.repairs[i]], ['Heaviest station', i => r.bottleneck[i]]];
  const stat = (key, f) => { const v = r[key]; return v ? f(v) : ''; };
  const foot = [['Mean', a => mean(a)], ['Min', a => Math.min(...a)], ['Max', a => Math.max(...a)]];
  const keyOf = {'Shipped':'shipped','JPH':'jph','Takt attainment':'takt_attainment','Line stop (s)':'line_stop_s','Balance loss':'balance_loss','Torque re-hits':'torque_nok','Colour catches':'colour_mismatch_detected','Repairs':'repairs'};
  const fmt = {'JPH': v => v.toFixed(2), 'Takt attainment': pct, 'Balance loss': pct, 'Line stop (s)': v => Math.round(v), 'Shipped': v => v.toFixed(1), 'Torque re-hits': v => v.toFixed(1), 'Colour catches': v => v.toFixed(2), 'Repairs': v => v.toFixed(2)};
  $('dayTable').innerHTML = '<thead><tr>' + cols.map(c => `<th>${c[0]}</th>`).join('') + '</tr></thead><tbody>' +
    r.day.map((_, i) => '<tr>' + cols.map(c => `<td>${c[1](i)}</td>`).join('') + '</tr>').join('') + '</tbody><tfoot>' +
    foot.map(([lab, f]) => '<tr>' + cols.map((c, j) => j === 0 ? `<td>${lab}</td>` : (keyOf[c[0]] ? `<td>${(fmt[c[0]] || (v => v))(f(r[keyOf[c[0]]]))}</td>` : '<td></td>')).join('') + '</tr>').join('') + '</tfoot>';
  const sel = $('stFilter'), keep = sel.value;
  sel.innerHTML = '<option value="">all</option>' + S.stations.map(x => `<option${x.id === keep ? ' selected' : ''}>${x.id}</option>`).join('');
  const st = S.stations.map(x => x.id).filter(id => !sel.value || id === sel.value);
  $('stationTable').innerHTML = '<thead><tr><th>Day</th>' + st.map(id => `<th>${id}<br><span style="font-weight:400">load · util</span></th>`).join('') + '</tr></thead><tbody>' +
    r.day.map((d, i) => '<tr><td>' + d + '</td>' + st.map(id => { const L = r['load_' + id][i], U = r['util_' + id][i];
      return `<td><span class="${L > 1 ? 'over' : ''}">${pct(L)}${L > 1 ? ' over takt' : ''}</span> · ${pct(U)}</td>`; }).join('') + '</tr>').join('') + '</tbody>';
}
function tableCSV(id){
  const rows = [...$(id).querySelectorAll('tr')].map(tr => [...tr.children].map(c => '"' + c.textContent.replace(/"/g, '""').trim() + '"').join(','));
  const a = document.createElement('a'); a.href = URL.createObjectURL(new Blob([rows.join('\n')], {type:'text/csv'}));
  a.download = `${S.name}_${id}.csv`; a.click(); URL.revokeObjectURL(a.href);
}
document.querySelectorAll('[data-csv]').forEach(b => b.onclick = () => tableCSV(b.dataset.csv));
const sd = a => { const m = mean(a); return Math.sqrt(a.reduce((x, y) => x + (y - m) ** 2, 0) / Math.max(1, a.length - 1)); };
let figsDrawn = false;
function showTab(rep){ $('live').classList.toggle('hidden', rep); $('report').classList.toggle('hidden', !rep); $('tabLive').classList.toggle('on', !rep); $('tabReport').classList.toggle('on', rep);
  if (rep && !figsDrawn){ figsDrawn = true; D.figures.forEach(f => { const d = document.createElement('div'); d.className = 'panel'; $('figs').appendChild(d);
    Plotly.newPlot(d, f.data, f.layout, {displaylogo:false, responsive:true, modeBarButtonsToRemove:['lasso2d','select2d']}); }); } }

D.scenarios.forEach((s, i) => { const o = document.createElement('option'); o.value = i; o.textContent = `${s.name} (${s.stations.length} positions)`; $('scen').appendChild(o); });
$('colourKey').innerHTML = Object.entries(D.frameColours).map(([k, c]) => `<span style="margin-right:10px"><i class="sw" style="background:${c}"></i>${k}</span>`).join('');
$('scen').onchange = e => { togglePlay(false); loadScenario(Number(e.target.value)); };
$('play').onclick = () => togglePlay();
let scrubTo = null;                              // scrubbing: remember the target, apply it once per animation frame
$('scrub').oninput = e => { scrubTo = Number(e.target.value); const r = e.target, f = (scrubTo - r.min) / (r.max - r.min || 1);
  $('tip').textContent = scrubTo >= S.t0 ? fmtClock(scrubTo) : 'warm-up'; $('tip').style.left = (f * r.offsetWidth) + 'px'; $('tip').classList.remove('hidden'); };
$('scrub').onchange = () => $('tip').classList.add('hidden');
$('stFilter').onchange = () => buildDayTables();
$('tabLive').onclick = () => showTab(false); $('tabReport').onclick = () => showTab(true);
document.addEventListener('keydown', e => { if (e.code === 'Space' && e.target.tagName !== 'SELECT'){ e.preventDefault(); togglePlay(); } });
loadScenario(0); requestAnimationFrame(loop);
</script></body></html>
"""
