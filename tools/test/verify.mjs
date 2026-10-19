#!/usr/bin/env node
// Browser verification of the career map (dev-time only; the site itself needs no Node).
//
// Serves the repository under /Interactive-World-Map/ - the same sub-path a
// GitHub Pages project site uses - and drives it with Playwright/Chromium.
//
//   node tools/test/verify.mjs                 # all checks
//   PW_CHROMIUM=/path/to/chrome node tools/test/verify.mjs
//
// Needs the `playwright` package resolvable from this folder or NODE_PATH.
// Writes screenshots to tools/test/out/.

import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const OUT = path.join(ROOT, 'tools', 'test', 'out');
const BASE = '/Interactive-World-Map/';
fs.mkdirSync(OUT, { recursive: true });

const require = createRequire(import.meta.url);
let playwright;
for (const p of ['playwright', '/opt/node-tools/node_modules/playwright']) {
  try { playwright = require(p); break; } catch { /* try next */ }
}
if (!playwright) { console.error('playwright not found (npm i -D playwright)'); process.exit(2); }

// ------------------------------------------------------------ static server
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml' };
const requests = [];
const server = http.createServer((req, res) => {
  const url = decodeURIComponent(req.url.split('?')[0]);
  requests.push(url);
  if (!url.startsWith(BASE)) { res.writeHead(404); return res.end('outside project path'); }
  let file = path.join(ROOT, url.slice(BASE.length));
  if (!file.startsWith(ROOT)) { res.writeHead(403); return res.end(); }
  if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
  if (!fs.existsSync(file)) { res.writeHead(404); return res.end('not found'); }
  res.writeHead(200, { 'content-type': TYPES[path.extname(file)] ?? 'application/octet-stream' });
  fs.createReadStream(file).pipe(res);
});
await new Promise((r) => server.listen(0, r));
const ORIGIN = `http://127.0.0.1:${server.address().port}`;
const APP = `${ORIGIN}${BASE}career-map.html`;

// ------------------------------------------------------------------ helpers
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? `  - ${detail}` : ''}`); };
const browser = await playwright.chromium.launch(process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {});

async function open(url, viewport = { width: 1920, height: 1080 }) {
  const page = await browser.newPage({ viewport });
  const errors = [];
  const bad = [];
  page.on('pageerror', (e) => errors.push(e.message));
  page.on('response', (r) => { if (r.status() >= 400) bad.push(`${r.status()} ${r.url()}`); });
  await page.goto(url);
  await page.waitForFunction(() => document.body.classList.contains('ready') || document.querySelector('#boot-error')?.hidden === false || !document.querySelector('#app'), null, { timeout: 20000 });
  await settle(page);
  return { page, errors, bad };
}
const settle = (page, ms = 900) => page.waitForTimeout(ms);
const hash = (page) => page.evaluate(() => location.hash);

/** A screen point inside a territory/region path (avoids holes and lakes). */
async function pointIn(page, selector) {
  return page.evaluate((sel) => {
    const p = document.querySelector(sel);
    if (!p) return null;
    const b = p.getBBox();
    const m = p.getScreenCTM();
    const pt = p.ownerSVGElement.createSVGPoint();
    let best = null;
    for (let i = 1; i < 12; i++) for (let j = 1; j < 12; j++) {
      pt.x = b.x + (b.width * i) / 12; pt.y = b.y + (b.height * j) / 12;
      if (!p.isPointInFill(pt)) continue;
      const s = pt.matrixTransform(m);
      if (s.x < 300 || s.y < 120 || s.x > innerWidth - 20 || s.y > innerHeight - 40) continue;
      const hit = document.elementFromPoint(s.x, s.y);
      if (hit === p) { const d = Math.hypot(i - 6, j - 6); if (!best || d < best.d) best = { x: s.x, y: s.y, d }; }
    }
    return best;
  }, selector);
}

// ------------------------------------------------------------------- tests
try {
  // 1. images
  {
    const { page } = await open(`${APP}#/world`);
    const maps = await page.evaluate(() => Object.entries(window.careerMap.db.maps).map(([id, m]) => ({ id, src: m.image, w: m.width, h: m.height })));
    for (const m of maps) {
      const dims = await page.evaluate((src) => new Promise((res) => { const i = new Image(); i.onload = () => res([i.naturalWidth, i.naturalHeight]); i.onerror = () => res(null); i.src = src; }), m.src);
      check(`1. map image loads: ${m.src}`, dims && dims[0] === m.w && dims[1] === m.h, dims ? `${dims[0]}x${dims[1]}` : 'failed');
    }
    await page.close();
  }

  // 2/3. navigation + back
  {
    const { page, errors } = await open(`${APP}`);
    check('2. default route is the world map', (await hash(page)) === '#/world');
    for (const [rid, title] of [['north-america', 'North America'], ['europe', 'Europe'], ['eurasia', 'Russia & Eurasia']]) {
      await page.goto(`${APP}#/world`); await settle(page);
      const p = await pointIn(page, `path.region[data-id="${rid}"]`);
      if (!p) { check(`2. world -> ${rid}`, false, 'no clickable point'); continue; }
      await page.mouse.click(p.x, p.y); await settle(page, 1300);
      const h = await hash(page);
      const t = await page.textContent('#view-title');
      const layer = await page.evaluate(() => document.querySelector('.map-layer:not(.leaving)')?.dataset.view);
      check(`2. world -> ${rid} by clicking the map`, h === `#/${rid}` && t === title && layer === rid, `${h} "${t}"`);
      await page.screenshot({ path: path.join(OUT, `region-${rid}.png`) });
      await page.click('#back'); await settle(page, 1300);
      check(`3. back button from ${rid} returns to world`, (await hash(page)) === '#/world');
    }
    await page.goto(`${APP}#/europe/t/swe/l/shl`); await settle(page, 1300);
    await page.click('#back'); await settle(page);
    const h1 = await hash(page);
    await page.keyboard.press('Escape'); await settle(page);
    const h2 = await hash(page);
    await page.keyboard.press('Escape'); await settle(page);
    const h3 = await hash(page);
    await page.keyboard.press('Escape'); await settle(page, 1300);
    const h4 = await hash(page);
    check('3. back/Escape walk up league -> info -> selected -> region -> world',
      h1 === '#/europe/t/swe/info' && h2 === '#/europe/t/swe' && h3 === '#/europe' && h4 === '#/world', [h1, h2, h3, h4].join(' '));
    await page.goBack(); await settle(page, 1300);
    check('3. browser history back works', (await hash(page)) === '#/europe', await hash(page));
    check('2/3. no script errors during navigation', !errors.length, errors.join('; '));
    await page.close();
  }

  // 4/5. territory selection, highlight alignment, info panel
  {
    const { page } = await open(`${APP}#/europe`);
    for (const [tid, name] of [['swe', 'Sweden'], ['che', 'Switzerland'], ['cze', 'Czechia'], ['fin', 'Finland']]) {
      await page.goto(`${APP}#/europe`); await settle(page, 1200);
      const p = await pointIn(page, `path.territory[data-id="${tid}"]`);
      if (!p) { check(`5. select ${tid}`, false, 'no clickable point'); continue; }
      await page.mouse.move(p.x, p.y); await settle(page, 300);
      const hovered = await page.evaluate((id) => document.querySelector(`path.territory[data-id="${id}"]`).classList.contains('hover'), tid);
      const tip = await page.textContent('.map-tooltip strong');
      check(`4. hover highlights ${name} and shows its name`, hovered && tip === name, `tooltip "${tip}"`);
      await page.mouse.click(p.x, p.y); await settle(page, 1200);
      const sel = await page.evaluate((id) => document.querySelector(`path.territory[data-id="${id}"]`).classList.contains('selected'), tid);
      const pin = await page.textContent('.territory-pin strong').catch(() => null);
      check(`5. click selects ${name}`, sel && (await hash(page)) === `#/europe/t/${tid}` && pin === name, `pin "${pin}"`);
      const p2 = await pointIn(page, `path.territory[data-id="${tid}"]`);
      await page.mouse.click(p2.x, p2.y); await settle(page, 1200);
      const h2 = await page.textContent('#panel-content h2');
      const open = await page.evaluate(() => document.querySelector('#app').classList.contains('panel-open'));
      check(`5. clicking selected ${name} opens its information panel`, open && h2 === name && (await hash(page)) === `#/europe/t/${tid}/info`, `panel "${h2}"`);
      await page.screenshot({ path: path.join(OUT, `territory-${tid}.png`) });
    }
    // click outside the panel (on the map) closes it
    await page.mouse.click(60, 600); await settle(page);
    check('5. clicking outside the panel closes it', !(await page.evaluate(() => document.querySelector('#app').classList.contains('panel-open'))), await hash(page));
    await page.close();
  }

  // 4. alignment numbers come from the tracer; report them here
  {
    const maps = JSON.parse(fs.readFileSync(path.join(ROOT, 'data', 'maps.json')));
    for (const [id, v] of Object.entries(maps.views)) {
      const f = v.calibration?.fit ?? {};
      check(`4. calibration for ${id} present`, !!v.calibration, `coast median error ${f.coastMedianErrorPx}px, land overlap (Dice) ${f.landDice}`);
    }
  }

  // 6/7. badges: positions and league panel
  {
    const { page } = await open(`${APP}#/europe`);
    const report = await page.evaluate(() => {
      const { stage, db } = window.careerMap;
      const L = stage.layer;
      return L.badges.filter((b) => b.visible).map((b) => {
        const lg = db.leagues.get(b.badge.league);
        const dot = b.dot.getBoundingClientRect();
        const [sx, sy] = stage.toScreen(L, b.pos);
        // anchor must fall inside one of the league's territories on this map
        const pt = L.svg.createSVGPoint();
        pt.x = b.pos[0]; pt.y = b.pos[1];
        const terr = [...L.paths.entries()].filter(([, p]) => p.isPointInFill(pt)).map(([id]) => id);
        const covers = new Set(lg?.territories ?? []);
        for (const t of lg?.territories ?? []) for (const m of db.territories.get(t)?.members ?? []) covers.add(m);
        return { id: b.badge.id, league: lg?.id, dx: dot.x + dot.width / 2 - sx, dy: dot.y + dot.height / 2 - sy, terr, covers: [...covers] };
      });
    });
    for (const r of report) {
      const inside = r.terr.some((t) => r.covers.includes(t));
      check(`6. badge ${r.id} sits on its anchor inside its territory`, Math.hypot(r.dx, r.dy) < 2 && inside, `anchor in [${r.terr.join(', ')}]`);
    }
    await page.click('.badge[data-badge="badge-nl"]'); await settle(page, 1300);
    check('7. clicking a badge opens the league panel', (await page.textContent('#panel-content h2')) === 'National League' && (await hash(page)) === '#/europe/l/nl', await hash(page));
    const clubs = await page.$$eval('.club-list li', (li) => li.length);
    check('7. league panel lists participating clubs', clubs === 14, `${clubs} clubs`);
    const hasCover = await page.$$eval('path.cover', (p) => p.length);
    check('7. league coverage is highlighted on the map', hasCover > 0, `${hasCover} coverage paths`);
    await page.screenshot({ path: path.join(OUT, 'league-nl.png') });

    // more badges appear when zooming in to a territory
    await page.goto(`${APP}#/north-america`); await settle(page, 1300);
    const before = await page.$$eval('.badge:not(.hidden)', (b) => b.map((x) => x.dataset.badge));
    await page.goto(`${APP}#/north-america/t/can`); await settle(page, 1300);
    const after = await page.$$eval('.badge:not(.hidden)', (b) => b.map((x) => x.dataset.badge));
    check('6. territory focus reveals more league badges', after.includes('badge-whl') && !before.includes('badge-whl'), `${before.length} -> ${after.length} badges`);
    await page.goto(`${APP}#/world`); await settle(page, 1300);
    const world = await page.$$eval('.badge:not(.hidden)', (b) => b.length);
    check('6. world map keeps badges to the main competitions', world <= 5, `${world} badges`);
    await page.close();
  }

  // 8. missing data
  {
    const { page, errors } = await open(`${ORIGIN}${BASE}career-map.html?game=test-missing-data#/world`);
    const warnings = await page.evaluate(() => window.careerMap.db.warnings);
    check('8. broken references load without script errors', !errors.length && warnings.length >= 4, `${warnings.length} warnings, ${errors.length} errors`);
    await page.goto(`${ORIGIN}${BASE}career-map.html?game=test-missing-data#/europe/l/test-league`); await settle(page, 1300);
    const h2 = await page.textContent('#panel-content h2');
    const clubsMsg = await page.textContent('.block .empty').catch(() => null);
    check('8. league with missing clubs/logo still renders', h2 === 'League with gaps' && !errors.length, clubsMsg);
    await page.goto(`${ORIGIN}${BASE}career-map.html?game=test-missing-data#/europe/t/no-boundary/info`); await settle(page, 1300);
    const warn = await page.textContent('#panel-content .warn').catch(() => null);
    check('8. territory without boundary shows a fallback', /No map boundary/.test(warn ?? ''), warn);
    await page.goto(`${ORIGIN}${BASE}career-map.html?game=test-missing-data#/nowhere`); await settle(page, 1300);
    check('8. view with a missing map image falls back to the world map', (await hash(page)) === '#/world' && !errors.length, await hash(page));
    await page.goto(`${APP}#/atlantis/t/xyz/l/nope`); await settle(page, 1300);
    check('8. unknown route falls back gracefully', (await hash(page)) === '#/world' && !errors.length, await hash(page));
    await page.goto(`${ORIGIN}${BASE}career-map.html?game=no-such-game`); await settle(page);
    check('8. unknown game shows an error message', await page.isVisible('#boot-error'));
    await page.close();
  }

  // 9/10. layouts
  for (const vp of [{ width: 1920, height: 1080 }, { width: 1366, height: 768 }, { width: 1024, height: 768 }, { width: 390, height: 844 }]) {
    const { page, errors } = await open(`${APP}#/europe/t/swe/l/shl`, vp);
    await settle(page, 800);
    const m = await page.evaluate(() => {
      const r = (s) => document.querySelector(s).getBoundingClientRect();
      const panel = r('#panel'), top = r('#topbar .heading');
      const overlap = !(top.right <= panel.left || top.bottom <= panel.top);
      return { scrollW: document.documentElement.scrollWidth, innerW: innerWidth, panelIn: panel.left >= 0 && panel.right <= innerWidth + 1 && panel.bottom <= innerHeight + 1, overlap };
    });
    const name = `${vp.width}x${vp.height}`;
    check(`${vp.width >= 1920 ? 9 : 10}. layout ${name}: no horizontal overflow, panel on screen, header clear of panel`,
      m.scrollW <= m.innerW && m.panelIn && !m.overlap && !errors.length, JSON.stringify(m));
    await page.screenshot({ path: path.join(OUT, `layout-${name}.png`) });
    await page.close();
  }

  // 11. sub-path hosting
  {
    const outside = requests.filter((u) => !u.startsWith(BASE) && u !== '/favicon.ico');
    check('11. every request stays under the project sub-path', !outside.length, outside.slice(0, 5).join(', '));
    const { page, bad } = await open(`${ORIGIN}${BASE}`);
    const link = await page.getAttribute('a.game', 'href');
    await page.click('a.game'); await page.waitForFunction(() => document.body.classList.contains('ready'), null, { timeout: 15000 });
    check('11/12. landing page links to the map with a relative URL', link.startsWith('career-map.html') && page.url().includes(`${BASE}career-map.html`), link);
    check('11. no failed requests on the landing page', !bad.filter((b) => !b.includes('favicon')).length, bad.join(', '));
    await page.close();
  }
} finally {
  await browser.close();
  server.close();
}

const failed = results.filter((r) => !r.ok);
console.log(`\n${results.length - failed.length}/${results.length} checks passed`);
fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify(results, null, 2));
process.exit(failed.length ? 1 : 0);
