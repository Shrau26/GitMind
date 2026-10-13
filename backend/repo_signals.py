"""Shared signal-detection helpers for the GitHub-repo pipeline
(dependencies.py, fed by github_client.fetch_root_contents).

Keeping these constants and the doc-score formula in one place keeps the
definitions of "has tests" / "has documentation" consistent everywhere.
"""

from typing import Iterable, List, Optional, Tuple

DEPENDENCY_FILES = ["package.json", "requirements.txt", "pyproject.toml", "pom.xml"]

# Lock files pin the *resolved* dependency tree — direct + transitive — as
# it actually existed at last commit. Detecting/parsing these (see
# dependencies.py's transitive-dependency parsers) is how transitive
# dependencies get counted without querying any package registry live.
LOCK_FILES = [
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml",
    "poetry.lock", "Pipfile.lock", "Cargo.lock", "composer.lock", "go.sum",
]

TEST_DIR_NAMES = {"tests", "test", "__tests__", "spec", "specs"}
TEST_FILE_HINTS = {
    "pytest.ini", "jest.config.js", "jest.config.ts", "jest.config.mjs",
    "phpunit.xml", "phpunit.xml.dist", "karma.conf.js", "tox.ini", "vitest.config.ts",
    "vitest.config.js",
}
DOC_DIR_NAMES = {"docs", "documentation"}


def detect_signals(entries: Iterable[Tuple[str, str]]) -> dict:
    """entries: iterable of (name, type) where type is "file" or "dir",
    covering the *top level* of a repository (root directory listing only —
    this is a lightweight heuristic, not a full repo scan).

    Returns booleans for the presence of tests, a docs/ directory, a
    CONTRIBUTING file, and a LICENSE file, plus which of the four known
    dependency-manifest filenames are present.
    """
    by_name = {}
    original_case = {}
    for name, entry_type in entries:
        if not name:
            continue
        lower = name.lower()
        by_name[lower] = entry_type
        original_case[lower] = name

    has_tests = any(
        by_name.get(n) == "dir" for n in TEST_DIR_NAMES
    ) or any(n in by_name for n in TEST_FILE_HINTS)
    has_docs_dir = any(by_name.get(n) == "dir" for n in DOC_DIR_NAMES)
    has_contributing = any(n.startswith("contributing") for n in by_name)
    license_matches = [n for n in by_name if n.startswith("license") and by_name.get(n) == "file"]
    has_license = len(license_matches) > 0
    dependency_files_found = [f for f in DEPENDENCY_FILES if f.lower() in by_name]
    lock_files_found = [
        original_case[f.lower()] for f in LOCK_FILES if f.lower() in by_name
    ]

    return {
        "has_tests": has_tests,
        "has_docs_dir": has_docs_dir,
        "has_contributing": has_contributing,
        "has_license": has_license,
        "license_filename": original_case[license_matches[0]] if license_matches else None,
        "dependency_files_found": dependency_files_found,
        "lock_files_found": lock_files_found,
    }


def compute_doc_score(
    readme_text: Optional[str],
    has_contributing: bool,
    has_license: bool,
    has_docs_dir: bool,
) -> float:
    """0-100 documentation score. Deliberately simple and explainable: a
    real, substantial README is worth the most since it's what most people
    actually read; CONTRIBUTING/LICENSE/docs/ each add a smaller amount for
    signaling a more complete project."""
    score = 0.0
    stripped = (readme_text or "").strip()
    if len(stripped) > 300:
        score += 60
    elif len(stripped) > 0:
        score += 30
    if has_contributing:
        score += 15
    if has_license:
        score += 15
    if has_docs_dir:
        score += 10
    return min(100.0, score)
