from __future__ import annotations

import re
from dataclasses import dataclass

from app.models import ComplianceReport, ContentPlan, RiskFlag, Severity, StoryBrief


@dataclass(frozen=True)
class Rule:
    code: str
    pattern: re.Pattern[str]
    severity: Severity
    message: str
    suggestion: str


RULES: tuple[Rule, ...] = (
    Rule(
        "medical-treatment",
        re.compile(r"治疗|治愈|根治|药到病除|替代药物|比药.*管用"),
        Severity.high,
        "出现疾病治疗或替代药物暗示。",
        "改为一般生活信息，并删除治疗保证；必要时引用专业来源并人工审核。",
    ),
    Rule(
        "disease-claim",
        re.compile(r"降血糖|降血压|抗癌|防癌|降尿酸|逆转脂肪肝|治失眠"),
        Severity.high,
        "出现具体疾病或生理指标功效声明。",
        "改为食品标签、一般膳食搭配或就医提示，不承诺疾病效果。",
    ),
    Rule(
        "body-transformation",
        re.compile(r"暴瘦|躺瘦|月瘦|天瘦|越吃越瘦|减肥神器|瘦[0-9一二三四五六七八九十]+斤"),
        Severity.high,
        "出现确定性或快速减重承诺。",
        "改为可长期执行的饮食安排，不承诺体重变化。",
    ),
    Rule(
        "beauty-guarantee",
        re.compile(r"越吃越白|脸越吃越干净|祛斑|美白神器|抗衰神器|生发|防脱神器"),
        Severity.high,
        "出现美容、生发或外观变化保证。",
        "改为一般食材信息、护理流程或真实使用记录，避免保证结果。",
    ),
    Rule(
        "pseudo-science",
        re.compile(r"排毒|清宿便|祛湿神器|排湿毒|清肺毒|刮油"),
        Severity.warning,
        "出现缺少明确定义、容易误导的养生概念。",
        "改成可观测的做法，例如少油、补水、食材保存或配料表阅读。",
    ),
    Rule(
        "authority-impersonation",
        re.compile(r"医生不会告诉你|专家不敢说|内部秘方|祖传秘方"),
        Severity.high,
        "出现虚假权威、阴谋式或秘方表达。",
        "删除权威冒充与阴谋话术，明确资料来源和不确定性。",
    ),
)


def _collect_text(brief: StoryBrief, plan: ContentPlan | None) -> str:
    pieces: list[str] = [
        brief.title,
        brief.audience,
        brief.scenario,
        brief.objective,
        *brief.source_notes,
        *brief.avoid_claims,
    ]
    if plan is not None:
        pieces.extend([plan.project_title, plan.core_promise, plan.caption, *plan.tags])
        for slide in plan.slides:
            pieces.extend([slide.headline, slide.subheadline, *slide.body_points])
            pieces.extend(claim.text for claim in slide.claims)
    return "\n".join(piece for piece in pieces if piece)


def scan_content(brief: StoryBrief, plan: ContentPlan | None = None) -> ComplianceReport:
    text = _collect_text(brief, plan)
    flags: list[RiskFlag] = []
    for rule in RULES:
        match = rule.pattern.search(text)
        if not match:
            continue
        flags.append(
            RiskFlag(
                code=rule.code,
                severity=rule.severity,
                message=rule.message,
                excerpt=match.group(0),
                suggestion=rule.suggestion,
            )
        )
    passed = not any(flag.severity == Severity.high for flag in flags)
    return ComplianceReport(passed=passed, flags=flags)
