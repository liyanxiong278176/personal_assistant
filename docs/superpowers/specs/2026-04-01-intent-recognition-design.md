# 意图识别增强设计文档

**项目**: AI旅游助手
**阶段**: 1/4 - 意图识别增强
**日期**: 2026-04-01
**状态**: 设计已批准

---

## 1. 概述

### 1.1 目标

在现有架构基础上，实现轻量级意图识别功能，使AI能够准确判断用户意图并路由到对应的处理流程。

### 1.2 意图类型

| 意图 | 说明 | 处理方式 |
|------|------|----------|
| `itinerary` | 行程规划/调整 | 调用ItineraryAgent |
| `query` | 信息查询（天气、交通、景点等） | 调用WeatherAgent/MapAgent |
| `image` | 图片识别 | 调用VisionService |
| `chat` | 闲聊对话 | LLM直接回复 |

---

## 2. 架构设计

```
用户消息进入
    │
    ▼
┌─────────────────────────────────────────┐
│         快速关键词预判断                │
│  ┌─────────────────────────────────┐   │
│  │ 图片检测？ → 图片识别意图          │   │
│  └─────────────────────────────────┘   │
│  ┌─────────────────────────────────┐   │
│  │ 行程关键词？ → 行程规划意图        │   │
│  └─────────────────────────────────┘   │
│         │ 不确定                      │
│         ▼                             │
│  ┌─────────────────────────────────┐   │
│  │    LLM意图分类 (仅当不确定时)     │   │
│  │    分类: 查询/闲聊                 │   │
│  └─────────────────────────────────┘   │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│           路由到对应处理器                │
│  行程规划 → ItineraryAgent              │
│  信息查询 → WeatherAgent/MapAgent        │
│  图片识别 → VisionService               │
│  闲聊对话 → LLM直接回复                  │
└─────────────────────────────────────────┘
```

---

## 3. 核心组件

### 3.1 IntentClassifier

```python
class IntentClassifier:
    """轻量级意图分类器"""

    async def classify(
        self,
        message: str,
        has_image: bool = False
    ) -> IntentResult:
        """分类用户意图

        Args:
            message: 用户消息内容
            has_image: 是否包含图片附件

        Returns:
            IntentResult: 意图分类结果
        """
```

### 3.2 IntentResult 数据模型

```python
class IntentResult(BaseModel):
    """意图识别结果"""
    intent: Literal["itinerary", "query", "image", "chat"]
    confidence: float  # 0.0 - 1.0
    method: Literal["keyword", "llm", "attachment"]
    extracted_params: dict = {}  # 提取的参数（见下文ExtractedParams定义）

class ExtractedParams(BaseModel):
    """从消息中提取的参数"""
    destination: str | None = None      # 目的地，如 "北京"
    date_range: str | None = None       # 日期范围，如 "4月1日-4月5日"
    travelers: int | None = None        # 人数
    query_type: str | None = None       # 查询类型，如 "weather"/"traffic"/"poi"
    has_image: bool = False             # 是否包含图片
```

### 3.3 关键词规则配置

```python
INTENT_KEYWORDS = {
    "itinerary": {
        "keywords": ["规划", "行程", "旅游", "旅行", "几天", "日游", "去玩"],
        "weight": 1.0,
    },
    "query": {
        "keywords": ["天气", "温度", "怎么去", "交通", "门票", "开放时间", "地址"],
        "weight": 0.8,
    },
    "image": {
        "keywords": ["识别", "这是哪里", "图片", "照片"],
        "weight": 1.0,
    },
    "chat": {
        "keywords": ["你好", "在吗", "谢谢", "哈哈"],
        "weight": 0.9,
    },
}
```

---

## 4. 文件结构

### 4.1 新建文件

```
backend/app/services/
├── intent_classifier.py      # 意图分类器
├── intent_prompts.py         # 意图识别提示词
```

### 4.2 修改文件

```
backend/app/api/chat.py              # 集成意图分类
backend/app/models.py                # 添加 has_image 字段到 WSMessage
backend/app/services/llm_service.py  # 添加 get_llm_response_for_intent 方法
```

### 4.3 模型变更

**WSMessage 扩展** (backend/app/models.py):

```python
class WSMessage(BaseModel):
    # 现有字段...
    content: str
    user_id: str | None = None
    conversation_id: str | None = None

    # 新增字段
    has_image: bool = False          # 是否包含图片附件
    image_data: str | None = None    # 图片base64数据（当has_image=True时）
```

---

## 5. 数据流

```
WebSocket 收到消息
    │
    ▼
┌─────────────────────────────────────────┐
│  1. 检查是否有图片附件                   │
│     has_image → intent = "image"        │
└─────────────────────────────────────────┘
    │ 无图片
    ▼
┌─────────────────────────────────────────┐
│  2. 关键词快速匹配                       │
│     匹配到 → 直接返回意图                │
│     未匹配 → 进入下一步                  │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  3. LLM意图分类（低置信度时调用）        │
│     返回意图 + 置信度分数                 │
└─────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────┐
│  4. 意图结果                             │
│     {                                   │
│       "intent": "itinerary",            │
│       "confidence": 0.95,               │
│       "method": "keyword"               │
│     }                                   │
└─────────────────────────────────────────┘
```

---

## 6. LLM 提示词

```python
INTENT_CLASSIFICATION_PROMPT = """你是一个意图分类专家。分析用户消息，判断用户意图。

用户消息：{message}

请判断用户意图并返回JSON：
{{
  "intent": "itinerary|query|image|chat",
  "confidence": 0.0-1.0,
  "reasoning": "简要说明判断依据"
}}

意图说明：
- itinerary: 用户想要规划/调整旅行行程
- query: 用户想查询具体信息（天气、交通、景点等）
- image: 用户上传图片需要识别
- chat: 普通对话、问候、闲聊
"""
```

---

## 7. 错误处理

| 场景 | 处理方式 |
|------|----------|
| 意图识别失败 | 降级为默认意图 "chat" |
| LLM调用超时 | 使用关键词判断结果 |
| LLM置信度 < 0.5 | 使用默认意图 |
| 多个关键词匹配 | 选择权重最高的 |

---

## 8. 性能优化

### 8.1 缓存机制

```python
# 缓存键设计
cache_key = f"intent:{hashlib.md5(message.encode()).hexdigest()}"

# 缓存策略
# - 相同消息内容返回相同意图（24小时TTL）
# - 不区分用户，因为意图分类是通用的
# - LRU淘汰策略，最多缓存1000条
```

### 8.2 异步处理

- 意图识别与参数提取并行执行
- 超时控制：LLM分类超时2秒自动降级为关键词判断

### 8.3 性能目标

| 场景 | 目标耗时 |
|------|----------|
| 关键词直接命中 | < 50ms |
| LLM分类 | < 2s |
| 缓存命中 | < 10ms |

---

## 9. 集成点

### 9.1 chat.py 修改

```python
# 原有流程（保留作为参考）
# itinerary_keywords = ["规划", "行程", "旅游", "旅行", "几天", "日游"]
# has_itinerary_intent = any(kw in msg.content for kw in itinerary_keywords)

# 新流程
from app.services.intent_classifier import intent_classifier

intent_result = await intent_classifier.classify(
    message=msg.content,
    has_image=msg.has_image
)

# 根据意图路由
if intent_result.intent == "itinerary":
    # 调用行程规划Agent（原有逻辑）
    itinerary = await itinerary_agent.generate_itinerary(...)
elif intent_result.intent == "query":
    # 调用查询Agent（新增）
    if "天气" in msg.content:
        weather = await weather_service.get_weather_forecast(...)
    elif "怎么去" in msg.content:
        route = await map_service.get_route(...)
elif intent_result.intent == "image":
    # 调用图片识别服务（新增）
    result = await vision_service.recognize_image(msg.image_data)
else:
    # 直接LLM回复（原有逻辑）
    async for chunk in llm_service.stream_chat(...):
        ...
```

### 9.2 与现有代码的关系

- **保留**: chat.py 中现有的 itinerary 关键词检测作为 IntentClassifier 的内部实现
- **扩展**: 添加 LLM fallback 机制处理关键词无法覆盖的情况
- **新增**: query 和 image 意图的处理逻辑

---

## 10. 测试策略

### 10.1 单元测试

```python
# 测试关键词分类
test_classify_by_keyword()
test_classify_with_image()
test_multiple_keyword_matches()

# 测试LLM分类
test_llm_fallback_classification()
test_confidence_scoring()

# 测试边界情况
test_empty_message()
test_ambiguous_message()
```

### 10.2 集成测试

```python
# 测试完整流程
test_itinerary_intent_routing()
test_query_intent_routing()
test_image_intent_routing()
test_chat_intent_routing()
```

---

## 11. 成功标准

### 11.1 准确率测试

**测试数据集**: 100条标记好的用户消息

| 意图类型 | 测试样本数 | 目标准确率 |
|----------|-----------|-----------|
| itinerary | 30 | > 85% |
| query | 30 | > 85% |
| image | 10 | > 95%（关键词直接匹配） |
| chat | 30 | > 85% |

**测试方法**:
```python
# tests/test_intent_classifier.py
TEST_SAMPLES = [
    {"message": "帮我规划一下去北京的行程", "expected": "itinerary"},
    {"message": "北京明天天气怎么样", "expected": "query"},
    {"message": "你好，在吗", "expected": "chat"},
    # ... 更多样本
]

async def test_accuracy():
    correct = 0
    for sample in TEST_SAMPLES:
        result = await classifier.classify(sample["message"])
        if result.intent == sample["expected"]:
            correct += 1
    accuracy = correct / len(TEST_SAMPLES)
    assert accuracy > 0.85
```

### 11.2 性能标准

- [ ] 关键词分类平均耗时 < 50ms
- [ ] LLM分类平均耗时 < 2s
- [ ] 缓存命中时耗时 < 10ms

### 11.3 功能标准

- [ ] 所有测试用例通过
- [ ] 无错误处理降级失败
- [ ] 4种意图类型均可正确路由

---

## 12. 后续阶段

- **阶段2**: 记忆系统完善
- **阶段3**: 上下文管理优化
- **阶段4**: 工具调用标准化

---

*文档版本: 1.0*
*最后更新: 2026-04-01*
