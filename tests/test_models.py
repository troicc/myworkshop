from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.models import ContentPlan, StoryBrief, VisualBrief


def test_story_brief_normalizes_whitespace() -> None:
    brief = StoryBrief(title="  早八   早餐  ")
    assert brief.title == "早八 早餐"


def test_visual_contract_rejects_conflict() -> None:
    with pytest.raises(ValidationError):
        VisualBrief(
            primary_subject="早餐",
            must_show=["品牌包装"],
            must_not_show=["品牌包装"],
        )


def test_content_plan_requires_cover_first() -> None:
    with pytest.raises(ValidationError):
        ContentPlan.model_validate(
            {
                "project_title": "一个足够长的项目标题",
                "audience": "上班族",
                "core_promise": "给出可执行的解决方案",
                "slides": [
                    {
                        "index": 1,
                        "kind": "cards",
                        "headline": "第一页",
                        "visual": {"primary_subject": "早餐"},
                    },
                    {
                        "index": 2,
                        "kind": "checklist",
                        "headline": "第二页",
                        "visual": {"primary_subject": "清单"},
                    },
                    {
                        "index": 3,
                        "kind": "sources",
                        "headline": "来源",
                        "body_points": ["人工核验"],
                    },
                ],
                "caption": "这是一段足够长度的测试发布文案。",
            }
        )
