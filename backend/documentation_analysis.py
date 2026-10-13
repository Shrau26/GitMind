"""Analyzes README content for the presence of standard documentation
sections (description, installation, usage, examples, configuration, API
docs, contribution guide) and computes a 0-100 documentation score.

This is a distinct, more detailed metric from the lightweight doc_score
used inside health.py's "documentation" health factor (which only checks
README length + presence of CONTRIBUTING/LICENSE/docs — used there to keep
the health-score engine simple and unchanged). This module instead reads
the README's actual section headers to say specifically what's covered and
what's missing.

Detection is header-based: it looks at markdown headers (# / ## / ### etc.)
and matches their text against keyword sets for each section. This means a
project that documents "Usage" only as plain paragraphs with no header
won't be detected — a reasonable, disclosed limitation rather than trying
to parse arbitrary prose, which would be far less reliable.
"""

import re
from typing import List, Optional

_HEADER_RE = re.compile(r"^#{1,6}\s+(.+?)\s*#*$", re.MULTILINE)

# Each section: (display name, keywords matched against header text).
# "description" is handled separately below (see summarize_documentation)
# since projects essentially never have a header literally called
# "Description" — it's almost always the untitled opening paragraph(s).
SECTION_KEYWORDS = [
    ("Installation / Setup", {
        "install", "installation", "setup", "getting started", "quick start",
        "quickstart", "requirements", "prerequisites",
    }),
    ("Usage", {
        "usage", "how to use", "using", "basic usage", "quick usage",
    }),
    ("Examples", {
        "example", "examples", "demo", "demos", "sample", "samples",
    }),
    ("Configuration", {
        "configuration", "config", "options", "settings",
        "environment variable", "env var",
    }),
    ("API Documentation", {
        "api", "api reference", "api documentation", "reference", "endpoints",
    }),
    ("Contribution Guide", {
        "contributing", "contribution", "contribute", "development guide",
        "developer guide",
    }),
]

MIN_DESCRIPTION_CHARS = 80  # opening content this long counts as a real description


def _extract_headers(readme_text: str) -> List[str]:
    return [h.strip().lower() for h in _HEADER_RE.findall(readme_text)]


def _has_description(readme_text: str) -> bool:
    """A README "has a description" if there's substantial prose after the
    title (the first header — usually just the project name) and before
    the next header. That block is, in practice, always what a project is
    / what it does, whether or not it sits under a literal "Description"
    header."""
    headers = list(_HEADER_RE.finditer(readme_text))
    if not headers:
        # No headers at all — the whole README is the "opening" content.
        opening = readme_text
    elif len(headers) == 1:
        # Only a title — everything after it is the opening content.
        opening = readme_text[headers[0].end():]
    else:
        # Content between the title and the next header.
        opening = readme_text[headers[0].end():headers[1].start()]
    lines = [
        ln for ln in opening.splitlines()
        if ln.strip() and not ln.strip().startswith("#") and not ln.strip().startswith("![")
        and not ln.strip().startswith("[![")
    ]
    return len(" ".join(lines).strip()) >= MIN_DESCRIPTION_CHARS


def summarize_documentation(
    readme_text: Optional[str],
    has_contributing_file: bool = False,
) -> dict:
    """readme_text: raw README content, or None/empty if there isn't one.
    has_contributing_file: whether a standalone CONTRIBUTING.md exists —
    that satisfies the "Contribution Guide" section just as well as an
    in-README header does, so it's OR'd in rather than requiring both."""

    if not readme_text or not readme_text.strip():
        sections_missing = ["Description"] + [name for name, _ in SECTION_KEYWORDS]
        return {
            "available": True,
            "has_readme": False,
            "documentation_score": 0,
            "sections_detected": [],
            "sections_missing": sections_missing,
        }

    headers = _extract_headers(readme_text)

    detected = []
    missing = []

    if _has_description(readme_text):
        detected.append("Description")
    else:
        missing.append("Description")

    for display_name, keywords in SECTION_KEYWORDS:
        found = any(any(kw in header for kw in keywords) for header in headers)
        if display_name == "Contribution Guide" and has_contributing_file:
            found = True
        if found:
            detected.append(display_name)
        else:
            missing.append(display_name)

    total_sections = len(SECTION_KEYWORDS) + 1  # +1 for Description
    score = round(100 * len(detected) / total_sections)

    return {
        "available": True,
        "has_readme": True,
        "documentation_score": score,
        "sections_detected": detected,
        "sections_missing": missing,
    }
