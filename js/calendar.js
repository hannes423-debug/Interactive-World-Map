// Career calendar: day, month, standings and team views over the whole season,
// with the simulator advancing every league to the career date.
//
// Routes: #/day/<league|all>/<date>  #/month/<league|all>/<yyyy-mm>  #/table/<league>  #/team/<team>

import { loadGame } from './data.js';
import { loadBranding, useGameLogos } from './branding.js';
import * as brand from './branding.js';
import { loadSeason, addDays } from './season.js';
import { result, standings } from './sim.js';

const params = new URLSearchParams(location.search);
const gameId = params.get('game') || 'nhl13';
const SAVE_KEY = `iwm-career:${gameId}`;
const REGION_ORDER = ['north-america', 'europe', 'eurasia'];
const END_LABEL = { REG: 'Final', OT: 'Final/OT', SO: 'Final/SO' };

const $ = (id) => document.getElementById(id);
function h(tag, cls, ...kids) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  for (const k of kids.flat()) if (k != null && k !== false) el.append(k instanceof Node ? k : String(k));
  return el;
}

let db, season, career, route;

// ------------------------------------------------------------------ save
function defaultCareer() {
  return { format: 'iwm-career/1', game: gameId, season: db.game.season, seed: Math.floor(Math.random() * 1e9), date: season.first, team: null, results: {} };
}

function loadCareer() {
  try {
    const s = JSON.parse(localStorage.getItem(SAVE_KEY));
    if (s?.format === 'iwm-career/1' && s.date) return { results: {}, ...s };
  } catch { /* storage unavailable or corrupt: start fresh */ }
  return null;
}

function saveCareer() {
  try { localStorage.setItem(SAVE_KEY, JSON.stringify(career)); } catch { /* private window: keep in memory */ }
}

// ------------------------------------------------------------------ helpers
const team = (id) => db.teams.get(id);
const fmtDate = (iso, opts = { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' }) =>
  new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-GB', { timeZone: 'UTC', ...opts });

function clubMark(id, size = 22) {
  const t = team(id);
  const box = h('span', 'club-mark');
  box.style.setProperty('--s', `${size}px`);
  box.append(brand.img(`club:${id}`, size, t?.name ?? id));
  return box;
}

function leagueMark(id, size = 22) {
  const lg = db.leagues.get(id);
  const box = h('span', 'league-mark');
  box.style.setProperty('--s', `${size}px`);
  box.append(brand.img(`league:${id}`, size, lg?.shortName ?? id));
  return box;
}

function link(r, ...kids) {
  const a = h('a', null, ...kids);
  a.href = format(r);
  return a;
}

function format(r) {
  if (r.tab === 'table') return `#/table/${r.scope}`;
  if (r.tab === 'team') return `#/team/${r.scope}`;
  return `#/${r.tab}/${r.scope ?? 'all'}/${r.tab === 'month' ? (r.date ?? career.date).slice(0, 7) : r.date ?? career.date}`;
}

function parse(hash) {
  const [tab, scope, date] = hash.replace(/^#\/?/, '').split('/').map(decodeURIComponent);
  const r = { tab: ['day', 'month', 'table', 'team'].includes(tab) ? tab : 'day', scope: scope || 'all', date: date || null };
  if (r.tab === 'team' && !db.teams.has(r.scope)) return { tab: 'day', scope: 'all', date: null };
  if (r.tab !== 'team' && r.scope !== 'all' && !season.leagues.has(r.scope)) r.scope = 'all';
  if (r.tab === 'table' && r.scope === 'all') r.scope = career.team ? team(career.team).league : [...season.leagues.keys()][0];
  if (r.tab === 'day' && !/^\d{4}-\d{2}-\d{2}$/.test(r.date ?? '')) r.date = career.date;
  if (r.tab === 'month' && !/^\d{4}-\d{2}$/.test(r.date ?? '')) r.date = career.date.slice(0, 7);
  return r;
}

const go = (r) => { location.hash = format(r); };

function sourceNote(entry) {
  if (!entry.games.length) return h('p', 'source none', entry.clubs.length ? 'No schedule: this competition is not simulated yet.' : 'No clubs in the database yet, so no schedule.');
  if (entry.official) {
    const a = h('a', null, entry.source.name);
    a.href = entry.source.url;
    a.target = '_blank';
    a.rel = 'noopener';
    return h('p', 'source official', h('span', 'tag tag-official', 'Official schedule'), ' Dates and start times as published: ', a, `, fetched ${entry.source.fetched}. Times are venue-local.`);
  }
  return h('p', 'source simulated', h('span', 'tag tag-sim', 'Simulated schedule'),
    ' No published fixtures are loaded for this league. Dates and pairings are generated and are not the real schedule.');
}

function gameStatus(g, res) {
  if (res) return h('span', `status ${res.reported ? 'played' : ''}`, END_LABEL[res.end], res.reported ? ' · played' : '');
  if (g.date === career.date) return h('span', 'status today', 'Today');
  return h('span', 'status', 'Scheduled');
}

function gameRow(g) {
  const res = result(career, season, g, db.teams);
  const mine = career.team && (g.home === career.team || g.away === career.team);
  const side = (id, win) => h('span', `side ${win ? 'win' : ''}`, clubMark(id), link({ tab: 'team', scope: id }, team(id)?.name ?? id));
  return h('li', `game ${mine ? 'mine' : ''}`,
    h('span', 'time', g.time ?? 'TBD', g.time ? h('small', null, 'local') : null),
    side(g.home, res && res.h > res.a),
    h('span', 'score', res ? `${res.h} – ${res.a}` : 'vs'),
    side(g.away, res && res.a > res.h),
    h('span', 'meta', gameStatus(g, res), g.official ? null : h('span', 'tag tag-sim', 'Sim fixture')));
}

// ------------------------------------------------------------------ views
function dayView(r) {
  const nav = h('div', 'datebar',
    link({ ...r, date: addDays(r.date, -1) }, '‹'),
    h('strong', null, fmtDate(r.date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })),
    link({ ...r, date: addDays(r.date, 1) }, '›'),
    r.date !== career.date ? link({ ...r, date: career.date }, 'Career date') : null);
  const games = (season.byDate.get(r.date) ?? []).filter((g) => r.scope === 'all' || g.leagues.includes(r.scope));
  const body = h('div', 'day');
  if (!games.length) body.append(h('p', 'empty', 'No games on this day.'));
  const groups = new Map();
  for (const g of games) {
    const lid = r.scope === 'all' ? g.league : r.scope;
    if (!groups.has(lid)) groups.set(lid, []);
    groups.get(lid).push(g);
  }
  for (const [lid, list] of groups) {
    const entry = season.leagues.get(lid);
    body.append(h('section', 'block',
      h('h3', null, leagueMark(lid), link({ tab: 'table', scope: lid }, entry.lg.name), h('span', `tag ${entry.official ? 'tag-official' : 'tag-sim'}`, entry.official ? 'Official' : 'Simulated')),
      h('ul', 'games', list.map(gameRow))));
  }
  return [nav, r.scope !== 'all' ? sourceNote(season.leagues.get(r.scope)) : null, body];
}

function monthView(r) {
  const [y, m] = r.date.split('-').map(Number);
  const first = `${r.date}-01`;
  const prev = new Date(Date.UTC(y, m - 2, 1)).toISOString().slice(0, 7);
  const next = new Date(Date.UTC(y, m, 1)).toISOString().slice(0, 7);
  const nav = h('div', 'datebar', link({ ...r, date: prev }, '‹'), h('strong', null, fmtDate(first, { month: 'long', year: 'numeric' })), link({ ...r, date: next }, '›'));
  const grid = h('div', 'month');
  for (const d of ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']) grid.append(h('span', 'dow', d));
  const lead = (new Date(`${first}T12:00:00Z`).getUTCDay() + 6) % 7;
  for (let i = 0; i < lead; i++) grid.append(h('span', 'cell pad'));
  for (let d = first; d.startsWith(r.date); d = addDays(d, 1)) {
    const games = (season.byDate.get(d) ?? []).filter((g) => r.scope === 'all' || g.leagues.includes(r.scope));
    const cls = ['cell', d === career.date && 'today', d < career.date && 'past', games.length && 'has'].filter(Boolean).join(' ');
    const cell = link({ tab: 'day', scope: r.scope, date: d }, h('span', 'num', Number(d.slice(8))));
    cell.className = cls;
    const mine = career.team && games.find((g) => g.home === career.team || g.away === career.team);
    if (mine) {
      const res = result(career, season, mine, db.teams);
      const home = mine.home === career.team;
      const opp = home ? mine.away : mine.home;
      const won = res && (home ? res.h > res.a : res.a > res.h);
      cell.append(h('span', `mygame ${res ? (won ? 'w' : 'l') : ''}`, clubMark(opp, 18), home ? 'vs' : '@',
        res ? ` ${won ? 'W' : res.end === 'REG' ? 'L' : 'OTL'} ${home ? res.h : res.a}–${home ? res.a : res.h}` : ''));
    }
    if (games.length) cell.append(h('span', 'count', `${games.length} game${games.length > 1 ? 's' : ''}`));
    grid.append(cell);
  }
  return [nav, r.scope !== 'all' ? sourceNote(season.leagues.get(r.scope)) : null, grid];
}

function tableView(r) {
  const entry = season.leagues.get(r.scope);
  const three = entry.rules.points === '3pt';
  const rows = standings(career, season, r.scope, db.teams);
  const head = three ? ['#', 'Club', 'GP', 'W', 'OTW', 'OTL', 'L', 'GF', 'GA', '+/-', 'Pts', 'Form'] : ['#', 'Club', 'GP', 'W', 'L', 'OTL', 'GF', 'GA', '+/-', 'Pts', 'Form'];
  const table = h('table', 'standings', h('thead', null, h('tr', null, head.map((c) => h('th', null, c)))));
  const tb = h('tbody');
  rows.forEach((row, i) => {
    const nums = three ? [row.gp, row.w, row.otw, row.otl, row.l] : [row.gp, row.w + row.otw, row.l, row.otl];
    const gd = row.gf - row.ga;
    tb.append(h('tr', row.id === career.team ? 'mine' : null,
      h('td', null, i + 1),
      h('td', null, h('span', 'club', clubMark(row.id), link({ tab: 'team', scope: row.id }, team(row.id)?.name ?? row.id))),
      nums.map((n) => h('td', null, n)), h('td', null, row.gf), h('td', null, row.ga), h('td', null, gd > 0 ? `+${gd}` : gd),
      h('td', 'pts', row.pts), h('td', null, h('span', 'form', row.form.map((f) => h('i', `f-${f}`, f))))));
  });
  table.append(tb);
  return [
    h('div', 'datebar', leagueMark(r.scope, 32), h('strong', null, `${entry.lg.name} · standings`), h('span', 'sub', `as of ${fmtDate(career.date)}`)),
    sourceNote(entry),
    entry.clubs.length ? h('div', 'table-wrap', table) : null,
    h('p', 'note', three ? 'Points: regulation win 3, overtime/shootout win 2, overtime/shootout loss 1.' : 'Points: win 2, overtime/shootout loss 1.',
      ' All results are simulated; club ratings are placeholders until rosters exist.'),
  ];
}

function teamView(r) {
  const t = team(r.scope);
  const entry = season.leagues.get(t.league);
  const games = season.games.filter((g) => g.home === t.id || g.away === t.id);
  let w = 0, l = 0, o = 0;
  const list = h('ul', 'games');
  for (const g of games) {
    const res = result(career, season, g, db.teams);
    if (res) {
      const won = g.home === t.id ? res.h > res.a : res.a > res.h;
      if (won) w++; else if (res.end === 'REG') l++; else o++;
    }
    const row = gameRow(g);
    row.prepend(h('span', 'date', link({ tab: 'day', scope: g.league, date: g.date }, fmtDate(g.date, { weekday: 'short', day: 'numeric', month: 'short' }))));
    list.append(row);
  }
  const pick = h('button', 'btn', career.team === t.id ? 'Your club' : 'Make this my club');
  pick.disabled = career.team === t.id;
  pick.addEventListener('click', () => { career.team = t.id; saveCareer(); render(); });
  return [
    h('div', 'datebar', clubMark(t.id, 40), h('strong', null, t.name), link({ tab: 'table', scope: t.league }, entry.lg.shortName), h('span', 'sub', `${w}–${l}–${o}`), pick),
    sourceNote(entry),
    games.length ? list : h('p', 'empty', 'No fixtures for this club.'),
  ];
}

// ------------------------------------------------------------------ chrome
function sidebar() {
  const nav = $('leagues');
  nav.replaceChildren();
  const scope = route.tab === 'team' ? team(route.scope).league : route.scope;
  const tab = route.tab === 'team' ? 'table' : route.tab;
  const item = (id, label, mark, tag) => {
    const a = link({ tab: id === 'all' && tab === 'table' ? 'day' : tab, scope: id, date: route.tab === 'month' ? route.date : career.date }, mark, h('span', 'lname', label), tag);
    if (id === scope) a.setAttribute('aria-current', 'true');
    return h('li', null, a);
  };
  nav.append(h('ul', null, item('all', 'All leagues', h('span', 'league-mark all'), null)));
  const groups = new Map(REGION_ORDER.map((v) => [v, []]));
  for (const [id, e] of season.leagues) {
    const v = groups.has(e.lg.homeView) ? e.lg.homeView : REGION_ORDER[0];
    groups.get(v).push([id, e]);
  }
  for (const [v, list] of groups) {
    if (!list.length) continue;
    nav.append(h('p', 'group', db.game.views[v]?.title ?? v));
    nav.append(h('ul', null, list.map(([id, e]) => item(id, e.lg.shortName ?? e.lg.name, leagueMark(id),
      h('span', `tag ${!e.games.length ? 'tag-none' : e.official ? 'tag-official' : 'tag-sim'}`, !e.games.length ? '—' : e.official ? 'Official' : 'Sim')))));
  }
}

function tabs() {
  const scope = route.tab === 'team' ? team(route.scope).league : route.scope;
  const t = $('tabs');
  t.replaceChildren();
  const add = (tab, label, r) => {
    const a = link(r, label);
    if (route.tab === tab) a.setAttribute('aria-current', 'page');
    t.append(a);
  };
  add('day', 'Day', { tab: 'day', scope, date: route.tab === 'day' ? route.date : career.date });
  add('month', 'Calendar', { tab: 'month', scope, date: (route.tab === 'day' ? route.date : career.date).slice(0, 7) });
  add('table', 'Standings', { tab: 'table', scope: scope === 'all' ? (career.team ? team(career.team).league : 'nhl') : scope });
  if (career.team) add('team', 'My club', { tab: 'team', scope: career.team });
}

function header() {
  $('career-date').textContent = fmtDate(career.date, { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
  const t = career.team && team(career.team);
  $('career-team').replaceChildren(...(t ? [clubMark(t.id, 24), t.name] : ['No club chosen']));
  const played = season.games.filter((g) => g.date < career.date).length;
  $('progress').value = played / Math.max(1, season.games.length);
  $('progress-label').textContent = `${played.toLocaleString('en')} of ${season.games.length.toLocaleString('en')} games played`;
  const next = career.team && season.games.find((g) => g.date >= career.date && (g.home === career.team || g.away === career.team));
  $('sim-next').hidden = !next;
  $('sim-next').dataset.date = next?.date ?? '';
  $('sim-to').min = career.date;
  $('sim-to').max = addDays(season.last, 1);
}

function render() {
  route = parse(location.hash);
  header();
  sidebar();
  tabs();
  const view = { day: dayView, month: monthView, table: tableView, team: teamView }[route.tab](route);
  $('view').replaceChildren(...view.flat().filter(Boolean));
}

function advanceTo(date) {
  const end = addDays(season.last, 1);
  career.date = date > end ? end : date < career.date ? career.date : date;
  saveCareer();
  if (route.tab === 'day') go({ ...route, date: career.date });
  render();
}

// ------------------------------------------------------------------ career dialog
function careerDialog() {
  const dlg = $('career-dialog');
  const lsel = $('c-league'), tsel = $('c-team');
  lsel.replaceChildren(h('option', null, '— choose a league —'));
  lsel.firstChild.value = '';
  for (const [id, e] of season.leagues) {
    if (!e.clubs.length || !e.games.length) continue;
    const o = h('option', null, `${e.lg.name}${e.official ? '' : ' (simulated schedule)'}`);
    o.value = id;
    lsel.append(o);
  }
  const fillTeams = () => {
    tsel.replaceChildren(...season.leagues.get(lsel.value)?.clubs.map((id) => {
      const o = h('option', null, team(id).name);
      o.value = id;
      return o;
    }).sort((a, b) => a.textContent.localeCompare(b.textContent)) ?? []);
  };
  lsel.onchange = fillTeams;
  lsel.value = career.team ? team(career.team).league : '';
  fillTeams();
  if (career.team) tsel.value = career.team;
  $('c-seed').value = career.seed;
  dlg.showModal();
}

function startCareer() {
  const seed = Number($('c-seed').value) || Math.floor(Math.random() * 1e9);
  career = { ...defaultCareer(), seed, team: $('c-team').value || null };
  saveCareer();
  $('career-dialog').close();
  go(career.team ? { tab: 'team', scope: career.team } : { tab: 'day', scope: 'all', date: career.date });
  render();
}

function exportCareer() {
  const blob = new Blob([JSON.stringify(career, null, 1)], { type: 'application/json' });
  const a = h('a');
  a.href = URL.createObjectURL(blob);
  a.download = `career-${gameId}-${career.date}.json`;
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

async function importCareer(file) {
  try {
    const s = JSON.parse(await file.text());
    if (s.format !== 'iwm-career/1' || s.game !== gameId) throw new Error('not a career save for this game');
    career = { results: {}, ...s };
    saveCareer();
    $('career-dialog').close();
    render();
  } catch (err) {
    alert(`Could not import: ${err.message}`);
  }
}

// ------------------------------------------------------------------ boot
async function boot() {
  try {
    db = await loadGame(gameId);
    await loadBranding();
    useGameLogos(db);
    season = await loadSeason(db);
  } catch (err) {
    $('view').replaceChildren(h('p', 'empty', `Could not load the season: ${err.message}`));
    return;
  }
  document.title = `Career Calendar · ${db.game.title}`;
  $('season').textContent = `${db.game.title} · Season ${db.game.season}`;
  $('to-map').href = `career-map.html?game=${encodeURIComponent(gameId)}#/world`;
  career = loadCareer() ?? defaultCareer();
  saveCareer();

  $('sim-day').onclick = () => advanceTo(addDays(career.date, 1));
  $('sim-week').onclick = () => advanceTo(addDays(career.date, 7));
  $('sim-next').onclick = (e) => advanceTo(e.currentTarget.dataset.date);
  $('sim-end').onclick = () => advanceTo(addDays(season.last, 1));
  $('sim-to').onchange = (e) => e.target.value && advanceTo(e.target.value);
  $('career-btn').onclick = careerDialog;
  $('c-start').onclick = startCareer;
  $('c-export').onclick = exportCareer;
  $('c-import').onchange = (e) => e.target.files[0] && importCareer(e.target.files[0]);
  $('c-cancel').onclick = () => $('career-dialog').close();
  addEventListener('hashchange', render);
  if (!location.hash) history.replaceState(null, '', career.team ? format({ tab: 'team', scope: career.team }) : format({ tab: 'day', scope: 'all', date: career.date }));
  render();
}

boot();
