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
    return 0

def draw_el(d, e, y, t, at):
    typ, col = e["type"], e.get("color", "white")
    a = ease((t - at) / 0.45)
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

    def frame(T):
        im = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(im)
        d.rectangle([0, 0, W * T / total, 10], fill=rgb("yellow"))
        i = max(k for k in range(len(starts)) if starts[k] <= T); t = T - starts[i]
        for e, y, at in layouts[i]: draw_el(d, e, y, t, at)
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
