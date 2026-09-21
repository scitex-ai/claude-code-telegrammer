#!/usr/bin/env python3
"""Generate fleet-style Telegram bot avatar icons for SciTeX agents.

Style: solid-color FULL-BLEED SQUARE + short label + small "SciTeX"
wordmark, matching the fleet's existing bot avatars (Hub / TODO / SAC / NV /
pClew). Square on purpose: Telegram crops avatars to a circle client-side, so
a square yields a perfectly smooth circle in every client — while a
self-drawn circle both aliases at the edge (PIL ellipses are unantialiased)
and would get double-cropped. Set the output through BotFather /setuserpic or convert to JPEG for
the Bot API setMyProfilePhoto multipart endpoint.

Usage:
    python3 generate_bot_icons.py [--font /path/to/font.ttf] [--out DIR]

Requires: Pillow. The default font is Lato if resolvable; pass --font
otherwise (any sans-serif TTF works — the label is stroke-thickened, so a
regular weight suffices).
"""

import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZE = 1024  # BotFather accepts >=512; 1024 keeps headroom.
WORDMARK = "SciTeX"

# Lead colors are the named RGB colors in FigRecipe's
# src/figrecipe/styles/presets/SCITEX.yaml, not the website brand palette.
# Other package avatars retain their existing colors.
BOTS = {
    "research-lead": ("R&D", "#0080c0"),
    "infrastructure-lead": ("Infra", "#808080"),
    "applications-lead": ("App", "#ff4632"),
    "business-lead": ("Biz", "#e6a014"),
    "cct": ("CCT", "#1a2a40"),        # claude-code-telegrammer — SciTeX-01 navy
    "writer": ("Writer", "#5865c9"),  # scitex-writer — indigo
    "figrecipe": ("Fig", "#d97742"),  # figrecipe — orange
    "dsp": ("DSP", "#6c8ba0"),        # scitex-dsp — SciTeX-04 steel
}

# Candidate font locations (first hit wins) when --font is not given.
FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/lato/Lato-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def resolve_font(explicit: str | None) -> str:
    candidates = [explicit] if explicit else FONT_CANDIDATES
    for c in candidates:
        if c and Path(c).is_file():
            return c
    raise SystemExit(
        "no usable TTF found — pass --font /path/to/font.ttf "
        f"(tried: {', '.join(str(c) for c in candidates)})"
    )


def make_icon(label: str, color: str, font_path: str) -> Image.Image:
    # Full-bleed square — Telegram's client-side circle crop supplies the
    # smooth round mask; text is kept inside the inscribed circle's safe area.
    img = Image.new("RGB", (SIZE, SIZE), color)
    d = ImageDraw.Draw(img)
    # Operator preference: black on the four plotting-theme lead colors.
    # Keep existing package-avatar lettering white.
    ink = "black" if label in {"Infra", "App", "Biz", "R&D"} else "white"

    # Fit actual glyph width, rather than shrinking every four-letter label.
    # Keep the main word large while preserving the circular crop's safe area.
    for font_size in range(340, 79, -4):
        f_big = ImageFont.truetype(font_path, font_size)
        bb = d.textbbox((0, 0), label, font=f_big, stroke_width=10)
        if bb[2] - bb[0] <= SIZE * 0.78:
            break
    else:
        raise ValueError("label is too long for the avatar's safe area")
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    d.text(
        ((SIZE - w) / 2 - bb[0], SIZE * 0.42 - h / 2 - bb[1]),
        label, font=f_big, fill=ink, stroke_width=10, stroke_fill=ink,
    )

    f_small = ImageFont.truetype(font_path, 110)
    bb = d.textbbox((0, 0), WORDMARK, font=f_small)
    d.text(
        ((SIZE - (bb[2] - bb[0])) / 2 - bb[0], SIZE * 0.66 - bb[1]),
        WORDMARK, font=f_small, fill=ink,
    )
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--font", help="TTF font path (default: first candidate found)")
    ap.add_argument("--out", default=".", help="output directory (default: cwd)")
    ap.add_argument("--only", nargs="+", choices=sorted(BOTS), help="Generate selected bots only")
    args = ap.parse_args()

    font_path = resolve_font(args.font)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for slug, (label, color) in BOTS.items():
        if args.only and slug not in args.only:
            continue
        dest = out / f"bot-icon-{slug}.png"
        make_icon(label, color, font_path).save(dest)
        print(f"wrote {dest}")


if __name__ == "__main__":
    main()
