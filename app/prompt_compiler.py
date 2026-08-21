from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.brand import BrandSpec
from app.models import ContentPlan, SlidePlan


@dataclass(frozen=True)
class CompiledPrompt:
    text: str
    sha256: str


class PromptCompiler:
    """Compile a stable visual contract instead of improvising one prompt per post."""

    def compile(
        self,
        *,
        plan: ContentPlan,
        slide: SlidePlan,
        brand: BrandSpec,
        history: list[dict[str, Any]],
        retry_instruction: str = "",
    ) -> CompiledPrompt:
        if slide.visual is None:
            raise ValueError("source slides do not require image prompts")
        visual = slide.visual
        recent_subjects: list[str] = []
        for entry in history[-8:]:
            values = entry.get("visual_subjects", [])
            if isinstance(values, list):
                recent_subjects.extend(str(value) for value in values[:4])
        continuity_memory = "；".join(recent_subjects[-12:]) or "暂无历史作品"
        must_show = "；".join(visual.must_show) or "仅保留一个明确主体"
        must_not_show = "；".join(
            [
                *visual.must_not_show,
                "任何文字",
                "汉字",
                "英文标签",
                "数字",
                "Logo",
                "水印",
                "边框模板",
                "信息图排版",
            ]
        )
        count_rule = (
            f"画面中可数的主对象必须恰好为 {visual.exact_count} 个。"
            if visual.exact_count
            else "只呈现完成叙事所需的最少对象，不堆砌。"
        )
        retry_block = f"\n上一版纠偏：{retry_instruction}\n" if retry_instruction else ""
        prompt = f"""
生成一张竖版、无文字的原始视觉素材，供后续本地中文排版使用。不要设计最终信息图。

【本页叙事任务】
整组标题：{plan.project_title}
本页标题（仅帮助理解，绝不能画进图片）：{slide.headline}
本页要点：{json.dumps(slide.body_points, ensure_ascii=False)}
目标用户：{plan.audience}

【精确视觉合同】
主视觉：{visual.primary_subject}
数量：{count_rule}
主体状态：{visual.subject_state}
必须清楚出现：{must_show}
绝对不能出现：{must_not_show}
镜头：{visual.camera}
构图：{visual.composition}
文字安全区：{visual.text_safe_area}；该区域必须是同一连续背景，不能做成卡片或面板
光线：{visual.lighting}
背景：{visual.background}
版式意图：{visual.layout_hint}

【不可变 Brand DNA】
Style ID：{brand.style_id}
{brand.prompt_anchor()}
主色关系仅作为整体色调指导：纸色 {brand.palette.paper}，主色 {brand.palette.primary}，强调色 {brand.palette.accent}，深色 {brand.palette.ink}。
同一账号的每张素材必须保持相同镜头克制、自然侧光、低饱和背景、真实份量和稀疏道具。

【跨作品连续性】
近期已经使用过的主体包括：{continuity_memory}。
不要机械复制旧构图；在不破坏 Brand DNA 的前提下，更换本页的主体关系或局部角度。

【验收标准】
1. 第一眼就能辨认本页主对象及其状态。
2. 必须出现项全部可见，禁止项一个也没有。
3. 留白位置与 VisualBrief 一致，能容纳后续中文标题和要点。
4. 像真实编辑摄影/克制插画，而不是图库拼贴、广告海报或AI信息图。
5. 不生成任何可读或伪造文字。
{retry_block}
只输出图片。
""".strip()
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        return CompiledPrompt(text=prompt, sha256=digest)
