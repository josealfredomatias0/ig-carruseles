"""Reel narrado estilo "explicador oscuro" (1080x1920, 30 fps, voz IA + subtítulos + música original).

Uso: python3 tools/reel_voz.py FECHA/reel.json FECHA
Salida: FECHA/reel.mp4, FECHA/cover.jpg, FECHA/frames_check/escenaN.jpg (para revisar), FECHA/voz.txt (guion).

Requiere (se instala solo si falta): pip install kokoro-onnx soundfile --break-system-packages
y el modelo de voz en ~/.cache/kokoro (se descarga de GitHub la primera vez, ~350 MB).

JSON:
{
  "voice": "em_alex",            # voces en español: em_alex (hombre), ef_dora (mujer), em_santa
  "speed": 1.12,
  "scenes": [
    {
      "say": ["Microsoft le debe dinero", {"say": "a cuarenta y tres millones", "cap": "a 43 millones"}],
      "html": "<div class='badge in'>Caída · 12 nov</div><div class='t1 pop' style='--d:{t1}'>TE <span class='o'>DEBE</span></div>",
      "wipe": true               # opcional: barrido naranja al ENTRAR en esta escena
    }
  ],
  "cover_scene": 0
}
- "say": frases que dice la voz, en orden. Escribe cifras y siglas COMO SE PRONUNCIAN ("trece por ciento",
  "ce, e, o"). Si quieres que el subtítulo muestre otra cosa (cifras), usa {"say": ..., "cap": ...}.
- En "html", {tN} se reemplaza por el segundo (con "s") en que empieza la frase N de esa escena y {nN} por el
  mismo número sin "s". Úsalo para que cada elemento aparezca justo cuando la voz lo menciona: style='--d:{t1}'.
- Contador animado: <span class='count' data-to='43' data-d='{n1}' data-suf='%' data-dec='0'></span>

Clases: badge (etiqueta naranja), kicker (texto pequeño en mayúsculas), t1 (título gigante Anton),
t2 (título mediano Anton), o (naranja), w (blanco), red, outline (solo contorno naranja), num (cifra gigante
naranja) + unit, label, card (tarjeta crema), steps > step > k (número) + div, chips > chip, meter > span (barra),
row > box (.n cifra / .l etiqueta), art (ilustración SVG).
Animaciones: in, pop, left, right, grow (barras), shake, pulse, slam (golpe de tamaño).
Zona útil: de y=220 a y=1360; los subtítulos van solos en y≈1430. Nada importante a la derecha (últimos 150 px).
"""
import json, sys, pathlib, shutil, subprocess, base64, re, os, wave
import numpy as np
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).parent))
from reel import music  # pista instrumental original

W, H, FPS, SR = 1080, 1920, 30, 24000
NAR = "#F28C28"; CREMA = "#F7F1E8"; HANDLE = "@josealfredomatias1"
FONT = base64.b64encode((pathlib.Path(__file__).parent / "fonts/Anton-Regular.ttf").read_bytes()).decode()
CACHE = pathlib.Path.home() / ".cache/kokoro"
MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"

CSS = """
@font-face{font-family:'Anton';src:url(data:font/ttf;base64,%FONT%) format('truetype')}
*{margin:0;padding:0;box-sizing:border-box}
body{width:1080px;height:1920px;overflow:hidden;position:relative;color:#fff;font-family:'Inter',sans-serif;
 background:radial-gradient(120% 70% at 25% 0%,#4a2c14 0%,#24170e 45%,#140e0a 100%)}
.glow{position:absolute;width:900px;height:900px;border-radius:50%;background:#F28C28;opacity:.10;filter:blur(120px);
 left:-300px;top:-250px;animation:gl 9s ease-in-out infinite alternate;animation-delay:var(--start)}
@keyframes gl{to{transform:translate(380px,520px)}}
.waves{position:absolute;left:0;right:0;bottom:250px;opacity:.10;animation:wv 8s linear infinite;animation-delay:var(--start)}
@keyframes wv{to{transform:translateX(-540px)}}
.wrap{position:absolute;left:80px;right:150px;top:220px;bottom:560px;display:flex;flex-direction:column;justify-content:center;
 animation:out .25s ease-in forwards;animation-delay:var(--outd)}
@keyframes out{to{opacity:0}}
.badge{align-self:flex-start;background:#F28C28;color:#1a120c;font:800 34px 'Inter';letter-spacing:.05em;text-transform:uppercase;
 padding:12px 26px;border-radius:14px;margin-bottom:34px}
.kicker{font:800 32px 'Inter';letter-spacing:.07em;text-transform:uppercase;color:#E8DCCD;margin-bottom:26px}
.t1{font:400 190px/0.98 'Anton';text-transform:uppercase;letter-spacing:.005em}
.t2{font:400 120px/1.02 'Anton';text-transform:uppercase}
.o{color:#F28C28}.w{color:#fff}.red{color:#EF4444}
.outline{color:transparent;-webkit-text-stroke:5px #F28C28}
.num{font:400 330px/0.9 'Anton';color:#F28C28;letter-spacing:-.01em}
.unit{font:400 90px 'Anton';color:#fff;margin-left:14px;text-transform:lowercase}
.label{font:800 52px/1.25 'Inter';color:#fff;margin:18px 0}
.small{font:600 38px/1.35 'Inter';color:#D9CCBC;margin-top:22px}
.card{background:#F7F1E8;color:#1a120c;border-radius:28px;padding:40px 44px;margin-top:30px;box-shadow:0 20px 60px rgba(0,0,0,.35)}
.card p{font:600 42px/1.35 'Inter'} .card b{color:#C2410C;font-weight:800}
.steps{background:#F7F1E8;border-radius:28px;padding:38px 40px;margin-top:30px;display:flex;flex-direction:column;gap:30px}
.step{display:flex;gap:26px;align-items:flex-start;color:#1a120c;font:600 38px/1.3 'Inter'}
.step .k{flex:none;width:62px;height:62px;border-radius:12px;background:#F28C28;color:#1a120c;display:grid;place-items:center;font:400 40px 'Anton'}
.step b{font-weight:800}
.chips{display:flex;gap:22px;flex-wrap:wrap;margin:10px 0 20px}
.chip{background:#F7F1E8;color:#1a120c;font:800 44px 'Inter';padding:16px 30px;border-radius:18px}
.meter{height:46px;border-radius:12px;background:rgba(255,255,255,.08);margin:14px 0 26px;overflow:hidden}
.meter span{display:block;height:100%;border-radius:12px;background:#F28C28}
.row{display:flex;gap:26px;margin-top:30px}
.box{flex:1;border:3px solid rgba(242,140,40,.6);border-radius:26px;padding:34px 30px}
.box .n{font:400 110px/1 'Anton';color:#F28C28}.box .l{font:700 36px/1.3 'Inter';color:#E8DCCD;margin-top:10px}
.art{display:flex;justify-content:center;margin:20px 0}
.cap{position:absolute;left:70px;right:150px;top:1395px;text-align:center;font:800 56px/1.2 'Inter';color:#fff;
 text-shadow:0 4px 18px rgba(0,0,0,.8)}
.cap span{background:rgba(0,0,0,.35);padding:6px 16px;border-radius:12px;-webkit-box-decoration-break:clone}
.foot{position:absolute;left:80px;top:150px;font:700 32px 'Inter';color:rgba(255,255,255,.55)}
.wipe{position:absolute;inset:-10% -30%;background:#F28C28;transform:skewX(-12deg) translateX(-140%);z-index:50}
.wipe.inn{animation:wi .4s cubic-bezier(.6,0,.3,1) forwards}
@keyframes wi{from{transform:skewX(-12deg) translateX(0)}to{transform:skewX(-12deg) translateX(140%)}}
.wipe.outt{animation:wo .3s cubic-bezier(.6,0,.3,1) forwards;animation-delay:var(--wod)}
@keyframes wo{from{transform:skewX(-12deg) translateX(-140%)}to{transform:skewX(-12deg) translateX(0)}}
.in,.pop,.left,.right,.slam,.shake{animation-fill-mode:both;animation-delay:var(--d,0s)}
.in{animation:in .45s cubic-bezier(.2,.8,.2,1) both;animation-delay:var(--d,0s)}
.pop{animation:pop .5s cubic-bezier(.3,1.5,.5,1) both;animation-delay:var(--d,0s)}
.slam{animation:slam .45s cubic-bezier(.2,.9,.3,1) both;animation-delay:var(--d,0s)}
.left{animation:left .45s cubic-bezier(.2,.8,.2,1) both;animation-delay:var(--d,0s)}
.right{animation:right .45s cubic-bezier(.2,.8,.2,1) both;animation-delay:var(--d,0s)}
.grow{transform-origin:left;animation:grow 1s cubic-bezier(.2,.8,.2,1) both;animation-delay:var(--d,0s)}
.shake{animation:in .35s ease-out both,shake .45s ease-in-out 3;animation-delay:var(--d,0s),calc(var(--d,0s) + .35s)}
.pulse{animation:pulse 1.1s ease-in-out infinite}
@keyframes in{from{opacity:0;transform:translateY(50px)}to{opacity:1;transform:none}}
@keyframes pop{from{opacity:0;transform:scale(.3)}to{opacity:1;transform:none}}
@keyframes slam{from{opacity:0;transform:scale(1.8)}to{opacity:1;transform:none}}
@keyframes left{from{opacity:0;transform:translateX(-140px)}to{opacity:1;transform:none}}
@keyframes right{from{opacity:0;transform:translateX(140px)}to{opacity:1;transform:none}}
@keyframes grow{from{transform:scaleX(0)}to{transform:scaleX(1)}}
@keyframes shake{0%,100%{transform:none}25%{transform:translateX(-12px) rotate(-1deg)}75%{transform:translateX(12px) rotate(1deg)}}
@keyframes pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.05)}}
""".replace("%FONT%", FONT)

WAVES = ("<svg class='waves' width='2160' height='300' viewBox='0 0 2160 300'>" +
         "".join(f"<path d='M0 {120+i*40} " + " ".join(f"Q {270+k*540} {60+i*40} {540+k*540} {120+i*40} T {1080+k*540} {120+i*40}" for k in range(0, 4, 2)) +
                 f"' fill='none' stroke='#F28C28' stroke-width='3'/>" for i in range(3)) + "</svg>")

JS = """
window.__tick=(ms)=>{
 document.querySelectorAll('[data-to]').forEach(e=>{const d=parseFloat(e.dataset.d||0)*1000,du=parseFloat(e.dataset.dur||.9)*1000;
  let p=Math.min(1,Math.max(0,(ms-d)/du));const q=Math.min(1,Math.max(0,(ms-d)/250));e.style.display='inline-block';e.style.opacity=q;e.style.transform='scale('+(0.6+0.4*q)+')';p=1-Math.pow(1-p,3);const dec=parseInt(e.dataset.dec||0);
  e.textContent=(e.dataset.pre||'')+(parseFloat(e.dataset.to)*p).toLocaleString('es-DO',{minimumFractionDigits:dec,maximumFractionDigits:dec})+(e.dataset.suf||'');});
 const c=document.getElementById('cap');let t='';for(const [a,b,x] of window.__caps){if(ms>=a&&ms<b){t=x;break;}}
 c.innerHTML=t?'<span>'+t+'</span>':'';
};
"""


def ensure_tts():
    try:
        import kokoro_onnx, soundfile  # noqa
    except ImportError:
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "kokoro-onnx", "soundfile", "--break-system-packages"], check=True)
    CACHE.mkdir(parents=True, exist_ok=True)
    for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
        p = CACHE / f
        if not p.exists() or p.stat().st_size < 1_000_000:
            subprocess.run(["curl", "-sSL", "-m", "600", "-o", str(p), MODEL_URL + f], check=True)
    from kokoro_onnx import Kokoro
    return Kokoro(str(CACHE / "kokoro-v1.0.onnx"), str(CACHE / "voices-v1.0.bin"))


def chunks(text, maxw=4):
    """Divide el subtítulo en trozos cortos (máx. 4 palabras), cortando en la puntuación."""
    out, cur = [], []
    for w in text.split():
        cur.append(w)
        if len(cur) >= maxw or re.search(r"[.,;:!?…]$", w):
            out.append(" ".join(cur)); cur = []
    if cur: out.append(" ".join(cur))
    # evita trozos de 1 palabra sueltos al final
    if len(out) > 1 and len(out[-1].split()) == 1:
        last = out.pop(); out[-1] += " " + last
    return out


def trim(a, thr=0.01):
    idx = np.where(np.abs(a) > thr)[0]
    return a if len(idx) == 0 else a[max(0, idx[0] - 600): idx[-1] + 1200]


def main(src, out):
    data = json.loads(pathlib.Path(src).read_text())
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    tts = ensure_tts()
    voice, speed = data.get("voice", "em_alex"), data.get("speed", 1.12)
    GAP, PRE, POST = 0.10, 0.20, 0.30
    plan, voz_txt, t_abs = [], [], 0.0
    track = []
    for si, s in enumerate(data["scenes"]):
        lines = [l if isinstance(l, dict) else {"say": l} for l in s["say"]]
        t = PRE; starts, caps = [], []
        for ln in lines:
            a, sr = tts.create(ln["say"], voice=voice, speed=speed, lang="es")
            a = trim(np.asarray(a, dtype=np.float32)); d = len(a) / sr
            starts.append(t); track.append((t_abs + t, a))
            parts = chunks(ln.get("cap", ln["say"]))
            tot = sum(len(p) for p in parts); c0 = t
            for p in parts:
                c1 = c0 + d * len(p) / tot
                caps.append([int(c0 * 1000), int(c1 * 1000) + 40, p]); c0 = c1
            voz_txt.append(ln["say"]); t += d + GAP
        dur = round(t - GAP + POST, 3)
        html = s["html"]
        for i, st in enumerate(starts):
            html = html.replace("{t%d}" % i, f"{st:.2f}s").replace("{n%d}" % i, f"{st:.2f}")
        plan.append(dict(html=html, dur=dur, caps=caps, start=t_abs, wipe=bool(s.get("wipe"))))
        t_abs += dur
    total = t_abs
    (out / "voz.txt").write_text("\n".join(voz_txt))

    tmp = out / "_frames"; shutil.rmtree(tmp, ignore_errors=True); tmp.mkdir()
    chk = out / "frames_check"; shutil.rmtree(chk, ignore_errors=True); chk.mkdir()
    idx = 0
    with sync_playwright() as pw:
        b = pw.chromium.launch(); pg = b.new_page(viewport={"width": W, "height": H})
        for si, sc in enumerate(plan):
            nxt = plan[si + 1] if si + 1 < len(plan) else None
            last = nxt is None
            wipe = ""
            if sc["wipe"] and si > 0: wipe += "<div class='wipe inn'></div>"
            if nxt and nxt["wipe"]: wipe += "<div class='wipe outt'></div>"
            outd = "999s" if last or (nxt and nxt["wipe"]) else f"{sc['dur'] - 0.25:.2f}s"
            doc = (f"<html><head><meta charset='utf-8'><style>{CSS}</style></head>"
                   f"<body style='--start:-{sc['start']:.2f}s;--outd:{outd};--wod:{sc['dur'] - 0.3:.2f}s'>"
                   f"<div class='glow'></div>{WAVES}<div class='foot'>{HANDLE}</div>"
                   f"<div class='wrap'>{sc['html']}</div><div class='cap' id='cap'></div>{wipe}"
                   f"<script>window.__caps={json.dumps(sc['caps'])};{JS}</script></body></html>")
            pg.set_content(doc); pg.wait_for_timeout(250)
            pg.evaluate("document.getAnimations().forEach(a=>a.pause())")
            nf = int(round(sc["dur"] * FPS))
            shot = max(0, int((sc["dur"] - 0.45) * FPS)) if not (nxt and nxt["wipe"]) else max(0, int((sc["dur"] - 0.4) * FPS))
            for fi in range(nf):
                ms = fi * 1000 / FPS
                pg.evaluate(f"document.getAnimations().forEach(a=>a.currentTime={ms});window.__tick({ms})")
                f = tmp / f"f{idx:05d}.jpg"
                pg.screenshot(path=str(f), type="jpeg", quality=92)
                if fi == min(nf - 1, shot): shutil.copy(f, chk / f"escena{si + 1}.jpg")
                idx += 1
        # portada: escena elegida, todo visible y sin subtítulo
        cs = data.get("cover_scene", 0); sc = plan[cs]
        doc = (f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body style='--start:0s;--outd:999s'>"
               f"<div class='glow'></div>{WAVES}<div class='foot'>{HANDLE}</div><div class='wrap'>{sc['html']}</div>"
               f"<div class='cap' id='cap'></div><script>window.__caps=[];{JS}</script></body></html>")
        pg.set_content(doc); pg.wait_for_timeout(250)
        pg.evaluate("document.getAnimations().forEach(a=>{a.pause();a.currentTime=60000});window.__tick(60000)")
        pg.screenshot(path=str(out / "cover.jpg"), type="jpeg", quality=92)
        b.close()

    # audio: voz + música de fondo bajita
    n = int(total * SR) + SR
    v = np.zeros(n, dtype=np.float32)
    for t0, a in track:
        i = int(t0 * SR); v[i:i + len(a)] += a[: n - i]
    v = v / max(1e-6, np.abs(v).max()) * 0.9
    vw = out / "_voz.wav"
    with wave.open(str(vw), "w") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes((v * 32767).astype("<i2").tobytes())
    mw = out / "_music.wav"; music(mw, total)
    mp4 = out / "reel.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", str(tmp / "f%05d.jpg"),
                    "-i", str(vw), "-i", str(mw), "-filter_complex",
                    "[1:a]aresample=44100,volume=1.0[v];[2:a]volume=0.13[m];[v][m]amix=inputs=2:duration=first:normalize=0,"
                    "acompressor=threshold=0.3:ratio=3,loudnorm=I=-14:TP=-1.5[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
                    "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "160k", "-ar", "44100",
                    "-t", f"{total:.2f}", "-movflags", "+faststart", str(mp4)], check=True)
    shutil.rmtree(tmp); vw.unlink(); mw.unlink()
    print("ok", mp4, f"{total:.1f}s", idx, "frames")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
