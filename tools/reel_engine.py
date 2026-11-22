#!/usr/bin/env python3
"""Reel engine: spec.json -> vertical MP4 (1080x1920) with Kokoro voice-over, animations and synced subtitles.
Usage: python3 reel_engine.py spec.json out.mp4 [--preview]"""
import json, os, re, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont

W, H, FPS, SR = 1080, 1920, 30, 24000
MODEL_DIR = os.path.expanduser("~/.cache/kokoro")
SPEC = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
PREVIEW = "--preview" in sys.argv

TH = {"bg": "#0E0E14", "white": "#F5F5FA", "grey": "#9696A5", "yellow": "#FFD23F",
      "a": "#4FD1C5", "b": "#FF7A59", "c": "#A78BFA", "d": "#60A5FA"}
TH.update(SPEC.get("theme", {}))
def rgb(c):
    c = TH.get(c, c); return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))
BG = rgb("bg")
CHIP_COLORS = ["a", "b", "c", "yellow", "d"]

def find_font(names):
    for n in names:
        for root in ("/usr/share/fonts", os.path.expanduser("~/.fonts")):
            for dp, _, fs in os.walk(root):
                if n in fs: return os.path.join(dp, n)
    return None
FB = find_font(["InterDisplay-Bold.otf", "Inter-Bold.otf", "Poppins-Bold.ttf", "DejaVuSans-Bold.ttf"])
FM = find_font(["InterDisplay-Medium.otf", "Inter-Medium.otf", "Poppins-Medium.ttf", "DejaVuSans.ttf"])
FMONO = find_font(["DejaVuSansMono-Bold.ttf", "DejaVuSansMono.ttf"]) or FB
_fc = {}
def font(kind, size):
    k = (kind, size)
    if k not in _fc: _fc[k] = ImageFont.truetype({"bold": FB, "med": FM, "mono": FMONO}[kind], size)
    return _fc[k]

def ease(x): x = max(0.0, min(1.0, x)); return 1 - (1 - x) ** 3
def mix(c, a): c = rgb(c) if isinstance(c, str) else c; return tuple(int(BG[i] + (c[i] - BG[i]) * a) for i in range(3))
_d = ImageDraw.Draw(Image.new("RGB", (10, 10)))
def wrap(text, f, maxw=920):
    lines, cur = [], ""
    for w in text.split(" "):
        t = (cur + " " + w).strip()
        if _d.textlength(t, font=f) <= maxw or not cur: cur = t
        else: lines.append(cur); cur = w
    return lines + [cur]

# ---------- 1. voice ----------
def ensure_model():
    os.makedirs(MODEL_DIR, exist_ok=True)
    base = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
    for f, remote in (("kokoro.onnx", "kokoro-v1.0.onnx"), ("voices.bin", "voices-v1.0.bin")):
        p = os.path.join(MODEL_DIR, f)
        if not os.path.exists(p) or os.path.getsize(p) < 1e6:
            subprocess.run(["curl", "-sSL", "-o", p, base + remote], check=True)

def synth():
    import soundfile as sf
    from kokoro_onnx import Kokoro
    ensure_model()
    k = Kokoro(os.path.join(MODEL_DIR, "kokoro.onnx"), os.path.join(MODEL_DIR, "voices.bin"))
    voice, speed, gap = SPEC.get("voice", "em_alex"), SPEC.get("speed", 1.12), 0.18
    res = []
    for sc in SPEC["scenes"]:
        pieces, subs, t = [], [], 0.0
        for line in sc["say"]:
            shown, spoken = (line, line) if isinstance(line, str) else line
            s, sr = k.create(spoken, voice=voice, speed=speed, lang=SPEC.get("lang", "es"))
            idx = np.where(np.abs(s) > 0.01)[0]
            s = s[max(0, idx[0] - 600): idx[-1] + 1200].astype(np.float32)
            d = len(s) / SR
            subs.append((t, t + d, shown)); t += d + gap
            pieces += [s, np.zeros(int(gap * SR), np.float32)]
        res.append((np.concatenate(pieces), t, subs))
    return res

# ---------- 1b. animated icons, background ----------
import math
def _ic_canvas(sz): return Image.new("RGBA", (sz * 2, sz * 2), (0, 0, 0, 0))
def C(c, al=255): return rgb(c) + (al,) if isinstance(c, str) else tuple(c[:3]) + (al,)

def icon_img(name, sz, u, col):
    """u = seconds since the icon appeared. Drawn at 2x then downsampled (antialias)."""
    im = _ic_canvas(sz); d = ImageDraw.Draw(im); S = sz * 2; k = S / 400.0
    P = lambda *v: [x * k for x in v]
    a = ease(u / 0.5)
    if name == "chip":
        g = 0.5 + 0.5 * math.sin(u * 4)
        for r in range(6, 0, -1):
            d.rounded_rectangle(P(100 - r * 9, 100 - r * 9, 300 + r * 9, 300 + r * 9), radius=40 * k,
                                fill=C(col, int(14 * g * a)))
        for i in range(5):
            on = (u * 6 + i) % 5 < 1.2
            cc = C("yellow") if on else C(col, 200)
            o = 125 + i * 37.5
            for x0, y0, x1, y1 in ((o - 7, 55, o + 7, 100), (o - 7, 300, o + 7, 345),
                                   (55, o - 7, 100, o + 7), (300, o - 7, 345, o + 7)):
                d.rounded_rectangle(P(x0, y0, x1, y1), radius=5 * k, fill=cc)
        d.rounded_rectangle(P(100, 100, 300, 300), radius=30 * k, fill=C("#1B1B28"), outline=C(col), width=int(8 * k))
        f = font("bold", int(90 * k)); w = d.textlength("IA", font=f)
        d.text((200 * k - w / 2, 200 * k - f.size * 0.62), "IA", font=f, fill=C(col))
    elif name == "gavel":
        d.rounded_rectangle(P(215, 318, 365, 356), radius=10 * k, fill=C("#8B5E3C"))
        d.rounded_rectangle(P(232, 302, 348, 322), radius=8 * k, fill=C("#A0704A"))
        cyc = (u % 1.6) / 1.6
        lift = (1 - ease(cyc / 0.3)) if cyc < 0.3 else (0 if cyc < 0.5 else ease((cyc - 0.5) / 0.5))
        ang = math.radians(-50 * lift); px, py = 70, 250
        def rot(x, y):
            c, s_ = math.cos(ang), math.sin(ang)
            return ((px + x * c - y * s_) * k, (py + x * s_ + y * c) * k)
        d.polygon([rot(*q) for q in ((0, -9), (200, -9), (200, 9), (0, 9))], fill=C("#C68B59"))
        d.polygon([rot(*q) for q in ((180, -52), (240, -52), (240, 52), (180, 52))], fill=C(col))
        d.polygon([rot(*q) for q in ((172, -58), (248, -58), (248, -44), (172, -44))], fill=C("yellow"))
        d.polygon([rot(*q) for q in ((172, 44), (248, 44), (248, 58), (172, 58))], fill=C("yellow"))
        if 0.28 < cyc < 0.55:
            for x0, y0, x1, y1 in ((215, 290, 190, 262), (340, 285, 362, 252), (375, 312, 398, 296)):
                d.line(P(x0, y0, x1, y1), fill=C("yellow"), width=int(9 * k))
    elif name == "scales":
        tilt = math.sin(u * 2.2) * 12
        d.rectangle(P(192, 110, 208, 330), fill=C(col)); d.rounded_rectangle(P(130, 325, 270, 350), radius=10 * k, fill=C(col))
        d.ellipse(P(185, 92, 215, 122), fill=C("yellow"))
        r = math.radians(tilt); L = 140
        lx, ly = 200 - L * math.cos(r), 115 - L * math.sin(r); rx, ry = 200 + L * math.cos(r), 115 + L * math.sin(r)
        d.line([(lx * k, ly * k), (rx * k, ry * k)], fill=C(col), width=int(12 * k))
        for x, y, cc in ((lx, ly, "a"), (rx, ry, "b")):
            d.line([(x * k, y * k), ((x - 45) * k, (y + 110) * k)], fill=C("grey"), width=int(4 * k))
            d.line([(x * k, y * k), ((x + 45) * k, (y + 110) * k)], fill=C("grey"), width=int(4 * k))
            d.chord(P(x - 65, y + 70, x + 65, y + 150), 0, 180, fill=C(cc))
    elif name == "race":
        for j, (lab, cc, sp) in enumerate((("EE. UU.", "d", 1.0), ("China", "b", 0.93))):
            y = 110 + j * 150
            d.rounded_rectangle(P(20, y + 40, 380, y + 52), radius=6 * k, fill=C("#2A2A38"))
            for m in range(0, 360, 40):
                d.rectangle(P(20 + m + ((u * 160) % 40), y + 44, 36 + m + ((u * 160) % 40), y + 48), fill=C("#4A4A5A"))
            prog = 0.1 + 0.8 * ease(min(1, u / 3.0)) * sp + 0.04 * math.sin(u * 3 + j * 2)
            x = 20 + prog * 260
            d.rounded_rectangle(P(x, y, x + 70, y + 70), radius=12 * k, fill=C("#1B1B28"), outline=C(cc), width=int(6 * k))
            for q in range(3):
                d.rectangle(P(x + 14 + q * 18, y - 10, x + 22 + q * 18, y), fill=C(cc))
                d.rectangle(P(x + 14 + q * 18, y + 70, x + 22 + q * 18, y + 80), fill=C(cc))
            for q in range(3):  # speed lines
                d.line(P(x - 20 - q * 22, y + 20 + q * 15, x - 50 - q * 22, y + 20 + q * 15), fill=C(cc, 150), width=int(5 * k))
            f = font("bold", int(34 * k)); d.text((20 * k, (y - 58) * k), lab, font=f, fill=C(cc))
        d.rectangle(P(370, 90, 380, 380), fill=C("white"))
        for q in range(8):
            d.rectangle(P(380, 90 + q * 18, 392, 99 + q * 18), fill=C("white" if q % 2 else "grey"))
    elif name == "docs":
        for i in range(4):
            b = ease((u - i * 0.35) / 0.4)
            if b <= 0: continue
            x, y = 110 + i * 22, 90 + i * 34 - (1 - b) * 120
            d.rounded_rectangle(P(x, y, x + 170, y + 220), radius=14 * k, fill=C("#F5F5FA", int(255 * b)), outline=C(col, int(255 * b)), width=int(5 * k))
            for l in range(5):
                d.rounded_rectangle(P(x + 22, y + 40 + l * 30, x + 148 - (l % 2) * 40, y + 50 + l * 30), radius=4 * k, fill=C("#9696A5", int(255 * b)))
        sb = ease((u - 1.6) / 0.3)
        if sb > 0:  # stamp
            sc = 1 + (1 - sb) * 0.6
            d.rounded_rectangle(P(200 - 90 * sc, 250 - 38 * sc, 200 + 90 * sc, 250 + 38 * sc), radius=10 * k, outline=C("b"), width=int(8 * k))
            f = font("bold", int(46 * k * sc)); w = d.textlength("CASO", font=f)
            d.text((200 * k - w / 2, 250 * k - f.size * 0.6), "CASO", font=f, fill=C("b"))
    elif name == "trend_down":
        pts = [(40, 110), (110, 150), (170, 130), (240, 210), (300, 190), (360, 300)]
        d.line(P(40, 340, 370, 340), fill=C("grey"), width=int(5 * k)); d.line(P(40, 60, 40, 340), fill=C("grey"), width=int(5 * k))
        prog = ease(u / 1.6) * (len(pts) - 1); n = int(prog)
        seg = pts[:n + 1]
        if n < len(pts) - 1:
            f_ = prog - n; a0, b0 = pts[n], pts[n + 1]; seg = seg + [(a0[0] + (b0[0] - a0[0]) * f_, a0[1] + (b0[1] - a0[1]) * f_)]
        if len(seg) > 1: d.line([(x * k, y * k) for x, y in seg], fill=C(col), width=int(14 * k), joint="curve")
        x, y = seg[-1]; d.ellipse(P(x - 16, y - 16, x + 16, y + 16), fill=C(col))
        if prog >= len(pts) - 1.01:
            d.polygon(P(360, 330, 330, 290, 385, 285), fill=C(col))
    elif name == "ballot":
        cyc = (u % 1.8) / 1.8; y = 30 + 190 * ease(cyc / 0.7)
        d.rounded_rectangle(P(160, y, 240, y + 110), radius=8 * k, fill=C("white"))
        d.line(P(178, y + 55, 195, y + 75, 225, y + 30), fill=C(col), width=int(9 * k))
        d.rectangle(P(80, 200, 320, 400), fill=(0, 0, 0, 0))
        im2 = Image.new("RGBA", im.size, (0, 0, 0, 0)); d2 = ImageDraw.Draw(im2)
        d2.rounded_rectangle(P(90, 200, 310, 350), radius=16 * k, fill=C("#1B1B28"), outline=C(col), width=int(7 * k))
        d2.rounded_rectangle(P(150, 192, 250, 208), radius=6 * k, fill=C("#0E0E14"), outline=C("white"), width=int(4 * k))
        f = font("bold", int(46 * k)); w = d2.textlength("VOTO", font=f)
        d2.text((200 * k - w / 2, 250 * k), "VOTO", font=f, fill=C(col))
        im.alpha_composite(im2)
    elif name == "trophy":
        bob = math.sin(u * 2.5) * 8
        d.chord(P(120, 70 + bob, 280, 250 + bob), 0, 180, fill=C("yellow")); d.rectangle(P(120, 70 + bob, 280, 160 + bob), fill=C("yellow"))
        for x0 in (80, 270):
            d.arc(P(x0, 95 + bob, x0 + 50, 175 + bob), 90 if x0 > 100 else 270, 90 if x0 < 100 else 270, fill=C("yellow"), width=int(14 * k))
        d.rectangle(P(185, 245 + bob, 215, 295 + bob), fill=C("yellow")); d.rounded_rectangle(P(135, 290 + bob, 265, 325 + bob), radius=8 * k, fill=C("#C9A227"))
        f = font("bold", int(50 * k)); w = d.textlength("IA", font=f); d.text((200 * k - w / 2, 110 * k + bob * k), "IA", font=f, fill=C("#0E0E14"))
        for i in range(6):
            ph = u * 1.5 + i * 1.05; r_ = 150 + 30 * math.sin(ph * 1.3); al = int(255 * (0.5 + 0.5 * math.sin(ph * 3)))
            x, y = 200 + r_ * math.cos(ph), 190 + r_ * math.sin(ph) * 0.8; s_ = 12
            d.polygon(P(x, y - s_, x + s_ / 3, y - s_ / 3, x + s_, y, x + s_ / 3, y + s_ / 3, x, y + s_, x - s_ / 3, y + s_ / 3, x - s_, y, x - s_ / 3, y - s_ / 3), fill=C("white", al))
    elif name == "question":
        r_ = math.sin(u * 2) * 8
        f = font("bold", int(300 * k)); w = d.textlength("?", font=f)
        d.text((200 * k - w / 2, 20 * k + r_ * k), "?", font=f, fill=C(col))
    out = im.resize((sz, sz), Image.LANCZOS)
    if a < 1:
        al = out.getchannel("A").point(lambda v: int(v * a)); out.putalpha(al)
    return out

_bg_cache = {}
def background(T):
    kind = SPEC.get("background")
    if not kind: return Image.new("RGB", (W, H), BG)
    if "base" not in _bg_cache:
        b = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(b); gc = mix("d", 0.10)
        for x in range(0, W + 1, 90): d.line([(x, 0), (x, H)], fill=gc, width=2)
        for y in range(0, H + 1, 90): d.line([(0, y), (W, y)], fill=gc, width=2)
        for x in range(0, W + 1, 90):
            for y in range(0, H + 1, 90):
                if (x * 7 + y * 13) % 5 == 0: d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=mix("d", 0.22))
        _bg_cache["base"] = b
        rnd = np.random.default_rng(7)
        _bg_cache["pulses"] = [(int(rnd.integers(0, W // 90 + 1)), int(rnd.integers(0, H // 90 + 1)), int(rnd.integers(0, 2)),
                                float(rnd.uniform(0, 10)), float(rnd.uniform(60, 140)), CHIP_COLORS[int(rnd.integers(0, 5))]) for _ in range(26)]
    im = _bg_cache["base"].copy(); d = ImageDraw.Draw(im)
    for gx, gy, horiz, ph, sp, cc in _bg_cache["pulses"]:
        pos = (ph * 100 + T * sp) % (H if not horiz else W)
        x, y = (pos, gy * 90) if horiz else (gx * 90, pos)
        for tl in range(6):
            al = 0.35 * (1 - tl / 6); off = tl * 9
            xx, yy = (x - off, y) if horiz else (x, y - off)
            d.ellipse([xx - 5, yy - 5, xx + 5, yy + 5], fill=mix(cc, al))
    return im

# ---------- 2. layout ----------
def resolve_at(at, subs):
    """at: number, or 's<N>' / 's<N>+x' = when spoken line N of the scene starts."""
    if isinstance(at, (int, float)): return float(at)
    m = re.match(r"s(\d+)\s*([+-]\s*[\d.]+)?$", str(at).replace(" ", ""))
    base = subs[min(int(m.group(1)), len(subs) - 1)][0] + LEAD
    return base + (float(m.group(2)) if m.group(2) else 0.0)

def el_height(e):
    t = e["type"]
    if t == "text":
        f = font(e.get("weight", "bold"), e.get("size", 72))
        return int(len(wrap(e["text"], f, e.get("maxw", 920))) * f.size * 1.18)
    if t == "chips": return e.get("size", 60) + 70
    if t == "bar": return 200
    if t == "big": return int(e.get("size", 190) * 1.15)
    if t == "list":
        f = font("bold", e.get("size", 54))
        return sum(max(1, len(wrap(i, f, 800))) * int(f.size * 1.22) + 70 for i in e["items"])
    if t == "gap": return e.get("h", 40)
    if t == "icon": return e.get("size", 320)
    return 0

def draw_el(im, d, e, y, t, at):
    typ, col = e["type"], e.get("color", "white")
    a = ease((t - at) / 0.45)
    if typ == "icon":
        if t < at: return
        sz = e.get("size", 320); ic = icon_img(e["name"], sz, t - at, e.get("color", "a"))
        im.paste(ic, (int((W - sz) / 2), int(y + (1 - a) * 40)), ic); return
    if typ == "text":
        if a <= 0: return
        f = font(e.get("weight", "bold"), e.get("size", 72))
        for line in wrap(e["text"], f, e.get("maxw", 920)):
            w = d.textlength(line, font=f)
            d.text(((W - w) / 2, y + (1 - a) * 40), line, font=f, fill=mix(col, a)); y += int(f.size * 1.18)
    elif typ == "chips":
        f = font("mono", e.get("size", 60)); pad, gap, step = 22, 12, e.get("step", 0.25)
        ws = [d.textlength(p, font=f) + pad * 2 for p in e["pieces"]]
        x = (W - sum(ws) - gap * (len(ws) - 1)) / 2
        for i, (p, w) in enumerate(zip(e["pieces"], ws)):
            b = ease((t - at - i * step) / 0.35)
            if b > 0:
                c = rgb(CHIP_COLORS[i % 5]); yy = y + (1 - b) * 30
                d.rounded_rectangle([x, yy, x + w, yy + f.size + 46], radius=18,
                                    fill=mix(tuple(int(v * .28) for v in c), b), outline=mix(c, b), width=4)
                d.text((x + pad, yy + 18), p, font=f, fill=mix("white", b))
            x += w + gap
    elif typ == "bar":
        if t < at: return
        b = ease((t - at) / 1.0); full = 900 * e["value"] / e["max"]
        d.text((90, y), e["label"], font=font("bold", 54), fill=rgb(col))
        d.rounded_rectangle([90, y + 72, 990, y + 162], radius=24, fill=(32, 32, 42))
        d.rounded_rectangle([90, y + 72, 90 + max(48, full * b), y + 162], radius=24, fill=rgb(col))
        v = e["value"] * b; v = int(round(v)) if float(e["value"]).is_integer() else round(v, 1)
        d.text((120, y + 86), f"{v}{e.get('unit', '')}", font=font("bold", 56), fill=BG)
    elif typ == "big":
        if a <= 0: return
        f = font("bold", int(e.get("size", 190) * (1 + .15 * (1 - a))))
        w = d.textlength(e["text"], font=f); d.text(((W - w) / 2, y), e["text"], font=f, fill=mix(col, a))
    elif typ == "list":
        f = font("bold", e.get("size", 54)); cols = ["b", "yellow", "a", "c", "d"]
        for k, item in enumerate(e["items"]):
            b = ease((t - at - k * e.get("step", 0.9)) / 0.4); off = (1 - b) * 30
            lines = wrap(item, f, 800)
            if b > 0:
                d.ellipse([90, y + 4 + off, 150, y + 64 + off], fill=mix(cols[k % 5], b))
                n = str(k + 1); nw = d.textlength(n, font=font("bold", 42))
                d.text((120 - nw / 2, y + 8 + off), n, font=font("bold", 42), fill=BG)
                for j, line in enumerate(lines):
                    d.text((190, y + j * int(f.size * 1.22) + off), line, font=f, fill=mix("white", b))
            y += max(1, len(lines)) * int(f.size * 1.22) + 70

# ---------- 3. render ----------
LEAD, TOP, BOTTOM = 0.25, 230, 1560
def main():
    voice = synth()
    durs = [max(sc.get("min", 3.0), v[1] + LEAD + 0.45) for sc, v in zip(SPEC["scenes"], voice)]
    starts = [sum(durs[:i]) for i in range(len(durs))]; total = sum(durs)
    # layout per scene: vertical centering within safe area
    layouts = []
    for sc, (_, _, subs) in zip(SPEC["scenes"], voice):
        els, h = sc["elements"], 0
        hs = [el_height(e) for e in els]; gaps = [e.get("space", 36) for e in els]
        tot = sum(hs) + sum(gaps[:-1]); y = TOP + max(0, (BOTTOM - TOP - tot) / 2); ys = []
        for hh, g in zip(hs, gaps): ys.append(y); y += hh + g
        auto = [resolve_at(e["at"], subs) if "at" in e else i * 0.5 for i, e in enumerate(els)]
        layouts.append(list(zip(els, ys, auto)))
    # subtitle chunks
    chunks = []
    for st, (_, _, subs) in zip(starts, voice):
        for s0, s1, txt in subs:
            gs, cur = [], ""
            for w in txt.split():
                if cur and len(cur) + 1 + len(w) > 20: gs.append(cur); cur = w
                else: cur = (cur + " " + w).strip()
            gs.append(cur); n = sum(len(g) for g in gs); t0 = st + LEAD + s0
            for g in gs:
                dd = (s1 - s0) * len(g) / n; chunks.append((t0, t0 + dd, g)); t0 += dd
    subf = font("bold", 62)

    TR = 0.35 if SPEC.get("transition") else 0
    def scene_layer(i, t):
        L = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(L)
        for e, y, at in layouts[i]: draw_el(L, d, e, y, t, at)
        return L
    def frame(T):
        im = background(T); d = ImageDraw.Draw(im)
        i = max(k for k in range(len(starts)) if starts[k] <= T); t = T - starts[i]
        if TR and i > 0 and t < TR:
            p = ease(t / TR); kind = SPEC.get("transition")
            old = scene_layer(i - 1, durs[i - 1] - 0.01); new = scene_layer(i, t)
            if kind == "zoom":
                o = old.resize((int(W * (1 + .25 * p)), int(H * (1 + .25 * p)))); o.putalpha(o.getchannel("A").point(lambda v: int(v * (1 - p))))
                im.paste(o, (-(o.width - W) // 2, -(o.height - H) // 2), o)
                n = new.resize((int(W * (0.8 + .2 * p)), int(H * (0.8 + .2 * p)))); n.putalpha(n.getchannel("A").point(lambda v: int(v * p)))
                im.paste(n, ((W - n.width) // 2, (H - n.height) // 2), n)
            else:
                im.paste(old, (int(-W * p), 0), old); im.paste(new, (int(W * (1 - p)), 0), new)
        else:
            L = scene_layer(i, t); im.paste(L, (0, 0), L)
        d.rectangle([0, 0, W * T / total, 10], fill=rgb("yellow"))
        cur = [c for c in chunks if c[0] <= T < c[1] + 0.12]
        if cur and SPEC.get("subtitles", True):
            txt = cur[-1][2]; w = d.textlength(txt, font=subf); x, y = (W - w) / 2, 1640
            d.rounded_rectangle([x - 28, y - 14, x + w + 28, y + 86], radius=22, fill=(0, 0, 0))
            d.text((x, y), txt, font=subf, fill=rgb("yellow"))
        return im

    if PREVIEW:  # contact sheet with the last frame of each scene
        ims = [frame(s + d - 0.05).resize((360, 640)) for s, d in zip(starts, durs)]
        sheet = Image.new("RGB", (360 * len(ims), 640))
        for k, im in enumerate(ims): sheet.paste(im, (k * 360, 0))
        sheet.save(OUT.rsplit(".", 1)[0] + "_preview.png")
    import soundfile as sf
    track = np.zeros(int((total + .5) * SR), np.float32)
    for st, (a, _, _) in zip(starts, voice):
        o = int((st + LEAD) * SR); track[o:o + len(a)] += a
    wav = OUT.rsplit(".", 1)[0] + "_voz.wav"; sf.write(wav, track, SR)
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
                          "-r", str(FPS), "-i", "-", "-i", wav, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                          "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-af", "loudnorm=I=-14:TP=-1.5",
                          "-shortest", "-movflags", "+faststart", OUT], stdin=subprocess.PIPE)
    for n in range(int(total * FPS)): p.stdin.write(frame(n / FPS).tobytes())
    p.stdin.close(); p.wait(); os.remove(wav)
    print(f"OK {OUT} {total:.1f}s scenes={[round(x, 1) for x in durs]}")

main()
