#!/usr/bin/env python3
"""Generate the app icon (PNG + .icns + .ico) without external assets."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
BG = (30, 30, 30, 255)
ACCENT = (74, 158, 255, 255)
RED = (192, 57, 43, 255)
GREEN = (39, 174, 96, 255)
WHITE = (240, 240, 240, 255)


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 1024.0

    # rounded background
    r = int(220 * s)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=r, fill=BG)

    # camera body
    body = [int(150 * s), int(330 * s), int(874 * s), int(760 * s)]
    d.rounded_rectangle(body, radius=int(60 * s), fill=(60, 60, 60, 255),
                        outline=ACCENT, width=max(2, int(14 * s)))

    # lens
    cx, cy = int(512 * s), int(545 * s)
    rad = int(150 * s)
    d.ellipse([cx - rad, cy - rad, cx + rad, cy + rad],
              outline=ACCENT, width=max(2, int(18 * s)))
    d.ellipse([cx - int(70 * s), cy - int(70 * s),
               cx + int(70 * s), cy + int(70 * s)], fill=ACCENT)

    # viewfinder bump
    d.rounded_rectangle([int(380 * s), int(270 * s), int(644 * s), int(350 * s)],
                        radius=int(30 * s), fill=(60, 60, 60, 255),
                        outline=ACCENT, width=max(2, int(12 * s)))

    # unlock shackle (open padlock) over the lens
    lx, ly = int(512 * s), int(880 * s)
    d.rounded_rectangle([lx - int(120 * s), ly - int(60 * s),
                         lx + int(120 * s), ly + int(90 * s)],
                        radius=int(28 * s), fill=GREEN)
    # open shackle: arc missing the right leg
    d.arc([lx - int(80 * s), ly - int(190 * s),
           lx + int(80 * s), ly - int(30 * s)],
          start=180, end=360, fill=GREEN, width=max(2, int(26 * s)))
    d.line([lx - int(80 * s), ly - int(110 * s),
            lx - int(80 * s), ly - int(60 * s)],
           fill=GREEN, width=max(2, int(26 * s)))

    # small red slash = "bypass"
    d.line([int(300 * s), int(820 * s), int(724 * s), int(300 * s)],
           fill=RED, width=max(2, int(26 * s)))
    return img


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    base = draw_icon(1024)
    png = ASSETS / "icon.png"
    base.save(png)
    print("wrote", png)

    # .ico for Windows (multi-size)
    ico = ASSETS / "icon.ico"
    base.save(ico, sizes=[(16, 16), (32, 32), (48, 48), (64, 64),
                          (128, 128), (256, 256)])
    print("wrote", ico)

    # .icns for macOS via iconutil
    iconset = ASSETS / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    for sz in (16, 32, 64, 128, 256, 512):
        base.resize((sz, sz), Image.LANCZOS).save(iconset / f"icon_{sz}x{sz}.png")
        base.resize((sz * 2, sz * 2), Image.LANCZOS).save(
            iconset / f"icon_{sz}x{sz}@2x.png")
    icns = ASSETS / "icon.icns"
    try:
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
                       check=True)
        print("wrote", icns)
    except Exception as e:
        print("iconutil failed (non-macOS?):", e, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
