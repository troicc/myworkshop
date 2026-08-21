from __future__ import annotations

import json
from itertools import cycle
from typing import Any

from pydantic import ValidationError

from app.brand import BrandSpec
from app.config import Settings
from app.models import Claim, ContentPlan, SlidePlan, StoryBrief, VisualBrief
from app.providers.text import OpenAICompatibleTextProvider

PLANNER_SYSTEM_PROMPT = """
你是中文生活方式图文内容的高级编辑、信息架构师和视觉制片人。
你的任务不是写一篇散文，而是把一个标题转换为可生产、可核验、逐页明确的内容计划。

硬性规则：
1. 第一页必须是 cover；最后一页优先使用 sources，记录来源、核验状态和边界。
2. 每一页只承担一个明确任务，标题和要点不得互相重复。
3. 非 sources 页必须提供 VisualBrief：一个主视觉，明确主体、数量、状态、必须出现、禁止出现、镜头、背景和文字安全区。
4. 图片只作为无文字视觉素材，禁止要求图片模型生成中文、Logo、页码、信息图文字或水印。
5. 不得编造研究、机构、医生、营养师、测试数据、成交数据或个人经历。
6. 对营养、健康、保存时长、价格、法规等可核验事实，放入 claims，并将 needs_verification 设为 true；没有可靠来源时使用谨慎表述。
7. 禁止疾病治疗、保证减重、生发、美白、排毒、权威冒充等确定性承诺。
8. 文案要具体、自然、像真实编辑写作；避免“赋能、解锁、轻松拿捏、闭眼冲、宝藏”等泛AI套话。
9. 让整组内容形成连续叙事：问题 → 选择标准 → 具体方案 → 执行/保存 → 来源与边界。
10. 严格输出符合 JSON Schema 的一个对象，不要解释过程。
""".strip()


class ContentPlanner:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.provider: OpenAICompatibleTextProvider | None = None
        if settings.llm_provider == "openai_compatible":
            self.provider = OpenAICompatibleTextProvider(
                base_url=settings.llm_base_url,
                api_key=settings.llm_api_key,
                model=settings.llm_model,
                timeout=settings.request_timeout,
                temperature=settings.llm_temperature,
                max_tokens=settings.llm_max_tokens,
                use_json_schema=settings.llm_json_schema,
            )

    def plan(
        self,
        *,
        brief: StoryBrief,
        brand: BrandSpec,
        history: list[dict[str, Any]],
    ) -> ContentPlan:
        if self.provider is None:
            return self._mock_plan(brief, brand)

        history_summary = [
            {
                "title": item.get("title", ""),
                "core_promise": item.get("core_promise", ""),
                "visual_subjects": item.get("visual_subjects", [])[:5],
            }
            for item in history[-10:]
        ]
        schema = ContentPlan.model_json_schema()
        user_prompt = (
            f"选题简报：\n{brief.model_dump_json(indent=2)}\n\n"
            f"品牌规则：\n{brand.prompt_anchor()}\n\n"
            f"账号近期历史（用于避免重复，不可照抄）：\n"
            f"{json.dumps(history_summary, ensure_ascii=False, indent=2)}\n\n"
            f"必须输出恰好 {brief.slide_count} 页。style_version 写入 {brand.style_id}。"
        )
        data = self.provider.generate_json(
            system_prompt=PLANNER_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            schema=schema,
            schema_name="content_plan",
        )
        data = self._normalize_indices(data, brand)
        try:
            plan = ContentPlan.model_validate(data)
            self._validate_requested_count(plan, brief.slide_count)
            return plan
        except (ValidationError, ValueError) as first_error:
            repair_prompt = (
                f"上一版 JSON 未通过校验。错误：{first_error}\n"
                f"原始 JSON：{json.dumps(data, ensure_ascii=False)}\n"
                f"重新输出完整对象，恰好 {brief.slide_count} 页，并符合 Schema。"
            )
            repaired = self.provider.generate_json(
                system_prompt=PLANNER_SYSTEM_PROMPT,
                user_prompt=repair_prompt,
                schema=schema,
                schema_name="content_plan_repair",
            )
            repaired = self._normalize_indices(repaired, brand)
            plan = ContentPlan.model_validate(repaired)
            self._validate_requested_count(plan, brief.slide_count)
            return plan

    @staticmethod
    def _normalize_indices(data: dict[str, Any], brand: BrandSpec) -> dict[str, Any]:
        data = dict(data)
        data["style_version"] = brand.style_id
        slides = data.get("slides")
        if isinstance(slides, list):
            normalized: list[Any] = []
            for index, slide in enumerate(slides, start=1):
                if isinstance(slide, dict):
                    slide = dict(slide)
                    slide["index"] = index
                normalized.append(slide)
            data["slides"] = normalized
        return data

    @staticmethod
    def _validate_requested_count(plan: ContentPlan, requested: int) -> None:
        if len(plan.slides) != requested:
            raise ValueError(f"expected {requested} slides, model returned {len(plan.slides)}")

    def _mock_plan(self, brief: StoryBrief, brand: BrandSpec) -> ContentPlan:
        items = self._demo_items(brief.title)
        content_page_count = brief.slide_count - 2
        groups: list[list[tuple[str, str, str]]] = [[] for _ in range(content_page_count)]
        for index, item in enumerate(items):
            groups[index % content_page_count].append(item)

        cover_visual = VisualBrief(
            primary_subject="一张有三种早餐组合的整洁木桌，主体集中成一个视觉簇",
            exact_count=3,
            subject_state="真实可执行、份量普通、没有商业包装",
            must_show=[item[0] for item in items[:3]],
            must_not_show=["文字", "水印", "品牌包装", "人物脸部", "药品", "保健品"],
            camera="45度轻俯视，接近50毫米自然透视",
            composition="主体位于中下区域，上方保留大块干净文字安全区",
            lighting=brand.visual.lighting,
            background=brand.visual.background,
            text_safe_area="top",
            layout_hint="hero",
        )
        slides: list[SlidePlan] = [
            SlidePlan(
                index=1,
                kind="cover",
                headline=brief.title,
                subheadline="先解决时间和执行，再谈复杂营养计算",
                body_points=[item[0] for item in items[:3]],
                visual=cover_visual,
            )
        ]

        kinds = cycle(["cards", "steps", "checklist"])
        for page_index, group in enumerate(groups, start=2):
            kind = next(kinds)
            descriptions = [f"{name}：{description}" for name, description, _ in group]
            subjects = [item[2] for item in group]
            slide = SlidePlan(
                index=page_index,
                kind=kind,  # type: ignore[arg-type]
                headline=self._page_headline(page_index, kind, brief.title),
                subheadline="每个方案只保留一个动作重点",
                body_points=descriptions,
                visual=VisualBrief(
                    primary_subject="同一画面中的整齐早餐组合，形成一个统一视觉簇",
                    exact_count=max(1, len(group)),
                    subject_state="刚制作完成、食材可辨认、份量真实",
                    must_show=subjects,
                    must_not_show=[
                        "文字",
                        "数字",
                        "水印",
                        "品牌包装",
                        "夸张蒸汽",
                        "医疗符号",
                        "手部畸形",
                    ],
                    camera="45度轻俯视，镜头高度与前一页一致",
                    composition=(
                        "主体集中在画面下方三分之二，顶部和右侧保留连续留白"
                        if page_index % 2 == 0
                        else "主体集中在画面右下，左侧保留连续留白"
                    ),
                    lighting=brand.visual.lighting,
                    background=brand.visual.background,
                    text_safe_area="top" if page_index % 2 == 0 else "left",
                    layout_hint="grid" if kind == "cards" else "steps",
                ),
                claims=[
                    Claim(
                        text=description,
                        source=brief.source_notes[0] if brief.source_notes else None,
                        needs_verification=True,
                        risk="low",
                    )
                    for _, description, _ in group
                ],
            )
            slides.append(slide)

        source_points = brief.source_notes or [
            "演示计划未自动引用外部资料；正式发布前逐条核验食材、保存和过敏信息",
            "图片模型只生成无文字素材，最终中文由本地模板渲染",
            "AI辅助整理与制图，内容需根据个人情况人工核对",
        ]
        slides.append(
            SlidePlan(
                index=brief.slide_count,
                kind="sources",
                headline="来源、替换与发布边界",
                subheadline="把可核验信息与视觉表达分开保存",
                body_points=source_points,
                claims=[],
            )
        )
        caption = (
            f"{brief.title}\n\n"
            f"这组内容面向{brief.audience}，场景是{brief.scenario}。"
            "先收藏作为搭配框架，再根据自己的时间、预算、过敏情况和食材标签调整。\n\n"
            f"{brand.copywriting.ai_disclosure}。"
        )
        return ContentPlan(
            project_title=brief.title,
            audience=brief.audience,
            core_promise=brief.objective,
            style_version=brand.style_id,
            slides=slides,
            caption=caption,
            tags=["一人食", "早餐", "备餐", "上班族", "生活效率"],
        )

    @staticmethod
    def _demo_items(title: str) -> list[tuple[str, str, str]]:
        if "早餐" in title or "早八" in title:
            return [
                ("牛奶燕麦香蕉杯", "前一晚装杯，早上直接拿走", "透明杯中的燕麦、牛奶和香蕉片"),
                ("鸡蛋全麦吐司", "一口锅完成，咸口更耐吃", "全麦吐司、切开的水煮蛋和少量生菜"),
                ("酸奶水果碗", "水果切小块，口感和份量更统一", "白色酸奶碗、蓝莓和苹果块"),
                ("玉米鸡蛋组合", "蒸煮可同时完成，减少看火时间", "一段甜玉米和一枚去壳鸡蛋"),
                ("花生酱香蕉吐司", "抹酱薄一些，避免画面和口感过重", "全麦吐司上的薄层花生酱和香蕉片"),
                ("饭团与无糖豆浆", "米饭提前分装，早上只做复热", "小饭团和一杯无品牌豆浆"),
                ("奶酪番茄贝果", "食材层数少，拿取不容易散", "半个贝果、奶酪片和番茄片"),
                ("冷冻杂粮粥", "按一人份冷冻，前一晚转冷藏", "白碗中的杂粮粥和简洁木勺"),
            ]
        if "蔬菜" in title or "买菜" in title or "保存" in title:
            return [
                ("胡萝卜", "按一次用量分装，减少反复拿取", "完整胡萝卜与透明分装盒"),
                ("卷心菜", "保留完整叶球，需要时再切", "完整卷心菜与干燥厨房纸"),
                ("西兰花", "按小朵分开并保持表面干燥", "西兰花小朵与带孔沥水篮"),
                ("彩椒", "整颗保存，切开后尽快使用", "三色彩椒与简洁保鲜盒"),
                ("洋葱", "放在干燥通风处并远离潮湿", "完整洋葱与通风网篮"),
                ("南瓜", "切开后密封并标注日期", "南瓜切面、保鲜盒与空白标签"),
                ("蘑菇", "避免积水，用透气纸袋短期保存", "新鲜蘑菇与牛皮纸袋"),
                ("小番茄", "先挑出破损果，食用前再清洗", "小番茄、浅盘和干燥布面"),
            ]
        return [
            ("方案一", "准备动作控制在一个核心步骤", "一个清晰的生活用品组合"),
            ("方案二", "优先使用家中已有材料", "两个有明确功能差异的物件"),
            ("方案三", "减少重复清洗和搬运", "整洁台面上的单一工具组合"),
            ("方案四", "把高频动作放在顺手位置", "真实居家角落与收纳容器"),
            ("方案五", "一次只调整一个变量", "一组前后状态清楚的物件"),
            ("方案六", "保留可替换方案避免卡住", "主物件与一个替代物件"),
            ("方案七", "按实际频率决定是否购买", "普通无品牌生活物品"),
            ("方案八", "记录执行成本再决定放大", "纸笔、计时器与简单物品"),
        ]

    @staticmethod
    def _page_headline(page_index: int, kind: str, title: str) -> str:
        if "早餐" in title or "早八" in title:
            options = {
                "cards": "前一晚能完成的组合",
                "steps": "只用一个锅的咸口方案",
                "checklist": "冷藏、冷冻与替换方法",
            }
        else:
            options = {
                "cards": "先从最容易执行的开始",
                "steps": "把动作拆成三个小步骤",
                "checklist": "发布前再检查这几项",
            }
        return options[kind] if page_index < 8 else f"第{page_index - 1}组可执行方案"
