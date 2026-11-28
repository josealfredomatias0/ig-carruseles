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
    elif name == "primes":
        # numeros primos que aparecen uno a uno en fichas redondas; el activo brilla
        nums = ["2", "3", "5", "7", "11", "13"]
        f = font("bold", int(72 * k))
        for i, t in enumerate(nums):
            b = ease((u - i * 0.25) / 0.35)
            if b <= 0: continue
            cx, cy = 72 + (i % 3) * 128, 130 + (i // 3) * 140
            on = int(u * 2.5) % 6 == i
            r = 58 + (6 if on else 0)
            d.ellipse(P(cx - r, cy - r, cx + r, cy + r), fill=C("#1B1B28", int(255 * b)),
                      outline=C("yellow" if on else col, int(255 * b)), width=int(7 * k))
            w = d.textlength(t, font=f)
            d.text((cx * k - w / 2, cy * k - f.size * 0.62), t, font=f, fill=C("yellow" if on else "white", int(255 * b)))
    elif name == "lock":
        # candado que se cierra y brilla (cifrado, seguridad, contrasenas)
        cl = ease(min(1, u / 0.8)); up = (1 - cl) * 45
        g = 0.5 + 0.5 * math.sin(u * 4)
        for r in range(5, 0, -1):
            d.rounded_rectangle(P(95 - r * 8, 175 - r * 8, 305 + r * 8, 345 + r * 8), radius=36 * k, fill=C(col, int(12 * g)))
        d.arc(P(130, 60 - up, 270, 230 - up), 180, 360, fill=C("grey"), width=int(26 * k))
        d.rectangle(P(130, 145 - up, 156, 190), fill=C("grey")); d.rectangle(P(244, 145 - up, 270, 190 - (up if up > 0 else 0)), fill=C("grey"))
        d.rounded_rectangle(P(95, 175, 305, 345), radius=36 * k, fill=C("#1B1B28"), outline=C(col), width=int(9 * k))
        d.ellipse(P(178, 225, 222, 269), fill=C("yellow" if cl >= 1 else col))
        d.rounded_rectangle(P(192, 255, 208, 305), radius=6 * k, fill=C("yellow" if cl >= 1 else col))
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
    elif name in ("trophy", "cup"):  # cup = trofeo sin "IA": récords, leyendas, deportes
        bob = math.sin(u * 2.5) * 8
        d.chord(P(120, 70 + bob, 280, 250 + bob), 0, 180, fill=C("yellow")); d.rectangle(P(120, 70 + bob, 280, 160 + bob), fill=C("yellow"))
        for x0 in (80, 270):
            d.arc(P(x0, 95 + bob, x0 + 50, 175 + bob), 90 if x0 > 100 else 270, 90 if x0 < 100 else 270, fill=C("yellow"), width=int(14 * k))
        d.rectangle(P(185, 245 + bob, 215, 295 + bob), fill=C("yellow")); d.rounded_rectangle(P(135, 290 + bob, 265, 325 + bob), radius=8 * k, fill=C("#C9A227"))
        if name == "trophy":
            f = font("bold", int(50 * k)); w = d.textlength("IA", font=f); d.text((200 * k - w / 2, 110 * k + bob * k), "IA", font=f, fill=C("#0E0E14"))
        for i in range(6):
            ph = u * 1.5 + i * 1.05; r_ = 150 + 30 * math.sin(ph * 1.3); al = int(255 * (0.5 + 0.5 * math.sin(ph * 3)))
            x, y = 200 + r_ * math.cos(ph), 190 + r_ * math.sin(ph) * 0.8; s_ = 12
            d.polygon(P(x, y - s_, x + s_ / 3, y - s_ / 3, x + s_, y, x + s_ / 3, y + s_ / 3, x, y + s_, x - s_ / 3, y + s_ / 3, x - s_, y, x - s_ / 3, y - s_ / 3), fill=C("white", al))
    elif name == "question":
        r_ = math.sin(u * 2) * 8
        f = font("bold", int(300 * k)); w = d.textlength("?", font=f)
        d.text((200 * k - w / 2, 20 * k + r_ * k), "?", font=f, fill=C(col))
    elif name == "magnifier":  # lupa que recorre: investigación, pistas, "lo que se sabe"
        ox, oy = 30 * math.sin(u * 1.6), 20 * math.sin(u * 2.3)
        cx, cy = 170 + ox, 165 + oy
        d.line(P(cx + 70, cy + 70, cx + 160, cy + 160), fill=C("#C68B59"), width=int(34 * k))
        d.ellipse(P(cx - 105, cy - 105, cx + 105, cy + 105), fill=C(col, 50), outline=C(col), width=int(16 * k))
        d.arc(P(cx - 75, cy - 75, cx + 75, cy + 75), 200, 250, fill=C("white", 200), width=int(10 * k))
    elif name == "hourglass":  # reloj de arena: tiempo, años, historia
        ang = 0
        fl = (u % 3.0) / 3.0
        d.rounded_rectangle(P(110, 50, 290, 72), radius=8 * k, fill=C("#C68B59")); d.rounded_rectangle(P(110, 328, 290, 350), radius=8 * k, fill=C("#C68B59"))
        d.polygon(P(130, 72, 270, 72, 208, 200, 192, 200), outline=C(col), width=int(7 * k))
        d.polygon(P(192, 200, 208, 200, 270, 328, 130, 328), outline=C(col), width=int(7 * k))
        top = 1 - fl; ty = 200 - 110 * top
        if top > 0.02:
            hw = (200 - ty) / 128 * 70
            d.polygon(P(200 - hw, ty, 200 + hw, ty, 204, 196, 196, 196), fill=C("yellow"))
        bh = 100 * fl
        d.polygon(P(200 - 10 - bh * 0.55, 326, 200 + 10 + bh * 0.55, 326, 200, 326 - bh), fill=C("yellow"))
        if top > 0.02:
            for q in range(4):
                yy = 200 + ((u * 260 + q * 30) % 120)
                d.ellipse(P(197, yy, 203, yy + 6), fill=C("yellow"))
    elif name == "scroll":  # pergamino que se desenrolla: leyenda, tradición, relato antiguo
        o = ease(u / 1.0); h_ = 40 + 220 * o
        d.rectangle(P(110, 80, 290, 80 + h_), fill=C("#E8D5A8"))
        for l in range(6):
            yy = 115 + l * 32
            if yy + 8 < 80 + h_ - 10: d.rounded_rectangle(P(135, yy, 265 - (l % 2) * 35, yy + 8), radius=4 * k, fill=C("#8B6F47"))
        for yy in (80, 80 + h_):
            d.rounded_rectangle(P(90, yy - 22, 310, yy + 22), radius=22 * k, fill=C("#C9A86A"), outline=C("#8B6F47"), width=int(5 * k))
        if o >= 1:
            g = 0.5 + 0.5 * math.sin(u * 3)
            d.ellipse(P(230, 230, 280, 280), fill=C("b", int(150 + 100 * g)))
    elif name == "eye":  # ojo que parpadea y mira: avistamientos, "alguien vio…", vigilancia
        cyc = u % 3.2; bl = 1 - (math.sin((cyc - 2.9) / 0.3 * math.pi) if 2.9 < cyc < 3.2 else 0)
        h_ = 95 * max(0.05, bl); look = 35 * math.sin(u * 1.3)
        d.ellipse(P(40, 200 - h_, 360, 200 + h_), fill=C("#F2F2F7"), outline=C(col), width=int(10 * k))
        if bl > 0.3:
            im2 = Image.new("RGBA", im.size, (0, 0, 0, 0)); d2 = ImageDraw.Draw(im2)
            d2.ellipse(P(150 + look, 140, 250 + look, 240), fill=C(col)); d2.ellipse(P(178 + look, 168, 222 + look, 212), fill=C("#0B0B12"))
            d2.ellipse(P(200 + look, 165, 216 + look, 181), fill=C("white"))
            m = Image.new("L", im.size, 0); ImageDraw.Draw(m).ellipse(P(46, 206 - h_, 354, 194 + h_), fill=255)
            im.paste(im2, (0, 0), Image.composite(im2.getchannel("A"), m, m))
        for q in range(5):
            x = 80 + q * 60; d.line(P(x, 200 - h_ - 10, x - 10 + q * 5, 200 - h_ - 45), fill=C(col), width=int(7 * k))
    elif name == "ship":  # barco que se mece en las olas: mar, naufragios, navegantes
        rk = math.sin(u * 2) * 6; by = 200 + math.sin(u * 2.4) * 8
        r = math.radians(rk)
        def R(x, y): return ((200 + (x - 200) * math.cos(r) - (y - by) * math.sin(r)) * k, (by + (x - 200) * math.sin(r) + (y - by) * math.cos(r)) * k)
        d.polygon([R(x, y) for x, y in ((70, by), (330, by), (290, by + 60), (110, by + 60))], fill=C("#8B5E3C"))
        d.line([R(200, by), R(200, by - 170)], fill=C("#C68B59"), width=int(10 * k))
        d.polygon([R(x, y) for x, y in ((208, by - 160), (208, by - 20), (300, by - 30))], fill=C("#F2F2F7"))
        d.polygon([R(x, y) for x, y in ((192, by - 140), (192, by - 20), (120, by - 30))], fill=C("#E5E5EE"))
        d.polygon([R(x, y) for x, y in ((200, by - 170), (200, by - 145), (240, by - 158))], fill=C("b"))
        for row in range(2):
            pts = [(x, 290 + row * 40 + 10 * math.sin(x / 30 + u * 3 + row)) for x in range(0, 401, 10)]
            d.line([(x * k, y * k) for x, y in pts], fill=C(col, 230 - row * 80), width=int(10 * k))
    elif name == "map":  # mapa con pin que cae: lugares, "dónde pasó"
        d.polygon(P(40, 110, 150, 80, 250, 110, 360, 80, 360, 320, 250, 350, 150, 320, 40, 350), fill=C("#E8D5A8"))
        d.line(P(150, 80, 150, 320), fill=C("#C9A86A"), width=int(4 * k)); d.line(P(250, 110, 250, 350), fill=C("#C9A86A"), width=int(4 * k))
        d.line(P(70, 290, 120, 240, 170, 260, 220, 200), fill=C("#8B6F47"), width=int(6 * k))
        b = ease((u - 0.3) / 0.5); py = 60 + 130 * b
        if b > 0:
            if b >= 1:
                g = (u * 1.2) % 1; d.ellipse(P(255 - 50 * g, 215 - 18 * g, 255 + 50 * g, 215 + 18 * g), outline=C(col, int(255 * (1 - g))), width=int(5 * k))
            d.polygon(P(225, py - 10, 285, py - 10, 255, py + 30), fill=C(col)); d.ellipse(P(220, py - 70, 290, py), fill=C(col))
            d.ellipse(P(243, py - 47, 267, py - 23), fill=C("#0B0B12"))
    elif name == "shield":  # escudo con palomita que brilla: ciberseguridad, protección
        g = 0.5 + 0.5 * math.sin(u * 3.5)
        sh = lambda s: [((200 + (x - 200) * s) * k, (200 + (y - 200) * s) * k) for x, y in
                        ((200, 40), (330, 90), (320, 230), (200, 360), (80, 230), (70, 90))]
        for r in range(5, 0, -1):
            d.polygon(sh(1 + r * 0.05), fill=C(col, int(14 * g)))
        d.polygon(sh(1.0), fill=C("#1B1B28"), outline=C(col), width=int(10 * k))
        d.polygon(sh(0.8), outline=C(col, 120), width=int(5 * k))
        c_ = ease((u - 0.3) / 0.6)
        if c_ > 0:
            p0, p1, p2 = (140, 205), (185, 255), (265, 150)
            if c_ < 0.4:
                f_ = c_ / 0.4; pts = [p0, (p0[0] + (p1[0] - p0[0]) * f_, p0[1] + (p1[1] - p0[1]) * f_)]
            else:
                f_ = (c_ - 0.4) / 0.6; pts = [p0, p1, (p1[0] + (p2[0] - p1[0]) * f_, p1[1] + (p2[1] - p1[1]) * f_)]
            d.line([(x * k, y * k) for x, y in pts], fill=C("yellow"), width=int(24 * k), joint="curve")
    elif name == "merge":  # dos bloques que se juntan en uno: compras, fusiones, alianzas
        j = ease(u / 1.0); off = (1 - j) * 70
        g = 0.5 + 0.5 * math.sin(u * 4)
        if j >= 1:
            for r in range(5, 0, -1):
                d.rounded_rectangle(P(40 - r * 8, 120 - r * 8, 360 + r * 8, 280 + r * 8), radius=30 * k, fill=C("yellow", int(12 * g)))
        d.rounded_rectangle(P(40 - off, 120, 200 - off, 280), radius=26 * k, fill=C(col), outline=C("white"), width=int(6 * k))
        d.rounded_rectangle(P(200 + off, 120, 360 + off, 280), radius=26 * k, fill=C("b"), outline=C("white"), width=int(6 * k))
        f = font("bold", int(110 * k))
        for t, cx in (("A", 120 - off), ("B", 280 + off)):
            w = d.textlength(t, font=f); d.text((cx * k - w / 2, 200 * k - f.size * 0.62), t, font=f, fill=C("#0E0E14"))
        if j >= 1:
            fp = font("bold", int(70 * k)); w = d.textlength("+", font=fp)
            d.ellipse(P(165, 165, 235, 235), fill=C("yellow")); d.text((200 * k - w / 2, 200 * k - fp.size * 0.62), "+", font=fp, fill=C("#0E0E14"))
    elif name == "bsod":  # pantalla azul de error con carita triste que parpadea: caídas, fallas, "se cayó todo"
        fl = 1 if (u % 1.2) < 1.0 else 0
        d.rounded_rectangle(P(40, 50, 360, 270), radius=18 * k, fill=C("#1B1B28"), outline=C("grey"), width=int(10 * k))
        d.rectangle(P(58, 68, 342, 252), fill=C("#2B6CE0" if fl else "#1E4FB0"))
        f = font("bold", int(110 * k)); d.text((85 * k, 95 * k), ":(", font=f, fill=C("white"))
        for i in range(3):
            d.rounded_rectangle(P(220, 110 + i * 40, 320 - i * 25, 126 + i * 40), radius=6 * k, fill=C("white", 200))
        d.rectangle(P(180, 270, 220, 320), fill=C("grey")); d.rounded_rectangle(P(120, 315, 280, 340), radius=10 * k, fill=C("grey"))
    elif name == "moon":  # luna con nubes: leyendas, noche, lo sobrenatural
        g = 0.5 + 0.5 * math.sin(u * 2)
        for r_ in range(5, 0, -1): d.ellipse(P(200 - 110 - r_ * 14, 170 - 110 - r_ * 14, 200 + 110 + r_ * 14, 170 + 110 + r_ * 14), fill=C(col, int(10 * g)))
        d.ellipse(P(90, 60, 310, 280), fill=C("#F2EFD8"))
        for x, y, rr in ((150, 120, 22), (240, 180, 30), (180, 220, 16)): d.ellipse(P(x - rr, y - rr, x + rr, y + rr), fill=C("#D8D3B0"))
        for j, (yy, sp) in enumerate(((250, 40), (300, -30))):
            x = (u * sp + j * 150) % 520 - 60
            for dx, rr in ((0, 40), (45, 55), (95, 40)): d.ellipse(P(x + dx - rr, yy - rr * 0.7, x + dx + rr, yy + rr * 0.7), fill=C("#3A3A4E", 235))
    elif name == "cart":  # carrito de compras al que le caen paquetes: compras, ofertas, comercio online
        bob = abs(math.sin(u * 3)) * -6
        for i, (bx, cc) in enumerate(((150, "b"), (215, "yellow"), (180, "a"))):
            b = ease(((u - 0.2 - i * 0.45) % 2.4) / 0.4) if u > 0.2 + i * 0.45 else 0
            if b <= 0: continue
            y = -40 + (150 - i * 22) * b + bob
            d.rounded_rectangle(P(bx - 32, y, bx + 32, y + 60), radius=8 * k, fill=C(cc), outline=C("#0E0E14"), width=int(4 * k))
            d.line(P(bx, y, bx, y + 60), fill=C("#0E0E14", 160), width=int(4 * k))
        d.line(P(30, 90 + bob, 80, 90 + bob, 115, 260 + bob), fill=C("grey"), width=int(12 * k), joint="curve")
        d.polygon(P(88, 140 + bob, 340, 140 + bob, 310, 260 + bob, 115, 260 + bob), fill=C(col, 70), outline=C(col), width=int(10 * k))
        for x in (150, 200, 250, 300):
            d.line(P(x - (x - 200) * 0.1, 145 + bob, x - (x - 200) * 0.1 - 8, 255 + bob), fill=C(col, 150), width=int(5 * k))
        d.line(P(115, 260 + bob, 125, 295 + bob, 300, 295 + bob), fill=C("grey"), width=int(10 * k))
        for wx in (145, 280):
            d.ellipse(P(wx - 24, 300, wx + 24, 348), fill=C("#1B1B28"), outline=C("white"), width=int(7 * k))
            an = u * 8
            d.line(P(wx, 324, wx + 16 * math.cos(an), 324 + 16 * math.sin(an)), fill=C("white"), width=int(5 * k))
    elif name == "tag":  # etiqueta de precio que se balancea con "%": descuentos, ofertas, precios
        ang = math.radians(math.sin(u * 2.2) * 14); px, py = 200, 40
        def R(x, y):
            c, s_ = math.cos(ang), math.sin(ang)
            return ((px + (x - px) * c - (y - py) * s_) * k, (py + (x - px) * s_ + (y - py) * c) * k)
        d.line([R(200, 40), R(200, 105)], fill=C("grey"), width=int(6 * k))
        d.polygon([R(x, y) for x, y in ((200, 95), (290, 160), (290, 360), (110, 360), (110, 160))], fill=C(col), outline=C("white"), width=int(6 * k))
        cx, cy = R(200, 150); d.ellipse([cx - 16 * k, cy - 16 * k, cx + 16 * k, cy + 16 * k], fill=C("#0E0E14"))
        g = 0.5 + 0.5 * math.sin(u * 5)
        f = font("bold", int(120 * k)); tx, ty = R(200, 265); w = d.textlength("%", font=f)
        d.text((tx - w / 2, ty - f.size * 0.62), "%", font=f, fill=C("#0E0E14"))
        for i in range(4):
            ph = u * 2 + i * 1.6; x, y = 200 + 150 * math.cos(ph), 220 + 120 * math.sin(ph); s_ = 10 + 6 * g
            d.polygon(P(x, y - s_, x + s_ / 3, y - s_ / 3, x + s_, y, x + s_ / 3, y + s_ / 3, x, y + s_, x - s_ / 3, y + s_ / 3, x - s_, y, x - s_ / 3, y - s_ / 3), fill=C("yellow", int(120 + 135 * g)))
    elif name == "flame":  # llama que parpadea: pasión, energía, disciplina, "fuego interno"
        g = 0.5 + 0.5 * math.sin(u * 5)
        for r_ in range(5, 0, -1): d.ellipse(P(200 - 120 - r_ * 12, 230 - 120 - r_ * 12, 200 + 120 + r_ * 12, 230 + 120 + r_ * 12), fill=C("b", int(12 * g)))
        f1, f2, f3 = math.sin(u * 9) * 12, math.sin(u * 13 + 1) * 9, math.sin(u * 7 + 2) * 10
        def flame(sc, cc):
            pts = [(200, 360), (110, 300), (100, 220 + f2), (140, 150), (165, 195), (195, 45 + f1), (245, 150 + f3), (268, 115 + f2), (305, 215), (292, 300)]
            d.polygon(P(*[v for x, y in pts for v in (200 + (x - 200) * sc, 360 - (360 - y) * sc)]), fill=C(cc))
        flame(1.0, "b"); flame(0.72, "#FF9F43"); flame(0.42, "yellow")
        for i in range(5):  # chispas
            ph = (u * 0.9 + i * 0.37) % 1; x = 130 + i * 35 + math.sin(u * 4 + i) * 12
            d.ellipse(P(x - 6, 120 - ph * 120 - 6, x + 6, 120 - ph * 120 + 6), fill=C("yellow", int(255 * (1 - ph))))
    elif name == "mountain":  # montaña con escalador que llega a la cima y bandera que ondea: metas, superación
        d.polygon(P(20, 360, 160, 150, 300, 360), fill=C("#2A2A3C"))
        d.polygon(P(80, 360, 220, 90, 380, 360), fill=C(col, 120), outline=C(col), width=int(6 * k))
        d.polygon(P(220, 90, 185, 150, 205, 140, 222, 158, 240, 140, 258, 152), fill=C("white"))
        c = ease(min(1, u / 2.0)); x, y = 110 + (218 - 110) * c, 330 + (88 - 330) * c
        d.ellipse(P(x - 12, y - 34, x + 12, y - 10), fill=C("yellow"))
        if c >= 1:
            fl = ease((u - 2.0) / 0.4)
            d.line(P(222, 88, 222, 88 - 70 * fl), fill=C("white"), width=int(6 * k))
            w_ = math.sin(u * 6) * 8
            d.polygon(P(222, 18 + 70 * (1 - fl), 290, 32 + w_ + 70 * (1 - fl), 222, 50 + 70 * (1 - fl)), fill=C("b", int(255 * fl)))
    elif name == "rocket":  # cohete que tiembla y despega: crecimiento, éxito, "ir por más"
        sh = math.sin(u * 40) * 3; lift = -min(30, u * 8)
        for i in range(6):  # líneas de velocidad
            ph = (u * 1.6 + i * 0.17) % 1; x = 80 + i * 50
            d.line(P(x, 40 + ph * 360, x, 40 + ph * 360 + 40), fill=C("white", int(120 * (1 - ph))), width=int(5 * k))
        fl = 60 + math.sin(u * 20) * 18
        d.polygon(P(175 + sh, 300 + lift, 225 + sh, 300 + lift, 200 + sh, 300 + fl + lift), fill=C("#FF9F43"))
        d.polygon(P(188 + sh, 300 + lift, 212 + sh, 300 + lift, 200 + sh, 300 + fl * 0.6 + lift), fill=C("yellow"))
        d.polygon(P(160 + sh, 230 + lift, 130 + sh, 300 + lift, 165 + sh, 290 + lift), fill=C("b"))
        d.polygon(P(240 + sh, 230 + lift, 270 + sh, 300 + lift, 235 + sh, 290 + lift), fill=C("b"))
        d.polygon(P(200 + sh, 40 + lift, 245 + sh, 130 + lift, 240 + sh, 300 + lift, 160 + sh, 300 + lift, 155 + sh, 130 + lift), fill=C("white"))
        d.ellipse(P(178 + sh, 140 + lift, 222 + sh, 184 + lift), fill=C(col), outline=C("#1B1B28"), width=int(6 * k))
    elif name == "bolt":  # rayo que destella: energía, decisión, "ahora o nunca"
        g = 1 if (u % 1.4) < 0.12 else 0.5 + 0.3 * math.sin(u * 4)
        for r_ in range(6, 0, -1): d.ellipse(P(200 - 100 - r_ * 14, 200 - 100 - r_ * 14, 200 + 100 + r_ * 14, 200 + 100 + r_ * 14), fill=C(col, int(14 * g)))
        d.polygon(P(230, 30, 110, 220, 190, 220, 160, 370, 295, 160, 210, 160, 255, 30), fill=C("yellow" if g >= 1 else col), outline=C("white"), width=int(5 * k))
    elif name == "heart":  # corazón que late: familia, amor, gratitud
        s_ = 1 + 0.08 * max(0, math.sin(u * 7)) ** 8 + 0.05 * math.sin(u * 3.5)
        def H_(x, y): return (200 + (x - 200) * s_, 210 + (y - 210) * s_)
        pts = [H_(200 + 160 * math.sin(th) ** 3 * 0.95, 200 - (130 * math.cos(th) - 50 * math.cos(2 * th) - 20 * math.cos(3 * th) - 10 * math.cos(4 * th)) * 0.9) for th in [i * 2 * math.pi / 60 for i in range(60)]]
        d.polygon(P(*[v for p in pts for v in p]), fill=C(col), outline=C("white"), width=int(5 * k))
    out = im.resize((sz, sz), Image.LANCZOS)
    if a < 1:
        al = out.getchannel("A").point(lambda v: int(v * a)); out.putalpha(al)
    return out

def _bg_stars(T):
    """Fondo de misterio: estrellas que titilan + niebla que se desplaza despacio."""
    if "stars" not in _bg_cache:
        rnd = np.random.default_rng(11)
        _bg_cache["stars"] = [(float(rnd.uniform(0, W)), float(rnd.uniform(0, H)), float(rnd.uniform(1.5, 4.5)), float(rnd.uniform(0, 6.3)), float(rnd.uniform(0.6, 2.2))) for _ in range(140)]
        _bg_cache["fog"] = [(float(rnd.uniform(-200, W)), float(rnd.uniform(0, H)), float(rnd.uniform(180, 380)), float(rnd.uniform(8, 22)), CHIP_COLORS[int(rnd.integers(0, 5))]) for _ in range(9)]
        _bg_cache["fog_img"] = {}
    im = Image.new("RGB", (W, H), BG)
    fog = Image.new("RGB", (W // 4, H // 4), BG); fd = ImageDraw.Draw(fog)
    for x, y, r, sp, cc in _bg_cache["fog"]:
        xx = ((x + T * sp + r) % (W + 2 * r)) - r
        fd.ellipse([(xx - r) / 4, (y - r * 0.6) / 4, (xx + r) / 4, (y + r * 0.6) / 4], fill=mix(cc, 0.07))
    from PIL import ImageFilter
    fog = fog.filter(ImageFilter.GaussianBlur(10)).resize((W, H), Image.BILINEAR)
    im = fog; d = ImageDraw.Draw(im)
    for x, y, r, ph, sp in _bg_cache["stars"]:
        al = 0.25 + 0.55 * (0.5 + 0.5 * math.sin(T * sp + ph))
        yy = (y + T * 6) % H
        d.ellipse([x - r, yy - r, x + r, yy + r], fill=mix("white", al))
    return im

def _bg_energy(T):
    """Fondo motivacional: manchas de luz de colores que se mueven + chispas que suben."""
    from PIL import ImageFilter
    if "blobs" not in _bg_cache:
        rnd = np.random.default_rng(5)
        _bg_cache["blobs"] = [(float(rnd.uniform(0.1, 0.9)), float(rnd.uniform(0.1, 0.9)), float(rnd.uniform(260, 420)),
                               float(rnd.uniform(0, 6.3)), float(rnd.uniform(0.15, 0.35)), CHIP_COLORS[i % 5]) for i in range(6)]
        _bg_cache["sparks"] = [(float(rnd.uniform(0, W)), float(rnd.uniform(0, H)), float(rnd.uniform(2, 5)), float(rnd.uniform(60, 180)),
                                float(rnd.uniform(0, 6.3))) for _ in range(70)]
    s = 8; sm = Image.new("RGB", (W // s, H // s), BG); sd = ImageDraw.Draw(sm)
    for fx, fy, r, ph, sp, cc in _bg_cache["blobs"]:
        x = (fx + 0.22 * math.sin(T * sp + ph)) * W; y = (fy + 0.15 * math.cos(T * sp * 1.3 + ph)) * H
        sd.ellipse([(x - r) / s, (y - r) / s, (x + r) / s, (y + r) / s], fill=mix(cc, 0.20))
    im = sm.filter(ImageFilter.GaussianBlur(14)).resize((W, H), Image.BILINEAR); d = ImageDraw.Draw(im)
    for x, y, r, sp, ph in _bg_cache["sparks"]:
        yy = (y - T * sp) % H; xx = x + 14 * math.sin(T * 1.5 + ph)
        al = 0.25 + 0.45 * (0.5 + 0.5 * math.sin(T * 3 + ph))
        d.ellipse([xx - r, yy - r, xx + r, yy + r], fill=mix("yellow" if ph > 3 else "white", al))
    return im

_bg_cache = {}
def background(T):
    kind = SPEC.get("background")
    if not kind: return Image.new("RGB", (W, H), BG)
    if kind == "stars": return _bg_stars(T)
    if kind == "energy": return _bg_energy(T)
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

MOTION = SPEC.get("motion") in ("alta", "high", True)
def back(x):  # easing con rebote (se pasa un poco y vuelve)
    x = max(0.0, min(1.0, x)); c1 = 1.9; return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2
def _norm(w): return re.sub(r"[^\wáéíóúñü%]", "", w.lower())

def draw_words(d, e, y, t, at, col):
    """Texto palabra por palabra (cada una salta al entrar); las palabras de 'hl' van en color de resaltado."""
    f = font(e.get("weight", "bold"), e.get("size", 72)); step = e.get("step", 0.09)
    hl = {_norm(w) for w in e.get("hl", [])}; hc = e.get("hlcolor", "yellow"); k = 0
    sp = d.textlength(" ", font=f)
    for line in wrap(e["text"], f, e.get("maxw", 920)):
        ws = line.split(" "); x = (W - d.textlength(line, font=f)) / 2
        for w in ws:
            b = back((t - at - k * step) / 0.3); al = min(1.0, max(0.0, (t - at - k * step) / 0.12))
            if al > 0:
                d.text((x, y + (1 - b) * 45), w, font=f, fill=mix(hc if _norm(w) in hl else col, al))
            x += d.textlength(w, font=f) + sp; k += 1
        y += int(f.size * 1.18)

def draw_el(im, d, e, y, t, at):
    typ, col = e["type"], e.get("color", "white")
    a = ease((t - at) / 0.45)
    if typ == "text" and (MOTION or e.get("fx") == "words" or e.get("hl")) and e.get("fx") != "fade":
        if t >= at: draw_words(d, e, y, t, at, col)
        return
    if typ == "big" and (MOTION or "count_to" in e):
        if t < at: return
        u = t - at; size = e.get("size", 190); txt = e.get("text", "")
        if "count_to" in e:
            n = e["count_to"] * ease(u / e.get("count_dur", 1.2))
            txt = e.get("prefix", "") + f"{int(round(n)):,}".replace(",", ".") + e.get("suffix", "")
        sc = (0.35 + 0.65 * back(u / 0.4)) * (1 + 0.03 * math.sin(u * 3.2)) if MOTION else 1.0
        f = font("bold", max(12, int(size * sc / 2) * 2)); al = min(1.0, u / 0.12)
        dx = 14 * math.sin(u * 55) * max(0.0, 1 - u / 0.35) if e.get("shake") else 0
        w = d.textlength(txt, font=f); yy = y + (size - f.size) * 0.55
        d.text(((W - w) / 2 + dx + 7, yy + 9), txt, font=f, fill=mix((0, 0, 0), 0.9 * al))
        d.text(((W - w) / 2 + dx, yy), txt, font=f, fill=mix(col, al)); return
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
            if b > 0 and MOTION:  # entra deslizándose desde la izquierda con rebote
                bx = -260 * (1 - back((t - at - k * e.get("step", 0.9)) / 0.4))
                d.ellipse([90 + bx, y + 4, 150 + bx, y + 64], fill=mix(cols[k % 5], b))
                n = str(k + 1); nw = d.textlength(n, font=font("bold", 42))
                d.text((120 + bx - nw / 2, y + 8), n, font=font("bold", 42), fill=BG)
                for j, line in enumerate(lines):
                    d.text((190 + bx, y + j * int(f.size * 1.22)), line, font=f, fill=mix("white", b))
            elif b > 0:
                d.ellipse([90, y + 4 + off, 150, y + 64 + off], fill=mix(cols[k % 5], b))
                n = str(k + 1); nw = d.textlength(n, font=font("bold", 42))
                d.text((120 - nw / 2, y + 8 + off), n, font=font("bold", 42), fill=BG)
                for j, line in enumerate(lines):
                    d.text((190, y + j * int(f.size * 1.22) + off), line, font=f, fill=mix("white", b))
            y += max(1, len(lines)) * int(f.size * 1.22) + 70

# ---------- 3. render ----------
LEAD, TOP, BOTTOM = 0.25, 230, 1560
POP = SPEC.get("captions") == "pop" or (MOTION and SPEC.get("captions") != "box")
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
                if cur and len(cur) + 1 + len(w) > (14 if POP else 20): gs.append(cur); cur = w
                else: cur = (cur + " " + w).strip()
            gs.append(cur); n = sum(len(g) for g in gs); t0 = st + LEAD + s0
            for g in gs:
                dd = (s1 - s0) * len(g) / n; chunks.append((t0, t0 + dd, g)); t0 += dd
    subf = font("bold", 62)

    def camera(L, i, t):
        """Modo motion: golpe de zoom al entrar a la escena + acercamiento lento continuo."""
        z = 1 + 0.04 * min(1.0, t / durs[i]) + (0.09 * (1 - ease(t / 0.3)) if i > 0 else 0)
        if z <= 1.001: return L, 0, 0
        L2 = L.resize((int(W * z), int(H * z)), Image.BILINEAR)
        return L2, -(L2.width - W) // 2, -(L2.height - H) // 2

    def draw_pop_caption(im, d, T):
        cur = [c for c in chunks if c[0] <= T < c[1] + 0.08]
        if not cur: return
        t0, t1, txt = cur[-1]; ws = txt.split(); n = sum(len(w) for w in ws) or 1
        u = T - t0; sc = 0.8 + 0.2 * back(u / 0.18); f = font("bold", int(84 * sc / 2) * 2)
        tw = [d.textlength(w, font=f) for w in ws]; sp = d.textlength(" ", font=f)
        x = (W - sum(tw) - sp * (len(ws) - 1)) / 2; y = 1630 + (84 - f.size) / 2; acc = t0
        for w, wpx in zip(ws, tw):
            wd = (t1 - t0) * len(w) / n; on = acc <= T < acc + wd + 0.02; acc += wd
            d.text((x, y - (8 if on else 0)), w, font=f, fill=rgb("yellow") if on else rgb("white"),
                   stroke_width=7, stroke_fill=(0, 0, 0))
            x += wpx + sp

    TR = 0.3 if SPEC.get("transition") else 0
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
            L = scene_layer(i, t)
            if MOTION: L, ox, oy = camera(L, i, t); im.paste(L, (ox, oy), L)
            else: im.paste(L, (0, 0), L)
        if MOTION and i > 0 and t < 0.14:  # destello suave al cortar de escena
            fl = Image.new("RGB", (W, H), (255, 255, 255)); im = Image.blend(im, fl, 0.22 * (1 - t / 0.14)); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W * T / total, 10], fill=rgb("yellow"))
        if POP and SPEC.get("subtitles", True): draw_pop_caption(im, d, T); return im
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
