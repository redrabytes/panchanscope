#!/usr/bin/python3

import sys
import json
import shutil
import argparse
import subprocess


def meta_from_info(info):
    parts = []
    loc = " ".join(x for x in [info.get("countryCode"), info.get("city")] if x)
    if loc:
        parts.append(loc)
    if info.get("as"):
        parts.append(info["as"])
    return " - ".join(parts)


def normalize(d):
    edges = []
    nodes = {}
    parent_of = {}

    if isinstance(d.get("edges"), list):
        for n in d.get("nodes", []):
            ip = n.get("ip")
            if not ip:
                continue
            raw = n.get("info", {}) or {}
            nodes[ip] = {
                "state": n.get("state", "pending"),
                "meta": meta_from_info(raw),
                "info": raw,
            }
            if n.get("parent"):
                parent_of[ip] = n["parent"]
        for e in d["edges"]:
            if e.get("from") and e.get("to"):
                edges.append((e["from"], e["to"]))
        return edges, nodes, parent_of

    graph = d.get("graph", {})
    alive = set(d.get("alive", []))
    info = d.get("nodes", {})
    parent_of = dict(d.get("parents", {}))
    contacted = set(graph)
    allips = contacted | {c for cs in graph.values() for c in cs}
    for ip in allips:
        if ip in alive:
            state = "alive"
        elif ip in contacted:
            state = "dead"
        else:
            state = "pending"
        raw = info.get(ip, {}) or {}
        nodes[ip] = {"state": state, "meta": meta_from_info(raw), "info": raw}
    for p, cs in graph.items():
        for c in cs:
            edges.append((p, c))
    return edges, nodes, parent_of


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PanchanScope</title>
<script src="https://unpkg.com/vis-network/standalone/umd/vis-network.min.js"></script>
<style>
  :root { --bg:#0b0f14; --panel:#111827; --line:#1f2937; --txt:#e5e7eb; --dim:#8a97a6;
          --alive:#7bc043; --dead:#e0564c; --pend:#f6c744; --hub:#f59e0b; }
  * { box-sizing:border-box; }
  html, body { margin:0; height:100%; background:var(--bg); color:var(--txt);
               font-family:ui-sans-serif, system-ui, sans-serif; }
  body { display:flex; flex-direction:column; }
  #bar { display:flex; align-items:center; gap:8px; height:46px; padding:0 14px;
         border-bottom:1px solid var(--line); background:var(--panel); font-size:13px; }
  #bar .title { font-weight:700; letter-spacing:.3px; margin-right:6px; }
  #bar button { background:#1f2937; color:var(--txt); border:1px solid #374151;
                border-radius:6px; padding:4px 9px; font:inherit; font-size:12px; cursor:pointer; }
  #bar button:hover { background:#374151; }
  #bar button.on { background:var(--hub); color:#0b0f14; border-color:var(--hub); }
  #net { flex:1; min-height:0; position:relative; }
  #legend { position:absolute; left:16px; bottom:16px; z-index:5;
            background:rgba(17,24,39,.85); border:1px solid var(--line);
            border-radius:10px; padding:12px 16px; font-size:14px; }
  #legend .row { display:flex; align-items:center; gap:12px; padding:3px 0; }
  #legend .ln { width:34px; height:5px; border-radius:3px; }
  #details { position:absolute; right:12px; bottom:12px; width:300px; z-index:6;
             background:rgba(17,24,39,.95); border:1px solid var(--line);
             border-radius:10px; padding:12px 14px; font-size:12px; display:none;
             font-family:ui-monospace, monospace; }
  #details .ip { font-size:14px; font-weight:700; color:#fff; margin-bottom:8px; word-break:break-all; }
  #details .r { display:flex; justify-content:space-between; gap:12px; padding:2px 0; }
  #details .k { color:var(--dim); }
  #details .v { color:var(--txt); text-align:right; word-break:break-word; }
  #details .close { position:absolute; top:8px; right:11px; color:var(--dim); cursor:pointer; font-size:14px; }
</style>
</head>
<body>
<div id="bar">
  <span class="title">PanchanScope</span>
  <button id="btn-layout">layout: organic</button>
  <button id="btn-core" class="on">core</button>
  <button id="btn-labels" class="on">labels</button>
  <button id="btn-full">full links</button>
  <button id="btn-dead">hide dead</button>
  <button id="btn-fit">fit</button>
  <button id="btn-png">export png</button>
</div>
<div id="net">
  <div id="legend">
    <div class="row"><span class="ln" style="background:#7bc043"></span>link to alive node</div>
    <div class="row"><span class="ln" style="background:#f6c744"></span>link to pending node</div>
    <div class="row"><span class="ln" style="background:#e0564c"></span>link to dead node</div>
    <div class="row"><span class="ln" style="background:transparent; border:2px solid #f59e0b; width:14px; height:14px; border-radius:3px"></span>hub (controls others)</div>
  </div>
  <div id="details"></div>
</div>
<script>
  const DATA = __DATA__;
  const hubMin = __HUBMIN__;
  const ICONS = __ICONS__;
  const providers = ['amazon','aws','google','cloudflare','facebook','meta','akamai',
                     'microsoft','azure','digitalocean','digital ocean','ovh','oracle',
                     'alibaba','fastly','netflix','apple','tencent','linode','hetzner'];
  const ring = { alive:'#7bc043', dead:'#e0564c', pending:'#f6c744' };
  const edgeCol = { alive:'#7bc043', dead:'#e0564c', pending:'#f6c744' };

  const stateOf = {}, metaOf = {}, infoOf = {}, outdeg = {}, kidsOf = {}, inOf = {}, parentOf = {};
  const nodes = new vis.DataSet();
  const edges = new vis.DataSet();
  const CORE = '__core__';
  let hideDead = false, coreOn = true, labelsAll = true, fullOn = false, layered = false, focusId = null;

  function isHub(id){ return (outdeg[id] || 0) >= hubMin; }
  function sizeFor(id){ return 24 + Math.min((outdeg[id] || 0) * 2, 30); }
  function shortMeta(id){
    const d = infoOf[id] || {};
    const asn = (d.as || '').split(' ')[0] || '';
    return [d.countryCode || '', asn].filter(Boolean).join(' ');
  }
  function isProvider(id){
    const d = infoOf[id] || {};
    const s = ((d.asname || '') + ' ' + (d.org || '') + ' ' + (d.as || '')).toLowerCase();
    return providers.some(p => s.includes(p));
  }
  function iconKey(id){ return isHub(id) ? 'hub' : (stateOf[id] || 'pending'); }
  function iconFor(id){ return (isProvider(id) ? ICONS.cloud : ICONS.router)[iconKey(id)]; }
  function labelFor(id){
    if(id === CORE) return 'core';
    if(!labelsAll && !isHub(id)) return '';
    const m = shortMeta(id);
    return m ? id + '\\n' + m : id;
  }

  DATA.edges.forEach(e => {
    outdeg[e.from] = (outdeg[e.from] || 0) + 1;
    (kidsOf[e.from] || (kidsOf[e.from] = new Set())).add(e.to);
    (inOf[e.to] || (inOf[e.to] = new Set())).add(e.from);
  });
  DATA.nodes.forEach(n => { stateOf[n.ip] = n.state; metaOf[n.ip] = n.meta || '';
    infoOf[n.ip] = n.info || {}; if(n.parent) parentOf[n.ip] = n.parent; });

  const allIds = new Set(DATA.nodes.map(n => n.ip));
  DATA.edges.forEach(e => { allIds.add(e.from); allIds.add(e.to); });
  allIds.forEach(id => nodes.add({ id, shape:'image', image:iconFor(id),
    label:labelFor(id), title:metaOf[id] || id, size:sizeFor(id) }));

  function edgeStyle(from, to){
    return { color:{ color:edgeCol[stateOf[to] || 'pending'] || edgeCol.pending, opacity:0.9 },
             width:2 + Math.min((outdeg[from] || 0) * 0.35, 4) };
  }
  const treeIds = new Set();
  allIds.forEach(id => { if(parentOf[id] && allIds.has(parentOf[id])) treeIds.add(parentOf[id] + '->' + id); });
  if(treeIds.size === 0) DATA.edges.forEach(e => treeIds.add(e.from + '->' + e.to));
  DATA.edges.forEach(e => { const id = e.from + '->' + e.to;
    if(treeIds.has(id) && !edges.get(id)){ const s = edgeStyle(e.from, e.to);
      edges.add({ id, from:e.from, to:e.to, color:s.color, width:s.width }); } });
  const extraEdges = DATA.edges.filter(e => !treeIds.has(e.from + '->' + e.to)).map(e => {
    const s = edgeStyle(e.from, e.to);
    return { id:e.from + '->' + e.to, from:e.from, to:e.to,
             color:{ color:s.color.color, opacity:0.4 }, width:1.4, dashes:true }; });

  function treeRoots(){ const r = []; allIds.forEach(id => { if(!parentOf[id]) r.push(id); }); return r; }
  function addCore(){
    if(!nodes.get(CORE)) nodes.add({ id:CORE, label:'core', shape:'star', size:30,
      color:{ background:'#f59e0b', border:'#f59e0b' }, font:{ color:'#0b0f14', size:14, strokeWidth:0 } });
    treeRoots().forEach(r => { const id = CORE + '->' + r;
      if(!edges.get(id)) edges.add({ id, from:CORE, to:r, color:{ color:'#f59e0b', opacity:0.8 }, width:2, dashes:true }); });
  }
  function removeCore(){ const rm = []; edges.forEach(e => { if(e.from === CORE) rm.push(e.id); }); edges.remove(rm); nodes.remove(CORE); }
  if(coreOn) addCore();

  const physicsOpts = { enabled:true, stabilization:{ iterations:250 },
    barnesHut:{ gravitationalConstant:-30000, centralGravity:0.1, springLength:170,
                springConstant:0.04, damping:0.5, avoidOverlap:0.6 } };
  const options = {
    layout: { hierarchical:false },
    physics: physicsOpts,
    nodes: { font:{ color:'#e5e7eb', size:13, face:'ui-monospace, monospace',
                    strokeWidth:4, strokeColor:'#0b0f14', vadjust:2 } },
    edges: { smooth:{ type:'continuous' }, arrows:{ to:{ enabled:true, scaleFactor:0.4 } } },
    interaction: { hover:true, tooltipDelay:120 }
  };
  const network = new vis.Network(document.getElementById('net'), { nodes, edges }, options);
  network.once('stabilizationIterationsDone', () => network.fit({ animation:false }));

  function applyLayout(){
    if(layered) network.setOptions({ layout:{ hierarchical:{ enabled:true, direction:'UD',
      sortMethod:'directed', levelSeparation:190, nodeSpacing:130, treeSpacing:230 } }, physics:false });
    else network.setOptions({ layout:{ hierarchical:{ enabled:false } }, physics:physicsOpts });
    network.once('afterDrawing', () => network.fit({ animation:false }));
  }

  const details = document.getElementById('details');
  function renderDetails(id){
    const d = infoOf[id] || {}, st = stateOf[id] || 'pending', ctrl = outdeg[id] || 0;
    const rows = [];
    const esc = (s) => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    const add = (k, v) => { if(v || v === 0) rows.push(
      `<div class="r"><span class="k">${esc(k)}</span><span class="v">${esc(v)}</span></div>`); };
    add('status', st + (isHub(id) ? ' - hub' : ''));
    add('controls', ctrl + (ctrl === 1 ? ' node' : ' nodes'));
    add('announced by', parentOf[id] || '(seed)');
    const loc = [d.city, d.country].filter(Boolean).join(', ');
    if(loc) add('location', loc);
    if(d.lat != null && d.lon != null) add('coords', d.lat + ', ' + d.lon);
    add('isp', d.isp); add('org', d.org); add('as', d.as); add('asname', d.asname);
    details.innerHTML = '<span class="close">\\u00d7</span><div class="ip">' + esc(id) + '</div>' + rows.join('');
    details.querySelector('.close').onclick = () => { setFocus(null); details.style.display = 'none'; };
    details.style.display = 'block';
  }

  function baseEdgeColor(e){
    if(e.from === CORE) return { color:'#f59e0b', opacity:0.8 };
    const c = edgeCol[stateOf[e.to] || 'pending'] || edgeCol.pending;
    return { color:c, opacity:treeIds.has(e.id) ? 0.9 : 0.4 };
  }
  function nodeReset(id){
    if(id === CORE) return null;
    return { id, opacity:1, label:labelFor(id) };
  }
  function setFocus(id){
    focusId = id;
    if(id === null){
      nodes.update(nodes.map(n => nodeReset(n.id)).filter(Boolean));
      edges.update(edges.map(e => ({ id:e.id, color:baseEdgeColor(e) })));
      return;
    }
    const keep = new Set([id]);
    (kidsOf[id] || []).forEach(x => keep.add(x));
    (inOf[id] || []).forEach(x => keep.add(x));
    nodes.update(nodes.map(n => {
      if(n.id === CORE) return null;
      if(keep.has(n.id)) return { id:n.id, opacity:1,
        label:(shortMeta(n.id) ? n.id + '\\n' + shortMeta(n.id) : n.id) };
      return { id:n.id, opacity:0.15 };
    }).filter(Boolean));
    edges.update(edges.map(e => ({ id:e.id,
      color:(keep.has(e.from) && keep.has(e.to)) ? { color:'#e5e7eb', opacity:1 } : { color:'#1a222c', opacity:0.25 } })));
  }
  network.on('click', (p) => {
    if(p.nodes.length){ const id = p.nodes[0]; if(id === CORE) return; setFocus(id); renderDetails(id); }
    else { setFocus(null); details.style.display = 'none'; }
  });

  function applyHideDead(){
    const upd = []; nodes.forEach(n => { if(stateOf[n.id] === 'dead') upd.push({ id:n.id, hidden:hideDead }); });
    nodes.update(upd);
  }

  document.getElementById('btn-layout').onclick = (ev) => {
    layered = !layered; ev.target.textContent = 'layout: ' + (layered ? 'layered' : 'organic'); applyLayout();
  };
  document.getElementById('btn-core').onclick = (ev) => {
    coreOn = !coreOn; ev.target.classList.toggle('on', coreOn);
    if(coreOn) addCore(); else removeCore();
    if(layered) applyLayout();
  };
  document.getElementById('btn-labels').onclick = (ev) => {
    labelsAll = !labelsAll; ev.target.classList.toggle('on', labelsAll);
    nodes.update(nodes.map(n => ({ id:n.id, label:labelFor(n.id) })));
  };
  document.getElementById('btn-full').onclick = (ev) => {
    fullOn = !fullOn; ev.target.classList.toggle('on', fullOn);
    if(fullOn) edges.add(extraEdges.filter(e => !edges.get(e.id)));
    else edges.remove(extraEdges.map(e => e.id));
    if(layered) applyLayout();
  };
  document.getElementById('btn-dead').onclick = (ev) => {
    hideDead = !hideDead; ev.target.classList.toggle('on', hideDead); applyHideDead();
  };
  document.getElementById('btn-fit').onclick = () => network.fit({ animation:true });
  document.getElementById('btn-png').onclick = () => {
    const c = document.querySelector('#net canvas'); if(!c) return;
    const a = document.createElement('a'); a.href = c.toDataURL('image/png');
    a.download = 'panchanscope.png'; a.click();
  };
</script>
</body>
</html>
"""


import urllib.parse

_ROUTER_GLYPH = (
    "<rect x='14' y='28' width='36' height='14' rx='2' fill='#0f151c' stroke='#cbd5e1' stroke-width='2'/>"
    "<rect x='18' y='37' width='5' height='3' fill='#cbd5e1'/>"
    "<rect x='26' y='37' width='5' height='3' fill='#cbd5e1'/>"
    "<rect x='34' y='37' width='5' height='3' fill='#cbd5e1'/>"
    "<rect x='42' y='37' width='4' height='3' fill='#cbd5e1'/>"
    "<path d='M26 28 L31 20 M38 28 L33 20' stroke='#cbd5e1' stroke-width='2' fill='none'/>"
)
_CLOUD_GLYPH = (
    "<path d='M22 43 a9 9 0 0 1 1 -18 a12 12 0 0 1 23 3 a8 8 0 0 1 -2 15 z' fill='#7cc4ff'/>"
)
_ICON_COLORS = {"alive": "#7bc043", "pending": "#f6c744", "dead": "#e0564c", "hub": "#f59e0b"}


def _icon(glyph, color, width):
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'>"
        f"<rect x='3' y='3' width='58' height='58' rx='9' fill='#141b24' "
        f"stroke='{color}' stroke-width='{width}'/>" + glyph + "</svg>"
    )
    return "data:image/svg+xml," + urllib.parse.quote(svg)


def _icon_set():
    out = {"router": {}, "cloud": {}}
    for key, col in _ICON_COLORS.items():
        w = 6 if key == "hub" else 4
        out["router"][key] = _icon(_ROUTER_GLYPH, col, w)
        out["cloud"][key] = _icon(_CLOUD_GLYPH, col, w)
    return out


ICONS = _icon_set()


def build_html(edges, nodes, parent_of=None, hub_min=3):
    parent_of = parent_of or {}
    allips = set(nodes) | {x for e in edges for x in e}
    out_nodes = []
    for ip in sorted(allips):
        meta = nodes.get(ip, {})
        out_nodes.append({
            "ip": ip,
            "state": meta.get("state", "pending"),
            "meta": meta.get("meta", ""),
            "info": meta.get("info", {}),
            "parent": parent_of.get(ip),
        })
    data = {"nodes": out_nodes, "edges": [{"from": a, "to": b} for a, b in edges]}
    return (HTML_TEMPLATE
            .replace("__ICONS__", json.dumps(ICONS))
            .replace("__DATA__", json.dumps(data, ensure_ascii=False))
            .replace("__HUBMIN__", str(hub_min)))


def to_dot(edges, nodes, hub_min=3, central=True):
    outdeg = {}
    for a, _ in edges:
        outdeg[a] = outdeg.get(a, 0) + 1

    allips = set(nodes) | {x for e in edges for x in e}
    children = {b for _, b in edges}
    roots = sorted(ip for ip in allips if ip not in children)

    statecol = {"alive": "#22c55e", "dead": "#ef4444", "pending": "#6b7280"}
    lines = ["digraph panchan {"]
    if central:
        lines += ['  layout=twopi;', '  root="__core__";', '  ranksep=2.4;', '  overlap=false;']
    else:
        lines += ['  rankdir=lr;']
    lines += [
        '  bgcolor="#0b0f14";',
        '  node [shape=box, style="rounded,filled", fontname=monospace,'
        ' fillcolor="#111827", fontcolor="#e5e7eb"];',
        '  edge [color="#4b5563", arrowsize=0.7];',
    ]

    if central:
        lines.append('  "__core__" [label="panchan", shape=doublecircle,'
                     ' style=filled, fillcolor="#f59e0b", fontcolor="#0b0f14",'
                     ' color="#f59e0b", penwidth=2];')

    for ip in sorted(allips):
        meta = nodes.get(ip, {})
        state = meta.get("state", "pending")
        col = statecol.get(state, statecol["pending"])
        hub = outdeg.get(ip, 0) >= hub_min
        border = "#f59e0b" if hub else col
        label = ip
        if meta.get("meta"):
            label += "\\n" + meta["meta"]
        label = label.replace('"', "'")
        pen = 3 if hub else 1
        lines.append(
            f'  "{ip}" [label="{label}", color="{border}", '
            f'fontcolor="{col}", penwidth={pen}];'
        )

    if central:
        for r in roots:
            lines.append(f'  "__core__" -> "{r}" [color="#f59e0b", style=dashed];')
    for a, b in edges:
        lines.append(f'  "{a}" -> "{b}";')
    lines.append("}")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="build a graphviz schema from a panchan json export"
    )
    parser.add_argument("input", help="json file (browser export or -j dump)")
    parser.add_argument("-o", "--output", default="schema.html",
                        help="output file (.html / .png / .svg / .pdf / .dot, default: schema.html)")
    parser.add_argument("--hub-min", type=int, default=3,
                        help="out-degree to flag a node as a hub (default: 3)")
    parser.add_argument("--no-central", action="store_true",
                        help="disable the central node + radial layout (dot/graphviz output)")
    args = parser.parse_args()

    with open(args.input, encoding="utf-8") as f:
        data = json.load(f)

    central = not args.no_central
    edges, nodes, parent_of = normalize(data)
    ext = args.output.rsplit(".", 1)[-1].lower()

    if ext == "html":
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(build_html(edges, nodes, parent_of, hub_min=args.hub_min))
        print(f"interactive schema written to {args.output} (open it in a browser)")
        return

    dot = to_dot(edges, nodes, hub_min=args.hub_min, central=central)

    if ext in ("png", "svg", "pdf"):
        if shutil.which("dot"):
            subprocess.run(["dot", f"-T{ext}", "-o", args.output],
                           input=dot.encode(), check=True)
            print(f"schema written to {args.output}")
        else:
            html_path = args.output.rsplit(".", 1)[0] + ".html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(build_html(edges, nodes, parent_of, hub_min=args.hub_min))
            print(f"graphviz 'dot' not found - wrote an interactive page instead: {html_path}")
            print("open it in a browser; you can export a png from there with the 'export png' button")
    else:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(dot)
        print(f"dot written to {args.output}")


if __name__ == "__main__":
    main()
