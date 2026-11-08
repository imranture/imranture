#!/usr/bin/env python3
"""Generate the animated pixel-art profile assets.

Writes into assets/:
  banner.svg            animated room scene (clouds, commit log, steam, sleeping cat)
  stats.svg             commits / pull requests / stars / best streak strip
  projects-heading.svg  "> PROJECTS" heading
  project-1..4.svg      one card per featured repository
and rewrites the block between <!-- PROJECTS:START --> and <!-- PROJECTS:END --> in README.md.

Standard library only, so the GitHub Action needs no installs.

Usage:
  GH_TOKEN=... GH_USER=you python scripts/generate.py   # real data
  python scripts/generate.py --demo                     # sample data, no network
"""

import hashlib
import json
import math
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
CONFIG = ROOT / "profile.config.json"
README = ROOT / "README.md"

MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

# --------------------------------------------------------------------------- #
# 5x7 pixel font
# --------------------------------------------------------------------------- #
_F = {
    "A": [" ### ", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "B": ["#### ", "#   #", "#   #", "#### ", "#   #", "#   #", "#### "],
    "C": [" ### ", "#   #", "#    ", "#    ", "#    ", "#   #", " ### "],
    "D": ["#### ", "#   #", "#   #", "#   #", "#   #", "#   #", "#### "],
    "E": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#####"],
    "F": ["#####", "#    ", "#    ", "#### ", "#    ", "#    ", "#    "],
    "G": [" ### ", "#   #", "#    ", "# ###", "#   #", "#   #", " ####"],
    "H": ["#   #", "#   #", "#   #", "#####", "#   #", "#   #", "#   #"],
    "I": [" ### ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "J": ["  ###", "   # ", "   # ", "   # ", "   # ", "#  # ", " ##  "],
    "K": ["#   #", "#  # ", "# #  ", "##   ", "# #  ", "#  # ", "#   #"],
    "L": ["#    ", "#    ", "#    ", "#    ", "#    ", "#    ", "#####"],
    "M": ["#   #", "## ##", "# # #", "# # #", "#   #", "#   #", "#   #"],
    "N": ["#   #", "##  #", "# # #", "#  ##", "#   #", "#   #", "#   #"],
    "O": [" ### ", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "P": ["#### ", "#   #", "#   #", "#### ", "#    ", "#    ", "#    "],
    "Q": [" ### ", "#   #", "#   #", "#   #", "# # #", "#  # ", " ## #"],
    "R": ["#### ", "#   #", "#   #", "#### ", "# #  ", "#  # ", "#   #"],
    "S": [" ####", "#    ", "#    ", " ### ", "    #", "    #", "#### "],
    "T": ["#####", "  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "  #  "],
    "U": ["#   #", "#   #", "#   #", "#   #", "#   #", "#   #", " ### "],
    "V": ["#   #", "#   #", "#   #", "#   #", "#   #", " # # ", "  #  "],
    "W": ["#   #", "#   #", "#   #", "# # #", "# # #", "# # #", " # # "],
    "X": ["#   #", "#   #", " # # ", "  #  ", " # # ", "#   #", "#   #"],
    "Y": ["#   #", "#   #", " # # ", "  #  ", "  #  ", "  #  ", "  #  "],
    "Z": ["#####", "    #", "   # ", "  #  ", " #   ", "#    ", "#####"],
    "0": [" ### ", "#   #", "#  ##", "# # #", "##  #", "#   #", " ### "],
    "1": ["  #  ", " ##  ", "  #  ", "  #  ", "  #  ", "  #  ", " ### "],
    "2": [" ### ", "#   #", "    #", "   # ", "  #  ", " #   ", "#####"],
    "3": ["#####", "   # ", "  #  ", "   # ", "    #", "#   #", " ### "],
    "4": ["   # ", "  ## ", " # # ", "#  # ", "#####", "   # ", "   # "],
    "5": ["#####", "#    ", "#### ", "    #", "    #", "#   #", " ### "],
    "6": ["  ## ", " #   ", "#    ", "#### ", "#   #", "#   #", " ### "],
    "7": ["#####", "    #", "   # ", "  #  ", " #   ", " #   ", " #   "],
    "8": [" ### ", "#   #", "#   #", " ### ", "#   #", "#   #", " ### "],
    "9": [" ### ", "#   #", "#   #", " ####", "    #", "   # ", " ##  "],
    "-": ["     ", "     ", "     ", " ### ", "     ", "     ", "     "],
    ".": ["     ", "     ", "     ", "     ", "     ", "     ", "  #  "],
    "_": ["     ", "     ", "     ", "     ", "     ", "     ", "#####"],
    ">": ["#    ", " #   ", "  #  ", "   # ", "  #  ", " #   ", "#    "],
    "/": ["    #", "    #", "   # ", "  #  ", " #   ", "#    ", "#    "],
    "!": ["  #  ", "  #  ", "  #  ", "  #  ", "  #  ", "     ", "  #  "],
    "'": ["  #  ", "  #  ", "     ", "     ", "     ", "     ", "     "],
    "(": ["   # ", "  #  ", " #   ", " #   ", " #   ", "  #  ", "   # "],
    ")": [" #   ", "  #  ", "   # ", "   # ", "   # ", "  #  ", " #   "],
    "&": [" ##  ", "#  # ", "# #  ", " #   ", "# # #", "#  # ", " ## #"],
    "+": ["     ", "  #  ", "  #  ", "#####", "  #  ", "  #  ", "     "],
    " ": ["     "] * 7,
}


def pixel_text_prepare(text):
    """Uppercase and strip accents so names like 'Türe' render as 'TURE'."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).upper()
    return "".join(c if c in _F else " " for c in text)


def pixel_text_width(text, s, gap=1):
    n = len(pixel_text_prepare(text))
    return 0 if n == 0 else (n * (5 + gap) - gap) * s


def pixel_text(text, x, y, s, fill, gap=1, extra=""):
    """Render text as a single <path> of s x s squares. (x, y) is the top-left."""
    d = []
    cx = x
    for ch in pixel_text_prepare(text):
        for row, line in enumerate(_F[ch]):
            col = 0
            while col < 5:
                if line[col] == "#":
                    start = col
                    while col < 5 and line[col] == "#":
                        col += 1
                    w = (col - start) * s
                    d.append(f"M{cx + start * s} {y + row * s}h{w}v{s}h{-w}z")
                else:
                    col += 1
        cx += (5 + gap) * s
    return f'<path d="{"".join(d)}" fill="{fill}" {extra}/>'


# --------------------------------------------------------------------------- #
# small SVG helpers
# --------------------------------------------------------------------------- #
def r(x, y, w, h, fill, extra=""):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}" {extra}/>'


def pixmap(rows, x, y, u, palette):
    """Draw a character grid. Each char maps to a colour in palette ('.' = empty)."""
    out = []
    for j, line in enumerate(rows):
        i = 0
        while i < len(line):
            c = line[i]
            if c in palette:
                start = i
                while i < len(line) and line[i] == c:
                    i += 1
                out.append(r(x + start * u, y + j * u, (i - start) * u, u, palette[c]))
            else:
                i += 1
    return "".join(out)


def pixel_disc(cx, cy, radius, u, fill):
    out = []
    y = -radius
    while y < radius:
        mid = y + u / 2
        half = math.sqrt(max(radius * radius - mid * mid, 0))
        half = round(half / u) * u
        if half > 0:
            out.append(r(cx - half, cy + y, 2 * half, u, fill))
        y += u
    return "".join(out)


def fmt_num(n):
    if n >= 10000:
        return f"{n / 1000:.0f}K"
    if n >= 1000:
        return f"{n / 1000:.1f}K".replace(".0K", "K")
    return str(n)


def shade(hex_color, f):
    """f < 1 darkens, f > 1 lightens."""
    h = hex_color.lstrip("#")
    rgb = [int(h[i:i + 2], 16) for i in (0, 2, 4)]
    if f <= 1:
        rgb = [int(c * f) for c in rgb]
    else:
        rgb = [int(c + (255 - c) * (f - 1)) for c in rgb]
    return "#" + "".join(f"{max(0, min(255, c)):02x}" for c in rgb)


def svg_doc(w, h, body, style="", title="", defs=""):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" '
        f'viewBox="0 0 {w} {h}" shape-rendering="crispEdges" role="img" '
        f'aria-label="{escape(title)}"><title>{escape(title)}</title>'
        f"<defs>{defs}</defs><style>{style}"
        "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
        f"</style>{body}</svg>"
    )


# --------------------------------------------------------------------------- #
# Banner scene (880 x 440)
# --------------------------------------------------------------------------- #
W, H = 880, 440
FLOOR_Y = 360


def scene_banner(data):
    name = data["display_name"]
    commits = data["commits"]
    books = data["books"]

    style = """
    .cloud{animation:drift linear infinite}
    @keyframes drift{from{transform:translateX(-90px)}to{transform:translateX(250px)}}
    .steam{animation:steam 3s steps(8) infinite;opacity:0}
    @keyframes steam{0%{transform:translateY(0);opacity:0}25%{opacity:.75}100%{transform:translateY(-30px);opacity:0}}
    .zz{animation:zz 4.5s steps(9) infinite;opacity:0}
    @keyframes zz{0%{transform:translate(0,0);opacity:0}20%{opacity:1}80%{opacity:.8}100%{transform:translate(18px,-36px);opacity:0}}
    .tail{transform-box:fill-box;transform-origin:100% 100%;animation:wag 2.4s steps(2) infinite}
    @keyframes wag{0%,60%{transform:rotate(0)}70%,90%{transform:rotate(-14deg)}}
    .breathe{animation:breathe 3.2s steps(2) infinite}
    @keyframes breathe{0%,100%{transform:translateY(0)}50%{transform:translateY(-2px)}}
    .led{animation:led 1.3s steps(1) infinite}
    @keyframes led{0%,30%,55%{opacity:1}20%,45%,80%{opacity:.15}}
    .gpu{animation:gpu 2.6s ease-in-out infinite}
    @keyframes gpu{0%,100%{opacity:.55}50%{opacity:1}}
    .neon{animation:flicker 7s infinite}
    @keyframes flicker{0%,18%,22%,24%,100%{opacity:1}20%,23%{opacity:.35}}
    .sec{transform-box:view-box;transform-origin:88px 100px;animation:spin 60s steps(60) infinite}
    .min{transform-box:view-box;transform-origin:88px 100px;animation:spin 3600s linear infinite}
    @keyframes spin{to{transform:rotate(360deg)}}
    """

    defs = """
    <pattern id="wp" width="32" height="32" patternUnits="userSpaceOnUse">
      <rect width="32" height="32" fill="#26213a"/>
      <rect x="14" y="14" width="4" height="4" fill="#2f2948"/>
      <rect x="0" y="0" width="4" height="4" fill="#2a2440"/>
    </pattern>
    <clipPath id="glass"><rect x="636" y="76" width="188" height="148"/></clipPath>
    <clipPath id="term"><rect x="272" y="134" width="226" height="108"/></clipPath>
    <filter id="glow" x="-20%" y="-60%" width="140%" height="220%">
      <feGaussianBlur stdDeviation="3" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <radialGradient id="lampglow"><stop offset="0" stop-color="#ffd96b" stop-opacity=".22"/>
      <stop offset="1" stop-color="#ffd96b" stop-opacity="0"/></radialGradient>
    """

    b = []
    # wall, baseboard, floor
    b.append(r(0, 0, W, FLOOR_Y, "url(#wp)"))
    b.append(r(0, FLOOR_Y - 10, W, 10, "#3a3150"))
    b.append(r(0, FLOOR_Y - 12, W, 2, "#4a4066"))
    for i, yy in enumerate(range(FLOOR_Y, H, 20)):
        b.append(r(0, yy, W, 20, "#5b3a29" if i % 2 == 0 else "#553626"))
        b.append(r(0, yy, W, 2, "#4a2f21"))
        off = 0 if i % 2 == 0 else 70
        for sx in range(off + 40, W, 140):
            b.append(r(sx, yy, 2, 20, "#4a2f21"))

    b.append(_carpet())

    # cat's bed
    b.append(r(652, 380, 120, 28, "#7a3b52"))
    b.append(r(644, 384, 136, 20, "#7a3b52"))
    b.append(r(656, 388, 112, 4, "#9b4d68"))
    b.append(r(656, 396, 112, 2, "#9b4d68"))
    for fx in range(646, 778, 8):
        b.append(r(fx, 408, 4, 4, "#c7a27a"))

    b.append(_bookcase(books))
    b.append(_clock())
    b.append(_sign(name))
    b.append(_window())
    b.append(_desk_and_monitor(commits))
    b.append(_cat())

    body = "".join(b)
    return svg_doc(W, H, body, style, f"{name}'s pixel room", defs)


def _carpet():
    """Kilim-style carpet in the middle of the floor."""
    w, h = 280, 52
    x0, y0 = (196 + 572) // 2 - w // 2, 376   # centred under the desk (desk spans x 196-572)
    b = [
        r(x0, y0, w, h, "#6e2828"),                      # outer edge
        r(x0 + 4, y0 + 4, w - 8, h - 8, "#d9a441"),      # mustard border
        r(x0 + 8, y0 + 8, w - 16, h - 16, "#a13d3d"),    # red field
    ]
    # teal notches along the border
    for nx in range(x0 + 12, x0 + w - 12, 16):
        b.append(r(nx, y0 + 4, 4, 4, "#2f6f73"))
        b.append(r(nx + 8, y0 + h - 8, 4, 4, "#2f6f73"))
    # thin cream frame inside the field
    fx0, fy0, fw, fh = x0 + 12, y0 + 12, w - 24, h - 24
    b += [r(fx0, fy0, fw, 2, "#efe6d2"), r(fx0, fy0 + fh - 2, fw, 2, "#efe6d2"),
          r(fx0, fy0, 2, fh, "#efe6d2"), r(fx0 + fw - 2, fy0, 2, fh, "#efe6d2")]
    # row of diamonds with dots between
    diamond = ["..t..", ".tct.", "tcmct", ".tct.", "..t.."]
    pal = {"t": "#2f6f73", "c": "#efe6d2", "m": "#d9a441"}
    cy = y0 + h // 2
    centers = [x0 + w // 2 + k * 50 for k in (-2, -1, 0, 1, 2)]
    for cx in centers:
        b.append(pixmap(diamond, cx - 10, cy - 10, 4, pal))
    for a, c in zip(centers, centers[1:]):
        b.append(r((a + c) // 2 - 2, cy - 2, 4, 4, "#d9a441"))
    # fringe on both ends
    for fy in range(y0 + 2, y0 + h - 2, 6):
        b.append(r(x0 - 8, fy, 8, 2, "#efe6d2"))
        b.append(r(x0 + w, fy, 8, 2, "#efe6d2"))
    return "".join(b)


def _luma(hex_color):
    h = hex_color.lstrip("#")
    r_, g_, b_ = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return 0.2126 * r_ + 0.7152 * g_ + 0.0722 * b_


def _bookcase(books):
    """Bookcase whose books carry the names of the technologies you use on their spines."""
    b = []
    x0, y0, w = 20, 136, 156
    h = FLOOR_Y - y0
    b.append(r(x0, y0, w, h, "#6b4430"))
    b.append(r(x0 + 8, y0 + 8, w - 16, h - 8, "#3e271b"))
    b.append(r(x0 - 4, y0 - 4, w + 8, 8, "#7d5139"))
    shelves = [y0 + 74, y0 + 144, y0 + 214]          # bottom edge of each row of books
    for sy in shelves:
        b.append(r(x0 + 8, sy, w - 16, 6, "#7d5139"))

    heights = [56, 50, 60, 52, 58, 48, 54, 50]
    bw, gap = 14, 2
    per_shelf = (w - 24) // (bw + gap)
    rows = [books[i:i + per_shelf] for i in range(0, len(books), per_shelf)][: len(shelves)]
    k = 0
    last_x = {}
    for shelf_i, row in enumerate(rows):
        bx = x0 + 12
        for book in row:
            name = book["name"]
            est = len(name) * 4.6                      # rough width of the spine text
            bh = min(60, max(heights[k % len(heights)], int(est) + 16))
            k += 1
            col = book.get("color") or "#8b949e"
            top = shelves[shelf_i] - bh
            b.append(r(bx, top, bw, bh, col))
            b.append(r(bx, top, bw, 2, shade(col, 1.35)))
            b.append(r(bx, shelves[shelf_i] - 8, bw, 2, shade(col, 0.7)))
            b.append(r(bx + bw - 2, top, 2, bh, shade(col, 0.8)))
            # spine title, reading top to bottom; squeezed only if it would not fit
            avail = bh - 14
            fit = f' textLength="{avail}" lengthAdjust="spacingAndGlyphs"' if est > avail else ""
            ink = "#1b2130" if _luma(col) > 0.6 else "#f5f1e8"
            cx = bx + (bw - 2) / 2
            cy = top + 4 + avail / 2
            b.append(
                f'<text transform="translate({cx:.1f} {cy:.1f}) rotate(90)" text-anchor="middle" '
                f'dominant-baseline="central" font-family="{SANS}" font-size="7.5" font-weight="700" '
                f'fill="{ink}"{fit}>{escape(name)}</text>'
            )
            bx += bw + gap
        last_x[shelf_i] = bx

    def free(shelf_i):
        return x0 + w - 12 - last_x.get(shelf_i, x0 + 12)

    # fill leftover space with props, only where they fit
    sx = last_x.get(0, x0 + 12)
    if free(0) >= 20:
        b.append(f'<g transform="rotate(14 {sx + 8} {shelves[0]})">'
                 + r(sx + 2, shelves[0] - 48, 12, 48, "#58627a") + "</g>")
    if free(1) >= 30:
        px = x0 + w - 12 - 28
        b.append(r(px, shelves[1] - 16, 24, 16, "#c0714f"))
        b.append(r(px, shelves[1] - 16, 24, 4, "#d88a64"))
        b.append(pixmap(["..g..", ".ggg.", "ggggg", ".g.g."], px + 2, shelves[1] - 32, 4,
                        {"g": "#58a65c"}))
    if 1 not in last_x:
        stack = ["#4f8a8b", "#b5566a", "#d9a441", "#5c6bc0"]
        for i, c in enumerate(stack):
            b.append(r(x0 + 14 + (i % 2) * 2, shelves[1] - 8 * (i + 1), 44, 8, c))
            b.append(r(x0 + 14 + (i % 2) * 2, shelves[1] - 8 * (i + 1), 4, 8, shade(c, 0.75)))
    if free(2) >= 48:
        cx = x0 + w - 12 - 44
        b.append(r(cx, shelves[2] - 28, 40, 28, "#8a6a4a"))
        b.append(r(cx, shelves[2] - 16, 40, 2, "#6b4f36"))
    return "".join(b)


def _clock():
    cx, cy = 88, 100
    b = [pixel_disc(cx, cy, 28, 4, "#1a1626"), pixel_disc(cx, cy, 24, 4, "#efe6d2")]
    for a in range(0, 360, 90):
        px = cx + round(math.sin(math.radians(a)) * 18 / 2) * 2
        py = cy - round(math.cos(math.radians(a)) * 18 / 2) * 2
        b.append(r(px - 2, py - 2, 4, 4, "#8a7f6a"))
    b.append(f'<g class="min">{r(cx - 2, cy - 18, 4, 18, "#2b2541")}</g>')
    b.append(f'<g transform="rotate(120 {cx} {cy})">{r(cx - 2, cy - 12, 4, 12, "#2b2541")}</g>')
    b.append(f'<g class="sec">{r(cx - 1, cy - 20, 2, 20, "#d9534f")}</g>')
    b.append(r(cx - 3, cy - 3, 6, 6, "#2b2541"))
    return "".join(b)


def _sign(name):
    max_w, cx = 372, 384
    s = 6
    while s > 2 and pixel_text_width(name, s) > max_w:
        s -= 1
    tw = pixel_text_width(name, s)
    th = 7 * s
    pad_x, pad_y = 22, 12
    bw, bh = tw + 2 * pad_x, th + 2 * pad_y
    bx, by = cx - bw // 2, 22          # leaves ~18px between the sign and the monitor
    b = [
        # hanging wires
        r(bx + 24, 0, 2, by, "#4a4066"), r(bx + bw - 26, 0, 2, by, "#4a4066"),
        r(bx - 4, by - 4, bw + 8, bh + 8, "#141120"),
        r(bx, by, bw, bh, "#1d1830"),
        r(bx, by, bw, 2, "#2b2541"),
    ]
    b.append(
        f'<g class="neon" filter="url(#glow)">'
        + pixel_text(name, bx + pad_x, by + pad_y, s, "#5ce1e6")
        + "</g>"
    )
    return "".join(b)


def _window():
    x0, y0, w, h = 628, 68, 204, 164
    b = [r(x0, y0, w, h, "#e8dcc4")]
    gx, gy, gw, gh = 636, 76, 188, 148
    sky = [r(gx, gy, gw, gh, "#8fb8de"), r(gx, gy + 90, gw, 58, "#a9c9e6")]
    sky.append(pixel_disc(790, 106, 16, 4, "#ffe08a"))
    # skyline
    for bx, bw2, bh2 in [(636, 28, 34), (664, 20, 50), (684, 32, 28), (716, 24, 44),
                          (740, 36, 30), (776, 20, 56), (796, 28, 38)]:
        sky.append(r(bx, gy + gh - bh2, bw2, bh2, "#6f8fb5"))
        for wy in range(gy + gh - bh2 + 6, gy + gh - 4, 10):
            for wx in range(bx + 4, bx + bw2 - 4, 8):
                sky.append(r(wx, wy, 4, 4, "#86a5c8"))
    # clouds
    cloud_shapes = [
        ["..####....", ".#######..", "##########"],
        ["...###.", ".######", "#######"],
        [".#####...", "#########"],
    ]
    clouds = [(0, 92, 34, -4), (1, 120, 46, -26), (2, 104, 40, -15), (1, 84, 52, -40)]
    for shape_i, cy, dur, delay in clouds:
        sky.append(
            f'<g class="cloud" style="animation-duration:{dur}s;animation-delay:{delay}s">'
            + pixmap(cloud_shapes[shape_i], gx, cy, 6, {"#": "#ffffff"})
            + "</g>"
        )
    b.append(f'<g clip-path="url(#glass)">{"".join(sky)}</g>')
    # mullions
    b.append(r(gx + gw // 2 - 2, gy, 4, gh, "#e8dcc4"))
    b.append(r(gx, gy + gh // 2 - 2, gw, 4, "#e8dcc4"))
    # sill
    b.append(r(x0 - 10, y0 + h, w + 20, 8, "#7d5139"))
    b.append(r(x0 - 6, y0 + h + 8, w + 12, 4, "#5b3a29"))
    # cactus on sill
    b.append(pixmap(["..g..", ".gg.g", "g.g.g", "ggggg", "..g..", "..g.."], 800, y0 + h - 30, 4,
                    {"g": "#4f9a58"}))
    b.append(r(796, y0 + h - 8, 28, 8, "#c0714f"))
    # curtains + rod
    b.append(r(x0 - 22, y0 - 16, w + 44, 4, "#a08868"))
    for side in (x0 - 18, x0 + w - 6):
        b.append(r(side, y0 - 12, 24, h + 28, "#b4495f"))
        b.append(r(side + 8, y0 - 12, 4, h + 28, "#93394d"))
        b.append(r(side + 18, y0 - 12, 2, h + 28, "#93394d"))
    return "".join(b)


def short_repo(name, max_len=12):
    """Keep repo names short on the monitor so the commit message stays readable."""
    if name.lower().endswith(".github.io"):
        return "github.io"
    if len(name) > max_len:
        return name[: max_len - 1] + "…"
    return name


def _desk_and_monitor(commits):
    b = []
    # lamp glow
    b.append(f'<circle cx="226" cy="214" r="80" fill="url(#lampglow)" shape-rendering="auto"/>')

    # monitor
    b.append(r(262, 112, 244, 140, "#2e3447"))
    b.append(r(266, 116, 236, 132, "#1b2130"))
    b.append(r(270, 120, 228, 124, "#0d1117"))
    b.append(r(270, 120, 228, 12, "#161b22"))
    for i, c in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        b.append(r(276 + i * 8, 124, 4, 4, c))
    b.append(f'<text x="384" y="129" text-anchor="middle" font-family="{MONO}" font-size="7" '
             f'fill="#6e7681">~/ml — zsh</text>')
    b.append(r(372, 252, 24, 10, "#2e3447"))
    b.append(r(350, 262, 68, 6, "#3a4256"))

    # scrolling git log
    lh = 13
    lines = ['<tspan fill="#79c0ff">$</tspan><tspan fill="#e6edf3"> git log --oneline</tspan>']
    for c in commits:
        sha = escape(c["sha"][:7])
        repo = short_repo(c["repo"])
        msg = c["message"]
        budget = 36 - 8 - len(repo) - 3
        if len(msg) > budget:
            msg = msg[: budget - 1].rstrip() + "…"
        lines.append(
            f'<tspan fill="#e3b341">{sha}</tspan> <tspan fill="#7ee787">({escape(repo)})</tspan> '
            f'<tspan fill="#c9d1d9">{escape(msg)}</tspan>'
        )
    n = len(lines)
    text_rows = []
    for copy in range(2):
        for i, ln in enumerate(lines):
            y = 146 + (copy * n + i) * lh
            text_rows.append(f'<text x="276" y="{y}" xml:space="preserve">{ln}</text>')
    dur = n * 3.0                       # seconds per full loop: slow, continuous scroll
    anim = (f"@keyframes scroll{{from{{transform:translateY(0)}}to{{transform:translateY(-{n * lh}px)}}}}")
    b.append(f"<style>{anim}.log{{animation:scroll {dur:.1f}s linear infinite}}</style>")
    b.append(
        f'<g clip-path="url(#term)"><g class="log" font-family="{MONO}" font-size="9.5" '
        f'shape-rendering="auto">{"".join(text_rows)}</g></g>'
    )
    b.append(r(270, 238, 228, 6, "#0d1117"))

    # desk
    b.append(r(196, 268, 376, 12, "#8a5a3c"))
    b.append(r(196, 268, 376, 2, "#a06c4a"))
    b.append(r(196, 280, 376, 6, "#6b4430"))
    b.append(r(208, 286, 12, FLOOR_Y - 286, "#6b4430"))
    b.append(r(548, 286, 12, FLOOR_Y - 286, "#6b4430"))
    b.append(r(464, 286, 84, 46, "#7d5139"))
    b.append(r(464, 308, 84, 2, "#6b4430"))
    b.append(r(498, 294, 16, 4, "#c7a27a"))
    b.append(r(498, 318, 16, 4, "#c7a27a"))

    # keyboard + mouse
    b.append(r(296, 260, 148, 8, "#3a4256"))
    for kx in range(300, 440, 8):
        b.append(r(kx, 262, 4, 2, "#58627a"))
    b.append(r(454, 262, 10, 6, "#3a4256"))

    # lamp
    b.append(r(208, 262, 32, 6, "#2e3447"))
    b.append(r(222, 214, 4, 48, "#3a4256"))
    b.append(r(206, 200, 40, 16, "#3a4256"))
    b.append(r(206, 200, 40, 4, "#f2c94c"))
    b.append(r(210, 216, 32, 2, "#ffe08a"))

    # Turkish tea: tulip-shaped (ince belli) glass with a spoon, on a white saucer
    b.append(r(513, 264, 34, 2, "#f2f2f2"))           # saucer rim
    b.append(r(516, 266, 28, 2, "#bdbdbd"))           # saucer underside
    glass = [
        ".btttttttttb.",   # flared rim
        ".bwtttttthdb.",
        "..bwtttttdb..",
        "...bttttdb...",   # waist
        "...bttttdb...",
        "...bwtttdb...",
        "..bwhtttddb..",
        ".bwhhttttddb.",   # round belly
        ".bwhhttttddb.",
        ".bwhtttttddb.",
        "..btttttddb..",
        "..ooooooooo..",   # thick glass base
    ]
    gx, gy = 517, 264 - 2 * len(glass)
    b.append(pixmap(glass, gx, gy, 2, {
        "b": "#a9d4fb", "o": "#d6ebff", "t": "#d7322a", "d": "#a3211b",
        "h": "#f07a3c", "w": "#ffffff"}))
    b.append(r(gx + 2, gy - 1, 22, 1, "#d6ebff", 'fill-opacity=".8"'))   # thin rim line
    spoon = [(521, 238), (519, 236), (517, 234), (515, 232)]
    for i, (sx, sy) in enumerate(spoon):
        b.append(r(sx, sy, 2, 2, "#c7ced6" if i == len(spoon) - 1 else "#9aa3ad"))  # spoon handle
    for sx, delay in [(526, 0), (531, -1), (536, -2)]:
        b.append(f'<g class="steam" style="animation-delay:{delay}s">'
                 f'{r(sx, 230, 4, 4, "#d8dee9")}{r(sx + 2, 222, 4, 4, "#d8dee9")}</g>')

    # workstation tower under the desk, busy training
    b.append(r(228, 300, 40, 60, "#2b3040"))
    b.append(r(228, 300, 40, 2, "#3a4256"))
    b.append(r(232, 306, 4, 48, "#1b2130"))
    b.append(f'<g class="gpu">{r(240, 310, 22, 34, "#3d2a6b")}{r(242, 326, 18, 4, "#a371f7")}'
             f'{r(242, 334, 18, 2, "#a371f7")}</g>')
    b.append(r(240, 310, 22, 2, "#4a5470"))
    b.append(r(242, 350, 4, 4, "#3fb950"))
    b.append(f'<g class="led">{r(250, 350, 4, 4, "#e3b341")}</g>')

    b.append(_chair())
    return "".join(b)


def _chair():
    """Ergonomic office chair in side view, facing right toward the desk."""
    shell, body, hi, accent = "#232736", "#3b4157", "#58617f", "#3aa6ab"
    metal, chrome, wheel = "#1b1f2c", "#c3cad6", "#151824"
    b = []
    # backrest: reclines slightly, with a rounded headrest and a lumbar curve
    top, bottom = 246, 308
    for y in range(top, bottom, 2):
        lean = round((bottom - y) * 0.13 / 2) * 2
        i = (y - top) // 2
        width = 16 if i == 0 else 20 if i == 1 else 22
        if 18 <= i <= 25:
            width += 2                                      # lumbar support
        if i == 8:
            width -= 2                                      # neck notch under headrest
        xl = 350 - lean
        b.append(r(xl, y, 2, 2, shell))                     # back shell
        b.append(r(xl + 2, y, width - 4, 2, body))          # cushion
        b.append(r(xl + 2 + (width - 4) // 2, y, (width - 4) - (width - 4) // 2, 2, "#454c66"))
        b.append(r(xl + width - 2, y, 2, 2, hi))            # front highlight
        if 2 <= i <= 27 and i != 8:
            b.append(r(xl + 6, y, 2, 2, accent))            # accent piping
    # seat cushion with rounded front edge
    b.append(r(352, 304, 72, 2, hi))
    b.append(r(348, 306, 80, 10, body))
    b.append(r(428, 308, 2, 6, body))
    b.append(r(350, 316, 76, 2, body))
    b.append(r(354, 318, 68, 4, shell))
    # tilt mechanism and gas lift
    b.append(r(374, 322, 28, 6, metal))
    b.append(r(384, 328, 8, 28, "#8a93a6"))
    b.append(r(386, 328, 2, 14, chrome))
    b.append(r(382, 342, 12, 14, shell))
    # five-star base (side view): hub, two legs, front leg
    b.append(r(378, 354, 20, 6, metal))
    for x, y, w_ in [(366, 356, 12), (356, 358, 10), (398, 356, 12), (410, 358, 10)]:
        b.append(r(x, y, w_, 4, metal))
    # castor wheels
    for wx, wy in [(350, 362), (384, 364), (418, 362)]:
        b.append(r(wx + 2, wy, 6, 10, wheel))
        b.append(r(wx, wy + 2, 10, 6, wheel))
        b.append(r(wx + 4, wy + 4, 2, 2, "#4a5470"))
    return "".join(b)


def _cat():
    u = 4
    x, y = 650, 360
    pal = {"o": "#f0a35e", "s": "#d9844a", "k": "#5a3a2a", "p": "#ff9db0", "w": "#fff3e0"}
    body = [
        "........ooosoooosoooo...",
        "......oooooosoooosooooo.",
        ".....oooooooosoooosooooo",
        ".....ooooooooooooooooooo",
        ".....wwwoooooooooooooooo",
        "......wwwwooooooooooooo.",
    ]
    head = [
        ".o....o.",
        ".oo..oo.",
        "oooooooo",
        "okkoookk",
        "oooopooo",
        ".oooooo.",
        "..wwww..",
    ]
    tail = ["....oo", "...oso", "ooooo.", "sooo.."]
    out = [
        f'<g class="breathe">{pixmap(body, x, y, u, pal)}</g>',
        pixmap(head, x + 2 * u, y - 4 * u, u, pal),
        f'<g class="tail">{pixmap(tail, x + 88, y + 4 * u, u, pal)}</g>',
    ]
    # Zs
    for i, (scale, dx, delay) in enumerate([(2, 0, 0), (3, 10, -1.5), (2, 22, -3)]):
        out.append(
            f'<g class="zz" style="animation-delay:{delay}s">'
            + pixel_text("Z", x + 4 + dx, y - 40 - i * 4, scale, "#c9d1d9")
            + "</g>"
        )
    return "".join(out)


# --------------------------------------------------------------------------- #
# Stats strip
# --------------------------------------------------------------------------- #
ICONS = {
    "commit": ["...##...", "...##...", "..####..", ".##..##.", ".##..##.", "..####..", "...##...", "...##..."],
    "pr": ["##..#...", "##.####.", ".#..#.#.", ".#....#.", ".#....#.", ".#....#.", "##...##.", "##...##."],
    "star": ["...##...", "...##...", "########", ".######.", "..####..", ".##..##.", ".#....#.", "........"],
    "flame": ["....#...", "...##...", "..###.#.", ".######.", ".##.###.", "###..###", ".##..##.", "..####.."],
}


def stats_svg(stats):
    w, h = 880, 104
    items = [
        ("commit", fmt_num(stats["commits"]), "COMMITS", "past 12 months", "#7ee787"),
        ("pr", fmt_num(stats["prs"]), "PULL REQS", "all time", "#a5a2ff"),
        ("star", fmt_num(stats["stars"]), "STARS", "across my repos", "#e3b341"),
        ("flame", str(stats["streak"]), "DAY STREAK", "best, past 12 months", "#ff7b72"),
    ]
    b = [r(1, 1, w - 2, h - 2, "#161b22", 'rx="12" stroke="#30363d" stroke-width="2" shape-rendering="auto"')]
    col_w = (w - 40) // 4
    for i, (icon, num, label, sub, color) in enumerate(items):
        x = 28 + i * col_w
        if i:
            b.append(r(x - 14, 22, 2, h - 44, "#21262d"))
        b.append(pixmap(ICONS[icon], x, 22, 3, {"#": color}))
        b.append(pixel_text(num, x + 36, 18, 5, "#e6edf3"))
        b.append(pixel_text(label, x, 64, 2, "#8b949e"))
        b.append(f'<text x="{x}" y="90" font-family="{MONO}" font-size="10" fill="#6e7681">{sub}</text>')
    return svg_doc(w, h, "".join(b), "", "GitHub stats")


def heading_svg(text="PROJECTS"):
    w, h = 880, 56
    style = ".blink{animation:blink 1.2s steps(1) infinite}@keyframes blink{50%{opacity:0}}"
    s = 4
    tw = pixel_text_width(text, s)
    b = [
        f'<g class="blink">{pixel_text(">", 4, 14, s, "#3fb950")}</g>',
        pixel_text(text, 44, 14, s, "#3fb950"),
    ]
    for x in range(44 + tw + 20, w - 4, 12):
        b.append(r(x, 27, 6, 2, "#30363d"))
    return svg_doc(w, h, "".join(b), style, text.title())


# --------------------------------------------------------------------------- #
# Project cards
# --------------------------------------------------------------------------- #
def identicon(name, x, y, size, color):
    digest = hashlib.sha256(name.encode()).digest()
    n = 7
    cell = size // (n + 1)
    pad = (size - cell * n) // 2
    bg = shade(color, 0.32)
    out = [r(x, y, size, size, bg, 'rx="10" shape-rendering="auto"')]
    bits = "".join(f"{byte:08b}" for byte in digest)
    k = 0
    for row in range(n):
        for col in range(4):
            on = bits[k] == "1"
            tone = shade(color, 1.25) if bits[k + 1] == "1" else color
            k += 2
            if on:
                for c in {col, n - 1 - col}:
                    out.append(r(x + pad + c * cell, y + pad + row * cell, cell, cell, tone))
    return "".join(out)


def wrap(text, width, max_lines):
    words = text.split()
    lines, cur = [], ""
    for w_ in words:
        if len(cur) + len(w_) + (1 if cur else 0) <= width:
            cur = f"{cur} {w_}".strip()
        else:
            if cur:
                lines.append(cur)
            cur = w_[:width]
        if len(lines) == max_lines:
            break
    if cur and len(lines) < max_lines:
        lines.append(cur)
    if len(lines) == max_lines and " ".join(lines) != " ".join(words):
        last = lines[-1]
        lines[-1] = (last[: width - 1].rstrip() + "…") if len(last) >= width - 1 else last + "…"
    return lines


def card_svg(repo):
    w, h = 436, 184
    lang = repo.get("language") or {}
    color = lang.get("color") or "#8b949e"
    hue_color = color if lang.get("color") else "#" + hashlib.md5(repo["name"].encode()).hexdigest()[:6]
    b = [r(1, 1, w - 2, h - 2, "#161b22", 'rx="12" stroke="#30363d" stroke-width="2" shape-rendering="auto"')]
    b.append(identicon(repo["name"], 20, 24, 104, hue_color))
    name = repo["name"] if len(repo["name"]) <= 24 else repo["name"][:23] + "…"
    b.append(f'<text x="144" y="44" font-family="{MONO}" font-size="16" font-weight="700" '
             f'fill="#e6edf3">{escape(name)}</text>')
    desc = repo.get("description") or "No description yet."
    for i, line in enumerate(wrap(desc, 34, 3)):
        b.append(f'<text x="144" y="{70 + i * 20}" font-family="{SANS}" font-size="13" '
                 f'fill="#8b949e">{escape(line)}</text>')
    b.append(pixmap(ICONS["star"], 144, 146, 2, {"#": "#3fb950"}))
    b.append(pixel_text(fmt_num(repo["stars"]), 166, 145, 2, "#3fb950"))
    if lang.get("name"):
        b.append(f'<text x="{w - 20}" y="158" text-anchor="end" font-family="{MONO}" '
                 f'font-size="12" fill="#8b949e">{escape(lang["name"])}</text>')
        tw = len(lang["name"]) * 7.3
        b.append(f'<circle cx="{w - 30 - tw:.0f}" cy="154" r="5" fill="{color}" shape-rendering="auto"/>')
    return svg_doc(w, h, "".join(b), "", f'{repo["name"]}: {desc}')


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #
QUERY = """
query($login: String!) {
  user(login: $login) {
    login name
    pullRequests { totalCount }
    contributionsCollection {
      totalCommitContributions
      restrictedContributionsCount
      contributionCalendar { weeks { contributionDays { date contributionCount } } }
    }
    pinnedItems(first: 4, types: REPOSITORY) {
      nodes { ... on Repository { name description url stargazerCount primaryLanguage { name color } } }
    }
    top: repositories(first: 100, ownerAffiliations: OWNER, isFork: false,
                      orderBy: {field: STARGAZERS, direction: DESC}) {
      nodes { name description url stargazerCount primaryLanguage { name color }
              languages(first: 5, orderBy: {field: SIZE, direction: DESC}) {
                edges { size node { name color } } } }
    }
    recent: repositories(first: 8, ownerAffiliations: OWNER,
                         orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes { name
        defaultBranchRef { target { ... on Commit {
          history(first: 10) { nodes { abbreviatedOid messageHeadline committedDate
                                       author { user { login } } } } } } } }
    }
  }
}
"""


def graphql(token, login):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": {"login": login}}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "pixel-profile-generator",
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise SystemExit(f"GitHub API error: {payload['errors']}")
    return payload["data"]["user"]


def best_streak(days):
    best = cur = 0
    for d in days:
        cur = cur + 1 if d["contributionCount"] > 0 else 0
        best = max(best, cur)
    return best


def repo_card_data(node):
    return {
        "name": node["name"],
        "description": node.get("description") or "",
        "url": node["url"],
        "stars": node["stargazerCount"],
        "language": node.get("primaryLanguage"),
    }


def build_data(cfg, user):
    login = user["login"]
    cc = user["contributionsCollection"]
    days = [d for w_ in cc["contributionCalendar"]["weeks"] for d in w_["contributionDays"]]
    repos = user["top"]["nodes"]

    lang_size = {}
    lang_color = {}
    for repo in repos:
        for e in repo["languages"]["edges"]:
            n = e["node"]["name"]
            lang_size[n] = lang_size.get(n, 0) + e["size"]
            lang_color[n] = e["node"]["color"]
    languages = [{"name": n, "color": lang_color[n]}
                 for n, _ in sorted(lang_size.items(), key=lambda kv: -kv[1])]

    commits = []
    for repo in user["recent"]["nodes"]:
        ref = repo.get("defaultBranchRef")
        if not ref or not ref.get("target") or "history" not in ref["target"]:
            continue
        for c in ref["target"]["history"]["nodes"]:
            author = (c.get("author") or {}).get("user") or {}
            if author.get("login", "").lower() != login.lower():
                continue
            commits.append({"sha": c["abbreviatedOid"], "repo": repo["name"],
                            "message": c["messageHeadline"], "date": c["committedDate"]})
    commits.sort(key=lambda c: c["date"], reverse=True)
    commits = commits[: cfg.get("commit_lines", 10)] or [
        {"sha": "0000000", "repo": "hello", "message": "no public commits yet", "date": ""}]

    wanted = cfg.get("projects") or []
    by_name = {r_["name"].lower(): r_ for r_ in repos}
    if wanted:
        projects = [repo_card_data(by_name[n.lower()]) for n in wanted if n.lower() in by_name]
    else:
        pinned = [n for n in user["pinnedItems"]["nodes"] if n]
        projects = [repo_card_data(n) for n in pinned] or [repo_card_data(n) for n in repos[:4]]

    return {
        "display_name": cfg.get("display_name") or user.get("name") or login,
        "commits": commits,
        "languages": languages,
        "stats": {
            "commits": cc["totalCommitContributions"] + cc["restrictedContributionsCount"],
            "prs": user["pullRequests"]["totalCount"],
            "stars": sum(r_["stargazerCount"] for r_ in repos),
            "streak": best_streak(days),
        },
        "projects": projects[:4],
    }


def demo_data(cfg):
    return {
        "display_name": cfg.get("display_name") or "Your Name",
        "commits": [
            {"sha": "a1f9c3e", "repo": "pixel-room", "message": "Animate the sleeping cat"},
            {"sha": "7be2d40", "repo": "pixel-room", "message": "Add drifting clouds to window"},
            {"sha": "c09d1a7", "repo": "data-tools", "message": "Fix CSV parser edge case"},
            {"sha": "4e8a2f1", "repo": "data-tools", "message": "Bump version to 1.4.0"},
            {"sha": "f3b7e92", "repo": "notes", "message": "Update README.md"},
            {"sha": "9d1c6b0", "repo": "dotfiles", "message": "Switch shell prompt theme"},
            {"sha": "2aa4e5c", "repo": "notes", "message": "Add weekly reading list"},
            {"sha": "e71f0d8", "repo": "pixel-room", "message": "Initial commit"},
        ],
        "languages": [
            {"name": "Python", "color": "#3572A5"}, {"name": "TypeScript", "color": "#3178c6"},
            {"name": "HTML", "color": "#e34c26"}, {"name": "Jupyter Notebook", "color": "#DA5B0B"},
            {"name": "Shell", "color": "#89e051"},
        ],
        "stats": {"commits": 412, "prs": 23, "stars": 96, "streak": 31},
        "projects": [
            {"name": "pixel-room", "description": "Animated pixel-art banner for a GitHub profile README.",
             "url": "https://github.com", "stars": 54, "language": {"name": "Python", "color": "#3572A5"}},
            {"name": "data-tools", "description": "Small command-line helpers for cleaning and summarising CSV files.",
             "url": "https://github.com", "stars": 21, "language": {"name": "TypeScript", "color": "#3178c6"}},
            {"name": "notes", "description": "Personal notes, reading lists and snippets.",
             "url": "https://github.com", "stars": 12, "language": {"name": "HTML", "color": "#e34c26"}},
            {"name": "stats-exercises", "description": "Practice exercises for an intro statistics course, with worked solutions.",
             "url": "https://github.com", "stars": 9, "language": {"name": "Jupyter Notebook", "color": "#DA5B0B"}},
        ],
    }


# --------------------------------------------------------------------------- #
# Skill badges -> bookshelf
# --------------------------------------------------------------------------- #
_NAMED = {"brightgreen": "#44cc11", "green": "#97ca00", "yellow": "#dfb317", "orange": "#fe7d37",
          "red": "#e05d44", "blue": "#007ec6", "lightgrey": "#9f9f9f", "grey": "#555555",
          "black": "#000000", "white": "#ffffff"}


def readme_badges(text):
    """Read shields.io badges (img.shields.io/badge/LABEL-COLOR) from the README, in order."""
    books, seen = [], set()
    for path in re.findall(r"img\.shields\.io/badge/([^)\"'\s?]+)", text):
        parts = re.split(r"(?<!-)-(?!-)", path)
        if len(parts) < 2:
            continue
        name = urllib.parse.unquote(parts[0]).replace("--", "-").replace("__", "\0")
        name = name.replace("_", " ").replace("\0", "_").strip()
        color = urllib.parse.unquote(parts[-1]).removesuffix(".svg").lstrip("#").lower()
        if re.fullmatch(r"[0-9a-f]{6}", color):
            color = "#" + color
        elif re.fullmatch(r"[0-9a-f]{3}", color):
            color = "#" + "".join(c * 2 for c in color)
        else:
            color = _NAMED.get(color)
        if name and name.lower() not in seen:
            seen.add(name.lower())
            books.append({"name": name, "color": color})
    return books


# Approximate brand colours for common technologies, used when a book has no colour of its
# own and no matching README badge. Keys are normalised with _tech_key(). Add your own freely.
BRAND_COLORS = {
    "python": "#3776AB", "javascript": "#F7DF1E", "js": "#F7DF1E", "typescript": "#3178C6",
    "ts": "#3178C6", "java": "#ED8B00", "c": "#A8B9CC", "c++": "#00599C", "cpp": "#00599C",
    "c#": "#239120", "csharp": "#239120", "go": "#00ADD8", "golang": "#00ADD8",
    "rust": "#DEA584", "ruby": "#CC342D", "php": "#777BB4", "swift": "#F05138",
    "kotlin": "#7F52FF", "r": "#276DC3", "julia": "#9558B2", "scala": "#DC322F",
    "matlab": "#E16737", "sql": "#4479A1", "bash": "#4EAA25", "shell": "#4EAA25",
    "html": "#E34F26", "html5": "#E34F26", "css": "#1572B6", "css3": "#1572B6",
    "react": "#61DAFB", "vue": "#4FC08D", "vuejs": "#4FC08D", "angular": "#DD0031",
    "svelte": "#FF3E00", "nextjs": "#000000", "nodejs": "#339933", "node": "#339933",
    "tailwind": "#06B6D4", "tailwindcss": "#06B6D4", "graphql": "#E10098",
    "django": "#092E20", "flask": "#000000", "fastapi": "#009688", "streamlit": "#FF4B4B",
    "numpy": "#013243", "pandas": "#150458", "polars": "#CD792C", "scipy": "#0C55A5",
    "scikitlearn": "#F7931E", "sklearn": "#F7931E", "tensorflow": "#FF6F00",
    "keras": "#D00000", "pytorch": "#EE4C2C", "opencv": "#5C3EE8", "matplotlib": "#11557C",
    "plotly": "#3F4F75", "seaborn": "#5F4F75", "jupyter": "#F37626", "tableau": "#E97627",
    "powerbi": "#F2C811", "excel": "#217346", "huggingface": "#FFD21E",
    "langchain": "#1C3C3C", "openai": "#412991", "mysql": "#4479A1",
    "postgresql": "#4169E1", "postgres": "#4169E1", "sqlite": "#003B57",
    "mongodb": "#47A248", "redis": "#DC382D", "snowflake": "#29B5E8",
    "databricks": "#FF3621", "spark": "#E25A1C", "apachespark": "#E25A1C",
    "airflow": "#017CEE", "apacheairflow": "#017CEE", "hadoop": "#66CCFF", "dbt": "#FF694B",
    "docker": "#2496ED", "kubernetes": "#326CE5", "k8s": "#326CE5", "aws": "#FF9900",
    "gcp": "#4285F4", "googlecloud": "#4285F4", "azure": "#0078D4", "firebase": "#FFCA28",
    "git": "#F05032", "github": "#181717", "linux": "#FCC624", "figma": "#F24E1E",
}


def _tech_key(name):
    return re.sub(r"[^a-z0-9+#]", "", name.lower())


def _hash_color(name):
    """A stable, pleasant colour derived from the name, so a tech keeps its colour
    no matter where it sits in the list."""
    hue = int(hashlib.md5(_tech_key(name).encode()).hexdigest()[:4], 16) % 360
    s, l_ = 0.55, 0.45
    c = (1 - abs(2 * l_ - 1)) * s
    x = c * (1 - abs((hue / 60) % 2 - 1))
    m = l_ - c / 2
    r_, g_, b_ = [(c, x, 0), (x, c, 0), (0, c, x), (0, x, c), (x, 0, c), (c, 0, x)][hue // 60]
    return "#" + "".join(f"{round((v + m) * 255):02x}" for v in (r_, g_, b_))


def _valid_hex(color):
    if not isinstance(color, str):
        return None
    h = color.strip().lstrip("#")
    if re.fullmatch(r"[0-9a-fA-F]{3}", h):
        h = "".join(ch * 2 for ch in h)
    return "#" + h if re.fullmatch(r"[0-9a-fA-F]{6}", h) else None


def book_color(name, explicit=None, badge_color=None):
    """Colour for one book, first match wins:
    1. "color" given for it in profile.config.json
    2. the README badge with the same name
    3. the built-in BRAND_COLORS table
    4. a stable colour generated from the name
    """
    key = _tech_key(name)
    return (_valid_hex(explicit)
            or (badge_color or {}).get(key)
            or BRAND_COLORS.get(key)
            or _hash_color(name))


def pick_books(cfg, languages):
    """Books on the shelf, first non-empty source wins:
    1. "books" in profile.config.json: names ("Python") or {"name": "Python", "color": "#3776AB"}
    2. the shields.io badges in README.md
    3. your top GitHub languages
    """
    badges = readme_badges(README.read_text(encoding="utf-8")) if README.exists() else []
    badge_color = {_tech_key(b_["name"]): b_["color"] for b_ in badges if b_["color"]}
    books = []
    for item in cfg.get("books") or []:
        if isinstance(item, str):
            item = {"name": item}
        name = str(item.get("name", "")).strip()
        if name:
            books.append({"name": name, "color": book_color(name, item.get("color"), badge_color)})
    if books:
        return books
    if badges:
        return [{"name": b_["name"], "color": book_color(b_["name"], b_["color"])} for b_ in badges]
    return [{"name": l_["name"], "color": book_color(l_["name"], l_["color"])} for l_ in languages[:6]]


# --------------------------------------------------------------------------- #
# README block
# --------------------------------------------------------------------------- #
def update_readme(projects):
    if not README.exists():
        return
    rows = []
    for i in range(0, len(projects), 2):
        cells = [
            f'  <a href="{escape(p["url"])}"><img src="assets/project-{i + j + 1}.svg" width="49%" '
            f'alt="{escape(p["name"])}"></a>'
            for j, p in enumerate(projects[i:i + 2])
        ]
        rows.append("<p>\n" + "\n".join(cells) + "\n</p>")
    block = "<!-- PROJECTS:START -->\n" + "\n".join(rows) + "\n<!-- PROJECTS:END -->"
    text = README.read_text(encoding="utf-8")
    new = re.sub(r"<!-- PROJECTS:START -->.*?<!-- PROJECTS:END -->", block, text, flags=re.S)
    if new != text:
        README.write_text(new, encoding="utf-8")


def main():
    cfg = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    if "--demo" in sys.argv:
        data = demo_data(cfg)
    else:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        login = cfg.get("username") or os.environ.get("GH_USER") or os.environ.get("GITHUB_REPOSITORY_OWNER")
        if not token or not login or login == "your-username":
            raise SystemExit("Set GH_TOKEN and your username (profile.config.json or GH_USER), "
                             "or run with --demo.")
        data = build_data(cfg, graphql(token, login))

    data["books"] = pick_books(cfg, data["languages"])

    ASSETS.mkdir(exist_ok=True)
    (ASSETS / "banner.svg").write_text(scene_banner(data), encoding="utf-8")
    (ASSETS / "stats.svg").write_text(stats_svg(data["stats"]), encoding="utf-8")
    (ASSETS / "projects-heading.svg").write_text(heading_svg(), encoding="utf-8")
    for old in ASSETS.glob("project-*.svg"):
        old.unlink()
    for i, p in enumerate(data["projects"], 1):
        (ASSETS / f"project-{i}.svg").write_text(card_svg(p), encoding="utf-8")
    update_readme(data["projects"])
    print(f"Generated assets for {data['display_name']} ({len(data['projects'])} projects).")


if __name__ == "__main__":
    main()