// Loaded by launch.sh for ~40 s: editor window on one screen, game view on the other.
// With a single screen the two windows share it (editor 58 %, game view 42 %).
var GAME_SCREEN = "DVI-D-1";   // preferred screen for the game view when two are connected
var done = {};

function screens() {
    var s = workspace.screens, game = s[s.length - 1], editor = s[0];
    for (var i = 0; i < s.length; i++) if (s[i].name === GAME_SCREEN) game = s[i];
    for (var j = 0; j < s.length; j++) if (s[j] !== game) { editor = s[j]; break; }
    return { editor: editor, game: game, single: s.length < 2 };
}

function place(w) {
    if (!w || String(w.resourceClass).toLowerCase().indexOf("firefox") < 0) return;
    var cap = String(w.caption);
    var role = cap.indexOf("League Editor") >= 0 ? "editor" : cap.indexOf("Game view") >= 0 ? "game" : null;
    if (!role || done[role] === w) return;
    done[role] = w;
    var s = screens();
    var out = role === "editor" ? s.editor : s.game;
    workspace.sendClientToScreen(w, out);
    var g = out.geometry;
    if (s.single) {
        w.setMaximize(false, false);
        var split = Math.round(g.width * 0.58);
        w.frameGeometry = role === "editor"
            ? { x: g.x, y: g.y, width: split, height: g.height }
            : { x: g.x + split, y: g.y, width: g.width - split, height: g.height };
    } else {
        w.setMaximize(true, true);
    }
}

function watch(w) {
    if (!w) return;
    place(w);
    w.captionChanged.connect(function () { place(w); });
}
workspace.windowAdded.connect(watch);
var ws = workspace.windowList();
for (var i = 0; i < ws.length; i++) watch(ws[i]);
