from __future__ import annotations

import json
from html import escape


class AnimationHtmlComposerService:
    def compose(
        self,
        *,
        title: str,
        viz_type: str,
        render_payload: dict[str, object],
        fragment_payload: dict[str, object],
    ) -> str:
        safe_title = escape(title or "故事可视化")
        render_json = json.dumps(render_payload, ensure_ascii=False)
        fragment_json = json.dumps(fragment_payload, ensure_ascii=False)

        if viz_type == "relationship":
            body = self._relationship_body(title=safe_title, payload=render_payload)
        elif viz_type == "claim_judgment":
            body = self._comparison_body(title=safe_title, payload=render_payload)
        else:
            body = self._timeline_body(title=safe_title, payload=render_payload)

        needs_d3 = viz_type in {"relationship", "claim_judgment"}
        subtitle_map = {"relationship": "关系图", "claim_judgment": "诉求 vs 判决"}
        subtitle = subtitle_map.get(viz_type, "时间线")

        if viz_type == "relationship":
            script_js = self._d3_script(render_payload=render_payload)
        elif viz_type == "claim_judgment":
            script_js = self._comparison_script(render_payload=render_payload)
        else:
            script_js = self._timeline_script(render_payload=render_payload)

        return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{safe_title}</title>
<style>
:root {{
  --bg:#0b1220;--bg2:#0f1a2e;--glass:rgba(255,255,255,.06);--border:rgba(148,163,184,.2);
  --text:#e2e8f0;--muted:#94a3b8;--accent:#38bdf8;--accent2:#818cf8;--accent3:#34d399;
  --danger:#f87171;--card-bg:rgba(15,23,42,.55);
}}
html{{scroll-behavior:smooth}}
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,'Noto Sans SC',sans-serif;background:var(--bg);color:var(--text);line-height:1.6}}
.wrap{{padding:24px 16px;max-width:960px;margin:0 auto}}
header{{text-align:center;margin-bottom:28px}}
h1{{font-size:22px;font-weight:700;margin-bottom:6px;color:var(--text)}}
.meta{{font-size:12px;color:var(--muted);letter-spacing:.5px}}
.card{{background:var(--card-bg);border:1px solid var(--border);border-radius:20px;backdrop-filter:blur(12px);box-shadow:0 8px 30px rgba(0,0,0,.3)}}
.card-inner{{padding:20px}}
.section-title{{font-size:14px;font-weight:600;color:var(--accent);margin-bottom:12px;display:flex;align-items:center;gap:6px}}
.section-title::before{{content:'';display:inline-block;width:4px;height:16px;background:var(--accent);border-radius:2px}}
.annotation{{font-size:13px;color:var(--muted);padding:8px 14px;border-left:3px solid var(--accent3);background:rgba(52,211,153,.08);border-radius:0 8px 8px 0;margin:6px 0;}}
</style>
{self._d3_head() if needs_d3 else ""}
</head>
<body>
<div class="wrap">
<header><h1>{safe_title}</h1><div class="meta">法穿 · 故事可视化 · {subtitle}</div></header>
{body}
</div>
<script>
const renderPayload = {render_json};
const fragmentPayload = {fragment_json};
{script_js}
</script>
</body>
</html>"""

    # ── Relationship ────────────────────────────────────────────────────
    def _relationship_body(self, title: str, payload: dict[str, object]) -> str:
        """构建关系图 HTML body."""
        return '<div class="card viz-wrap"><div class="card-inner"><div class="section-title">关系图</div><div id="viz-root"></div></div></div>'

    # ── D3 ──────────────────────────────────────────────────────────────
    def _d3_head(self) -> str:
        return '<script src="https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"></script>'

    def _d3_script(self, render_payload: dict[str, object]) -> str:
        edges = render_payload.get("edges", [])
        nodes = render_payload.get("nodes", [])
        nodes_str = json.dumps(nodes, ensure_ascii=False)
        edges_str = json.dumps(edges, ensure_ascii=False)
        return f"""
(function(){{
const width=Math.min(920,document.querySelector('.viz-wrap').clientWidth);
const height=520;
const nodes={nodes_str}.map((d,i)=>({{id:d.id||d.label||String(i),label:d.label||d.id||'',category:d.category||'person'}}));
const edges={edges_str}.map(e=>({{source:e.source,target:e.target,relation:e.relation||''}}));
if(nodes.length===0){{document.getElementById('viz-root').innerHTML='<div style="text-align:center;color:var(--muted);padding:40px;">暂无可视化数据</div>';return;}}

const categories=Array.from(new Set(nodes.map(d=>d.category)));
const color=d3.scaleOrdinal(categories,['#38bdf8','#818cf8','#34d399','#fbbf24','#f87171','#a78bfa','#fb7185']);

const svg=d3.select('#viz-root').append('svg').attr('width',width).attr('height',height).attr('viewBox',[0,0,width,height]).style('border-radius','14px');
svg.append('rect').attr('width',width).attr('height',height).attr('fill','transparent');

const defs=svg.append('defs');
const frags=(typeof fragmentPayload!=='undefined'&&fragmentPayload.fragments)?fragmentPayload.fragments:[];
frags.forEach((f,i)=>{{if(f.svg)defs.append('g').attr('id','frag-'+i).html(f.svg);}});

const g=svg.append('g');
const zoom=d3.zoom().on('zoom',e=>g.attr('transform',e.transform));
svg.call(zoom).call(zoom.transform,d3.zoomIdentity);

const fragG=g.append('g').attr('opacity',0.08);
frags.forEach((f,i)=>{{
  const use=fragG.append('use').attr('href','#frag-'+i);
  use.attr('x',Math.random()*width*0.8+width*0.1).attr('y',Math.random()*height*0.8+height*0.1);
}});

const link=g.append('g').selectAll('line').data(edges).join('line').attr('stroke','rgba(148,163,184,.35)').attr('stroke-width',1.5);
const linkText=g.append('g').selectAll('text').data(edges).join('text').text(d=>d.relation).attr('font-size','10px').attr('fill','var(--muted)').attr('text-anchor','middle');

const node=g.append('g').selectAll('g').data(nodes).join('g').call(d3.drag().on('start',(e,d)=>{{if(!e.active)sim.alphaTarget(.3).restart();d.fx=d.x;d.fy=d.y;}}).on('drag',(e,d)=>{{d.fx=e.x;d.fy=e.y;}}).on('end',(e,d)=>{{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}}));

node.append('circle').attr('r',d=>d.category==='center'?28:18).attr('fill',d=>{{const c=color(d.category);return c+"22";}}).attr('stroke',d=>color(d.category)).attr('stroke-width',2).style('filter','drop-shadow(0 0 8px '+color(0)+')');
node.append('text').text(d=>d.label||d.id).attr('dy','.35em').attr('text-anchor','middle').attr('font-size','11px').attr('fill','var(--text)');

node.append('title').text(d=>d.label+(d.category?` [${{d.category}}]`));

const sim=d3.forceSimulation(nodes).force('link',d3.forceLink(edges).id(d=>d.id).distance(100)).force('charge',d3.forceManyBody().strength(-320)).force('center',d3.forceCenter(width/2,height/2)).force('collide',d3.forceCollide(36));

sim.on('tick',()=>{{link.attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);linkText.attr('x',d=>(d.source.x+d.target.x)/2).attr('y',d=>(d.source.y+d.target.y)/2);node.attr('transform',d=>`translate(${{d.x}},${{d.y}})`);}});
}})();
"""

    # ── Comparison (claim_judgment) ──────────────────────────────────────
    def _comparison_body(self, title: str, payload: dict[str, object]) -> str:
        annotations: list[object] = payload.get("annotations", []) or []  # type: ignore[assignment]
        anno_html = ""
        if annotations:
            items = "".join(
                f'<div class="annotation">• {escape(str(a))}</div>'
                for a in annotations
                if isinstance(a, (str, int, float))
            )
            anno_html = f'<div class="card" style="margin-bottom:16px"><div class="card-inner"><div class="section-title">裁判要点</div>{items}</div></div>'

        return f"""
{anno_html}
<div class="card viz-wrap"><div class="card-inner"><div class="section-title">诉求 vs 判决</div><div id="viz-root"></div></div></div>
<style>
.cmp-row{{display:flex;align-items:center;gap:8px;margin-bottom:14px;padding:10px 14px;background:var(--glass);border:1px solid var(--border);border-radius:12px;opacity:0;animation:tl-in .5s both}}
.cmp-label{{flex:0 0 140px;font-size:13px;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.cmp-bars{{flex:1;display:flex;flex-direction:column;gap:4px}}
.cmp-bar-row{{display:flex;align-items:center;gap:8px;font-size:11px}}
.cmp-bar-label{{width:32px;color:var(--muted);text-align:right;flex-shrink:0}}
.cmp-bar-track{{flex:1;height:18px;background:rgba(255,255,255,.04);border-radius:4px;overflow:hidden;position:relative}}
.cmp-bar{{height:100%;border-radius:4px;transition:width .8s ease-out;display:flex;align-items:center;padding:0 6px;font-size:10px;color:#fff;white-space:nowrap}}
.cmp-bar-claim{{background:linear-gradient(90deg,#3b82f6,#60a5fa)}}
.cmp-bar-judgment{{background:linear-gradient(90deg,#22c55e,#4ade80)}}
.cmp-badge{{flex:0 0 60px;text-align:center;font-size:11px;font-weight:600;padding:2px 8px;border-radius:999px}}
.cmp-badge-yes{{background:rgba(34,197,94,.15);color:#4ade80}}
.cmp-badge-no{{background:rgba(248,113,113,.15);color:#f87171}}
@keyframes tl-in{{from{{opacity:0;transform:translateY(12px)}}to{{opacity:1;transform:translateY(0)}}}}
</style>"""

    def _comparison_script(self, render_payload: dict[str, object]) -> str:
        nodes = render_payload.get("nodes", [])
        return f"""
(function(){{
const items={json.dumps(nodes, ensure_ascii=False)};
const root=document.getElementById('viz-root');
if(!items.length){{root.innerHTML='<div style="text-align:center;color:var(--muted);padding:40px">暂无可视化数据</div>';return;}}

function parseAmt(s){{if(!s)return 0;const n=parseFloat(String(s).replace(/[^0-9.\\-]/g,''));return isNaN(n)?0:n;}}

const maxAmt=Math.max(1,...items.map(d=>Math.max(parseAmt(d.amount_claim),parseAmt(d.amount_judgment))));

items.forEach((d,i)=>{{
  const row=document.createElement('div');row.className='cmp-row';row.style.animationDelay=(i*.1)+'s';
  const label=document.createElement('div');label.className='cmp-label';label.textContent=d.claim||'诉求'+(i+1);label.title=d.claim||'';

  const bars=document.createElement('div');bars.className='cmp-bars';

  const ac=parseAmt(d.amount_claim),aj=parseAmt(d.amount_judgment);
  if(ac>0||aj>0){{
    const r1=document.createElement('div');r1.className='cmp-bar-row';
    r1.innerHTML='<span class="cmp-bar-label">主张</span><div class="cmp-bar-track"><div class="cmp-bar cmp-bar-claim" style="width:'+Math.round(ac/maxAmt*100)+'%">'+(d.amount_claim||'')+'</div></div>';
    bars.appendChild(r1);
    const r2=document.createElement('div');r2.className='cmp-bar-row';
    r2.innerHTML='<span class="cmp-bar-label">判决</span><div class="cmp-bar-track"><div class="cmp-bar cmp-bar-judgment" style="width:'+Math.round(aj/maxAmt*100)+'%">'+(d.amount_judgment||'')+'</div></div>';
    bars.appendChild(r2);
  }} else {{
    const desc=document.createElement('div');desc.style.cssText='font-size:12px;color:var(--muted);line-height:1.5';
    const c=d.claim||'',j=d.judgment||'';
    desc.innerHTML=(c?'<div>主张: '+escapeHtml(c)+'</div>':'')+(j?'<div>判决: '+escapeHtml(j)+'</div>':'');
    bars.appendChild(desc);
  }}

  const badge=document.createElement('div');
  badge.className='cmp-badge '+(d.supported?'cmp-badge-yes':'cmp-badge-no');
  badge.textContent=d.supported?'支持':'未支持';

  row.appendChild(label);row.appendChild(bars);row.appendChild(badge);
  root.appendChild(row);
}});

function escapeHtml(t){{if(!t)return'';return String(t).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
}})();
"""

    # ── Timeline ────────────────────────────────────────────────────────
    def _timeline_body(self, title: str, payload: dict[str, object]) -> str:
        nodes = payload.get("nodes", [])
        annotations: list[object] = payload.get("annotations", []) or []  # type: ignore[assignment]
        anno_html = ""
        if annotations:
            items = "".join(
                f'<div class="annotation">• {escape(str(a))}</div>'
                for a in annotations
                if isinstance(a, (str, int, float))
            )
            anno_html = f'<div class="card" style="margin-bottom:16px"><div class="card-inner"><div class="section-title">关键节点</div>{items}</div></div>'

        return f"""
{anno_html}
<div class="card viz-wrap"><div class="card-inner"><div class="section-title">时间线</div><div id="viz-root"></div></div></div>
<style>
.timeline{{position:relative;padding-left:24px}}
.timeline::before{{content:'';position:absolute;left:7px;top:0;bottom:0;width:3px;background:linear-gradient(180deg,var(--accent),var(--accent2),var(--accent3));border-radius:3px;opacity:.6}}
.tl-node{{position:relative;margin-bottom:24px;padding-left:18px;opacity:0;animation:tl-in .7s both}}
.tl-node::before{{content:'';position:absolute;left:-22px;top:5px;width:14px;height:14px;border-radius:50%;background:var(--card-bg);border:3px solid var(--accent);box-shadow:0 0 10px var(--accent);z-index:2}}
.tl-node:last-child::before{{border-color:var(--accent3);background:var(--accent3)}}
.tl-time{{font-size:11px;color:var(--accent);font-weight:700;margin-bottom:4px;letter-spacing:.3px}}
.tl-label{{font-size:14px;color:var(--text);background:var(--glass);border:1px solid var(--border);padding:10px 14px;border-radius:12px;backdrop-filter:blur(4px)}}
@keyframes tl-in{{from{{opacity:0;transform:translateY(16px)}}to{{opacity:1;transform:translateY(0)}}}}
</style>"""

    def _timeline_script(self, render_payload: dict[str, object]) -> str:
        nodes = render_payload.get("nodes", [])
        return f"""
(function(){{
const nodes={json.dumps(nodes, ensure_ascii=False)};
const root=document.getElementById('viz-root');
if(!nodes.length){{root.innerHTML='<div style="text-align:center;color:var(--muted);padding:40px">暂无可视化数据</div>';return;}}

const frags=(typeof fragmentPayload!=='undefined'&&fragmentPayload.fragments)?fragmentPayload.fragments:[];
if(frags.length){{
  const fragWrap=document.createElement('div');fragWrap.style.cssText='display:flex;gap:12px;justify-content:center;margin-bottom:16px;opacity:.3';
  frags.forEach(function(f){{
    if(!f.svg)return;
    const d=document.createElement('div');d.innerHTML='<svg width="40" height="40" viewBox="0 0 40 40">'+f.svg+'</svg>';
    fragWrap.appendChild(d);
  }});
  root.appendChild(fragWrap);
}}

const wrap=document.createElement('div');wrap.className='timeline';
nodes.forEach((n,i)=>{{
  const el=document.createElement('div');el.className='tl-node';el.style.animationDelay=(i*.12)+'s';
  el.innerHTML='<div class="tl-time">'+escapeHtml(n.time||'──')+'</div><div class="tl-label">'+escapeHtml(n.label||'')+'</div>';
  wrap.appendChild(el);
}});
root.appendChild(wrap);
function escapeHtml(t){{if(!t)return'';return t.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}}
}})();
"""
