// League editor: edits a game's leagues, teams, logos and map positions in the
// league database (served by tools/editor/server.py) and keeps the game view in
// sync. Same data files and branding lookup as the game itself.

import { toPixel } from './projection.js';
import * as brand from './branding.js';

const $ = (s) => document.querySelector(s);
const params = new URLSearchParams(location.search);

let info;                 // api/info
let maps;                 // data/maps.json views
let gameId;
let D = null;             // { game, territories, leagues, teams, badges } - whole files
let sel = { league: null, team: null };
let viewId = null;
let cam = { k: 1, tx: 0, ty: 0 };
let placing = null;       // { kind: 'team' | 'badge', id }
const undoStack = [];
let dirty = false;
let saveTimer = null;

// ---------------------------------------------------------------- helpers
function h(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props ?? {})) {
    if (v == null || v === false) continue;
    if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
    else if (k === 'class') e.className = v;
    else if (k in e && typeof v !== 'string') e[k] = v;
    else e.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c instanceof Node ? c : String(c));
  return e;
}

function toast(msg, error = false) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.toggle('error', error);
  t.classList.add('on');
  clearTimeout(toast.t);
  toast.t = setTimeout(() => t.classList.remove('on'), error ? 6000 : 2800);
}

async function api(path, body, raw = false) {
  const res = await fetch(`api/${path}`, {
    method: body === undefined ? 'GET' : 'POST',
    body: body === undefined ? undefined : raw ? body : JSON.stringify(body),
  });
  const out = await res.json().catch(() => ({ error: `HTTP ${res.status}` }));
  if (!res.ok || out.error) throw new Error(out.error ?? `HTTP ${res.status}`);
  return out;
}

const slug = (s) => String(s).normalize('NFKD').replace(/[̀-ͯ]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || 'item';
function uniqueId(base, taken) {
  let id = slug(base), n = 2;
  while (taken(id)) id = `${slug(base)}-${n++}`;
  return id;
}

const leagues = () => D.leagues.leagues;
const teams = () => D.teams.teams;
const badges = () => D.badges.badges;
const territories = () => D.territories.territories;
const league = (id) => leagues().find((l) => l.id === id);
const team = (id) => teams().find((t) => t.id === id);
const badgeOf = (lid) => badges().find((b) => b.league === lid);
const clubsOf = (lg) => (lg.clubs?.length ? lg.clubs : teams().filter((t) => t.league === lg.id).map((t) => t.id)).map(team).filter(Boolean);
const mapOf = (vid) => maps[D.game.views[vid]?.map];

/** Re-point the branding lookup at the logos currently in the data. */
function refreshLogos() {
  brand.useGameLogos({ leagues: new Map(leagues().map((l) => [l.id, l])), teams: new Map(teams().map((t) => [t.id, t])) });
}
const logoSrc = (key, label, size = 64) => brand.src(key, size, label).src;
function logoImg(key, label, size = 64) {
  const i = h('img', { src: logoSrc(key, label, size), alt: '' });
  brand.applyPlate(i, key);
  return i;
}

// ------------------------------------------------------- projection maths
/** Image pixel -> [lon, lat] on a map: Newton steps on the forward projection. */
function toLonLat(map, x, y, guess) {
  let best = guess;
  if (!best) {
    let bd = Infinity;
    for (let lo = -180; lo <= 180; lo += 5) for (let la = -60; la <= 85; la += 5) {
      const p = toPixel(map, lo, la);
      const d = Math.hypot(p[0] - x, p[1] - y);
      if (d < bd) { bd = d; best = [lo, la]; }
    }
  }
  let [lo, la] = best;
  for (let i = 0; i < 40; i++) {
    const p = toPixel(map, lo, la);
    const ex = x - p[0], ey = y - p[1];
    if (Math.hypot(ex, ey) < 0.05) break;
    const e = 0.01;
    const px = toPixel(map, lo + e, la), py = toPixel(map, lo, la + e);
    const a = (px[0] - p[0]) / e, b = (py[0] - p[0]) / e, c = (px[1] - p[1]) / e, d = (py[1] - p[1]) / e;
    const det = a * d - b * c;
    if (!det) break;
    let dlo = (d * ex - b * ey) / det, dla = (-c * ex + a * ey) / det;
    const step = Math.hypot(dlo, dla);
    if (step > 5) { dlo *= 5 / step; dla *= 5 / step; }
    lo += dlo; la = Math.max(-85, Math.min(85, la + dla));
  }
  return [Math.round(lo * 10000) / 10000, Math.round(la * 10000) / 10000];
}

/** Where a team or badge sits on a view, in image pixels (or null). */
function posOf(item, vid, lonlatKey) {
  if (item.position?.[vid]) return item.position[vid];
  const ll = item[lonlatKey];
  return ll ? toPixel(mapOf(vid), ll[0], ll[1]) : null;
}

// ------------------------------------------------------- change tracking
const snapshot = () => JSON.stringify({ l: D.leagues, t: D.teams, b: D.badges });

/** Every edit goes through here: undo point, logos, redraw, (auto)save. */
function change(fn, { redraw = true } = {}) {
  undoStack.push(snapshot());
  if (undoStack.length > 100) undoStack.shift();
  fn();
  for (const lg of leagues()) if (lg.teamCount && typeof lg.teamCount === 'object' && lg.clubs) lg.teamCount.value = lg.clubs.length;
  refreshLogos();
  setDirty(true);
  if (redraw) renderAll();
  else { renderList(); drawMarkers(); }
}

function undo() {
  const s = undoStack.pop();
  if (!s) return toast('Nothing to undo');
  const o = JSON.parse(s);
  D.leagues = o.l; D.teams = o.t; D.badges = o.b;
  if (sel.league && !league(sel.league)) sel.league = null;
  if (sel.team && !team(sel.team)) sel.team = null;
  refreshLogos();
  setDirty(true);
  renderAll();
}

function setDirty(on) {
  dirty = on;
  const st = $('#status');
  st.textContent = on ? 'Unsaved changes' : 'All changes saved';
  st.className = `status${on ? ' dirty' : ''}`;
  clearTimeout(saveTimer);
  if (on && $('#autosave').checked) saveTimer = setTimeout(save, 900);
}

let lastSave = 0;
async function save() {
  clearTimeout(saveTimer);
  lastSave = Date.now();
  try {
    const r = await api('save', { game: gameId, files: { leagues: D.leagues, teams: D.teams, badges: D.badges } });
    setDirty(false);
    if (r.written.length) $('#status').textContent = `Saved ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    $('#status').textContent = 'Save failed';
    $('#status').className = 'status error';
    toast(`Save failed: ${e.message}`, true);
  }
}

// ------------------------------------------------------------ game view
function routeFor() {
  const lg = sel.league && league(sel.league);
  if (!lg) return `#/${viewId}`;
  const home = D.game.views[viewId]?.level !== 'world' && badgeOf(lg.id)?.views?.includes(viewId) ? viewId : lg.homeView ?? viewId;
  return `#/${home}/l/${encodeURIComponent(lg.id)}`;
}
function follow() {
  if ($('#follow').checked) api('focus', { hash: routeFor() }).catch(() => {});
}
function openGame() {
  window.open(`career-map.html?game=${encodeURIComponent(gameId)}&live=1${routeFor()}`, 'iwm-game', 'popup,width=1400,height=850');
}

// ------------------------------------------------------------- loading
async function loadGame(id) {
  gameId = id;
  const get = (f) => fetch(`games/${id}/${f}.json`, { cache: 'no-cache' }).then((r) => (r.ok ? r.json() : null));
  const [game, terr, lgs, tms, bdg] = await Promise.all(['game', 'territories', 'leagues', 'teams', 'badges'].map(get));
  D = { game, territories: terr ?? { territories: [] }, leagues: lgs ?? { leagues: [] }, teams: tms ?? { teams: [] }, badges: bdg ?? { badges: [] } };
  undoStack.length = 0;
  sel = { league: null, team: null };
  viewId = Object.keys(game.views).find((v) => game.views[v].level !== 'world') ?? game.rootView;
  refreshLogos();
  setDirty(false);
  $('#status').textContent = '';
  history.replaceState(null, '', `?game=${id}`);
  renderAll();
  fitMap();
}

async function boot() {
  try {
    [info, maps] = await Promise.all([api('info'), fetch('data/maps.json').then((r) => r.json()).then((m) => m.views), brand.loadBranding()]);
  } catch (e) {
    document.body.replaceChildren(h('div', { class: 'empty' }, `The editor needs its local server (tools/editor/server.py). ${e.message}`));
    return;
  }
  const gs = $('#game');
  for (const g of info.games) gs.append(h('option', { value: g }, info.titles[g] ?? g));
  const want = params.get('game');
  gs.value = info.games.includes(want) ? want : info.games.includes('nhl13') ? 'nhl13' : info.games[0];
  gs.addEventListener('change', async () => {
    if (dirty && !confirm('Discard unsaved changes?')) { gs.value = gameId; return; }
    await loadGame(gs.value);
  });
  const pref = (id) => { try { const v = localStorage.getItem(`iwm-${id}`); if (v != null) $(`#${id}`).checked = v === '1'; } catch { /* storage blocked */ } };
  for (const id of ['autosave', 'follow', 'drag-mode', 'show-all-teams']) {
    pref(id);
    $(`#${id}`).addEventListener('change', (e) => { try { localStorage.setItem(`iwm-${id}`, e.target.checked ? '1' : '0'); } catch { /* ignore */ } if (id === 'show-all-teams') drawMarkers(); if (id === 'autosave' && e.target.checked && dirty) save(); });
  }
  $('#save').addEventListener('click', save);
  $('#undo').addEventListener('click', undo);
  $('#open-game').addEventListener('click', openGame);
  $('#add-league').addEventListener('click', addLeague);
  $('#league-filter').addEventListener('input', renderList);
  $('#new-game').addEventListener('click', newGame);
  $('#export').addEventListener('click', exportRepo);
  window.addEventListener('keydown', (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === 's') { e.preventDefault(); save(); }
    else if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement?.tagName)) { e.preventDefault(); undo(); }
    else if (e.key === 'Escape' && placing) { placing = null; drawMarkers(); }
  });
  window.addEventListener('beforeunload', (e) => { if (dirty) e.preventDefault(); });
  setupMap();
  // data saved by someone else (e.g. tools/editor/fetch_logos.py): pick it up unless we have unsaved edits
  new EventSource('api/events').addEventListener('reload', async (e) => {
    if (e.data !== gameId || dirty || Date.now() - lastSave < 3000) return;
    const keep = { ...sel }, v = viewId;
    await loadGame(gameId);
    sel = { league: keep.league && league(keep.league) ? keep.league : null, team: keep.team && team(keep.team) ? keep.team : null };
    viewId = v;
    renderAll();
    fitMap();
    toast('Database changed on disk - reloaded');
  });
  await loadGame(gs.value);
  if (params.get('open') === 'game') openGame();
}

// ------------------------------------------------------------- rendering
function renderAll() {
  renderList();
  renderTabs();
  renderDetails();
  drawMarkers();
}

function renderList() {
  const q = $('#league-filter').value.trim().toLowerCase();
  const ul = $('#league-list');
  ul.replaceChildren();
  for (const lg of leagues()) {
    if (q && !`${lg.name} ${lg.shortName} ${lg.id}`.toLowerCase().includes(q)) continue;
    const n = clubsOf(lg).length;
    const unplaced = clubsOf(lg).filter((t) => !t.lonlat && !Object.keys(t.position ?? {}).length).length;
    ul.append(h('li', { class: sel.league === lg.id ? 'sel' : '', onclick: () => selectLeague(lg.id) },
      logoImg(`league:${lg.id}`, lg.shortName, 32),
      h('span', { class: 'name', title: lg.name }, lg.shortName || lg.name),
      unplaced ? h('small', { class: 'warn', title: `${unplaced} team(s) without a location` }, '⚠') : null,
      h('small', null, n ? `${n}` : '')));
  }
}

function renderTabs() {
  const nav = $('#view-tabs');
  nav.replaceChildren();
  for (const [vid, v] of Object.entries(D.game.views)) {
    if (!maps[v.map]) continue;
    const lg = sel.league && league(sel.league);
    const n = lg ? clubsOf(lg).filter((t) => teamOn(t, vid)).length : null;
    nav.append(h('button', { type: 'button', class: vid === viewId ? 'sel' : '', onclick: () => { viewId = vid; renderTabs(); fitMap(); follow(); } },
      v.title, n != null && v.level !== 'world' ? h('small', null, `${n} teams`) : null));
  }
}

const inView = (p, vid) => { const m = mapOf(vid); return p && p[0] >= 0 && p[1] >= 0 && p[0] <= m.width && p[1] <= m.height; };
/** A team is drawn on a map when its spot is on the image and its territory belongs to that map. */
function teamOn(t, vid) {
  if (t.position?.[vid]) return true;
  const tv = territories().find((x) => x.id === t.territory)?.views;
  return (!tv || tv.includes(vid)) && inView(posOf(t, vid, 'lonlat'), vid);
}

function selectLeague(id) {
  sel = { league: id, team: null };
  const lg = league(id);
  if (lg) {
    // stay on this map if the league has teams on it, else go to the league's home map
    const here = D.game.views[viewId]?.level !== 'world' && clubsOf(lg).some((t) => teamOn(t, viewId));
    if (!here && D.game.views[lg.homeView]) viewId = lg.homeView;
  }
  renderAll();
  fitMap();
  follow();
}

function selectTeam(id) {
  const t = team(id);
  if (!t) return;
  sel = { league: sel.league ?? t.league, team: id };
  renderList();
  renderTabs();
  renderDetails();
  drawMarkers();
}

// --------------------------------------------------------------- the map
function setupMap() {
  const box = $('#mapbox');
  let drag = null;
  box.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || e.target.closest('.mk')) return;
    drag = { x: e.clientX, y: e.clientY, cam: { ...cam }, moved: false };
    try { box.setPointerCapture(e.pointerId); } catch { /* synthetic event */ }
  });
  box.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 4) return;
    drag.moved = true;
    box.classList.add('panning');
    cam = { ...drag.cam, tx: drag.cam.tx + dx, ty: drag.cam.ty + dy };
    applyCam();
  });
  box.addEventListener('pointerup', (e) => {
    if (!drag) return;
    box.classList.remove('panning');
    if (!drag.moved && placing) placeAt(toImage(e));
    drag = null;
  });
  box.addEventListener('wheel', (e) => {
    e.preventDefault();
    const r = box.getBoundingClientRect();
    const mx = e.clientX - r.left, my = e.clientY - r.top;
    const k = Math.max(0.2, Math.min(12, cam.k * Math.exp(-e.deltaY * 0.0015)));
    cam = { k, tx: mx - ((mx - cam.tx) / cam.k) * k, ty: my - ((my - cam.ty) / cam.k) * k };
    applyCam();
  }, { passive: false });
  box.addEventListener('dblclick', (e) => { if (!e.target.closest('.mk')) fitMap(); });
  new ResizeObserver(() => fitMap()).observe(box);
}

function toImage(e) {
  const r = $('#mapbox').getBoundingClientRect();
  return [(e.clientX - r.left - cam.tx) / cam.k, (e.clientY - r.top - cam.ty) / cam.k];
}

/** Fit the selected league's teams, or the whole image. */
function fitMap() {
  if (!D) return;
  const m = mapOf(viewId);
  const img = $('#mapimg');
  if (img.getAttribute('src') !== m.image) { img.src = m.image; img.width = m.width; img.height = m.height; }
  const box = $('#mapbox').getBoundingClientRect();
  let rect = [0, 0, m.width, m.height];
  const lg = sel.league && league(sel.league);
  if (lg && D.game.views[viewId].level !== 'world') {
    const pts = clubsOf(lg).filter((t) => teamOn(t, viewId)).map((t) => posOf(t, viewId, 'lonlat'));
    if (pts.length > 1) {
      const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
      const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      const pad = 80;
      rect = [x0 - pad, y0 - pad, Math.max(240, x1 - x0 + pad * 2), Math.max(160, y1 - y0 + pad * 2)];
    }
  }
  const k = Math.min(box.width / rect[2], box.height / rect[3]);
  cam = { k, tx: box.width / 2 - (rect[0] + rect[2] / 2) * k, ty: box.height / 2 - (rect[1] + rect[3] / 2) * k };
  applyCam();
}

function applyCam() {
  $('#mapcam').style.transform = `translate(${cam.tx}px, ${cam.ty}px) scale(${cam.k})`;
  for (const m of $('#markers').children) {
    const [x, y] = m._pos;
    m.style.transform = `translate(${x * cam.k + cam.tx}px, ${y * cam.k + cam.ty}px)`;
  }
}

function drawMarkers() {
  const layer = $('#markers');
  layer.replaceChildren();
  const hint = $('#map-hint');
  hint.classList.toggle('on', !!placing);
  $('#mapbox').classList.toggle('placing', !!placing);
  if (placing) hint.textContent = `Click the map where ${placing.kind === 'team' ? team(placing.id)?.name : `the ${league(placing.id)?.shortName} logo`} should go · Esc cancels`;
  const lg = sel.league && league(sel.league);
  const world = D.game.views[viewId].level === 'world';

  // league logos
  for (const b of badges()) {
    if (!(b.views ?? []).includes(viewId)) continue;
    const p = posOf(b, viewId, 'anchor');
    if (!inView(p, viewId)) continue;
    const l = league(b.league);
    const mine = lg && b.league === lg.id;
    marker(layer, p, {
      cls: `badge${lg && !mine ? ' dim' : ''}${mine ? ' sel' : ''}${b.position?.[viewId] ? ' local' : ''}`,
      key: `league:${b.league}`, label: l?.shortName ?? b.league,
      onclick: () => selectLeague(b.league),
      onmove: (xy) => moveItem(b, 'anchor', xy),
    });
  }
  if (world) return;
  // teams: selected league, optionally everyone else faded
  const shown = new Set();
  if (lg) for (const t of clubsOf(lg)) shown.add(t.id);
  const all = $('#show-all-teams').checked;
  for (const t of teams()) {
    const mine = shown.has(t.id);
    if (!mine && !all) continue;
    if (!teamOn(t, viewId)) continue;
    marker(layer, posOf(t, viewId, 'lonlat'), {
      cls: `team${mine ? '' : ' other'}${sel.team === t.id ? ' sel' : ''}${t.position?.[viewId] ? ' local' : ''}`,
      key: `club:${t.id}`, label: t.city ? `${t.name} · ${t.city}` : t.name,
      onclick: () => selectTeam(t.id),
      onmove: (xy) => moveItem(t, 'lonlat', xy),
    });
  }
  applyCam();
}

function marker(layer, pos, { cls, key, label, onclick, onmove }) {
  const m = h('div', { class: `mk ${cls}`, title: label }, logoImg(key, label, 48), h('span', { class: 'lbl' }, label));
  m._pos = pos;
  let drag = null;
  m.addEventListener('pointerdown', (e) => {
    if (e.button !== 0) return;
    e.stopPropagation();
    drag = { x: e.clientX, y: e.clientY, pos: [...pos], moved: false };
    try { m.setPointerCapture(e.pointerId); } catch { /* synthetic event */ }
  });
  m.addEventListener('pointermove', (e) => {
    if (!drag) return;
    const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
    if (!drag.moved && Math.hypot(dx, dy) < 3) return;
    drag.moved = true;
    m._pos = [drag.pos[0] + dx / cam.k, drag.pos[1] + dy / cam.k];
    m.style.transform = `translate(${m._pos[0] * cam.k + cam.tx}px, ${m._pos[1] * cam.k + cam.ty}px)`;
  });
  m.addEventListener('pointerup', () => {
    if (!drag) return;
    const moved = drag.moved;
    drag = null;
    if (moved) onmove(m._pos);
    else onclick();
  });
  layer.append(m);
}

/** Dragged on the map: real location (all maps) or a nudge on this map only. */
function moveItem(item, key, [x, y]) {
  const thisMapOnly = $('#drag-mode').checked;
  change(() => {
    if (thisMapOnly) {
      item.position = { ...(item.position ?? {}), [viewId]: [Math.round(x), Math.round(y)] };
    } else {
      item[key] = toLonLat(mapOf(viewId), x, y, item[key] ?? undefined);
      if (item.position) { delete item.position[viewId]; if (!Object.keys(item.position).length) delete item.position; }
    }
  }, { redraw: false });
  renderDetails();
}

function placeAt(xy) {
  const p = placing;
  placing = null;
  const item = p.kind === 'team' ? team(p.id) : badgeOf(p.id);
  if (item) moveItem(item, p.kind === 'team' ? 'lonlat' : 'anchor', xy);
  drawMarkers();
}

// ----------------------------------------------------------- side panel
function renderDetails() {
  const box = $('#details');
  const t = sel.team && team(sel.team);
  const lg = sel.league && league(sel.league);
  box.replaceChildren(t ? teamForm(t) : lg ? leagueForm(lg) : h('div', { class: 'empty' },
    h('p', null, 'Pick a league on the left (or click its logo on the map) to edit it and its teams.'),
    h('p', null, 'Open the game view and drag it to your second screen: it reloads by itself whenever you save, and jumps to what you select here.')));
}

const row = (label, ...kids) => h('div', { class: 'row' }, h('span', null, label), ...kids);
function text(obj, key, after) {
  return h('input', { type: 'text', value: obj[key] ?? '', onchange: (e) => change(() => { obj[key] = e.target.value.trim() || null; after?.(); }) });
}
function select(options, value, onchange) {
  const s = h('select', { onchange: (e) => onchange(e.target.value) });
  for (const [v, label] of options) s.append(h('option', { value: v, selected: v === value }, label));
  return s;
}

function logoBox(kind, obj, key, label) {
  const custom = !!obj.logo;
  const img = logoImg(key, label, 96);
  const bgSel = select([['', 'Glow (auto)'], ['light', 'Light plate'], ['dark', 'Dark plate'], ['none', 'No plate'], ['custom', 'Custom colour…']],
    !obj.logoBg ? '' : ['light', 'dark', 'none'].includes(obj.logoBg) ? obj.logoBg : 'custom', (v) => {
      if (v === 'custom') return colour.click();
      change(() => { obj.logoBg = v || null; });
    });
  const colour = h('input', { type: 'color', value: /^#/.test(obj.logoBg ?? '') ? obj.logoBg : '#ffffff', style: 'width:0;height:0;opacity:0;position:absolute',
    onchange: (e) => change(() => { obj.logoBg = e.target.value; }) });
  const box = h('div', { class: 'logo-box' }, img,
    h('div', { class: 'btns' },
      h('button', { type: 'button', class: 'primary', onclick: () => pickFile((f) => uploadLogo(kind, obj, f)) }, custom ? 'Replace logo…' : 'Upload logo…'),
      custom ? h('button', { type: 'button', class: 'small', onclick: () => change(() => { obj.logo = null; }) }, 'Remove custom logo') : null,
      bgSel, colour,
      h('span', { class: 'muted' }, custom ? 'Custom logo from the database' : 'Library logo / placeholder', h('br'), 'Or drop an image file here')));
  box.addEventListener('dragover', (e) => { e.preventDefault(); box.classList.add('drop'); });
  box.addEventListener('dragleave', () => box.classList.remove('drop'));
  box.addEventListener('drop', (e) => { e.preventDefault(); box.classList.remove('drop'); const f = e.dataTransfer.files[0]; if (f) uploadLogo(kind, obj, f); });
  return box;
}

function pickFile(cb) {
  const inp = $('#file');
  inp.value = '';
  inp.onchange = () => inp.files[0] && cb(inp.files[0]);
  inp.click();
}

/**
 * Logos are stored as uploaded when SVG; other formats are converted to a
 * square transparent PNG (max 512 px). A plain white background is removed.
 */
async function normaliseImage(file) {
  if (file.type === 'image/svg+xml' || /\.svg$/i.test(file.name)) return { blob: file, ext: 'svg', note: '' };
  const bmp = await createImageBitmap(file);
  const c = h('canvas');
  c.width = bmp.width; c.height = bmp.height;
  const g = c.getContext('2d', { willReadFrequently: true });
  g.drawImage(bmp, 0, 0);
  const img = g.getImageData(0, 0, c.width, c.height);
  const px = img.data, W = c.width, H = c.height;
  const at = (x, y) => (y * W + x) * 4;
  const whiteish = (i) => px[i + 3] > 250 && px[i] > 236 && px[i + 1] > 236 && px[i + 2] > 236;
  let note = '';
  if ([at(0, 0), at(W - 1, 0), at(0, H - 1), at(W - 1, H - 1)].every(whiteish)) {
    // flood-fill the white backdrop from the edges
    const seen = new Uint8Array(W * H), stack = [];
    for (let x = 0; x < W; x++) stack.push([x, 0], [x, H - 1]);
    for (let y = 0; y < H; y++) stack.push([0, y], [W - 1, y]);
    while (stack.length) {
      const [x, y] = stack.pop();
      if (x < 0 || y < 0 || x >= W || y >= H || seen[y * W + x]) continue;
      seen[y * W + x] = 1;
      const i = at(x, y);
      if (!whiteish(i)) continue;
      px[i + 3] = 0;
      stack.push([x + 1, y], [x - 1, y], [x, y + 1], [x, y - 1]);
    }
    g.putImageData(img, 0, 0);
    note = ' (white background made transparent)';
  }
  // trim empty margins
  let x0 = W, y0 = H, x1 = -1, y1 = -1;
  for (let y = 0; y < H; y++) for (let x = 0; x < W; x++) if (px[at(x, y) + 3] > 8) { if (x < x0) x0 = x; if (x > x1) x1 = x; if (y < y0) y0 = y; if (y > y1) y1 = y; }
  if (x1 < 0) { x0 = 0; y0 = 0; x1 = W - 1; y1 = H - 1; }
  const w = x1 - x0 + 1, hh = y1 - y0 + 1;
  const S = Math.min(512, Math.max(w, hh));
  const out = h('canvas');
  out.width = out.height = S;
  const pad = S * 0.04, f = (S - pad * 2) / Math.max(w, hh);
  const o = out.getContext('2d');
  o.imageSmoothingQuality = 'high';
  o.drawImage(c, x0, y0, w, hh, (S - w * f) / 2, (S - hh * f) / 2, w * f, hh * f);
  if (Math.max(w, hh) < 128) note += ' - small image, it may look blurry';
  return { blob: await new Promise((r) => out.toBlob(r, 'image/png')), ext: 'png', note };
}

async function uploadLogo(kind, obj, file) {
  try {
    const { blob, ext, note } = await normaliseImage(file);
    const r = await api(`logo?game=${encodeURIComponent(gameId)}&kind=${kind}&id=${encodeURIComponent(obj.id)}&ext=${ext}`, blob, true);
    change(() => { obj.logo = r.path; });
    toast(`Logo saved${note}`);
  } catch (e) {
    toast(`Could not use that image: ${e.message}`, true);
  }
}

// ---------------------------------------------------------- league form
function leagueForm(lg) {
  const b = badgeOf(lg.id);
  const views = Object.entries(D.game.views).filter(([, v]) => maps[v.map]);
  const terrOpts = territories().map((t) => [t.id, `${t.name} (${t.id})`]);
  const clubs = clubsOf(lg);
  const tier = lg.tier && typeof lg.tier === 'object' ? lg.tier : (lg.tier = { value: lg.tier ?? null, status: 'game' });

  const terrChips = h('div', { class: 'chips' }, (lg.territories ?? []).map((tid) => h('span', { class: 'chip' },
    territories().find((t) => t.id === tid)?.name ?? tid,
    h('button', { type: 'button', title: 'Remove', onclick: () => change(() => { lg.territories = lg.territories.filter((x) => x !== tid); }) }, '×'))));
  const addTerr = select([['', '+ add territory…'], ...terrOpts.filter(([id]) => !(lg.territories ?? []).includes(id))], '', (v) => v && change(() => { lg.territories = [...(lg.territories ?? []), v]; }));

  const badgeBlock = b
    ? h('div', { class: 'form' },
      row('Show on', h('div', { class: 'chips' }, views.map(([vid, v]) => h('label', { class: 'check' },
        h('input', { type: 'checkbox', checked: (b.views ?? []).includes(vid), onchange: (e) => change(() => { b.views = e.target.checked ? [...new Set([...(b.views ?? []), vid])] : b.views.filter((x) => x !== vid); }) }), v.title)))),
      row('Visible from', select([['world', 'World map and closer'], ['region', 'Region maps and closer'], ['territory', 'Only when its country is selected']], b.minLevel ?? 'region', (v) => change(() => { b.minLevel = v; }))),
      row('Priority', h('input', { type: 'number', value: b.priority ?? 0, title: 'Higher wins the spot when logos would overlap', onchange: (e) => change(() => { b.priority = Number(e.target.value) || 0; }) })),
      h('div', { class: 'chips' },
        h('button', { type: 'button', class: 'small', onclick: () => { placing = { kind: 'badge', id: lg.id }; drawMarkers(); } }, 'Click map to place logo'),
        h('button', { type: 'button', class: 'small', onclick: () => centreBadge(lg) }, 'Centre on its teams'),
        b.position?.[viewId] ? h('button', { type: 'button', class: 'small', onclick: () => change(() => { delete b.position[viewId]; }) }, 'Undo nudge on this map') : null,
        h('button', { type: 'button', class: 'small danger', onclick: () => change(() => { D.badges.badges = badges().filter((x) => x !== b); }) }, 'Hide league logo from map')))
    : h('button', { type: 'button', onclick: () => change(() => { badges().push(newBadge(lg)); }) }, 'Show league logo on the map');

  return h('div', { class: 'form' },
    h('div', { class: 'title-line' }, h('h2', null, lg.name), h('span', { class: 'muted' }, lg.id)),
    logoBox('leagues', lg, `league:${lg.id}`, lg.shortName),
    row('Name', text(lg, 'name', renderList)),
    row('Short name', text(lg, 'shortName')),
    row('Kind', select(['professional', 'junior', 'college', 'semi-pro', 'international', 'other'].map((k) => [k, k]), lg.kind ?? 'professional', (v) => change(() => { lg.kind = v; }))),
    row('Level', h('div', { class: 'pair' },
      h('input', { type: 'number', min: 1, max: 9, title: '1 = top tier', value: tier.level ?? '', onchange: (e) => change(() => { tier.level = Number(e.target.value) || null; }) }),
      h('input', { type: 'text', placeholder: 'e.g. Top professional league', value: tier.value ?? '', onchange: (e) => change(() => { tier.value = e.target.value.trim() || null; }) }))),
    row('Home map', select(views.filter(([, v]) => v.level !== 'world').map(([vid, v]) => [vid, v.title]), lg.homeView, (v) => change(() => { lg.homeView = v; }))),
    row('Plays in', h('div', { class: 'form' }, terrChips, addTerr)),
    h('h3', null, 'League logo on the map'),
    badgeBlock,
    h('h3', null, `Teams (${clubs.length})`),
    h('div', { class: 'chips' },
      h('button', { type: 'button', class: 'primary small', onclick: () => addTeam(lg) }, '+ New team'),
      addExistingPicker(lg)),
    h('ul', { class: 'list' }, clubs.map((t) => h('li', { onclick: () => selectTeam(t.id), class: sel.team === t.id ? 'sel' : '' },
      logoImg(`club:${t.id}`, t.name, 32),
      h('span', { class: 'name' }, t.name, h('br'), h('small', null, t.city ?? 'city not set')),
      !t.lonlat && !t.position ? h('small', { class: 'warn', title: 'No location - it will not appear on the map' }, '⚠ no location') : null,
      h('button', { type: 'button', class: 'small', title: 'Remove from this league', onclick: (e) => { e.stopPropagation(); removeFromLeague(lg, t); } }, '×')))),
    h('div', { class: 'danger-zone' },
      h('button', { type: 'button', class: 'danger', onclick: () => deleteLeague(lg) }, 'Delete league')));
}

function addExistingPicker(lg) {
  const listId = `teams-dl-${lg.id}`;
  const dl = h('datalist', { id: listId }, teams().filter((t) => !(lg.clubs ?? []).includes(t.id)).map((t) => h('option', { value: `${t.name} — ${t.id}` })));
  const inp = h('input', { type: 'search', list: listId, placeholder: '+ add an existing team…', onchange: (e) => {
    const id = e.target.value.split(' — ').pop();
    if (!team(id)) return;
    change(() => { lg.clubs = [...new Set([...(lg.clubs ?? clubsOf(lg).map((t) => t.id)), id])]; });
  } });
  return h('span', null, inp, dl);
}

function newBadge(lg) {
  const vid = lg.homeView ?? viewId;
  const pts = clubsOf(lg).filter((t) => t.lonlat).map((t) => t.lonlat);
  const m = mapOf(vid);
  const anchor = pts.length ? [pts.reduce((s, p) => s + p[0], 0) / pts.length, pts.reduce((s, p) => s + p[1], 0) / pts.length]
    : toLonLat(m, m.width / 2, m.height / 2);
  return { id: `badge-${lg.id}`, league: lg.id, image: null, views: [vid], minLevel: 'region', anchor: anchor.map((v) => Math.round(v * 100) / 100), priority: 50, action: { type: 'league', id: lg.id } };
}

function centreBadge(lg) {
  const b = badgeOf(lg.id);
  const pts = clubsOf(lg).filter((t) => t.lonlat).map((t) => t.lonlat);
  if (!b || !pts.length) return toast('No team locations to centre on');
  change(() => { b.anchor = [0, 1].map((i) => Math.round((pts.reduce((s, p) => s + p[i], 0) / pts.length) * 100) / 100); delete b.position; });
}

function addLeague() {
  const name = prompt('Name of the new league (e.g. "Finnish Mestis")');
  if (!name) return;
  const id = uniqueId(name, (x) => !!league(x));
  const short = prompt('Short name shown on the map (e.g. "Mestis")', name.split(/\s+/).map((w) => w[0]).join('').toUpperCase().slice(0, 6)) || name;
  const home = D.game.views[viewId].level === 'world' ? Object.keys(D.game.views).find((v) => D.game.views[v].level !== 'world') : viewId;
  const season = leagues()[0]?.season ?? { value: D.game.season ?? null, status: 'game' };
  const unknown = () => ({ value: null, status: 'unknown' });
  change(() => {
    const lg = { id, name, shortName: short, logo: null, kind: 'professional', multinational: false, territories: [], homeView: home,
      tier: { value: null, status: 'game', level: 3 }, teamCount: { value: 0, status: 'game' }, season: { ...season },
      salary: unknown(), career: unknown(), eligibility: unknown(), clubs: [] };
    leagues().push(lg);
    badges().push(newBadge(lg));
    sel = { league: id, team: null };
  });
  toast('League added - set where it plays, upload a logo, then add teams');
  follow();
}

function deleteLeague(lg) {
  const only = teams().filter((t) => t.league === lg.id);
  if (!confirm(`Delete ${lg.name}?`)) return;
  const dropTeams = only.length && confirm(`Also delete its ${only.length} team(s)? (OK = delete them, Cancel = keep them without a league)`);
  change(() => {
    D.leagues.leagues = leagues().filter((l) => l !== lg);
    D.badges.badges = badges().filter((b) => b.league !== lg.id);
    if (dropTeams) {
      const gone = new Set(only.map((t) => t.id));
      D.teams.teams = teams().filter((t) => !gone.has(t.id));
      for (const l of leagues()) if (l.clubs) l.clubs = l.clubs.filter((c) => !gone.has(c));
    } else for (const t of only) t.league = null;
    sel = { league: null, team: null };
  });
}

function removeFromLeague(lg, t) {
  const home = t.league === lg.id;
  const elsewhere = leagues().some((l) => l !== lg && (l.clubs ?? []).includes(t.id));
  if (home && !elsewhere) {
    if (!confirm(`${t.name} only plays in ${lg.shortName}. Delete the team?`)) return;
    return deleteTeam(t, true);
  }
  change(() => {
    lg.clubs = (lg.clubs ?? []).filter((c) => c !== t.id);
    if (home) t.league = leagues().find((l) => (l.clubs ?? []).includes(t.id))?.id ?? null;
  });
}

// ------------------------------------------------------------ team form
function teamForm(t) {
  const lg = sel.league && league(sel.league);
  const views = Object.entries(D.game.views).filter(([, v]) => maps[v.map] && v.level !== 'world');
  const results = h('div', { class: 'results' });
  const cityInput = h('input', { type: 'text', value: t.city ?? '', placeholder: 'e.g. Tampere', onkeydown: (e) => { if (e.key === 'Enter') { e.preventDefault(); find(); } } });
  async function find() {
    const q = cityInput.value.trim();
    if (!q) return;
    results.replaceChildren(h('span', { class: 'muted' }, 'Searching…'));
    try {
      const r = await fetch(`https://geocoding-api.open-meteo.com/v1/search?count=6&language=en&name=${encodeURIComponent(q)}`).then((x) => x.json());
      const list = r.results ?? [];
      results.replaceChildren(...(list.length ? list.map((c) => h('button', { type: 'button', class: 'small', onclick: () => {
        change(() => { t.city = c.name; t.lonlat = [Math.round(c.longitude * 10000) / 10000, Math.round(c.latitude * 10000) / 10000]; delete t.position; });
        follow();
      } }, `${c.name}, ${[c.admin1, c.country].filter(Boolean).join(', ')}${c.population ? ` · ${Math.round(c.population / 1000)}k` : ''}`))
        : [h('span', { class: 'muted' }, 'No match - type the city differently, or place it by clicking the map.')]));
    } catch {
      results.replaceChildren(h('span', { class: 'muted' }, 'City search needs internet. You can still place the team by clicking the map.'));
    }
  }
  const nudged = Object.keys(t.position ?? {});
  const memberOf = leagues().filter((l) => (l.clubs ?? []).includes(t.id) || l.id === t.league);
  return h('div', { class: 'form' },
    lg ? h('button', { type: 'button', class: 'back', onclick: () => { sel.team = null; renderDetails(); drawMarkers(); } }, `‹ ${lg.name}`) : null,
    h('div', { class: 'title-line' }, h('h2', null, t.name), h('span', { class: 'muted' }, t.id)),
    logoBox('teams', t, `club:${t.id}`, t.name),
    row('Name', text(t, 'name')),
    row('City', h('div', { class: 'pair' }, cityInput, h('button', { type: 'button', onclick: find, style: 'flex:none' }, 'Find'))),
    results,
    row('Location', h('div', { class: 'pair' },
      h('input', { type: 'number', step: 'any', placeholder: 'longitude', title: 'Longitude', value: t.lonlat?.[0] ?? '', onchange: (e) => change(() => { t.lonlat = [Number(e.target.value), t.lonlat?.[1] ?? 0]; }) }),
      h('input', { type: 'number', step: 'any', placeholder: 'latitude', title: 'Latitude', value: t.lonlat?.[1] ?? '', onchange: (e) => change(() => { t.lonlat = [t.lonlat?.[0] ?? 0, Number(e.target.value)]; }) }))),
    h('div', { class: 'chips' },
      h('button', { type: 'button', class: 'small', onclick: () => { placing = { kind: 'team', id: t.id }; drawMarkers(); } }, 'Click map to place'),
      ...nudged.map((vid) => h('button', { type: 'button', class: 'small', title: 'This map uses a hand-placed spot instead of the city coordinates', onclick: () => change(() => { delete t.position[vid]; if (!Object.keys(t.position).length) delete t.position; }) }, `Reset nudge on ${D.game.views[vid]?.title ?? vid}`))),
    !t.lonlat && !nudged.length ? h('p', { class: 'warn' }, 'No location yet - find the city or click the map to place it.') : null,
    row('Main league', select([['', '(none)'], ...leagues().map((l) => [l.id, l.name])], t.league ?? '', (v) => change(() => {
      const old = league(t.league);
      if (old?.clubs) old.clubs = old.clubs.filter((c) => c !== t.id);
      t.league = v || null;
      const nl = league(v);
      if (nl) nl.clubs = [...new Set([...(nl.clubs ?? []), t.id])];
    }))),
    row('Territory', select([['', '(none)'], ...territories().map((x) => [x.id, x.name])], t.territory ?? '', (v) => change(() => {
      t.territory = v || null;
      t.geo = territories().find((x) => x.id === v)?.geo?.[0] ?? t.geo ?? null;
    }))),
    memberOf.length > 1 ? row('Also plays in', h('span', null, memberOf.filter((l) => l.id !== t.league).map((l) => l.shortName).join(', '))) : null,
    h('div', { class: 'danger-zone' }, h('button', { type: 'button', class: 'danger', onclick: () => deleteTeam(t) }, 'Delete team')));
}

function addTeam(lg) {
  const name = prompt(`Name of the new ${lg.shortName} team`);
  if (!name) return;
  const id = uniqueId(name, (x) => !!team(x));
  const terr = territories().find((x) => x.id === lg.territories?.[0]);
  change(() => {
    teams().push({ id, name, city: null, league: lg.id, territory: terr?.id ?? null, geo: terr?.geo?.[0] ?? null, logo: null, lonlat: null, status: 'game' });
    lg.clubs = [...new Set([...(lg.clubs ?? clubsOf(lg).map((t) => t.id)), id])];
    sel = { league: lg.id, team: id };
  });
  toast('Team added - type its city and press Find, or click the map');
}

function deleteTeam(t, confirmed = false) {
  if (!confirmed && !confirm(`Delete ${t.name}?`)) return;
  change(() => {
    D.teams.teams = teams().filter((x) => x !== t);
    for (const l of leagues()) if (l.clubs) l.clubs = l.clubs.filter((c) => c !== t.id);
    sel.team = null;
  });
}

// ---------------------------------------------------------- game files
async function newGame() {
  const title = prompt('Title of the new game database (it starts as a copy of the current one)');
  if (!title) return;
  const id = uniqueId(title, (x) => info.games.includes(x));
  try {
    if (dirty) await save();
    await api('new-game', { id, from: gameId, title });
    location.href = `editor.html?game=${id}`;
  } catch (e) { toast(e.message, true); }
}

async function exportRepo() {
  if (!confirm(`Copy "${gameId}" from the league database into the git repository (${info.repo})? Files there are overwritten; commit and push to publish.`)) return;
  try {
    if (dirty) await save();
    const r = await api('export', { game: gameId });
    toast(`Copied to ${r.to}`);
  } catch (e) { toast(e.message, true); }
}

window.addEventListener('error', (e) => toast(`Editor error: ${e.message}`, true));
boot();
