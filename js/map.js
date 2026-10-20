// The map stage: background image, interactive territory layer, league badge
// layer and a camera that zooms between them. Geometry lives in image pixel
// space; the camera maps it to the screen.

import { toPixel } from './projection.js';
import * as brand from './branding.js';
import { territoryPath, loadViewGeo, geoUnits, children, coverage, leaguesIn } from './data.js';

const SVGNS = 'http://www.w3.org/2000/svg';
const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)');
const LEVELS = { world: 0, region: 1, territory: 2 };

const el = (tag, attrs = {}, ns = SVGNS) => {
  const e = ns ? document.createElementNS(ns, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) if (v != null) e.setAttribute(k, v);
  return e;
};
const html = (tag, cls, text) => {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
};
const ease = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);

export class MapStage {
  constructor(root, db, handlers) {
    this.root = root;
    this.db = db;
    this.h = handlers;
    this.layer = null;
    this.insets = { right: 0, bottom: 0, top: 0, left: 0 };
    this.tooltip = html('div', 'map-tooltip');
    this.tooltip.setAttribute('role', 'status');
    root.append(this.tooltip);
    this.seq = 0;
    new ResizeObserver(() => this.relayout()).observe(root);
    this.enablePan();
  }

  /** Drag the map to look around; a drag never counts as a click. */
  enablePan() {
    let drag = null;
    this.root.addEventListener('pointerdown', (e) => {
      if (e.button !== 0 || !this.layer || e.target.closest('.badge, .territory-pin, .team-pin')) return;
      drag = { x: e.clientX, y: e.clientY, cam: { ...this.layer.cam }, moved: false, id: e.pointerId };
    });
    this.root.addEventListener('pointermove', (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (!drag.moved && Math.hypot(dx, dy) < 6) return;
      if (!drag.moved) { drag.moved = true; this.root.setPointerCapture(e.pointerId); this.root.classList.add('panning'); this.hideTip(); }
      const L = this.layer;
      cancelAnimationFrame(L.raf);
      L.cam = this.clampCamera(L, { k: drag.cam.k, tx: drag.cam.tx + dx, ty: drag.cam.ty + dy });
      this.applyCamera(L);
    });
    const end = (e) => {
      if (!drag || e.pointerId !== drag.id) return;
      if (drag.moved) {
        this.suppressClick = true;
        setTimeout(() => { this.suppressClick = false; }, 0);
        this.root.classList.remove('panning');
        this.placeBadges(this.layer);
      }
      drag = null;
    };
    this.root.addEventListener('pointerup', end);
    this.root.addEventListener('pointercancel', end);
    this.root.addEventListener('click', (e) => { if (this.suppressClick) { e.stopPropagation(); e.preventDefault(); } }, true);
  }

  setInsets(insets) {
    this.insets = { ...this.insets, ...insets };
  }

  // ------------------------------------------------------------ view switch
  async show(viewId, state, direction = 'none') {
    const seq = ++this.seq;
    if (this.layer?.viewId === viewId) return this.update(state);

    const old = this.layer;
    const layer = await this.buildLayer(viewId);
    if (seq !== this.seq) { layer.el.remove(); return; }
    this.layer = layer;
    this.state = {};
    const dur = REDUCED.matches || !old ? 0 : 650;

    if (old) {
      old.el.classList.add('leaving');
      old.el.style.pointerEvents = 'none';
      if (direction === 'in') {
        // zoom the old map into the region we are entering
        const rect = this.regionRectOn(old, viewId);
        if (rect) this.animate(old, this.cameraFor(old, rect, { pad: 0.02, maxZoom: 6, cover: true }), dur);
        layer.cam = this.scaleCamera(this.baseCamera(layer), 0.8);
      } else if (direction === 'out') {
        this.animate(old, this.scaleCamera(old.cam, 0.8), dur);
        const rect = this.regionRectOn(layer, old.viewId);
        layer.cam = rect ? this.cameraFor(layer, rect, { pad: 0.02, maxZoom: 6, cover: true }) : this.baseCamera(layer);
      } else {
        layer.cam = this.baseCamera(layer);
      }
      setTimeout(() => old.el.remove(), dur + 80);
    } else {
      layer.cam = this.baseCamera(layer);
    }
    this.applyCamera(layer);
    requestAnimationFrame(() => layer.el.classList.add('shown'));
    await this.update(state, dur ? dur : 0);
  }

  // ------------------------------------------------------ state in a view
  async update(state, duration = 550) {
    const L = this.layer;
    if (!L) return;
    const prev = this.state || {};
    this.state = state;

    for (const [id, p] of L.paths) {
      p.classList.toggle('selected', id === state.territory);
    }
    await this.showSubdivisions(L, state.territory);
    await this.showCoverage(L, state.league);
    this.showTeams(L, state.league);
    this.placeBadges(L);
    this.pinLabel(L);

    const changed = prev.territory !== state.territory || prev.info !== state.info || prev.league !== state.league;
    if (changed || duration === 0 || !L.cam) {
      const target = this.targetCamera(L, state);
      this.animate(L, target, REDUCED.matches ? 0 : duration);
    }
  }

  targetCamera(L, state) {
    const focusId = state.territory || null;
    if (focusId) {
      const r = this.bboxOf(L, focusId);
      if (r) return this.cameraFor(L, r, { pad: 0.18, maxZoom: 2.4, avail: true });
    }
    if (state.league && L.coverRect) return this.cameraFor(L, L.coverRect, { pad: 0.12, maxZoom: 1.8, avail: true });
    return this.baseCamera(L);
  }

  relayout() {
    if (!this.layer) return;
    this.layer.cam = this.targetCamera(this.layer, this.state || {});
    this.applyCamera(this.layer);
  }

  // ------------------------------------------------------------ building
  async buildLayer(viewId) {
    const db = this.db;
    const view = db.game.views[viewId];
    const map = db.maps[view.map];
    const L = {
      viewId, view, map, mapId: view.map, level: view.level,
      paths: new Map(), badges: [], sub: null, cover: null, cam: null,
    };
    L.el = html('div', `map-layer level-${view.level}`);
    L.el.dataset.view = viewId;
    L.svg = el('svg', { class: 'map-svg', role: 'img', 'aria-label': `${view.title} map` });
    L.g = el('g', { class: 'camera' });
    L.svg.append(L.g);
    L.overlay = html('div', 'map-overlay');
    L.el.append(L.svg, L.overlay);

    // background image, never stretched: drawn at its own pixel size
    const img = el('image', { width: map.width, height: map.height, preserveAspectRatio: 'none', class: 'map-image' });
    img.setAttribute('href', map.image);
    const imgLoaded = new Promise((resolve) => {
      img.addEventListener('load', () => resolve(true), { once: true });
      img.addEventListener('error', () => resolve(false), { once: true });
      setTimeout(() => resolve(null), 4000);
    });
    const backdrop = el('rect', { width: map.width, height: map.height, class: 'map-backdrop' });
    L.g.append(backdrop, img);
    backdrop.addEventListener('click', () => this.h.onBackground());
    img.addEventListener('click', () => this.h.onBackground());

    L.gOff = el('g', { class: 'units-off' });
    L.gTerr = el('g', { class: 'territories' });
    L.gSub = el('g', { class: 'subdivisions' });
    L.gCover = el('g', { class: 'coverage' });
    L.g.append(L.gOff, L.gTerr, L.gSub, L.gCover);
    this.root.append(L.el);

    const geo = await loadViewGeo(db, L.mapId);
    L.geo = geo;
    if (view.level === 'world') this.buildRegions(L, geo);
    else await this.buildTerritories(L, geo);
    this.buildBadges(L);

    const ok = await imgLoaded;
    if (ok === false) {
      const warn = html('div', 'map-missing', `Map image failed to load: ${map.image}`);
      L.el.append(warn);
      db.warnings.push(`Map image failed to load: ${map.image}`);
    }
    L.imageStatus = ok === false ? 'error' : ok ? 'loaded' : 'timeout';
    return L;
  }

  buildRegions(L, geo) {
    const db = this.db;
    for (const rid of L.view.regions ?? []) {
      const rv = db.game.views[rid];
      if (!rv) continue;
      let d = '';
      const units = (rv.worldUnits ?? []).filter((u) => geo[u]);
      for (const u of units) d += geo[u].d;
      if (!d) continue;
      const p = el('path', { d, class: 'region', 'data-id': rid, tabindex: 0, role: 'button', 'aria-label': rv.title });
      this.bindHover(p, () => ({ title: rv.title, sub: 'Open region map' }));
      p.addEventListener('click', (e) => { e.stopPropagation(); this.h.onRegion(rid); });
      p.addEventListener('keydown', (e) => { if (e.key === 'Enter') this.h.onRegion(rid); });
      L.gTerr.append(p);
      L.paths.set(rid, p);
      const label = html('div', 'region-label', rv.title);
      L.overlay.append(label);
      L.labels = L.labels || [];
      L.labels.push({ el: label, rect: this.unionRect(units.map((u) => geo[u].bbox)), id: rid });
    }
  }

  async buildTerritories(L, geo) {
    const db = this.db;
    const used = new Set();
    for (const tid of L.view.territories ?? []) {
      const t = db.territories.get(tid);
      if (!t) continue;
      const { d, quality, units } = await territoryPath(db, L.mapId, tid);
      units.forEach((u) => used.add(u));
      // subdivided countries: their subdivision units belong to them too
      for (const [uid, f] of Object.entries(geo)) if (f.kind === 'subdivision' && (t.geo ?? []).includes(f.country)) used.add(uid);
      if (!d) { L.missing = [...(L.missing ?? []), tid]; continue; }
      const p = el('path', { d, class: `territory q-${quality}`, 'data-id': tid, tabindex: 0, role: 'button', 'aria-label': t.name });
      this.bindHover(p, () => this.territoryTip(tid));
      p.addEventListener('click', (e) => { e.stopPropagation(); this.h.onTerritory(tid); });
      p.addEventListener('keydown', (e) => { if (e.key === 'Enter') this.h.onTerritory(tid); });
      L.gTerr.append(p);
      L.paths.set(tid, p);
    }
    // everything else on this map: visible on hover as "not available"
    for (const [uid, f] of Object.entries(geo)) {
      if (used.has(uid)) continue;
      const p = el('path', { d: f.d, class: 'unit-off', 'data-unit': uid });
      this.bindHover(p, () => ({ title: f.name, sub: 'Not available in career mode', off: true }));
      p.addEventListener('click', (e) => { e.stopPropagation(); this.h.onBackground(); });
      L.gOff.append(p);
    }
  }

  territoryTip(tid) {
    const t = this.db.territories.get(tid);
    const n = leaguesIn(this.db, tid).length;
    return { title: t?.name ?? tid, sub: n ? `${n} league${n === 1 ? '' : 's'}` : 'No supported leagues yet' };
  }

  // -------------------------------------------------- subdivisions layer
  async showSubdivisions(L, tid) {
    if (L.subFor === tid) return;
    L.subFor = tid;
    L.gSub.replaceChildren();
    L.el.classList.remove('has-sub');
    if (!tid || L.level === 'world') return;
    const t = this.db.territories.get(tid);
    const kids = children(this.db, tid);
    const codes = t?.geo ?? [];
    const subUnits = Object.entries(L.geo).filter(([, f]) => f.kind === 'subdivision' && codes.includes(f.country));
    if (!kids.length && !subUnits.length) return;
    L.el.classList.add('has-sub');
    const covered = new Set();
    for (const k of kids) {
      const { d, units } = await territoryPath(this.db, L.mapId, k.id);
      if (L.subFor !== tid) return;
      units.forEach((u) => covered.add(u));
      if (!d) continue;
      const p = el('path', { d, class: 'subdivision', 'data-id': k.id, tabindex: 0, role: 'button', 'aria-label': k.name });
      this.bindHover(p, () => this.territoryTip(k.id));
      p.addEventListener('click', (e) => { e.stopPropagation(); this.h.onTerritory(k.id); });
      L.gSub.append(p);
    }
    for (const [uid, f] of subUnits) {
      if (covered.has(uid)) continue;
      const p = el('path', { d: f.d, class: 'subdivision sub-off', 'data-unit': uid });
      this.bindHover(p, () => ({ title: f.name, sub: `Part of ${t.name} · no separate leagues`, off: true }));
      p.addEventListener('click', (e) => { e.stopPropagation(); this.h.onTerritory(tid); });
      L.gSub.prepend(p);
    }
  }

  // ------------------------------------------------------ league coverage
  async showCoverage(L, leagueId, preview = false) {
    const key = `${leagueId}|${preview}`;
    if (L.coverKey === key) return;
    L.coverKey = key;
    L.gCover.replaceChildren();
    L.coverRect = null;
    if (!leagueId || L.level === 'world') return;
    const lg = this.db.leagues.get(leagueId);
    if (!lg) return;
    const ids = coverage(this.db, lg);
    const boxes = [];
    for (const id of ids) {
      const { d } = await territoryPath(this.db, L.mapId, id);
      if (L.coverKey !== key) return;
      if (!d) continue;
      const p = el('path', { d, class: `cover${preview ? ' preview' : ''}` });
      L.gCover.append(p);
      try { const b = p.getBBox(); if (b.width) boxes.push([b.x, b.y, b.width, b.height]); } catch { /* not rendered */ }
    }
    if (boxes.length) L.coverRect = this.clampRect(L, this.unionRect(boxes));
  }

  // ---------------------------------------------------------------- badges
  buildBadges(L) {
    const db = this.db;
    for (const b of db.badges) {
      if (!(b.views ?? []).includes(L.viewId)) continue;
      const lg = db.leagues.get(b.league);
      const pos = b.position?.[L.viewId] ?? (b.anchor ? toPixel(L.map, b.anchor[0], b.anchor[1]) : null);
      if (!pos || pos[0] < 0 || pos[1] < 0 || pos[0] > L.map.width || pos[1] > L.map.height) continue;
      const node = html('button', 'badge');
      node.type = 'button';
      node.dataset.badge = b.id;
      node.setAttribute('aria-label', lg ? `${lg.name}` : b.id);
      const imgEl = b.image ? Object.assign(html('img'), { src: b.image, alt: '' }) : brand.img(`league:${b.league}`, 58, lg?.shortName ?? b.league, 'badge-img');
      imgEl.draggable = false;
      imgEl.addEventListener('error', () => node.classList.add('no-image'));
      const fallback = html('span', 'badge-fallback', lg?.shortName ?? '?');
      const cap = html('span', 'badge-caption', lg?.shortName ?? b.league);
      node.append(imgEl, fallback, cap);
      const stem = html('div', 'badge-stem');
      const dot = html('div', 'badge-dot');
      L.overlay.append(stem, dot, node);
      node.addEventListener('click', (e) => { e.stopPropagation(); this.h.onBadge(b); });
      node.addEventListener('pointerenter', () => { this.showCoverage(L, b.league, true); this.showTip(node, { title: lg?.name ?? b.league, sub: lg?.tier?.value ?? '' }); });
      node.addEventListener('pointerleave', () => { this.hideTip(); this.showCoverage(L, this.state?.league ?? null); });
      L.badges.push({ badge: b, league: lg, pos, node, stem, dot, offset: [0, -34] });
    }
  }

  badgeVisible(L, item) {
    const s = this.state || {};
    const b = item.badge;
    // a league's own clubs are on the map: other leagues step aside
    if (s.league && L.teams?.length) return b.league === s.league;
    const need = LEVELS[b.minLevel] ?? 0;
    if (L.level === 'world') return need === LEVELS.world;
    if (s.territory) {
      // territory focus: only leagues playing in that territory (or its parts)
      return leaguesIn(this.db, s.territory).some((x) => x.league.id === b.league) || b.league === s.league;
    }
    return need <= LEVELS.region || b.league === s.league;
  }

  placeBadges(L) {
    const placed = [];
    const items = [...L.badges].sort((a, b) => (b.badge.priority ?? 0) - (a.badge.priority ?? 0));
    const cands = [[0, -42], [46, -26], [-46, -26], [52, 16], [-52, 16], [0, 48], [82, -42], [-82, -42], [0, -94]];
    for (const it of items) {
      const vis = this.badgeVisible(L, it);
      it.visible = vis;
      for (const n of [it.node, it.stem, it.dot]) n.classList.toggle('hidden', !vis);
      it.node.classList.toggle('active', it.badge.league === this.state?.league);
      if (!vis) continue;
      const [sx, sy] = this.toScreen(L, it.pos);
      let best = cands[0];
      for (const c of cands) {
        const r = [sx + c[0] - 32, sy + c[1] - 32, 64, 72];
        if (!placed.some((q) => r[0] < q[0] + q[2] && q[0] < r[0] + r[2] && r[1] < q[1] + q[3] && q[1] < r[1] + r[3])) { best = c; break; }
      }
      it.offset = best;
      placed.push([sx + best[0] - 32, sy + best[1] - 32, 64, 72]);
    }
    this.placeTeams(L, placed);
    this.positionOverlay(L);
  }

  // ------------------------------------------------------ team thumbnails
  /** With a league open, each of its clubs gets its logo on its home city. */
  showTeams(L, leagueId) {
    if (L.teamsFor === leagueId) return;
    L.teamsFor = leagueId;
    for (const it of L.teams ?? []) it.node.remove(), it.stem.remove(), it.dot.remove();
    L.teams = [];
    const lg = leagueId ? this.db.leagues.get(leagueId) : null;
    if (!lg || L.level === 'world') return;
    const ids = lg.clubs?.length ? lg.clubs : [...this.db.teams.values()].filter((t) => t.league === leagueId).map((t) => t.id);
    for (const id of ids) {
      const t = this.db.teams.get(id);
      // the projection runs past the artwork's edges: only teams whose territory is on this map
      const tv = t && this.db.territories.get(t.territory)?.views;
      if (tv && !tv.includes(L.viewId) && !t.position?.[L.viewId]) continue;
      const pos = t && (t.position?.[L.viewId] ?? (t.lonlat ? toPixel(L.map, t.lonlat[0], t.lonlat[1]) : null));
      if (!pos || pos[0] < 0 || pos[1] < 0 || pos[0] > L.map.width || pos[1] > L.map.height) continue;
      const node = html('button', 'team-pin');
      node.type = 'button';
      node.dataset.team = id;
      node.setAttribute('aria-label', t.city ? `${t.name}, ${t.city}` : t.name);
      const imgEl = brand.img(`club:${id}`, 40, t.name, 'team-img');
      imgEl.draggable = false;
      node.append(imgEl);
      const stem = html('div', 'team-stem');
      const dot = html('div', 'team-dot');
      L.overlay.append(stem, dot, node);
      node.addEventListener('click', (e) => e.stopPropagation());
      node.addEventListener('pointerenter', () => this.showTip(node, { title: t.name, sub: t.city ?? '' }));
      node.addEventListener('pointerleave', () => this.hideTip());
      L.teams.push({ team: t, pos, node, stem, dot, offset: [0, 0], visible: true });
    }
    // west to east, so neighbours spread out the same way every time
    L.teams.sort((a, b) => a.pos[0] - b.pos[0] || a.pos[1] - b.pos[1]);
  }

  /** Thumbnails sit on their city; when cities crowd, later ones move to the nearest free spot. */
  placeTeams(L, placed) {
    const S = 44;
    const rings = [[0, 0]];
    for (let r = 1; r <= 6; r++) {
      const n = 6 * r;
      for (let i = 0; i < n; i++) rings.push([Math.cos((i / n) * 2 * Math.PI - Math.PI / 2) * r * S, Math.sin((i / n) * 2 * Math.PI - Math.PI / 2) * r * S]);
    }
    for (const it of L.teams ?? []) {
      const [sx, sy] = this.toScreen(L, it.pos);
      let best = rings[0];
      for (const c of rings) {
        const r = [sx + c[0] - S / 2, sy + c[1] - S / 2, S, S];
        if (!placed.some((q) => r[0] < q[0] + q[2] && q[0] < r[0] + r[2] && r[1] < q[1] + q[3] && q[1] < r[1] + r[3])) { best = c; break; }
      }
      it.offset = best;
      placed.push([sx + best[0] - S / 2, sy + best[1] - S / 2, S, S]);
      it.stem.classList.toggle('hidden', !best[0] && !best[1]);
    }
  }

  // ------------------------------------------------------------- tooltips
  bindHover(node, info) {
    node.addEventListener('pointerenter', () => { node.classList.add('hover'); this.showTip(null, info()); });
    node.addEventListener('pointermove', (e) => this.moveTip(e));
    node.addEventListener('pointerleave', () => { node.classList.remove('hover'); this.hideTip(); });
    node.addEventListener('focus', () => { const r = node.getBoundingClientRect(); this.showTip(null, info()); this.moveTip({ clientX: r.x + r.width / 2, clientY: r.y + r.height / 2 }); });
    node.addEventListener('blur', () => this.hideTip());
  }

  showTip(anchorEl, { title, sub, off }) {
    const t = this.tooltip;
    t.replaceChildren(html('strong', null, title), ...(sub ? [html('span', null, sub)] : []));
    t.classList.toggle('off', !!off);
    t.classList.add('visible');
    if (anchorEl) {
      const r = anchorEl.getBoundingClientRect();
      this.moveTip({ clientX: r.x + r.width / 2, clientY: r.y - 6 });
    }
  }

  moveTip(e) {
    const box = this.root.getBoundingClientRect();
    const x = Math.min(box.width - 180, Math.max(8, e.clientX - box.x + 14));
    const y = Math.max(8, e.clientY - box.y - 42);
    this.tooltip.style.transform = `translate(${x}px, ${y}px)`;
  }

  hideTip() { this.tooltip.classList.remove('visible'); }

  pinLabel(L) {
    L.pin?.remove();
    L.pin = null;
    const s = this.state || {};
    if (!s.territory || s.info || s.league || L.level === 'world') return;
    const t = this.db.territories.get(s.territory);
    if (!t) return;
    const n = leaguesIn(this.db, s.territory).length;
    const pin = html('div', 'territory-pin');
    pin.append(html('strong', null, t.name), html('span', null, n ? `${n} league${n === 1 ? '' : 's'}` : 'No supported leagues yet'));
    const btn = html('button', 'pin-open', 'View details');
    btn.type = 'button';
    btn.addEventListener('click', (e) => { e.stopPropagation(); this.h.onTerritory(s.territory); });
    pin.append(btn);
    L.overlay.append(pin);
    L.pin = pin;
    this.positionOverlay(L);
  }

  // --------------------------------------------------------------- camera
  stageSize() {
    const r = this.root.getBoundingClientRect();
    return { w: r.width || window.innerWidth, h: r.height || window.innerHeight };
  }

  /** Whole image: cover when cropping is small; otherwise part-way, and the user can pan. */
  baseCamera(L) {
    const { w, h } = this.stageSize();
    const W = L.map.width, H = L.map.height;
    const cover = Math.max(w / W, h / H), contain = Math.min(w / W, h / H);
    const k = cover / contain <= 1.18 ? cover : Math.min(cover, contain * 1.9);
    const [fx, fy] = L.view.focus ?? [W / 2, H / 2];
    return this.clampCamera(L, { k, tx: w / 2 - fx * k, ty: h / 2 - fy * k });
  }

  /** Keep the image covering the stage (or the free area beside the panel) where it can. */
  clampCamera(L, cam, ins = { left: 0, right: 0, top: 0, bottom: 0 }) {
    const { w, h } = this.stageSize();
    const W = L.map.width * cam.k, H = L.map.height * cam.k;
    const fit = (t, size, a0, a1) => {
      if (size >= a1 - a0) return Math.min(a0, Math.max(a1 - size, t));
      return a0 + (a1 - a0 - size) / 2;
    };
    // the image must cover the visible area: the stage minus the panel / bottom sheet
    const x1 = w - (ins.right || 0), y1 = h - (ins.bottom || 0);
    const y0 = H >= y1 ? 0 : ins.top || 0;
    return { k: cam.k, tx: fit(cam.tx, W, 0, x1), ty: fit(cam.ty, H, y0, y1) };
  }

  scaleCamera(cam, f) {
    const { w, h } = this.stageSize();
    const cx = (w / 2 - cam.tx) / cam.k, cy = (h / 2 - cam.ty) / cam.k;
    const k = cam.k * f;
    return { k, tx: w / 2 - cx * k, ty: h / 2 - cy * k };
  }

  cameraFor(L, [x, y, rw, rh], { pad = 0.15, maxZoom = 2.4, avail = false, cover = false } = {}) {
    const { w, h } = this.stageSize();
    const base = this.baseCamera(L);
    const ins = avail ? this.insets : { left: 0, right: 0, top: 0, bottom: 0 };
    const aw = Math.max(80, w - ins.left - ins.right), ah = Math.max(80, h - ins.top - ins.bottom);
    const pw = rw * (1 + pad * 2), ph = rh * (1 + pad * 2);
    let k = cover ? Math.max(aw / pw, ah / ph) : Math.min(aw / pw, ah / ph);
    k = Math.max(base.k, Math.min(base.k * maxZoom, k));
    const cx = x + rw / 2, cy = y + rh / 2;
    return this.clampCamera(L, { k, tx: ins.left + aw / 2 - cx * k, ty: ins.top + ah / 2 - cy * k }, ins);
  }

  animate(L, target, duration) {
    cancelAnimationFrame(L.raf);
    const from = L.cam || target;
    if (!duration) { L.cam = target; this.applyCamera(L); this.placeBadges(L); return; }
    const { w, h } = this.stageSize();
    const c0 = [(w / 2 - from.tx) / from.k, (h / 2 - from.ty) / from.k];
    const c1 = [(w / 2 - target.tx) / target.k, (h / 2 - target.ty) / target.k];
    const t0 = performance.now();
    const step = (now) => {
      const t = Math.min(1, (now - t0) / duration), e = ease(t);
      const k = Math.exp(Math.log(from.k) + (Math.log(target.k) - Math.log(from.k)) * e);
      const cx = c0[0] + (c1[0] - c0[0]) * e, cy = c0[1] + (c1[1] - c0[1]) * e;
      L.cam = { k, tx: w / 2 - cx * k, ty: h / 2 - cy * k };
      this.applyCamera(L);
      if (t < 1) L.raf = requestAnimationFrame(step);
      else { L.cam = target; this.applyCamera(L); if (L === this.layer) this.placeBadges(L); }
    };
    L.raf = requestAnimationFrame(step);
  }

  applyCamera(L) {
    const { k, tx, ty } = L.cam;
    L.g.setAttribute('transform', `translate(${tx.toFixed(2)} ${ty.toFixed(2)}) scale(${k.toFixed(5)})`);
    L.el.style.setProperty('--zoom', k.toFixed(4));
    this.positionOverlay(L);
  }

  toScreen(L, [x, y]) {
    return [x * L.cam.k + L.cam.tx, y * L.cam.k + L.cam.ty];
  }

  positionOverlay(L) {
    if (!L.cam) return;
    for (const it of L.badges) {
      if (!it.visible) continue;
      const [sx, sy] = this.toScreen(L, it.pos);
      const [ox, oy] = it.offset;
      it.dot.style.transform = `translate(${sx}px, ${sy}px)`;
      it.node.style.transform = `translate(${sx + ox}px, ${sy + oy}px)`;
      const len = Math.hypot(ox, oy) - 28;
      const ang = Math.atan2(oy, ox);
      it.stem.style.transform = `translate(${sx}px, ${sy}px) rotate(${ang}rad)`;
      it.stem.style.width = `${Math.max(0, len)}px`;
    }
    for (const it of L.teams ?? []) {
      const [sx, sy] = this.toScreen(L, it.pos);
      const [ox, oy] = it.offset;
      it.dot.style.transform = `translate(${sx}px, ${sy}px)`;
      it.node.style.transform = `translate(${sx + ox}px, ${sy + oy}px)`;
      it.stem.style.transform = `translate(${sx}px, ${sy}px) rotate(${Math.atan2(oy, ox)}rad)`;
      it.stem.style.width = `${Math.max(0, Math.hypot(ox, oy) - 20)}px`;
    }
    for (const lab of L.labels ?? []) {
      const [x, y, w, h] = lab.rect;
      const [sx, sy] = this.toScreen(L, [x + w / 2, y + h * 0.42]);
      lab.el.style.transform = `translate(${sx}px, ${sy}px)`;
    }
    if (L.pin && this.state?.territory) {
      const r = this.bboxOf(L, this.state.territory);
      if (r) {
        const [sx, sy] = this.toScreen(L, [r[0] + r[2] / 2, r[1]]);
        const { w } = this.stageSize();
        L.pin.style.transform = `translate(${Math.min(w - 120, Math.max(120, sx))}px, ${Math.max(70, sy)}px)`;
      }
    }
  }

  // --------------------------------------------------------------- geometry
  bboxOf(L, id) {
    const p = L.paths.get(id) || L.gSub.querySelector(`[data-id="${CSS.escape(id)}"]`);
    if (p) {
      try {
        const b = p.getBBox();
        if (b.width && b.height) return this.clampRect(L, [b.x, b.y, b.width, b.height]);
      } catch { /* not rendered yet */ }
    }
    const units = geoUnits(this.db, id).filter((u) => L.geo?.[u]);
    return units.length ? this.clampRect(L, this.unionRect(units.map((u) => L.geo[u].bbox))) : null;
  }

  clampRect(L, [x, y, w, h]) {
    const x0 = Math.max(0, x), y0 = Math.max(0, y);
    const x1 = Math.min(L.map.width, x + w), y1 = Math.min(L.map.height, y + h);
    return [x0, y0, Math.max(1, x1 - x0), Math.max(1, y1 - y0)];
  }

  unionRect(boxes) {
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const [x, y, w, h] of boxes) { x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x + w); y1 = Math.max(y1, y + h); }
    return [x0, y0, x1 - x0, y1 - y0];
  }

  /** Rectangle on layer L's map that corresponds to another view (for zoom transitions). */
  regionRectOn(L, viewId) {
    const v = this.db.game.views[viewId];
    if (L.level === 'world') {
      const units = (v?.worldUnits ?? []).filter((u) => L.geo?.[u]);
      return units.length ? this.clampRect(L, this.unionRect(units.map((u) => L.geo[u].bbox))) : null;
    }
    return null;
  }
}
