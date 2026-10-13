"""Detects test files/directories and computes a test-to-source ratio and a
plain-language status, from a flat list of repo-relative file paths.

Deliberately does NOT claim code coverage — coverage requires actually
running the test suite and measuring which lines executed, which this tool
doesn't do. This only measures whether tests *exist* and roughly how many,
relative to source files; that's a proxy for testing discipline, not a
coverage percentage, and the two are never conflated in the output.

Fed by github_client.fetch_repo_tree(), which returns the full file tree in
one call.
"""

import os
import re
from typing import List, Optional

# Common source-code extensions. Deliberately excludes markup/config/docs
# (.md, .json, .yml, .css, .html, ...) — those aren't "source" for the
# purpose of a test-to-source ratio.
SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".java", ".kt", ".scala",
    ".go", ".rs",
    ".rb", ".php",
    ".c", ".h", ".cpp", ".cc", ".hpp", ".cs",
    ".swift", ".m", ".mm",
}

_TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec", "specs"}
# *.test.js / *.spec.js and their .ts/.jsx/.tsx siblings (common Jest/Vitest
# convention) plus the two Python conventions explicitly requested.
_JS_TEST_SUFFIX_RE = re.compile(r"\.(test|spec)\.[cm]?[jt]sx?$", re.IGNORECASE)
_PY_TEST_PREFIX_RE = re.compile(r"^test_.*\.py$", re.IGNORECASE)
_PY_TEST_SUFFIX_RE = re.compile(r".*_test\.py$", re.IGNORECASE)

# Thresholds for the plain-language status (test files / source files).
GOOD_RATIO = 0.40
FAIR_RATIO = 0.15


def is_test_file(path: str) -> bool:
    """path: forward-slash-separated, repo-relative (e.g. 'src/utils/test_math.py')."""
    parts = path.split("/")
    name = parts[-1]
    if any(p.lower() in _TEST_DIR_NAMES for p in parts[:-1]):
        return True
    if _JS_TEST_SUFFIX_RE.search(name):
        return True
    if _PY_TEST_PREFIX_RE.match(name) or _PY_TEST_SUFFIX_RE.match(name):
        return True
    return False


def is_source_file(path: str) -> bool:
    ext = os.path.splitext(path)[1].lower()
    return ext in SOURCE_EXTENSIONS


def classify(test_files: int, source_files: int) -> str:
    if test_files == 0:
        return "Not Detected"
    if source_files == 0:
        return "Good"
    ratio = test_files / source_files
    if ratio >= GOOD_RATIO:
        return "Good"
    if ratio >= FAIR_RATIO:
        return "Fair"
    return "Weak"


def summarize_testing(
    paths: Optional[List[str]],
    available: bool = True,
    reason: Optional[str] = None,
    truncated: bool = False,
) -> dict:
    """paths: flat list of repo-relative file paths (files only, not
    directories), forward-slash separated. available=False when the file
    listing itself couldn't be fetched (e.g. GitHub tree API failed) —
    reported honestly rather than defaulting to "Not Detected", which would
    look identical to "genuinely has no tests" but means something
    different (we don't know)."""

    if not available or paths is None:
        return {
            "available": False,
            "reason": reason or "File listing wasn't available.",
            "total_source_files": None,
            "total_test_files": None,
            "test_source_ratio": None,
            "status": None,
            "has_test_directory": None,
            "truncated": truncated,
        }

    test_files = [p for p in paths if is_test_file(p)]
    source_files = [p for p in paths if is_source_file(p) and p not in test_files]
    # A file can be both "source" (by extension) and "test" (by name/dir) —
    # count it as a test file only, not double-counted as source too.

    has_test_dir = any(
        part.lower() in _TEST_DIR_NAMES for p in paths for part in p.split("/")[:-1]
    )

    total_source = len(source_files)
    total_test = len(test_files)
    ratio = round(total_test / total_source, 2) if total_source > 0 else (1.0 if total_test > 0 else None)
    status = classify(total_test, total_source)

    return {
        "available": True,
        "reason": None,
        "total_source_files": total_source,
        "total_test_files": total_test,
        "test_source_ratio": ratio,
        "status": status,
        "has_test_directory": has_test_dir,
        "truncated": truncated,
    }
