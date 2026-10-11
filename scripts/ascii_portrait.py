"""Turn a photo into an animated "terminal" SVG where the ASCII portrait
assembles itself, followed by a neofetch-style info panel.

usage: python scripts/ascii_portrait.py <photo> [out.svg]

If `rembg` is installed the background is removed first (recommended).
"""
import random
import sys
from html import escape

from PIL import Image, ImageFilter, ImageOps

COLS = 76
CELL_W, CELL_H = 6.0, 10.2  # monospace cell at font-size 10
RAMP = " .'`^,:;-~+=*!ri?7tfjlcxzvunoaeswmdbpqkhAZXO0Q#%&8B@$"
GROUPS = 24  # number of reveal waves
SHADES = 7  # brightness levels, dim -> bright
SHADE_FILL = ["#1f5130", "#2e6d40", "#3f8a52", "#57a866", "#7cc483", "#a6e3a1", "#e2ffdc"]
FORM_START, FORM_DUR = 1.4, 3.2  # seconds


def load_subject(path):
    im = Image.open(path).convert("RGBA")
    try:
        from rembg import remove  # noqa: optional dependency
        im = remove(im)
    except ImportError:
        pass
    alpha = im.getchannel("A").point(lambda a: 255 if a > 40 else 0)
    l, t, r, b = alpha.getbbox()
    # centre a head-and-shoulders crop on the head (top of the silhouette)
    head = alpha.crop((l, t, r, t + (b - t) // 6)).getbbox()
    cx = l + (head[0] + head[2]) // 2
    bottom = t + int((b - t) * 0.6)
    half = int((bottom - t) * 0.56)
    left = max(l, min(cx - half, r - 2 * half))
    im = im.crop((left, t, min(r, left + 2 * half), bottom))
    flat = Image.new("RGBA", im.size, (0, 0, 0, 255))
    flat.alpha_composite(im)
    flat.putalpha(im.getchannel("A"))
    return flat


def to_ascii(im):
    w, h = im.size
    rows = round(COLS * (h / w) * (CELL_W / CELL_H))
    small = im.resize((COLS, rows), Image.LANCZOS)
    alpha = small.getchannel("A")
    # equalise over the subject only so the face keeps its detail
    big_alpha = im.getchannel("A").point(lambda a: 255 if a > 90 else 0)
    base = ImageOps.autocontrast(im.convert("RGB").convert("L"), cutoff=1)
    gray = Image.blend(base, ImageOps.equalize(base, mask=big_alpha), 0.45)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=4, percent=120)).resize((COLS, rows), Image.LANCZOS)
    edges = small.convert("L").filter(ImageFilter.FIND_EDGES)
    grid = []
    for y in range(rows):
        row = []
        for x in range(COLS):
            a = alpha.getpixel((x, y))
            if a < 90:
                row.append((" ", 0))
                continue
            v = gray.getpixel((x, y)) / 255
            v = max(v, min(edges.getpixel((x, y)) / 255 * 1.5, 0.4))
            v = 0.1 + 0.9 * v ** 1.15  # keep dark shirt/hair visible
            ch = RAMP[min(int(v * (len(RAMP) - 1)), len(RAMP) - 1)]
            row.append((ch, min(SHADES - 1, int(v * SHADES))))
        grid.append(row)
    return grid


def portrait_svg(grid, ox, oy, rng):
    rows, cols = len(grid), len(grid[0])
    cy, cx = rows * 0.35, cols / 2
    groups = [[[] for _ in range(SHADES)] for _ in range(GROUPS)]
    noise = []
    for y, row in enumerate(grid):
        for x, (ch, lv) in enumerate(row):
            if ch == " ":
                continue
            # waves sweep from top + spread out from the face, with jitter
            d = (y / rows) * 0.55 + (((x - cx) ** 2 + ((y - cy) * 1.6) ** 2) ** 0.5 / cols) * 0.45
            g = min(GROUPS - 1, max(0, int((d + rng.uniform(-0.18, 0.18)) * GROUPS)))
            groups[g][lv].append((x, y, ch))
            if rng.random() < 0.55:
                noise.append((x, y, rng.choice("01#$%&@*+=/\\<>{}[]")))

    def text(cells, cls, style=""):
        xs = " ".join(f"{ox + x * CELL_W:.1f}" for x, _, _ in cells)
        ys = " ".join(f"{oy + y * CELL_H:.1f}" for _, y, _ in cells)
        s = escape("".join(c for _, _, c in cells))
        st = f' style="{style}"' if style else ""
        return f'<text class="{cls}" x="{xs}" y="{ys}"{st}>{s}</text>'

    out = [text(noise, "noise")]
    for i, shades in enumerate(groups):
        delay = FORM_START + FORM_DUR * i / GROUPS
        for lv, cells in enumerate(shades):
            if cells:
                out.append(text(cells, f"px s{lv}", f"animation-delay:{delay:.2f}s"))
    return "\n".join(out)


INFO = [
    ("mark@github", None),
    ("-" * 26, None),
    ("Name", "Mark Ryan Balatero"),
    ("School", "Bohol Island State University"),
    ("Role", "Student · Builder · Tinkerer"),
    ("Vibe", "Problem Solver · Curious · Delusional"),
    ("Mobile", "Kotlin, Flutter, React Native"),
    ("Web", "React, Node.js, Vercel"),
    ("Backend", "Supabase, Firebase, PostgreSQL"),
    ("Hardware", "Arduino, sensors, IoT"),
    ("Langs", "TS, JS, Python, Java, Dart, C++"),
    ("Now", "iPass, CS Hub, PayakApp, SowSmart"),
    ("Hobby", "Playing board games, building nonsense stuff"),
    ("Email", "markryanbalatero5@gmail.com"),
]

PALETTE = ["#1e1e2e", "#f38ba8", "#a6e3a1", "#f9e2af", "#89b4fa", "#cba6f7", "#94e2d5", "#cdd6f4"]


def build(grid):
    rng = random.Random(7)
    rows, cols = len(grid), len(grid[0])
    pad = 22
    top = 40 + 30  # title bar + command line
    art_w, art_h = cols * CELL_W, rows * CELL_H
    info_x = pad + art_w + 34
    W = int(info_x + 440)
    H = int(top + art_h + 46)

    info_start = FORM_START + FORM_DUR + 0.6
    info = []
    y = top + 20
    for i, (k, v) in enumerate(INFO):
        d = info_start + i * 0.18
        if v is None:
            cls = "host" if i == 0 else "dim"
            info.append(f'<text class="ln {cls}" x="{info_x}" y="{y}" style="animation-delay:{d:.2f}s">{escape(k)}</text>')
        else:
            info.append(
                f'<text class="ln" x="{info_x}" y="{y}" style="animation-delay:{d:.2f}s">'
                f'<tspan class="key">{escape(k)}</tspan><tspan class="val" x="{info_x + 72}">{escape(v)}</tspan></text>'
            )
        y += 21
    d = info_start + len(INFO) * 0.18
    y += 8
    for j, c in enumerate(PALETTE):
        info.append(f'<rect class="ln" x="{info_x + j * 26}" y="{y}" width="24" height="14" rx="2" fill="{c}" style="animation-delay:{d:.2f}s"/>')
    y += 42
    end = d + 0.4
    info.append(
        f'<text class="ln" x="{info_x}" y="{y}" style="animation-delay:{end:.2f}s">'
        f'<tspan class="prompt">➜</tspan><tspan class="path"> ~</tspan></text>'
        f'<rect class="cursor" x="{info_x + 36}" y="{y - 12}" width="8" height="15" style="animation-delay:{end:.2f}s"/>'
    )

    shade_css = " ".join(f".s{i} {{ fill: {c}; }}" for i, c in enumerate(SHADE_FILL))
    cmd = f"ascii-render --input mark.jpg --chars {COLS}"
    css = f"""
    text {{ font-family: 'JetBrains Mono','Fira Code','SFMono-Regular',Consolas,'Liberation Mono',Menlo,monospace; font-size: 12px; }}
    .px, .noise {{ font-size: 10px; }}
    .px {{ opacity: 0; animation: form .45s ease-out forwards; }}
    {shade_css}
    .noise {{ fill: #2f6f3f; opacity: 0; animation: flick {FORM_START + FORM_DUR:.2f}s steps(8) forwards; }}
    .title {{ fill: #9399b2; font-size: 12px; }}
    .prompt {{ fill: #a6e3a1; font-weight: bold; }}
    .path {{ fill: #89b4fa; }}
    .cmd {{ fill: #cdd6f4; }}
    .host {{ fill: #a6e3a1; font-weight: bold; font-size: 14px; }}
    .dim {{ fill: #585b70; }}
    .key {{ fill: #89b4fa; font-weight: bold; }}
    .val {{ fill: #cdd6f4; }}
    .ln {{ opacity: 0; animation: show .01s linear forwards; }}
    .cursor {{ fill: #cdd6f4; opacity: 0; animation: show .01s linear forwards, blink 1s step-end infinite; }}
    .typed {{ clip-path: inset(0 100% 0 0); animation: type 1s steps({len(cmd)}) .2s forwards; }}
    @keyframes form {{ 0% {{ opacity: 0; transform: translateY(-3px); }} 100% {{ opacity: 1; transform: none; }} }}
    @keyframes flick {{ 0% {{ opacity: 0; }} 10% {{ opacity: .9; }} 30% {{ opacity: .3; }} 50% {{ opacity: .8; }} 70% {{ opacity: .4; }} 100% {{ opacity: 0; }} }}
    @keyframes show {{ to {{ opacity: 1; }} }}
    @keyframes blink {{ 50% {{ fill: transparent; }} }}
    @keyframes type {{ to {{ clip-path: inset(0 0 0 0); }} }}
    """
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" aria-label="Animated ASCII portrait of Mark Ryan Balatero in a terminal window">
<style>{css}</style>
<rect width="{W}" height="{H}" rx="12" fill="#11111b"/>
<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="11" fill="#1e1e2e" stroke="#313244"/>
<path d="M1 12 a11 11 0 0 1 11 -11 H{W - 12} a11 11 0 0 1 11 11 V34 H1 Z" fill="#181825"/>
<circle cx="22" cy="18" r="6" fill="#f38ba8"/><circle cx="42" cy="18" r="6" fill="#f9e2af"/><circle cx="62" cy="18" r="6" fill="#a6e3a1"/>
<text class="title" x="{W / 2}" y="22" text-anchor="middle">mark@github: ~/profile — zsh</text>
<text x="{pad}" y="58"><tspan class="prompt">➜</tspan><tspan class="path"> ~/profile </tspan></text>
<text class="cmd typed" x="{pad + 94}" y="58">{escape(cmd)}</text>
{portrait_svg(grid, pad, top + 8, rng)}
{"".join(info)}
</svg>
"""


if __name__ == "__main__":
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else "assets/terminal-portrait.svg"
    grid = to_ascii(load_subject(src))
    with open(dst, "w", encoding="utf-8") as f:
        f.write(build(grid))
    print("\n".join("".join(c for c, _ in r) for r in grid))
    print(f"wrote {dst}")
