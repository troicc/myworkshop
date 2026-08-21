from __future__ import annotations

from pathlib import Path

from app.brand import load_brand
from app.models import ContentPlan, SlidePlan, VisualBrief
from app.prompt_compiler import PromptCompiler


def test_prompt_contains_contract_and_brand_anchor() -> None:
    brand = load_brand(Path("brand/default/brand.yaml"))
    slide = SlidePlan(
        index=1,
        kind="cover",
        headline="8套早餐",
        body_points=["燕麦杯"],
        visual=VisualBrief(
            primary_subject="一只透明燕麦杯",
            exact_count=1,
            must_show=["燕麦层", "香蕉片"],
            must_not_show=["包装"],
        ),
    )
    plan = ContentPlan(
        project_title="早八来不及做饭｜8套早餐",
        audience="上班族",
        core_promise="提供可执行的轮换方案",
        slides=[
            slide,
            SlidePlan(
                index=2,
                kind="checklist",
                headline="执行清单",
                body_points=["提前准备"],
                visual=VisualBrief(primary_subject="整洁台面"),
            ),
            SlidePlan(
                index=3,
                kind="sources",
                headline="来源",
                body_points=["人工核验"],
            ),
        ],
        caption="这是一段足够长度的发布文案，用于测试结构。",
    )
    compiled = PromptCompiler().compile(
        plan=plan,
        slide=slide,
        brand=brand,
        history=[],
    )
    assert "恰好为 1 个" in compiled.text
    assert "香蕉片" in compiled.text
    assert brand.style_id.split("+")[0] in compiled.text
    assert "不生成任何可读或伪造文字" in compiled.text
    assert len(compiled.sha256) == 64
