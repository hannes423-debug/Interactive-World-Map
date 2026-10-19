#!/usr/bin/env python3
"""Validate branding masters and generate the PNG variants listed in the manifest.

Reads  assets/branding/manifest.json
Writes assets/branding/generated/<type>/<id>-<size>.png   (square canvases; flags keep their proportions)
       assets/branding/validation-report.json            (machine-readable)
       assets/branding/validation-report.md              (summary)
and updates each asset's "outputs" and "technical" fields in the manifest.

Checks (flags only - nothing is deleted or altered automatically):
  missing-master        master path does not exist
  svg-invalid           SVG does not parse
  svg-embeds-raster     SVG contains <image> elements (often a wrapped bitmap)
  low-resolution        raster master below 512 px on its longest side
  no-alpha-background   raster without transparency whose border is a solid colour
  excessive-margin      content covers < 60 % of the master on both axes
  probable-duplicate    identical file hash or near-identical rendering as another asset
  not-upscaled          output sizes skipped because they would enlarge a raster master

Usage
  python3 tools/branding/process.py              # all assets
  python3 tools/branding/process.py --check      # validate only, no image output
Requires Pillow and resvg-py (pip install resvg-py).
"""
import hashlib
import io
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date

import resvg_py
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
BRAND = os.path.join(ROOT, "assets", "branding")
MANIFEST = os.path.join(BRAND, "manifest.json")
SIZES = [128, 256, 512, 1024]
MARGIN = {"horizontal": 0.05, "crest": 0.06, "symbol": 0.08, "federation": 0.06,
          "national-team": 0.06, "tournament": 0.06}
LOW_RES = 512


def rel(p):
    return os.path.relpath(p, ROOT).replace(os.sep, "/")


def load_master(path):
    """Return (RGBA image at high resolution, info dict, flags)."""
    flags, info = [], {}
    if path.lower().endswith(".svg"):
        raw = open(path, "rb").read()
        try:
            root = ET.fromstring(raw)
        except ET.ParseError as e:
            return None, info, [("svg-invalid", str(e))]
        images = [el for el in root.iter() if el.tag.split("}")[-1] == "image"]
        paths = [el for el in root.iter() if el.tag.split("}")[-1] in ("path", "polygon", "rect", "circle", "ellipse", "text", "polyline", "line")]
        if images:
            flags.append(("svg-embeds-raster", f"{len(images)} <image> element(s), {len(paths)} vector shapes"))
        info.update(format="svg", vectorShapes=len(paths))
        # render large on the longest side
        probe = Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_path=path))))
        w, h = probe.size
        info["intrinsic"] = [w, h]
        scale = 2048 / max(w, h)
        kw = {"width": round(w * scale)} if w >= h else {"height": round(h * scale)}
        img = Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_path=path, **kw)))).convert("RGBA")
        info["native"] = None  # vector: any size
        return img, info, flags
    img = Image.open(path)
    info.update(format=img.format.lower() if img.format else "raster", intrinsic=list(img.size))
    has_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    img = img.convert("RGBA")
    info["native"] = max(img.size)
    if max(img.size) < LOW_RES:
        flags.append(("low-resolution", f"{img.size[0]}x{img.size[1]}"))
    if not has_alpha:
        px = img.load()
        w, h = img.size
        border = [px[x, 0] for x in range(w)] + [px[x, h - 1] for x in range(w)] + [px[0, y] for y in range(h)] + [px[w - 1, y] for y in range(h)]
        first = border[0]
        if all(sum(abs(a - b) for a, b in zip(p[:3], first[:3])) < 24 for p in border):
            flags.append(("no-alpha-background", f"opaque border colour {first[:3]}"))
    return img, info, flags


def content_box(img):
    alpha = img.getchannel("A").point(lambda a: 255 if a > 8 else 0)
    return alpha.getbbox()


def ahash(img):
    import numpy as np
    small = np.asarray(img.convert("LA").resize((16, 16), Image.LANCZOS)).reshape(-1, 2)
    vals = [int(l) if a > 8 else 255 for l, a in small]
    avg = sum(vals) / len(vals)
    return "".join("1" if v > avg else "0" for v in vals)


def render_outputs(asset, img, info, flags):
    out = {}
    typ = asset["type"]
    folder = os.path.join(BRAND, "generated", typ)
    os.makedirs(folder, exist_ok=True)
    native = info.get("native")
    if asset["renderClass"] == "flag":
        # flags: keep the real proportions, width = size
        w, h = img.size
        for s in SIZES:
            if native and s > native:
                continue
            o = img.resize((s, max(1, round(h * s / w))), Image.LANCZOS)
            p = os.path.join(folder, f"{asset['id'].split('.', 1)[1]}-{s}.png")
            o.save(p, optimize=True)
            out[str(s)] = rel(p)
    else:
        box = content_box(img)
        if not box:
            flags.append(("empty-render", "no visible pixels"))
            return out
        art = img.crop(box)
        aw, ah = art.size
        cw = (box[2] - box[0]) / img.size[0]
        ch = (box[3] - box[1]) / img.size[1]
        if cw < 0.6 and ch < 0.6:
            flags.append(("excessive-margin", f"content {cw:.0%} x {ch:.0%} of master"))
        m = MARGIN.get(asset["renderClass"], 0.06)
        for s in SIZES:
            inner = s * (1 - 2 * m)
            k = min(inner / aw, inner / ah)
            if native and k > 1.0 and s > SIZES[0]:
                # would enlarge a bitmap: skip rather than fake a high-res output
                continue
            tw, th = max(1, round(aw * k)), max(1, round(ah * k))
            canvas = Image.new("RGBA", (s, s), (0, 0, 0, 0))
            canvas.alpha_composite(art.resize((tw, th), Image.LANCZOS), ((s - tw) // 2, (s - th) // 2))
            p = os.path.join(folder, f"{asset['id'].split('.', 1)[1]}-{s}.png")
            canvas.save(p, optimize=True)
            out[str(s)] = rel(p)
        if native and len(out) < len(SIZES):
            flags.append(("not-upscaled", f"sizes above native {native}px skipped"))
    return out


def main():
    check_only = "--check" in sys.argv
    manifest = json.load(open(MANIFEST))
    assets = manifest["assets"]
    report = {"date": date.today().isoformat(), "assets": {}, "summary": {}}
    hashes, phashes = {}, {}
    entity_ids = set()
    for aid, a in sorted(assets.items()):
        flags = []
        if a.get("id") != aid:
            flags.append(("manifest-id-mismatch", f"key {aid} vs id {a.get('id')}"))
        master = a.get("master")
        if not master:
            report["assets"][aid] = {"status": "no-master", "flags": [], "rights": a.get("rights", {}).get("status")}
            a["outputs"] = {}
            continue
        path = os.path.join(ROOT, master)
        if not os.path.exists(path):
            flags.append(("missing-master", master))
            report["assets"][aid] = {"status": "flagged", "flags": [dict(code=c, detail=d) for c, d in flags]}
            a["outputs"] = {}
            continue
        data = open(path, "rb").read()
        sha = hashlib.sha256(data).hexdigest()
        if sha in hashes:
            flags.append(("probable-duplicate", f"same file as {hashes[sha]}"))
        hashes.setdefault(sha, aid)
        try:
            img, info, f2 = load_master(path)
        except Exception as e:  # unreadable file
            img, info, f2 = None, {}, [("unreadable", str(e)[:200])]
        flags += f2
        if img is not None:
            ph = ahash(img)
            for other, oph in phashes.items():
                if sum(x != y for x, y in zip(ph, oph)) <= 4 and assets[other].get("entity") != a.get("entity") and a["type"] != "flag":
                    flags.append(("probable-duplicate", f"looks like {other}"))
                    break
            phashes[aid] = ph
            if not check_only:
                a["outputs"] = render_outputs(a, img, info, flags)
        a["technical"] = {
            "status": "flagged" if any(c not in ("not-upscaled",) for c, _ in flags) else "verified",
            "checked": report["date"], "format": info.get("format"), "intrinsicSize": info.get("intrinsic"),
            "sha256": sha, "bytes": len(data), "flags": [dict(code=c, detail=d) for c, d in flags],
        }
        report["assets"][aid] = {"status": a["technical"]["status"], "flags": a["technical"]["flags"],
                                 "rights": a.get("rights", {}).get("status"), "outputs": sorted(a.get("outputs", {}), key=int)}
        # expected output sizes really are what they claim
        for s, p in a.get("outputs", {}).items():
            with Image.open(os.path.join(ROOT, p)) as o:
                if a["renderClass"] != "flag" and o.size != (int(s), int(s)):
                    flags.append(("bad-output-size", f"{p} is {o.size}"))
                if o.mode != "RGBA":
                    flags.append(("output-no-alpha", p))

    # entity references
    for key, ent in manifest.get("entities", {}).items():
        entity_ids.add(key)
        for ref in [ent.get("active")] + ent.get("alternates", []):
            if ref and ref not in assets:
                report.setdefault("brokenReferences", []).append(f"{key} -> {ref}")

    from collections import Counter
    st = Counter(r["status"] for r in report["assets"].values())
    fl = Counter(f["code"] for r in report["assets"].values() for f in r.get("flags", []))
    rights = Counter(a.get("rights", {}).get("status") for a in assets.values())
    report["summary"] = {"assets": len(assets), "status": dict(st), "flags": dict(fl), "rights": dict(rights),
                         "brokenReferences": len(report.get("brokenReferences", []))}
    json.dump(report, open(os.path.join(BRAND, "validation-report.json"), "w"), indent=1, ensure_ascii=False)
    if not check_only:
        # merge only our fields into the file on disk (fetch.py may have updated it meanwhile)
        disk = json.load(open(MANIFEST))
        for aid, a in assets.items():
            if aid in disk["assets"] and disk["assets"][aid].get("master") == a.get("master"):
                disk["assets"][aid]["outputs"] = a.get("outputs", {})
                if "technical" in a:
                    disk["assets"][aid]["technical"] = a["technical"]
        tmp = MANIFEST + ".tmp"
        json.dump(disk, open(tmp, "w"), indent=1, ensure_ascii=False)
        os.replace(tmp, MANIFEST)

    lines = [f"# Branding validation report ({report['date']})", "",
             f"Assets in manifest: **{len(assets)}**", "",
             "| Technical status | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(st.items())] + \
            ["", "| Rights status | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(rights.items(), key=lambda x: str(x[0]))] + \
            ["", "| Flag | Count |", "|---|---|"] + [f"| {k} | {v} |" for k, v in sorted(fl.items())] + \
            ["", "## Flagged assets", ""]
    for aid, r in sorted(report["assets"].items()):
        if r["status"] == "flagged":
            lines.append(f"- `{aid}`: " + "; ".join(f"{f['code']} ({f['detail']})" for f in r["flags"]))
    if report.get("brokenReferences"):
        lines += ["", "## Broken references", ""] + [f"- {b}" for b in report["brokenReferences"]]
    open(os.path.join(BRAND, "validation-report.md"), "w").write("\n".join(lines) + "\n")
    print(json.dumps(report["summary"], indent=1))


if __name__ == "__main__":
    main()
