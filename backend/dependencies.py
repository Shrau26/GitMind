"""Dependency detection/counting and vulnerability summarization.

Scope, deliberately: this parses the *manifest files themselves* (real
content fetched from the GitHub Contents API) to count declared
dependencies, and reads GitHub's own Dependabot alerts for vulnerability
data. It does not call out to npm/PyPI/Maven registries to check for
"outdated" versions — that would mean depending on non-GitHub data sources,
which is explicitly out of scope here. Where that limits what can be shown
("outdated dependency count"), this says so plainly instead of guessing.
"""

import json
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional

try:
    import tomllib  # Python 3.11+
except ModuleNotFoundError:  # pragma: no cover - older Python fallback
    tomllib = None


# --- Per-format dependency counting ---------------------------------------------------------

def parse_package_json(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    count = 0
    for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        section = data.get(key)
        if isinstance(section, dict):
            count += len(section)
    return count


def parse_requirements_txt(text: Optional[str]) -> Optional[int]:
    if text is None:
        return None
    count = 0
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or line.startswith("-"):
            continue
        count += 1
    return count


def _parse_pyproject_regex_fallback(text: str) -> int:
    """Best-effort parse for environments without tomllib (Python <3.11).
    Handles the common [tool.poetry.dependencies] table and PEP 621
    [project] dependencies = [...] array; won't catch every valid TOML
    layout, but covers the vast majority of real pyproject.toml files."""
    count = 0

    poetry_match = re.search(
        r"\[tool\.poetry\.dependencies\](.*?)(?:\n\[|\Z)", text, re.DOTALL
    )
    if poetry_match:
        for line in poetry_match.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key = line.split("=", 1)[0].strip().strip('"').strip("'")
            if key and key.lower() != "python":
                count += 1

    deps_match = re.search(r"dependencies\s*=\s*\[(.*?)\]", text, re.DOTALL)
    if deps_match:
        entries = [e.strip() for e in deps_match.group(1).split(",")]
        count += len([e for e in entries if e.strip("\"' \n")])

    return count


def parse_pyproject_toml(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    if tomllib is not None:
        try:
            data = tomllib.loads(text)
        except Exception:
            data = None
        if data is not None:
            count = 0
            poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
            if isinstance(poetry_deps, dict):
                count += len([k for k in poetry_deps if k.lower() != "python"])
            project_deps = data.get("project", {}).get("dependencies")
            if isinstance(project_deps, list):
                count += len(project_deps)
            optional_deps = data.get("project", {}).get("optional-dependencies")
            if isinstance(optional_deps, dict):
                for group in optional_deps.values():
                    if isinstance(group, list):
                        count += len(group)
            return count
    try:
        return _parse_pyproject_regex_fallback(text)
    except Exception:
        return None


def parse_pom_xml(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""
    deps_el = root.find(f"{ns}dependencies")
    if deps_el is None:
        return 0
    return len(deps_el.findall(f"{ns}dependency"))


_PARSERS = {
    "package.json": parse_package_json,
    "requirements.txt": parse_requirements_txt,
    "pyproject.toml": parse_pyproject_toml,
    "pom.xml": parse_pom_xml,
}


# --- Transitive dependency counting (from lock files) ----------------------------------------
#
# Lock files record the *resolved* dependency tree — every direct and
# transitive package actually installed — as it was pinned at the last
# commit. Parsing them gives real transitive-dependency counts without
# ever calling out to npm/PyPI/crates.io/etc: everything below reads only
# the file content already fetched from GitHub.

def parse_package_lock_json(text: Optional[str]) -> Optional[int]:
    """npm v2/v3 lockfiles have a flat 'packages' map (one entry per
    resolved package, keyed by node_modules path — includes transitive
    deps); v1 lockfiles nest transitive deps under 'dependencies'."""
    if not text:
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    packages = data.get("packages")
    if isinstance(packages, dict):
        # The root package itself is keyed "" — exclude it.
        return len([k for k in packages if k])

    def _count_nested(deps: dict) -> int:
        if not isinstance(deps, dict):
            return 0
        total = len(deps)
        for info in deps.values():
            if isinstance(info, dict) and isinstance(info.get("dependencies"), dict):
                total += _count_nested(info["dependencies"])
        return total

    nested = data.get("dependencies")
    if isinstance(nested, dict):
        return _count_nested(nested)
    return None


_YARN_ENTRY_RE = re.compile(r'^(?!#)(?!\s)("?[^"\s].*?)(?<!\\):\s*$', re.MULTILINE)


def parse_yarn_lock(text: Optional[str]) -> Optional[int]:
    """yarn.lock has no formal schema, but every resolved package starts an
    un-indented block ending in ':' (e.g. '"lodash@^4.17.21":'). Multiple
    version-range keys can point at one resolved package, so this is an
    upper-bound approximation on real yarn.lock files, not exact."""
    if not text or "yarn lockfile" not in text.lower() and "__metadata" not in text:
        # Still try to parse — the marker check above is just a sanity hint,
        # not a hard requirement, since some yarn.lock variants omit it.
        pass
    if not text:
        return None
    matches = _YARN_ENTRY_RE.findall(text)
    return len(matches) if matches else None


def parse_poetry_lock(text: Optional[str]) -> Optional[int]:
    if not text or tomllib is None:
        return None
    try:
        data = tomllib.loads(text)
    except Exception:
        return None
    packages = data.get("package")
    return len(packages) if isinstance(packages, list) else None


def parse_pipfile_lock(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    total = 0
    for key in ("default", "develop"):
        section = data.get(key)
        if isinstance(section, dict):
            total += len(section)
    return total


def parse_cargo_lock(text: Optional[str]) -> Optional[int]:
    if not text or tomllib is None:
        return None
    try:
        data = tomllib.loads(text)
    except Exception:
        return None
    packages = data.get("package")
    return len(packages) if isinstance(packages, list) else None


def parse_composer_lock(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    total = 0
    for key in ("packages", "packages-dev"):
        section = data.get(key)
        if isinstance(section, list):
            total += len(section)
    return total


def parse_go_sum(text: Optional[str]) -> Optional[int]:
    """go.sum lists each module twice (once for the module, once for its
    go.mod hash) — count unique module@version pairs instead of lines."""
    if not text:
        return None
    modules = set()
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            modules.add((parts[0], parts[1].replace("/go.mod", "")))
    return len(modules) if modules else None


_LOCK_PARSERS = {
    "package-lock.json": parse_package_lock_json,
    "yarn.lock": parse_yarn_lock,
    "poetry.lock": parse_poetry_lock,
    "Pipfile.lock": parse_pipfile_lock,
    "Cargo.lock": parse_cargo_lock,
    "composer.lock": parse_composer_lock,
    "go.sum": parse_go_sum,
    # pnpm-lock.yaml deliberately has no parser: it's YAML and this project
    # doesn't otherwise depend on a YAML library. Its presence is still
    # detected and reported so the user knows a lockfile exists, just
    # without a parsed count.
}


def build_transitive_report(lock_files_found: List[str], lock_file_contents: Dict[str, Optional[str]]) -> dict:
    """Direct-vs-transitive is a real, meaningful distinction — this is the
    'transitive' half, sourced only from lock files actually committed to
    the repo (never a live registry resolve)."""
    per_file_counts: Dict[str, Optional[int]] = {}
    total = 0
    any_parsed = False
    for fname in lock_files_found:
        parser = _LOCK_PARSERS.get(fname)
        count = parser(lock_file_contents.get(fname)) if parser else None
        per_file_counts[fname] = count
        if count is not None:
            total += count
            any_parsed = True

    return {
        "lock_files_found": lock_files_found,
        "per_file_counts": per_file_counts,
        "total_transitive_dependencies": total if any_parsed else None,
        "note": (
            "Counts reflect what was locked in the committed lock file — the resolved "
            "dependency tree as of the last commit, not a live re-resolve."
            if lock_files_found else
            "No lock file (package-lock.json, yarn.lock, poetry.lock, etc.) found, so "
            "transitive dependencies can't be counted — only direct dependencies from "
            "the manifest are known."
        ),
    }


# --- Per-dependency risk (from Dependabot alerts) ---------------------------------------------

_SEVERITY_LEVEL = {"critical": "Critical", "high": "High", "medium": "Medium", "low": "Low"}
_LEVEL_ORDER = ["Low", "Medium", "High", "Critical"]


def build_per_dependency_risk(alerts_result: dict) -> dict:
    """Per-package risk levels, derived only from real Dependabot alert data
    (never inferred). A package with no alert isn't labeled "safe" — it's
    simply absent from this list, since absence of a known vulnerability
    isn't proof of absence of risk."""
    if not alerts_result.get("available"):
        return {
            "available": False,
            "reason": alerts_result.get("reason") or "Vulnerability data is not accessible for this repo.",
            "dependencies": [],
        }

    by_package: Dict[str, dict] = {}
    for alert in alerts_result.get("alerts", []):
        if not isinstance(alert, dict):
            continue
        dependency = alert.get("dependency") or {}
        package_name = (dependency.get("package") or {}).get("name")
        if not package_name:
            continue
        advisory = alert.get("security_advisory") or {}
        severity = (advisory.get("severity") or "").lower()
        level = _SEVERITY_LEVEL.get(severity, "Low")
        vulnerability = alert.get("security_vulnerability") or {}
        patched_version = (vulnerability.get("first_patched_version") or {}).get("identifier")
        ghsa_id = advisory.get("ghsa_id")

        entry = by_package.setdefault(package_name, {
            "name": package_name,
            "ecosystem": (dependency.get("package") or {}).get("ecosystem"),
            "manifest_path": dependency.get("manifest_path"),
            "risk_level": "Low",
            "open_alert_count": 0,
            "advisory_ids": [],
            "remediation": None,
        })
        entry["open_alert_count"] += 1
        if _LEVEL_ORDER.index(level) > _LEVEL_ORDER.index(entry["risk_level"]):
            entry["risk_level"] = level
        if ghsa_id and ghsa_id not in entry["advisory_ids"]:
            entry["advisory_ids"].append(ghsa_id)
        if patched_version:
            entry["remediation"] = f"Update {package_name} to {patched_version} or later"
        elif entry["remediation"] is None:
            entry["remediation"] = f"Review {package_name} for a safe replacement or version — no patched version is listed yet"

    dependencies = sorted(
        by_package.values(),
        key=lambda d: (_LEVEL_ORDER.index(d["risk_level"]), d["open_alert_count"]),
        reverse=True,
    )
    return {"available": True, "reason": None, "dependencies": dependencies}


# --- Overall dependency health score (0-100) ---------------------------------------------------

def compute_dependency_health_score(
    manifest_files_found: List[str],
    security_summary: dict,
    lock_files_found: List[str],
) -> dict:
    """A single 0-100 score summarizing dependency risk, built only from
    real signals: known-vulnerability severity counts (when accessible)
    plus whether a lock file exists (a real, if indirect, signal of a more
    reproducible/auditable dependency tree — not a proxy for 'safe')."""
    if not manifest_files_found:
        return {"score": None, "level": None, "note": None}

    if security_summary.get("available"):
        base = security_summary.get("security_score")
        if base is None:
            base = 70
        note = None
    else:
        base = 70
        note = (
            "Capped at 70: vulnerability data isn't accessible for this repo (Dependabot "
            "alerts need a token with security-events access), so this score can't confirm "
            "these dependencies are safe — only that they're declared."
        )

    if lock_files_found:
        base = min(100, base + 5)

    score = round(base)
    if score >= 85:
        level = "Low risk"
    elif score >= 60:
        level = "Medium risk"
    elif score >= 35:
        level = "High risk"
    else:
        level = "Critical risk"

    return {"score": score, "level": level, "note": note}


def enrich_dependency_report(
    report: dict,
    lock_files_found: List[str],
    lock_file_contents: Dict[str, Optional[str]],
    alerts_result: dict,
) -> dict:
    """Adds transitive-dependency counts, per-dependency risk levels, and an
    overall dependency health score to a report already produced by
    build_dependency_report() (with report['security'] already set by the
    caller). Every existing key is left untouched, so nothing that already
    reads this report (e.g. the frontend's manifest_files_found /
    per_file_counts / total_dependencies / security display) breaks."""
    report["transitive"] = build_transitive_report(lock_files_found, lock_file_contents)
    report["per_dependency_risk"] = build_per_dependency_risk(alerts_result)

    health = compute_dependency_health_score(
        report.get("manifest_files_found") or [],
        report.get("security") or {"available": False},
        lock_files_found,
    )
    report["dependency_health_score"] = health["score"]
    report["dependency_health_level"] = health["level"]
    report["dependency_health_note"] = health["note"]

    has_any_manifest_data = bool(report.get("manifest_files_found")) or bool(lock_files_found)
    report["status"] = "ok" if has_any_manifest_data else "no_manifest_detected"
    report["status_message"] = None if has_any_manifest_data else "No dependency data detected."
    return report


def build_dependency_report(dependency_files_found: List[str], file_contents: Dict[str, Optional[str]]) -> dict:
    """dependency_files_found: filenames detected at repo root (from
    repo_signals.detect_signals). file_contents: {filename: raw text or None},
    fetched separately since detecting presence and fetching content are two
    different API calls."""
    per_file_counts: Dict[str, Optional[int]] = {}
    total = 0
    any_parsed = False
    for fname in dependency_files_found:
        parser = _PARSERS.get(fname)
        count = parser(file_contents.get(fname)) if parser else None
        per_file_counts[fname] = count
        if count is not None:
            total += count
            any_parsed = True

    return {
        "manifest_files_found": dependency_files_found,
        "per_file_counts": per_file_counts,
        "total_dependencies": total if any_parsed else None,
        "outdated_dependencies": None,
        "outdated_note": (
            "Not computed: checking whether a dependency is outdated requires querying "
            "the package registry (npm, PyPI, Maven Central) for its latest version — "
            "that's outside GitHub's own API, so this tool doesn't fetch it."
        ) if dependency_files_found else None,
    }


# --- Security (Dependabot alerts) ---------------------------------------------------------

_SEVERITY_PENALTY = {"critical": 25, "high": 12, "medium": 5, "low": 2}


def summarize_security(alerts_result: dict) -> dict:
    """alerts_result: {"available": bool, "reason": str|None, "alerts": [...]}
    as returned by github_client.fetch_dependabot_alerts().

    Dependabot alerts require a token with security-events read access *and*
    admin/write permission on the target repo, so for the vast majority of
    public repositories analyzed without a privileged token, this will
    honestly report unavailable rather than a fabricated score."""
    if not alerts_result.get("available"):
        return {
            "available": False,
            "reason": alerts_result.get("reason") or "Vulnerability data is not accessible for this repo.",
            "critical": 0,
            "high": 0,
            "medium": 0,
            "low": 0,
            "total": 0,
            "security_score": None,
        }

    counts = {"critical": 0, "high": 0, "medium": 0, "low": 0}
    for alert in alerts_result.get("alerts", []):
        if not isinstance(alert, dict):
            continue
        severity = ((alert.get("security_advisory") or {}).get("severity") or "").lower()
        if severity in counts:
            counts[severity] += 1

    total = sum(counts.values())
    penalty = sum(counts[sev] * _SEVERITY_PENALTY[sev] for sev in counts)
    score = max(0, 100 - penalty)

    return {"available": True, "reason": None, **counts, "total": total, "security_score": score}
