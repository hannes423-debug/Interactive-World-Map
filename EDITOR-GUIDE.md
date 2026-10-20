# League Editor – guide

The editor changes leagues, teams, logos and map positions. The **game view** is the real in-game career map, and it updates by itself while you edit. Your edits are stored in the **league database** on the 1 TB HDD, not in the git repository.

## Starting it

Use the desktop icons:

| Icon | Opens |
|---|---|
| **World Map - Editor + Game** | The editor on one screen and the game view on the other. With one screen they share it side by side. |
| **World Map - Editor** | The editor only. |
| **World Map - Game** | The game view only. |
| **World Map Leagues** (folder) | The league database on the HDD. |

Each icon mounts the HDD if needed and starts a small local server at `http://127.0.0.1:8765`. You can also open these addresses in any browser yourself:

- Editor: `http://127.0.0.1:8765/editor.html`
- Game view: `http://127.0.0.1:8765/career-map.html?game=nhl13&live=1`

When the two-screen icon runs, a KWin script sends the game view to the screen named `DVI-D-1`. To use a different screen, change `GAME_SCREEN` in `tools/editor/kwin-place.js`; `kscreen-doctor -o` lists the screen names. If the windows land in the wrong place, drag them yourself. Each window keeps working wherever it is.

## How the two windows work together

- **Auto-save** (on by default) saves about a second after each change. Without it, press **Save** or **Ctrl+S**.
- After every save, the game view reloads and shows the change.
- With **Follow selection** ticked, the game view opens whatever league you select in the editor, so you see its teams on the map straight away.
- **Undo** (Ctrl+Z) steps back through your changes in this session.
- Each save also keeps the previous files in `backups/<game>/<date_time>/` (the newest 60 are kept). To roll back further, copy files from a backup into `games/<game>/`.

## The editor screen

- **Left:** the leagues, with a team count. ⚠ means a team has no location yet.
- **Middle:** the map, with one tab per map (World, North America, Europe, Russia & Eurasia).
  - With a league selected you see its teams' logos, plus the league logo (the dashed square).
  - Drag any logo to move it. Use the mouse wheel to zoom and drag empty map to pan. Double-click empty map to reset the view.
  - Tick **Show teams of all leagues** to see every other team faded, which helps when placing a new one.
- **Right:** the details of the selected league or team.

### Moving things: real location vs. "this map only"

Usually you drag a team to its real city. The editor stores the new point as longitude/latitude, so the team moves on **every** map.

The maps are painted artwork, so a city can sit slightly off on one of them. Tick **Moving only changes this map** and the drag becomes a nudge on the current map only. The other maps are not affected. Logos with a nudge have a small gold dot, and the team's panel shows **Reset nudge on …** to remove it.

## Common tasks

**Add a league.** Click **+ League** and enter a name and a short name (the short name appears under the logo on the map). Then, on the right:
1. Under **Plays in**, add the countries or regions. These are highlighted when the league is opened in the game.
2. Set **Home map**, the map the game opens for this league.
3. Upload a logo.
4. Under *League logo on the map*, choose the maps the logo appears on and how far out it is visible (**Visible from**). Drag the logo where you want it, or press **Centre on its teams**. **Priority** decides which logo keeps its spot when two would overlap.
5. Add teams.

**Add a team.** Select the league and press **+ New team**, then give it a name. Type its city and press **Find** (this needs internet), then pick the right match. If the city isn't found, press **Click map to place** and click the spot. Upload its logo.

**A team in several leagues** (e.g. the Champions Hockey League). In that league, use **+ add an existing team…** and type the team's name. The team's *Main league* stays the same.

**Change a logo.** Select the league or team. Press **Upload logo…**, or drag an image file onto the logo box. **Remove custom logo** goes back to the library logo or the placeholder.

**Remove things.** The **×** next to a team in a league's list takes it out of that league. If that was its only league, the editor offers to delete the team. **Delete team** and **Delete league** are at the bottom of each panel. When you delete a league, the editor asks whether to delete its teams as well.

**A whole new database** (another game or a fantasy setup). **New game…** copies the current database under a new name. Pick it in the **Game** menu. The game view for it is `career-map.html?game=<id>&live=1`.

## What images to use

| | Best | OK |
|---|---|---|
| Format | **SVG** (sharp at any size), or **PNG with a transparent background** | WebP, GIF, JPG (see below) |
| Size | **512 × 512 px** or larger | 256 px or more. Below 128 px the logo looks blurry when zoomed. |
| Shape | Square canvas, logo centred | Any shape. It is fitted into a square automatically. |
| Background | Transparent | Plain white. It is removed automatically. |
| File size | Under 1 MB | Up to 8 MB |

When you upload a PNG, JPG, WebP or GIF, the editor:
- trims empty borders,
- centres the logo on a transparent square with a little padding,
- makes a plain white background transparent (only when all four corners are white),
- saves it as PNG, at most 512 px.

SVG files are stored unchanged.

**Logo background:** by default every logo gets a glow around its outline so it stands out on the dark map. Dark and colourful logos get a white glow, and mostly white logos get an icy blue one. To change it for one logo, use the menu under that logo: *Light plate*, *Dark plate* or *Custom colour…* put a round plate behind it, and *No plate* shows the logo bare.

Tips:
- Thumbnails on the map are about 26 px, so pick the plain emblem without small text or a wordmark if you can.
- Avoid logos with a white outline on a white background, because the background removal can eat into them. Use a transparent PNG instead.
- Logos you upload are for your own use. Only publish ones you have the right to share (see the *Branding library* part of README.md).

## The league database (HDD)

```
/run/media/hasa/HDD/LeagueDatabase/      (= "World Map Leagues" on the desktop)
  games/<game>/      game.json territories.json leagues.json teams.json badges.json tournaments.json
  logos/<game>/leagues/<league-id>.png|svg
  logos/<game>/teams/<team-id>.png|svg
  backups/<game>/<date_time>/    previous versions of changed files
  server.log                     log of the local server
  GUIDE.md                       this guide
```

The JSON files can also be edited by hand while the editor is closed. The format is described in README.md (*Data model*). Fields added for the editor:

- team `lonlat`: `[longitude, latitude]` of the home city. It places the team on every map.
- team `position`: `{ "<map>": [x, y] }`, a per-map nudge in image pixels.
- team `logo` / league `logo`: an uploaded logo (`db/logos/...`). It overrides the branding library.

The first time the server starts, it copies `games/` from the repository into the database. After that, the database is the master copy.

## Publishing to GitHub Pages

The public site reads the repository, not the HDD. To publish your edits:
1. Press **Copy to repo**. This copies `games/<game>/` and the uploaded logos (`db/logos/<game>/`) into `~/Projects/Interactive-World-Map/`.
2. Commit and push from there.

## Troubleshooting

- **"The editor needs its local server"**: open it from the desktop icon, not as a file.
- **"League database not found"**: the HDD isn't mounted. Open it once in the file manager (Dolphin), or run `udisksctl mount -b /dev/disk/by-uuid/8c4db688-dc74-4efe-b68d-b9d02cdae3ec`. The autostart entry `~/.config/autostart/mount-league-hdd.desktop` mounts it at every login.
- **The game view doesn't update**: its address must contain `&live=1`. Reload it once.
- **Stop the server**: `tools/editor/launch.sh stop`.
- **Settings** (database folder, port, default game): edit the top of `tools/editor/launch.sh`.
- **Re-locating all teams from Wikidata**: `python3 tools/data/geocode_teams.py <path>/teams.json`. It only fills teams that have no location. Add `--force` to redo all of them.
