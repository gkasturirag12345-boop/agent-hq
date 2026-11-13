// Agent HQ: pixel-art office. Original sprites drawn in code; no image assets.
// Rule: motion and lamps come only from observed data (transcript metadata); boards and trays only from
// recorded Markdown. Nothing here invents activity.
'use strict';

(function () {
  const W = 400, H = 225;                 // logical pixel canvas
  const AGENT_W = 262;                    // agent floor width; project wing to the right
  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const PAL = {
    light: { wall: '#c9bfa4', wallTop: '#a89e83', floor: '#ddd3b8', floorAlt: '#d4c9ac', carpet: '#b9c4cf', carpetAlt: '#aeb9c5',
      wood: '#a8754a', woodDark: '#7d5534', woodTop: '#c48f5f', ink: '#2a2633', screenOff: '#3b3a45', screenOn: '#9fd3f0',
      screenDim: '#5f7f96', chair: '#4b4f63', board: '#f4efe0', boardFrame: '#6b5a44', paper: '#fbfaf4', text: '#2a2633', muted: '#6b6475',
      bubble: '#ffffff', shadow: 'rgba(0,0,0,0.18)', door: '#5c4b3a' },
    dark: { wall: '#2e2a3d', wallTop: '#23202f', floor: '#3a3548', floorAlt: '#353043', carpet: '#2d3a4a', carpetAlt: '#293545',
      wood: '#7a5537', woodDark: '#5a3d27', woodTop: '#946845', ink: '#0b0a10', screenOff: '#1c1b24', screenOn: '#6fb8e6',
      screenDim: '#3c5468', chair: '#2b2e3d', board: '#d9d2c0', boardFrame: '#4a3d2e', paper: '#e9e6dc', text: '#ece7f5', muted: '#a59eb4',
      bubble: '#f4f1fa', shadow: 'rgba(0,0,0,0.35)', door: '#3d3226' },
  };
  const LAMP = { active: '#3fd15a', recent: '#4a8ff0', idle: '#e0a73a', dormant: '#8a8494', ended: '#8a8494', unknown: '#f06176', none: null };
  const STATUS_COL = { TODO: '#8a8494', IN_PROGRESS: '#2f6fd1', NEEDS_CONTEXT: '#7d4bc4', IN_REVIEW: '#d39a1c',
    REVISION_REQUIRED: '#d9622b', BLOCKED: '#c2364b', APPROVED: '#1aa198', DONE: '#3a9a46' };

  // Character looks: body colour, hair, skin and a prop. Unknown agent names get a generic look.
  const LOOKS = {
    researcher: { body: '#7d4bc4', dark: '#5a3391', hair: '#3b2a1e', skin: '#e9b98f', prop: 'glasses-book' },
    coder: { body: '#2f6fd1', dark: '#21509a', hair: '#1d1b22', skin: '#c98d62', prop: 'headphones' },
    verifier: { body: '#b3263a', dark: '#83192a', hair: '#8a5a2b', skin: '#f0c9a4', prop: 'magnifier' },
    analyst: { body: '#c08514', dark: '#8d600c', hair: '#5a3a22', skin: '#a8714c', prop: 'tie-chart' },
    'technical-writer': { body: '#138a83', dark: '#0c625d', hair: '#c46b2c', skin: '#efc19b', prop: 'quill' },
    'workspace-manager': { body: '#5b6b2e', dark: '#40501d', hair: '#2a2420', skin: '#d7a275', prop: 'hardhat' },
    'context-integrator': { body: '#8a4b2e', dark: '#663520', hair: '#e1c16e', skin: '#b67a52', prop: 'plug' },
    orchestrator: { body: '#2f2b3a', dark: '#1d1a26', hair: '#4a4a52', skin: '#d9a77c', prop: 'headset' },
  };
  function lookFor(name) {
    if (LOOKS[name]) return LOOKS[name];
    let hsh = 0; for (const c of String(name)) hsh = (hsh * 31 + c.charCodeAt(0)) >>> 0;
    const hue = hsh % 360;
    return { body: `hsl(${hue},45%,45%)`, dark: `hsl(${hue},45%,32%)`, hair: '#3a3030', skin: '#d8a57a', prop: null };
  }

  let canvas, ctx, off, octx, wrap, tip, scale = 1, theme = PAL.light;
  let model = { agents: [], projects: [], live: null, liveError: null, focus: null };
  let hits = [], frame = 0, timer = null, listening = false, observer = null;

  // ---------- low-level pixel helpers (logical coordinates on the offscreen canvas) ----------
  function px(x, y, w, h, c) { octx.fillStyle = c; octx.fillRect(x, y, w, h); }

  function drawCharacter(x, y, look, typing, dim) {
    // 14 x 15 sprite, top-left at (x, y); seated, lower body hidden by the desk
    octx.globalAlpha = dim ? 0.45 : 1;
    const bob = typing ? (frame % 2) : 0;
    const hx = x + 3, hy = y + 2 + bob;                     // head origin
    px(hx + 1, hy - 1, 6, 2, look.hair);                    // hair top
    px(hx, hy, 8, 6, look.skin);                            // face
    px(hx, hy, 8, 2, look.hair);                            // fringe
    px(hx, hy + 2, 1, 2, look.hair); px(hx + 7, hy + 2, 1, 2, look.hair);
    px(hx + 2, hy + 3, 1, 1, theme.ink); px(hx + 5, hy + 3, 1, 1, theme.ink);   // eyes
    px(hx + 3, hy + 5, 2, 1, look.dark);                    // mouth
    px(x + 5, y + 8 + bob, 4, 1, look.skin);                // neck
    px(x + 2, y + 9 + bob, 10, 6, look.body);               // torso
    px(x + 2, y + 9 + bob, 10, 1, look.dark);
    const handY = y + 12 + (typing ? (frame % 2 ? 0 : 1) : 1);
    px(x + 1, y + 10 + bob, 2, 3, look.body); px(x + 11, y + 10 + bob, 2, 3, look.body);   // arms
    px(x + 1, handY, 2, 2, look.skin); px(x + 11, handY + (typing ? (frame % 2 ? 1 : -1) : 0), 2, 2, look.skin);
    drawProp(x, y + bob, hx, hy, look);
    octx.globalAlpha = 1;
  }

  function drawProp(x, y, hx, hy, look) {
    switch (look.prop) {
      case 'glasses-book':
        px(hx + 1, hy + 3, 3, 1, '#222'); px(hx + 4, hy + 3, 3, 1, '#222');
        px(hx + 2, hy + 3, 1, 1, '#9fd3f0'); px(hx + 5, hy + 3, 1, 1, '#9fd3f0');
        px(x + 3, y + 11, 5, 4, '#f4efe0'); px(x + 5, y + 11, 1, 4, look.dark);        // open book
        break;
      case 'headphones':
        px(hx, hy - 2, 8, 1, '#1b1b1b'); px(hx - 1, hy + 2, 2, 3, '#e4572e'); px(hx + 7, hy + 2, 2, 3, '#e4572e');
        break;
      case 'magnifier':
        px(x + 12, y + 7, 3, 1, '#c9c9c9'); px(x + 12, y + 10, 3, 1, '#c9c9c9');
        px(x + 11, y + 8, 1, 2, '#c9c9c9'); px(x + 15, y + 8, 1, 2, '#c9c9c9');
        px(x + 12, y + 8, 3, 2, '#bfe6ff'); px(x + 12, y + 11, 1, 3, '#6b4a2b');       // lens + handle
        break;
      case 'tie-chart':
        px(x + 6, y + 9, 2, 5, '#2a2633');
        px(x - 3, y + 6, 4, 6, '#f4efe0'); px(x - 2, y + 9, 1, 2, '#3a9a46'); px(x - 1, y + 8, 1, 3, '#2f6fd1'); px(x, y + 7, 1, 4, '#c2364b');
        break;
      case 'quill':
        px(x + 13, y + 3, 1, 1, '#ffffff'); px(x + 12, y + 4, 2, 2, '#ffffff'); px(x + 12, y + 6, 1, 4, '#ffffff'); px(x + 12, y + 10, 1, 2, '#2a2633');
        break;
      case 'hardhat':
        px(hx - 1, hy - 2, 10, 3, '#f2c12e'); px(hx - 2, hy, 12, 1, '#d9a514'); px(hx + 3, hy - 3, 2, 1, '#f2c12e');
        break;
      case 'plug':
        px(x + 13, y + 9, 2, 3, '#3a3a3a'); px(x + 13, y + 8, 1, 1, '#c9c9c9'); px(x + 14, y + 8, 1, 1, '#c9c9c9');
        px(x + 14, y + 12, 1, 3, '#2fbf71');
        break;
      case 'headset':
        px(hx, hy - 2, 8, 1, '#111'); px(hx - 1, hy + 2, 1, 3, '#111'); px(hx - 1, hy + 5, 3, 1, '#111'); px(hx + 2, hy + 5, 1, 1, '#ff5d5d');
        px(x + 8, y + 10, 2, 2, '#f2c12e');                                             // badge
        break;
    }
  }

  function drawDesk(x, y, w, state, glowFrame) {
    // chair back is drawn before the character; desk and monitor after
    const mx = x + w - 13, my = y - 9;
    px(mx + 4, my + 8, 3, 2, theme.ink);                     // monitor stand
    px(mx, my, 11, 8, theme.ink);                            // monitor frame
    let scr = theme.screenOff;
    if (state === 'active' || state === 'recent') scr = theme.screenOn;
    else if (state === 'idle' || state === 'endedRecent') scr = theme.screenDim;
    px(mx + 1, my + 1, 9, 6, scr);
    if (state === 'active') {                                 // scrolling code lines: only when observed active
      for (let i = 0; i < 3; i++) {
        const len = 2 + ((glowFrame + i * 3) % 6);
        px(mx + 2, my + 2 + i * 2, len, 1, '#2a6f9e');
      }
    }
    px(x, y, w, 3, theme.woodTop);                           // desk top
    px(x, y + 3, w, 8, theme.wood);
    px(x + 1, y + 4, w - 2, 1, theme.woodDark);
    px(x + 2, y + 11, 2, 3, theme.woodDark); px(x + w - 4, y + 11, 2, 3, theme.woodDark);
    px(x + 4, y + 1, 7, 1, '#4b4b55');                       // keyboard
    return { mx, my };
  }

  function lampAt(x, y, state) {
    const c = LAMP[state] || null;
    if (!c) { px(x, y, 3, 3, theme.ink); px(x + 1, y + 1, 1, 1, theme.screenOff); return; }
    px(x - 1, y - 1, 5, 5, theme.ink); px(x, y, 3, 3, c);
  }

  // ---------- state from data ----------
  function obsFor(name) {
    const live = model.live;
    if (!live) return { state: 'nodata', run: null };                 // not fetched yet, or fetch failed
    if (!live.available) return { state: 'nofolder', run: null };     // no transcript folder on this Mac
    if (name === 'orchestrator') {
      const s = live.sessions[0];
      return s ? { state: s.state, run: s } : { state: 'none', run: null };
    }
    const r = Object.prototype.hasOwnProperty.call(live.agents, name) ? live.agents[name] : null;
    if (!r) return { state: 'none', run: null };
    return { state: r.state, run: r };
  }
  function screenState(o) {
    if (o.state === 'ended') return o.run && o.run.age_s < 3600 ? 'endedRecent' : 'off';
    return o.state;
  }

  // ---------- layout ----------
  function layout() {
    const names = model.agents.map(a => a.name).filter(n => typeof n === 'string' && n);
    const cols = Math.min(4, Math.max(1, Math.ceil(names.length / 2)));
    const rows = Math.ceil(names.length / cols);
    const deskW = 40, cellW = Math.floor((AGENT_W - 16) / cols), rowH = Math.min(52, Math.floor(118 / Math.max(1, rows)));
    const desks = names.map((n, i) => {
      const c = i % cols, r = Math.floor(i / cols);
      const inRow = Math.min(cols, names.length - r * cols);
      const offset = Math.floor((cols - inRow) * cellW / 2);
      return { name: n, x: 8 + offset + c * cellW + Math.floor((cellW - deskW) / 2), y: 64 + r * rowH, w: deskW };
    });
    const orch = { name: 'orchestrator', x: Math.floor(AGENT_W / 2) - 26, y: 64 + rows * rowH + 6, w: 52 };
    return { desks, orch };
  }

  // ---------- full redraw ----------
  function draw() {
    hits = [];
    octx.clearRect(0, 0, W, H);
    // walls and floor
    px(0, 0, W, 40, theme.wall); px(0, 36, W, 4, theme.wallTop);
    for (let y = 40; y < H; y += 8) for (let x = 0; x < AGENT_W; x += 8) px(x, y, 8, 8, ((x + y) / 8) % 2 ? theme.floor : theme.floorAlt);
    // windows and sign on the agent side
    for (let i = 0; i < 2; i++) { const wx = 70 + i * 90; px(wx, 8, 34, 20, theme.ink); px(wx + 2, 10, 14, 16, '#8fc7e8'); px(wx + 18, 10, 14, 16, '#8fc7e8'); }
    // Layer A door (role marker only; not a reachability indicator)
    px(14, 10, 22, 30, theme.door); px(16, 12, 18, 28, theme.woodDark); px(31, 26, 2, 2, '#f2c12e');
    hits.push({ x: 14, y: 10, w: 22, h: 30, kind: 'door' });

    const L = layout();
    const items = L.desks.concat([L.orch]);
    const texts = [];
    items.forEach(d => {
      const o = obsFor(d.name);
      const look = lookFor(d.name);
      const st = screenState(o);
      px(d.x + 9, d.y - 15, 14, 12, theme.chair);                         // chair back
      const typing = o.state === 'active' && !reduceMotion;
      drawCharacter(d.x + 9, d.y - 15, look, typing, o.state === 'none');
      const { mx, my } = drawDesk(d.x, d.y, d.w, st, frame);
      lampAt(mx + 12, my, o.state);
      px(d.x + 2, d.y + 15, d.w - 4, 1, theme.shadow);
      hits.push({ x: d.x, y: d.y - 18, w: d.w, h: 34, kind: 'agent', name: d.name, obs: o });
      texts.push({ x: d.x + d.w / 2, y: d.y + 20, text: d.name, kind: 'label', maxW: d.w + 10 });
      if ((o.state === 'active' || o.state === 'recent') && o.run && o.run.last_tool) {
        texts.push({ x: d.x + 16, y: d.y - 22, text: o.run.last_tool, kind: 'bubble', state: o.state });
      } else if (o.state === 'unknown') {
        texts.push({ x: d.x + 16, y: d.y - 22, text: '?', kind: 'bubble', state: 'unknown' });
      } else if (o.state === 'dormant' || (o.state === 'ended' && st === 'off')) {
        texts.push({ x: d.x + 24, y: d.y - 18, text: 'zz', kind: 'zz' });
      }
    });
    // the context-integrator's cable to the Layer A door (static role marker)
    const ci = L.desks.find(d => d.name === 'context-integrator');
    if (ci) { octx.globalAlpha = 0.5; for (let x = 36; x < ci.x + 4; x += 4) px(x, 41, 2, 1, '#2fbf71'); for (let y = 41; y < ci.y; y += 4) px(ci.x + 2, y, 1, 2, '#2fbf71'); octx.globalAlpha = 1; }

    drawProjects(texts);
    if (model.live === null || (model.live && !model.live.available)) {   // say plainly that nothing can be observed
      const msg = model.live === null ? (model.liveError ? 'LIVE DATA UNAVAILABLE — lamps off, activity unknown' : 'WAITING FOR LIVE DATA')
        : 'NO TRANSCRIPT FOLDER ON THIS MAC — activity unknown';
      texts.push({ x: AGENT_W / 2, y: H - 8, text: msg, kind: 'banner' });
    }
    blit(texts);
  }

  function drawProjects(texts) {
    const x0 = AGENT_W, w = W - AGENT_W;
    px(x0, 0, 3, H, theme.ink);                                           // dividing wall
    const ps = model.projects;
    const n = Math.max(1, ps.length);
    const roomH = Math.floor((H - 2) / n);
    ps.forEach((p, i) => {
      const y = i * roomH + 1, focus = model.focus === p.slug;
      for (let yy = y; yy < y + roomH; yy += 6) for (let xx = x0 + 3; xx < W; xx += 6) px(xx, yy, 6, 6, ((xx + yy) / 6) % 2 ? theme.carpet : theme.carpetAlt);
      px(x0 + 3, y, w - 3, 2, theme.ink);
      // task board: one column per status, a note per task (recorded counts only)
      const bx = x0 + 10, by = y + 16, bw = w - 20, bh = Math.max(30, Math.min(54, roomH - 52));
      px(bx - 2, by - 2, bw + 4, bh + 4, theme.boardFrame); px(bx, by, bw, bh, theme.board);
      const statuses = Object.keys(STATUS_COL), colW = Math.floor(bw / statuses.length);
      const counts = {}; p.board.tasks.forEach(t => { counts[t.status] = (counts[t.status] || 0) + 1; });
      const other = p.board.tasks.filter(t => !STATUS_COL[t.status]).length;
      if (other) { counts['?'] = other; texts.push({ x: bx + bw - 4, y: by - 6, text: `?${other}`, kind: 'col' }); }
      statuses.forEach((s, k) => {
        const cx = bx + k * colW + 1;
        px(cx, by + 1, colW - 2, 2, STATUS_COL[s]);
        texts.push({ x: cx + (colW - 2) / 2, y: by + bh - 3, text: COL_ABBR[s] + (counts[s] ? counts[s] : ''), kind: 'col' });
        for (let j = 0; j < Math.min(counts[s] || 0, Math.floor((bh - 6) / 5)); j++) px(cx + 1, by + 5 + j * 5, colW - 4, 4, STATUS_COL[s]);
      });
      hits.push({ x: bx, y: by, w: bw, h: bh, kind: 'board', project: p, counts });
      // handoff tray: one sheet per recorded handoff (capped), red edge if any checker failure
      const tx = x0 + 12, ty = by + bh + 12;
      const failed = p.handoffs.filter(hf => hf.checker !== 'PASS').length;
      px(tx - 2, ty + 10, 30, 3, theme.woodDark);
      for (let j = 0; j < Math.min(p.handoffs.length, 10); j++) px(tx, ty + 9 - j, 26, 1, j % 2 ? theme.paper : '#e6e1d2');
      if (failed) px(tx + 24, ty, 2, 10, '#c2364b');
      hits.push({ x: tx - 2, y: ty - 2, w: 30, h: 15, kind: 'tray', project: p, failed });
      // warning sign for recorded inconsistencies
      if (p.warnings.length) {
        const sx = x0 + w - 26, sy = by + bh + 8;
        for (let r = 0; r < 9; r++) px(sx + 8 - r, sy + r, 2 * r + 1, 1, '#f2c12e');
        px(sx + 8, sy + 3, 1, 3, theme.ink); px(sx + 8, sy + 7, 1, 1, theme.ink);
        hits.push({ x: sx, y: sy, w: 17, h: 9, kind: 'warn', project: p });
      }
      if (focus) { octx.globalAlpha = 0.9; px(x0 + 3, y, w - 3, 1, '#f2c12e'); px(x0 + 3, y + roomH - 1, w - 3, 1, '#f2c12e'); px(W - 1, y, 1, roomH, '#f2c12e'); octx.globalAlpha = 1; }
      hits.push({ x: x0 + 3, y, w: w - 3, h: roomH, kind: 'room', project: p });
      texts.push({ x: x0 + 10, y: y + 10, text: (p.registry && p.registry.Title) || p.slug, kind: 'room' });
      texts.push({ x: tx + 34, y: ty + 9, text: `${p.handoffs.length} handoffs` + (failed ? ` · ${failed} incomplete` : ''), kind: 'small' });
    });
    if (!ps.length) texts.push({ x: x0 + 10, y: 20, text: 'no projects found', kind: 'room' });
  }

  const SHORT = { 'technical-writer': 'writer', 'workspace-manager': 'ws-mgr', 'context-integrator': 'context', orchestrator: 'orch', researcher: 'research' };
  function fitLabel(name, maxPx) {
    const opts = [name, SHORT[name] || name, name.split('-').map(w => w[0]).join('').toUpperCase()];
    return opts.find(o => ctx.measureText(o).width + 6 <= maxPx) || opts[2];
  }
  const COL_ABBR = { TODO: 'T', IN_PROGRESS: 'P', NEEDS_CONTEXT: 'C', IN_REVIEW: 'R', REVISION_REQUIRED: 'V', BLOCKED: 'B', APPROVED: 'A', DONE: 'D' };

  // offscreen (logical) -> visible canvas at integer scale, then crisp text on top
  function blit(texts) {
    ctx.imageSmoothingEnabled = false;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(off, 0, 0, W * scale, H * scale);
    ctx.textBaseline = 'middle';
    texts.forEach(t => {
      const X = t.x * scale, Y = t.y * scale;
      if (t.kind === 'label') {
        ctx.font = `bold ${Math.max(9, 3.4 * scale)}px ui-monospace, Menlo, monospace`; ctx.textAlign = 'center';
        const label = fitLabel(t.text, t.maxW * scale);
        const wdt = ctx.measureText(label).width + 6;
        ctx.fillStyle = theme.board; ctx.fillRect(X - wdt / 2, Y - 2.6 * scale, wdt, 5.2 * scale);
        ctx.fillStyle = '#2a2633'; ctx.fillText(label, X, Y);
      } else if (t.kind === 'bubble') {
        ctx.font = `bold ${Math.max(9, 3.4 * scale)}px ui-monospace, Menlo, monospace`; ctx.textAlign = 'center';
        const wdt = ctx.measureText(t.text).width + 8, hgt = 6 * scale;
        ctx.fillStyle = '#2a2633'; ctx.fillRect(X - wdt / 2 - 2, Y - hgt / 2 - 2, wdt + 4, hgt + 4);
        ctx.fillStyle = t.state === 'unknown' ? '#ffd9df' : theme.bubble; ctx.fillRect(X - wdt / 2, Y - hgt / 2, wdt, hgt);
        ctx.fillStyle = '#2a2633'; ctx.fillRect(X - 2, Y + hgt / 2 + 2, 4, scale * 1.5);
        ctx.fillText(t.text, X, Y);
      } else if (t.kind === 'banner') {
        ctx.font = `bold ${Math.max(9, 3.4 * scale)}px ui-monospace, Menlo, monospace`; ctx.textAlign = 'center';
        const wdt = ctx.measureText(t.text).width + 12;
        ctx.fillStyle = '#c2364b'; ctx.fillRect(X - wdt / 2, Y - 3.5 * scale, wdt, 7 * scale);
        ctx.fillStyle = '#ffffff'; ctx.fillText(t.text, X, Y);
      } else if (t.kind === 'col') {
        ctx.font = `bold ${Math.max(7, 2.6 * scale)}px ui-monospace, Menlo, monospace`; ctx.textAlign = 'center';
        ctx.fillStyle = '#2a2633'; ctx.fillText(t.text, X, Y);
      } else if (t.kind === 'zz') {
        ctx.font = `bold ${Math.max(9, 3.6 * scale)}px ui-monospace, Menlo, monospace`; ctx.textAlign = 'left';
        ctx.fillStyle = theme.muted; ctx.fillText(t.text, X, Y);
      } else if (t.kind === 'room') {
        ctx.font = `bold ${Math.max(9, 3.6 * scale)}px ui-monospace, Menlo, monospace`; ctx.textAlign = 'left';
        let txt = t.text; const maxPx = (W - t.x - 6) * scale;
        while (txt.length > 4 && ctx.measureText(txt).width > maxPx) txt = txt.slice(0, -2) + '…';
        ctx.fillStyle = theme.text; ctx.fillText(txt, X, Y);
      } else {
        ctx.font = `${Math.max(8, 3 * scale)}px ui-monospace, Menlo, monospace`; ctx.textAlign = 'left';
        ctx.fillStyle = theme.text; ctx.fillText(t.text, X, Y);
      }
    });
    ctx.textAlign = 'left'; ctx.font = `bold ${Math.max(9, 3.6 * scale)}px ui-monospace, Menlo, monospace`;
    ctx.fillStyle = theme.text; ctx.fillText('AGENT FLOOR', 44 * scale, 20 * scale);
    ctx.font = `${Math.max(8, 2.8 * scale)}px ui-monospace, Menlo, monospace`; ctx.fillStyle = theme.text;
    ctx.fillText('LAYER A', 13 * scale, 6 * scale);
  }

  // ---------- tooltip ----------
  const AGO = s => s === null || s === undefined ? 'not recorded' : s < 60 ? `${s} s ago` : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : `${Math.floor(s / 86400)} d ago`;
  function tipLines(hit) {
    if (hit.kind === 'agent') {
      const a = model.agents.find(x => x.name === hit.name);
      const o = hit.obs, lines = [[hit.name, 'title']];
      if (a) lines.push([`model ${a.model || 'not recorded'} · ${a.tools.includes('Write') || a.tools.includes('Edit') ? 'can write' : 'read-only'}`]);
      if (hit.name === 'orchestrator') lines.push(['main Claude Code session (routes work; not an agent definition)']);
      lines.push(['OBSERVED (transcript metadata)', 'head']);
      if (o.state === 'nodata') lines.push([model.liveError ? `live data unavailable (${model.liveError}) — activity cannot be observed` : 'waiting for live data']);
      else if (o.state === 'nofolder') lines.push(['no transcript folder for this workspace on this Mac — activity cannot be observed']);
      else if (o.state === 'none') lines.push([hit.name === 'orchestrator' ? 'no workspace session in the live window' : 'no sub-agent run found in the transcripts']);
      else lines.push([`${o.state} · last write ${AGO(o.run.age_s)}`],
        [o.run.tool_read === false ? 'tool not read (older than 24 h)' : o.run.last_tool ? `last tool ${o.run.last_tool}` : 'no tool call in recent records']);
      if (a) {
        lines.push(['RECORDED (Markdown)', 'head']);
        const lh = a.last_handoff;
        const v = x => (x === null || x === undefined || x === '') ? 'not recorded' : x;
        lines.push([lh ? `last handoff ${lh.file.slice(0, 13)} · ${v(lh.task_id)} · agent says ${v(lh.status)}` : 'no recorded handoffs']);
        if (a.owned_tasks.length) lines.push([`named in Owner: ${a.owned_tasks.map(t => `${v(t.id)} ${v(t.status)}`).join(', ')}`]);
      }
      return lines;
    }
    const p = hit.project;
    if (hit.kind === 'board') {
      const lines = [[`${p.slug} task board`, 'title'], ['RECORDED (TASK_BOARD.md)', 'head']];
      Object.keys(STATUS_COL).forEach(s => { if (hit.counts[s]) lines.push([`${s} ×${hit.counts[s]}`, 'status', STATUS_COL[s]]); });
      if (hit.counts['?']) lines.push([`unrecognised status ×${hit.counts['?']} (see the inconsistency list)`]);
      if (!p.board.tasks.length) lines.push(['no tasks recorded']);
      lines.push(['click to open the project view']);
      return lines;
    }
    if (hit.kind === 'tray') return [[`${p.slug} handoffs`, 'title'], [`${p.handoffs.length} recorded handoffs`],
      [!p.handoffs.length ? 'no handoffs recorded' : hit.failed ? `${hit.failed} fail the handoff checker` : 'all pass the handoff checker']];
    if (hit.kind === 'warn') return [[`${p.slug}: ${p.warnings.length} inconsistenc${p.warnings.length === 1 ? 'y' : 'ies'}`, 'title'], ...p.warnings.slice(0, 4).map(w => [w.text])];
    if (hit.kind === 'room') return [[(p.registry && p.registry.Title) || p.slug, 'title'], [p.slug], ['click to open the project view']];
    if (hit.kind === 'door') return [['Layer A door', 'title'], ['original sources (local files, servers), reached only through the context-integrator'], ['decoration: not a reachability indicator']];
    return [];
  }
  function showTip(hit, ev) {
    if (!hit) { tip.hidden = true; return; }
    tip.replaceChildren();
    tipLines(hit).forEach(([text, kind, color]) => {
      const d = document.createElement('div');
      d.className = 'tip-' + (kind || 'line'); d.textContent = text;
      if (color) d.style.borderLeftColor = color;
      tip.appendChild(d);
    });
    tip.hidden = false;
    const r = wrap.getBoundingClientRect();
    let left = ev.clientX - r.left + 14, top = ev.clientY - r.top + 14;
    if (left + tip.offsetWidth > r.width) left = Math.max(0, ev.clientX - r.left - tip.offsetWidth - 14);
    if (top + tip.offsetHeight > r.height) top = Math.max(0, ev.clientY - r.top - tip.offsetHeight - 14);
    tip.style.left = left + 'px'; tip.style.top = top + 'px';
  }
  function hitAt(ev) {
    const r = canvas.getBoundingClientRect();
    const lx = (ev.clientX - r.left) * W / r.width, ly = (ev.clientY - r.top) * H / r.height;
    const order = ['agent', 'warn', 'tray', 'board', 'door', 'room'];
    return hits.filter(hh => lx >= hh.x && lx < hh.x + hh.w && ly >= hh.y && ly < hh.y + hh.h)
      .sort((a, b) => order.indexOf(a.kind) - order.indexOf(b.kind))[0] || null;
  }

  // ---------- sizing, theme, loop ----------
  function resize() {
    const cssW = Math.max(200, wrap.clientWidth);
    const dpr = window.devicePixelRatio || 1;
    scale = Math.max(1, Math.floor(cssW * dpr / W));
    canvas.width = W * scale; canvas.height = H * scale;
    canvas.style.width = '100%'; canvas.style.aspectRatio = `${W} / ${H}`;
    draw();
  }
  function pickTheme() {
    const forced = document.documentElement.dataset.theme;
    const dark = forced ? forced === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
    theme = dark ? PAL.dark : PAL.light;
  }
  function anyActive() {
    return model.agents.some(a => obsFor(a.name).state === 'active') || obsFor('orchestrator').state === 'active';
  }
  function tick() {
    frame++;
    if (anyActive()) draw();                // animation only while something is observed active
  }

  window.AgentScene = {
    mount(container, data) {
      wrap = document.createElement('div'); wrap.className = 'scene-wrap';
      canvas = document.createElement('canvas'); canvas.className = 'scene';
      canvas.setAttribute('role', 'img');
      canvas.setAttribute('aria-label', 'Pixel-art office: agent desks with observed activity lamps, and project rooms with recorded task boards. The same information is listed in text below.');
      tip = document.createElement('div'); tip.className = 'scene-tip'; tip.hidden = true;
      wrap.append(canvas, tip); container.appendChild(wrap);
      ctx = canvas.getContext('2d');
      off = document.createElement('canvas'); off.width = W; off.height = H; octx = off.getContext('2d');
      model = Object.assign(model, data);
      pickTheme();
      canvas.addEventListener('mousemove', ev => { const hh = hitAt(ev); showTip(hh, ev); canvas.style.cursor = hh && (hh.kind === 'room' || hh.kind === 'board') ? 'pointer' : 'default'; });
      canvas.addEventListener('mouseleave', () => showTip(null));
      canvas.addEventListener('click', ev => { const hh = hitAt(ev); if (hh && hh.project && (hh.kind === 'room' || hh.kind === 'board')) location.href = '/p/' + encodeURIComponent(hh.project.slug); });
      if (observer) observer.disconnect();                       // one observer for the current canvas only
      if (window.ResizeObserver) { observer = new ResizeObserver(resize); observer.observe(wrap); }
      if (!listening) {                                         // page-level listeners are added once
        listening = true;
        if (!window.ResizeObserver) window.addEventListener('resize', () => wrap && resize());
        window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => { pickTheme(); if (ctx) draw(); });
      }
      resize();
      if (!timer && !reduceMotion) timer = setInterval(tick, 300);
    },
    setLive(live, error) { model.live = live; model.liveError = error || null; if (ctx) draw(); },
  };
})();
