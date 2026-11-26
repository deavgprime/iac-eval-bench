"""Render two editable diagrams for the retry experiment."""

from html import escape
from pathlib import Path

import cairosvg

OUT = Path(__file__).resolve().parent
OUT.mkdir(exist_ok=True)
INK = "#172d3c"
MUTED = "#596975"
MINT = "#d8f2e9"
PALE = "#f3f6f7"
ACCENT = "#21775c"
RED = "#aa3f30"
WARM = "#fff0e9"
LINE = "#ccd6db"


def text(x, y, value, size=28, weight=400, color=INK, anchor="start", mono=False):
    font = "DejaVu Sans Mono" if mono else "DejaVu Sans"
    return (
        f'<text x="{x}" y="{y}" font-family="{font},sans-serif" '
        f'font-size="{size}" font-weight="{weight}" fill="{color}" '
        f'text-anchor="{anchor}">{escape(value)}</text>'
    )


def rect(x, y, w, h, fill=PALE, radius=16):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"/>'


def arrow(x1, y1, x2, y2, color=ACCENT):
    return (
        f'<path d="M{x1} {y1} H{x2}" stroke="{color}" stroke-width="3" fill="none"/>'
        f'<path d="M{x2 - 10} {y2 - 8} L{x2} {y2} L{x2 - 10} {y2 + 8}" '
        f'stroke="{color}" stroke-width="3" fill="none"/>'
    )


def save(name, height, parts, description):
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="{height}" '
        f'viewBox="0 0 1600 {height}" role="img" aria-labelledby="title desc">'
        f'<title id="title">{escape(name)}</title><desc id="desc">{escape(description)}</desc>'
        f'<rect width="1600" height="{height}" fill="white"/>' + "".join(parts) + "</svg>"
    )
    (OUT / f"{name}.svg").write_text(svg + "\n")
    cairosvg.svg2png(bytestring=svg.encode(), write_to=str(OUT / f"{name}.png"))


def boundaries():
    p = [
        text(64, 58, "TWO DURABLE BOUNDARIES", 22, 700, ACCENT),
        text(64, 126, "Keep the action identity. Commit its result.", 48, 700),
    ]
    p.extend(
        [
            rect(64, 200, 420, 300),
            text(94, 250, "Caller journal", 31, 700),
            text(94, 314, "action-1", 30, mono=True),
            text(94, 365, "key: 9f2a...", 30, mono=True),
            text(94, 453, "Save before the first send.", 25, color=MUTED),
            arrow(500, 347, 610, 347),
            rect(626, 200, 330, 300),
            text(656, 250, "HTTP tool call", 30, 700),
            text(656, 320, "POST /orders", 28, mono=True),
            text(656, 372, "same key", 29, 700, ACCENT),
            text(656, 453, "Reuse on each attempt.", 23, color=MUTED),
            arrow(972, 347, 1082, 347),
            rect(1098, 200, 438, 300, MINT),
            text(1128, 250, "Service database", 30, 700),
            text(1128, 320, "Order + replay receipt", 26, 700),
            text(1128, 372, "one transaction", 29, 700, ACCENT),
            text(1128, 453, "Commit both or neither.", 25, color=MUTED),
            rect(64, 557, 1472, 98, PALE),
            text(
                800,
                616,
                "A repeat returns the stored order ID and response.",
                31,
                700,
                anchor="middle",
            ),
            text(
                64,
                716,
                "Schematic of the local test. The HTTP request can still be delivered more than once.",
                25,
                color=MUTED,
            ),
        ]
    )
    save(
        "durable-boundaries",
        765,
        p,
        "The caller saves an action key before sending. Every attempt reuses that key. The service "
        "commits the order and replay receipt in one transaction, then replays its result for a repeated request.",
    )


def gap():
    p = [
        text(64, 58, "THE CRASH BOUNDARY", 22, 700, ACCENT),
        text(64, 126, "The same key cannot replay a missing receipt.", 47, 700),
        rect(64, 190, 1472, 224, WARM),
        text(94, 240, "Separate transactions", 29, 700, RED),
        rect(94, 269, 390, 92, "white"),
        text(289, 327, "Commit order", 28, 700, anchor="middle"),
        arrow(500, 315, 625, 315, RED),
        text(720, 323, "CRASH", 26, 700, RED, "middle"),
        arrow(815, 315, 940, 315, RED),
        rect(956, 269, 548, 92, "white"),
        text(1230, 327, "Receipt was never committed", 26, 700, anchor="middle"),
        text(
            94,
            394,
            "Restart + same key: no receipt found, so the retry creates another order.",
            26,
            color=RED,
        ),
        rect(64, 450, 1472, 224, MINT),
        text(94, 500, "One transaction", 29, 700, ACCENT),
        rect(94, 529, 820, 92, "white"),
        text(504, 587, "Order + receipt commit together", 28, 700, anchor="middle"),
        arrow(930, 575, 1045, 575),
        text(1270, 585, "Replay original result", 27, 700, ACCENT, "middle"),
        text(
            94,
            654,
            "Before commit: both roll back. After commit: both are available on restart.",
            26,
            color=ACCENT,
        ),
        text(
            64,
            735,
            "Measured split-transaction control: 2 orders in each of 3 runs with the same durable key.",
            25,
            color=MUTED,
        ),
    ]
    save(
        "commit-gap",
        785,
        p,
        "Separate commits allow a crash after the order but before its receipt, creating a duplicate "
        "on retry. One database transaction commits both or rolls back both. The split control created "
        "two orders in all three runs with a durable key.",
    )


if __name__ == "__main__":
    boundaries()
    gap()
