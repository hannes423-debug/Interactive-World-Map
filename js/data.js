// Loads a game's data files and builds lookup indexes.
// All references between files use stable ids; anything that does not resolve
// is reported in db.warnings and skipped, never thrown.

import { ringsToPath } from './projection.js';

async function fetchJSON(url) {
  const res = await fetch(url, { cache: 'no-cache' });
  if (!res.ok) throw new Error(`${url}: HTTP ${res.status}`);
  return res.json();
}

async function tryJSON(url, warnings) {
  try {
    return await fetchJSON(url);
  } catch (err) {
    warnings.push(`Could not load ${url} (${err.message})`);
    return null;
  }
}

export async function loadGame(gameId) {
  const warnings = [];
  const base = `games/${encodeURIComponent(gameId)}/`;
  // game.json and maps.json are required; the rest degrade to empty lists.
  const [game, maps] = await Promise.all([fetchJSON(base + 'game.json'), fetchJSON('data/maps.json')]);
  const [terr, leagues, teams, badges, tournaments] = await Promise.all(
    ['territories', 'leagues', 'teams', 'badges', 'tournaments'].map((n) => tryJSON(`${base}${n}.json`, warnings)),
  );

  const db = {
    id: gameId,
    game,
    maps: maps.views,
    territories: new Map((terr?.territories ?? []).map((t) => [t.id, t])),
    leagues: new Map((leagues?.leagues ?? []).map((l) => [l.id, l])),
    teams: new Map((teams?.teams ?? []).map((t) => [t.id, t])),
    badges: badges?.badges ?? [],
    tournaments: Object.fromEntries((tournaments?.tournaments ?? []).map((t) => [t.id, t])),
    warnings,
    viewGeo: new Map(),
    rawGeo: null,
  };
  validate(db);
  return db;
}

function validate(db) {
  const w = db.warnings;
  for (const [vid, v] of Object.entries(db.game.views ?? {})) {
    if (!db.maps[v.map]) w.push(`View "${vid}" uses unknown map "${v.map}"`);
    for (const t of v.territories ?? []) if (!db.territories.has(t)) w.push(`View "${vid}" lists unknown territory "${t}"`);
  }
  for (const t of db.territories.values()) {
    if (t.parent && !db.territories.has(t.parent)) w.push(`Territory "${t.id}" has unknown parent "${t.parent}"`);
    for (const m of t.members ?? []) if (!db.territories.has(m)) w.push(`Territory "${t.id}" has unknown member "${m}"`);
  }
  for (const l of db.leagues.values()) {
    for (const t of l.territories ?? []) if (!db.territories.has(t)) w.push(`League "${l.id}" covers unknown territory "${t}"`);
    for (const c of l.clubs ?? []) if (!db.teams.has(c)) w.push(`League "${l.id}" lists unknown club "${c}"`);
  }
  for (const b of db.badges) {
    if (b.league && !db.leagues.has(b.league)) w.push(`Badge "${b.id}" points to unknown league "${b.league}"`);
  }
  for (const msg of w) console.warn('[career-map]', msg);
}

/** Traced outlines for one map image (data/geo/views/<map>.json), cached. */
export async function loadViewGeo(db, mapId) {
  if (!db.viewGeo.has(mapId)) {
    db.viewGeo.set(mapId, tryJSON(`data/geo/views/${mapId}.json`, db.warnings).then((g) => g?.features ?? {}));
  }
  return db.viewGeo.get(mapId);
}

/** Natural Earth lon/lat outlines, only loaded when a unit has no traced outline. */
async function loadRawGeo(db) {
  if (!db.rawGeo) {
    db.rawGeo = Promise.all([
      tryJSON('data/geo/countries.json', db.warnings),
      tryJSON('data/geo/subdivisions.json', db.warnings),
    ]).then(([c, s]) => ({ ...(c?.features ?? {}), ...(s?.features ?? {}) }));
  }
  return db.rawGeo;
}

// ---------------------------------------------------------------- queries
export const territory = (db, id) => db.territories.get(id);
export const league = (db, id) => db.leagues.get(id);

export function ancestors(db, id) {
  const out = [];
  let t = db.territories.get(id);
  while (t?.parent && !out.includes(t.parent)) {
    out.push(t.parent);
    t = db.territories.get(t.parent);
  }
  return out;
}

export function children(db, id) {
  return [...db.territories.values()].filter((t) => t.parent === id);
}

/** Geo unit ids (country / subdivision codes) that make up a territory. */
export function geoUnits(db, id, seen = new Set()) {
  if (seen.has(id)) return [];
  seen.add(id);
  const t = db.territories.get(id);
  if (!t) return [];
  const units = new Set(t.geo ?? []);
  for (const m of t.members ?? []) for (const u of geoUnits(db, m, seen)) units.add(u);
  return [...units];
}

/** Does league L cover territory T (directly, through a parent, or through a region)? */
function covers(db, lg, tid) {
  const scope = new Set([tid, ...ancestors(db, tid)]);
  return (lg.territories ?? []).some((lt) => {
    if (scope.has(lt)) return true;
    const r = db.territories.get(lt);
    return r?.kind === 'region' && (r.members ?? []).some((m) => scope.has(m));
  });
}

/** Leagues playing in a territory, including those only in its subdivisions. */
export function leaguesIn(db, tid) {
  const out = [];
  const subs = children(db, tid).map((c) => c.id);
  for (const lg of db.leagues.values()) {
    if (covers(db, lg, tid)) out.push({ league: lg, via: null });
    else {
      const via = subs.filter((s) => covers(db, lg, s));
      if (via.length) out.push({ league: lg, via });
    }
  }
  return out.sort((a, b) => tierRank(a.league) - tierRank(b.league));
}

export function tierRank(lg) {
  const level = lg?.tier?.level;
  return typeof level === 'number' && level > 0 ? level : 99;
}

/** Territories a league is shown on (regions expanded to members). */
export function coverage(db, lg) {
  const out = new Set();
  for (const t of lg.territories ?? []) {
    out.add(t);
    const r = db.territories.get(t);
    if (r?.kind === 'region') for (const m of r.members ?? []) out.add(m);
  }
  return [...out];
}

/** SVG path for a territory on a map: traced outline, else calibrated approximation. */
export async function territoryPath(db, mapId, id) {
  const units = geoUnits(db, id);
  if (!units.length) return { d: '', quality: 'none', units };
  const traced = await loadViewGeo(db, mapId);
  let d = '';
  const missing = [];
  for (const u of units) {
    if (traced[u]) { d += traced[u].d; continue; }
    // a country drawn as subdivisions on this map (e.g. Canada as provinces)
    const parts = Object.values(traced).filter((f) => f.kind === 'subdivision' && f.country === u);
    if (parts.length) parts.forEach((f) => { d += f.d; });
    else missing.push(u);
  }
  let quality = missing.length ? 'partial' : 'traced';
  if (missing.length) {
    const raw = await loadRawGeo(db);
    const view = db.maps[mapId];
    let any = false;
    for (const u of missing) {
      if (!raw[u]) continue;
      const p = ringsToPath(view, raw[u].rings);
      if (p) { d += p; any = true; }
    }
    if (!d) quality = 'none';
    else if (any && missing.length === units.length) quality = 'approximate';
  }
  return { d, quality, units };
}
