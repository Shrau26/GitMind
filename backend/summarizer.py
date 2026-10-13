"""Plain-English repo summary — generated locally, no LLM API call.

Approach: frequency-weighted extractive summarization (a lightweight
cousin of TextRank/Luhn's algorithm). It strips markdown noise (badges,
code fences, links, headers) out of the README, scores each remaining
sentence by how many "important" (high-frequency, non-stopword) terms it
contains, and keeps the 2-3 highest scoring sentences in their original
order.

This is deterministic, has zero external dependencies beyond the
standard library, and needs no training data or network access. It will
never be as good as an LLM at genuinely rephrasing jargon, but it
reliably surfaces the README's own best "what is this" sentences —
which is exactly what's missing in jargon-heavy or sparse READMEs.
If you supply a labeled dataset (README -> ideal 2-3 sentence summary
pairs), that's a real path to a learned model later; swap this module
out without touching the rest of the app.
"""

import re
from collections import Counter
from typing import List, Optional

_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "for",
    "with", "is", "are", "was", "were", "be", "been", "being", "it", "its",
    "this", "that", "these", "those", "as", "at", "by", "from", "into",
    "your", "you", "we", "our", "can", "will", "if", "then", "so", "than",
    "which", "who", "what", "when", "where", "how", "not", "no", "yes",
    "also", "using", "use", "used", "based", "such", "via", "each", "any",
    "all", "more", "most", "some", "other", "over", "under", "up", "down",
    "out", "about", "just", "like", "have", "has", "had", "do", "does",
    "did", "their", "them", "they", "it's", "i", "my",
}

_MD_IMAGE_OR_LINK = re.compile(r"!?\[([^\]]*)\]\(([^)]*)\)")
_MD_BADGE_LINE = re.compile(r"^\s*(\[!\[|\[!\[|!\[)", re.MULTILINE)
_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]*`")
_HEADER = re.compile(r"^#{1,6}\s*", re.MULTILINE)
_HTML_TAG = re.compile(r"<[^>]+>")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z(])")


def _clean_readme(raw: str) -> str:
    text = _CODE_FENCE.sub(" ", raw)
    text = _INLINE_CODE.sub(" ", text)
    text = _HTML_TAG.sub(" ", text)
    # Replace markdown links/images with just their visible label text.
    text = _MD_IMAGE_OR_LINK.sub(lambda m: m.group(1), text)
    text = _HEADER.sub("", text)

    paragraphs = []
    for para in re.split(r"\n\s*\n", text):
        joined_lines = []
        for ln in para.splitlines():
            stripped = ln.strip()
            if not stripped or _MD_BADGE_LINE.match(ln) or stripped.startswith(("|", "---")):
                continue
            joined_lines.append(stripped)
        if not joined_lines:
            continue
        paragraph_text = " ".join(joined_lines).strip()
        # Ensure each paragraph ends with sentence punctuation before joining
        # with the next one, so a short header-like paragraph (e.g. "Installation")
        # doesn't fuse into the following paragraph as one run-on sentence.
        if not paragraph_text.endswith((".", "!", "?", ":")):
            paragraph_text += "."
        paragraphs.append(paragraph_text)

    return " ".join(paragraphs)


def _sentences(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return []
    raw_sentences = _SENTENCE_SPLIT.split(text)
    # Keep sentences that look like real prose, not stray fragments/table junk.
    return [
        s.strip() for s in raw_sentences
        if 25 <= len(s.strip()) <= 280 and re.search(r"[a-zA-Z]{3,}", s)
    ]


def summarize(
    description: Optional[str],
    readme_markdown: Optional[str],
    repo_name: str,
    max_sentences: int = 3,
) -> str:
    """Produce a 2-3 sentence plain-English summary from README + description."""

    cleaned = _clean_readme(readme_markdown) if readme_markdown else ""
    sentences = _sentences(cleaned)

    if not sentences:
        if description:
            return description.strip().rstrip(".") + "."
        return f"{repo_name} does not have enough README content to summarize automatically."

    word_pattern = re.compile(r"[a-zA-Z][a-zA-Z0-9'\-]{2,}")
    freq = Counter()
    for sentence in sentences:
        for word in word_pattern.findall(sentence.lower()):
            if word not in _STOPWORDS:
                freq[word] += 1

    if not freq:
        return (description.strip().rstrip(".") + ".") if description else sentences[0]

    max_freq = max(freq.values())
    for word in freq:
        freq[word] = freq[word] / max_freq

    scored = []
    for idx, sentence in enumerate(sentences):
        words = [w for w in word_pattern.findall(sentence.lower()) if w not in _STOPWORDS]
        if not words:
            continue
        score = sum(freq.get(w, 0) for w in words) / len(words)
        # Mild preference for sentences that appear earlier (READMEs tend to
        # front-load the "what is this" statement).
        position_bonus = 0.15 if idx < 3 else 0.0
        scored.append((score + position_bonus, idx, sentence))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:max_sentences]
    # Restore original reading order for coherence.
    top.sort(key=lambda x: x[1])
    summary = " ".join(s for _, _, s in top)

    if description and description.strip() not in summary:
        summary = description.strip().rstrip(".") + ". " + summary

    return summary.strip()
