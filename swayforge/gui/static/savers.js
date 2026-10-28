// Small canvas versions of the terminal screensavers, in the theme's colours.
"use strict";

const Savers = (() => {
  let speed = 5;
  function matrixStep(ctx, w, h, c, st) {
    const cs = 10, cols = Math.ceil(w / cs);
    st.y = st.y || Array.from({ length: cols }, () => Math.random() * -h / cs);
    ctx.fillStyle = Desk.rgba(c.crust, 0.22); ctx.fillRect(0, 0, w, h);
    ctx.font = `${cs}px monospace`;
    st.y.forEach((y, i) => {
      const ch = String.fromCharCode(0x30a0 + Math.floor(Math.random() * 96));
      ctx.fillStyle = Math.random() < 0.08 ? c.text : c.accent;
      ctx.fillText(ch, i * cs, y * cs);
      st.y[i] = y * cs > h && Math.random() > 0.96 ? 0 : y + 1;
    });
  }
  const scenes = {
    matrix(ctx, w, h, c, st) {
      // speed 1…10 like the real one: slow speeds skip frames, fast ones take several steps per frame
      st.f = (st.f || 0) + 0.25 * 1.32 ** (speed - 1);
      if (st.f < 1 && st.y) return;
      const steps = Math.max(1, Math.floor(st.f)); st.f -= steps;
      for (let i = 0; i < steps; i++) matrixStep(ctx, w, h, c, st);
    },
    cmatrix(ctx, w, h, c, st) { scenes.matrix(ctx, w, h, Object.assign({}, c, { accent: "#22dd44", crust: "#000000", text: "#c8ffc8" }), st); },
    starfield(ctx, w, h, c, st) {
      st.s = st.s || Array.from({ length: 140 }, () => ({ x: Math.random() * 2 - 1, y: Math.random() * 2 - 1, z: Math.random() }));
      ctx.fillStyle = c.crust; ctx.fillRect(0, 0, w, h);
      st.s.forEach(p => {
        p.z -= 0.012; if (p.z <= 0.02) { p.x = Math.random() * 2 - 1; p.y = Math.random() * 2 - 1; p.z = 1; }
        const x = w / 2 + p.x / p.z * w / 2, y = h / 2 + p.y / p.z * h / 2, r = (1 - p.z) * 2.2;
        ctx.fillStyle = p.z < 0.3 ? c.text : c.accent; ctx.fillRect(x, y, r, r);
      });
    },
    pipes(ctx, w, h, c, st) {
      const g = 8;
      if (!st.p || st.n++ > 900) { ctx.fillStyle = c.crust; ctx.fillRect(0, 0, w, h); st.n = 0; st.p = []; }
      if (st.p.length < 4) st.p.push({ x: Math.floor(Math.random() * w / g), y: Math.floor(Math.random() * h / g), d: Math.floor(Math.random() * 4),
        col: [c.accent, c.accent2, c.green, c.blue, c.magenta, c.yellow][Math.floor(Math.random() * 6)] });
      st.p.forEach(p => {
        if (Math.random() < 0.15) p.d = (p.d + (Math.random() < .5 ? 1 : 3)) % 4;
        p.x += [1, 0, -1, 0][p.d]; p.y += [0, 1, 0, -1][p.d];
        p.x = (p.x + Math.ceil(w / g)) % Math.ceil(w / g); p.y = (p.y + Math.ceil(h / g)) % Math.ceil(h / g);
        ctx.fillStyle = p.col; ctx.fillRect(p.x * g + 2, p.y * g + 2, g - 2, g - 2);
      });
    },
    fire(ctx, w, h, c, st) {
      const cw = 4, cols = Math.ceil(w / cw), rows = Math.ceil(h / cw);
      st.f = st.f || new Float32Array(cols * rows);
      const f = st.f;
      for (let x = 0; x < cols; x++) f[(rows - 1) * cols + x] = Math.random() < 0.6 ? 1 : 0.2;
      for (let y = 0; y < rows - 1; y++) for (let x = 0; x < cols; x++) {
        const b = (y + 1) * cols;
        f[y * cols + x] = Math.max(0, (f[b + x] + f[b + ((x + 1) % cols)] + f[b + ((x - 1 + cols) % cols)] + f[Math.min(rows - 1, y + 2) * cols + x]) / 4.0 - 0.022);
      }
      const pal = [c.crust, Desk.mix(c.crust, c.red, .7), c.red, c.orange, c.yellow, c.text];
      for (let y = 0; y < rows; y++) for (let x = 0; x < cols; x++) {
        const v = f[y * cols + x];
        ctx.fillStyle = pal[Math.min(pal.length - 1, Math.floor(v * pal.length))];
        ctx.fillRect(x * cw, y * cw, cw, cw);
      }
    },
    life(ctx, w, h, c, st) {
      const cs = 6, cols = Math.floor(w / cs), rows = Math.floor(h / cs);
      if (!st.g || st.n++ > 300) { st.n = 0; st.g = Array.from({ length: rows }, () => Array.from({ length: cols }, () => Math.random() < 0.25)); }
      if (st.n % 4 === 0) {
        const g = st.g;
        st.g = g.map((row, y) => row.map((v, x) => {
          let n = 0;
          for (let dy = -1; dy <= 1; dy++) for (let dx = -1; dx <= 1; dx++) if (dx || dy) n += g[(y + dy + rows) % rows][(x + dx + cols) % cols] ? 1 : 0;
          return n === 3 || (v && n === 2);
        }));
      }
      ctx.fillStyle = c.crust; ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = c.accent;
      st.g.forEach((row, y) => row.forEach((v, x) => { if (v) ctx.fillRect(x * cs, y * cs, cs - 1, cs - 1); }));
    },
    bounce(ctx, w, h, c, st) {
      st.b = st.b || { x: 20, y: 20, dx: 1.4, dy: 1.1, col: 0 };
      const b = st.b, txt = "swayforge", fw = 70, fh = 16;
      b.x += b.dx; b.y += b.dy;
      if (b.x < 0 || b.x + fw > w) { b.dx *= -1; b.col++; }
      if (b.y < 0 || b.y + fh > h) { b.dy *= -1; b.col++; }
      ctx.fillStyle = c.crust; ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = [c.accent, c.accent2, c.green, c.blue, c.magenta, c.yellow][b.col % 6];
      ctx.font = `bold 12px monospace`; ctx.fillText(txt, b.x, b.y + 12);
    },
    clock(ctx, w, h, c) {
      const d = new Date(), t = d.toTimeString().slice(0, 8);
      ctx.fillStyle = c.crust; ctx.fillRect(0, 0, w, h);
      ctx.textAlign = "center"; ctx.fillStyle = c.accent; ctx.font = `bold ${Math.round(h / 4)}px monospace`;
      ctx.fillText(t, w / 2, h / 2 + h / 12);
      ctx.fillStyle = c.subtext; ctx.font = `${Math.round(h / 14)}px monospace`;
      ctx.fillText(d.toDateString(), w / 2, h / 2 + h / 4);
      ctx.textAlign = "start";
    },
    off(ctx, w, h, c) {
      ctx.fillStyle = c.crust; ctx.fillRect(0, 0, w, h);
      ctx.fillStyle = c.subtext; ctx.textAlign = "center"; ctx.font = `${Math.round(h / 8)}px monospace`;
      ctx.fillText("🔒", w / 2, h / 2); ctx.font = `${Math.round(h / 16)}px monospace`; ctx.fillText("lock only", w / 2, h / 2 + h / 6);
      ctx.textAlign = "start";
    },
  };

  const running = new Map();     // canvas → {name, colours, state}
  let raf = 0, last = 0;
  const reduced = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const io = new IntersectionObserver(es => es.forEach(e => { const r = running.get(e.target); if (r) r.visible = e.isIntersecting; }));

  function tick(ts) {
    raf = requestAnimationFrame(tick);
    if (ts - last < 50) return;        // ~20 fps is plenty for previews
    last = ts;
    for (const [cv, r] of running) {
      if (!cv.isConnected) { running.delete(cv); io.unobserve(cv); continue; }
      if (!r.visible) continue;
      (scenes[r.name] || scenes.matrix)(r.ctx, cv.width, cv.height, r.c, r.st);
    }
  }

  function attach(canvas, name, colours) {
    const ctx = canvas.getContext("2d");
    const r = { name, c: colours, st: {}, ctx, visible: true };
    running.set(canvas, r);
    io.observe(canvas);
    (scenes[name] || scenes.matrix)(ctx, canvas.width, canvas.height, colours, r.st);
    if (!reduced && !raf) raf = requestAnimationFrame(tick);
  }
  function recolour(colours) { for (const r of running.values()) { r.c = colours; r.st = {}; } }
  return { attach, recolour, setSpeed: v => (speed = Math.max(1, Math.min(10, +v || 5))) };
})();
