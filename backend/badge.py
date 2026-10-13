"""Generates a small, shields.io-style SVG badge for a repo's health score —
e.g. "GitMind Health | 87" with a color matching the health bucket. Meant to
be embedded directly in a README via an <img> tag or Markdown image syntax
pointing at GET /api/repos/{id}/badge.svg. Pure string templating: no
external image library, no network call, deterministic output for a given
score/label.
"""

# Same bucket boundaries as the health-status labels used everywhere else
# in the app (see health.py / Dashboard.jsx) — the badge should always
# agree with the color the rest of the UI already uses for this score.
_COLORS = [
    (80, "#3fb950"),  # healthy — green
    (55, "#d4a72c"),  # fair — yellow
    (30, "#db6d28"),  # at risk — orange
    (0, "#da3633"),   # critical — red
]


def _color_for_score(score: int) -> str:
    for threshold, color in _COLORS:
        if score >= threshold:
            return color
    return _COLORS[-1][1]


def _char_width(ch: str) -> float:
    """Rough per-character width in px for an 11px Verdana-ish sans-serif —
    good enough to size a badge without a real font metrics table, same
    approximation shields.io itself used for years before switching to
    precomputed tables."""
    if ch in "iIl.:,'!|":
        return 4.0
    if ch in "mMW":
        return 9.5
    if ch.isupper():
        return 7.5
    return 6.5


def _text_width(text: str) -> int:
    return max(6, round(sum(_char_width(c) for c in text)))


def render_health_badge(score: int, label: str = "GitMind Health") -> str:
    """Returns a complete, self-contained SVG document (as a string)."""
    score = max(0, min(100, int(score)))
    value_text = str(score)
    color = _color_for_score(score)

    pad = 10
    label_w = _text_width(label) + pad * 2
    value_w = _text_width(value_text) + pad * 2
    total_w = label_w + value_w
    height = 20

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="{total_w}" height="{height}" role="img" aria-label="{label}: {value_text}">
  <linearGradient id="smooth" x2="0" y2="100%">
    <stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
    <stop offset="1" stop-opacity=".1"/>
  </linearGradient>
  <clipPath id="round">
    <rect width="{total_w}" height="{height}" rx="3" fill="#fff"/>
  </clipPath>
  <g clip-path="url(#round)">
    <rect width="{label_w}" height="{height}" fill="#555"/>
    <rect x="{label_w}" width="{value_w}" height="{height}" fill="{color}"/>
    <rect width="{total_w}" height="{height}" fill="url(#smooth)"/>
  </g>
  <g fill="#fff" text-anchor="middle" font-family="Verdana,Geneva,DejaVu Sans,sans-serif" font-size="11">
    <text x="{label_w / 2}" y="14" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{label_w / 2}" y="13">{label}</text>
    <text x="{label_w + value_w / 2}" y="14" fill="#010101" fill-opacity=".3">{value_text}</text>
    <text x="{label_w + value_w / 2}" y="13">{value_text}</text>
  </g>
</svg>'''
