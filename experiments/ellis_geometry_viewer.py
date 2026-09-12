#!/usr/bin/env python3
"""Render a verified Ellis toy-geometry receipt as a standalone local HTML observer.

The observer is a lossy presentation of an already-produced experiment receipt.
It does not recompute geometry, promote claims, or alter experiment state. When
an input is supplied, the underlying experiment verifier is invoked before any
HTML is written.
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from pathlib import Path
from typing import Any

from ellis_wormhole import ContractError, RECEIPT_SCHEMA, verify_receipt

VIEWER_SCHEMA = "axm.matter-transfer.ellis-geometry-viewer/v1"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot read valid JSON from {path}: {exc}") from exc


def _require_receipt_shape(receipt: Any) -> dict[str, Any]:
    if not isinstance(receipt, dict) or receipt.get("schema") != RECEIPT_SCHEMA:
        raise ContractError(f"receipt schema must be {RECEIPT_SCHEMA}")
    if receipt.get("status") not in {"PASS", "HOLD"}:
        raise ContractError("receipt status must be PASS or HOLD")
    if not isinstance(receipt.get("claim_ceiling"), str) or not receipt["claim_ceiling"]:
        raise ContractError("receipt claim_ceiling must be present")
    if not isinstance(receipt.get("receipt_sha256"), str) or len(receipt["receipt_sha256"]) != 64:
        raise ContractError("receipt_sha256 must be present")
    results = receipt.get("results")
    if not isinstance(results, dict):
        raise ContractError("receipt results must be an object")
    samples = results.get("samples")
    if not isinstance(samples, list) or not samples:
        raise ContractError("receipt results.samples must be a non-empty array")
    required_sample_fields = {
        "l",
        "areal_radius",
        "shape_ratio_b_over_r",
        "embedding_height_over_a",
        "scaled_radial_nec_8pi_a2_rho_plus_pr",
    }
    for index, sample in enumerate(samples):
        if not isinstance(sample, dict) or not required_sample_fields.issubset(sample):
            raise ContractError(f"receipt sample {index} is missing viewer fields")
        for field in required_sample_fields:
            value = sample[field]
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise ContractError(f"receipt sample {index}.{field} must be numeric")
    gates = receipt.get("gates")
    if not isinstance(gates, list) or not gates:
        raise ContractError("receipt gates must be a non-empty array")
    truth = receipt.get("truth_boundary")
    if not isinstance(truth, dict):
        raise ContractError("receipt truth_boundary must be an object")
    return receipt


def render_html(receipt: Any) -> str:
    receipt = _require_receipt_shape(receipt)
    payload = json.dumps(receipt, sort_keys=True, separators=(",", ":")).replace("</", "<\\/")
    status = html.escape(receipt["status"])
    digest = html.escape(receipt["receipt_sha256"])
    ceiling = html.escape(receipt["claim_ceiling"])
    gate_pass = sum(1 for gate in receipt["gates"] if gate.get("status") == "PASS")
    gate_total = len(receipt["gates"])
    return f'''<!doctype html>
<html lang="en" data-viewer-schema="{VIEWER_SCHEMA}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="dark">
<title>AXM Matter Transfer · Ellis Geometry Observer</title>
<style>
:root{{font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#05070b;color:#eef5ff;--panel:#0b1018;--line:#23344a;--text2:#98aabd;--bright:#eaf7ff;--accent:#7be7ff;--warn:#ffd37b;--bad:#ff8b8b}}
*{{box-sizing:border-box}} body{{margin:0;min-height:100vh;background:radial-gradient(circle at 50% 0%,#102031 0,#070b11 34rem,#05070b 70rem);}}
button{{font:inherit}} .shell{{width:min(1180px,100%);margin:0 auto;padding:24px}} .truth{{border:1px solid #41637d;background:#0b151f;padding:12px 14px;display:flex;gap:12px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}}
.eyebrow,.micro{{text-transform:uppercase;letter-spacing:.16em;font-size:.72rem;font-weight:800;color:var(--accent)}} .truth strong{{display:block;font-size:.92rem;max-width:760px}} .truth small{{color:var(--text2)}}
.hero{{display:grid;grid-template-columns:1.5fr .8fr;gap:18px;margin:18px 0}} .card{{border:1px solid var(--line);background:linear-gradient(180deg,rgba(15,23,34,.94),rgba(7,11,17,.96));box-shadow:0 18px 60px rgba(0,0,0,.25)}} .hero-main{{padding:22px}} h1{{font-size:clamp(2rem,6vw,4.7rem);line-height:.92;margin:.35rem 0 1rem;letter-spacing:-.055em}} .lede{{max-width:62ch;color:#b8c8d8;line-height:1.55}}
.receipt{{padding:18px;display:grid;gap:14px}} .metric{{padding-top:12px;border-top:1px solid var(--line)}} .metric:first-child{{border-top:0;padding-top:0}} .metric b{{display:block;margin-top:3px;font-size:1.35rem}} .hash{{word-break:break-all;color:var(--text2);font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.72rem}}
.stage{{display:grid;grid-template-columns:1.6fr .8fr;gap:18px;align-items:stretch}} .plot-card{{padding:14px;min-height:470px;position:relative;overflow:hidden}} .plot-head{{display:flex;align-items:end;justify-content:space-between;gap:16px;margin-bottom:8px}} .plot-head h2{{margin:4px 0 0;font-size:1.2rem}} .legend{{color:var(--text2);font-size:.8rem;text-align:right}}
svg{{width:100%;height:380px;display:block}} .axis{{stroke:#42566d;stroke-width:1}} .guide{{stroke:#1a2b3d;stroke-width:1}} .geometry-line{{fill:none;stroke:var(--accent);stroke-width:3;stroke-linejoin:round;stroke-linecap:round}} .nec-line{{fill:none;stroke:var(--warn);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}} .point{{fill:#08121a;stroke:var(--accent);stroke-width:2;cursor:pointer}} .point[aria-current="true"]{{fill:var(--accent);stroke:#fff;stroke-width:2.5}} .nec-point{{fill:#17120a;stroke:var(--warn)}} .nec-point[aria-current="true"]{{fill:var(--warn);stroke:#fff}} .label{{fill:#8097ae;font-size:11px}} .throat{{stroke:#7be7ff55;stroke-dasharray:4 5}}
.inspector{{padding:18px;display:flex;flex-direction:column;gap:15px}} .sample-index{{display:flex;justify-content:space-between;align-items:center;gap:12px}} .nav{{display:flex;gap:8px}} .nav button,.sample-chip{{border:1px solid #38506a;background:#0a121b;color:var(--bright);padding:9px 11px;cursor:pointer}} .nav button:hover,.nav button:focus-visible,.sample-chip:hover,.sample-chip:focus-visible{{outline:2px solid var(--accent);outline-offset:2px}} .sample-chip[aria-current="true"]{{background:#173143;border-color:var(--accent)}}
.readout{{display:grid;grid-template-columns:1fr 1fr;gap:8px}} .readout div{{border-top:1px solid var(--line);padding:10px 0}} .readout span{{display:block;color:var(--text2);font-size:.75rem}} .readout b{{font-size:1.02rem}} .meaning{{padding:12px;border:1px solid #5b4725;background:#18130b;color:#ffe0a6;line-height:1.45}} .meaning strong{{display:block;color:#fff2cf}}
.samples{{display:flex;flex-wrap:wrap;gap:7px}} .boundary{{margin-top:18px;padding:18px}} .boundary-grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:12px}} .boundary-item{{border:1px solid var(--line);padding:12px;min-height:92px}} .boundary-item b{{display:block;margin-bottom:5px}} .yes{{color:#8ff1c5}} .no{{color:#f3c98b}} .foot{{color:var(--text2);font-size:.79rem;line-height:1.5;margin-top:14px}}
.sr-only{{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}}
@media(max-width:820px){{.hero,.stage{{grid-template-columns:1fr}} .boundary-grid{{grid-template-columns:1fr 1fr}} .plot-card{{min-height:390px}} svg{{height:300px}}}}
@media(max-width:460px){{.shell{{padding:12px}} .hero-main,.receipt,.inspector,.boundary{{padding:14px}} .boundary-grid{{grid-template-columns:1fr}} .readout{{grid-template-columns:1fr}} .plot-card{{min-height:350px}} svg{{height:270px}} h1{{font-size:2.55rem}}}}
@media(prefers-reduced-motion:reduce){{*{{scroll-behavior:auto!important;transition:none!important;animation:none!important}}}}
@media(prefers-contrast:more){{:root{{--line:#6f8daa;--text2:#d4e2ef}} .card,.truth{{border-width:2px}}}}
</style>
</head>
<body>
<main class="shell">
<section class="truth" aria-label="Truth boundary">
<div><span class="eyebrow">MODEL REPRODUCTION ONLY</span><strong>No physical macroscopic matter-transfer mechanism is established.</strong></div>
<small>DISPLAY ≠ PROOF · receipt-derived projection · no network · no model execution in this page</small>
</section>
<section class="hero">
<div class="card hero-main"><span class="eyebrow">ELLIS ZERO-MASS WORMHOLE · TOY GEOMETRY</span><h1>See the receipt.<br>Not a promise.</h1><p class="lede">This observer turns one independently verified computational receipt into a human-readable geometry and stress-energy view. It adds no samples and changes no experiment result. Lines between recorded sample points are visual guides only.</p></div>
<aside class="card receipt" aria-label="Receipt status"><div class="metric"><span class="micro">RECEIPT</span><b>{status}</b></div><div class="metric"><span class="micro">GATES</span><b>{gate_pass} / {gate_total} PASS</b></div><div class="metric"><span class="micro">CLAIM CEILING</span><div class="hash">{ceiling}</div></div><div class="metric"><span class="micro">RECEIPT SHA-256</span><div class="hash">{digest}</div></div></aside>
</section>
<section class="stage">
<div class="card plot-card"><div class="plot-head"><div><span class="micro">RECORDED SAMPLE MAP</span><h2>Areal radius + radial NEC</h2></div><div class="legend">cyan = areal radius<br>amber = scaled radial NEC</div></div><svg id="plot" role="img" aria-labelledby="plot-title plot-desc" viewBox="0 0 760 380"><title id="plot-title">Ellis toy geometry sample map</title><desc id="plot-desc">Recorded receipt samples across proper radial coordinate l. Select a point to inspect its exact receipt values.</desc></svg><p class="foot">The chart connects only the receipt's recorded samples for orientation. It does not claim unsampled values or physical realizability.</p></div>
<aside class="card inspector"><div class="sample-index"><div><span class="micro">SELECTED RECEIPT SAMPLE</span><h2 id="sample-heading" style="margin:.25rem 0 0">—</h2></div><div class="nav"><button id="prev" type="button" aria-label="Previous sample">←</button><button id="next" type="button" aria-label="Next sample">→</button></div></div><div id="readout" class="readout"></div><div id="meaning" class="meaning"></div><div><span class="micro">JUMP TO SAMPLE</span><div id="samples" class="samples" style="margin-top:8px"></div></div><div id="announce" class="sr-only" aria-live="polite"></div></aside>
</section>
<section class="card boundary"><span class="micro">WHAT THIS RECEIPT DOES / DOES NOT ESTABLISH</span><div id="boundary" class="boundary-grid"></div><p class="foot">Source lineage, metric contract, numerical checks and full machine-readable gates remain in the receipt. This view is intentionally subordinate to that evidence.</p></section>
</main>
<script id="receipt-data" type="application/json">{payload}</script>
<script>
(()=>{{
  'use strict';
  const receipt=JSON.parse(document.getElementById('receipt-data').textContent);
  const samples=receipt.results.samples;
  const svg=document.getElementById('plot');
  const ns='http://www.w3.org/2000/svg';
  let selected=Math.max(0,samples.findIndex(s=>Number(s.l)===0));
  const finite=n=>Number.isFinite(Number(n));
  const fmt=n=>{{const v=Number(n);return Math.abs(v)>=1000?String(v):Number(v.toFixed(6)).toString();}};
  const extent=(values,pad=.08)=>{{let lo=Math.min(...values),hi=Math.max(...values);if(lo===hi){{lo-=1;hi+=1}}const d=hi-lo;return [lo-d*pad,hi+d*pad]}};
  const xs=samples.map(s=>Number(s.l)), rs=samples.map(s=>Number(s.areal_radius)), necs=samples.map(s=>Number(s.scaled_radial_nec_8pi_a2_rho_plus_pr));
  if(![...xs,...rs,...necs].every(finite)) throw new Error('viewer receipt contains non-finite plotting data');
  const [xmin,xmax]=extent(xs,.03), [rmin,rmax]=extent(rs,.15), [nmin,nmax]=extent(necs,.16);
  const x=v=>70+(Number(v)-xmin)/(xmax-xmin)*640;
  const yR=v=>42+(rmax-Number(v))/(rmax-rmin)*142;
  const yN=v=>224+(nmax-Number(v))/(nmax-nmin)*105;
  function el(name,attrs={{}}){{const node=document.createElementNS(ns,name);for(const [k,v] of Object.entries(attrs))node.setAttribute(k,String(v));return node}}
  function line(x1,y1,x2,y2,cls){{svg.append(el('line',{{x1,y1,x2,y2,class:cls}}))}}
  line(70,186,710,186,'axis'); line(70,340,710,340,'axis'); line(70,34,70,306,'axis'); line(x(0),30,x(0),340,'throat');
  for(const tick of xs){{line(x(tick),34,x(tick),340,'guide');const t=el('text',{{x:x(tick),y:363,class:'label','text-anchor':'middle'}});t.textContent=`l=${{fmt(tick)}}`;svg.append(t)}}
  const geo=el('polyline',{{class:'geometry-line',points:samples.map(s=>`${{x(s.l)}},${{yR(s.areal_radius)}}`).join(' ')}});svg.append(geo);
  const nec=el('polyline',{{class:'nec-line',points:samples.map(s=>`${{x(s.l)}},${{yN(s.scaled_radial_nec_8pi_a2_rho_plus_pr)}}`).join(' ')}});svg.append(nec);
  samples.forEach((s,i)=>{{
    const gp=el('circle',{{cx:x(s.l),cy:yR(s.areal_radius),r:7,class:'point',tabindex:'0',role:'button','aria-label':`Inspect sample l=${{fmt(s.l)}}`}});
    const np=el('circle',{{cx:x(s.l),cy:yN(s.scaled_radial_nec_8pi_a2_rho_plus_pr),r:5,class:'point nec-point','aria-hidden':'true'}});
    gp.dataset.index=i;np.dataset.index=i;gp.addEventListener('click',()=>select(i));gp.addEventListener('keydown',e=>{{if(e.key==='Enter'||e.key===' '){{e.preventDefault();select(i)}}}});svg.append(gp);svg.append(np);
  }});
  const boundaryLabels={{
    computational_identity_reproduced:'Computational identities reproduced',
    stress_energy_requirement_exposed:'Stress-energy requirement exposed',
    stability_tested:'Stability tested',
    quantum_energy_inequalities_tested:'Quantum energy inequalities tested',
    physical_source_or_actuator_known:'Physical source / actuator known',
    engineering_feasibility_established:'Engineering feasibility established',
    matter_transfer_demonstrated:'Matter transfer demonstrated',
    merge_or_canon_authority:'Merge / CANON authority'
  }};
  const boundary=document.getElementById('boundary');
  Object.entries(boundaryLabels).forEach(([key,label])=>{{const value=receipt.truth_boundary[key]===true;const d=document.createElement('div');d.className='boundary-item';d.innerHTML=`<b>${{label}}</b><span class="${{value?'yes':'no'}}">${{value?'YES — receipt says true':'NO — not established'}}</span>`;boundary.append(d)}});
  const chips=document.getElementById('samples');samples.forEach((s,i)=>{{const b=document.createElement('button');b.type='button';b.className='sample-chip';b.textContent=`l ${{fmt(s.l)}}`;b.dataset.index=i;b.addEventListener('click',()=>select(i));chips.append(b)}});
  function select(index,announce=true){{
    selected=(index+samples.length)%samples.length;const s=samples[selected];
    document.getElementById('sample-heading').textContent=`l = ${{fmt(s.l)}}`;
    document.getElementById('readout').innerHTML=`<div><span>areal radius r</span><b>${{fmt(s.areal_radius)}}</b></div><div><span>shape ratio b/r</span><b>${{fmt(s.shape_ratio_b_over_r)}}</b></div><div><span>embedding height / a</span><b>${{fmt(s.embedding_height_over_a)}}</b></div><div><span>scaled radial NEC</span><b>${{fmt(s.scaled_radial_nec_8pi_a2_rho_plus_pr)}}</b></div>`;
    const nec=Number(s.scaled_radial_nec_8pi_a2_rho_plus_pr);document.getElementById('meaning').innerHTML=nec<0?`<strong>Negative radial NEC in this declared GR model.</strong>This is a requirement exposed by the toy geometry, not evidence that usable stress-energy exists.`:`<strong>Receipt value is not negative at this sample.</strong>Inspect the machine-readable gate before interpreting this point.`;
    document.querySelectorAll('.point').forEach(p=>p.setAttribute('aria-current',String(Number(p.dataset.index)===selected)));
    document.querySelectorAll('.sample-chip').forEach(p=>p.setAttribute('aria-current',String(Number(p.dataset.index)===selected)));
    if(announce)document.getElementById('announce').textContent=`Selected sample l ${{fmt(s.l)}}, areal radius ${{fmt(s.areal_radius)}}, scaled radial NEC ${{fmt(nec)}}.`;
  }}
  document.getElementById('prev').addEventListener('click',()=>select(selected-1));document.getElementById('next').addEventListener('click',()=>select(selected+1));
  document.addEventListener('keydown',e=>{{if(e.target.matches('input,textarea,select'))return;if(e.key==='ArrowLeft')select(selected-1);if(e.key==='ArrowRight')select(selected+1)}});
  select(selected,false);
  window.__AXM_VIEWER__={{schema:'{VIEWER_SCHEMA}',receiptSha:receipt.receipt_sha256,get selectedIndex(){{return selected}},select}};
}})();
</script>
</body>
</html>'''


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="experiment input used to verify the receipt")
    parser.add_argument("--receipt", type=Path, required=True, help="receipt produced by ellis_wormhole.py")
    parser.add_argument("--output", type=Path, required=True, help="new standalone HTML path; existing files are never replaced")
    args = parser.parse_args(argv)
    try:
        raw_input = _read_json(args.input)
        receipt = _read_json(args.receipt)
        verify_receipt(raw_input, receipt)
        _require_receipt_shape(receipt)
        if args.output.exists():
            raise ContractError(f"refusing to overwrite existing output: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_html(receipt), encoding="utf-8")
        print(json.dumps({"status":"PASS","viewer_schema":VIEWER_SCHEMA,"receipt_sha256":receipt["receipt_sha256"],"output":str(args.output),"display_is_authority":False},sort_keys=True,separators=(",",":")))
        return 0
    except ContractError as exc:
        print(f"HOLD: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
