from __future__ import annotations

from app.compliance import scan_content
from app.models import StoryBrief


def test_high_risk_claim_is_flagged() -> None:
    report = scan_content(StoryBrief(title="脸越吃越干净的8种食物"))
    assert report.passed is False
    assert any(flag.code == "beauty-guarantee" for flag in report.flags)


def test_normal_operational_title_passes_keyword_scan() -> None:
    report = scan_content(StoryBrief(title="早八来不及做饭｜8套10分钟早餐"))
    assert report.passed is True
