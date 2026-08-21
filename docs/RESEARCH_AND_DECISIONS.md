# Research and engineering decisions

## 1. 为什么使用结构化输出

自然语言文案无法稳定表达“对象数量、状态、必须出现、禁止出现、文字安全区”等约束。工作站把这些字段固化为 Pydantic Schema，并在模型返回后本地校验。

参考：

- OpenAI Structured Outputs: https://platform.openai.com/docs/guides/structured-outputs
- Pydantic JSON Schema: https://docs.pydantic.dev/latest/concepts/json_schema/

## 2. 为什么把最终中文从图片模型中拿出来

图片模型适合生成视觉素材，但最终品牌识别还取决于字号、边距、页码、标签、卡片和重复符号。将这些设计决策保存为令牌并由确定性渲染器执行，可以把随机变化限制在素材层。

参考：

- Design Tokens Format Module: https://design-tokens.github.io/community-group/format/
- OpenAI Image Generation: https://platform.openai.com/docs/guides/image-generation

## 3. 为什么保留参考图，但不把它当唯一办法

参考图能增强材质、色温和构图连续性，但不同模型、端点和图片编辑能力并不一致。Brand DNA、固定排版和 Prompt 合同必须在没有参考图输入时仍然工作；参考图是增强层，而不是唯一控制层。

## 4. 为什么保存历史记忆

品牌一致和内容重复不是一回事。系统读取近期主题和视觉主体，要求新作品保持视觉语法但改变局部构图，避免连续发布同一标题结构和同一摆盘。

## 5. 为什么默认保留 AI 披露

中国《人工智能生成合成内容标识办法》自 2025 年 9 月 1 日起施行，用户发布生成合成内容时应主动声明并使用平台提供的标识功能。工作站在页脚和发布检查中保留披露文案，但最终仍需使用发布平台当期提供的标识入口。

官方文件：

- https://www.cac.gov.cn/2025-03/14/c_1743654684782215.htm
