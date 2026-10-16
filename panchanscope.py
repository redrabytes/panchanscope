#!/usr/bin/python3

import re
import sys
import json
import time
import socket
import argparse
import ipaddress
import threading
import urllib.request
import queue
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from loguru import logger

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

logger.remove()
logger.add(
    sys.stderr,
    format="<cyan>{time:YYYY-MM-DD HH:mm:ss.SSS}</cyan> | <level>{level: <8}</level> | <level>{message}</level>",
    filter=lambda r: r["level"].no < logger.level("WARNING").no,
)

ip_regex = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')

ipapi_url = (
    "http://ip-api.com/batch"
    "?fields=status,message,query,country,countryCode,city,lat,lon,isp,org,as,asname"
)

web_page = """<!doctype html>
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
  #bar .stat { color:var(--dim); font-size:12px; }
  #bar .stat b { color:#fff; }
  #bar .spacer { margin-left:auto; }
  #main { flex:1; display:flex; min-height:0; }
  #side { width:300px; flex:none; display:flex; flex-direction:column;
          border-right:1px solid var(--line); min-height:0; }
  .panel { overflow:auto; padding:10px 12px; }
  .panel .hdr { color:var(--dim); margin:2px 0 8px; text-transform:uppercase;
                letter-spacing:.6px; font-size:11px; display:flex; justify-content:space-between; }
  #asPanel { border-bottom:1px solid var(--line); max-height:45%; font-family:ui-monospace, monospace; }
  #tree { flex:1; font-size:12.5px; font-family:ui-monospace, monospace; }
  .asrow { display:flex; align-items:center; gap:8px; padding:3px 4px; border-radius:5px;
           cursor:pointer; white-space:nowrap; }
  .asrow:hover { background:rgba(255,255,255,.05); }
  .asrow.sel { background:rgba(245,158,11,.16); }
  .asrow .sw { width:11px; height:11px; border-radius:3px; flex:none; }
  .asrow .nm { overflow:hidden; text-overflow:ellipsis; }
  .asrow .ct { margin-left:auto; color:var(--dim); font-size:11px; }
  #net { flex:1; min-width:0; position:relative; }
  #details { position:absolute; right:12px; bottom:12px; width:300px; z-index:5;
             background:rgba(17,24,39,.95); border:1px solid var(--line);
             border-radius:10px; padding:12px 14px; font-size:12px; display:none;
             font-family:ui-monospace, monospace; }
  #details .ip { font-size:14px; font-weight:700; color:#fff; margin-bottom:8px; word-break:break-all; }
  #details .r { display:flex; justify-content:space-between; gap:12px; padding:2px 0; }
  #details .k { color:var(--dim); }
  #details .v { color:var(--txt); text-align:right; word-break:break-word; }
  #details .close { position:absolute; top:8px; right:11px; color:var(--dim); cursor:pointer; font-size:14px; }
  .tn > .row { display:flex; align-items:center; gap:7px; padding:2px 0; white-space:nowrap;
               cursor:pointer; border-radius:4px; }
  .tn > .row:hover { background:rgba(255,255,255,.05); }
  .tn > .row.sel { background:rgba(245,158,11,.16); }
  .tn .st { width:9px; height:9px; border-radius:50%; flex:none; background:var(--pend); }
  .tn .ip { color:var(--txt); }
  .tn .meta { color:var(--dim); font-size:11px; }
  .tn .kids { margin-left:9px; padding-left:12px; border-left:1px solid var(--line); }
</style>
</head>
<body>
<div id="bar">
  <span class="title">PanchanScope</span>
  <button id="btn-group">group by AS</button>
  <button id="btn-dead">hide dead</button>
  <button id="btn-fit">fit</button>
  <button id="exp-json">export json</button>
  <button id="exp-dot">export dot</button>
  <span class="spacer"></span>
  <span class="stat">nodes <b id="s-nodes">0</b> &middot; alive <b id="s-alive">0</b>
    &middot; AS <b id="s-as">0</b> &middot; <b id="s-state">crawling&hellip;</b></span>
</div>
<div id="main">
  <div id="side">
    <div id="asPanel" class="panel">
      <div class="hdr"><span>AS groups</span><span id="as-count">0</span></div>
      <div id="asList"></div>
    </div>
    <div id="tree" class="panel">
      <div class="hdr"><span>discovery tree</span></div>
      <div id="treeRoot"></div>
    </div>
  </div>
  <div id="net"><div id="details"></div></div>
</div>
<script>
  const palette = { pending:'#6b7280', alive:'#7bc043', dead:'#e0564c' };
  const asPalette = ['#60a5fa','#f59e0b','#a855f7','#ec4899','#14b8a6','#eab308',
                     '#f97316','#06b6d4','#84cc16','#e11d48','#8b5cf6','#22c55e',
                     '#fb7185','#38bdf8','#fbbf24','#4ade80','#c084fc','#2dd4bf'];
  const asColorMap = {};
  const nodes = new vis.DataSet();
  const edges = new vis.DataSet();
  const tree = {};
  const stateOf = {}, parentOf = {}, metaOf = {}, infoOf = {}, asnOf = {}, outdeg = {}, inOf = {};
  let finished = false, grouped = false, hideDead = false, selected = null, selAS = null;

  function asOf(id){ return asnOf[id] || 'unknown'; }
  function asColor(asn){
    if(asn === 'unknown') return '#3b4654';
    if(!asColorMap[asn]) asColorMap[asn] = asPalette[Object.keys(asColorMap).length % asPalette.length];
    return asColorMap[asn];
  }
  function isHub(id){ return (outdeg[id] || 0) >= 3; }
  function sizeFor(id){ const b = stateOf[id] === 'dead' ? 8 : 12; return b + Math.min((outdeg[id] || 0) * 1.8, 30); }
  function nodeColor(id){
    const border = palette[stateOf[id] || 'pending'];
    const bg = asnOf[id] ? asColor(asnOf[id]) : '#1f2630';
    return { background:bg, border, highlight:{ background:bg, border:'#ffffff' } };
  }
  function refresh(id){ if(nodes.get(id)) nodes.update({ id, color:nodeColor(id),
    size:sizeFor(id), borderWidth:isHub(id) ? 4 : 2 }); }
  function ensure(id){ if(!nodes.get(id)){ if(!(id in stateOf)) stateOf[id] = 'pending';
    nodes.add({ id, label:id, title:id, color:nodeColor(id), size:sizeFor(id) }); } }

  function tnode(id){
    if(tree[id]) return tree[id];
    const wrap = document.createElement('div'); wrap.className = 'tn';
    const row = document.createElement('div'); row.className = 'row'; row.dataset.id = id;
    const st = document.createElement('span'); st.className = 'st';
    const ip = document.createElement('span'); ip.className = 'ip'; ip.textContent = id;
    const meta = document.createElement('span'); meta.className = 'meta';
    row.append(st, ip, meta);
    const kids = document.createElement('div'); kids.className = 'kids';
    wrap.append(row, kids);
    tree[id] = { wrap, row, st, meta, kids, attached:false };
    return tree[id];
  }
  function treeRoot(id){ const n = tnode(id);
    if(!n.attached){ document.getElementById('treeRoot').append(n.wrap); n.attached = true; } }
  function treeChild(id, p){ const pn = tnode(p), n = tnode(id);
    if(!n.attached){ pn.kids.append(n.wrap); n.attached = true; } }
  function treeState(id, s){ const n = tree[id]; if(n) n.st.style.background = palette[s] || palette.pending; }
  function treeMeta(id, m){ const n = tree[id]; if(n && m) n.meta.textContent = m; }

  function hud(){
    let alive = 0; for(const k in stateOf) if(stateOf[k] === 'alive') alive++;
    const asset = new Set(Object.values(asnOf)); asset.delete(undefined);
    document.getElementById('s-nodes').textContent = nodes.length;
    document.getElementById('s-alive').textContent = alive;
    document.getElementById('s-as').textContent = asset.size;
    document.getElementById('s-state').textContent = finished ? 'done' : 'crawling…';
  }

  function rebuildASPanel(){
    const groups = {};
    for(const id in asnOf){ const a = asnOf[id]; (groups[a] || (groups[a] = [])).push(id); }
    const arr = Object.entries(groups).sort((a, b) => b[1].length - a[1].length);
    document.getElementById('as-count').textContent = arr.length;
    const list = document.getElementById('asList'); list.innerHTML = '';
    arr.forEach(([asn, ips]) => {
      const row = document.createElement('div'); row.className = 'asrow'; row.dataset.as = asn;
      if(asn === selAS) row.classList.add('sel');
      const sw = document.createElement('span'); sw.className = 'sw'; sw.style.background = asColor(asn);
      const nm = document.createElement('span'); nm.className = 'nm'; nm.textContent = asn;
      nm.title = asn;
      const ct = document.createElement('span'); ct.className = 'ct'; ct.textContent = ips.length;
      row.append(sw, nm, ct); list.append(row);
    });
  }

  const options = {
    nodes: { shape:'dot', size:12, borderWidth:2,
             font:{ color:'#e5e7eb', size:12, face:'ui-monospace, monospace',
                    strokeWidth:4, strokeColor:'#0b0f14' } },
    edges: { color:{ color:'#3a4553', highlight:'#9ca3af' }, width:1,
             smooth:{ type:'continuous' }, arrows:{ to:{ enabled:true, scaleFactor:0.45 } } },
    physics: { stabilization:false,
               barnesHut:{ gravitationalConstant:-32000, centralGravity:0.1, springLength:180,
                           springConstant:0.03, damping:0.5, avoidOverlap:0.6 } },
    interaction: { hover:true, tooltipDelay:120 }
  };
  const network = new vis.Network(document.getElementById('net'), { nodes, edges }, options);

  const details = document.getElementById('details');
  function renderDetails(id){
    const d = infoOf[id] || {}, st = stateOf[id] || 'pending', ctrl = outdeg[id] || 0;
    const rows = [];
    const esc = (s) => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));
    const add = (k, v) => { if(v || v === 0) rows.push(
      '<div class="r"><span class="k">' + esc(k) + '</span><span class="v">' + esc(v) + '</span></div>'); };
    add('status', st + (isHub(id) ? ' - hub' : ''));
    add('controls', ctrl + (ctrl === 1 ? ' node' : ' nodes'));
    add('announced by', parentOf[id] || '(seed)');
    add('AS', asOf(id));
    if(d.asname) add('asname', d.asname);
    const loc = [d.city, d.country].filter(Boolean).join(', '); if(loc) add('location', loc);
    add('isp', d.isp); add('org', d.org);
    details.innerHTML = '<span class="close">×</span><div class="ip">' + esc(id) + '</div>' + rows.join('');
    details.querySelector('.close').onclick = () => selectNode(null);
    details.style.display = 'block';
  }

  function dimAll(dim){
    nodes.update(nodes.get().filter(n => !n.id.startsWith('as:')).map(n => ({ id:n.id,
      color: dim && !dim.has(n.id) ? { background:'#10151b', border:'#1b2430' } : nodeColor(n.id),
      opacity: dim && !dim.has(n.id) ? 0.25 : 1 })));
  }
  function selectAS(asn){
    selAS = (selAS === asn) ? null : asn;
    selected = null;
    document.querySelectorAll('.asrow').forEach(r => r.classList.toggle('sel', r.dataset.as === selAS));
    if(!selAS){ dimAll(null); return; }
    const keep = new Set(); for(const id in asnOf) if(asnOf[id] === selAS) keep.add(id);
    dimAll(keep);
  }
  function selectNode(id){
    if(selected && tree[selected]) tree[selected].row.classList.remove('sel');
    selected = id;
    if(!id){ details.style.display = 'none'; dimAll(null); try{ network.unselectAll(); }catch(_){} return; }
    if(tree[id]) tree[id].row.classList.add('sel');
    renderDetails(id);
    const keep = new Set([id]); (inOf[id] || []).forEach(x => keep.add(x));
    nodes.get(id); const kids = nodes.get().filter(n => parentOf[n.id] === id).map(n => n.id);
    kids.forEach(x => keep.add(x));
    dimAll(keep);
  }

  network.on('click', (p) => {
    if(p.nodes.length){ const id = p.nodes[0];
      if(typeof id === 'string' && id.startsWith('cluster:')){ network.openCluster(id); return; }
      selectNode(id);
    } else selectNode(null);
  });
  document.getElementById('asList').addEventListener('click', (e) => {
    const row = e.target.closest('.asrow'); if(row) selectAS(row.dataset.as);
  });
  document.getElementById('tree').addEventListener('click', (e) => {
    const row = e.target.closest('.row'); if(!row || !row.dataset.id) return;
    selectNode(row.dataset.id);
    try{ network.selectNodes([row.dataset.id]); network.focus(row.dataset.id, { scale:1.1, animation:true }); }catch(_){}
  });

  function groupByAS(){
    const groups = {};
    for(const id in asnOf){ const a = asnOf[id]; (groups[a] || (groups[a] = [])).push(id); }
    Object.entries(groups).forEach(([asn, ips]) => {
      if(ips.length < 2) return;
      network.cluster({
        joinCondition: (n) => asnOf[n.id] === asn,
        clusterNodeProperties: {
          id: 'cluster:' + asn, shape:'box',
          label: asn + '  ×' + ips.length,
          color: { background: asColor(asn), border:'#0b0f14' },
          font: { color:'#0b0f14', size:14, face:'ui-monospace, monospace', strokeWidth:0 },
          borderWidth: 2, margin: 8, shapeProperties:{ borderRadius:6 }
        }
      });
    });
  }
  function ungroup(){
    nodes.getIds().filter(id => typeof id === 'string' && id.startsWith('cluster:'))
      .forEach(id => { try{ network.openCluster(id); }catch(_){} });
  }

  document.getElementById('btn-group').onclick = (ev) => {
    grouped = !grouped; ev.target.classList.toggle('on', grouped);
    ev.target.textContent = grouped ? 'ungroup' : 'group by AS';
    if(grouped) groupByAS(); else ungroup();
  };
  document.getElementById('btn-dead').onclick = (ev) => {
    hideDead = !hideDead; ev.target.classList.toggle('on', hideDead);
    nodes.update(nodes.get().filter(n => stateOf[n.id] === 'dead').map(n => ({ id:n.id, hidden:hideDead })));
  };
  document.getElementById('btn-fit').onclick = () => network.fit({ animation:true });

  function download(name, text, type){
    const blob = new Blob([text], { type }); const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name; document.body.appendChild(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 0);
  }
  function exportJSON(){
    const out = { generated:new Date().toISOString(), as_groups:{}, nodes:[], edges:[] };
    for(const id in asnOf){ const a = asnOf[id]; (out.as_groups[a] || (out.as_groups[a] = [])).push(id); }
    nodes.get().filter(n => !String(n.id).startsWith('cluster:')).forEach(n => out.nodes.push({
      ip:n.id, state:stateOf[n.id] || 'pending', parent:parentOf[n.id] || null,
      controls:outdeg[n.id] || 0, as:asOf(n.id), info:infoOf[n.id] || {} }));
    edges.get().forEach(e => { if(!String(e.from).startsWith('cluster:')) out.edges.push({ from:e.from, to:e.to }); });
    download('panchanscope-export.json', JSON.stringify(out, null, 2), 'application/json');
  }
  function exportDOT(){
    const lines = ['digraph panchan {', '  rankdir=lr;',
                   '  node [shape=box, style=rounded, fontname=monospace];'];
    nodes.get().filter(n => !String(n.id).startsWith('cluster:')).forEach(n => {
      const st = stateOf[n.id] || 'pending';
      const col = st === 'alive' ? 'green' : st === 'dead' ? 'red' : 'gray';
      const label = (n.id + '\\\\n' + asOf(n.id)).replace(/"/g, "'");
      lines.push('  "' + n.id + '" [label="' + label + '", color=' + col + '];');
    });
    edges.get().forEach(e => { if(!String(e.from).startsWith('cluster:'))
      lines.push('  "' + e.from + '" -> "' + e.to + '";'); });
    lines.push('}');
    download('panchanscope.dot', lines.join('\\n'), 'text/plain');
  }
  document.getElementById('exp-json').onclick = exportJSON;
  document.getElementById('exp-dot').onclick = exportDOT;

  const es = new EventSource('/events');
  es.onmessage = (e) => {
    const ev = JSON.parse(e.data);
    switch(ev.t){
      case 'node':
        stateOf[ev.id] = ev.state; ensure(ev.id); refresh(ev.id); treeState(ev.id, ev.state); break;
      case 'root':
        if(!(ev.id in stateOf)) stateOf[ev.id] = 'pending'; ensure(ev.id); treeRoot(ev.id); break;
      case 'tree':
        parentOf[ev.id] = ev.parent; treeChild(ev.id, ev.parent); break;
      case 'edge': {
        ensure(ev.from); ensure(ev.to);
        const eid = ev.from + '->' + ev.to;
        if(!edges.get(eid)){ edges.add({ id:eid, from:ev.from, to:ev.to });
          (inOf[ev.to] || (inOf[ev.to] = new Set())).add(ev.from);
          outdeg[ev.from] = (outdeg[ev.from] || 0) + 1; refresh(ev.from); }
        break;
      }
      case 'info': {
        infoOf[ev.id] = ev.data || {};
        const asn = (ev.data && ev.data.as) ? ev.data.as : null;
        if(asn) asnOf[ev.id] = asn;
        nodes.update({ id:ev.id, title:ev.meta || ev.id }); refresh(ev.id);
        treeMeta(ev.id, ev.meta); rebuildASPanel();
        if(selected === ev.id) renderDetails(ev.id);
        break;
      }
      case 'done':
        finished = true; rebuildASPanel();
        try{ network.fit({ animation:{ duration:500 } }); }catch(_){}
        break;
    }
    hud();
  };
</script>
</body>
</html>
"""


class bus:
    def __init__(self):
        self.events = []
        self.cond = threading.Condition()

    def emit(self, **ev):
        with self.cond:
            self.events.append(ev)
            self.cond.notify_all()


def make_handler(eventbus):
    class handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                body = web_page.encode()
                self.send_response(200)
                self.send_header("content-type", "text/html; charset=utf-8")
                self.send_header("content-length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif self.path == "/events":
                self.send_response(200)
                self.send_header("content-type", "text/event-stream")
                self.send_header("cache-control", "no-cache")
                self.send_header("connection", "keep-alive")
                self.end_headers()
                last = 0
                while True:
                    with eventbus.cond:
                        if last >= len(eventbus.events):
                            eventbus.cond.wait(timeout=10)
                        batch = eventbus.events[last:]
                        last = len(eventbus.events)
                    try:
                        if batch:
                            for ev in batch:
                                self.wfile.write(f"data: {json.dumps(ev)}\n\n".encode())
                        else:
                            self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                    except Exception:
                        return
            else:
                self.send_response(404)
                self.send_header("content-length", "0")
                self.end_headers()

    return handler


def panchan(host, port=1919, timeout=30):
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(timeout)
    try:
        s.connect((host, port))
        logger.success(f"connected to {host}:{port}/tcp")
    except socket.error as e:
        logger.error(f"failed to connect to {host}:{port}/tcp: {e}")
        s.close()
        return None

    res = b""
    try:
        while True:
            data = s.recv(1024)

            if not data:
                logger.warning(f"no data received from {host}:{port}/tcp")
                break

            if b"pan-chan's mining island hi!" in data:
                logger.info("panchan node confirmed !")

            res += data

            if b"finish" in data:
                break
    except socket.timeout:
        logger.warning(f"timeout while reading from {host}:{port}/tcp")
    except socket.error as e:
        logger.error(f"socket error from {host}:{port}/tcp: {e}")
    finally:
        s.close()

    return res.decode(errors="replace")


def extract_relays(data):
    relays = []
    seen = set()
    for line in data.splitlines():
        for ip in ip_regex.findall(line):
            if ip in seen:
                continue
            try:
                ipaddress.ip_address(ip)
            except ValueError:
                continue
            seen.add(ip)
            relays.append(ip)
    return relays


def crawl(seeds, port=1919, timeout=5, max_nodes=None, workers=20, eventbus=None):
    graph = {}
    alive = set()
    visited = set()
    parent_of = {}
    queued = set(seeds)
    lock = threading.Lock()
    work = queue.Queue()
    stopped = threading.Event()

    for s in seeds:
        work.put(s)
        if eventbus:
            eventbus.emit(t="node", id=s, state="pending")
            eventbus.emit(t="root", id=s)

    def process(host):
        with lock:
            if host in visited or stopped.is_set():
                return
            if max_nodes is not None and len(visited) >= max_nodes:
                stopped.set()
                return
            visited.add(host)

        data = panchan(host, port=port, timeout=timeout)

        if not data:
            with lock:
                graph.setdefault(host, [])
            if eventbus:
                eventbus.emit(t="node", id=host, state="dead")
            return

        relays = extract_relays(data)
        with lock:
            alive.add(host)
            graph[host] = relays
            new = []
            for ip in relays:
                if ip not in queued:
                    queued.add(ip)
                    parent_of[ip] = host
                    new.append(ip)

        if eventbus:
            eventbus.emit(t="node", id=host, state="alive")
            for ip in relays:
                eventbus.emit(t="node", id=ip, state="pending")
                eventbus.emit(t="edge", **{"from": host, "to": ip})

        for ip in new:
            if eventbus:
                eventbus.emit(t="tree", id=ip, parent=host)
            logger.success(f"new node found -> {ip} (via {host})")
            if not stopped.is_set():
                work.put(ip)

    def worker():
        while True:
            host = work.get()
            if host is None:
                work.task_done()
                return
            try:
                process(host)
            finally:
                work.task_done()

    threads = [threading.Thread(target=worker, daemon=True) for _ in range(max(1, workers))]
    for t in threads:
        t.start()

    work.join()
    for _ in threads:
        work.put(None)
    for t in threads:
        t.join()

    logger.info("no nodes left to extract, aborting...")
    return graph, alive, visited, parent_of


def enrich(ips, timeout=30):
    info = {}
    ips = list(ips)
    for i in range(0, len(ips), 100):
        chunk = ips[i:i + 100]
        payload = json.dumps(chunk).encode()
        req = urllib.request.Request(
            ipapi_url, data=payload, headers={"content-type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                results = json.load(resp)
        except Exception as e:
            logger.error(f"enrichment failed for a batch: {e}")
            continue

        for entry in results:
            ip = entry.get("query")
            if entry.get("status") != "success":
                logger.warning(f"no geo/as data for {ip}: {entry.get('message', 'unknown')}")
                info[ip] = {}
                continue
            info[ip] = entry
            logger.info(f"{ip} -> {entry.get('countryCode', '?')} / {entry.get('as', '?')}")

        if i + 100 < len(ips):
            time.sleep(5)
    return info


def node_meta(ip, info):
    meta = info.get(ip, {})
    parts = []
    loc = " ".join(x for x in [meta.get("countryCode"), meta.get("city")] if x)
    if loc:
        parts.append(loc)
    if meta.get("as"):
        parts.append(meta["as"])
    return " - ".join(parts)


def print_tree(seeds, graph, alive, visited, parent_of, info):
    children = {}
    for ip, par in parent_of.items():
        children.setdefault(par, []).append(ip)
    for k in children:
        children[k].sort()

    tty = sys.stdout.isatty()
    c_alive = "\033[32m" if tty else ""
    c_dead = "\033[31m" if tty else ""
    c_pend = "\033[90m" if tty else ""
    c_dim = "\033[2m" if tty else ""
    c_reset = "\033[0m" if tty else ""

    utf = "utf" in (getattr(sys.stdout, "encoding", "") or "").lower()
    g_mid = "├── " if utf else "|-- "
    g_last = "└── " if utf else "`-- "
    g_bar = "│   " if utf else "|   "
    g_pad = "    "

    def classify(ip):
        if ip in alive:
            return "alive", c_alive
        if ip in visited:
            return "dead", c_dead
        return "pending", c_pend

    def walk(ip, prefix, is_last, is_root):
        state, col = classify(ip)
        branch = "" if is_root else prefix + (g_last if is_last else g_mid)
        meta = node_meta(ip, info)
        suffix = f"  {c_dim}{meta}{c_reset}" if meta else ""
        print(f"{branch}{col}{ip}{c_reset} [{state}]{suffix}")
        kids = children.get(ip, [])
        child_prefix = "" if is_root else prefix + (g_pad if is_last else g_bar)
        for i, k in enumerate(kids):
            walk(k, child_prefix, i == len(kids) - 1, False)

    print("--- discovery tree")
    for r in seeds:
        walk(r, "", True, True)
    print("--- end of tree")


def load_seeds(host, path):
    seeds = []
    if path:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    seeds.append(line)
    if host:
        seeds.append(host)
    out = []
    seen = set()
    for s in seeds:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def main():
    parser = argparse.ArgumentParser(
        description="maps the panchan p2p network via the 1919/tcp socket"
    )
    parser.add_argument("host", nargs="?", help="ip of the seed node")
    parser.add_argument("-f", "--file", help="txt file with one seed ip per line")
    parser.add_argument("-p", "--port", type=int, default=1919,
                        help="panchan socket port (default: 1919)")
    parser.add_argument("-t", "--timeout", type=int, default=5,
                        help="socket timeout in seconds (default: 5)")
    parser.add_argument("-m", "--max-nodes", type=int, default=None,
                        help="max number of nodes to contact (anti-runaway safety)")
    parser.add_argument("-T", "--workers", type=int, default=20,
                        help="number of parallel crawler threads (default: 20)")
    parser.add_argument("-o", "--output",
                        help="output dot file for the graph (graphviz)")
    parser.add_argument("-j", "--json", dest="json_out",
                        help="dump enriched node data to a json file")
    parser.add_argument("--no-enrich", action="store_true",
                        help="skip geo/as enrichment")
    parser.add_argument("-w", "--web", action="store_true",
                        help="serve a live tree + graph in the browser")
    parser.add_argument("--web-host", default="0.0.0.0",
                        help="bind address for the live view (default: 0.0.0.0)")
    parser.add_argument("--web-port", type=int, default=8080,
                        help="port for the live view (default: 8080)")
    args = parser.parse_args()

    seeds = load_seeds(args.host, args.file)
    if not seeds:
        parser.error("provide a seed host or a --file")

    eventbus = None
    if args.web:
        eventbus = bus()
        server = ThreadingHTTPServer((args.web_host, args.web_port), make_handler(eventbus))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        logger.info(f"live view -> http://{args.web_host}:{args.web_port}")

    graph, alive, visited, parent_of = crawl(
        seeds, port=args.port, timeout=args.timeout,
        max_nodes=args.max_nodes, workers=args.workers, eventbus=eventbus,
    )

    edges = sum(len(c) for c in graph.values())
    if not edges and not args.web:
        return

    nodes = set(graph) | {c for cs in graph.values() for c in cs}
    info = {}
    if not args.no_enrich and nodes:
        logger.info("--- enrichment")
        info = enrich(nodes, timeout=args.timeout)
        if eventbus:
            for ip in sorted(nodes):
                eventbus.emit(t="info", id=ip,
                              meta=node_meta(ip, info), data=info.get(ip, {}))

    print_tree(seeds, graph, alive, visited, parent_of, info)

    logger.success(
        f"{len(visited)} nodes contacted - {len(alive)} alive - {edges} edges"
    )

    if args.json_out:
        with open(args.json_out, "w") as f:
            json.dump(
                {"graph": graph, "alive": sorted(alive),
                 "parents": parent_of, "nodes": info},
                f, indent=2,
            )
        logger.success(f"data written to {args.json_out}")

    if args.output:
        with open(args.output, "w") as f:
            f.write(to_dot(graph, alive, info))
        logger.success(
            f"graph written to {args.output} "
            f"(render: dot -tpng {args.output} -o panchan.png)"
        )

    if args.web:
        eventbus.emit(t="done")
        logger.info("crawl finished - live view still up, ctrl-c to quit")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass


def to_dot(graph, alive, info=None):
    info = info or {}
    lines = [
        "digraph panchan {",
        "  rankdir=lr;",
        "  node [shape=box, style=rounded, fontname=monospace];",
    ]
    nodes = set(graph) | {c for cs in graph.values() for c in cs}
    for node in sorted(nodes):
        parts = [node]
        meta = node_meta(node, info)
        if meta:
            parts.append(meta)
        label = "\\n".join(parts).replace('"', "'")
        color = "green" if node in alive else "gray"
        lines.append(f'  "{node}" [label="{label}", color={color}];')
    for parent, children in graph.items():
        for child in children:
            lines.append(f'  "{parent}" -> "{child}";')
    lines.append("}")
    return "\n".join(lines)


if __name__ == "__main__":
    main()
