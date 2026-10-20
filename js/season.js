// Season data: fixtures for every league in a game, plus each league's rules.
//
// Official fixtures come from data/hockey/fixtures/<season>/<league>.json
// (written by tools/fixtures/fetch_fixtures.py from the leagues' own feeds).
// A league without such a file gets a generated double round-robin whose
// games carry official: false, so the UI can never pass it off as a published
// schedule.

const FIXTURES = 'data/hockey/fixtures/2026-27/';

// Points systems: '2pt' = win 2 (any), OT/SO loss 1; '3pt' = regulation win 3, OT/SO win 2, OT/SO loss 1.
const THREE_POINT = new Set(['shl', 'allsvenskan', 'liiga', 'mestis', 'czech-extraliga', 'nl', 'swiss-league', 'del', 'del2', 'icehl',
  'slovak-extraliga', 'belarus-extraleague', 'kazakhstan', 'champions', 'asia-league']);

// Placeholder playing strength per league (0-100) until rosters drive ratings.
const STRENGTH = { nhl: 100, khl: 84, ahl: 78, shl: 80, nl: 80, liiga: 77, 'czech-extraliga': 76, del: 75, icehl: 70, allsvenskan: 68,
  'slovak-extraliga': 66, vhl: 65, echl: 64, 'swiss-league': 62, del2: 62, eihl: 62, mestis: 60, 'belarus-extraleague': 58,
  kazakhstan: 56, ncaa: 56, 'asia-league': 55, ohl: 55, whl: 55, qmjhl: 54, ushl: 52, mhl: 50 };
const JUNIOR_SCORING = new Set(['ohl', 'whl', 'qmjhl', 'ushl', 'mhl']);

export function rules(lg) {
  const level = lg?.tier?.level > 0 ? lg.tier.level : 3;
  return {
    points: THREE_POINT.has(lg.id) ? '3pt' : '2pt',
    strength: STRENGTH[lg.id] ?? 100 - 10 * (level - 1),
    goals: JUNIOR_SCORING.has(lg.id) ? 3.3 : 2.95,
  };
}

async function getJSON(url) {
  try {
    const r = await fetch(url, { cache: 'no-cache' });
    return r.ok ? await r.json() : null;
  } catch {
    return null;
  }
}

/**
 * Load the season for a game db (from data.js).
 * Returns { games, byDate, leagues: Map(id -> {lg, rules, official, source, clubs, games}) , first, last }.
 * A game: { key, league, leagues[], date, time, start, home, away, official }.
 */
export async function loadSeason(db) {
  const index = await getJSON(FIXTURES + 'index.json');
  const leagueIds = [...db.leagues.keys()];
  const files = await Promise.all(leagueIds.map((id) => (index?.leagues?.[id] ? getJSON(`${FIXTURES}${id}.json`) : null)));

  const leagues = new Map();
  const byKey = new Map();
  const add = (g) => {
    // inter-league games are published by both leagues: keep one, count it for both
    const k = `${g.date}|${g.home}|${g.away}`;
    const dup = byKey.get(k);
    if (dup) { if (!dup.leagues.includes(g.league)) dup.leagues.push(g.league); return dup; }
    g.leagues = [g.league];
    byKey.set(k, g);
    return g;
  };

  leagueIds.forEach((id, i) => {
    const lg = db.leagues.get(id);
    const clubs = [...db.teams.values()].filter((t) => t.league === id).map((t) => t.id);
    const entry = { lg, rules: rules(lg), clubs, official: false, source: null, games: [] };
    leagues.set(id, entry);
    const doc = files[i];
    if (doc?.games?.length) {
      entry.official = doc.status === 'official';
      entry.source = doc.source;
      const col = Object.fromEntries(doc.columns.map((c, j) => [c, j]));
      for (const r of doc.games) {
        if (!db.teams.has(r[col.home]) || !db.teams.has(r[col.away])) continue;
        entry.games.push(add({ key: `${id}:${r[col.id]}`, league: id, date: r[col.date], time: r[col.time], start: r[col.start],
          home: r[col.home], away: r[col.away], official: entry.official }));
      }
    } else if (lg.kind !== 'international' && clubs.length >= 4) {
      for (const g of generate(id, clubs)) entry.games.push(add(g));
    }
  });

  const games = [...byKey.values()].sort((a, b) => (a.date + (a.time ?? '99')).localeCompare(b.date + (b.time ?? '99')));
  const byDate = new Map();
  for (const g of games) {
    if (!byDate.has(g.date)) byDate.set(g.date, []);
    byDate.get(g.date).push(g);
  }
  return { games, byDate, leagues, first: games[0]?.date ?? '2026-09-01', last: games.at(-1)?.date ?? '2027-04-30' };
}

// ------------------------------------------------------- simulated schedule
const SIM_START = '2026-09-12', SIM_END = '2027-03-07';
const PLAY_DAYS = new Set([2, 4, 5, 6]);  // Tue, Thu, Fri, Sat

export function addDays(iso, n) {
  const d = new Date(`${iso}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

/** Circle-method round robin, repeated with home/away swapped, spread over the season window. */
function generate(league, clubs) {
  const ids = [...clubs].sort();
  if (ids.length % 2) ids.push(null);
  const n = ids.length;
  const single = [];
  for (let r = 0; r < n - 1; r++) {
    const round = [];
    for (let i = 0; i < n / 2; i++) {
      const a = ids[i], b = ids[n - 1 - i];
      if (a && b) round.push(r % 2 ? [a, b] : [b, a]);
    }
    single.push(round);
    ids.splice(1, 0, ids.pop());
  }
  // about 50 games a club: 2, 4 or 6 meetings
  const cycles = Math.max(2, 2 * Math.round(50 / (n - 1) / 2));
  const rounds = [];
  for (let c = 0; c < cycles; c++) for (const round of single) rounds.push(round.map(([h, a]) => (c % 2 ? [a, h] : [h, a])));

  const days = [];
  for (let d = SIM_START; d <= SIM_END; d = addDays(d, 1)) if (PLAY_DAYS.has(new Date(`${d}T12:00:00Z`).getUTCDay())) days.push(d);
  const out = [];
  rounds.forEach((round, r) => {
    const date = days[Math.min(days.length - 1, Math.floor((r * days.length) / rounds.length))];
    round.forEach(([home, away], i) => out.push({ key: `${league}:sim-${r}-${i}`, league, date, time: null, start: null, home, away, official: false }));
  });
  return out;
}
