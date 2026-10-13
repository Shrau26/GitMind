"""Helpers for parsing GitHub URLs and fetching repository data from the GitHub API."""

import asyncio
import base64
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import httpx

GITHUB_API_BASE = "https://api.github.com"

# Matches https://github.com/owner/repo, github.com/owner/repo,
# git@github.com:owner/repo, and owner/repo (with optional .git suffix / trailing slash).
_URL_PATTERN = re.compile(
    r"(?:github\.com[/:])?(?P<owner>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)/"
    r"(?P<repo>[A-Za-z0-9._-]+)"
)


class GitHubError(Exception):
    """Raised when the GitHub API returns an error or is unreachable."""

    def __init__(self, message: str, status_code: int = 502):
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def parse_github_url(raw_url: str) -> Tuple[str, str]:
    """Extract (owner, repo) from a GitHub URL or 'owner/repo' shorthand."""
    if not raw_url or not raw_url.strip():
        raise ValueError("Repository URL is required")

    url = raw_url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]

    match = _URL_PATTERN.search(url)
    if not match:
        raise ValueError(
            "Could not parse owner/repository from that URL. "
            "Try a format like https://github.com/owner/repo"
        )

    return match.group("owner"), match.group("repo")


def _rate_limit_message(response: httpx.Response, had_token: bool) -> str:
    """GitHub returns 403 for both 'you're rate limited' and other access
    problems (e.g. secondary rate limits, blocked IPs). Check the
    rate-limit headers rather than assuming, so the message is accurate."""
    remaining = response.headers.get("X-RateLimit-Remaining")
    reset = response.headers.get("X-RateLimit-Reset")
    if remaining == "0" and reset:
        try:
            reset_dt = datetime.fromtimestamp(int(reset), tz=timezone.utc)
            wait_min = max(1, round((reset_dt - datetime.now(timezone.utc)).total_seconds() / 60))
            when = f" It resets in about {wait_min} minute{'s' if wait_min != 1 else ''}."
        except (ValueError, OSError):
            when = ""
        if had_token:
            return f"GitHub's API rate limit has been reached for this token.{when}"
        return (
            f"GitHub's API rate limit has been reached (60 requests/hour without a token)."
            f"{when} Add a personal access token on the analyze form to raise this to 5,000/hour."
        )
    # 403 without a clearly-exhausted rate limit — usually a secondary rate
    # limit (too many requests too fast) or an access restriction.
    return "GitHub declined this request, possibly due to a temporary rate limit. Please wait a moment and try again."


async def fetch_repo_details(owner: str, repo: str, token: Optional[str] = None) -> dict:
    """Fetch basic repository details from the GitHub REST API."""
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}", headers=headers
            )
        except httpx.TimeoutException:
            raise GitHubError(
                "GitHub took too long to respond. Please try again in a moment.",
                status_code=504,
            )
        except httpx.RequestError as exc:
            raise GitHubError(f"Could not reach GitHub: {exc}", status_code=502) from exc

    if response.status_code == 404:
        # GitHub deliberately returns 404 (not 403) for private repos you
        # don't have access to, specifically so it doesn't leak whether a
        # private repo exists — the two cases are genuinely
        # indistinguishable from the API response, so the message says so
        # honestly instead of guessing which one it is.
        raise GitHubError(
            f"'{owner}/{repo}' wasn't found on GitHub. Double-check the URL — "
            "or if it's a private repository, add a personal access token with access to it.",
            status_code=404,
        )
    if response.status_code == 401:
        raise GitHubError(
            "That GitHub token isn't valid (it may be expired or malformed). "
            "Double-check it, or remove it to analyze as a public, unauthenticated request.",
            status_code=401,
        )
    if response.status_code == 403:
        raise GitHubError(_rate_limit_message(response, had_token=bool(token)), status_code=403)
    if response.status_code != 200:
        raise GitHubError(
            f"GitHub API returned an unexpected error ({response.status_code}). Please try again.",
            status_code=response.status_code,
        )

    data = response.json()
    license_info = data.get("license")
    return {
        "owner": data["owner"]["login"],
        "name": data["name"],
        "full_name": data["full_name"],
        "description": data.get("description"),
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "language": data.get("language"),
        "url": data.get("html_url"),
        "default_branch": data.get("default_branch", "main"),
        # GitHub already runs its own license-detection (the "licensee"
        # library) against every repo and exposes the result here — using
        # it is not a guess, it's GitHub's own authoritative determination.
        # None when GitHub didn't detect a recognized license.
        "license_spdx_id": license_info.get("spdx_id") if license_info else None,
        "license_name": license_info.get("name") if license_info else None,
        "topics": data.get("topics") or [],
    }


def _auth_headers(token: Optional[str]) -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def fetch_last_commit_date(
    owner: str, repo: str, token: Optional[str] = None, branch: Optional[str] = None
) -> Optional[str]:
    """Return the ISO date of the most recent commit, or None if unavailable.

    Failures here are treated as "unknown" rather than raised, since this is
    a secondary signal for the health score and shouldn't block the core
    repo-analysis flow.
    """
    params = {"per_page": 1}
    if branch:
        params["sha"] = branch
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits",
                headers=_auth_headers(token),
                params=params,
            )
        except httpx.RequestError:
            return None
    if response.status_code != 200:
        return None
    commits = response.json()
    if not commits:
        return None
    try:
        return commits[0]["commit"]["committer"]["date"]
    except (KeyError, IndexError, TypeError):
        return None


async def fetch_stale_pr_stats(
    owner: str, repo: str, token: Optional[str] = None, stale_after_days: int = 30
) -> Tuple[int, int]:
    """Return (open_pr_count, stale_pr_count) among the most recent 100 open PRs."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
                headers=_auth_headers(token),
                params={"state": "open", "per_page": 100, "sort": "created", "direction": "asc"},
            )
        except httpx.RequestError:
            return 0, 0
    if response.status_code != 200:
        return 0, 0
    pulls = response.json()
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_after_days)
    stale = 0
    for pr in pulls:
        created_at = pr.get("created_at")
        if not created_at:
            continue
        try:
            created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        except ValueError:
            continue
        if created < cutoff:
            stale += 1
    return len(pulls), stale


async def fetch_readme(
    owner: str, repo: str, token: Optional[str] = None
) -> Optional[str]:
    """Return the decoded README markdown text, or None if there isn't one."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/readme",
                headers=_auth_headers(token),
            )
        except httpx.RequestError:
            return None
    if response.status_code != 200:
        return None
    data = response.json()
    content = data.get("content")
    if not content:
        return None
    try:
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except Exception:
        return None


async def fetch_branches(
    owner: str, repo: str, token: Optional[str] = None, limit: int = 30
) -> List[str]:
    """Return up to `limit` branch names. Failures degrade to an empty list."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/branches",
                headers=_auth_headers(token),
                params={"per_page": limit},
            )
        except httpx.RequestError:
            return []
    if response.status_code != 200:
        return []
    try:
        return [b["name"] for b in response.json() if "name" in b]
    except (TypeError, KeyError):
        return []


async def fetch_contributors(
    owner: str, repo: str, token: Optional[str] = None, limit: int = 10
) -> List[dict]:
    """Return up to `limit` contributors as [{name, commits}], sorted by commit
    count descending (GitHub already returns them in that order). Failures
    degrade to an empty list — GitHub omits this endpoint's data for repos
    with a very large contributor count, so this is treated as best-effort."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contributors",
                headers=_auth_headers(token),
                params={"per_page": limit},
            )
        except httpx.RequestError:
            return []
    if response.status_code != 200:
        return []
    try:
        return [
            {"name": c.get("login", "unknown"), "commits": c.get("contributions", 0)}
            for c in response.json()
            if isinstance(c, dict)
        ]
    except (TypeError, KeyError):
        return []


async def fetch_languages(owner: str, repo: str, token: Optional[str] = None) -> dict:
    """Return {language: bytes_of_code} for the repo, as reported by GitHub's
    linguist-based detection. Failures degrade to an empty dict."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/languages",
                headers=_auth_headers(token),
            )
        except httpx.RequestError:
            return {}
    if response.status_code != 200:
        return {}
    try:
        data = response.json()
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


async def fetch_commit_activity(owner: str, repo: str, token: Optional[str] = None) -> List[dict]:
    """Return weekly commit counts for the last ~52 weeks, as
    [{week: "YYYY-MM-DD", commits: N}, ...] in chronological order.

    GitHub computes these stats asynchronously server-side: the first
    request for a repo can return 202 while it caches the result. When that
    happens we wait briefly and retry once, since the cache often finishes
    within a couple of seconds for small-to-medium repos. If it's still not
    ready after the retry, this returns an empty list — the next analysis of
    the same repo will very likely succeed."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        for attempt in range(2):
            try:
                response = await client.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repo}/stats/commit_activity",
                    headers=_auth_headers(token),
                )
            except httpx.RequestError:
                return []
            if response.status_code == 200:
                break
            if response.status_code == 202 and attempt == 0:
                await asyncio.sleep(2.5)
                continue
            return []
        else:
            return []
    try:
        weeks = response.json()
        if not isinstance(weeks, list):
            return []
        result = []
        for w in weeks:
            if not isinstance(w, dict) or "week" not in w:
                continue
            week_date = datetime.fromtimestamp(w["week"], tz=timezone.utc).date().isoformat()
            result.append({"week": week_date, "commits": w.get("total", 0)})
        return result
    except (ValueError, TypeError, OSError):
        return []


async def fetch_workflow_runs(owner: str, repo: str, token: Optional[str] = None, limit: int = 30) -> List[dict]:
    """Return up to `limit` most-recent GitHub Actions workflow runs, as
    [{name, status, conclusion, created_at, html_url}, ...], newest first.

    Important: GitHub's /actions/runs endpoint returns 200 with an empty
    list for a repo that has no workflows configured at all — it does not
    404. So an empty list from this function means "no CI/CD", which
    ci_cd.summarize_ci() reports explicitly rather than as an error."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/actions/runs",
                headers=_auth_headers(token),
                params={"per_page": limit},
            )
        except httpx.RequestError:
            return []
    if response.status_code != 200:
        return []
    try:
        data = response.json()
        runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
        return [
            {
                "name": r.get("name") or "unnamed workflow",
                "status": r.get("status"),
                "conclusion": r.get("conclusion"),
                "created_at": r.get("created_at"),
                "html_url": r.get("html_url"),
            }
            for r in runs
            if isinstance(r, dict)
        ]
    except (ValueError, TypeError):
        return []


async def fetch_releases(owner: str, repo: str, token: Optional[str] = None, limit: int = 10) -> List[dict]:
    """Return up to `limit` most-recent GitHub releases, newest first, as
    [{tag_name, name, published_at}, ...]. Failures degrade to an empty
    list — a repo with no releases looks identical to a fetch failure here,
    which is fine since both cases mean "no release data to score"."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/releases",
                headers=_auth_headers(token),
                params={"per_page": limit},
            )
        except httpx.RequestError:
            return []
    if response.status_code != 200:
        return []
    try:
        data = response.json()
        if not isinstance(data, list):
            return []
        return [
            {"tag_name": r.get("tag_name"), "name": r.get("name"), "published_at": r.get("published_at")}
            for r in data
            if isinstance(r, dict)
        ]
    except (ValueError, TypeError):
        return []


async def fetch_root_contents(owner: str, repo: str, token: Optional[str] = None) -> List[dict]:
    """Return the top-level directory listing as [{name, type, path}, ...].
    Used to detect dependency manifests, test directories, and docs — a
    single call serves several signals rather than one call per signal."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents",
                headers=_auth_headers(token),
            )
        except httpx.RequestError:
            return []
    if response.status_code != 200:
        return []
    try:
        data = response.json()
        if not isinstance(data, list):
            return []
        return [
            {"name": c.get("name"), "type": c.get("type"), "path": c.get("path")}
            for c in data
            if isinstance(c, dict)
        ]
    except (ValueError, TypeError):
        return []


async def fetch_file_content(owner: str, repo: str, path: str, token: Optional[str] = None) -> Optional[str]:
    """Return the decoded text content of a single file in the repo, or
    None if it doesn't exist / isn't a plain file / can't be fetched."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contents/{path}",
                headers=_auth_headers(token),
            )
        except httpx.RequestError:
            return None
    if response.status_code != 200:
        return None
    try:
        data = response.json()
        content = data.get("content") if isinstance(data, dict) else None
        if not content:
            return None
        return base64.b64decode(content).decode("utf-8", errors="replace")
    except Exception:
        return None


async def fetch_dependabot_alerts(owner: str, repo: str, token: Optional[str] = None) -> dict:
    """Return {"available": bool, "reason": str|None, "alerts": [...]}.

    Dependabot alerts require a token with security-events read access *and*
    admin/write permission on the target repo. For the vast majority of
    public repos analyzed without a privileged token, GitHub will return 403
    or 404 here — that's reported honestly as "not available" rather than
    treated as an error or silently producing a fabricated score."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/dependabot/alerts",
                headers=_auth_headers(token),
                params={"state": "open", "per_page": 100},
            )
        except httpx.RequestError:
            return {"available": False, "reason": "Could not reach GitHub", "alerts": []}
    if response.status_code == 200:
        try:
            data = response.json()
            return {"available": True, "reason": None, "alerts": data if isinstance(data, list) else []}
        except ValueError:
            return {"available": False, "reason": "Unexpected response from GitHub", "alerts": []}
    if response.status_code in (403, 404):
        return {
            "available": False,
            "reason": (
                "Dependabot alerts aren't accessible (this requires a token with security-events "
                "read access and admin/write permission on the repo — most public-repo analyses "
                "won't have this)."
            ),
            "alerts": [],
        }
    return {"available": False, "reason": f"GitHub returned {response.status_code}", "alerts": []}


# --- Issue analysis support -------------------------------------------------------------------

async def fetch_issue_search_counts(owner: str, repo: str, token: Optional[str] = None) -> dict:
    """Return {"available": bool, "reason": str|None, "open": int|None, "closed": int|None}.

    Uses the Search API (GET /search/issues?q=repo:{owner}/{repo}+type:issue+state:...)
    specifically because it excludes pull requests and gives an exact total
    count in one cheap call (per_page=1, we only read total_count) — the
    repo object's own open_issues_count field conflates issues and PRs.

    The Search API has a much stricter, separate rate limit than the rest of
    GitHub's API (10/min unauthenticated, 30/min authenticated), so this is
    more likely than other calls to come back unavailable — handled
    honestly rather than as a hard failure."""
    async def _count(state: str) -> Optional[int]:
        async with httpx.AsyncClient(timeout=8.0) as client:
            try:
                response = await client.get(
                    f"{GITHUB_API_BASE}/search/issues",
                    headers=_auth_headers(token),
                    params={"q": f"repo:{owner}/{repo} type:issue state:{state}", "per_page": 1},
                )
            except httpx.RequestError:
                return None
        if response.status_code != 200:
            return None
        try:
            return response.json().get("total_count")
        except ValueError:
            return None

    open_count, closed_count = await asyncio.gather(_count("open"), _count("closed"))
    if open_count is None and closed_count is None:
        return {
            "available": False,
            "reason": "GitHub's search API wasn't reachable or its (separate, stricter) rate "
                      "limit was hit — issue counts couldn't be fetched.",
            "open": None,
            "closed": None,
        }
    return {"available": True, "reason": None, "open": open_count, "closed": closed_count}


async def fetch_open_issues_sample(owner: str, repo: str, token: Optional[str] = None, limit: int = 100) -> List[dict]:
    """Return up to `limit` open issues (pull requests excluded), oldest
    first, as [{number, title, created_at, updated_at, html_url}, ...].

    GitHub's /issues endpoint returns both issues and PRs mixed together —
    an item is actually a PR if it has a "pull_request" key, so those are
    filtered out here. Sorted oldest-created-first so the sample is biased
    toward exactly the issues most useful for "oldest open issue" and stale
    detection; for repos with more than `limit` open issues, this is a
    sample of the oldest ones, not the complete set — real data, honestly
    a sample, not a fabricated total."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/issues",
                headers=_auth_headers(token),
                params={"state": "open", "per_page": limit, "sort": "created", "direction": "asc"},
            )
        except httpx.RequestError:
            return []
    if response.status_code != 200:
        return []
    try:
        items = response.json()
    except ValueError:
        return []
    if not isinstance(items, list):
        return []
    return [
        {
            "number": i.get("number"),
            "title": i.get("title"),
            "created_at": i.get("created_at"),
            "updated_at": i.get("updated_at"),
            "html_url": i.get("html_url"),
        }
        for i in items
        if isinstance(i, dict) and "pull_request" not in i
    ]


# --- Pull request analysis support ------------------------------------------------------------

async def fetch_open_prs(owner: str, repo: str, token: Optional[str] = None, limit: int = 100) -> List[dict]:
    """Return up to `limit` open PRs as
    [{number, title, created_at, updated_at, draft, awaiting_review, html_url}, ...].

    awaiting_review is True when the PR has reviewers requested and hasn't
    had them cleared (GitHub removes a reviewer from requested_reviewers
    once they submit a review) and isn't a draft — a reasonable proxy for
    "waiting on someone", not a perfectly authoritative review-state check
    (which would need one extra API call per PR)."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
                headers=_auth_headers(token),
                params={"state": "open", "per_page": limit, "sort": "created", "direction": "asc"},
            )
        except httpx.RequestError:
            return []
    if response.status_code != 200:
        return []
    try:
        items = response.json()
    except ValueError:
        return []
    if not isinstance(items, list):
        return []
    result = []
    for pr in items:
        if not isinstance(pr, dict):
            continue
        is_draft = bool(pr.get("draft"))
        requested_reviewers = pr.get("requested_reviewers") or []
        requested_teams = pr.get("requested_teams") or []
        result.append({
            "number": pr.get("number"),
            "title": pr.get("title"),
            "created_at": pr.get("created_at"),
            "updated_at": pr.get("updated_at"),
            "draft": is_draft,
            "awaiting_review": (not is_draft) and bool(requested_reviewers or requested_teams),
            "html_url": pr.get("html_url"),
        })
    return result


async def fetch_pr_merged_count(owner: str, repo: str, token: Optional[str] = None) -> Optional[int]:
    """Exact count of merged PRs via the Search API (type:pr is:merged).
    None if the search API wasn't reachable / rate-limited."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/search/issues",
                headers=_auth_headers(token),
                params={"q": f"repo:{owner}/{repo} type:pr is:merged", "per_page": 1},
            )
        except httpx.RequestError:
            return None
    if response.status_code != 200:
        return None
    try:
        return response.json().get("total_count")
    except ValueError:
        return None


async def fetch_recent_closed_prs(owner: str, repo: str, token: Optional[str] = None, limit: int = 100) -> List[dict]:
    """Return up to `limit` most-recently-updated closed PRs as
    [{created_at, merged_at, number, html_url}, ...] — merged_at is None for
    PRs that were closed without merging. Used to compute average merge
    time from a real, recent sample (not the full history for large repos)."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/pulls",
                headers=_auth_headers(token),
                params={"state": "closed", "per_page": limit, "sort": "updated", "direction": "desc"},
            )
        except httpx.RequestError:
            return []
    if response.status_code != 200:
        return []
    try:
        items = response.json()
    except ValueError:
        return []
    if not isinstance(items, list):
        return []
    return [
        {
            "number": pr.get("number"),
            "created_at": pr.get("created_at"),
            "merged_at": pr.get("merged_at"),
            "html_url": pr.get("html_url"),
        }
        for pr in items
        if isinstance(pr, dict)
    ]


# --- Contributor analysis support -------------------------------------------------------------

async def fetch_contributor_total_count(owner: str, repo: str, token: Optional[str] = None) -> Optional[int]:
    """Exact total contributor count via GitHub's Link-header pagination
    trick: request 1 contributor per page, and the "last" page number in
    the response's Link header equals the true total count — far cheaper
    than paging through every contributor to count them. Returns None if
    the repo has too many contributors for GitHub to compute this endpoint
    at all (it 202s while computing, or 204s with no data for very large
    repos) or the request otherwise fails."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/contributors",
                headers=_auth_headers(token),
                params={"per_page": 1, "anon": "false"},
            )
        except httpx.RequestError:
            return None
    if response.status_code == 204:
        return 0
    if response.status_code != 200:
        return None
    link_header = response.headers.get("Link", "")
    match = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link_header)
    if match:
        return int(match.group(1))
    # No "last" link means everything fit on page 1 (0 or 1 contributors).
    try:
        items = response.json()
        return len(items) if isinstance(items, list) else None
    except ValueError:
        return None


# --- Release analysis support -----------------------------------------------------------------

async def fetch_release_total_count(owner: str, repo: str, token: Optional[str] = None) -> Optional[int]:
    """Exact total release count via the Link-header pagination trick (see
    fetch_contributor_total_count for the same technique). None if the
    request failed; 0 if the repo genuinely has no releases (204 or no
    Link header with an empty page)."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/releases",
                headers=_auth_headers(token),
                params={"per_page": 1},
            )
        except httpx.RequestError:
            return None
    if response.status_code != 200:
        return None
    link_header = response.headers.get("Link", "")
    match = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link_header)
    if match:
        return int(match.group(1))
    try:
        items = response.json()
        return len(items) if isinstance(items, list) else None
    except ValueError:
        return None


# --- Branch analysis support ------------------------------------------------------------------

async def fetch_branch_total_count(owner: str, repo: str, token: Optional[str] = None) -> Optional[int]:
    """Exact total branch count via the same Link-header trick."""
    async with httpx.AsyncClient(timeout=8.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/branches",
                headers=_auth_headers(token),
                params={"per_page": 1},
            )
        except httpx.RequestError:
            return None
    if response.status_code != 200:
        return None
    link_header = response.headers.get("Link", "")
    match = re.search(r'[?&]page=(\d+)>;\s*rel="last"', link_header)
    if match:
        return int(match.group(1))
    try:
        items = response.json()
        return len(items) if isinstance(items, list) else None
    except ValueError:
        return None


async def fetch_branch_activity(
    owner: str, repo: str, branch_names: List[str], token: Optional[str] = None, limit: int = 20
) -> List[dict]:
    """Return [{name, last_commit_at}, ...] for up to `limit` of the given
    branch names. GitHub's branch-list endpoint doesn't include a commit
    date, so this makes one small request per branch (the cheapest way to
    get it: /commits?sha={branch}&per_page=1, reading just the newest
    commit's date) — capped at `limit` branches to bound the request count
    for repos with many branches; this is a sample, not every branch, for
    anything beyond that cap."""
    sample = branch_names[:limit]

    async def _one(name: str) -> dict:
        async with httpx.AsyncClient(timeout=8.0) as client:
            try:
                response = await client.get(
                    f"{GITHUB_API_BASE}/repos/{owner}/{repo}/commits",
                    headers=_auth_headers(token),
                    params={"sha": name, "per_page": 1},
                )
            except httpx.RequestError:
                return {"name": name, "last_commit_at": None}
        if response.status_code != 200:
            return {"name": name, "last_commit_at": None}
        try:
            commits = response.json()
            if isinstance(commits, list) and commits:
                date = (commits[0].get("commit", {}) or {}).get("committer", {}).get("date")
                return {"name": name, "last_commit_at": date}
        except ValueError:
            pass
        return {"name": name, "last_commit_at": None}

    return list(await asyncio.gather(*(_one(n) for n in sample)))


# --- Testing analysis support -----------------------------------------------------------------

async def fetch_repo_tree(
    owner: str, repo: str, default_branch: Optional[str], token: Optional[str] = None
) -> dict:
    """Return {"available": bool, "truncated": bool, "paths": [...]} — the
    full list of file paths (blobs only, not directories) in the repo at
    its default branch, via a single call to the Git Trees API with
    recursive=1. This is what powers testing_analysis.py's repo-wide
    source/test file scan without fetching every file's content.

    "truncated" is True if GitHub's tree-size limit (~100,000 entries) was
    hit — in that case, the paths returned are a partial, not complete,
    listing, and the summary should say so rather than treat it as exact."""
    if not default_branch:
        return {"available": False, "truncated": False, "paths": []}
    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            response = await client.get(
                f"{GITHUB_API_BASE}/repos/{owner}/{repo}/git/trees/{default_branch}",
                headers=_auth_headers(token),
                params={"recursive": 1},
            )
        except httpx.RequestError:
            return {"available": False, "truncated": False, "paths": []}
    if response.status_code != 200:
        return {"available": False, "truncated": False, "paths": []}
    try:
        data = response.json()
        tree = data.get("tree", []) if isinstance(data, dict) else []
        paths = [item["path"] for item in tree if isinstance(item, dict) and item.get("type") == "blob" and "path" in item]
        return {"available": True, "truncated": bool(data.get("truncated")), "paths": paths}
    except (ValueError, TypeError, KeyError):
        return {"available": False, "truncated": False, "paths": []}
