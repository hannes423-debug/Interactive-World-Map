"""Visual comparison of two logo files (dev-time helper).

Used to decide whether a freely licensed Commons file shows the same identity
as the logo currently displayed on Wikipedia. Both images are trimmed to their
visible content, flattened on white, padded to a square and reduced to 48 px.
The score combines grayscale correlation (shape) and mean colour agreement.
"""
import io

import numpy as np
import resvg_py
from PIL import Image

N = 48


def load(data, name):
    if name.lower().endswith(".svg"):
        try:
            png = bytes(resvg_py.svg_to_bytes(svg_string=data.decode("utf-8", "replace"), width=512))
        except Exception:
            return None
        img = Image.open(io.BytesIO(png))
    else:
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception:
            return None
    return img.convert("RGBA")


def signature(img):
    a = img.getchannel("A").point(lambda v: 255 if v > 16 else 0)
    box = a.getbbox()
    if not box:
        return None
    img = img.crop(box)
    w, h = img.size
    side = max(w, h)
    sq = Image.new("RGBA", (side, side), (255, 255, 255, 255))
    flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
    flat.alpha_composite(img)
    sq.paste(flat, ((side - w) // 2, (side - h) // 2))
    arr = np.asarray(sq.convert("RGB").resize((N, N), Image.LANCZOS), dtype=np.float32) / 255.0
    return arr, w / h


def score(sig_a, sig_b):
    if not sig_a or not sig_b:
        return 0.0
    (a, ra), (b, rb) = sig_a, sig_b
    ga, gb = a.mean(2), b.mean(2)
    ga, gb = ga - ga.mean(), gb - gb.mean()
    den = np.sqrt((ga ** 2).sum() * (gb ** 2).sum()) or 1.0
    ncc = float((ga * gb).sum() / den)
    colour = 1.0 - float(np.abs(a - b).mean())
    aspect = min(ra, rb) / max(ra, rb)
    return round(0.55 * ncc + 0.3 * colour + 0.15 * aspect, 3)
