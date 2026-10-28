// swayforge Studio – core: server calls, staged settings, skin, navigation, form building.
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
const PAGES = {};          // id → {title, group, icon, render(view), keywords}
const GROUPS = [["Look", ["overview", "themes", "layouts", "wallpapers", "look", "bar"]],
  ["Devices", ["display", "audio", "sound", "bluetooth", "network", "input"]],
  ["Work & play", ["shell", "keys", "apps", "games"]],
  ["System", ["power", "boot", "security", "cleanup", "mounts", "system", "about"]]];

const Studio = {
  page(id, def) { PAGES[id] = def; },
};

// ── small helpers ─────────────────────────────────────────────────────
const theme = () => S.themes[S.s.theme.name] || Object.values(S.themes)[0];
const colours = () => Desk.colours(theme(), S.s.theme.accent);
const layoutOf = id => S.data.layouts.find(l => l.id === id) || S.data.layouts[0];
const get = path => path.split(".").reduce((o, k) => (o || {})[k], S.s);
function wallUrl(themeId) {
  const w = S.s.theme.wallpaper;
  if (w === "solid") return null;
  if (!w || w === "theme") return `/api/themewall?id=${encodeURIComponent(themeId || S.s.theme.name)}&t=${TOKEN}`;
  return `/api/thumb?p=${encodeURIComponent(w)}&t=${TOKEN}`;
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

// fit 640×360 desktops into their frames
const ro = new ResizeObserver(es => es.forEach(e => e.target.style.setProperty("--k", e.contentRect.width / Desk.W)));
function desk(frame, opts) {
  Desk.render(frame, Object.assign({ settings: S.s, user: S.data.user }, opts));
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
  document.body.dataset.skin = S.s.bar.layout;
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

// ── navigation ────────────────────────────────────────────────────────
function buildNav() {
  const nav = $("#nav");
  nav.replaceChildren();
  for (const [g, ids] of GROUPS) {
    const sec = h(`<div class="navgroup"><span class="navhead">${esc(g)}</span><ul class="nav" role="list"></ul></div>`);
    for (const id of ids) {
      const p = PAGES[id]; if (!p) continue;
      sec.querySelector("ul").append(h(`<li><button data-go="${id}"><span class="ico" aria-hidden="true">${p.icon}</span>${esc(p.title)}</button></li>`));
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
    h(`<li><button data-go="${x.id}" ${x.path ? `data-path="${x.path}"` : ""}><span class="ico">›</span><span>${esc(x.label)}<small class="navsub">${esc(x.sub || "")}</small></span></button></li>`)));
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
    document.body.innerHTML = `<p style="padding:40px;font:15px monospace">swayforge Studio could not reach its server (${esc(e.message)}). Start it again with <b>swayforge gui</b>.</p>`;
    return;
  }
  buildNav(); skin();
  let start = "overview";
  try { start = localStorage.getItem("studio-page") || start; } catch (_) { /* ignore */ }
  go(PAGES[start] ? start : "overview");
});
