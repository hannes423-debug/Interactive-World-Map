#!/usr/bin/env python3
"""Contact sheets for reviewing the branding library.

  assets/branding/contact-sheet.html   every entity grouped by league/type, with its
                                       128 px output, rights/identity status and flags
  tools/branding/out/contact-sheet-<group>.png   the same as images (not committed)

Run after process.py.
"""
import html
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
BRAND = os.path.join(ROOT, "assets", "branding")
MEM = os.path.join(ROOT, "data", "hockey", "memberships-2026-27.json")


def groups(man):
    mem = json.load(open(MEM)) if os.path.exists(MEM) else {"leagues": {}}
    out = [("Leagues", [k for k in man["entities"] if k.startswith("league:")])]
    for lid, lg in mem["leagues"].items():
        out.append((f"{lid.upper()} clubs ({len(lg['clubs'])})", [f"club:{c['id']}" for c in lg["clubs"]]))
    for t, label in (("flag", "Flags"), ("federation", "Federations"), ("national-team", "National teams"), ("tournament", "Tournaments")):
        out.append((label, sorted(k for k in man["entities"] if k.startswith(t + ":"))))
    return out


def cell_state(man, key):
    ent = man["entities"].get(key)
    a = man["assets"].get(ent["active"]) if ent and ent.get("active") else None
    if a and a.get("outputs"):
        return a, "ok" if a.get("technical", {}).get("status") == "verified" else "flagged"
    if ent and ent.get("status") == "restricted":
        return a, "restricted"
    return a, "missing"


def main():
    man = json.load(open(os.path.join(BRAND, "manifest.json")))
    parts = ["""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Branding contact sheet</title><style>
:root{color-scheme:dark}body{margin:0;background:#0b111c;color:#e6ecf5;font:13px/1.4 system-ui,sans-serif}
main{max-width:1400px;margin:0 auto;padding:24px 16px}h1{font-weight:600}h2{margin:28px 0 8px;font-size:15px;color:#9fb3cc;text-transform:uppercase;letter-spacing:.1em}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:8px}
.c{background:#121a28;border:1px solid #223047;border-radius:8px;padding:8px;display:grid;gap:4px;justify-items:center;text-align:center}
.c img{width:96px;height:96px;object-fit:contain;background:repeating-conic-gradient(#1a2333 0 25%,#141c2a 0 50%) 0 0/12px 12px;border-radius:4px}
.c.flagged{border-color:#a5814b}.c.restricted,.c.missing{opacity:.75}.ph{width:96px;height:96px;display:grid;place-items:center;border:1px dashed #4b5b75;border-radius:4px;color:#7f8ea6;font-size:11px}
.n{font-weight:600;font-size:12px}.s{font-size:10.5px;color:#93a3ba}.f{font-size:10px;color:#e0b56b}
.legend span{margin-right:14px}</style></head><body><main><h1>Branding contact sheet</h1>
<p class="legend"><span>Checkerboard = transparency</span><span style="color:#e0b56b">amber = flagged by validation</span><span>dashed = no publishable file</span></p>
<p>Generated from <code>assets/branding/manifest.json</code>. Back to the <a href="../../career-map.html" style="color:#8fd0ff">career map</a>.</p>"""]
    for title, keys in groups(man):
        parts.append(f"<h2>{html.escape(title)}</h2><div class='grid'>")
        for k in keys:
            a, st = cell_state(man, k)
            ent = man["entities"].get(k, {})
            name = html.escape(ent.get("name") or k)
            if st in ("ok", "flagged"):
                out = a["outputs"].get("128") or next(iter(a["outputs"].values()))
                pic = f"<img src='../../{out}' alt='' loading='lazy'>"
            else:
                pic = f"<div class='ph'>{'restricted' if st == 'restricted' else 'missing'}</div>"
            info = ""
            if a:
                info = f"{html.escape(a['rights']['status'])} · {html.escape(a['identity']['status'])}"
                fl = [f['code'] for f in a.get('technical', {}).get('flags', [])]
                if fl:
                    info += f"<div class='f'>{html.escape(', '.join(fl))}</div>"
            parts.append(f"<div class='c {st}'>{pic}<div class='n'>{name}</div><div class='s'>{info}</div></div>")
        parts.append("</div>")
    parts.append("</main></body></html>")
    open(os.path.join(BRAND, "contact-sheet.html"), "w").write("\n".join(parts))

    # PNG sheets for quick review
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    font = ImageFont.load_default()
    for title, keys in groups(man):
        if not keys:
            continue
        cols = 10
        rows = (len(keys) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * 140, rows * 150 + 30), (18, 24, 36))
        d = ImageDraw.Draw(sheet)
        d.text((8, 8), title, fill=(220, 230, 240), font=font)
        for i, k in enumerate(keys):
            x, y = (i % cols) * 140, (i // cols) * 150 + 30
            a, st = cell_state(man, k)
            if st in ("ok", "flagged"):
                p = os.path.join(ROOT, a["outputs"].get("128") or next(iter(a["outputs"].values())))
                im = Image.open(p).convert("RGBA")
                im.thumbnail((112, 112))
                bg = Image.new("RGBA", (120, 120), (40, 48, 64, 255))
                bg.alpha_composite(im, ((120 - im.width) // 2, (120 - im.height) // 2))
                sheet.paste(bg.convert("RGB"), (x + 10, y))
            else:
                d.rectangle((x + 10, y, x + 130, y + 120), outline=(90, 100, 120))
                d.text((x + 30, y + 55), st, fill=(140, 150, 170), font=font)
            if st == "flagged":
                d.rectangle((x + 10, y, x + 130, y + 120), outline=(224, 181, 107), width=2)
            d.text((x + 10, y + 124), (man["entities"].get(k, {}).get("name") or k)[:22], fill=(200, 210, 225), font=font)
        safe = "".join(ch if ch.isalnum() else "-" for ch in title.lower())[:40]
        sheet.save(os.path.join(HERE, "out", f"contact-sheet-{safe}.png"))
    print("contact sheets written")


if __name__ == "__main__":
    main()
