// swayforge app – core: server calls, staged settings, skin, navigation, form building.
// The pages themselves live in pages.js and register with Studio.page().
"use strict";

const TOKEN = new URLSearchParams(location.hash.slice(1)).get("t") || "";
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch]));
const h = (html) => { const t = document.createElement("template"); t.innerHTML = html.trim(); return t.content.firstElementChild; };

const api = {
  async get(name, params = {}) {
    const q = new URLSearchParams(params).toString();
    const r = await fetch(`/api/${name}${q ? "?" + q : ""}`, { headers: { "X-Token": TOKEN } });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.error) throw new Error(j.error || r.statusText);
    return j;
  },
  async post(name, body = {}) {
    const r = await fetch(`/api/${name}`, { method: "POST", headers: { "X-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.error) throw new Error(j.error || r.statusText);
    return j;
  },
  // buttons: {ok, msg} – a failed action shows its message, a good one too when it has one
  async act(action, args = {}, quiet = false) {
    try {
      const r = await api.post("do", Object.assign({ action }, args));
      if (r.dirty !== undefined) setDirty(r.dirty);
      if (!r.ok) { toast(esc(r.msg), true); return null; }
      if (r.msg && !quiet) toast(esc(r.msg));
      return r;
    } catch (e) { toast(esc(e.message), true); return null; }
  },
};

const S = { data: null, s: null, themes: {}, fields: null, page: "overview", dirty: false, applying: false };
// one consistent line-icon set (24×24, drawn in the text colour) – no emoji, no mixed glyphs
const ICONS = {
  overview: '<path d="M3 11 12 4l9 7v9a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
  themes: '<path d="M12 3a9 9 0 1 0 0 18c1.1 0 1.5-.8 1.2-1.6-.4-1 .2-2.4 1.6-2.4H17a4 4 0 0 0 4-4c0-5-4-10-9-10z"/><circle cx="7.5" cy="11" r="1"/><circle cx="10" cy="7" r="1"/><circle cx="15" cy="7.5" r="1"/>',
  layouts: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 16h18M8 16v5"/>',
  wallpapers: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 17-5-5-9 8"/>',
  look: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>',
  bar: '<rect x="3" y="4" width="18" height="5" rx="1.5"/><path d="M6 6.5h2M10 6.5h2M3 14h18M3 18h12"/>',
  widgets: '<rect x="3" y="3" width="8" height="8" rx="2"/><circle cx="17" cy="7" r="4"/><rect x="3" y="14" width="18" height="7" rx="2"/>',
  display: '<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M9 21h6M12 17v4"/>',
  audio: '<path d="M4 9v6h4l5 4V5L8 9z"/><path d="M17 8a5 5 0 0 1 0 8M19.5 5.5a8.5 8.5 0 0 1 0 13"/>',
  sound: '<path d="M6 16v-5a6 6 0 0 1 12 0v5l2 2H4z"/><path d="M10 20a2 2 0 0 0 4 0"/>',
  bluetooth: '<path d="m7 7 10 10-5 4V3l5 4L7 17"/>',
  network: '<path d="M2 9a15 15 0 0 1 20 0M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0"/><circle cx="12" cy="19.5" r="1"/>',
  input: '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
  shell: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m7 9 3 3-3 3M12 15h5"/>',
  keys: '<path d="M9 6a3 3 0 1 0-3 3h12a3 3 0 1 0-3-3v12a3 3 0 1 0 3-3H6a3 3 0 1 0 3 3z"/>',
  apps: '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
  games: '<path d="M6 8h12a4 4 0 0 1 4 4l-1 4a3 3 0 0 1-5 1l-1.5-1.5h-5L8 17a3 3 0 0 1-5-1l-1-4a4 4 0 0 1 4-4z"/><path d="M7 11v3M5.5 12.5h3M16 11.5h.01M18 13h.01"/>',
  power: '<path d="M12 3v9"/><path d="M6.3 7a8 8 0 1 0 11.4 0"/>',
  boot: '<rect x="6" y="6" width="12" height="12" rx="1.5"/><path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4"/>',
  security: '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6z"/><path d="m9 12 2 2 4-4"/>',
  cleanup: '<path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 11v6M14 11v6"/>',
  mounts: '<rect x="3" y="13" width="18" height="7" rx="2"/><path d="M5 13 7 5h10l2 8M7 16.5h.01"/>',
  system: '<circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M4.2 4.2l2.1 2.1M17.7 17.7l2.1 2.1M2 12h3M19 12h3M4.2 19.8l2.1-2.1M17.7 6.3l2.1-2.1"/>',
  about: '<circle cx="12" cy="12" r="9"/><path d="M12 11v6M12 7.5h.01"/>',
  clipboard: '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4V3h6v1M9 10h6M9 14h6M9 18h3"/>',
  privacy: '<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
  maker: '<path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/>',
  found: '<path d="m9 6 6 6-6 6"/>',
};
const icon = id => `<svg class="ico" viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">${ICONS[id] || ICONS.found}</svg>`;
const PAGES = {};          // id → {title, group, icon, render(view), keywords}
const GROUPS = [["Look", ["overview", "themes", "layouts", "maker", "wallpapers", "look", "bar", "widgets"]],
  ["Devices", ["display", "audio", "sound", "bluetooth", "network", "input"]],
  ["Work & play", ["shell", "keys", "apps", "games", "clipboard"]],
  ["System", ["power", "boot", "security", "privacy", "cleanup", "mounts", "system", "about"]]];

const Studio = {
  page(id, def) { PAGES[id] = def; },
};

// ── small helpers ─────────────────────────────────────────────────────
const theme = () => S.themes[S.s.theme.name] || Object.values(S.themes)[0];
const colours = () => Desk.colours(theme(), S.s.theme.accent);
const layoutOf = id => S.data.layouts.find(l => l.id === id) || S.data.layouts[0];
const get = path => path.split(".").reduce((o, k) => (o || {})[k], S.s);
function wallUrl(themeId, big) {
  const w = S.s.theme.wallpaper;
  if (w === "solid") return null;
  if (!w || w === "theme") return `/api/themewall?id=${encodeURIComponent(themeId || S.s.theme.name)}&t=${TOKEN}`;
  // big previews get a big picture – a small thumbnail stretched over 1100 px looks blurry
  return `/api/thumb?p=${encodeURIComponent(w)}&w=${big ? 1760 : 480}&t=${TOKEN}`;
}
function toast(html, err = false) {
  const t = $("#toast");
  t.innerHTML = html; t.className = "toast" + (err ? " err" : ""); t.hidden = false;
  clearTimeout(toast.timer); toast.timer = setTimeout(() => (t.hidden = true), err ? 9000 : 4500);
}
function fmtBytes(n) {
  if (n < 0) return "?";
  const u = ["B", "KB", "MB", "GB", "TB"]; let i = 0;
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i ? 1 : 0)} ${u[i]}`;
}
// modal dialog; resolves with the button value ("" on cancel)
function dialog(html, init) {
  const d = $("#dlg"), body = $("#dlg-body");
  body.innerHTML = html;
  if (init) init(body);
  d.showModal();
  return new Promise(res => d.addEventListener("close", () => res(d.returnValue), { once: true }));
}

// one shared blink for every preview caret (no CSS animation – keeps previews sharp)
setInterval(() => $$(".desk-caret").forEach(c => c.classList.toggle("off")), 550);
// fit 640×360 desktops into their frames
const ro = new ResizeObserver(es => es.forEach(e => e.target.style.setProperty("--k", e.contentRect.width / Desk.W)));
function desk(frame, opts) {
  const mine = !opts.custom && String(opts.layout || "").startsWith("my-") ? (S.data.layouts.find(l => l.id === opts.layout) || {}).cfg : null;
  Desk.render(frame, Object.assign({ settings: S.s, user: S.data.user }, opts, mine ? { custom: mine } : {}));
  ro.observe(frame);
  frame.style.setProperty("--k", frame.clientWidth / Desk.W || 0.4);
}
const lazyIO = new IntersectionObserver(es => es.forEach(e => {
  if (e.isIntersecting && e.target._draw) { const f = e.target._draw; e.target._draw = null; lazyIO.unobserve(e.target); f(); }
}), { rootMargin: "300px" });
function lazy(frame, draw) { frame._draw = draw; lazyIO.observe(frame); }

// ── skin: the app wears the staged theme ───────────────────────────────
function skin() {
  const t = theme(), c = colours(), r = document.documentElement.style;
  const set = (k, v) => r.setProperty(k, v);
  set("--bg", c.base); set("--panel", c.mantle); set("--deep", c.crust); set("--raise", c.surface); set("--line", c.surface2);
  set("--dim", c.overlay); set("--muted", c.subtext); set("--ink", c.text); set("--acc", c.accent); set("--acc2", c.accent2);
  set("--on-acc", Desk.on(c.accent, c.crust, c)); set("--red", c.red); set("--green", c.green); set("--yellow", c.yellow);
  set("--r", Math.min(12, S.s.look.radius) + "px"); set("--r-big", Math.min(16, S.s.look.radius + 4) + "px");
  set("--mono", `"${S.s.theme.font}", "JetBrainsMono Nerd Font", ui-monospace, monospace`);
  const face = Desk.mix(c.surface, c.text, .1);
  set("--hi", Desk.mix(face, c.text, .6)); set("--lo", Desk.mix(face, c.crust, .85));
  document.documentElement.style.colorScheme = t.dark ? "dark" : "light";
  document.body.dataset.skin = layoutOf(S.s.bar.layout).base || S.s.bar.layout;
  logo(c);
}
const PIX = {
  S: [".####", "#....", ".###.", "....#", "####."], W: ["#...#", "#...#", "#.#.#", "##.##", "#...#"],
  A: [".###.", "#...#", "#####", "#...#", "#...#"], Y: ["#...#", ".#.#.", "..#..", "..#..", "..#.."],
  F: ["#####", "#....", "####.", "#....", "#...."], O: [".###.", "#...#", "#...#", "#...#", ".###."],
  R: ["####.", "#...#", "####.", "#..#.", "#...#"], G: [".####", "#....", "#..##", "#...#", ".####"],
  E: ["#####", "#....", "####.", "#....", "#####"],
};
function logo(c) {
  const cv = $("#logo"), g = cv.getContext("2d"), px = 4;
  g.clearRect(0, 0, cv.width, cv.height);
  let x = 2;
  for (const ch of "SWAYFORGE") {
    const gl = PIX[ch];
    for (let yy = 0; yy < 5; yy++) for (let xx = 0; xx < 5; xx++) if (gl[yy][xx] === "#") {
      g.fillStyle = Desk.mix(c.accent, c.crust, .55); g.fillRect(x + xx * px + 2, 6 + yy * px * 1.6 + 2, px, px * 1.6);
      g.fillStyle = c.accent; g.fillRect(x + xx * px, 6 + yy * px * 1.6, px, px * 1.6);
    }
    x += 6 * px - 1;
  }
}

// ── staged changes ────────────────────────────────────────────────────
let railPending = false;
function railRedraw() {
  if (railPending) return;
  railPending = true;
  requestAnimationFrame(() => {
    railPending = false; skin();
    const t = theme(), lay = layoutOf(S.s.bar.layout);
    desk($("#rail-desk"), { theme: t, layout: S.s.bar.layout, wallpaperUrl: wallUrl() });
    $("#rail-caption").textContent = `${t.label.split(" (")[0]} with ${lay.label}`;
    (PAGES[S.page].live || (() => {}))();
  });
}
function setDirty(d) {
  S.dirty = d;
  $("#apply").disabled = !d || S.applying; $("#revert").disabled = !d || S.applying;
  const st = $("#state");
  st.classList.toggle("dirty", d);
  st.textContent = S.applying ? "Applying …" : d ? "Not applied yet" : "Your desktop matches";
}
const sendQueue = new Map();
let sendTimer = 0;
function change(path, value) {
  if (path === "power.saver_speed") Savers.setSpeed(value);
  path.split(".").reduce((o, k, i, arr) => (i === arr.length - 1 ? (o[k] = value) : (o[k] = o[k] || {})), S.s);
  setDirty(true);
  railRedraw();
  sendQueue.set(path, value);
  clearTimeout(sendTimer);
  sendTimer = setTimeout(flush, 180);
}
async function flush() {
  const items = [...sendQueue]; sendQueue.clear();
  for (const [path, value] of items) {
    try { const r = await api.post("set", { path, value }); setDirty(r.dirty); }
    catch (e) { toast(`<b>Not taken:</b> ${esc(e.message)}`, true); }
  }
}
async function reloadSettings() {
  const st = await api.get("state");
  S.data = st; S.s = st.settings; st.themes.forEach(t => (S.themes[t.id] = t)); setDirty(st.dirty);
}
async function apply() {
  S.applying = true; setDirty(S.dirty); $("#apply").classList.add("busy");
  try {
    await flush();
    await api.post("apply");
    for (;;) {
      await new Promise(r => setTimeout(r, 600));
      const st = await api.get("status");
      if (!st.applying) {
        const res = st.result || {};
        if (res.ok) toast(`<b>Applied</b> in ${res.seconds}s.`);
        else toast(`<b>Apply failed:</b> ${esc((res.errors || ["unknown error"]).join(" "))}`, true);
        S.applying = false; setDirty(st.dirty);
        break;
      }
    }
  } catch (e) { S.applying = false; setDirty(true); toast(`<b>Apply failed:</b> ${esc(e.message)}`, true); }
  $("#apply").classList.remove("busy");
}

// ── forms from the shared field list (fields.py) ───────────────────────
function fieldRow(f) {
  const id = "f-" + f.path.replace(/\./g, "-"), v = get(f.path);
  const row = h(`<div class="row" data-path="${f.path}"><label for="${id}">${esc(f.label)}</label></div>`);
  let inp;
  if (f.kind === "bool") {
    inp = h(`<input id="${id}" class="switch" type="checkbox" role="switch">`);
    inp.checked = !!v;
    inp.addEventListener("change", () => change(f.path, inp.checked));
  } else if (f.kind === "choice") {
    inp = h(`<select id="${id}"></select>`);
    const opts = f.options.slice();
    if (!opts.some(([, x]) => String(x) === String(v))) opts.push([String(v), v]);
    opts.forEach(([lab, val]) => { const o = document.createElement("option"); o.value = JSON.stringify(val); o.textContent = lab; o.selected = String(val) === String(v); inp.append(o); });
    inp.addEventListener("change", () => change(f.path, JSON.parse(inp.value)));
  } else {
    const num = f.kind === "int" || f.kind === "float";
    inp = h(`<input id="${id}" type="${num ? "number" : "text"}" ${f.kind === "float" ? 'step="0.05"' : ""} spellcheck="false">`);
    inp.value = v ?? "";
    inp.addEventListener("input", () => {
      if (num && inp.value === "") return;
      change(f.path, num ? (f.kind === "int" ? parseInt(inp.value, 10) : parseFloat(inp.value)) : inp.value);
    });
  }
  row.append(inp);
  if (f.help) row.append(h(`<small>${esc(f.help)}</small>`));
  return row;
}
function form(pid, opts = {}) {
  const box = h(`<div class="controls"></div>`);
  const skip = new Set(opts.skip || []);
  let head = null;                       // a heading only shows when a field follows it
  for (const f of S.fields.forms[pid] || []) {
    if (typeof f === "string") { head = opts.noHeads ? null : f; continue; }
    if (skip.has(f.path)) continue;
    if (head) { box.append(h(`<h2>${esc(head.replace(/\s*[–(].*$/, ""))}</h2>`)); head = null; }
    box.append(fieldRow(f));
  }
  return box;
}
function section(title, lede) {
  const s = h(`<section class="block"><h2 class="block-title">${esc(title)}</h2></section>`);
  if (lede) s.append(h(`<p class="lede">${lede}</p>`));
  return s;
}
function button(label, cls, onclick) {
  const b = h(`<button type="button" class="btn ${cls || ""}">${esc(label)}</button>`);
  b.addEventListener("click", onclick);
  return b;
}
function busy(btn, promise) {
  btn.disabled = true; btn.classList.add("busy");
  return Promise.resolve(promise).finally(() => { btn.disabled = false; btn.classList.remove("busy"); });
}
function loading(view, text = "Looking …") { view.replaceChildren(h(`<p class="hint loading">${esc(text)}</p>`)); }

// sliders show how far they are filled (WebKit/Chromium need it as a variable)
function fill(inp) {
  const mn = +inp.min || 0, mx = +inp.max || 100;
  inp.style.setProperty("--fill", `${((+inp.value - mn) / (mx - mn || 1)) * 100}%`);
}
document.addEventListener("input", e => { if (e.target.matches?.("input[type=range]")) fill(e.target); });
new MutationObserver(ms => ms.forEach(m => m.addedNodes.forEach(n => n.querySelectorAll?.("input[type=range]").forEach(fill))))
  .observe(document.body, { childList: true, subtree: true });

// ── navigation ────────────────────────────────────────────────────────
function buildNav() {
  const nav = $("#nav");
  nav.replaceChildren();
  for (const [g, ids] of GROUPS) {
    const sec = h(`<div class="navgroup"><span class="navhead">${esc(g)}</span><ul class="nav" role="list"></ul></div>`);
    for (const id of ids) {
      const p = PAGES[id]; if (!p) continue;
      sec.querySelector("ul").append(h(`<li><button data-go="${id}">${icon(id)}${esc(p.title)}</button></li>`));
    }
    nav.append(sec);
  }
}
async function go(id, focusPath) {
  if (!PAGES[id]) id = "overview";
  S.page = id;
  $$(".nav button").forEach(b => { if (b.dataset.go === id) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  $("#title").textContent = PAGES[id].title;
  try { localStorage.setItem("studio-page", id); } catch (_) { /* private */ }
  const view = $("#view");
  view.dataset.page = id;
  view.replaceChildren();
  $("#main").scrollTop = 0;
  try { await PAGES[id].render(view); }
  catch (e) { view.replaceChildren(h(`<p class="hint">This page could not load: ${esc(e.message)}</p>`)); }
  railRedraw();
  if (focusPath) {
    const row = $(`[data-path="${focusPath}"]`);
    if (row) { row.scrollIntoView({ block: "center" }); row.classList.add("flash"); row.querySelector("input,select")?.focus(); }
  }
}

// search across every setting label and page title
function findSetting(q) {
  q = q.trim().toLowerCase();
  const nav = $("#nav");
  if (!q) return buildNav();
  const hits = [];
  for (const [id, p] of Object.entries(PAGES)) {
    if (p.title.toLowerCase().includes(q) || (p.keywords || "").includes(q)) hits.push({ id, label: p.title, sub: "page" });
  }
  for (const [pid, fs] of Object.entries(S.fields.forms)) {
    const page = { look: "look", bar: "bar", sound: "sound", input: "input", shell: "shell", keys: "keys", power: "power", boot: "boot", security: "security" }[pid];
    let head = "";
    for (const f of fs) {
      if (typeof f === "string") { head = f.replace(/\s*[–(].*$/, ""); continue; }
      if ((head + " " + f.label + " " + (f.help || "")).toLowerCase().includes(q))
        hits.push({ id: page, label: f.label, sub: `${PAGES[page]?.title} · ${head}`, path: f.path });
    }
  }
  nav.replaceChildren(h(`<div class="navgroup"><span class="navhead">${hits.length ? "Found" : "Nothing found"}</span><ul class="nav" role="list"></ul></div>`));
  hits.slice(0, 30).forEach(x => nav.querySelector("ul").append(
    h(`<li><button data-go="${x.id}" ${x.path ? `data-path="${x.path}"` : ""}>${icon("found")}<span>${esc(x.label)}<small class="navsub">${esc(x.sub || "")}</small></span></button></li>`)));
}

document.addEventListener("click", e => {
  const b = e.target.closest("button[data-go]");
  if (b) { e.preventDefault(); go(b.dataset.go, b.dataset.path); if (b.dataset.path) { $("#find").value = ""; buildNav(); } }
});
$("#apply").addEventListener("click", apply);
$("#revert").addEventListener("click", async () => {
  const r = await api.post("revert"); S.s = r.settings; setDirty(false); go(S.page); toast("Changes undone");
});
let findTimer = 0;
$("#find").addEventListener("input", e => { clearTimeout(findTimer); findTimer = setTimeout(() => findSetting(e.target.value), 120); });
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); if (S.dirty && !S.applying) apply(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "f") { e.preventDefault(); $("#find").focus(); }
});
setInterval(() => api.post("ping").catch(() => {}), 5000);

window.addEventListener("load", async () => {
  try {
    await reloadSettings();
    S.fields = await api.get("fields");
  } catch (e) {
    document.body.innerHTML = `<p style="padding:40px;font:15px monospace">swayforge app could not reach its server (${esc(e.message)}). Start it again with <b>swayforge gui</b>.</p>`;
    return;
  }
  buildNav(); skin();
  let start = "overview";
  try { start = localStorage.getItem("studio-page") || start; } catch (_) { /* ignore */ }
  go(PAGES[start] ? start : "overview");
});
