"""Genera un Reel vertical (1080x1920, 30 fps, MP4 H.264 + música original) a partir de un JSON.

Uso: python3 tools/reel.py FECHA/reel.json FECHA
Salida: FECHA/reel.mp4, FECHA/cover.jpg (portada) y FECHA/frames_check/escenaN.png (para revisar).

Formato del JSON:
{
  "scenes": [
    {"dur": 3.0, "html": "<div class='tag in'><i></i>Falla mundial</div><h1 class='in' style='--d:.2s'>...</h1>"},
    ...
  ],
  "cover_scene": 0          # opcional: escena usada como portada (por defecto la 0)
}

Animaciones (añade la clase al elemento; retraso con style='--d:.4s'):
  in    -> sube y aparece          pop  -> aparece con rebote
  left  -> entra desde la izquierda  grow -> barra/elemento que crece a lo ancho
  shake -> tiembla (fallas, alertas) pulse -> late suavemente en bucle
Clases de diseño: tag, h1, h2, p, b, sub, art, card, row, pill (.n/.l), cta, big, chip, red (texto rojo).
Zonas seguras de Reels: el contenido va entre y=230 y y=1500 px; nada importante a la derecha (últimos 140 px).
"""
import json, sys, pathlib, shutil, subprocess, math, wave, struct, random
from playwright.sync_api import sync_playwright

W, H, FPS = 1080, 1920, 30
BG, TXT, AZUL, VERDE, ROJO = "#F5F7FA", "#111827", "#2563EB", "#10B981", "#EF4444"
HANDLE = "@josealfredomatias1"

CSS = f"""
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:{W}px;height:{H}px;background:{BG};color:{TXT};font-family:'Poppins','Inter',sans-serif;
 overflow:hidden;position:relative}}
.blob{{position:absolute;border-radius:50%;filter:blur(70px);opacity:.35}}
.b1{{width:620px;height:620px;background:#BFDBFE;left:-200px;top:120px;animation:drift 14s ease-in-out infinite alternate;animation-delay:var(--start)}}
.b2{{width:560px;height:560px;background:#A7F3D0;right:-220px;top:1100px;animation:drift2 12s ease-in-out infinite alternate;animation-delay:var(--start)}}
@keyframes drift{{to{{transform:translate(160px,260px) scale(1.15)}}}}
@keyframes drift2{{to{{transform:translate(-180px,-240px) scale(1.1)}}}}
.bar{{position:absolute;left:90px;right:90px;top:150px;height:10px;border-radius:6px;background:#E5E7EB;overflow:hidden}}
.bar span{{display:block;height:100%;width:100%;background:{AZUL};transform-origin:left;
 animation:prog var(--total) linear forwards;animation-delay:var(--start)}}
@keyframes prog{{from{{transform:scaleX(0)}}to{{transform:scaleX(1)}}}}
.wrap{{position:absolute;left:90px;right:150px;top:240px;bottom:420px;display:flex;flex-direction:column;
 justify-content:center;animation:out .3s ease-in forwards;animation-delay:var(--outd)}}
@keyframes out{{to{{opacity:0;transform:translateY(-30px)}}}}
.tag{{display:inline-flex;align-items:center;gap:14px;font:700 36px 'Inter';letter-spacing:.06em;
 text-transform:uppercase;color:{AZUL};margin-bottom:40px}}
.tag i{{width:22px;height:22px;border-radius:50%;background:{VERDE};display:inline-block}}
h1{{font:800 112px/1.04 'Poppins';letter-spacing:-.02em}}
h2{{font:700 86px/1.1 'Poppins';letter-spacing:-.015em}}
p{{font:500 50px/1.4 'Inter';color:#1F2937;margin-top:30px}}
b{{color:{AZUL};font-weight:800}} .red{{color:{ROJO}}} .green{{color:{VERDE}}}
.sub{{font:700 50px/1.3 'Inter';color:{TXT};margin-top:40px}}
.art{{display:flex;align-items:center;justify-content:center;margin:40px 0}}
.big{{font:800 260px/1 'Poppins';color:{AZUL};letter-spacing:-.04em}}
.card{{background:#fff;border-radius:40px;padding:48px 52px;box-shadow:0 14px 50px rgba(17,24,39,.08);margin-top:40px}}
.card p{{margin-top:0}}
.row{{display:flex;gap:30px;margin-top:40px}}
.pill{{flex:1;background:#fff;border-radius:34px;padding:40px 34px;box-shadow:0 14px 50px rgba(17,24,39,.08)}}
.pill .n{{font:800 84px/1 'Poppins';color:{VERDE}}}
.pill .l{{font:600 36px/1.3 'Inter';color:#374151;margin-top:14px}}
.chip{{display:inline-block;background:{TXT};color:#fff;border-radius:999px;padding:16px 34px;font:700 40px 'Inter';margin-top:30px}}
.cta{{background:{AZUL};color:#fff;border-radius:999px;padding:34px 54px;font:700 52px 'Poppins';
 align-self:flex-start;display:flex;gap:20px;align-items:center;margin-top:50px}}
.cta i{{width:26px;height:26px;border-radius:50%;background:{VERDE};display:inline-block}}
.foot{{position:absolute;left:90px;bottom:330px;display:flex;align-items:center;gap:18px;font:700 36px 'Inter';color:#4B5563}}
.av{{width:66px;height:66px;border-radius:50%;background:{AZUL};color:#fff;display:grid;place-items:center;font:700 28px 'Poppins'}}
.in,.pop,.left,.grow,.shake{{opacity:0;animation-fill-mode:both;animation-delay:var(--d,0s)}}
.in{{animation:in .55s cubic-bezier(.2,.8,.2,1) both;animation-delay:var(--d,0s)}}
.pop{{animation:pop .6s cubic-bezier(.3,1.6,.5,1) both;animation-delay:var(--d,0s)}}
.left{{animation:left .55s cubic-bezier(.2,.8,.2,1) both;animation-delay:var(--d,0s)}}
.grow{{transform-origin:left;animation:grow .9s cubic-bezier(.2,.8,.2,1) both;animation-delay:var(--d,0s)}}
.shake{{animation:in .4s ease-out both, shake .5s ease-in-out 3;animation-delay:var(--d,0s),calc(var(--d,0s) + .4s)}}
.pulse{{animation:pulse 1.2s ease-in-out infinite}}
@keyframes in{{from{{opacity:0;transform:translateY(60px)}}to{{opacity:1;transform:none}}}}
@keyframes pop{{from{{opacity:0;transform:scale(.4)}}to{{opacity:1;transform:none}}}}
@keyframes left{{from{{opacity:0;transform:translateX(-120px)}}to{{opacity:1;transform:none}}}}
@keyframes grow{{from{{opacity:1;transform:scaleX(0)}}to{{opacity:1;transform:scaleX(1)}}}}
@keyframes shake{{0%,100%{{transform:none}}25%{{transform:translateX(-14px) rotate(-1deg)}}75%{{transform:translateX(14px) rotate(1deg)}}}}
@keyframes pulse{{0%,100%{{transform:scale(1)}}50%{{transform:scale(1.06)}}}}
"""


def page(scene, start, total, last):
    dur = scene["dur"]
    outd = f"{dur - 0.3:.2f}s" if not last else "999s"
    return (f"<html><head><meta charset='utf-8'><style>{CSS}</style></head>"
            f"<body style='--total:{total}s;--start:-{start}s;--outd:{outd}'>"
            f"<div class='blob b1'></div><div class='blob b2'></div>"
            f"<div class='bar'><span></span></div>"
            f"<div class='wrap'>{scene['html']}</div>"
            f"<div class='foot'><div class='av'>JA</div>{HANDLE}</div></body></html>")


def music(path, seconds, bpm=112, seed=7):
    """Pista instrumental original (sintetizada aquí, sin copyright): bombo, hi-hat, bajo y acordes."""
    sr = 44100
    n = int(seconds * sr)
    beat = 60 / bpm
    rnd = random.Random(seed)
    chords = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62]]  # Am F C G
    f = lambda m: 440 * 2 ** ((m - 69) / 12)
    buf = [0.0] * n
    def add(t0, dur, fn, amp):
        s0 = int(t0 * sr)
        for i in range(int(dur * sr)):
            j = s0 + i
            if j >= n: break
            buf[j] += amp * fn(i / sr)
    t = 0.0; k = 0
    while t < seconds:
        # bombo en 1 y 3, hi-hat en corcheas
        if k % 2 == 0:
            add(t, .35, lambda x: math.sin(2 * math.pi * (50 + 90 * math.exp(-x * 30)) * x) * math.exp(-x * 9), .55)
        for h in (0, .5):
            add(t + h * beat, .05, lambda x: (rnd.random() * 2 - 1) * math.exp(-x * 80), .12)
        bar = int(t / (beat * 4)) % 4
        ch = chords[bar]
        if k % 4 == 0:
            for m in ch:
                fr = f(m)
                add(t, beat * 4, lambda x, fr=fr: (math.sin(2 * math.pi * fr * x) + .3 * math.sin(4 * math.pi * fr * x))
                    * min(1, x * 8) * math.exp(-x * .6), .07)
        fb = f(ch[0] - 12)
        add(t, beat * .9, lambda x, fb=fb: math.sin(2 * math.pi * fb * x) * math.exp(-x * 3), .22)
        t += beat; k += 1
    fade = int(1.0 * sr)
    peak = max(1e-6, max(abs(v) for v in buf))
    with wave.open(str(path), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        frames = bytearray()
        for i, v in enumerate(buf):
            g = .8 / peak * min(1, i / 2000, (n - i) / fade)
            frames += struct.pack("<h", int(max(-1, min(1, v * g)) * 32767))
        w.writeframes(bytes(frames))


def main(src, out):
    data = json.loads(pathlib.Path(src).read_text())
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    scenes = data["scenes"]
    total = round(sum(s["dur"] for s in scenes), 2)
    tmp = out / "_frames"; shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
    chk = out / "frames_check"; shutil.rmtree(chk, ignore_errors=True); chk.mkdir()
    idx = 0; start = 0.0
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": W, "height": H})
        for si, s in enumerate(scenes):
            pg.set_content(page(s, start, total, si == len(scenes) - 1))
            pg.wait_for_timeout(200)
            pg.evaluate("document.getAnimations().forEach(a=>a.pause())")
            nf = int(round(s["dur"] * FPS))
            for fi in range(nf):
                ms = fi * 1000 / FPS
                pg.evaluate(f"document.getAnimations().forEach(a=>a.currentTime={ms})")
                pg.screenshot(path=str(tmp / f"f{idx:05d}.jpg"), type="jpeg", quality=92)
                if fi == min(nf - 1, int((s['dur'] - 0.45) * FPS)):
                    shutil.copy(tmp / f"f{idx:05d}.jpg", chk / f"escena{si+1}.jpg")
                idx += 1
            start += s["dur"]
        b.close()
    cs = data.get("cover_scene", 0)
    shutil.copy(chk / f"escena{cs+1}.jpg", out / "cover.jpg")
    wav = out / "_music.wav"; music(wav, total)
    mp4 = out / "reel.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "f%05d.jpg"),
                    "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
                    "-profile:v", "high", "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
                    "-shortest", "-movflags", "+faststart", str(mp4)], check=True)
    shutil.rmtree(tmp); wav.unlink()
    print("ok", mp4, f"{total}s", idx, "frames")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
