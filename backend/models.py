"""Pydantic models for request validation and response shaping."""

import json
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class RepoAnalyzeRequest(BaseModel):
    url: str = Field(..., description="GitHub repository URL, e.g. https://github.com/owner/repo")
    token: Optional[str] = Field(None, description="Optional GitHub personal access token")
    force_refresh: bool = Field(
        False, description="Bypass the cache and always re-fetch fresh data from GitHub"
    )


class RefreshRequest(BaseModel):
    token: Optional[str] = Field(None, description="Optional GitHub personal access token")


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000, description="A question about this repository")


class RepoResponse(BaseModel):
    id: int
    owner: str
    name: str
    full_name: str
    description: Optional[str] = None
    stars: int
    forks: int
    open_issues: int
    language: Optional[str] = None
    url: Optional[str] = None
    last_commit_at: Optional[str] = None
    open_pr_count: int = 0
    stale_pr_count: int = 0
    health_score: int = 0
    risk_flags: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    predicted_category: Optional[str] = None
    predicted_category_confidence: Optional[float] = None
    ml_health_label: Optional[str] = None
    ml_health_confidence: Optional[float] = None
    source: str = "github"
    branch: Optional[str] = None
    contributor_count: Optional[int] = None
    first_commit_at: Optional[str] = None
    branches: List[str] = Field(default_factory=list)
    contributors: List[dict] = Field(default_factory=list)
    languages: dict = Field(default_factory=dict)
    commit_activity: List[dict] = Field(default_factory=list)
    health_status: Optional[str] = None
    health_breakdown: dict = Field(default_factory=dict)
    ci_cd: Optional[dict] = None
    dependencies: Optional[dict] = None
    releases: List[dict] = Field(default_factory=list)
    issue_analysis: Optional[dict] = None
    pr_analysis: Optional[dict] = None
    contributor_analysis: Optional[dict] = None
    release_analysis: Optional[dict] = None
    branch_analysis: Optional[dict] = None
    testing_analysis: Optional[dict] = None
    documentation_analysis: Optional[dict] = None
    license_info: Optional[dict] = None
    topics: List[str] = Field(default_factory=list)
    is_favorite: bool = False
    from_cache: bool = False
    cached_at: Optional[str] = None
    created_at: str
    updated_at: str

    @field_validator(
        "branches", "contributors", "commit_activity", "releases", "topics", mode="before"
    )
    @classmethod
    def _parse_json_list(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return value or []

    @field_validator("languages", "health_breakdown", mode="before")
    @classmethod
    def _parse_json_dict(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return {}
        return value or {}

    @field_validator(
        "ci_cd", "dependencies", "issue_analysis", "pr_analysis", "contributor_analysis",
        "release_analysis", "branch_analysis", "testing_analysis",
        "documentation_analysis", "license_info",
        mode="before",
    )
    @classmethod
    def _parse_json_dict_optional(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return None
        return value

    @field_validator("risk_flags", mode="before")
    @classmethod
    def _parse_risk_flags(cls, value):
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return []
        return value or []


class SimilarRepoResponse(BaseModel):
    id: int
    full_name: str
    score: float
    similarity_percentage: float = 0.0
    reasons: List[str] = Field(default_factory=list)


class AnomalyResultResponse(BaseModel):
    id: int
    full_name: str
    is_anomaly: bool
    anomaly_score: float


class AnomalyReportResponse(BaseModel):
    available: bool
    min_repos_required: int = 5
    results: List[AnomalyResultResponse] = Field(default_factory=list)
