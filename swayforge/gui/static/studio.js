// swayforge Studio – front end. Talks to the local server (server.py) with the token from the URL.
"use strict";

const TOKEN = new URLSearchParams(location.hash.slice(1)).get("t") || "";
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const esc = s => String(s).replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));

const api = {
  async get(name, params = {}) {
    const q = new URLSearchParams(params).toString();
    const r = await fetch(`/api/${name}${q ? "?" + q : ""}`, { headers: { "X-Token": TOKEN } });
    if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || r.statusText);
    return r.json();
  },
  async post(name, body = {}) {
    const r = await fetch(`/api/${name}`, { method: "POST", headers: { "X-Token": TOKEN, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.error) throw new Error(j.error || r.statusText);
    return j;
  },
};

const S = { data: null, s: null, themes: {}, page: "overview", filter: "all", wallPage: 0, wallQ: "", dirty: false };

// ── helpers ───────────────────────────────────────────────────────────
const theme = () => S.themes[S.s.theme.name] || Object.values(S.themes)[0];
const layoutOf = id => S.data.layouts.find(l => l.id === id);
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

// fit 640×360 desktops into their frames
const ro = new ResizeObserver(es => es.forEach(e => e.target.style.setProperty("--k", e.contentRect.width / Desk.W)));
function desk(frame, opts) {
  Desk.render(frame, Object.assign({ settings: S.s, user: S.data.user }, opts));
  ro.observe(frame);
  frame.style.setProperty("--k", frame.clientWidth / Desk.W || 0.4);
}

// ── skin: the app wears the staged theme ───────────────────────────────
function skin() {
  const t = theme(), c = Desk.colours(t, S.s.theme.accent), r = document.documentElement.style;
  const set = (k, v) => r.setProperty(k, v);
  set("--bg", c.base); set("--panel", c.mantle); set("--deep", c.crust); set("--raise", c.surface); set("--line", c.surface2);
  set("--dim", c.overlay); set("--muted", c.subtext); set("--ink", c.text); set("--acc", c.accent); set("--acc2", c.accent2);
  set("--on-acc", Desk.on(c.accent, c.crust, c)); set("--red", c.red);
  set("--r", Math.min(12, S.s.look.radius) + "px"); set("--r-big", Math.min(16, S.s.look.radius + 4) + "px");
  set("--mono", `"${S.s.theme.font}", "JetBrainsMono Nerd Font", ui-monospace, monospace`);
  const face = Desk.mix(c.surface, c.text, .1);
  set("--hi", Desk.mix(face, c.text, .6)); set("--lo", Desk.mix(face, c.crust, .85));
  document.documentElement.style.colorScheme = t.dark ? "dark" : "light";
  document.body.dataset.skin = S.s.bar.layout;
  logo(c);
}

// pixel logo – the same 5-pixel font as the terminal banners
const PIX = {
  S: [".####", "#....", ".###.", "....#", "####."], W: ["#...#", "#...#", "#.#.#", "##.##", "#...#"],
  A: [".###.", "#...#", "#####", "#...#", "#...#"], Y: ["#...#", ".#.#.", "..#..", "..#..", "..#.."],
  F: ["#####", "#....", "####.", "#....", "#...."], O: [".###.", "#...#", "#...#", "#...#", ".###."],
  R: ["####.", "#...#", "####.", "#..#.", "#...#"], G: [".####", "#....", "#..##", "#...#", ".####"],
  E: ["#####", "#....", "####.", "#....", "#####"],
};
function logo(c) {
  const cv = $("#logo"), g = cv.getContext("2d"), word = "SWAYFORGE", px = 4;
  g.clearRect(0, 0, cv.width, cv.height);
  let x = 2;
  for (const ch of word) {
    const gl = PIX[ch];
    for (let yy = 0; yy < 5; yy++) for (let xx = 0; xx < 5; xx++) if (gl[yy][xx] === "#") {
      g.fillStyle = Desk.mix(c.accent, c.crust, .55); g.fillRect(x + xx * px + 2, 6 + yy * px * 1.6 + 2, px, px * 1.6);
      g.fillStyle = c.accent; g.fillRect(x + xx * px, 6 + yy * px * 1.6, px, px * 1.6);
    }
    x += 6 * px - 1;
  }
}

// ── rendering of each page ────────────────────────────────────────────
function railAndHero() {
  const t = theme(), lay = layoutOf(S.s.bar.layout);
  desk($("#rail-desk"), { theme: t, layout: S.s.bar.layout, wallpaperUrl: wallUrl() });
  $("#rail-caption").textContent = `${t.label.split(" (")[0]} with ${lay.label}`;
  if (S.page === "overview") {
    desk($("#hero-desk"), { theme: t, layout: S.s.bar.layout, wallpaperUrl: wallUrl(), notify: true });
    facts();
  }
  if (S.page === "look") desk($("#look-desk"), { theme: t, layout: S.s.bar.layout, wallpaperUrl: wallUrl(), notify: true });
}

function facts() {
  const t = theme(), lay = layoutOf(S.s.bar.layout), w = S.s.theme.wallpaper;
  const saver = S.data.savers[S.s.power.screensaver] || "None";
  const see = Math.round((1 - (S.s.look.ui_opacity ?? 1)) * 100);
  const rows = [
    ["Theme", t.label, "themes"], ["Layout", lay.label, "layouts"],
    ["Wallpaper", w === "theme" || !w ? "The theme's own" : w === "solid" ? "Solid colour" : w.split("/").pop(), "wallpapers"],
    ["Transparency", see ? `${see}% see-through` : "Off", "look"], ["Corners", S.s.look.radius ? `${S.s.look.radius} px round` : "Square", "look"],
    ["Screensaver", saver.split(" (")[0], "saver"],
  ];
  $("#facts").innerHTML = rows.map(([k, v, go]) => `<div><dt>${k}</dt><dd><button data-go="${go}">${esc(v)}</button></dd></div>`).join("");
}

function themeCards() {
  const grid = $("#theme-grid"), list = Object.values(S.themes).filter(t =>
    S.filter === "all" || (S.filter === "dark" && t.dark) || (S.filter === "light" && !t.dark) || (S.filter === "custom" && t.custom));
  grid.replaceChildren();
  if (!list.length) { grid.innerHTML = `<p class="hint">No themes of your own yet. Make one in the classic settings: Theme → Edit colours.</p>`; return; }
  for (const t of list) {
    const card = document.createElement("button");
    card.className = "card"; card.dataset.theme = t.id;
    card.setAttribute("aria-pressed", String(t.id === S.s.theme.name));
    const frame = document.createElement("div"); frame.className = "desk-frame";
    const keys = ["base", "surface", "accent", "accent2", "red", "green", "yellow", "blue", "magenta"];
    card.append(frame);
    card.insertAdjacentHTML("beforeend", `<div class="card-meta"><span class="card-name">${esc(t.label.split(" (")[0])}${t.id === S.s.theme.name ? ` <span class="tick">in use</span>` : ""}</span>
      <span class="swatch">${keys.map(k => `<i style="background:${t.colors[k]}"></i>`).join("")}</span></div>
      <div class="card-desc">${esc((t.label.match(/\((.*)\)/) || [, t.dark ? "dark" : "light"])[1])}</div>`);
    grid.append(card);
    lazy(frame, () => desk(frame, { theme: t, layout: S.s.bar.layout, compact: true,
      wallpaperUrl: S.s.theme.wallpaper === "theme" || !S.s.theme.wallpaper ? wallUrl(t.id) : wallUrl() }));
  }
  accents();
}

function accents() {
  const t = theme(), box = $("#accents");
  const cur = S.s.theme.accent || "";
  box.innerHTML = `<button class="auto" data-accent="" aria-pressed="${cur === ""}" title="The theme's own accent">Theme</button>` +
    S.data.accents.slice(1).map(k => `<button data-accent="${k}" aria-pressed="${cur === k}" title="${k}" aria-label="Accent ${k}" style="background:${t.colors[k]}"></button>`).join("");
}

function layoutCards() {
  const grid = $("#layout-grid");
  grid.replaceChildren();
  for (const l of S.data.layouts) {
    const card = document.createElement("button");
    card.className = "card"; card.dataset.layout = l.id;
    card.setAttribute("aria-pressed", String(l.id === S.s.bar.layout));
    const frame = document.createElement("div"); frame.className = "desk-frame";
    card.append(frame);
    card.insertAdjacentHTML("beforeend", `<div class="card-meta"><span class="card-name">${esc(l.label)}</span>${l.id === S.s.bar.layout ? `<span class="tick">in use</span>` : ""}</div>
      <div class="card-desc">${esc(l.desc)}</div>`);
    grid.append(card);
    lazy(frame, () => desk(frame, { theme: theme(), layout: l.id, wallpaperUrl: wallUrl(), compact: true }));
  }
}

// render previews only when they scroll into view
const lazyIO = new IntersectionObserver(es => es.forEach(e => {
  if (e.isIntersecting && e.target._draw) { const f = e.target._draw; e.target._draw = null; lazyIO.unobserve(e.target); f(); }
}), { rootMargin: "300px" });
function lazy(frame, draw) { frame._draw = draw; lazyIO.observe(frame); }

async function wallCards() {
  const grid = $("#wall-grid");
  let d;
  try { d = await api.get("wallpapers", { page: S.wallPage, q: S.wallQ }); }
  catch (e) { grid.innerHTML = `<p class="hint">Could not read your wallpapers: ${esc(e.message)}</p>`; return; }
  S.wallPage = d.page;
  $("#wall-page").textContent = `${d.page + 1} / ${d.pages}`;
  $("#wall-prev").disabled = d.page <= 0; $("#wall-next").disabled = d.page + 1 >= d.pages;
  const cur = S.s.theme.wallpaper;
  const special = d.page === 0 && !S.wallQ ? [
    { path: "theme", name: "The theme's own", html: `<img src="/api/themewall?id=${encodeURIComponent(S.s.theme.name)}&t=${TOKEN}" alt="">` },
    { path: "solid", name: "Solid colour", html: `<div class="special" style="background:${theme().colors.base}">plain ${theme().colors.base}</div>` },
  ] : [];
  grid.replaceChildren();
  for (const it of special) {
    grid.insertAdjacentHTML("beforeend", `<button class="card" data-wall="${esc(it.path)}" aria-pressed="${cur === it.path || (!cur && it.path === "theme")}">
      <div class="wall">${it.html}</div><div class="card-meta"><span class="card-name">${esc(it.name)}</span></div></button>`);
  }
  for (const it of d.items) {
    grid.insertAdjacentHTML("beforeend", `<button class="card" data-wall="${esc(it.path)}" aria-pressed="${cur === it.path}">
      <div class="wall"><img loading="lazy" decoding="async" src="/api/thumb?p=${encodeURIComponent(it.path)}&t=${TOKEN}" alt="">${it.video ? '<span class="badge">▶ video</span>' : ""}</div>
      <div class="card-meta"><span class="card-name" style="font-weight:500;font-size:12.5px">${esc(it.name)}</span></div>
      ${it.folder ? `<div class="card-desc">${esc(it.folder)}</div>` : ""}</button>`);
  }
  $("#wall-hint").textContent = d.total ? `${d.total} pictures and videos in ${d.folder}` :
    `Your wallpaper folder is empty. Put pictures or videos into ${d.folder}, or download collections in the classic settings (Wallpapers).`;
}

// ── Look & feel controls ──────────────────────────────────────────────
const LOOK = [
  ["Bar, launcher and notifications"],
  ["look.ui_opacity", "Transparency", "range", { min: 0, max: 80, step: 10, view: v => 100 - Math.round(v * 100), back: v => (100 - v) / 100, fmt: v => v ? `${v}%` : "Off" },
    "How see-through they are. Blur and shadows switch off while it is on, so the wallpaper shows."],
  ["Windows"],
  ["look.radius", "Corner radius", "range", { min: 0, max: 20, step: 1, fmt: v => v ? `${v} px` : "Square" }, "Rounded windows need SwayFX."],
  ["look.gaps_inner", "Gaps between windows", "range", { min: 0, max: 30, step: 1, fmt: v => `${v} px` }],
  ["look.gaps_outer", "Gaps at the screen edge", "range", { min: 0, max: 30, step: 1, fmt: v => `${v} px` }],
  ["look.border", "Border width", "range", { min: 0, max: 6, step: 1, fmt: v => `${v} px` }],
  ["look.title_bars", "Title bars", "switch"],
  ["look.smart_gaps", "No gaps with a single window", "switch"],
  ["Effects (SwayFX)"],
  ["look.fx_shadows", "Window shadows", "switch"],
  ["look.fx_blur", "Blur behind see-through windows", "switch"],
  ["look.fx_dim_inactive", "Dim inactive windows", "range", { min: 0, max: 0.5, step: 0.05, fmt: v => v ? `${Math.round(v * 100)}%` : "Off" }],
  ["Terminal"],
  ["look.terminal_opacity", "Terminal opacity", "range", { min: 0.5, max: 1, step: 0.05, fmt: v => `${Math.round(v * 100)}%` }],
  ["theme.font_size", "Font size", "range", { min: 9, max: 16, step: 1, fmt: v => `${v} pt` }],
];
const SAVER_FORM = [
  ["When it starts"],
  ["power.lock_after", "Start the screensaver after", "range", { min: 0, max: 60, step: 1, fmt: v => v ? `${v} min` : "Never" }],
  ["power.screen_off_after", "Screen off after", "range", { min: 0, max: 120, step: 5, fmt: v => v ? `${v} min` : "Never" },
    "Keep this longer than the screensaver time, or the screen goes dark first."],
  ["power.inhibit_fullscreen", "Not while a game or video is fullscreen", "switch"],
];
const get = path => path.split(".").reduce((o, k) => (o || {})[k], S.s);

function buildForm(form, spec) {
  form.replaceChildren();
  for (const [path, label, kind, o = {}, help] of spec) {
    if (!label) { form.insertAdjacentHTML("beforeend", `<h2>${esc(path)}</h2>`); continue; }
    const id = "f-" + path.replace(/\./g, "-");
    const row = document.createElement("div"); row.className = "row";
    const v = get(path);
    if (kind === "switch") {
      row.innerHTML = `<label for="${id}">${esc(label)}</label><input id="${id}" class="switch" type="checkbox" role="switch" ${v ? "checked" : ""}>`;
      $("input", row).addEventListener("change", e => change(path, e.target.checked));
    } else {
      const shown = o.view ? o.view(v) : v;
      row.innerHTML = `<label for="${id}">${esc(label)}</label><output for="${id}">${esc(o.fmt ? o.fmt(shown) : shown)}</output>
        <input id="${id}" type="range" min="${o.min}" max="${o.max}" step="${o.step}" value="${shown}">`;
      const inp = $("input", row), out = $("output", row);
      inp.addEventListener("input", () => {
        const raw = Number(inp.value);
        out.textContent = o.fmt ? o.fmt(raw) : raw;
        change(path, o.back ? o.back(raw) : raw);
      });
    }
    if (help) row.insertAdjacentHTML("beforeend", `<small>${esc(help)}</small>`);
    if (path.startsWith("look.fx_") && !S.data.swayfx) row.insertAdjacentHTML("beforeend", `<small>SwayFX is not installed – no effect yet.</small>`);
    form.append(row);
  }
}

function saverCards() {
  const grid = $("#saver-grid"), c = Desk.colours(theme(), S.s.theme.accent);
  grid.replaceChildren();
  for (const [id, label] of Object.entries(S.data.savers)) {
    const card = document.createElement("button");
    card.className = "card"; card.dataset.saver = id;
    card.setAttribute("aria-pressed", String(id === S.s.power.screensaver));
    card.innerHTML = `<div class="saver"><canvas width="320" height="200"></canvas></div>
      <div class="card-meta"><span class="card-name">${esc(label.split(" (")[0])}</span>${id === S.s.power.screensaver ? `<span class="tick">chosen</span>` : ""}</div>
      ${label.includes("(") ? `<div class="card-desc">${esc(label.match(/\((.*)\)/)[1])}</div>` : ""}`;
    grid.append(card);
    Savers.attach($("canvas", card), id, c);
  }
  buildForm($("#saver-form"), SAVER_FORM);
  $("#saver-form").insertAdjacentHTML("beforeend", `<div class="row"><span>See it full screen in a terminal window</span><button type="button" class="btn" id="saver-preview">Preview</button></div>`);
}

const MORE = [
  ["display", "Displays", "Resolution, refresh rate, scaling, FreeSync"], ["audio", "Audio", "Output, input, volume per device"],
  ["bluetooth", "Bluetooth", "Pair and connect devices"], ["network", "Network", "Wi-Fi, VPN, hotspot"],
  ["input", "Keyboard & mouse", "Layout, repeat rate, touchpad"], ["keys", "Apps & shortcuts", "Every key binding, default apps"],
  ["bar", "Bar modules", "Which buttons the bar shows"], ["shell", "Terminal & prompt", "kitty or Alacritty, prompt sections"],
  ["games", "Games", "CS2 chat translator, Steam shader cache"], ["power", "Power & lock", "Suspend, lock screen, night light"],
  ["boot", "Boot & login", "Boot screen and login screen"], ["security", "Security", "Firewall, malware scan, updates"],
  ["apps", "Apps", "Install and remove programs"], ["cleanup", "Cleanup & drives", "Caches, old kernels, wipe a stick"],
  ["system", "System & files", "Backups, import, update the system"], ["about", "About & updates", "Version, update swayforge"],
];
function morePage() {
  $("#more").innerHTML = MORE.map(([id, t, d]) => `<button data-classic="${id}"><b>${esc(t)}</b><span>${esc(d)}</span></button>`).join("") +
    `<button data-classic=""><b>Classic settings</b><span>The full terminal app, all pages</span></button>`;
}

// ── state changes ─────────────────────────────────────────────────────
let redrawPending = false;
function redraw(all = false) {
  if (redrawPending) return;
  redrawPending = true;
  requestAnimationFrame(() => {
    redrawPending = false;
    skin(); railAndHero();
    if (all) renderPage();
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
  path.split(".").reduce((o, k, i, arr) => (i === arr.length - 1 ? (o[k] = value) : o[k]), S.s);
  setDirty(true);
  redraw(path === "power.screensaver");
  sendQueue.set(path, value);
  clearTimeout(sendTimer);
  sendTimer = setTimeout(flush, 180);
}
async function flush() {
  const items = [...sendQueue]; sendQueue.clear();
  for (const [path, value] of items) {
    try { const r = await api.post("set", { path, value }); setDirty(r.dirty); }
    catch (e) { toast(`<b>Not saved:</b> ${esc(e.message)}`, true); }
  }
}

async function pickTheme(id) {
  try {
    const r = await api.post("theme", { id });
    S.s = r.settings; setDirty(r.dirty);
    redraw(true);
    const sw = $(".sweep"); sw.classList.remove("go"); void sw.offsetWidth; sw.classList.add("go");
    if (r.changed && r.changed.length) toast(`<b>${esc(S.themes[id].label.split(" (")[0])}</b> brings its own ${r.changed.map(esc).join(", ")}. Your values come back when you switch away.`);
  } catch (e) { toast(esc(e.message), true); }
}

async function apply() {
  S.applying = true; setDirty(S.dirty);
  $("#apply").classList.add("busy");
  try {
    await flush();
    await api.post("apply");
    for (;;) {
      await new Promise(r => setTimeout(r, 600));
      const st = await api.get("status");
      if (!st.applying) {
        const res = st.result || {};
        if (res.ok) toast(`<b>Applied</b> in ${res.seconds}s. ${res.notes && res.notes.length ? esc(res.notes.slice(0, 3).join(" · ")) : ""}`);
        else toast(`<b>Apply failed:</b> ${esc((res.errors || ["unknown error"]).join(" "))}`, true);
        S.applying = false; setDirty(st.dirty);
        break;
      }
    }
  } catch (e) { S.applying = false; setDirty(true); toast(`<b>Apply failed:</b> ${esc(e.message)}`, true); }
  $("#apply").classList.remove("busy");
}

// ── navigation ────────────────────────────────────────────────────────
const TITLES = { overview: "Overview", themes: "Themes", layouts: "Layouts", wallpapers: "Wallpapers", look: "Look & feel", saver: "Screensaver", more: "Everything else" };
function go(page) {
  S.page = page; document.body.dataset.page = page;
  $$(".page").forEach(p => (p.hidden = p.id !== "page-" + page));
  $$(".nav button").forEach(b => { if (b.dataset.go === page) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current"); });
  $("#title").textContent = TITLES[page];
  try { localStorage.setItem("studio-page", page); } catch (_) { /* private mode */ }
  renderPage(); railAndHero();
  $("main").scrollTop = 0;
}
function renderPage() {
  if (S.page === "themes") themeCards();
  else if (S.page === "layouts") layoutCards();
  else if (S.page === "wallpapers") wallCards();
  else if (S.page === "look") buildForm($("#look-form"), LOOK);
  else if (S.page === "saver") saverCards();
  else if (S.page === "more") morePage();
}

document.addEventListener("click", e => {
  const b = e.target.closest("button");
  if (!b) return;
  if (b.dataset.go) return go(b.dataset.go);
  if (b.dataset.filter) { S.filter = b.dataset.filter; $$("[data-filter]").forEach(x => x.setAttribute("aria-pressed", String(x === b))); return themeCards(); }
  if (b.dataset.theme) return pickTheme(b.dataset.theme);
  if (b.dataset.accent !== undefined) { change("theme.accent", b.dataset.accent); return renderPage(); }
  if (b.dataset.layout) { change("bar.layout", b.dataset.layout); return layoutCards(); }
  if (b.dataset.wall) { change("theme.wallpaper", b.dataset.wall); $$("[data-wall]").forEach(x => x.setAttribute("aria-pressed", String(x === b))); return; }
  if (b.dataset.saver) { change("power.screensaver", b.dataset.saver); return; }
  if (b.dataset.classic !== undefined) { api.post("classic", { page: b.dataset.classic }).then(() => toast("Opening the classic settings …")).catch(err => toast(esc(err.message), true)); return; }
  if (b.id === "saver-preview") { const n = S.s.power.screensaver === "off" ? "matrix" : S.s.power.screensaver; api.post("preview-saver", { name: n }); return; }
  if (b.id === "apply") return apply();
  if (b.id === "revert") return api.post("revert").then(r => { S.s = r.settings; setDirty(false); redraw(true); toast("Changes undone"); });
  if (b.id === "wall-prev") { S.wallPage--; return wallCards(); }
  if (b.id === "wall-next") { S.wallPage++; return wallCards(); }
  if (b.id === "wall-rescan") { api.get("wallpapers", { rescan: 1 }).then(() => { S.wallPage = 0; wallCards(); }); }
});
let qTimer = 0;
$("#wall-q").addEventListener("input", e => { clearTimeout(qTimer); qTimer = setTimeout(() => { S.wallQ = e.target.value.trim(); S.wallPage = 0; wallCards(); }, 250); });
document.addEventListener("keydown", e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); if (S.dirty && !S.applying) apply(); }
  if (e.altKey && /^[1-7]$/.test(e.key)) go(Object.keys(TITLES)[Number(e.key) - 1]);
});

// heartbeat: the server quits when the window is gone
setInterval(() => api.post("ping").catch(() => {}), 5000);

// ── start ─────────────────────────────────────────────────────────────
(async () => {
  try {
    S.data = await api.get("state");
  } catch (e) {
    document.body.innerHTML = `<p style="padding:40px;font:15px monospace">swayforge Studio could not reach its server (${esc(e.message)}). Start it again with <b>swayforge gui</b>.</p>`;
    return;
  }
  S.s = S.data.settings;
  S.data.themes.forEach(t => (S.themes[t.id] = t));
  setDirty(S.data.dirty);
  skin();
  let start = "overview";
  try { start = localStorage.getItem("studio-page") || start; } catch (_) { /* ignore */ }
  go(TITLES[start] ? start : "overview");
  requestAnimationFrame(() => { const sw = $(".sweep"); if (sw) sw.classList.add("go"); });
})();
