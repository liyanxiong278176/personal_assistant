"""Prompt templates for memory extraction and promotion."""

EXTRACTION_PROMPT = """分析以下旅游对话，提取用户的结构化信息。

对话内容：
{conversation}

请提取以下类型的信息（JSON 格式）：
{{
  "memories": [
    {{
      "type": "fact|preference|intent|constraint|emotion|state",
      "content": "自然语言描述",
      "structured": {{"key": "value"}},
      "confidence": 0.0-1.0,
      "importance": 0.0-1.0
    }}
  ]
}}

记忆类型说明：
- fact: 事实信息（目的地、日期、预算、人数）
- preference: 用户偏好（喜欢美食、偏好酒店、旅行风格）
- intent: 用户意图（想看樱花、寻找性价比方案）
- constraint: 约束条件（预算限制、不能住青旅、时间限制）
- emotion: 情感状态（对价格犹豫、对景点兴奋）
- state: 对话状态（正在比较方案、待确认日期）

只返回 JSON，不要有其他内容。"""

PROMOTION_PROMPT = """评估以下短期记忆是否应该升级到长期记忆。

用户画像：
{user_profile}

待评估记忆：
- 类型: {memory_type}
- 内容: {memory_content}
- 置信度: {confidence}
- 重要性: {importance}

判断此记忆是否：
1. 反映用户的长期偏好或习惯
2. 与未来旅行规划相关
3. 足够具体和可操作

返回 JSON 格式：
{{
  "should_promote": true/false,
  "reason": "原因说明",
  "action": "add|confirm|update|conflict"
}}

- add: 添加为新偏好
- confirm: 确认现有偏好
- update: 更新现有偏好
- conflict: 与现有偏好冲突，需要用户确认

只返回 JSON，不要有其他内容。"""

MEMORY_INJECTION_PROMPT = """以下是与用户相关的历史信息，可以帮助你提供更个性化的建议：

{memories}

请根据这些信息调整你的回复风格和建议内容。"""

SYSTEM_PROMPT_WITH_MEMORY = """你是一个专业的AI旅游助手，帮助用户规划旅行、推荐景点、提供实用建议。

你的职责：
1. 根据用户需求提供个性化的旅行建议
2. 考虑用户的偏好和约束条件
3. 推荐具体的景点、餐厅、活动
4. 提供实用的交通、住宿建议
5. 回答旅行相关问题

请用友好、专业的语气回复。"""
