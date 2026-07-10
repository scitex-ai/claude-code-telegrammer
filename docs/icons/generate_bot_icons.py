#!/usr/bin/env python3
"""Generate fleet-style Telegram bot avatar icons for SciTeX agents.

Style: solid-color FULL-BLEED SQUARE + short white label + small "SciTeX"
wordmark, matching the fleet's existing bot avatars (Hub / TODO / SAC / NV /
pClew). Square on purpose: Telegram crops avatars to a circle client-side, so
a square yields a perfectly smooth circle in every client — while a
self-drawn circle both aliases at the edge (PIL ellipses are unantialiased)
and would get double-cropped. Set the output on the bot via @BotFather ->
/setuserpic (the Bot API cannot change a bot's own avatar, so that last step
is manual).

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

# slug -> (label, circle color). Colors picked to stay distinct across the
# fleet's existing avatars (Hub=blue, TODO=teal, SAC=green, NV=purple,
# pClew=teal-green). Navy/slate/steel come from the SciTeX palette.
BOTS = {
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

    # Long labels get a smaller face so they stay inside the circle; the
    # stroke fakes a bold weight so a regular-weight TTF is enough.
    f_big = ImageFont.truetype(font_path, 340 if len(label) <= 3 else 240)
    bb = d.textbbox((0, 0), label, font=f_big, stroke_width=10)
    w, h = bb[2] - bb[0], bb[3] - bb[1]
    d.text(
        ((SIZE - w) / 2 - bb[0], SIZE * 0.42 - h / 2 - bb[1]),
        label, font=f_big, fill="white", stroke_width=10, stroke_fill="white",
    )

    f_small = ImageFont.truetype(font_path, 110)
    bb = d.textbbox((0, 0), WORDMARK, font=f_small)
    d.text(
        ((SIZE - (bb[2] - bb[0])) / 2 - bb[0], SIZE * 0.66 - bb[1]),
        WORDMARK, font=f_small, fill="white",
    )
    return img


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--font", help="TTF font path (default: first candidate found)")
    ap.add_argument("--out", default=".", help="output directory (default: cwd)")
    args = ap.parse_args()

    font_path = resolve_font(args.font)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    for slug, (label, color) in BOTS.items():
        dest = out / f"bot-icon-{slug}.png"
        make_icon(label, color, font_path).save(dest)
        print(f"wrote {dest}")


if __name__ == "__main__":
    main()
