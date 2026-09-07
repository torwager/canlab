/* CANlab hero: the lab's network graph, redrawn on canvas and made to fire.
   The layout (49 nodes, 150 edges) was extracted from the cover graphic and is loaded from
   assets/hero-graph.json (or an inline window.CANLAB_HERO_GRAPH). Every node is drawn light grey and
   only breathes very slowly at rest. Hovering, touching or clicking a node makes it fire: it lights up
   yellow and its edges light up from the node outwards, shifting yellow -> orange as the signal travels.
   Arriving signals light the neighbour orange and continue with probability 0.7, 0.5 and 0.2 at hops 1-3,
   so activity spreads a little and dies out (capped at 120 pulses / 3 hops).
   Dependency-free. Exposes window.CANLAB_HERO.fire(nodeId?) for a manual cascade. */
(function () {
  const canvas = document.getElementById("hero-canvas");
  if (!canvas || !canvas.getContext) return;
  const wrap = canvas.closest(".hero-canvas-wrap") || canvas.parentElement;
  const ctx = canvas.getContext("2d");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const SPEED = 220;        // pulse speed, px/s (screen pixels)
  const MAX_PULSES = 120, MAX_HOPS = 3;
  const P_HOP = [0.7, 0.5, 0.2];   // probability that a pulse continues along each edge at hop 1, 2, 3
  const REFIRE_MS = 600, FADE_MS = 700, BREATH = 0.03;
  const STOPS = [[255, 216, 74], [255, 160, 50], [255, 138, 42]]; // #ffd84a -> #ffa032 -> #ff8a2a (yellow to orange)
  const YELLOW = STOPS[0], ORANGE = STOPS[2];

  // Colour of a pulse at travel fraction t: linear RGB between yellow (0), orange (0.5) and pink (1).
  function pulseColor(t) {
    t = Math.max(0, Math.min(1, t));
    const a = t < 0.5 ? STOPS[0] : STOPS[1], b = t < 0.5 ? STOPS[1] : STOPS[2], k = t < 0.5 ? t * 2 : t * 2 - 1;
    return [a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k, a[2] + (b[2] - a[2]) * k];
  }
  const rgba = (c, al) => `rgba(${c[0] | 0},${c[1] | 0},${c[2] | 0},${al == null ? 1 : al})`;
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const mix = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];

  function theme() {
    const attr = document.documentElement.getAttribute("data-theme");
    const dark = attr === "dark" || (attr !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    return dark ? { fill: hex("#3a414d"), rim: hex("#4a5261"), edge: "#2a303a" }
                : { fill: hex("#d9d5cc"), rim: hex("#c3bfb5"), edge: "#d3cfc6" };
  }

  let graph = null, nodes = [], edges = [];
  let W = 0, H = 0, S = 1, OX = 0, OY = 0;
  const pulses = [];
  let raf = null, last = 0, visible = true, hover = false;
  const rnd = Math.random;

  function setGraph(g) {
    if (!g || !g.nodes || !g.edges) return;
    graph = g;
    nodes = g.nodes.map((n, i) => ({ id: i, x: n.x, y: n.y, r: n.r, nb: [], sx: 0, sy: 0, sr: 0,
      lit: 0, litAt: -1e9, col: YELLOW, ph: rnd() * Math.PI * 2 }));
    edges = g.edges.filter(([i, j]) => nodes[i] && nodes[j] && i !== j);
    edges.forEach(([i, j]) => { nodes[i].nb.push(j); nodes[j].nb.push(i); });
    resize();
  }

  function resize() {
    const rect = wrap.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = Math.max(1, Math.round(rect.width)); H = Math.max(1, Math.round(rect.height));
    canvas.width = Math.round(W * dpr); canvas.height = Math.round(H * dpr);
    canvas.style.width = W + "px"; canvas.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    if (!graph) return;
    const pad = Math.min(W, H) * 0.05;
    S = Math.min((W - 2 * pad) / graph.w, (H - 2 * pad) / graph.h);
    OX = (W - graph.w * S) / 2; OY = (H - graph.h * S) / 2;
    for (const n of nodes) { n.sx = OX + n.x * S; n.sy = OY + n.y * S; n.sr = Math.max(2.2, n.r * S); }
    kick();
  }

  // --- firing ---------------------------------------------------------------
  function light(n, col, now) { n.lit = 1; n.litAt = now; n.col = col; }

  // Send a pulse from node i along each edge (except back along `from`), each with probability p.
  function fire(i, from, hop, p, now) {
    const n = nodes[i];
    if (!n || hop >= MAX_HOPS) return;
    for (const j of n.nb) {
      if (j === from || pulses.length >= MAX_PULSES) continue;
      if (p < 1 && rnd() > p) continue;
      const m = nodes[j], len = Math.hypot(m.sx - n.sx, m.sy - n.sy) || 1;
      pulses.push({ a: i, b: j, t: 0, len, hop });
    }
    kick();
  }
  function fireNode(i, now, force) {
    const n = nodes[i];
    if (!n) return;
    if (!force && now - n.litAt < REFIRE_MS) return;
    light(n, YELLOW, now);
    fire(i, -1, 0, P_HOP[0], now);
  }
  function nearest(px, py, maxDist) {
    let best = -1, bd = Infinity;
    for (const n of nodes) {
      const d = Math.hypot(n.sx - px, n.sy - py);
      const lim = maxDist == null ? Infinity : Math.max(1.6 * n.sr, 14);
      if (d < lim && d < bd) { bd = d; best = n.id; }
    }
    return best;
  }

  // --- simulation -------------------------------------------------------------
  function step(dt, now) {
    for (const n of nodes) if (n.lit > 0) n.lit = Math.max(0, 1 - (now - n.litAt) / FADE_MS);
    for (let k = pulses.length - 1; k >= 0; k--) {
      const p = pulses[k];
      p.t += (SPEED * dt / 1000) / p.len;
      if (p.t < 1) continue;
      pulses.splice(k, 1);
      light(nodes[p.b], ORANGE, now);
      fire(p.b, p.a, p.hop + 1, P_HOP[p.hop + 1] || 0, now);
    }
  }

  // --- drawing ----------------------------------------------------------------
  function draw(now) {
    const T = theme();
    ctx.clearRect(0, 0, W, H);
    ctx.lineWidth = 1; ctx.strokeStyle = T.edge; ctx.beginPath();
    for (const [i, j] of edges) { ctx.moveTo(nodes[i].sx, nodes[i].sy); ctx.lineTo(nodes[j].sx, nodes[j].sy); }
    ctx.stroke();

    for (const n of nodes) {
      const breath = reduce ? 1 : 1 + BREATH * Math.sin(now * 0.00045 + n.ph);
      const r = n.sr * breath * (1 + 0.25 * n.lit);
      ctx.save();
      ctx.fillStyle = rgba(mix(T.fill, n.col, n.lit));
      ctx.beginPath(); ctx.arc(n.sx, n.sy, r, 0, Math.PI * 2); ctx.fill();
      ctx.strokeStyle = rgba(mix(T.rim, n.col, n.lit)); ctx.lineWidth = 1; ctx.stroke();
      ctx.restore();
    }

    // Pulses: the edge itself lights up from the source towards the target; colour shifts yellow -> orange with travel.
    ctx.lineCap = "round";
    for (const p of pulses) {
      const a = nodes[p.a], b = nodes[p.b], dx = b.sx - a.sx, dy = b.sy - a.sy;
      const hx = a.sx + dx * p.t, hy = a.sy + dy * p.t;
      const g = ctx.createLinearGradient(a.sx, a.sy, hx, hy);
      g.addColorStop(0, rgba(YELLOW, 0.35)); g.addColorStop(1, rgba(pulseColor(p.t), 0.95));
      ctx.strokeStyle = g; ctx.lineWidth = 2.2;
      ctx.beginPath(); ctx.moveTo(a.sx, a.sy); ctx.lineTo(hx, hy); ctx.stroke();
    }
  }

  // --- animation loop: run only while visible and something moves ---------------
  const animating = () => pulses.length > 0 || hover || (!reduce && nodes.length > 0) || nodes.some(n => n.lit > 0);
  function frame(now) {
    raf = null;
    const dt = Math.min(50, last ? now - last : 16); last = now;
    step(dt, now); draw(now);
    if (visible && animating()) raf = requestAnimationFrame(frame); else last = 0;
  }
  function kick() { if (!raf && graph) { last = 0; raf = requestAnimationFrame(frame); } }

  // --- input --------------------------------------------------------------------
  const local = e => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  canvas.addEventListener("pointermove", e => {
    hover = true; const [x, y] = local(e), i = nearest(x, y, true);
    if (i >= 0) fireNode(i, performance.now(), false);
    kick();
  });
  canvas.addEventListener("pointerleave", () => { hover = false; });
  canvas.addEventListener("pointerdown", e => {
    const [x, y] = local(e), i = nearest(x, y, null);
    if (i >= 0) fireNode(i, performance.now(), true);
  });
  canvas.addEventListener("touchmove", e => {
    const t = e.touches && e.touches[0]; if (!t) return;
    const [x, y] = local(t), i = nearest(x, y, true);
    if (i >= 0) fireNode(i, performance.now(), false);
  }, { passive: true });

  let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(resize, 120); });
  if (window.ResizeObserver) new ResizeObserver(() => { clearTimeout(rt); rt = setTimeout(resize, 60); }).observe(wrap);
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  if (mq.addEventListener) mq.addEventListener("change", kick); else if (mq.addListener) mq.addListener(kick);
  if (window.MutationObserver) new MutationObserver(kick).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  if (window.IntersectionObserver) new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible) kick(); }, { threshold: 0.02 }).observe(wrap);

  window.CANLAB_HERO = {
    fire(id) {
      if (!nodes.length) return;
      const i = (id == null || !nodes[id]) ? Math.floor(rnd() * nodes.length) : id;
      fireNode(i, performance.now(), true);
    }
  };

  // --- load the graph ---------------------------------------------------------------
  const me = document.currentScript && document.currentScript.src;
  const url = me ? me.replace(/[^\/]*$/, "hero-graph.json") : "assets/hero-graph.json";
  if (window.CANLAB_HERO_GRAPH) setGraph(window.CANLAB_HERO_GRAPH);
  else if (window.fetch) fetch(url).then(r => (r.ok ? r.json() : null)).then(setGraph).catch(() => {});
})();
