"""Genera un carrusel de Instagram (1080x1350) a partir de un JSON.
Uso: python3 render.py contenido.json carpeta_salida
"""
import json, sys, pathlib, html
from playwright.sync_api import sync_playwright

BG, TXT, AZUL, VERDE = "#F5F7FA", "#111827", "#2563EB", "#10B981"
HANDLE = "@josealfredomatias1"

CSS = f"""
*{{margin:0;padding:0;box-sizing:border-box}}
body{{width:1080px;height:1350px;background:{BG};color:{TXT};
 font-family:'Poppins','Inter',sans-serif;overflow:hidden;position:relative}}
.wrap{{position:absolute;inset:0;padding:96px 88px 150px;display:flex;flex-direction:column}}
.tag{{display:inline-flex;align-items:center;gap:14px;font:600 30px 'Inter';letter-spacing:.06em;
 text-transform:uppercase;color:{AZUL};margin-bottom:40px}}
.tag i{{width:18px;height:18px;border-radius:50%;background:{VERDE};display:inline-block}}
h1{{font:700 104px/1.05 'Poppins';letter-spacing:-.02em}}
h2{{font:700 76px/1.1 'Poppins';letter-spacing:-.015em;margin-bottom:44px}}
p{{font:400 44px/1.45 'Inter';color:#1F2937}}
p+p{{margin-top:28px}}
b{{color:{AZUL};font-weight:700}}
.sub{{font:500 46px/1.35 'Inter';color:#374151;margin-top:36px}}
.foot{{position:absolute;left:88px;right:88px;bottom:64px;display:flex;justify-content:space-between;
 align-items:center;font:600 30px 'Inter';color:#4B5563}}
.brand{{display:flex;align-items:center;gap:16px}}
.av{{width:58px;height:58px;border-radius:50%;background:{AZUL};color:#fff;display:grid;place-items:center;
 font:700 26px 'Poppins'}}
.dots{{display:flex;gap:10px}} .dots span{{width:14px;height:14px;border-radius:50%;background:#D1D5DB}}
.dots span.on{{background:{AZUL};width:40px;border-radius:8px}}
.art{{flex:1;display:flex;align-items:center;justify-content:center}}
.big{{font:800 210px/1 'Poppins';color:{AZUL};letter-spacing:-.04em}}
.big small{{font-size:90px;vertical-align:top;margin-right:6px}}
.card{{background:#fff;border-radius:36px;padding:44px 48px;box-shadow:0 10px 40px rgba(17,24,39,.07);margin-top:36px}}
.card p{{font-size:40px}}
.row{{display:flex;gap:28px;margin-top:36px}}
.pill{{flex:1;background:#fff;border-radius:30px;padding:34px 30px;box-shadow:0 10px 40px rgba(17,24,39,.07)}}
.pill .n{{font:800 64px/1 'Poppins';color:{VERDE}}}
.pill .l{{font:500 32px/1.3 'Inter';color:#374151;margin-top:12px}}
.cta{{margin-top:auto;background:{AZUL};color:#fff;border-radius:999px;padding:30px 48px;
 font:700 44px 'Poppins';align-self:flex-start;display:flex;gap:18px;align-items:center}}
.cta i{{width:22px;height:22px;border-radius:50%;background:{VERDE};display:inline-block}}
"""

def foot(i, n):
    dots = "".join(f'<span class="{"on" if k == i else ""}"></span>' for k in range(n))
    return (f'<div class="foot"><div class="brand"><div class="av">JA</div>{HANDLE}</div>'
            f'<div class="dots">{dots}</div></div>')

def page(body, i, n):
    return f"<html><head><meta charset='utf-8'><style>{CSS}</style></head><body><div class='wrap'>{body}</div>{foot(i, n)}</body></html>"

def main(src, out):
    data = json.loads(pathlib.Path(src).read_text())
    out = pathlib.Path(out); out.mkdir(parents=True, exist_ok=True)
    slides = data["slides"]
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1080, "height": 1350})
        for i, s in enumerate(slides):
            pg.set_content(page(s["html"], i, len(slides)))
            pg.wait_for_timeout(150)
            pg.screenshot(path=str(out / f"slide{i+1}.png"))
        b.close()
    print("ok", len(slides))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
