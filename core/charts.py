"""Small server-side SVG charts — no JavaScript or external assets needed."""

import html
import math
from decimal import Decimal

PALETTE = (
    "#2563eb",
    "#16a34a",
    "#d97706",
    "#dc2626",
    "#7c3aed",
    "#0891b2",
    "#db2777",
    "#65a30d",
)


def _palette(index):
    return PALETTE[index % len(PALETTE)]


def donut_chart(items, total=None, size=220, thickness=34):
    """Return an inline SVG donut chart for (label, value) pairs.

    `items` is an iterable of objects with ``label`` and ``value`` keys.
    """
    rows = [(str(item["label"]), item["value"]) for item in items]
    if total is None:
        total = sum((value for _, value in rows), Decimal("0"))

    radius = (size - thickness) / 2
    centre = size / 2
    base = (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        'role="img" aria-label="Donut chart of amounts by category">'
    )

    if not rows or total <= 0:
        return (
            base
            + "<title>No data</title>"
            + f'<circle cx="{centre}" cy="{centre}" r="{radius}" fill="none" '
            + f'stroke="#e2e8f0" stroke-width="{thickness}"/>'
            + f'<text x="{centre}" y="{centre + 5}" text-anchor="middle" '
            + 'font-size="14" fill="#64748b">No data</text>'
            + "</svg>"
        )

    parts = [base, "<title>Approved amount by category</title>"]
    drawn = 0
    angle = -math.pi / 2

    for index, (label, value) in enumerate(rows):
        if value <= 0:
            continue
        drawn += 1
        colour = _palette(index)
        if drawn == 1 and sum(1 for v in (v for _, v in rows) if v > 0) == 1:
            parts.append(
                f'<circle cx="{centre}" cy="{centre}" r="{radius}" fill="none" '
                f'stroke="{colour}" stroke-width="{thickness}">'
                f"<title>{html.escape(label)}: {value}</title></circle>"
            )
            break

        sweep = float(value) / float(total) * 2 * math.pi
        end_angle = angle + sweep
        large_arc = 1 if sweep > math.pi else 0
        x1 = centre + radius * math.cos(angle)
        y1 = centre + radius * math.sin(angle)
        x2 = centre + radius * math.cos(end_angle)
        y2 = centre + radius * math.sin(end_angle)
        parts.append(
            f'<path d="M {x1:.2f} {y1:.2f} A {radius:.2f} {radius:.2f} 0 '
            f'{large_arc} 1 {x2:.2f} {y2:.2f}" fill="none" stroke="{colour}" '
            f'stroke-width="{thickness}">'
            f"<title>{html.escape(label)}: {value}</title></path>"
        )
        angle = end_angle

    parts.append(
        f'<text x="{centre}" y="{centre - 2}" text-anchor="middle" '
        'font-size="11" fill="#64748b">TOTAL</text>'
        f'<text x="{centre}" y="{centre + 16}" text-anchor="middle" '
        f'font-size="14" font-weight="700" fill="#0f172a">{total}</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def chart_legend(items, total=None):
    """Legend rows with matching colours and percentages."""
    if total is None:
        total = sum((item["value"] for item in items), Decimal("0"))
    legend = []
    for index, item in enumerate(items):
        value = item["value"]
        percent = (float(value) / float(total) * 100) if total > 0 else 0.0
        legend.append(
            {
                "label": item["label"],
                "value": value,
                "percent": round(percent, 1),
                "colour": _palette(index),
            }
        )
    return legend
