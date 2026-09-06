/* CANlab hero: an interactive brain network.
   A stylised side-view brain (soft amber blob with a hint of cerebellum and brainstem) holds ~90 nodes
   joined to their nearest neighbours. Idle: nodes drift and activity pulses hop along edges. Hovering or
   touching stimulates nearby nodes, which fire pulses that cascade 2–3 hops with decay; click/tap fires a
   stronger cascade. Dependency-free canvas. Exposes window.CANLAB_HERO.burst() for a manual cascade. */
(function () {
  const canvas = document.getElementById("hero-canvas");
  const wrap = canvas && (canvas.closest(".hero-canvas-wrap") || canvas.parentElement);
  if (!canvas || !wrap || !canvas.getContext) return;
  const ctx = canvas.getContext("2d");
  const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const N = 92, HOVER_PX = 90, MIN_D = 5.3, UNIT_W = 100, UNIT_H = 90;

  // Brain outline (side view, facing left) in a 100×90 unit box: cerebrum, cerebellum, brainstem.
  const SHAPES = [
    [[7,44],[11,28],[22,13],[40,5],[58,4],[76,9],[90,21],[97,38],[95,52],[86,58],[68,60],[55,66],[40,70],[22,66],[12,58]],
    [[66,60],[78,56],[90,58],[96,67],[92,77],[80,81],[68,78],[61,69]],
    [[52,62],[64,62],[66,76],[62,90],[54,90],[50,76]],
  ];
  // Closed Catmull-Rom spline sampled to a polygon (drawn and used for point-in-brain tests).
  function outline(pts, inset) {
    const n = pts.length, out = [], cx = pts.reduce((s, p) => s + p[0], 0) / n, cy = pts.reduce((s, p) => s + p[1], 0) / n;
    const P = pts.map(p => [cx + (p[0] - cx) * inset, cy + (p[1] - cy) * inset]);
    for (let i = 0; i < n; i++) {
      const p0 = P[(i + n - 1) % n], p1 = P[i], p2 = P[(i + 1) % n], p3 = P[(i + 2) % n];
      for (let k = 0; k < 10; k++) {
        const t = k / 10, t2 = t * t, t3 = t2 * t;
        out.push([0.5 * (2 * p1[0] + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3),
                  0.5 * (2 * p1[1] + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)]);
      }
    }
    return out;
  }
  const POLYS = SHAPES.map(s => outline(s, 1)), INNER = SHAPES.map(s => outline(s, 0.9));
  function inside(x, y, polys) {
    return polys.some(poly => {
      let hit = false;
      for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
        const a = poly[i], b = poly[j];
        if ((a[1] > y) !== (b[1] > y) && x < (b[0] - a[0]) * (y - a[1]) / (b[1] - a[1]) + a[0]) hit = !hit;
      }
      return hit;
    });
  }

  // Deterministic layout: seeded RNG so the network looks the same on every visit.
  let seed = 20240917; const rnd = () => (seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296;
  const nodes = [];
  for (let tries = 0; nodes.length < N && tries < 6000; tries++) {
    const x = rnd() * UNIT_W, y = rnd() * UNIT_H;
    if (!inside(x, y, INNER) || nodes.some(n => Math.hypot(n.x - x, n.y - y) < MIN_D)) continue;
    nodes.push({ x, y, r: 2.2 + rnd() * 1.6, amber: rnd() < 0.22, ph: rnd() * Math.PI * 2, f: 0.7 + rnd() * 0.6, act: 0, fired: -1e9, nb: [], sx: 0, sy: 0 });
  }
  nodes.forEach((n, i) => {
    const k = 2 + Math.floor(rnd() * 3);
    nodes.map((m, j) => [Math.hypot(m.x - n.x, m.y - n.y), j]).sort((a, b) => a[0] - b[0]).slice(1, k + 1)
      .forEach(([, j]) => { if (!n.nb.includes(j)) { n.nb.push(j); nodes[j].nb.push(i); } });
  });
  const edges = []; nodes.forEach((n, i) => n.nb.forEach(j => { if (j > i) edges.push([i, j]); }));

  let W = 0, H = 0, S = 1, OX = 0, OY = 0, raf = null, last = 0, visible = true, idleIn = 400;
  const pulses = [];
  const hex = h => [1, 3, 5].map(i => parseInt(h.slice(i, i + 2), 16));
  const mix = (a, b, t, al) => `rgba(${a.map((v, i) => Math.round(v + (b[i] - v) * t)).join(",")},${al == null ? 1 : al})`;
  function theme() {
    const attr = document.documentElement.getAttribute("data-theme");
    const dark = attr === "dark" || (!attr && window.matchMedia("(prefers-color-scheme: dark)").matches);
    return dark
      ? { dark, blob0: "rgba(52,70,92,.9)", blob1: "rgba(30,44,61,.7)", rim: "rgba(143,176,210,.35)", edge: [143,176,210], steel: hex("#8fb0d2"), amber: hex("#e9b949"), hot: hex("#fff1c2"), glow: "233,185,73" }
      : { dark, blob0: "rgba(253,245,218,.96)", blob1: "rgba(244,218,140,.8)", rim: "rgba(199,147,26,.45)", edge: [63,99,144], steel: hex("#5f80a2"), amber: hex("#c7931a"), hot: hex("#e9b949"), glow: "199,147,26" };
  }

  function resize() {
    const r = wrap.getBoundingClientRect(), dpr = Math.min(window.devicePixelRatio || 1, 2);
    W = Math.max(1, Math.round(r.width)); H = Math.max(1, Math.round(r.height));
    canvas.width = W * dpr; canvas.height = H * dpr; canvas.style.width = W + "px"; canvas.style.height = H + "px";
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    const pad = Math.min(W, H) * 0.06;
    S = Math.min((W - 2 * pad) / UNIT_W, (H - 2 * pad) / UNIT_H);
    OX = (W - UNIT_W * S) / 2; OY = (H - UNIT_H * S) / 2;
    kick();
  }
  const toScreen = (x, y) => [OX + x * S, OY + y * S];

  // Spawn pulses from node i to up to `count` neighbours; each carries strength and remaining hops.
  function fire(i, str, hops, count, from) {
    const n = nodes[i], nb = n.nb.filter(j => j !== from).sort(() => rnd() - 0.5).slice(0, count);
    for (const j of nb) {
      if (pulses.length > 260) return;
      const len = Math.hypot(nodes[j].sx - n.sx, nodes[j].sy - n.sy) || 1;
      pulses.push({ a: i, b: j, t: 0, v: 0.17 / len, str, hops });
    }
  }
  function stimulate(px, py, strong) {
    const now = performance.now(), R = strong ? HOVER_PX * 1.25 : HOVER_PX;
    nodes.forEach((n, i) => {
      const d = Math.hypot(n.sx - px, n.sy - py); if (d > R) return;
      const k = 1 - d / R;
      n.act = Math.max(n.act, strong ? 1 : 0.85 * k);
      if (strong ? now - n.fired > 80 : k > 0.3 && now - n.fired > 550) { n.fired = now; fire(i, strong ? 1 : 0.55 + 0.35 * k, strong ? 3 : 2, strong ? 3 : 2); }
    });
    kick();
  }

  function step(dt, now) {
    const decay = Math.exp(-dt / 520);
    nodes.forEach(n => {
      const drift = reduce ? 0 : 0.012 * S;
      n.sx = OX + (n.x + Math.sin(now * 0.0007 * n.f + n.ph) * drift * 60 / S) * S;
      n.sy = OY + (n.y + Math.cos(now * 0.0009 * n.f + n.ph * 1.3) * drift * 60 / S) * S;
      n.act *= decay;
    });
    if (!reduce && (idleIn -= dt) <= 0) { idleIn = 500 + rnd() * 400; fire(Math.floor(rnd() * nodes.length), 0.75, 1, 1); }
    for (let i = pulses.length - 1; i >= 0; i--) {
      const p = pulses[i]; p.t += p.v * dt;
      if (p.t < 1) continue;
      pulses.splice(i, 1);
      const b = nodes[p.b]; b.act = Math.max(b.act, p.str);
      if (p.hops > 0 && p.str > 0.18) fire(p.b, p.str * 0.6, p.hops - 1, p.str > 0.7 ? 2 : 1, p.a);
    }
  }

  function draw() {
    const T = theme();
    ctx.clearRect(0, 0, W, H);
    // brain blob: soft inner gradient + rim
    ctx.save(); ctx.translate(OX, OY); ctx.scale(S, S);
    const g = ctx.createRadialGradient(38, 30, 4, 52, 46, 62);
    g.addColorStop(0, T.blob0); g.addColorStop(1, T.blob1);
    ctx.beginPath(); POLYS.forEach(poly => { poly.forEach((p, i) => i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1])); ctx.closePath(); });
    // rim: stroke wide, clear the interior, then fill: only the outer edge of the union survives (no inner seams)
    ctx.lineWidth = 2.8 / S; ctx.strokeStyle = T.rim; ctx.lineJoin = "round"; ctx.stroke();
    ctx.globalCompositeOperation = "destination-out"; ctx.fill("nonzero");
    ctx.globalCompositeOperation = "source-over"; ctx.fillStyle = g; ctx.fill("nonzero");
    ctx.restore();
    // edges brighten with the activation of either endpoint
    ctx.lineWidth = 1;
    for (const [i, j] of edges) {
      const a = nodes[i], b = nodes[j], k = Math.max(a.act, b.act);
      ctx.strokeStyle = mix(T.edge, T.hot, k, (T.dark ? 0.2 : 0.22) + 0.6 * k);
      ctx.lineWidth = 0.8 + 1.2 * k;
      ctx.beginPath(); ctx.moveTo(a.sx, a.sy); ctx.lineTo(b.sx, b.sy); ctx.stroke();
    }
    // pulses: short glowing trail + bright dot
    for (const p of pulses) {
      const a = nodes[p.a], b = nodes[p.b], t0 = Math.max(0, p.t - 0.22);
      const x = a.sx + (b.sx - a.sx) * p.t, y = a.sy + (b.sy - a.sy) * p.t, x0 = a.sx + (b.sx - a.sx) * t0, y0 = a.sy + (b.sy - a.sy) * t0;
      const tr = ctx.createLinearGradient(x0, y0, x, y);
      tr.addColorStop(0, `rgba(${T.glow},0)`); tr.addColorStop(1, `rgba(${T.glow},${0.75 * p.str})`);
      ctx.strokeStyle = tr; ctx.lineWidth = 2.2; ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x, y); ctx.stroke();
      const halo = ctx.createRadialGradient(x, y, 0, x, y, 9);
      halo.addColorStop(0, `rgba(${T.glow},${0.5 * p.str})`); halo.addColorStop(1, `rgba(${T.glow},0)`);
      ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(x, y, 9, 0, Math.PI * 2); ctx.fill();
      ctx.fillStyle = mix(T.hot, [255, 250, 235], p.str * 0.5); ctx.beginPath(); ctx.arc(x, y, 1.8 + 1.6 * p.str, 0, Math.PI * 2); ctx.fill();
    }
    // nodes: grow and warm with activation, with a soft halo
    for (const n of nodes) {
      const base = n.amber ? T.amber : T.steel, r = n.r * (1 + 0.9 * n.act);
      if (n.act > 0.04) {
        const hr = r + 3 + 9 * n.act, halo = ctx.createRadialGradient(n.sx, n.sy, r * 0.5, n.sx, n.sy, hr);
        halo.addColorStop(0, `rgba(${T.glow},${0.4 * n.act})`); halo.addColorStop(1, `rgba(${T.glow},0)`);
        ctx.fillStyle = halo; ctx.beginPath(); ctx.arc(n.sx, n.sy, hr, 0, Math.PI * 2); ctx.fill();
      }
      ctx.fillStyle = mix(base, T.hot, Math.min(1, n.act * 1.2)); ctx.beginPath(); ctx.arc(n.sx, n.sy, r, 0, Math.PI * 2); ctx.fill();
    }
  }

  const active = () => pulses.length > 0 || nodes.some(n => n.act > 0.01);
  function frame(now) {
    raf = null;
    const dt = Math.min(50, now - last || 16); last = now;
    step(dt, now); draw();
    if (visible && (!reduce || active())) raf = requestAnimationFrame(frame);
  }
  function kick() { if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); } }

  const local = e => { const r = canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
  canvas.addEventListener("pointermove", e => { const [x, y] = local(e); stimulate(x, y, false); });
  canvas.addEventListener("pointerdown", e => { const [x, y] = local(e); stimulate(x, y, true); });
  canvas.addEventListener("touchmove", e => { const t = e.touches[0]; if (t) { const [x, y] = local(t); stimulate(x, y, false); } }, { passive: true });
  let rt; window.addEventListener("resize", () => { clearTimeout(rt); rt = setTimeout(resize, 120); });
  const mq = window.matchMedia("(prefers-color-scheme: dark)"); if (mq.addEventListener) mq.addEventListener("change", kick);
  if (window.MutationObserver) new MutationObserver(kick).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
  if (window.IntersectionObserver) new IntersectionObserver(es => { visible = es[0].isIntersecting; if (visible) kick(); }, { threshold: 0.05 }).observe(wrap);

  window.CANLAB_HERO = { burst() {
    const n = nodes[Math.floor(rnd() * nodes.length)]; if (n) stimulate(n.sx, n.sy, true);
  } };
  resize();
})();
