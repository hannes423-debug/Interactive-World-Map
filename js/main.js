// Career map entry point: routing, header, breadcrumbs, panels.
import { loadGame, leaguesIn, territoryPath } from './data.js';
import { MapStage } from './map.js';
import { territoryPanel, leaguePanel, tournamentPanel } from './panel.js';
import { loadBranding } from './branding.js';
import * as router from './router.js';

const $ = (s) => document.querySelector(s);
const params = new URLSearchParams(location.search);
const gameId = (params.get('game') || 'nhl13').replace(/[^a-z0-9_-]/gi, '');

const ui = {
  app: $('#app'),
  stage: $('#stage'),
  title: $('#view-title'),
  subtitle: $('#view-subtitle'),
  brand: $('#brand'),
  crumbs: $('#crumbs'),
  back: $('#back'),
  panel: $('#panel'),
  panelBody: $('#panel-content'),
  panelClose: $('#panel-close'),
  explore: $('#explore'),
  exploreList: $('#explore-list'),
  exploreTitle: $('#explore-title'),
  toast: $('#toast'),
};

let db, stage, route = null;

function go(r, replace = false) {
  const hash = router.format(r);
  if (replace) history.replaceState(null, '', hash);
  if (location.hash === hash) render();
  else if (replace) render();
  else location.hash = hash;
}

function toast(msg) {
  ui.toast.textContent = msg;
  ui.toast.classList.add('visible');
  clearTimeout(toast.t);
  toast.t = setTimeout(() => ui.toast.classList.remove('visible'), 3800);
}

/** Make any parsed route valid for this game; unknown ids fall back gracefully. */
function normalise(r) {
  const views = db.game.views;
  const root = db.game.rootView;
  const out = { view: r.view, territory: r.territory, info: r.info, league: r.league, tournament: r.tournament };
  if (!views[out.view] || !db.maps[views[out.view].map]) {
    if (out.view) toast(`Map "${out.view}" is not available - showing the world map`);
    out.view = root;
  }
  if (out.territory) {
    const t = db.territories.get(out.territory);
    if (!t) { toast(`Unknown territory "${out.territory}"`); out.territory = null; out.info = false; }
    else if (!(t.views ?? []).includes(out.view) || views[out.view].level === 'world') out.view = t.homeView ?? out.view;
  }
  if (out.league) {
    const lg = db.leagues.get(out.league);
    if (!lg) { toast(`Unknown league "${out.league}"`); out.league = null; }
    else if (views[out.view].level === 'world' && !out.territory) out.view = lg.homeView ?? out.view;
  }
  if (out.tournament && !db.tournaments[out.tournament]) { toast(`Unknown competition "${out.tournament}"`); out.tournament = null; }
  if (out.league) out.tournament = null;
  if (!out.territory) out.info = false;
  return out;
}

const nav = {
  tournament(id) {
    if (db.tournaments[id]) go({ ...route, league: null, tournament: id });
  },
  territory(id, info = true) {
    const t = db.territories.get(id);
    if (!t) return;
    const view = (t.views ?? []).includes(route.view) && db.game.views[route.view].level !== 'world' ? route.view : t.homeView;
    go({ view, territory: id, info, league: null });
  },
  league(id) {
    const lg = db.leagues.get(id);
    if (!lg) return;
    const keepTerr = route.territory && leaguesIn(db, route.territory).some((x) => x.league.id === id);
    const viewOk = db.game.views[route.view]?.level !== 'world' && db.badges.some((b) => b.league === id && (b.views ?? []).includes(route.view));
    go({ view: keepTerr || viewOk ? route.view : lg.homeView, territory: keepTerr ? route.territory : null, info: false, league: id });
  },
};

const handlers = {
  onRegion: (id) => go({ view: id }),
  onTerritory: (id) => {
    if (route.territory === id && !route.league) go({ ...route, info: true });
    else go({ view: route.view, territory: id, info: false, league: null });
  },
  onBadge: (b) => {
    const a = b.action ?? { type: 'league', id: b.league };
    if (a.type === 'league') nav.league(a.id ?? b.league);
    else if (a.type === 'territory') nav.territory(a.id);
    else if (a.type === 'view') go({ view: a.id });
  },
  onBackground: () => {
    if (route.league || route.tournament || route.info || route.territory) back();
  },
};

function back() {
  const up = router.parent(route, db.game.rootView);
  if (up) go(up);
}

function levelOf(view) { return { world: 0, region: 1 }[db.game.views[view]?.level] ?? 1; }

async function render() {
  const prev = route;
  route = normalise(router.parse(location.hash));
  const canonical = router.format(route);
  if (location.hash !== canonical) history.replaceState(null, '', canonical);

  const view = db.game.views[route.view];
  document.title = `${view.title} · ${db.game.title}`;
  ui.app.dataset.level = view.level;
  ui.title.textContent = route.tournament ? db.tournaments[route.tournament]?.name : route.league ? db.leagues.get(route.league)?.name
    : route.territory ? db.territories.get(route.territory)?.name : view.title;
  ui.subtitle.textContent = route.territory || route.league ? view.title : (view.level === 'world' ? db.game.subtitle : `Select a territory · ${db.game.season} season`);
  renderCrumbs(view);
  ui.back.hidden = !router.parent(route, db.game.rootView);

  const panelOpen = !!(route.info || route.league || route.tournament);
  await renderPanel(panelOpen);
  renderExplore(view);

  const dir = !prev || prev.view === route.view ? 'none' : levelOf(route.view) > levelOf(prev.view) ? 'in' : levelOf(route.view) < levelOf(prev.view) ? 'out' : 'none';
  await stage.show(route.view, { territory: route.territory, info: route.info, league: route.league }, dir);
}

function renderCrumbs(view) {
  const items = [{ label: db.game.views[db.game.rootView].title, r: { view: db.game.rootView } }];
  if (route.view !== db.game.rootView) items.push({ label: view.title, r: { view: route.view } });
  if (route.territory) {
    const t = db.territories.get(route.territory);
    const p = t?.parent && db.territories.get(t.parent);
    if (p) items.push({ label: p.name, r: { view: route.view, territory: p.id, info: true } });
    items.push({ label: t?.name ?? route.territory, r: { view: route.view, territory: route.territory, info: true } });
  }
  if (route.league) items.push({ label: db.leagues.get(route.league)?.shortName ?? route.league, r: route });
  if (route.tournament) items.push({ label: db.tournaments[route.tournament]?.short ?? db.tournaments[route.tournament]?.name, r: route });
  ui.crumbs.replaceChildren();
  if (items.length < 2) return;
  items.forEach((it, i) => {
    const li = document.createElement('li');
    if (i === items.length - 1) { li.textContent = it.label; li.setAttribute('aria-current', 'page'); }
    else {
      const a = document.createElement('a');
      a.href = router.format({ territory: null, info: false, league: null, ...it.r });
      a.textContent = it.label;
      li.append(a);
    }
    ui.crumbs.append(li);
  });
}

async function renderPanel(open) {
  ui.app.classList.toggle('panel-open', open);
  ui.panel.setAttribute('aria-hidden', String(!open));
  if (open) {
    let content;
    if (route.tournament) content = tournamentPanel(db, route.tournament, nav);
    else if (route.league) content = leaguePanel(db, route.league, nav);
    else {
      const { quality } = await territoryPath(db, db.game.views[route.view].map, route.territory);
      content = territoryPanel(db, route.territory, nav, quality);
    }
    ui.panelBody.replaceChildren(content);
    ui.panelBody.scrollTop = 0;
  }
  updateInsets(open);
}

function updateInsets(open) {
  const narrow = window.matchMedia('(max-width: 820px)').matches;
  const header = $('#topbar').getBoundingClientRect().height;
  const rect = ui.panel.getBoundingClientRect();
  stage.setInsets({
    top: header + 8,
    left: narrow ? 0 : 24,
    right: open && !narrow ? rect.width + 24 : 0,
    bottom: open && narrow ? rect.height : 0,
  });
}

function renderExplore(view) {
  const list = ui.exploreList;
  list.replaceChildren();
  const add = (label, sub, onClick, cls = '') => {
    const li = document.createElement('li');
    const b = document.createElement('button');
    b.type = 'button';
    b.className = cls;
    b.innerHTML = '<span></span><small></small>';
    b.firstChild.textContent = label;
    b.lastChild.textContent = sub;
    b.addEventListener('click', onClick);
    li.append(b);
    list.append(li);
  };
  if (view.level === 'world') {
    ui.exploreTitle.textContent = 'Regions';
    for (const rid of view.regions ?? []) {
      const rv = db.game.views[rid];
      const n = (rv.territories ?? []).length;
      add(rv.title, `${n} territories`, () => go({ view: rid }));
    }
    for (const t of Object.values(db.tournaments).filter((x) => x.featured)) {
      add(t.name, 'International', () => nav.tournament(t.id), 'secondary');
    }
    return;
  }
  ui.exploreTitle.textContent = `Territories · ${view.title}`;
  for (const tid of view.territories ?? []) {
    const t = db.territories.get(tid);
    if (!t) continue;
    const n = leaguesIn(db, tid).length;
    add(t.name, n ? `${n} league${n === 1 ? '' : 's'}` : 'No leagues yet', () => handlers.onTerritory(tid), tid === route.territory ? 'current' : '');
  }
  // hockey regions and territories without a drawn boundary are reachable from here
  const others = [...db.territories.values()].filter((t) => (t.views ?? []).includes(route.view) && !(view.territories ?? []).includes(t.id) && (t.kind === 'region' || !(t.geo ?? []).length));
  for (const t of others) {
    add(t.name, t.kind === 'region' ? 'Hockey region' : 'No map boundary yet', () => nav.territory(t.id), 'secondary');
  }
}

async function boot() {
  try {
    [db] = await Promise.all([loadGame(gameId), loadBranding()]);
  } catch (err) {
    ui.app.classList.add('failed');
    $('#boot-error').hidden = false;
    $('#boot-error-msg').textContent = `Could not load game "${gameId}": ${err.message}. ` +
      (location.protocol === 'file:' ? 'Browsers block data files on file:// - start a local web server (see README).' : '');
    return;
  }
  ui.brand.textContent = db.game.title;
  stage = new MapStage(ui.stage, db, handlers);
  ui.back.addEventListener('click', back);
  ui.panelClose.addEventListener('click', back);
  $('#explore-toggle').addEventListener('click', () => ui.explore.classList.toggle('collapsed'));
  window.addEventListener('hashchange', render);
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !e.defaultPrevented) back();
  });
  window.addEventListener('resize', () => updateInsets(!!(route?.info || route?.league || route?.tournament)));
  ui.panel.addEventListener('click', (e) => e.stopPropagation());
  // preload the other map images in the background
  setTimeout(() => Object.values(db.maps).forEach((m) => { const i = new Image(); i.src = m.image; }), 1500);
  if (db.warnings.length) console.info(`[career-map] ${db.warnings.length} data warning(s)`);
  window.careerMap = { db, get route() { return route; }, stage };
  await render();
  document.body.classList.add('ready');
}

boot();
