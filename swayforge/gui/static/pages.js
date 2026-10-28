// swayforge app – the pages. Each one builds its view from the staged settings and the server.
"use strict";

// ═══ LOOK ═════════════════════════════════════════════════════════════
Studio.page("overview", {
  title: "Overview", icon: "◧", keywords: "home summary preview",
  render(view) {
    view.append(h(`<div class="hero"><div class="desk-frame big" id="hero-desk"></div><div class="sweep go" aria-hidden="true"></div></div>`));
    view.append(h(`<dl class="facts" id="facts"></dl>`));
    this.live();
  },
  live() {
    const hd = $("#hero-desk"); if (!hd) return;
    desk(hd, { theme: theme(), layout: S.s.bar.layout, wallpaperUrl: wallUrl(null, true), notify: true });
    const t = theme(), lay = layoutOf(S.s.bar.layout), w = S.s.theme.wallpaper;
    const see = Math.round((1 - (S.s.look.ui_opacity ?? 1)) * 100);
    const rows = [
      ["Theme", t.label, "themes"], ["Layout", lay.label, "layouts"],
      ["Wallpaper", w === "theme" || !w ? "The theme's own" : w === "solid" ? "Solid colour" : w.split("/").pop(), "wallpapers"],
      ["Transparency", see ? `${see}% see-through` : "Off", "look"], ["Font", `${S.s.theme.font} ${S.s.theme.font_size}`, "look"],
      ["Screensaver", (S.data.savers[S.s.power.screensaver] || "None").split(" (")[0], "power"],
      ["Terminal", S.s.general.terminal, "shell"], ["Browser", S.s.general.browser, "keys"],
    ];
    $("#facts").innerHTML = rows.map(([k, v, g]) => `<div><dt>${k}</dt><dd><button data-go="${g}">${esc(v)}</button></dd></div>`).join("");
  },
});

Studio.page("themes", {
  title: "Themes", icon: "◐", keywords: "colour color palette accent ascii art editor custom wallpaper",
  filter: "all",
  render(view) {
    const bar = h(`<div class="toolbar">
      <div class="seg" role="group" aria-label="Show">${["all", "dark", "light", "custom"].map(f =>
        `<button data-f="${f}" aria-pressed="${f === this.filter}">${{ all: "All", dark: "Dark", light: "Light", custom: "Yours" }[f]}</button>`).join("")}</div>
      <div class="accents" id="accents" role="group" aria-label="Accent colour"></div>
      <span class="grow"></span></div>`);
    bar.append(button("Edit colours", "", () => this.editor()), button("Theme from wallpaper", "", () => this.fromWall()));
    bar.addEventListener("click", e => { const b = e.target.closest("[data-f]"); if (b) { this.filter = b.dataset.f; go("themes"); } });
    view.append(bar, h(`<div class="grid" id="theme-grid"></div>`));
    const more = section("ASCII art and animation");
    more.append(artRows());
    view.append(more);
    this.cards(); this.accents();
  },
  cards() {
    const grid = $("#theme-grid"), f = this.filter;
    const list = Object.values(S.themes).filter(t => f === "all" || (f === "dark" && t.dark) || (f === "light" && !t.dark) || (f === "custom" && t.custom));
    if (!list.length) { grid.innerHTML = `<p class="hint">No themes of your own yet – “Edit colours” makes one from the current theme.</p>`; return; }
    for (const t of list) {
      const keys = ["base", "surface", "accent", "accent2", "red", "green", "yellow", "blue", "magenta"];
      const on = t.id === S.s.theme.name;
      const card = h(`<button class="card" aria-pressed="${on}"><div class="desk-frame"></div>
        <div class="card-meta"><span class="card-name">${esc(t.label.split(" (")[0])}${on ? ` <span class="tick">in use</span>` : ""}</span>
        <span class="swatch">${keys.map(k => `<i style="background:${t.colors[k]}"></i>`).join("")}</span></div>
        <div class="card-desc">${esc((t.label.match(/\((.*)\)/) || [, t.dark ? "dark" : "light"])[1])}</div></button>`);
      card.addEventListener("click", () => this.pick(t.id));
      grid.append(card);
      const fr = card.querySelector(".desk-frame");
      lazy(fr, () => desk(fr, { theme: t, layout: S.s.bar.layout, compact: true,
        wallpaperUrl: S.s.theme.wallpaper === "theme" || !S.s.theme.wallpaper ? wallUrl(t.id) : wallUrl() }));
    }
  },
  accents() {
    const t = theme(), box = $("#accents"), cur = S.s.theme.accent || "";
    box.innerHTML = `<button class="auto" data-a="" aria-pressed="${cur === ""}" title="The theme's own accent">Theme</button>` +
      S.data.accents.slice(1).map(k => `<button data-a="${k}" aria-pressed="${cur === k}" aria-label="Accent ${k}" title="${k}" style="background:${t.colors[k]}"></button>`).join("");
    box.onclick = e => { const b = e.target.closest("[data-a]"); if (b) { change("theme.accent", b.dataset.a); go("themes"); } };
  },
  async pick(id) {
    try {
      const r = await api.post("theme", { id });
      S.s = r.settings; setDirty(r.dirty); go("themes");
      if (r.changed && r.changed.length) toast(`<b>${esc(S.themes[id].label.split(" (")[0])}</b> brings its own ${r.changed.map(esc).join(", ")}. Your values come back when you switch away.`);
    } catch (e) { toast(esc(e.message), true); }
  },
  async editor() {
    const t = theme(), keys = S.fields.color_keys;
    const res = await dialog(`<h2>Your own theme</h2><p class="lede">Starts from ${esc(t.label)}. Change any colour, name it, save – it then shows up under “Yours”.</p>
      <div class="colgrid">${keys.map(k => `<label><input type="color" data-k="${k}" value="${t.colors[k]}"><span>${esc(S.fields.color_labels[k] || k)}</span><code>${t.colors[k]}</code></label>`).join("")}</div>
      <div class="row"><label for="tname">Name</label><input id="tname" type="text" value="${t.custom ? esc(t.label) : ""}" placeholder="e.g. My Retro"></div>
      <menu><button value="" class="btn ghost">Cancel</button><button value="save" class="btn primary">Save as my theme</button></menu>`,
      b => b.querySelectorAll("input[type=color]").forEach(i => i.addEventListener("input", () => (i.parentElement.querySelector("code").textContent = i.value))));
    if (res !== "save") return;
    const colors = {}; $$("#dlg-body input[type=color]").forEach(i => (colors[i.dataset.k] = i.value));
    const r = await api.act("theme_save", { label: $("#tname").value, colors });
    if (r) { await reloadSettings(); toast(`Theme <b>${esc(r.label)}</b> saved and selected`); go("themes"); }
  },
  async fromWall() {
    const w = S.s.theme.wallpaper;
    if (!w || w === "theme" || w === "solid") { toast("Pick a picture on the Wallpapers page first", true); return; }
    const res = await dialog(`<h2>Theme from your wallpaper</h2><p class="lede">Takes the colours of ${esc(w.split("/").pop())}.</p>
      <menu><button value="" class="btn ghost">Cancel</button><button value="light" class="btn">Light</button><button value="dark" class="btn">Dark</button><button value="auto" class="btn primary">Automatic</button></menu>`);
    if (!res) return;
    const r = await api.act("theme_from_wallpaper", { mode: res });
    if (r) { await reloadSettings(); toast(`${r.dark ? "Dark" : "Light"} theme made – “Edit colours” to name and keep it`); go("themes"); }
  },
});

function artRows() {
  const box = h(`<div class="controls"></div>`);
  const opts = [["Theme's motif", "auto"], ...S.fields.art.map(a => [a, a])];
  box.append(fieldRow({ path: "theme.ascii", label: "ASCII art", kind: "choice", options: opts, help: "fastfetch, login, boot screen · your own: ~/.config/swayforge/ascii" }));
  box.append(fieldRow({ path: "theme.animate", label: "Animate the ASCII art", kind: "bool", help: "the terminal app, the terminal greeting and the LibreWolf start page" }));
  box.append(fieldRow({ path: "theme.motion", label: "How it moves", kind: "choice", options: Object.entries(S.fields.motions).map(([k, v]) => [v, k]) }));
  return box;
}

Studio.page("layouts", {
  title: "Layouts", icon: "▤", keywords: "bar taskbar start menu noctalia shell transparency",
  render(view) {
    view.append(h(`<p class="lede">The layout shapes the bar, start menu, notifications and window frames. It works with every theme.</p>`));
    const grid = h(`<div class="grid"></div>`);
    for (const l of S.data.layouts) {
      const on = l.id === S.s.bar.layout;
      const card = h(`<button class="card" aria-pressed="${on}"><div class="desk-frame"></div>
        <div class="card-meta"><span class="card-name">${esc(l.label)}</span>${on ? `<span class="tick">in use</span>` : ""}</div>
        <div class="card-desc">${esc(l.desc)}</div></button>`);
      card.addEventListener("click", () => { change("bar.layout", l.id); go("layouts"); });
      grid.append(card);
      const fr = card.querySelector(".desk-frame");
      lazy(fr, () => desk(fr, { theme: theme(), layout: l.id, wallpaperUrl: wallUrl(), compact: true }));
    }
    view.append(grid);
    const sh = section("Desktop shell", "Noctalia can take over the bar and notifications. Theme, wallpaper and shortcuts keep working.");
    const noct = S.s.general.shell === "noctalia";
    sh.append(h(`<p>${noct ? "Noctalia runs the bar and notifications; swayforge's bar is off." : "swayforge's own bar and notifications are on."}</p>`));
    sh.append(button(noct ? "Switch back to swayforge's bar" : "Run Noctalia instead", "", async ev => {
      const r = await busy(ev.currentTarget, api.act("shell_toggle", {}, true));
      if (r) { S.s.general.shell = r.shell; await apply(); go("layouts"); }
    }));
    view.append(sh);
  },
});

Studio.page("wallpapers", {
  title: "Wallpapers", icon: "▣", keywords: "background picture video animated live collections download",
  pg: 0, q: "",
  async render(view) {
    const bar = h(`<div class="toolbar"><input id="wall-q" type="search" placeholder="Search your wallpapers" aria-label="Search wallpapers" value="${esc(this.q)}">
      <div class="pager"><button class="btn ghost" id="wp-prev" aria-label="Previous page">‹</button><span id="wp-page"></span><button class="btn ghost" id="wp-next" aria-label="Next page">›</button></div>
      <span class="grow"></span></div>`);
    bar.append(button("Look for new files", "ghost", () => { this.pg = 0; this.load(true); }));
    view.append(bar, h(`<div class="grid walls" id="wall-grid"></div>`), h(`<p class="hint" id="wall-hint"></p>`));
    bar.querySelector("#wall-q").addEventListener("input", e => { clearTimeout(this.t); this.t = setTimeout(() => { this.q = e.target.value.trim(); this.pg = 0; this.load(); }, 250); });
    bar.querySelector("#wp-prev").onclick = () => { this.pg--; this.load(); };
    bar.querySelector("#wp-next").onclick = () => { this.pg++; this.load(); };
    const live = section("Animated wallpapers", "Videos and GIFs in your folder play as wallpaper (mpvpaper). Or make a small loop in your theme colours:");
    const row = h(`<div class="btnrow"></div>`);
    [["aurora", "Make “Aurora”"], ["tide", "Make “Tide”"]].forEach(([st, lab]) => row.append(button(lab, "", async ev => {
      const r = await busy(ev.currentTarget, api.act("live_wallpaper", { style: st }));
      if (r) { await reloadSettings(); this.load(true); railRedraw(); }
    })));
    live.append(row, form("look", { noHeads: true, skip: S.fields.forms.look.filter(f => typeof f !== "string" && !f.path.startsWith("theme.live")).map(f => f.path) }));
    view.append(live);
    const packs = section("Download collections", "Free wallpaper collections from GitHub (not part of swayforge – the pictures belong to their authors).");
    packs.append(h(`<div id="packs" class="hint">Loading the list …</div>`));
    view.append(packs);
    this.load(); this.packs();
  },
  async load(rescan) {
    const grid = $("#wall-grid"); if (!grid) return;
    let d;
    try { d = await api.get("wallpapers", Object.assign({ page: this.pg, q: this.q }, rescan ? { rescan: 1 } : {})); }
    catch (e) { grid.innerHTML = `<p class="hint">Could not read your wallpapers: ${esc(e.message)}</p>`; return; }
    this.pg = d.page;
    $("#wp-page").textContent = `${d.page + 1} / ${d.pages}`;
    $("#wp-prev").disabled = d.page <= 0; $("#wp-next").disabled = d.page + 1 >= d.pages;
    const cur = S.s.theme.wallpaper;
    grid.replaceChildren();
    const add = (path, inner, name, sub) => {
      const c = h(`<button class="card" aria-pressed="${cur === path || (!cur && path === "theme")}"><div class="wall">${inner}</div>
        <div class="card-meta"><span class="card-name small">${esc(name)}</span></div>${sub ? `<div class="card-desc">${esc(sub)}</div>` : ""}</button>`);
      c.addEventListener("click", () => { change("theme.wallpaper", path); $$("#wall-grid .card").forEach(x => x.setAttribute("aria-pressed", String(x === c))); });
      grid.append(c);
    };
    if (d.page === 0 && !this.q) {
      add("theme", `<img src="/api/themewall?id=${encodeURIComponent(S.s.theme.name)}&t=${TOKEN}" alt="">`, "The theme's own");
      add("solid", `<div class="special" style="background:${theme().colors.base}">plain ${theme().colors.base}</div>`, "Solid colour");
    }
    for (const it of d.items) add(it.path, `<img loading="lazy" decoding="async" src="/api/thumb?p=${encodeURIComponent(it.path)}&t=${TOKEN}" alt="">${it.video ? '<span class="badge">▶ video</span>' : ""}`, it.name, it.folder);
    $("#wall-hint").textContent = d.total ? `${d.total} pictures and videos in ${d.folder}` :
      `Your wallpaper folder is empty. Put pictures or videos into ${d.folder}, or download a collection below.`;
  },
  async packs() {
    let d; try { d = await api.get("wallpacks"); } catch (e) { $("#packs").textContent = e.message; return; }
    const box = $("#packs"); if (!box) return;
    box.className = "packs"; box.replaceChildren();
    for (const p of d.packs) {
      const blk = h(`<div class="pack"><b>${esc(p.name)}</b> <span class="hint">${esc(p.blurb)} · ${esc(p.license)}</span><div class="chips"></div></div>`);
      for (const c of p.categories) blk.querySelector(".chips").append(h(`<label class="chip"><input type="checkbox" value="${esc(c.key)}" ${c.installed ? "disabled checked" : ""}>${esc(c.id)} <small>${c.files} · ${c.mb} MB${c.installed ? " · have it" : ""}</small></label>`));
      box.append(blk);
    }
    box.append(button("Download ticked", "primary", async () => {
      const keys = $$("#packs input:checked:not(:disabled)").map(i => i.value);
      await api.act("wallpacks", { keys });
    }));
  },
});

Studio.page("look", {
  title: "Look & feel", icon: "◇", keywords: "transparency radius corners gaps border font icons cursor blur shadow dim tiling title bars",
  render(view) {
    const split = h(`<div class="split"><div class="col"></div><div class="sticky"><div class="desk-frame big" id="look-desk"></div></div></div>`);
    const col = split.querySelector(".col");
    col.append(h(`<h2 class="block-title">Bar, launcher and notifications</h2>`));
    col.append(sliderRow("look.ui_opacity", "Transparency", { min: 0, max: 80, step: 10, view: v => 100 - Math.round(v * 100), back: v => (100 - v) / 100, fmt: v => v ? `${v}% see-through` : "Off" },
      "Blur and shadows switch off while it is on, so the wallpaper shows."));
    col.append(h(`<h2 class="block-title">Windows</h2>`));
    col.append(sliderRow("look.radius", "Corner radius", { min: 0, max: 20, step: 1, fmt: v => v ? `${v} px` : "Square" }, "Rounded windows need SwayFX."));
    col.append(sliderRow("look.gaps_inner", "Gaps between windows", { min: 0, max: 30, step: 1, fmt: v => `${v} px` }));
    col.append(sliderRow("look.gaps_outer", "Gaps at the screen edge", { min: 0, max: 30, step: 1, fmt: v => `${v} px` }));
    col.append(sliderRow("look.border", "Border width", { min: 0, max: 6, step: 1, fmt: v => v ? `${v} px` : "None" }));
    col.append(sliderRow("look.fx_dim_inactive", "Dim inactive windows", { min: 0, max: 0.5, step: 0.05, fmt: v => v ? `${Math.round(v * 100)}%` : "Off" }, S.data.swayfx ? "" : "Needs SwayFX."));
    const rest = form("look", { skip: ["look.gaps_inner", "look.gaps_outer", "look.border", "look.radius", "look.fx_dim_inactive",
      "theme.live_pause_fullscreen", "theme.live_pause_battery", "theme.live_fps"] });
    [...rest.querySelectorAll("h2")].forEach(x => { if (/^Animated/.test(x.textContent)) x.remove(); });
    col.append(rest);
    view.append(split);
    this.live();
  },
  live() { const d = $("#look-desk"); if (d) desk(d, { theme: theme(), layout: S.s.bar.layout, wallpaperUrl: wallUrl(null, true), notify: true }); },
});

function sliderRow(path, label, o, help) {
  const id = "f-" + path.replace(/\./g, "-"), v = get(path), shown = o.view ? o.view(v) : v;
  const row = h(`<div class="row" data-path="${path}"><label for="${id}">${esc(label)}</label><output for="${id}">${esc(o.fmt ? o.fmt(shown) : shown)}</output>
    <input id="${id}" type="range" min="${o.min}" max="${o.max}" step="${o.step}" value="${shown}"></div>`);
  const inp = row.querySelector("input"), out = row.querySelector("output");
  inp.addEventListener("input", () => { const raw = Number(inp.value); out.textContent = o.fmt ? o.fmt(raw) : raw; change(path, o.back ? o.back(raw) : raw); });
  if (help) row.append(h(`<small>${esc(help)}</small>`));
  return row;
}

Studio.page("bar", {
  title: "Bar modules", icon: "▭", keywords: "waybar clock date cpu memory network bluetooth battery tray",
  render(view) {
    view.append(h(`<p class="lede">What the bar shows. The look of the bar comes from the layout.</p>`), form("bar"));
  },
});

// ═══ DEVICES ══════════════════════════════════════════════════════════
Studio.page("display", {
  title: "Displays", icon: "▢", keywords: "monitor screen resolution refresh rate hz scale position freesync vrr tearing",
  async render(view) {
    loading(view, "Asking Sway for your screens …");
    const d = await api.get("page", { id: "display" });
    view.replaceChildren();
    const g = section("Games");
    g.append(fieldRow({ path: "display.allow_tearing", label: "Allow tearing in games", kind: "bool", help: "lower input lag in fullscreen games" }));
    if (!d.outputs.length) {
      view.append(h(`<p class="hint">Screens can only be read inside Sway. Start the app from your Sway desktop.</p>`), g);
      return;
    }
    const outs = d.outputs.map(o => Object.assign({}, o));
    // arrangement picture
    const arr = h(`<div class="arrange" aria-label="Screen arrangement"></div>`);
    const draw = () => {
      arr.replaceChildren();
      const rects = outs.filter(o => o.enabled).map(o => {
        const [w, hh] = (o.mode || "1920x1080").split("@")[0].split("x").map(Number);
        const [x, y] = (o.pos || "0 0").split(" ").map(Number);
        return { o, x, y, w: w / (o.scale || 1), h: hh / (o.scale || 1) };
      });
      const maxX = Math.max(...rects.map(r => r.x + r.w), 1), maxY = Math.max(...rects.map(r => r.y + r.h), 1);
      const k = Math.min(560 / maxX, 180 / maxY);
      rects.forEach(r => arr.append(h(`<div class="mon ${r.o.key === prim.value ? "main" : ""}" style="left:${r.x * k}px;top:${r.y * k}px;width:${r.w * k}px;height:${r.h * k}px">
        <b>${esc(r.o.name)}</b><small>${esc((r.o.mode || "").replace(/^(\d+)x(\d+)@([\d.]+)Hz$/, (m, w, hh, hz) => `${w}×${hh} @ ${Math.round(hz)} Hz`))}</small></div>`)));
      arr.style.height = (maxY * k + 4) + "px";
    };
    const scr = section("Screens", "Position is x y in pixels: right of a 2560 px wide screen is “2560 0”. With scaling, use the scaled width.");
    const prim = h(`<select id="f-primary">${outs.map(o => `<option value="${esc(o.key)}" ${o.key === d.primary ? "selected" : ""}>${esc(o.name)} – ${esc(o.make)} ${esc(o.model)}</option>`).join("")}</select>`);
    const pr = h(`<div class="row"><label for="f-primary">Main screen</label></div>`); pr.append(prim, h(`<small>workspace 1 opens here; games (XWayland) use it as the primary monitor</small>`));
    scr.append(arr, pr);
    const save = () => { draw(); api.act("outputs", { outputs: outs, primary: prim.value }, true).then(railRedraw); };
    prim.addEventListener("change", save);
    for (const o of outs) {
      const box = h(`<div class="card-plain"><h3>${esc(o.name)} <span class="hint">${esc(o.make)} ${esc(o.model)}</span></h3></div>`);
      const en = h(`<div class="row"><label>Enabled</label><input type="checkbox" class="switch" ${o.enabled ? "checked" : ""}></div>`);
      en.querySelector("input").onchange = e => { o.enabled = e.target.checked; save(); };
      const md = h(`<div class="row"><label>Resolution & refresh rate</label><select>${o.modes.map(([lab, v]) => `<option value="${esc(v)}" ${v === o.mode ? "selected" : ""}>${esc(lab)}</option>`).join("")}</select></div>`);
      md.querySelector("select").onchange = e => { o.mode = e.target.value; save(); };
      const sc = h(`<div class="row"><label>Scale</label><select>${[1, 1.25, 1.5, 1.75, 2].concat([o.scale]).filter((v, i, a) => a.indexOf(v) === i).sort().map(v => `<option ${Number(v) === Number(o.scale) ? "selected" : ""}>${v}</option>`).join("")}</select></div>`);
      sc.querySelector("select").onchange = e => { o.scale = Number(e.target.value); save(); };
      const ps = h(`<div class="row"><label>Position (x y)</label><input type="text" value="${esc(o.pos)}" spellcheck="false"></div>`);
      ps.querySelector("input").oninput = e => { if (/^-?\d+ -?\d+$/.test(e.target.value.trim())) { o.pos = e.target.value.trim(); save(); } };
      const vr = h(`<div class="row"><label>FreeSync / adaptive sync</label><input type="checkbox" class="switch" ${o.adaptive_sync ? "checked" : ""}></div>`);
      vr.querySelector("input").onchange = e => { o.adaptive_sync = e.target.checked; save(); };
      box.append(en, md, sc, ps, vr);
      scr.append(box);
    }
    view.append(scr, g);
    draw();
  },
});

Studio.page("audio", {
  title: "Audio", icon: "♪", keywords: "sound volume speaker headphones microphone mute output input",
  async render(view) {
    loading(view);
    const d = await api.get("page", { id: "audio" });
    view.replaceChildren();
    if (!d.have) view.append(h(`<p class="hint">pactl is missing – the installer sets up PipeWire.</p>`));
    for (const [kind, title] of [["sink", "Output – speakers and headphones"], ["source", "Input – microphone"]]) {
      const x = d[kind], sec = section(title);
      const dev = h(`<div class="row"><label>Device</label><select>${x.devices.map(v => `<option value="${esc(v.name)}" ${v.name === x.default ? "selected" : ""}>${esc(v.label)}</option>`).join("")}</select></div>`);
      dev.querySelector("select").onchange = e => api.act("audio", { kind, verb: "default", value: e.target.value }, true);
      const vol = sliderLike(`Volume`, x.volume, 0, 150, v => api.act("audio", { kind, verb: "volume", value: v }, true), v => `${v}%`);
      const mute = h(`<div class="row"><label>Muted</label><input type="checkbox" class="switch" ${x.mute ? "checked" : ""}></div>`);
      mute.querySelector("input").onchange = e => api.act("audio", { kind, verb: "mute", value: e.target.checked }, true);
      sec.append(dev, vol, mute);
      view.append(sec);
    }
    const r = h(`<div class="btnrow"></div>`);
    r.append(button("Look again", "ghost", () => go("audio")), button("Advanced mixer (pavucontrol)", "", () => api.act("audio", { kind: "sink", verb: "pavucontrol" }, true)));
    view.append(r, h(`<p class="hint">In the bar: scroll on the speaker for volume, right-click to mute.</p>`));
  },
});

function sliderLike(label, value, min, max, onset, fmt) {
  const row = h(`<div class="row"><label>${esc(label)}</label><output>${fmt(value)}</output><input type="range" min="${min}" max="${max}" step="1" value="${value}"></div>`);
  const inp = row.querySelector("input"), out = row.querySelector("output");
  let t = 0;
  inp.addEventListener("input", () => { out.textContent = fmt(Number(inp.value)); clearTimeout(t); t = setTimeout(() => onset(Number(inp.value)), 120); });
  return row;
}

Studio.page("sound", {
  title: "System sounds", icon: "♫", keywords: "chime notification bell sound pack",
  render(view) {
    view.append(form("sound"));
    const r = h(`<div class="btnrow"></div>`);
    r.append(button("Play all sounds", "", () => api.act("sound_test", {}, true)));
    for (const ev of ["desktop-login", "message-new-instant", "dialog-error"]) r.append(button(ev.replace(/-/g, " "), "ghost", () => api.act("sound_test", { event: ev }, true)));
    view.append(h(`<p class="hint">The sounds use the pack and volume that are applied – apply first to hear changes.</p>`), r);
  },
});

Studio.page("bluetooth", {
  title: "Bluetooth", icon: "ᛒ", keywords: "headphones controller pair connect devices",
  async render(view) {
    loading(view);
    const d = await api.get("page", { id: "bluetooth" });
    view.replaceChildren();
    if (!d.have) { view.append(h(`<p class="hint">bluetoothctl is missing – the installer sets up Bluetooth.</p>`)); return; }
    const pw = h(`<div class="row"><label>Bluetooth on</label><input type="checkbox" class="switch" ${d.powered ? "checked" : ""}></div>`);
    pw.querySelector("input").onchange = e => api.act("bluetooth", { verb: "power", on: e.target.checked }).then(() => go("bluetooth"));
    view.append(pw);
    const list = h(`<div class="list"></div>`);
    if (!d.devices.length) list.append(h(`<p class="hint">No devices yet. Put the device into pairing mode, then “Scan”.</p>`));
    for (const x of d.devices) {
      const row = h(`<div class="item"><span class="dot ${x.connected ? "on" : ""}"></span><div class="grow"><b>${esc(x.name)}</b><small>${x.connected ? "connected" : x.paired ? "paired" : "new"} · ${esc(x.mac)}</small></div></div>`);
      const act = (verb, lab, cls) => row.append(button(lab, cls, async ev => { await busy(ev.currentTarget, api.act("bluetooth", { verb, mac: x.mac })); go("bluetooth"); }));
      if (x.connected) act("disconnect", "Disconnect", "ghost");
      else if (x.paired) act("connect", "Connect", "primary");
      else act("pair", "Pair & connect", "primary");
      act("remove", "Remove", "ghost");
      list.append(row);
    }
    const r = h(`<div class="btnrow"></div>`);
    r.append(button("Scan (10 s)", "primary", async ev => { await busy(ev.currentTarget, api.act("bluetooth", { verb: "scan" })); go("bluetooth"); }),
      button("Blueman", "ghost", () => api.act("bluetooth", { verb: "blueman" }, true)));
    view.append(section("Devices"), list, r);
  },
});

Studio.page("network", {
  title: "Network & VPN", icon: "⌁", keywords: "wifi wlan ethernet vpn wireguard openvpn tailscale hotspot",
  async render(view, rescan) {
    loading(view, "Looking for networks …");
    const d = await api.get("page", Object.assign({ id: "network" }, rescan ? { rescan: 1 } : {}));
    view.replaceChildren();
    if (!d.have) { view.append(h(`<p class="hint">NetworkManager (nmcli) is missing.</p>`)); return; }
    const now = section("Connected");
    now.append(d.active.length ? h(`<div class="list">${d.active.map(a => `<div class="item"><span class="dot on"></span><div class="grow"><b>${esc(a.name)}</b><small>${esc(a.type)} · ${esc(a.device)} · ${esc(a.ip || "–")}</small></div></div>`).join("")}</div>`) : h(`<p class="hint">Not connected.</p>`));
    view.append(now);
    const wifi = section("Wi-Fi");
    const sw = h(`<div class="row"><label>Wi-Fi on</label><input type="checkbox" class="switch" ${d.wifi ? "checked" : ""}></div>`);
    sw.querySelector("input").onchange = e => api.act("network", { verb: "wifi", on: e.target.checked }, true).then(() => go("network"));
    wifi.append(sw);
    const list = h(`<div class="list"></div>`);
    for (const n of d.networks) {
      const bars = "▂▄▆█".slice(0, Math.max(1, Math.min(4, Math.floor(n.signal / 25) + 1)));
      const row = h(`<div class="item"><span class="dot ${n.inuse ? "on" : ""}"></span><div class="grow"><b>${esc(n.ssid)}</b><small>${bars} ${n.signal}% ${n.secure ? "· secured" : "· open"}</small></div></div>`);
      if (!n.inuse) row.append(button("Connect", "", async ev => {
        let password = "";
        if (n.secure) {
          const res = await dialog(`<h2>${esc(n.ssid)}</h2><div class="row"><label for="wpw">Password</label><input id="wpw" type="password" autocomplete="off"></div><p class="hint">Not needed for networks you joined before.</p>
            <menu><button value="" class="btn ghost">Cancel</button><button value="go" class="btn primary">Connect</button></menu>`, b => setTimeout(() => b.querySelector("#wpw").focus(), 50));
          if (res !== "go") return;
          password = $("#wpw").value;
        }
        await busy(ev.currentTarget, api.act("network", { verb: "connect", ssid: n.ssid, password }));
        go("network");
      }));
      list.append(row);
    }
    wifi.append(list);
    const r = h(`<div class="btnrow"></div>`);
    r.append(button("Scan again", "primary", () => PAGES.network.render($("#view"), true)), button("Disconnect Wi-Fi", "ghost", () => api.act("network", { verb: "disconnect" }).then(() => go("network"))),
      button("nmtui", "ghost", () => api.act("network", { verb: "nmtui" }, true)), button("Connection editor", "ghost", () => api.act("network", { verb: "editor" }, true)));
    wifi.append(r, h(`<p class="hint">Ethernet, static IP and hotspots: nmtui or the connection editor.</p>`));
    view.append(wifi);
    const vpn = section("VPN", "Import the file from your VPN provider (OpenVPN .ovpn or WireGuard .conf), then connect with one click. Passwords are never stored by swayforge.");
    const vl = h(`<div class="list"></div>`);
    if (!d.vpns.length) vl.append(h(`<p class="hint">No VPN yet.</p>`));
    for (const v of d.vpns) {
      const row = h(`<div class="item"><span class="dot ${v.active ? "on" : ""}"></span><div class="grow"><b>${esc(v.name)}</b><small>${esc(v.kind)}${v.auto ? " · connects by itself" : ""}</small></div></div>`);
      const a = (verb, lab, cls) => row.append(button(lab, cls, async ev => { await busy(ev.currentTarget, api.act("network", { verb, uuid: v.uuid })); go("network"); }));
      a(v.active ? "vpn_down" : "vpn_up", v.active ? "Disconnect" : "Connect", v.active ? "ghost" : "primary");
      a("vpn_auto", v.auto ? "Auto off" : "Auto on", "ghost");
      row.append(button("Delete", "ghost", async () => { if (await dialog(`<h2>Delete ${esc(v.name)}?</h2><menu><button value="" class="btn ghost">Keep</button><button value="del" class="btn primary">Delete</button></menu>`) === "del") { await api.act("network", { verb: "vpn_del", uuid: v.uuid }); go("network"); } }));
      vl.append(row);
    }
    const imp = h(`<div class="importrow"><select id="vpn-found"><option value="">Config files found …</option>${d.found.map(f => `<option>${esc(f)}</option>`).join("")}</select>
      <input id="vpn-path" type="text" placeholder="or the path to a .ovpn / .conf file" spellcheck="false"><input id="vpn-user" type="text" placeholder="user name (OpenVPN, optional)"></div>`);
    imp.querySelector("#vpn-found").onchange = e => (imp.querySelector("#vpn-path").value = e.target.value);
    imp.append(button("Import", "primary", async () => { await api.act("network", { verb: "vpn_import", path: $("#vpn-path").value, user: $("#vpn-user").value }); go("network"); }));
    vpn.append(vl, imp);
    if (d.tailscale) {
      const ts = h(`<div class="btnrow"><span class="hint">Tailscale:</span></div>`);
      [["ts_up", "Up"], ["ts_down", "Down"], ["ts_status", "Status"]].forEach(([v, l]) => ts.append(button(l, "ghost", () => api.act("network", { verb: v }, true))));
      vpn.append(ts);
    }
    view.append(vpn);
  },
});

Studio.page("input", {
  title: "Keyboard & mouse", icon: "⌨", keywords: "keyboard layout swiss german repeat mouse speed acceleration touchpad tap natural scrolling",
  render(view) { view.append(form("input")); },
});

// ═══ WORK & PLAY ══════════════════════════════════════════════════════
Studio.page("shell", {
  title: "Terminal & prompt", icon: "❯", keywords: "kitty alacritty zsh spaceship prompt fastfetch aliases",
  render(view) {
    view.append(form("shell"));
    const sec = section("Prompt sections", "What the prompt shows (the order is fixed).");
    const chips = h(`<div class="chips"></div>`);
    const cur = new Set(S.s.prompt.sections);
    for (const x of S.fields.prompt_sections) {
      const c = h(`<label class="chip"><input type="checkbox" value="${esc(x)}" ${cur.has(x) ? "checked" : ""}>${esc(x)}</label>`);
      c.querySelector("input").onchange = () => {
        const chosen = $$(".chips input:checked", sec).map(i => i.value);
        S.s.prompt.sections = chosen; api.act("sections", { sections: chosen }, true);
      };
      chips.append(c);
    }
    sec.append(chips);
    view.append(sec);
  },
});

Studio.page("keys", {
  title: "Apps & shortcuts", icon: "⌘", keywords: "shortcut keybinding hotkey super browser file manager editor autostart startup",
  render(view) {
    view.append(form("keys"));
    const sec = section("Shortcuts", "$mod is your main key (Super). Empty = shortcut off. Your own extra shortcuts go into ~/.config/sway/custom.conf.");
    const over = S.s.keys || {};
    const tbl = h(`<div class="keys"></div>`);
    const collect = () => { const k = {}; $$("input[data-key]", tbl).forEach(i => (k[i.dataset.key] = i.value)); S.s.keys = k; api.act("keys", { keys: k }, true); };
    for (const k of S.fields.keys) {
      const row = h(`<label class="keyrow"><span>${esc(k.label)}</span><input data-key="${k.id}" type="text" spellcheck="false" value="${esc(over[k.id] ?? k.default)}"></label>`);
      let t = 0; row.querySelector("input").addEventListener("input", () => { clearTimeout(t); t = setTimeout(collect, 400); });
      tbl.append(row);
    }
    const reset = button("Reset all shortcuts", "ghost", () => { $$("input[data-key]", tbl).forEach(i => (i.value = S.fields.keys.find(k => k.id === i.dataset.key).default)); collect(); });
    sec.append(h(`<input type="search" placeholder="Filter shortcuts" class="keyfilter" aria-label="Filter shortcuts">`), tbl, reset);
    sec.querySelector(".keyfilter").addEventListener("input", e => { const q = e.target.value.toLowerCase(); $$(".keyrow", tbl).forEach(r => (r.hidden = !r.textContent.toLowerCase().includes(q) && !r.querySelector("input").value.toLowerCase().includes(q))); });
    const auto = section("Autostart", "One command per line, for example: discord --start-minimized");
    const ta = h(`<textarea rows="5" spellcheck="false">${esc((S.s.autostart.extra || []).join("\n"))}</textarea>`);
    let t2 = 0; ta.addEventListener("input", () => { clearTimeout(t2); t2 = setTimeout(() => { const lines = ta.value.split("\n"); S.s.autostart.extra = lines; api.act("autostart", { lines }, true); }, 400); });
    auto.append(ta);
    view.append(sec, auto);
  },
});

Studio.page("apps", {
  title: "Apps", icon: "▦", keywords: "install uninstall remove program flatpak dnf copr find",
  tab: "installed",
  async render(view) {
    const tabs = h(`<div class="seg" role="tablist"><button role="tab" data-t="installed" aria-pressed="${this.tab === "installed"}">Installed</button><button role="tab" data-t="find" aria-pressed="${this.tab === "find"}">Find & install</button></div>`);
    tabs.onclick = e => { const b = e.target.closest("[data-t]"); if (b) { this.tab = b.dataset.t; go("apps"); } };
    const box = h(`<div></div>`);
    view.append(h(`<div class="toolbar"></div>`), box);
    view.firstChild.append(tabs);
    if (this.tab === "find") return this.find(box);
    loading(box, "Reading what is installed …");
    const d = await api.get("page", { id: "apps" });
    box.replaceChildren(h(`<p class="lede">${d.count} apps · ${esc(d.total)}. Grouped like the installer; “Other” is what you installed yourself. Uninstalling opens a terminal where dnf or flatpak ask once more.</p>`));
    const filter = h(`<input type="search" placeholder="Filter apps" aria-label="Filter apps">`);
    box.append(filter);
    const list = h(`<div class="applist"></div>`);
    for (const g of d.groups) {
      const det = h(`<details open><summary><b>${esc(g.label)}</b> <span class="hint">${g.apps.length} · ${fmtBytes(g.size)}</span></summary><div class="list"></div></details>`);
      for (const a of g.apps) {
        const row = h(`<div class="item" data-q="${esc((a.label + " " + a.source + " " + a.packages.join(" ")).toLowerCase())}"><div class="grow"><b>${esc(a.label)}</b><small>${esc(a.source)} · ${esc(a.human)}${a.locked ? " · part of the desktop" : ""}</small></div></div>`);
        if (!a.locked) row.append(button("Uninstall", "ghost", () => api.act("apps_remove", { id: a.id })));
        det.querySelector(".list").append(row);
      }
      list.append(det);
    }
    filter.oninput = () => { const q = filter.value.toLowerCase(); $$(".item", list).forEach(r => (r.hidden = q && !r.dataset.q.includes(q))); };
    const more = h(`<div class="btnrow"></div>`);
    more.append(button("Open the installer", "", () => api.act("system", { verb: "installer" })));
    box.append(list, more);
  },
  find(box) {
    box.append(h(`<p class="lede">Type a name or a few words. Results come in the order Fedora → COPR → RPM Fusion → Flathub – take the topmost one; native packages fit the system best. The exact command is shown before anything runs.</p>`));
    const row = h(`<form class="importrow"><input id="fd-q" type="search" placeholder="What do you want to install?" aria-label="Search apps"></form>`);
    const res = h(`<div class="list"></div>`);
    const go_ = async ev => {
      ev && ev.preventDefault();
      res.replaceChildren(h(`<p class="hint loading">Asking Fedora, COPR, RPM Fusion and Flathub …</p>`));
      const r = await api.act("apps_search", { term: $("#fd-q").value }, true);
      res.replaceChildren();
      if (!r) return;
      if (!r.hits.length) res.append(h(`<p class="hint">Nothing found.</p>`));
      let last = "";
      for (const x of r.hits) {
        if (x.source !== last) { res.append(h(`<h3 class="srchead">${esc(x.source)}</h3>`)); last = x.source; }
        const it = h(`<div class="item"><div class="grow"><b>${esc(x.name)}</b>${x.installed ? ' <span class="tick">installed</span>' : ""}<small>${esc(x.summary)}</small><code class="cmd">$ ${esc(x.cmd)}</code></div></div>`);
        it.append(button(x.installed ? "Reinstall" : "Install", x.installed ? "ghost" : "primary", () => api.act("apps_install", { n: x.n })));
        res.append(it);
      }
      const errs = Object.entries(r.errors || {});
      if (errs.length) res.append(h(`<p class="hint">Not everything answered: ${errs.map(([k, v]) => `${esc(k)}: ${esc(v)}`).join(" · ")}</p>`));
    };
    row.append(button("Search", "primary", go_));
    row.addEventListener("submit", go_);
    box.append(row, res);
    setTimeout(() => $("#fd-q")?.focus(), 30);
  },
});

Studio.page("games", {
  title: "Games", icon: "◆", keywords: "cs2 counter strike translator steam shader cache gaming",
  async render(view) {
    loading(view);
    const d = await api.get("page", { id: "games" });
    view.replaceChildren();
    const cs = section("CS2 chat translator", "Translates the in-game chat live as an overlay. Steam launch options: -condebug (and -netconport 2121 for writing back with Super+Ctrl+T).");
    if (!d.cs2.installed) cs.append(h(`<p class="hint">Not installed – Apps → “Open the installer” → Own tools → cs2translate.</p>`));
    else {
      const vals = Object.assign({}, d.cs2.values);
      for (const [k, [label, , hint]] of Object.entries(d.cs2.fields)) {
        const r = h(`<div class="row"><label>${esc(label)}</label><input type="text" value="${esc(vals[k] || "")}" spellcheck="false"></div>`);
        if (hint) r.append(h(`<small>${esc(hint)}</small>`));
        r.querySelector("input").oninput = e => (vals[k] = e.target.value);
        cs.append(r);
      }
      const no = h(`<div class="row"><label>Hide the original text</label><input type="checkbox" class="switch" ${vals["no-original"] ? "checked" : ""}></div>`);
      cs.append(no);
      const b = h(`<div class="btnrow"></div>`);
      b.append(button("Save", "primary", () => { delete vals["no-original"]; api.act("games", { verb: "cs2_save", values: vals, no_original: no.querySelector("input").checked }); }),
        button("Move the overlay", "", () => api.act("games", { verb: "cs2_move" })), button("Test in a terminal", "ghost", () => api.act("games", { verb: "cs2_test" }, true)));
      cs.append(b);
    }
    const st = section("Steam shader cache", "Why Steam downloads gigabytes before a game, a size limit per drive, and a time window for automatic updates.");
    if (!d.steam.installed) st.append(h(`<p class="hint">Not installed – installer → Own tools → steamtune.</p>`));
    else {
      if (d.steam.error) st.append(h(`<p class="hint">${esc(d.steam.error)}</p>`));
      for (const l of d.steam.libraries) {
        const r = h(`<div class="row"><label>${esc(l.path)}<small class="sub">cache ${esc(l.cache)} · drive free ${esc(l.free)}</small></label><input type="text" placeholder="limit, e.g. 20G" value="${esc(l.limit || "")}"></div>`);
        r.append(button("Set", "ghost", () => api.act("games", { verb: "steam_limit", n: l.n, limit: r.querySelector("input").value })));
        st.append(r);
      }
      const w = h(`<div class="row"><label>Auto-update window<small class="sub">hours, e.g. 2-6 · empty = any time</small></label><input type="text" value="${esc(d.steam.window || "")}"></div>`);
      w.append(button("Set", "ghost", () => api.act("games", { verb: "steam_window", window: w.querySelector("input").value })));
      st.append(w, button("Open steamtune", "ghost", () => api.act("games", { verb: "steamtune" }, true)));
    }
    view.append(cs, st);
  },
});

// ═══ SYSTEM ═══════════════════════════════════════════════════════════
Studio.page("power", {
  title: "Power & lock", icon: "⏻", keywords: "screensaver lock suspend sleep screen off night light power profile performance battery matrix",
  async render(view) {
    const sv = section("Screensaver", "Instead of a plain lock, a scene starts after the lock time. The first key or mouse move locks the screen and ends it.");
    const grid = h(`<div class="grid savers"></div>`), c = colours();
    Savers.setSpeed(S.s.power.saver_speed ?? 5);
    for (const [id, label] of Object.entries(S.data.savers)) {
      const on = id === S.s.power.screensaver;
      const card = h(`<button class="card" aria-pressed="${on}"><div class="saver"><canvas width="320" height="200"></canvas></div>
        <div class="card-meta"><span class="card-name">${esc(label.split(" (")[0])}</span>${on ? `<span class="tick">chosen</span>` : ""}</div>
        ${label.includes("(") ? `<div class="card-desc">${esc(label.match(/\((.*)\)/)[1])}</div>` : ""}</button>`);
      card.onclick = () => { change("power.screensaver", id); $$(".savers .card").forEach(x => x.setAttribute("aria-pressed", String(x === card))); };
      grid.append(card);
      Savers.attach(card.querySelector("canvas"), id, c);
    }
    const pick = () => (S.s.power.screensaver === "off" ? "matrix" : S.s.power.screensaver);
    const r = h(`<div class="btnrow"></div>`);
    r.append(button("Preview here", "primary", () => saverOverlay(pick())),
      button("Preview the real one (terminal, full screen)", "ghost", () => api.post("preview-saver", { name: pick() })));
    sv.append(grid, r, h(`<p class="hint">Double-click a screensaver to watch it big. Any key or click ends the preview.</p>`));
    grid.addEventListener("dblclick", e => { const c = e.target.closest(".card"); if (c) saverOverlay(Object.keys(S.data.savers)[[...grid.children].indexOf(c)]); });
    view.append(sv, form("power", { skip: ["power.screensaver"] }));
    const pp = await api.get("page", { id: "power" }).catch(() => null);
    if (pp && pp.profiles.length) {
      const sec = section("Power profile", "Takes effect immediately.");
      const seg = h(`<div class="seg">${pp.profiles.map(([l, v]) => `<button data-p="${esc(v)}" aria-pressed="${v === pp.profile}">${esc(l)}</button>`).join("")}</div>`);
      seg.onclick = async e => { const b = e.target.closest("[data-p]"); if (b && await api.act("power_profile", { profile: b.dataset.p })) $$("[data-p]", seg).forEach(x => x.setAttribute("aria-pressed", String(x === b))); };
      sec.append(seg);
      view.append(sec);
    }
  },
});

Studio.page("boot", {
  title: "Boot & login", icon: "⏼", keywords: "plymouth boot screen splash login greeter tuigreet sddm",
  async render(view) {
    loading(view);
    const d = await api.get("page", { id: "boot" });
    view.replaceChildren();
    const sec = section("Boot screen", "Uses your theme colours, font and ASCII art. Installing rebuilds the initramfs (about a minute).");
    const grid = h(`<div class="grid bootgrid"></div>`);
    const cur = S.s.boot.style || "auto";
    for (const [id, label, desc] of d.styles) {
      const pv = d.previews[id === "auto" ? d.current : id] || "";
      const card = h(`<button class="card" aria-pressed="${id === cur}"><pre class="bootpv">${esc(pv)}</pre><div class="card-meta"><span class="card-name">${esc(label)}</span></div><div class="card-desc">${esc(desc || `now: ${d.current}`)}</div></button>`);
      card.onclick = () => { change("boot.style", id); $$(".bootgrid .card").forEach(x => x.setAttribute("aria-pressed", String(x === card))); };
      grid.append(card);
    }
    sec.append(grid, fieldRow({ path: "boot.text", label: "Banner text", kind: "str", help: `empty = your host name (${d.banner})` }));
    sec.append(button("Install boot screen", "primary", async ev => { await busy(ev.currentTarget, api.act("boot_install", { verb: "boot" })); setDirty(false); }));
    const lg = section("Login screen", `Keyboard-only text login (tuigreet) with your ASCII art – ${d.greeter ? "active" : "not installed yet"}.`);
    lg.append(form("boot", { noHeads: true }));
    const r = h(`<div class="btnrow"></div>`);
    r.append(button("Install login screen", "primary", ev => busy(ev.currentTarget, api.act("boot_install", { verb: "login" }))),
      button("Back to SDDM", "ghost", ev => busy(ev.currentTarget, api.act("boot_install", { verb: "restore" }))));
    lg.append(r);
    view.append(sec, lg);
  },
});

Studio.page("security", {
  title: "Security", icon: "⛨", keywords: "malware virus clamav rootkit lynis audit scan usb ports quarantine",
  async render(view) {
    loading(view);
    const d = await api.get("page", { id: "security" });
    view.replaceChildren(h(`<p class="lede">Free scanners from Fedora. Linux malware is rare – ClamAV mostly finds Windows malware in downloads and on USB sticks. Nothing is deleted automatically; every run leaves a report.</p>`));
    const st = h(`<ul class="status">${d.tools.map(t => `<li class="${t.ok ? "ok" : "no"}">${esc(t.label)}</li>`).join("")}
      ${d.clam ? `<li class="${d.signature_age == null || d.signature_age > 7 ? "warn" : "ok"}">Virus signatures: ${d.signature_age == null ? "none yet" : d.signature_age >= 1 ? Math.round(d.signature_age) + " day(s) old" : "up to date"}</li>` : ""}</ul>`);
    view.append(st);
    const A = (verb, args = {}) => api.act("security", Object.assign({ verb }, args));
    const scan = section("Malware scan");
    const r1 = h(`<div class="btnrow"></div>`);
    r1.append(button("Scan Downloads", "primary", () => A("dl")), button("Scan home folder", "", () => A("home")), button("Update signatures", "ghost", () => A("fresh")));
    if (!d.clam) r1.append(button("Install the scanners", "primary", () => A("install")));
    const r2 = h(`<div class="importrow"><select id="sec-drive">${d.drives.length ? d.drives.map(x => `<option value="${esc(x.mount)}">${esc(x.label)} (${esc(x.size)}) – ${esc(x.mount)}</option>`).join("") : "<option value=''>No USB drive mounted</option>"}</select></div>`);
    r2.append(button("Scan drive", "", () => A("drive", { mount: $("#sec-drive").value })));
    const r3 = h(`<div class="importrow"><input id="sec-path" type="text" placeholder="any folder or file, e.g. ~/Games/setup.exe" spellcheck="false"></div>`);
    r3.append(button("Scan path", "", () => A("path", { path: $("#sec-path").value })));
    scan.append(r1, r2, r3);
    const rk = section("Rootkits & system audit", "Both need your password and report false alarms now and then – read before you act.");
    const r4 = h(`<div class="btnrow"></div>`);
    r4.append(button("Rootkit check", "", () => A("rootkit")), button("System audit (Lynis)", "", () => A("audit")), button("Open quarantine", "ghost", () => A("quarantine")));
    rk.append(r4);
    const ov = section("Devices & connections");
    const out = h(`<pre class="out" hidden></pre>`);
    const r5 = h(`<div class="btnrow"></div>`);
    [["usb", "USB devices"], ["drives", "Drives"], ["ports", "Open ports"], ["autostart", "Autostart"]].forEach(([k, l]) => r5.append(button(l, "ghost", async () => {
      const r = await A("overview", { kind: k }); if (r) { out.textContent = r.msg || r; out.hidden = false; } })));
    ov.append(r5, out);
    const rep = section("Reports");
    const rl = h(`<div class="list"></div>`);
    if (!d.reports.length) rl.append(h(`<p class="hint">None yet.</p>`));
    d.reports.forEach(x => { const it = h(`<div class="item"><div class="grow"><code>${esc(x.text)}</code></div></div>`); it.append(button("Read", "ghost", async () => {
      const r = await api.act("security", { verb: "report", path: x.path }, true);
      if (r) dialog(`<h2>Report</h2><pre class="out">${esc(r.msg)}</pre><menu><button value="" class="btn">Close</button></menu>`); })); rl.append(it); });
    rep.append(rl);
    view.append(scan, rk, ov, rep, form("security"));
  },
});

Studio.page("cleanup", {
  title: "Cleanup & drives", icon: "♻", keywords: "clean cache disk space free wipe usb stick format sd card",
  async render(view) {
    loading(view, "Measuring …");
    const d = await api.get("page", { id: "cleanup" });
    view.replaceChildren();
    const cl = section("System cleanup", `Tick what you want gone, then clean. It runs in a terminal with the plain command shown. About ${esc(d.total)} can be freed (plus what can't be measured without root).`);
    const list = h(`<div class="list"></div>`);
    for (const it of d.items) list.append(h(`<label class="item check"><input type="checkbox" value="${esc(it.id)}" ${it.default ? "checked" : ""}><div class="grow"><b>${esc(it.label)}</b> <span class="tick">${esc(it.human)}</span><small>${esc(it.desc)}</small><code class="cmd">$ ${esc(it.cmd)}</code></div></label>`));
    const r = h(`<div class="btnrow"></div>`);
    r.append(button("Clean ticked", "primary", () => api.act("cleanup", { ids: $$("input:checked", list).map(i => i.value) })), button("Measure again", "ghost", () => go("cleanup")));
    cl.append(list, r);
    const wp = section("Wipe a USB stick, SD card or external SSD", "Only removable drives that hold nothing of the running system are listed. Quick = new and empty in seconds; secure = every block overwritten, for giving a drive away.");
    if (!d.drives.length) wp.append(h(`<p class="hint">No removable drive found – plug one in and measure again.</p>`));
    else {
      const f = h(`<div class="controls">
        <div class="row"><label for="wp-d">Drive</label><select id="wp-d">${d.drives.map(x => `<option value="${esc(x.name)}">${esc(x.label)}</option>`).join("")}</select></div>
        <div class="row"><label for="wp-m">Erase</label><select id="wp-m">${Object.entries(d.modes).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></div>
        <div class="row"><label for="wp-f">Then format as</label><select id="wp-f">${Object.entries(d.fs).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join("")}</select></div>
        <div class="row"><label for="wp-l">Name</label><input id="wp-l" type="text" maxlength="11" value="USB"></div></div>`);
      f.querySelector("#wp-f").value = "exfat";
      wp.append(f, button("Wipe drive …", "danger", async () => {
        const name = $("#wp-d").value, dr = d.drives.find(x => x.name === name);
        const res = await dialog(`<h2>Wipe ${esc(dr.label)}?</h2><p class="lede">Everything on it will be gone – there is no undo. Partitions: ${esc((dr.parts || []).join(", ") || "none")}.</p>
          <div class="row"><label for="wc">Type <b>${esc(name)}</b> to confirm</label><input id="wc" type="text" autocomplete="off"></div>
          <menu><button value="" class="btn ghost">Cancel</button><button value="wipe" class="btn danger">Wipe</button></menu>`);
        if (res === "wipe") api.act("wipe", { name, confirm: $("#wc").value, mode: $("#wp-m").value, fs: $("#wp-f").value, label: $("#wp-l").value });
      }));
    }
    view.append(cl, wp);
  },
});

Studio.page("mounts", {
  title: "Mount drives", icon: "⛁", keywords: "mount drive ssd hdd fstab automount games data",
  async render(view) {
    loading(view);
    const d = await api.get("page", { id: "mounts" });
    view.replaceChildren(h(`<p class="lede">Pick a drive, give it a name: it appears at /mnt/NAME and in the file manager, now and after every reboot. /etc/fstab is backed up and checked first; a missing drive never blocks booting.</p>`));
    const add = section("Add a drive");
    if (!d.candidates.length) add.append(h(`<p class="hint">Nothing new to mount – every drive with a file system is set up already.</p>`));
    for (const c of d.candidates) {
      const r = h(`<div class="item"><div class="grow"><b>${esc(c.label)}</b><code class="cmd">${esc(c.line)}</code></div><input type="text" value="${esc(c.suggest)}" aria-label="Name" maxlength="32"></div>`);
      r.append(button("Mount", "primary", () => api.act("mounts", { verb: "add", name: c.name, as: r.querySelector("input").value })));
      add.append(r);
    }
    const ex = section("Mounted by swayforge");
    if (!d.entries.length) ex.append(h(`<p class="hint">None yet.</p>`));
    for (const e of d.entries) {
      const r = h(`<div class="item"><span class="dot ${e.mounted ? "on" : ""}"></span><div class="grow"><b>${esc(e.target)}</b><small>${esc(e.label)} · ${esc(e.fstype)} · ${e.mounted ? "mounted" : "not mounted"}</small></div></div>`);
      r.append(button("Open", "ghost", () => api.act("mounts", { verb: "open", target: e.target }, true)), button("Remove", "ghost", () => api.act("mounts", { verb: "remove", target: e.target })));
      ex.append(r);
    }
    view.append(add, ex, button("Look again", "ghost", () => go("mounts")));
  },
});

Studio.page("system", {
  title: "System & files", icon: "⚙", keywords: "update upgrade firmware config files backup export restore import sway config",
  async render(view) {
    const d = await api.get("page", { id: "system" });
    const sy = section("System");
    const r = h(`<div class="btnrow"></div>`);
    r.append(button("Update the system", "primary", () => api.act("system", { verb: "update" })), button("Check firmware", "", () => api.act("system", { verb: "firmware" }, true)),
      button("Check screen sharing", "", () => api.act("system", { verb: "screenshare" })),
      button("Installer", "ghost", () => api.act("system", { verb: "installer" })),
      button("Terminal settings app", "ghost", () => api.post("classic", { page: "" }).then(() => toast("Opening the terminal settings app …"))));
    sy.append(r);
    const bk = section("Back up for the next reset", "Saves settings, app selection, your themes, ASCII art, tweaks and the CS2 translator. After a reset: ./install.sh --restore FILE");
    const er = h(`<div class="importrow"><input id="exp" type="text" value="${esc(d.export)}" spellcheck="false"></div>`);
    er.append(button("Export", "primary", () => api.act("system", { verb: "export", path: $("#exp").value })));
    bk.append(er);
    const fl = section("Config files", "Generated files carry the line “swayforge generated”. Delete it and the file is yours – swayforge leaves it alone from then on.");
    const fls = h(`<div class="list"></div>`);
    d.files.forEach(f => { const it = h(`<div class="item"><div class="grow"><b>${esc(f.label)}</b><small>${esc(f.path)}</small></div></div>`); it.append(button("Edit", "ghost", () => api.act("open_file", { key: f.key }))); fls.append(it); });
    fl.append(fls);
    const im = section("Take over an existing Sway config", "Shortcuts, rules and autostarts go into custom.conf. Colours, font, bar and wallpaper keep coming from the theme.");
    const ir = h(`<div class="importrow"><input id="imp" type="text" placeholder="~/Downloads/config" spellcheck="false"></div>`);
    ir.append(button("Import", "", async () => { if (await api.act("system", { verb: "import", path: $("#imp").value })) { await reloadSettings(); setDirty(true); } }));
    im.append(ir);
    const ob = section("Automatic backups of replaced configs");
    const bl = h(`<div class="list"></div>`);
    if (!d.backups.length) bl.append(h(`<p class="hint">None yet.</p>`));
    d.backups.forEach(name => { const it = h(`<div class="item"><div class="grow"><code>${esc(name)}</code></div></div>`);
      it.append(button("Open", "ghost", () => api.act("system", { verb: "open_backup", name }, true)), button("Restore", "ghost", async () => {
        if (await dialog(`<h2>Restore ${esc(name)}?</h2><p class="lede">Copies those files back over the current ones.</p><menu><button value="" class="btn ghost">Cancel</button><button value="ok" class="btn primary">Restore</button></menu>`) === "ok") api.act("system", { verb: "restore", name }); }));
      bl.append(it); });
    ob.append(bl);
    view.append(sy, bk, fl, im, ob);
  },
});

Studio.page("about", {
  title: "About & updates", icon: "ⓘ", keywords: "version update github crash report",
  async render(view) {
    loading(view, "Checking GitHub …");
    const d = await api.get("page", { id: "about" });
    view.replaceChildren();
    const up = section("Versions");
    const list = h(`<div class="list"></div>`);
    for (const a of d.apps) {
      const v = { current: "up to date", update: `update available (${a.remote})`, unknown: "can't check (offline?)", missing: "not installed" }[a.verdict];
      list.append(h(`<div class="item"><span class="dot ${a.verdict === "current" ? "on" : a.verdict === "update" ? "warn" : ""}"></span><div class="grow"><b>${esc(a.name)} ${esc(a.version)}</b><small>${esc(a.commit)} ${esc(a.date)} · ${esc(v)}</small></div></div>`));
    }
    const r = h(`<div class="btnrow"></div>`);
    r.append(button("Update from GitHub", "primary", () => api.act("about", { verb: "update" })), button("Check again", "ghost", () => go("about")),
      button("swayforge on GitHub", "ghost", () => api.act("about", { verb: "gh_swayforge" }, true)), button("wolfforge on GitHub", "ghost", () => api.act("about", { verb: "gh_wolfforge" }, true)));
    up.append(list, r, h(`<p class="hint">Update pulls the newest swayforge and wolfforge, installs them and applies your settings again. Your own changes to the source copy are kept in git stash.</p>`));
    const cr = section("Crash reports");
    cr.append(d.crashes.length ? h(`<div class="list">${d.crashes.map(c => `<div class="item"><div class="grow"><code>${esc(c.name)}</code><small>${esc(c.last)}</small></div></div>`).join("")}</div>`) : h(`<p class="hint">No crashes recorded.</p>`));
    cr.append(button("Open crash folder", "ghost", () => api.act("about", { verb: "crash_dir" }, true)));
    const ab = section("About");
    ab.append(h(`<p class="lede">swayforge – Fedora Sway installer and settings. wolfforge – LibreWolf overhaul. Proof of concept, written by Claude (Anthropic). Provided as is, without any warranty; use at your own risk. MIT licence.</p>`));
    view.append(up, cr, ab);
  },
});

// full-window screensaver preview inside the app (fullscreen when allowed)
function saverOverlay(name) {
  const ov = h(`<div class="saver-ov" role="dialog" aria-label="Screensaver preview" tabindex="-1"><canvas></canvas><span class="saver-hint">any key or click ends the preview</span></div>`);
  document.body.append(ov);
  const cv = ov.querySelector("canvas");
  const fit = () => { cv.width = Math.round(innerWidth / 2); cv.height = Math.round(innerHeight / 2); };
  fit();
  Savers.attach(cv, name === "off" ? "matrix" : name, colours());
  ov.focus();
  ov.requestFullscreen?.().catch(() => {});
  const close = () => { ov.remove(); document.removeEventListener("keydown", close, true); if (document.fullscreenElement) document.exitFullscreen().catch(() => {}); };
  setTimeout(() => { ov.addEventListener("click", close); document.addEventListener("keydown", close, true); }, 400);
  addEventListener("resize", fit, { once: true });
}

// ═══ Desktop widgets – the same drawing as widgets.py, on a canvas ════════
const WidgetArt = (() => {
  const DIG = {
    "0": [".###.", "#...#", "#..##", "#.#.#", "##..#", "#...#", ".###."], "1": ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", ".###."],
    "2": [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#####"], "3": ["#####", "...#.", "..#..", "...#.", "....#", "#...#", ".###."],
    "4": ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."], "5": ["#####", "#....", "####.", "....#", "....#", "#...#", ".###."],
    "6": ["..##.", ".#...", "#....", "####.", "#...#", "#...#", ".###."], "7": ["#####", "....#", "...#.", "..#..", ".#...", ".#...", ".#..."],
    "8": [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."], "9": [".###.", "#...#", "#...#", ".####", "....#", "...#.", ".##.."],
    ":": [".", ".", "#", ".", "#", ".", "."],
  };
  const SIZE = { dots: [372, 150], digital: [330, 140], analog: [210, 230], player: [340, 118], sysmon: [280, 120], clippy: [330, 190] };
  const rr = (g, x, y, w, h, r) => { r = Math.max(0, Math.min(r, w / 2, h / 2)); g.beginPath(); g.roundRect ? g.roundRect(x, y, w, h, r) : g.rect(x, y, w, h); };
  function card(g, c, w, h, o) { rr(g, .5, .5, w - 1, h - 1, o.radius + 4); g.fillStyle = Desk.rgba(c.base, o.alpha); g.fill(); g.strokeStyle = c.surface2; g.lineWidth = 1; g.stroke(); }
  function text(g, c, x, y, s, size, key = "text", bold = false, maxw, font = "monospace") {
    g.font = `${bold ? "700 " : ""}${size}px ${font}`; g.fillStyle = c[key] || key;
    if (maxw) while (s.length > 2 && g.measureText(s).width > maxw) s = s.slice(0, -2) + "…";
    g.fillText(s, x, y); return g.measureText(s).width;
  }
  function clock(g, c, w, h, o, now) {
    const style = o.clock, hhmm = now.toTimeString().slice(0, 5), sec = now.getSeconds();
    const date = now.toLocaleDateString("en-GB", { weekday: "long", day: "2-digit", month: "long" });
    if (style === "analog") {
      const cx = w / 2, cy = w / 2, R = w / 2 - 8;
      g.beginPath(); g.arc(cx, cy, R, 0, Math.PI * 2); g.fillStyle = Desk.rgba(c.base, o.alpha); g.fill(); g.strokeStyle = c.surface2; g.lineWidth = 1.5; g.stroke();
      for (let i = 0; i < 60; i++) { const a = i / 60 * Math.PI * 2, inner = R - (i % 5 ? 5 : 12);
        g.beginPath(); g.moveTo(cx + Math.sin(a) * inner, cy - Math.cos(a) * inner); g.lineTo(cx + Math.sin(a) * (R - 3), cy - Math.cos(a) * (R - 3));
        g.strokeStyle = i % 5 ? c.overlay : c.text; g.lineWidth = i % 5 ? 1 : 2.4; g.stroke(); }
      const s = sec + now.getMilliseconds() / 1000, m = now.getMinutes() + s / 60, hr = now.getHours() % 12 + m / 60;
      for (const [v, len, lw, k] of [[hr / 12, .5, 5, "text"], [m / 60, .75, 3.2, "text"], [s / 60, .85, 1.4, "accent"]]) {
        const a = v * Math.PI * 2; g.beginPath(); g.moveTo(cx - Math.sin(a) * R * .12, cy + Math.cos(a) * R * .12); g.lineTo(cx + Math.sin(a) * R * len, cy - Math.cos(a) * R * len);
        g.strokeStyle = c[k]; g.lineWidth = lw; g.lineCap = "round"; g.stroke(); }
      g.beginPath(); g.arc(cx, cy, 4, 0, Math.PI * 2); g.fillStyle = c.accent; g.fill();
      text(g, c, cx - 34, h - 4, now.toLocaleDateString("en-GB", { weekday: "short", day: "2-digit", month: "2-digit" }), 13, "subtext", false, 0, o.font);
      return;
    }
    card(g, c, w, h, o);
    if (style === "digital") {
      text(g, c, 22, h * .58, hhmm, h * .46, "text", true, 0, o.font);
      text(g, c, w - 62, h * .58, ":" + String(sec).padStart(2, "0"), h * .2, "accent", true, 0, o.font);
      g.fillStyle = c.accent; g.fillRect(22, h * .67, (w - 44) * (sec + now.getMilliseconds() / 1000) / 60, 3);
      text(g, c, 22, h * .87, date, h * .12, "subtext", false, 0, o.font);
      return;
    }
    const cell = (w - 40) / 27, r = cell * .36, y0 = 18 + cell / 2;
    let x = 20 + cell / 2;
    for (const ch of hhmm) {
      const gl = DIG[ch], blink = ch === ":" && sec % 2;
      gl.forEach((row, yy) => [...row].forEach((v, xx) => {
        g.beginPath(); g.arc(x + xx * cell, y0 + yy * cell, r, 0, Math.PI * 2);
        g.fillStyle = v === "#" && !blink ? c.accent : Desk.rgba(c.surface2, .35); g.fill(); }));
      x += (gl[0].length + 1) * cell;
    }
    const sy = y0 + 7 * cell + cell * .3, step = (w - 40) / 60;
    for (let s2 = 0; s2 < 60; s2++) { g.beginPath(); g.arc(20 + step * (s2 + .5), sy, Math.max(1.2, r * .32), 0, Math.PI * 2);
      g.fillStyle = s2 <= sec ? c.accent : Desk.rgba(c.surface2, .4); g.fill(); }
    text(g, c, 20, h - 12, date, Math.max(10, h * .09), "subtext", false, 0, o.font);
  }
  function player(g, c, w, h, o) {
    card(g, c, w, h, o);
    text(g, c, 20, 32, "Midnight City", 16, "text", true, w - 40, o.font);
    text(g, c, 20, 54, "M83", 13, "subtext", false, w - 40, o.font);
    rr(g, 20, 66, w - 40, 4, 2); g.fillStyle = c.surface2; g.fill(); rr(g, 20, 66, (w - 40) * .42, 4, 2); g.fillStyle = c.accent; g.fill();
    const mid = w / 2; [["⏮", mid - 70, "text"], ["⏸", mid - 16, "accent"], ["⏭", mid + 38, "text"]].forEach(([s, x, k]) => text(g, c, x, h - 16, s, 22, k, true));
  }
  function sysmon(g, c, w, h, o, t) {
    card(g, c, w, h, o);
    [["CPU", .25 + .15 * Math.sin(t)], ["RAM", .58], ["TEMP", .52]].forEach(([lab, v], i) => {
      const y = 30 + i * 30; text(g, c, 18, y, lab, 12, "subtext", true, 0, o.font);
      rr(g, 70, y - 9, w - 140, 8, 4); g.fillStyle = Desk.rgba(c.surface2, .7); g.fill();
      rr(g, 70, y - 9, (w - 140) * v, 8, 4); g.fillStyle = v > .85 ? c.red : v > .65 ? c.yellow : c.accent; g.fill();
      text(g, c, w - 60, y, lab === "TEMP" ? `${Math.round(v * 100)}°` : `${Math.round(v * 100)}%`, 12, "text", true, 0, o.font);
    });
  }
  function clippy(g, c, w, h, o, t) {
    const bw = w - 84, bh = h - 30;
    rr(g, 4, 4, bw, bh, 10); g.fillStyle = Desk.rgba(c.base, Math.max(o.alpha, .92)); g.fill(); g.strokeStyle = c.accent; g.lineWidth = 1.5; g.stroke();
    g.beginPath(); g.moveTo(bw - 18, bh + 4); g.lineTo(bw + 10, bh + 18); g.lineTo(bw - 34, bh + 4); g.closePath(); g.fill();
    g.font = `13.5px ${o.font}`; g.fillStyle = c.text;
    let line = "", ly = 30;
    for (const word of "It looks like you're writing a config. Would you like a backup first?".split(" ")) {
      const test = (line + " " + word).trim();
      if (g.measureText(test).width > bw - 26 && line) { g.fillText(line, 16, ly); line = word; ly += 18; } else line = test;
    }
    g.fillText(line, 16, ly);
    text(g, c, 16, bh - 6, "click for another tip", 10.5, "overlay", false, 0, o.font);
    const x0 = w - 62, y0 = h - 150 + Math.sin(t * 1.5) * 3;
    g.strokeStyle = c.subtext; g.lineWidth = 5; g.lineCap = "round"; g.beginPath();
    g.moveTo(x0 + 14, y0 + 120); g.lineTo(x0 + 14, y0 + 30); g.bezierCurveTo(x0 + 14, y0 + 6, x0 + 46, y0 + 6, x0 + 46, y0 + 30);
    g.lineTo(x0 + 46, y0 + 128); g.bezierCurveTo(x0 + 46, y0 + 150, x0 + 4, y0 + 150, x0 + 4, y0 + 128); g.lineTo(x0 + 4, y0 + 46);
    g.bezierCurveTo(x0 + 4, y0 + 34, x0 + 30, y0 + 34, x0 + 30, y0 + 46); g.lineTo(x0 + 30, y0 + 110); g.stroke();
    const blink = (t % 5) < .15;
    for (const ex of [x0 + 10, x0 + 40]) {
      g.beginPath(); g.arc(ex, y0 + 62, 9, 0, Math.PI * 2); g.fillStyle = c.text; g.fill();
      if (!blink) { g.beginPath(); g.arc(ex + 2, y0 + 63, 4, 0, Math.PI * 2); g.fillStyle = c.crust; g.fill(); }
      g.beginPath(); g.moveTo(ex - 8, y0 + 48); g.lineTo(ex + 6, y0 + 45); g.strokeStyle = c.crust; g.lineWidth = 3; g.stroke();
    }
  }
  // the whole screen: wallpaper colour wash + widgets in their corners
  function scene(cv, o, t) {
    const g = cv.getContext("2d"), W = cv.width, H = cv.height, c = colours(), k = (o.scale || 1) * W / 1920;
    g.clearRect(0, 0, W, H);
    const list = [];
    if (o.clock !== "off") list.push(["clock", o.clock_pos, SIZE[o.clock] || SIZE.dots]);
    for (const kind of ["player", "sysmon", "clippy"]) if (o[kind]) list.push([kind, o[kind + "_pos"], SIZE[kind]]);
    // keep clear of the bar like the real widgets do (they respect its reserved space)
    const pos = layoutOf(S.s.bar.layout).position, barH = 1080 * ({ touch: 36, win7: 28 }[S.s.bar.layout] || 28) / 360;
    const top = pos === "top" ? barH : 0, bottom = pos === "bottom" ? barH : 0, left = pos === "left" ? 1920 * 28 / 640 : 0;
    const stack = {}, gap = 18;
    for (const [kind, corner, [bw, bh]] of list) {
      const off = stack[corner] || 0; stack[corner] = off + bh + 12;
      let x = left + gap, y = top + gap + off;
      if (corner === "center") { x = (W / k - bw) / 2; y = (H / k - bh) / 2; }
      else { if (corner.endsWith("right")) x = W / k - bw - gap; if (corner.startsWith("bottom")) y = H / k - bh - gap - off - bottom; }
      g.save(); g.scale(k, k); g.translate(x, y);
      const now = new Date();
      ({ clock: () => clock(g, c, bw, bh, o, now), player: () => player(g, c, bw, bh, o), sysmon: () => sysmon(g, c, bw, bh, o, t), clippy: () => clippy(g, c, bw, bh, o, t) })[kind]();
      g.restore();
    }
  }
  return { scene };
})();

Studio.page("widgets", {
  title: "Desktop widgets", icon: "◫", keywords: "widget clock dot matrix digital analog player music spotify system monitor cpu clippy desktop",
  render(view) {
    const split = h(`<div class="split"><div class="col"></div><div class="sticky"><div class="widget-preview"><div class="desk-frame big" id="wg-desk"></div><canvas id="wg-canvas" width="1280" height="720"></canvas></div>
      <p class="hint">Preview with your theme. The real widgets sit on the desktop under your windows; they need gtk-layer-shell (installed with swayforge's base packages).</p></div></div>`);
    split.querySelector(".col").append(form("widgets"));
    view.append(split);
    const fr = $("#wg-desk");
    desk(fr, { theme: theme(), layout: S.s.bar.layout, wallpaperUrl: wallUrl(null, true), empty: true });
    const cv = $("#wg-canvas"), t0 = performance.now();
    const loop = () => {
      if (!cv.isConnected) return;
      const o = Object.assign({ font: `"${S.s.theme.font}", monospace`, radius: Math.min(S.s.look.radius, 12) }, S.s.widgets, { alpha: S.s.widgets.opacity });
      cv.style.opacity = S.s.widgets.enabled ? 1 : .35;
      WidgetArt.scene(cv, o, (performance.now() - t0) / 1000);
      setTimeout(() => requestAnimationFrame(loop), 120);
    };
    loop();
  },
  live() { const fr = $("#wg-desk"); if (fr) desk(fr, { theme: theme(), layout: S.s.bar.layout, wallpaperUrl: wallUrl(null, true), empty: true }); },
});
