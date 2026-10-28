// Mock desktop renderer: draws a small Sway desktop (wallpaper, windows, bar, notification,
// launcher) for any theme × layout × look settings. Everything is plain DOM at a fixed
// 640×360 "virtual screen" that the caller scales with CSS.
"use strict";

const Desk = (() => {
  const W = 640, H = 360;

  function hex(c) { c = (c || "#000000").replace("#", ""); return [0, 2, 4].map(i => parseInt(c.substr(i, 2), 16)); }
  function rgba(c, a) { const [r, g, b] = hex(c); return `rgba(${r},${g},${b},${a})`; }
  function mix(a, b, t) {
    const x = hex(a), y = hex(b);
    return "#" + x.map((v, i) => Math.round(v + (y[i] - v) * t).toString(16).padStart(2, "0")).join("");
  }
  function lum(c) {
    return hex(c).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; })
      .reduce((s, v, i) => s + v * [0.2126, 0.7152, 0.0722][i], 0);
  }
  function contrast(a, b) { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); }
  // same rule as render.readable(): the wanted colour if readable, else the theme's crust/text, else black/white
  function on(bg, pref, c) {
    pref = pref || "#ffffff";
    if (contrast(pref, bg) >= 3) return pref;
    const best = [c.crust, c.text].sort((p, q) => contrast(q, bg) - contrast(p, bg))[0];
    if (contrast(best, bg) >= 3) return best;
    return contrast("#ffffff", bg) > contrast("#000000", bg) ? "#ffffff" : "#000000";
  }
  function bevel(c) {
    const face = mix(c.surface, c.text, 0.10);
    return { face, hi: mix(face, c.text, 0.6), lo: mix(face, c.crust, 0.85), pressed: mix(face, c.crust, 0.35),
             title: c.accent, title2: mix(c.accent, c.base, 0.55) };
  }
  function el(tag, style, html) {
    const e = document.createElement(tag);
    if (style) e.style.cssText = style;
    if (html !== undefined) e.innerHTML = html;
    return e;
  }
  const esc = s => String(s).replace(/[&<>"]/g, ch => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[ch]));

  // colours of a theme with the accent choice applied
  function colours(theme, accent) {
    const c = Object.assign({}, theme.colors);
    if (accent && c[accent]) c.accent = c[accent];
    else if (accent && /^#[0-9a-f]{6}$/i.test(accent)) c.accent = accent;
    return c;
  }

  const ROMAN = ["I", "II", "III", "IV", "V"];

  // ── bars ────────────────────────────────────────────────────────────
  function bar(lay, c, o) {
    const bv = bevel(c), ui = o.ui, f = o.font, R = o.radius;
    const wrap = el("div", "position:absolute;left:0;right:0;font:600 9px/1 " + f + ";color:" + c.text);
    const islands = (bg, border, top) => {
      wrap.style.cssText += `top:${top}px;display:flex;justify-content:space-between;padding:0 ${6 + o.gapsOuter}px`;
      const isl = html => el("div", `background:${bg};border:1px solid ${border};border-radius:${R}px;padding:5px 9px;display:flex;gap:7px;align-items:center`, html);
      const ws = [1, 2, 3, 4].map((n, i) => `<span style="${i === 0 ? `color:${c.accent};` + (lay === "glass" ? `outline:1px solid ${rgba(c.accent, .7)};border-radius:4px;padding:0 3px` : "") : `color:${c.subtext}`}">${n}</span>`).join("");
      wrap.append(isl(ws), isl("Thu 28.10.&nbsp; 20:14"), isl(`<span style="color:${c.subtext}">cpu 9%</span><span style="color:${c.subtext}">vol 40%</span><span style="color:${c.red}">⏻</span>`));
    };
    switch (lay) {
      case "modern": case "minimal":
        islands(rgba(c.base, 0.88 * ui), rgba(c.surface2, .6), 5);
        if (lay === "minimal") [...wrap.children].forEach((x, i) => { if (i === 2) x.innerHTML = `<span style="color:${c.red}">⏻</span>`; });
        return wrap;
      case "glass":
        islands(rgba(c.base, 0.55 * ui), rgba(c.text, .14), 6);
        return wrap;
      case "solid": {
        wrap.style.cssText += `top:0;height:22px;display:flex;align-items:center;justify-content:space-between;padding:0 10px;background:${rgba(c.base, .95 * ui)};border-bottom:2px solid ${c.surface}`;
        wrap.innerHTML = `<span><b style="color:${c.accent}">1</b>&nbsp; 2 &nbsp;3 &nbsp;4</span><span>Thu 28.10. 20:14</span><span style="color:${c.subtext}">cpu 9% │ vol 40% │ <span style="color:${c.red}">⏻</span></span>`;
        return wrap;
      }
      case "sidebar": {
        wrap.style.cssText += `top:0;bottom:0;left:0;right:auto;width:26px;display:flex;flex-direction:column;align-items:center;gap:9px;padding:10px 0;background:${rgba(c.base, .95 * ui)};border-right:2px solid ${c.surface}`;
        wrap.innerHTML = [1, 2, 3, 4].map((n, i) => `<span style="color:${i ? c.subtext : c.accent}">${n}</span>`).join("") +
          `<span style="flex:1"></span><span style="color:${c.subtext}">20<br>14</span><span style="color:${c.red}">⏻</span>`;
        return wrap;
      }
      case "win98": {
        const raised = `${bv.hi} ${bv.lo} ${bv.lo} ${bv.hi}`, sunk = `${bv.lo} ${bv.hi} ${bv.hi} ${bv.lo}`;
        wrap.style.cssText += `bottom:0;height:24px;display:flex;align-items:center;gap:4px;padding:0 3px;background:${bv.face};opacity:${ui};border-top:2px solid ${bv.hi}`;
        wrap.innerHTML = `<span style="border:2px solid;border-color:${raised};padding:2px 6px;font-weight:800">⊞ Start</span>` +
          `<span style="border:2px solid;border-color:${sunk};padding:2px 6px;background:${bv.pressed};min-width:90px">▣ kitty</span>` +
          `<span style="border:2px solid;border-color:${raised};padding:2px 6px;min-width:90px">▤ Files</span><span style="flex:1"></span>` +
          `<span style="border:1px solid;border-color:${sunk};padding:3px 7px;color:${c.text}">🔊 20:14</span>`;
        return wrap;
      }
      case "winxp": {
        const fg = on(c.accent, "#ffffff", c);
        wrap.style.cssText += `bottom:0;height:24px;display:flex;align-items:center;gap:4px;color:${fg};opacity:${ui};
          background:linear-gradient(to bottom,${mix(c.accent, "#ffffff", .32)},${mix(c.accent, "#ffffff", .08)} 9%,${c.accent} 45%,${mix(c.accent, "#000000", .18)})`;
        wrap.innerHTML = `<span style="height:100%;display:flex;align-items:center;padding:0 16px 0 10px;border-radius:0 12px 12px 0;font:italic 800 11px ${f};color:${on(c.green, "#ffffff", c)};background:linear-gradient(to bottom,${mix(c.green, "#ffffff", .45)},${c.green} 55%,${mix(c.green, "#000000", .22)})">start</span>` +
          `<span style="padding:4px 8px;border-radius:3px;min-width:90px;background:${mix(c.accent, "#000000", .2)}">▣ kitty</span>` +
          `<span style="padding:4px 8px;border-radius:3px;min-width:90px;background:${mix(c.accent, "#ffffff", .22)}">▤ Files</span><span style="flex:1"></span>` +
          `<span style="height:100%;display:flex;align-items:center;padding:0 10px;background:${mix(c.accent, "#2aa0f0", .45)}">20:14</span>`;
        return wrap;
      }
      case "win7": {
        wrap.style.cssText += `bottom:0;height:26px;display:flex;align-items:center;gap:5px;padding:0 6px;background:${rgba(c.base, .62 * ui)};border-top:1px solid ${rgba(c.text, .25)}`;
        wrap.innerHTML = `<span style="width:20px;height:20px;border-radius:50%;background:radial-gradient(circle,${mix(c.accent, "#ffffff", .55)},${c.accent} 55%,${c.accent2});box-shadow:0 0 6px ${rgba(c.accent, .7)}"></span>` +
          ["▣", "▤", "◉"].map((x, i) => `<span style="width:30px;height:20px;display:grid;place-items:center;border-radius:3px;border:1px solid ${rgba(c.text, i ? .1 : .35)};background:${rgba(c.text, i ? .04 : .14)}">${x}</span>`).join("") +
          `<span style="flex:1"></span><span>20:14</span>`;
        return wrap;
      }
      case "win11": {
        wrap.style.cssText += `bottom:0;height:24px;display:flex;align-items:center;justify-content:center;gap:5px;background:${rgba(c.mantle, .9 * ui)};border-top:1px solid ${rgba(c.text, .08)}`;
        wrap.innerHTML = `<span style="position:absolute;left:10px;color:${c.subtext}">☁ 12°</span>` +
          [["⊞", c.accent], ["⌕", c.text], ["▣", c.text], ["▤", c.text], ["◉", c.text]].map(([x, col], i) => `<span style="width:22px;height:20px;display:grid;place-items:center;border-radius:5px;color:${col};${i === 2 ? `background:${rgba(c.text, .1)};box-shadow:inset 0 -2px 0 ${c.accent}` : ""}">${x}</span>`).join("") +
          `<span style="position:absolute;right:10px">20:14</span>`;
        return wrap;
      }
      case "touch": {
        wrap.style.cssText += `bottom:0;height:34px;display:flex;align-items:center;gap:6px;padding:0 6px;font-size:12px;background:${rgba(c.base, .95 * ui)};border-top:2px solid ${c.surface2}`;
        wrap.innerHTML = `<span style="padding:6px 14px;border-radius:${R}px;background:${c.accent};color:${on(c.accent, c.crust, c)}">☰</span>` +
          [1, 2, 3].map((n, i) => `<span style="padding:6px 12px;border-radius:${R}px;${i ? `background:${c.surface}` : `background:${c.accent};color:${on(c.accent, c.crust, c)}`}">${n}</span>`).join("") +
          `<span style="flex:1"></span><span style="padding:6px 10px;border-radius:${R}px;background:${c.surface}">⌨</span><span style="padding:6px 12px;border-radius:${R}px;background:${c.red};color:${on(c.red, c.crust, c)}">⏻</span>`;
        return wrap;
      }
      case "dread": {
        wrap.style.cssText += `top:0;height:24px;display:flex;align-items:center;gap:3px;padding:0 6px;background:linear-gradient(to bottom,${c.mantle},${c.crust});opacity:${ui};border-bottom:2px solid ${mix(c.orange, c.crust, .45)}`;
        wrap.innerHTML = [1, 2, 3, 4].map((n, i) => `<span style="width:20px;height:17px;display:grid;place-items:center;border:1px solid ${i ? c.surface2 : c.red};${i ? "" : `box-shadow:0 0 6px ${rgba(c.red, .6)};color:${c.red}`};background:${rgba(c.base, .6)}">${n}</span>`).join("") +
          `<span style="flex:1"></span><span style="letter-spacing:1px">20:14</span><span style="flex:1"></span><span style="color:${c.subtext}">HP ▮▮▮▮▯</span><span style="color:${c.red};margin-left:6px">☠</span>`;
        return wrap;
      }
      case "wired": {
        wrap.style.cssText += `top:0;height:20px;display:flex;align-items:center;gap:10px;padding:0 8px;font-weight:500;background:${rgba(c.crust, .96 * ui)};border-bottom:1px solid ${c.accent};color:${c.subtext}`;
        wrap.innerHTML = `<span><span style="color:${c.accent}">[1]</span> 2 3 4</span><span style="flex:1"></span><span>[cpu 09%]</span><span>[vol 40]</span><span style="color:${c.text}">[20:14:07]</span><span style="color:${c.accent}">[shutdown]</span>`;
        return wrap;
      }
      case "cathedral": {
        wrap.style.cssText += `top:0;height:24px;display:flex;align-items:center;gap:12px;padding:0 10px;font-family:"DejaVu Serif",serif;background:linear-gradient(to bottom,${c.surface},${c.crust});opacity:${ui};border-bottom:4px double ${c.accent}`;
        wrap.innerHTML = ROMAN.slice(0, 4).map((n, i) => `<span style="color:${i ? c.subtext : c.accent}">${n}</span>`).join("") +
          `<span style="flex:1"></span><span><span style="color:${c.accent}">✠</span> XX:XIV <span style="color:${c.accent}">✠</span></span><span style="flex:1"></span><span style="color:${c.subtext}">❦</span>`;
        return wrap;
      }
    }
    islands(rgba(c.base, .88 * ui), rgba(c.surface2, .6), 5);
    return wrap;
  }

  // reserved space of the bar → where windows may go
  function area(lay, o) {
    const g = o.gapsOuter + o.gapsInner;
    const a = { top: g, bottom: g, left: g, right: g };
    if (["modern", "glass", "minimal"].includes(lay)) a.top += 30;
    else if (lay === "solid" || lay === "dread" || lay === "cathedral") a.top += 26;
    else if (lay === "wired") a.top += 22;
    else if (lay === "sidebar") a.left += 28;
    else if (lay === "touch") a.bottom += 36;
    else if (lay === "win7") a.bottom += 28;
    else a.bottom += 26;
    return a;
  }

  // ── windows ─────────────────────────────────────────────────────────
  function frame(lay, c, o, title, focused) {
    const bv = bevel(c), R = (["win98", "dread", "wired", "cathedral"].includes(lay) ? 0 : o.radius);
    const w = el("div", `position:absolute;overflow:hidden;display:flex;flex-direction:column;border-radius:${R}px;box-shadow:${o.shadows ? `0 6px 18px ${rgba("#000000", .45)}` : "none"}`);
    let bar = null;
    if (lay === "win98") {
      w.style.border = `2px solid`; w.style.borderColor = `${bv.hi} ${bv.lo} ${bv.lo} ${bv.hi}`;
      bar = el("div", `display:flex;justify-content:space-between;padding:2px 4px;font:700 8px ${o.font};color:${on(bv.title, c.crust, c)};background:${focused ? `linear-gradient(to right,${bv.title},${bv.title2})` : bv.pressed}`, `<span>${esc(title)}</span><span>_ □ x</span>`);
    } else if (lay === "winxp") {
      w.style.border = `2px solid ${c.accent}`; w.style.borderRadius = "7px 7px 0 0";
      bar = el("div", `display:flex;justify-content:space-between;padding:3px 6px;font:italic 700 8px ${o.font};color:${on(c.accent, "#ffffff", c)};background:linear-gradient(to bottom,${mix(c.accent, "#ffffff", .35)},${c.accent} 40%,${mix(c.accent, "#000000", .15)})`, `<span>${esc(title)}</span><span style="background:${c.red};padding:0 3px;border-radius:2px">x</span>`);
    } else if (lay === "win7") {
      w.style.border = `1px solid ${rgba(c.text, .3)}`;
      bar = el("div", `padding:4px 6px;font:600 8px ${o.font};color:${c.text};background:${rgba(c.base, .55)}`, esc(title));
    } else if (o.titleBars) {
      bar = el("div", `padding:2px 6px;font:600 8px ${o.font};color:${focused ? on(c.accent, c.crust, c) : c.subtext};background:${focused ? c.accent : c.surface}`, esc(title));
    }
    if (!["win98", "winxp", "win7"].includes(lay)) {
      const bw = Math.max(1, o.border);
      w.style.border = `${bw}px solid ${focused ? c.accent : c.surface2}`;
    }
    if (bar) w.append(bar);
    const body = el("div", `flex:1;overflow:hidden;background:${rgba(c.base, o.termOpacity)};padding:6px 8px;font:500 8px/1.35 ${o.font};color:${c.text}`);
    w.append(body);
    return [w, body];
  }

  function terminal(body, c, t, user) {
    const a = t.ansi || [];
    const blocks = a.slice(0, 8).map(x => `<span style="background:${x}">&nbsp;&nbsp;</span>`).join("");
    body.innerHTML =
      `<div><span style="color:${c.accent}">${esc(user)}</span> <span style="color:${c.subtext}">in</span> <span style="color:${a[6] || c.cyan}">~/projects</span> <span style="color:${c.green}">❯</span> fastfetch</div>` +
      `<div style="display:flex;gap:10px;margin-top:4px"><pre style="margin:0;font:inherit;color:${c.accent}"> ▄▀▀▀▄\n █ ◉ █\n  ▀▄▀\n ▄███▄</pre><div>` +
      `<div><b style="color:${c.accent}">${esc(user)}</b>@fedora</div><div><span style="color:${c.accent}">OS</span> Fedora 43</div>` +
      `<div><span style="color:${c.accent}">WM</span> Sway</div><div><span style="color:${c.accent}">Theme</span> ${esc(t.label.split(" (")[0])}</div>` +
      `<div style="margin-top:3px">${blocks}</div></div></div>` +
      `<div style="margin-top:4px"><span style="color:${c.accent}">${esc(user)}</span> <span style="color:${c.green}">❯</span> <span class="desk-caret" style="background:${c.text}">&nbsp;</span></div>`;
  }

  function files(body, c) {
    const rows = [["▸ Documents", c.blue], ["▸ Pictures", c.magenta], ["▸ Wallpapers", c.yellow], ["  notes.md", c.text], ["  sway.conf", c.text]];
    body.style.background = rgba(c.mantle, 1);
    body.innerHTML = rows.map(([n, col], i) => `<div style="padding:1px 4px;border-radius:3px;${i === 2 ? `background:${rgba(c.accent, .2)}` : ""};color:${col}">${n}</div>`).join("");
  }

  function notification(lay, c, o) {
    const pos = ["win98", "winxp", "win7", "win11", "touch"].includes(lay) ? "bottom:36px" : "top:34px";
    const bg = lay === "winxp" ? "#ffffe1" : lay === "win98" ? bevel(c).face : (lay === "wired" || lay === "dread") ? c.crust : c.base;
    const fg = lay === "winxp" ? "#000000" : c.text;
    const R = ["win98", "dread", "wired", "cathedral"].includes(lay) ? 0 : o.radius;
    const n = el("div", `position:absolute;right:${10 + o.gapsOuter}px;${pos};width:150px;padding:6px 8px;border-radius:${R}px;font:8px/1.35 ${o.font};color:${fg};
      background:${rgba(bg, (lay === "winxp" ? 1 : .93) * o.ui)};border:${lay === "cathedral" ? "3px double" : "1px solid"} ${lay === "winxp" ? "#000" : c.accent}`);
    const pre = lay === "wired" ? "// " : lay === "dread" ? `<span style="color:${c.accent}">▌</span> ` : "";
    n.innerHTML = `<b>${pre}Theme applied</b><div style="color:${lay === "winxp" ? "#333" : c.subtext}">Every app follows the new look.</div>`;
    return n;
  }

  // ── public: render(container, opts) ─────────────────────────────────
  // opts: theme, layout, settings, wallpaperUrl (or null), compact, notify
  function render(host, opts) {
    const t = opts.theme, s = opts.settings, lay = opts.layout;
    const c = colours(t, s.theme.accent);
    const o = {
      ui: s.look.ui_opacity ?? 1, radius: s.look.radius, gapsInner: Math.min(s.look.gaps_inner, 16), gapsOuter: Math.min(s.look.gaps_outer, 16),
      border: s.look.border, shadows: !!s.look.fx_shadows, titleBars: !!s.look.title_bars, termOpacity: s.look.terminal_opacity ?? .95,
      font: `"${s.theme.font}", "JetBrainsMono Nerd Font", ui-monospace, monospace`,
    };
    const screen = el("div", `position:relative;width:${W}px;height:${H}px;overflow:hidden;background:${c.base};font-family:${o.font}`);
    screen.className = "desk-screen";
    if (opts.wallpaperUrl) {
      const img = el("img", "position:absolute;inset:0;width:100%;height:100%;object-fit:cover");
      img.src = opts.wallpaperUrl; img.alt = ""; img.decoding = "async"; img.loading = "lazy";
      screen.append(img);
    } else {
      screen.style.background = s.theme.wallpaper === "solid" ? c.base : `radial-gradient(ellipse at 30% 20%, ${mix(c.base, c.accent, .25)}, ${c.base} 70%)`;
    }
    const a = area(lay, o), g = o.gapsInner;
    const fullW = W - a.left - a.right, fullH = H - a.top - a.bottom;
    // cards: one window, so the wallpaper shows; big previews: the usual two tiles
    const leftW = Math.round(fullW * (opts.compact ? 0.5 : 0.58));
    const [w1, b1] = frame(lay, c, o, "kitty — ~/projects", true);
    Object.assign(w1.style, { left: a.left + "px", top: a.top + "px", width: (leftW - g / 2) + "px", height: fullH + "px" });
    terminal(b1, c, t, opts.user || "you");
    const [w2, b2] = frame(lay, c, o, "Files", false);
    Object.assign(w2.style, { left: (a.left + leftW + g / 2) + "px", top: a.top + "px", width: (fullW - leftW - g / 2) + "px", height: fullH + "px" });
    files(b2, c);
    if (opts.compact) screen.append(w1, bar(lay, c, o));
    else screen.append(w1, w2, bar(lay, c, o));
    if (opts.notify) screen.append(notification(lay, c, o));
    host.replaceChildren(screen);
    return screen;
  }

  return { render, colours, on, mix, rgba, contrast, W, H };
})();
