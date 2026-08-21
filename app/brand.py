from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CanvasSpec(BaseModel):
    width: int = Field(default=1080, ge=600, le=4000)
    height: int = Field(default=1440, ge=800, le=5000)
    safe_margin: int = Field(default=72, ge=20, le=300)
    corner_radius: int = Field(default=32, ge=0, le=200)


class PaletteSpec(BaseModel):
    paper: str = "#F4E9D8"
    ink: str = "#1F2A24"
    muted: str = "#68716B"
    primary: str = "#4F7A61"
    accent: str = "#C96645"
    card: str = "#FFFDF8"
    line: str = "#8FA18F"

    @field_validator("*")
    @classmethod
    def validate_hex(cls, value: str) -> str:
        value = value.strip().upper()
        if len(value) != 7 or not value.startswith("#"):
            raise ValueError("palette values must be #RRGGBB")
        int(value[1:], 16)
        return value


class TypographySpec(BaseModel):
    sans_candidates: list[str] = Field(default_factory=list)
    serif_candidates: list[str] = Field(default_factory=list)
    title_size: int = Field(default=76, ge=30, le=160)
    h2_size: int = Field(default=52, ge=24, le=120)
    body_size: int = Field(default=30, ge=16, le=64)
    small_size: int = Field(default=22, ge=12, le=48)
    line_spacing: float = Field(default=1.25, ge=0.8, le=2.2)


class LayoutSpec(BaseModel):
    title_max_lines: int = Field(default=3, ge=1, le=5)
    body_max_lines: int = Field(default=8, ge=2, le=20)
    card_gap: int = Field(default=18, ge=0, le=80)
    footer_height: int = Field(default=56, ge=24, le=120)
    image_radius: int = Field(default=36, ge=0, le=120)
    signature_position: str = "bottom-left"


class VisualLanguageSpec(BaseModel):
    medium: str
    subject_rule: str
    camera: str
    lighting: str
    background: str
    texture: str
    prop_rule: str
    signature_motif: str
    continuity_rules: list[str] = Field(default_factory=list)
    negative_rules: list[str] = Field(default_factory=list)


class CopySpec(BaseModel):
    account_name: str
    tagline: str
    footer_left: str = "AI辅助制图｜内容经人工核对"
    footer_right: str = "事实需按来源与个人情况核对"
    ai_disclosure: str = "AI辅助整理与制图，发布前经人工核对"
    tone_rules: list[str] = Field(default_factory=list)


class BrandSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    version: str
    canvas: CanvasSpec
    palette: PaletteSpec
    typography: TypographySpec
    layout: LayoutSpec
    visual: VisualLanguageSpec
    copywriting: CopySpec = Field(alias="copy", serialization_alias="copy")

    def canonical_dict(self) -> dict:
        return self.model_dump(mode="json", exclude_none=True, by_alias=True)

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(
            self.canonical_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    @property
    def style_id(self) -> str:
        return f"{self.name}@{self.version}+{self.fingerprint}"

    def prompt_anchor(self) -> str:
        continuity = "；".join(self.visual.continuity_rules)
        negatives = "；".join(self.visual.negative_rules)
        return (
            f"品牌视觉身份：{self.name}，版本 {self.version}。"
            f"媒介：{self.visual.medium}。主体规则：{self.visual.subject_rule}。"
            f"镜头：{self.visual.camera}。光线：{self.visual.lighting}。"
            f"背景：{self.visual.background}。材质：{self.visual.texture}。"
            f"道具：{self.visual.prop_rule}。固定识别符号：{self.visual.signature_motif}。"
            f"连续性规则：{continuity}。禁止：{negatives}。"
        )


def load_brand(path: Path) -> BrandSpec:
    if not path.exists():
        raise FileNotFoundError(f"Brand file not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return BrandSpec.model_validate(data)
