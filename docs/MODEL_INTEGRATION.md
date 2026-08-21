# Model integration

## 文本：OpenAI-compatible Chat Completions

工作站使用标准 HTTP 请求而不是绑定某一家 SDK：

```text
POST {MW_LLM_BASE_URL}/chat/completions
Authorization: Bearer {MW_LLM_API_KEY}
```

### 智谱通用 API

```dotenv
MW_LLM_PROVIDER=openai_compatible
MW_LLM_BASE_URL=https://open.bigmodel.cn/api/paas/v4
MW_LLM_API_KEY=...
MW_LLM_MODEL=glm-5.2
MW_LLM_JSON_SCHEMA=false
```

智谱官方通用端点与 OpenAI 兼容说明：

- https://docs.bigmodel.cn/cn/api/introduction
- https://docs.bigmodel.cn/cn/guide/develop/openai/introduction

Coding Plan 使用独立端点和套餐 Key。是否允许把 Coding Plan 用于此类非编码内容生成，应按当期套餐条款和官方文档确认，工作站不绕过套餐限制。

### OpenAI

```dotenv
MW_LLM_PROVIDER=openai_compatible
MW_LLM_BASE_URL=https://api.openai.com/v1
MW_LLM_API_KEY=...
MW_LLM_MODEL=gpt-5-mini
MW_LLM_JSON_SCHEMA=true
```

OpenAI 官方文档：

- https://platform.openai.com/docs/guides/structured-outputs
- https://platform.openai.com/docs/api-reference/chat

若 Provider 支持 JSON Schema，工作站先请求严格结构；不支持则退回 Schema Prompt，并继续由 Pydantic 做强校验。

## 图片

### Mock

零成本测试整体流程。生成的是确定性抽象素材，不能代表真实摄影质量。

### Manual

1. 工作站输出 `prompts/XX.txt`；
2. 在 ChatGPT、Codex 或其他工具生成无文字图；
3. 上传至项目 `raw/XX.png`；
4. 执行 `rerender`。

这是最稳的跨平台模式，因为排版和品牌骨架仍由本地控制。

### OpenAI Images

```dotenv
MW_IMAGE_PROVIDER=openai
MW_IMAGE_BASE_URL=https://api.openai.com/v1
MW_IMAGE_API_KEY=...
MW_IMAGE_MODEL=gpt-image-2
MW_IMAGE_SIZE=1024x1536
MW_IMAGE_QUALITY=high
```

官方指南：

- https://platform.openai.com/docs/guides/image-generation
- https://platform.openai.com/docs/api-reference/images

打开 `MW_IMAGE_USE_REFERENCE_EDIT=true` 后，若 Approved References 存在，Provider 会尝试图片编辑接口；端点或模型不接受多图时自动退回纯文本生成。

## 多模态审查

```dotenv
MW_VISION_PROVIDER=openai_compatible
MW_VISION_BASE_URL=https://api.openai.com/v1
MW_VISION_API_KEY=...
MW_VISION_MODEL=gpt-5-mini
```

多模态审查会看到图片和 VisualBrief，但它仍然可能判断错误。报告是重试依据，不是事实证明。
