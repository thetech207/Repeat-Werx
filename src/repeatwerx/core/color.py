"""Color harmony schemes and 60-30-10 role assignment."""

from __future__ import annotations

import colorsys

HARMONIES = {
    "monochrome": "Monochrome",
    "analogous": "Analogous",
    "complementary": "Complementary",
    "split_complementary": "Split complementary",
    "triadic": "Triadic",
    "tetradic": "Tetradic",
}

ROLE_NAMES = ("Dominant (60%)", "Secondary (30%)", "Accent (10%)")


def hex_to_hls(hexcol: str):
    hexcol = hexcol.lstrip("#")
    r, g, b = (int(hexcol[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return colorsys.rgb_to_hls(r, g, b)


def hls_to_hex(h: float, l: float, s: float) -> str:
    r, g, b = colorsys.hls_to_rgb(h % 1.0, min(max(l, 0), 1),
                                  min(max(s, 0), 1))
    return "#{:02x}{:02x}{:02x}".format(round(r * 255), round(g * 255),
                                        round(b * 255))


def rotate(hexcol: str, degrees: float, dl: float = 0.0,
           ds: float = 0.0) -> str:
    h, l, s = hex_to_hls(hexcol)
    return hls_to_hex(h + degrees / 360.0, l + dl, s + ds)


def harmony(base: str, scheme: str) -> list[str]:
    """Colors ordered by role: [dominant, secondary, accent, extra...]."""
    if scheme == "monochrome":
        return [base, rotate(base, 0, 0.22, -0.1), rotate(base, 0, -0.2, 0.1)]
    if scheme == "analogous":
        return [base, rotate(base, 30), rotate(base, -30, 0.05)]
    if scheme == "complementary":
        return [base, rotate(base, 0, 0.25, -0.15), rotate(base, 180)]
    if scheme == "split_complementary":
        return [base, rotate(base, 150), rotate(base, 210)]
    if scheme == "tetradic":
        return [base, rotate(base, 90), rotate(base, 180), rotate(base, 270)]
    # triadic (default)
    return [base, rotate(base, 120), rotate(base, 240)]


def role_shares(colors: list, shares) -> list[float]:
    """Per-color share; extra colors (tetradic) split the accent share."""
    shares = list(shares[:3]) + [0.0] * max(0, 3 - len(shares))
    if len(colors) <= 3:
        return shares[:len(colors)]
    extra = len(colors) - 2
    return shares[:2] + [shares[2] / extra] * extra


def assign_roles(areas: list[float], shares: list[float], order=None
                 ) -> list[int]:
    """Assign each area a role index so per-role totals track `shares`.

    Items are visited in `order` (default: as given) and each goes to the
    role whose running total lags its target the most, which keeps the
    final split close to e.g. 60/30/10 regardless of item sizes.
    """
    n = len(areas)
    roles = [0] * n
    if n == 0:
        return roles
    total = sum(areas) or 1.0
    tot = sum(shares) or 1.0
    targets = [s / tot * total for s in shares]
    got = [0.0] * len(shares)
    for i in (order if order is not None else range(n)):
        a = areas[i]
        best = max(range(len(shares)),
                   key=lambda r: (targets[r] - got[r] - a / 2) / (
                       targets[r] or 1e-9))
        roles[i] = best
        got[best] += a
    return roles


def luminance(hexcol: str) -> float:
    hexcol = hexcol.lstrip("#")
    r, g, b = (int(hexcol[i:i + 2], 16) for i in (0, 2, 4))
    return 0.299 * r + 0.587 * g + 0.114 * b
