# MyWorkshop

面向小红书图文账号的 **AI 辅助、品牌一致、可审计内容工作站**。

它不是“把标题直接扔给图片模型”的脚本，而是把生产流程拆成可检查的内容合同：

```text
标题 / 选题
  → StoryBrief（人群、场景、承诺、禁区）
  → ContentPlan（逐页文案与事实声明）
  → VisualBrief（主体、数量、状态、必须出现/禁止出现）
  → 无文字视觉素材
  → 自动审查与定向重试
  → 本地确定性中文排版
  → 归档、导出、历史记忆
```

## 为什么这样做

- **精准**：每页都必须通过结构化的 VisualBrief，而不是依赖一段模糊自然语言。
- **统一**：颜色、字体、留白、镜头、背景、签名符号集中在 `brand/default/brand.yaml`。
- **可控**：图片模型只生成无文字素材；中文标题、页码、标签由 Pillow 固定渲染。
- **可复用**：每次项目保存 Prompt、原图、审查报告、成品与品牌指纹。
- **可切换模型**：文本支持 Mock 与 OpenAI-compatible Chat Completions；图片支持 Mock、手工回填和 OpenAI Images。
- **默认安全**：对食品、减肥、生发、疾病治疗等高风险表达做提示，不把未经核验的功效结论直接进入成品。

## 5 分钟启动

要求 Python 3.10+。

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# 不需要 API Key，先跑完整流程
python -m app.cli doctor
python -m app.cli demo

# 打开网页工作台
python -m app.cli run
```

浏览器访问：`http://127.0.0.1:8000`

Mock 模式会在 `workspace/projects/` 生成一套可直接检查的 1080×1440 图文。它用于验证流程、排版和品牌系统，不代表真实图片模型的最终摄影质量。

## 接入 GLM / 其他 OpenAI-compatible 文本模型

`.env`：

```dotenv
MW_LLM_PROVIDER=openai_compatible
MW_LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
MW_LLM_API_KEY=your_key
MW_LLM_MODEL=glm-5.2
MW_LLM_JSON_SCHEMA=false
```

通用接口使用 `/chat/completions`。若提供方不支持 `json_schema`，工作站会使用“Schema Prompt → JSON 提取 → Pydantic 校验”的兼容路径。

## 接入 OpenAI 图片 API

```dotenv
MW_IMAGE_PROVIDER=openai
MW_IMAGE_BASE_URL=https://api.openai.com/v1
MW_IMAGE_API_KEY=your_key
MW_IMAGE_MODEL=gpt-image-2
MW_IMAGE_SIZE=1024x1536
MW_IMAGE_QUALITY=high
```

也可以使用 `MW_IMAGE_PROVIDER=manual`：工作站先导出逐页精准 Prompt，你在任意生图工具中生成无文字素材后，将图片放回 `raw/`，再执行重排版。

## 常用命令

```bash
python -m app.cli demo
python -m app.cli generate --title "早八来不及做饭｜8套10分钟早餐"
python -m app.cli rerender <project_id>
python -m app.cli brand-preview
python -m app.cli doctor
python -m app.cli run --host 127.0.0.1 --port 8000
pytest -q
```

## 项目输出

```text
workspace/projects/<project-id>/
├── brief.json
├── plan.json
├── manifest.json
├── compliance.json
├── prompts/
├── raw/
├── reviews/
├── output/
├── caption.md
└── export.zip
```

## 目录

- `app/models.py`：内容合同与视觉合同
- `app/planner.py`：标题到结构化内容计划
- `app/prompt_compiler.py`：品牌规则与视觉合同编译
- `app/providers/`：文本、图片与视觉审查 Provider
- `app/render.py`：确定性中文排版
- `app/pipeline.py`：端到端编排
- `app/web.py`：网页工作台
- `brand/default/brand.yaml`：Brand DNA
- `docs/`：架构、运营流程、风格校准与模型接入

## 重要边界

本项目帮助组织资料、标记风险和保存来源状态，**不自动证明营养、医疗或产品功效为真**。涉及健康、疾病、减肥、生发、孕妇、儿童等内容时，发布前必须由人工核验原始来源与平台规则。

## License

MIT
