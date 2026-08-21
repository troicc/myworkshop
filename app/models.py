from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Severity(str, Enum):
    info = "info"
    warning = "warning"
    high = "high"


class ProjectStatus(str, Enum):
    created = "created"
    planning = "planning"
    generating = "generating"
    reviewing = "reviewing"
    rendering = "rendering"
    completed = "completed"
    failed = "failed"


class StoryBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=4, max_length=100)
    audience: str = Field(default="忙碌的普通用户", min_length=2, max_length=80)
    scenario: str = Field(default="日常可执行的生活场景", min_length=2, max_length=120)
    objective: str = Field(
        default="提供清晰、可收藏、可执行的解决方案", min_length=4, max_length=160
    )
    slide_count: int = Field(default=5, ge=3, le=10)
    source_notes: list[str] = Field(default_factory=list, max_length=20)
    avoid_claims: list[str] = Field(default_factory=list, max_length=20)
    call_to_action: str = Field(default="收藏备用，下次照着做", max_length=80)
    locale: str = Field(default="zh-CN", max_length=20)

    @field_validator("title", "audience", "scenario", "objective", "call_to_action")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return " ".join(value.strip().split())


class Claim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=2, max_length=240)
    source: str | None = Field(default=None, max_length=500)
    needs_verification: bool = True
    risk: Literal["low", "medium", "high"] = "low"


class VisualBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_subject: str = Field(min_length=2, max_length=200)
    exact_count: int | None = Field(default=None, ge=1, le=30)
    subject_state: str = Field(default="真实、完整、无夸张", max_length=240)
    must_show: list[str] = Field(default_factory=list, max_length=15)
    must_not_show: list[str] = Field(default_factory=list, max_length=20)
    camera: str = Field(default="45度轻俯视", max_length=160)
    composition: str = Field(default="单一主视觉，信息清楚，保留文字安全区", max_length=240)
    lighting: str = Field(default="柔和自然侧光", max_length=160)
    background: str = Field(default="低对比度暖米色生活场景", max_length=160)
    text_safe_area: Literal["top", "bottom", "left", "right", "none"] = "top"
    layout_hint: Literal["hero", "grid", "steps", "comparison", "minimal"] = "hero"

    @model_validator(mode="after")
    def ensure_no_conflict(self) -> VisualBrief:
        overlap = {item.strip() for item in self.must_show} & {
            item.strip() for item in self.must_not_show
        }
        if overlap:
            raise ValueError(f"must_show and must_not_show overlap: {sorted(overlap)}")
        return self


SlideKind = Literal["cover", "cards", "steps", "checklist", "sources"]


class SlidePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int = Field(ge=1, le=20)
    kind: SlideKind
    headline: str = Field(min_length=2, max_length=60)
    subheadline: str = Field(default="", max_length=100)
    body_points: list[str] = Field(default_factory=list, max_length=12)
    visual: VisualBrief | None = None
    claims: list[Claim] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_slide(self) -> SlidePlan:
        if self.kind != "sources" and self.visual is None:
            raise ValueError("non-source slides require a visual brief")
        if self.kind == "sources" and not self.body_points:
            raise ValueError("source slide requires at least one source or verification note")
        return self


class ContentPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_title: str = Field(min_length=4, max_length=100)
    audience: str = Field(min_length=2, max_length=100)
    core_promise: str = Field(min_length=4, max_length=180)
    style_version: str = Field(default="unassigned", max_length=80)
    slides: list[SlidePlan] = Field(min_length=3, max_length=10)
    caption: str = Field(min_length=10, max_length=2000)
    tags: list[str] = Field(default_factory=list, max_length=15)

    @model_validator(mode="after")
    def normalize_and_validate_indices(self) -> ContentPlan:
        indices = [slide.index for slide in self.slides]
        expected = list(range(1, len(self.slides) + 1))
        if indices != expected:
            raise ValueError(f"slide indices must be sequential: expected {expected}, got {indices}")
        if self.slides[0].kind != "cover":
            raise ValueError("first slide must be cover")
        return self


class RiskFlag(BaseModel):
    code: str
    severity: Severity
    message: str
    excerpt: str = ""
    suggestion: str = ""


class ComplianceReport(BaseModel):
    passed: bool
    flags: list[RiskFlag] = Field(default_factory=list)


class CriticReport(BaseModel):
    passed: bool
    score: int = Field(ge=0, le=100)
    issues: list[str] = Field(default_factory=list)
    observations: list[str] = Field(default_factory=list)
    retry_instruction: str = ""


class ProjectManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str
    title: str
    status: ProjectStatus = ProjectStatus.created
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    brand_name: str = ""
    brand_version: str = ""
    brand_fingerprint: str = ""
    llm_provider: str = ""
    image_provider: str = ""
    slide_count: int = 0
    output_files: list[str] = Field(default_factory=list)
    error: str = ""

    def touch(self, status: ProjectStatus | None = None) -> None:
        self.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if status is not None:
            self.status = status


class GenerateRequest(StoryBrief):
    """API request model kept separate for future web-only fields."""


class ProjectSummary(BaseModel):
    project_id: str
    title: str
    status: ProjectStatus
    created_at: str
    output_files: list[str] = Field(default_factory=list)
