# Phase 1: 上下��管理系统设计规范

**日期**: 2026-04-04
**版本**: 1.0
**状态**: 设计阶段

---

## 1. 概述

### 1.1 目标

实现统一工作流程 v2.0 中的上下文管理功能，包括：

- **Step 0**: 会话初始化（上下文窗口配置、核心文件注入）
- **阶段 3**: 上下文前置清理（TTL检查、软修剪、硬清除）
- **阶段 7**: 上下文后置管理（摘要压缩、核心规则重注入）

### 1.2 设计原则

1. **渐进式改进**: 在现有代码基础上添加功能，保持向后兼容
2. **混合模式**: 支持自动+手动两种压缩触发方式
3. **启动缓存**: 核心规则文件在启动时加载到内存
4. **DeepSeek优先**: 摘要压缩使用项目已有的 DeepSeek API

---

## 2. 架构设计

### 2.1 模块结构

```
backend/app/core/context/
├── __init__.py       # 模块导出
├── config.py         # ContextConfig 配置类
├── guard.py          # ContextGuard 主类
├── cleaner.py        # Cleaner 前置清理器
├── compressor.py     # Compressor 后置压缩器
└── reinjector.py     # RuleReinjector 规则重注入器
```

### 2.2 核心类图

```
┌─────────────────────────────────────────────────────────┐
│                    ContextGuard                         │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐    │
│  │ContextConfig│  │  Cleaner   │  │ Compressor  │    │
│  │• window_size│  │• TTL检查   │  │• 摘要压缩   │    │
│  │• trim_ratio│  │• 软修剪    │  │• LLM调用    │    │
│  │• rules_cache│ │• 硬清除    │  │• 裁剪替换   │    │
│  └─────────────┘  └─────────────┘  └─────────────┘    │
│                  ┌─────────────┐                       │
│                  │RuleReinjector│                      │
│                  │• 规则重注入  │                       │
│                  └─────────────┘                       │
├─────────────────────────────────────────────────────────┤
│ pre_process(messages)   → List[Dict]                   │
│ post_process(messages)  → List[Dict]                   │
│ should_compress(messages) → bool                       │
│ force_compress(messages) → List[Dict]                  │
└─────────────────────────────────────────────────────────┘
```

### 2.3 处理流程

```
                    用户消息
                       │
                       ▼
    ┌──────────────��───────────────────────┐
    │         阶段 3: 前置清理             │
    │  ┌────────────────────────────────┐  │
    │  │ 1. TTL 检查                   │  │
    │  │ 2. 软修剪 (超长结果保留首尾)   │  │
    │  │ 3. 硬清除 (过期结果替换占位符) │  │
    │  └────────────────────────────────┘  │
    └──────────────────────────────────────┘
                       │
                       ▼
              LLM 推理 (阶段 5-6)
                       │
                       ▼
    ┌──────────────────────────────────────┐
    │         阶段 7: 后置管理             │
    │  ┌────────────────────────────────┐  │
    │  │ 1. should_compress() 判断     │  │
    │  │ 2. 摘要压缩 (LLM + 重试)       │  │
    │  │ 3. 核心规则重注入              │  │
    │  └────────────────────────────────┘  │
    └──────────────────────────────────────┘
                       │
                       ▼
                   返回结果
```

---

## 3. 详细设计

### 3.1 config.py - 上下文配置

```python
@dataclass
class ContextConfig:
    """上下文窗口配置"""

    # 窗口配置
    window_size: int = 128000              # DeepSeek 上下文窗口
    soft_trim_ratio: float = 0.3           # 30% 触发软修剪
    hard_clear_ratio: float = 0.5          # 50% 触发硬清除
    compress_threshold: float = 0.75       # 75% 触发摘要压缩

    # TTL 配置
    tool_result_ttl_seconds: int = 300     # 工具结果 5 分钟过期
    max_tool_result_chars: int = 4000      # 单条结果超过 4000 字符修剪

    # 摘要配置
    summary_model: str = "deepseek-chat"
    max_summary_retries: int = 3

    # 核心规则文件
    rules_files: List[str] = ["AGENTS.md", "TOOLS.md"]
    rules_cache: Dict[str, str] = field(default_factory=dict)

    # 保护配置
    protected_message_types: List[str] = ["user", "system", "image"]

    @classmethod
    def load_rules_at_startup(cls, rules_dir: Path) -> Dict[str, str]:
        """启动时加载核心规则文件到缓存"""

    def get_injected_rules(self) -> str:
        """获取需要注入的核心规则"""
```

### 3.2 guard.py - ContextGuard 主类

```python
class ContextGuard:
    """上下文守卫 - 统一的前置/后置处理入口"""

    def __init__(self, config: ContextConfig, llm_client: Optional[LLMClient] = None):
        self.config = config
        self.cleaner = Cleaner(config)
        self.compressor = Compressor(config, llm_client)
        self.reinjector = RuleReinjector(config)

    async def pre_process(self, messages: List[Dict]) -> List[Dict]:
        """阶段3: 上下文前置清理"""

    async def post_process(self, messages: List[Dict]) -> List[Dict]:
        """阶段7: 上下文后置管理"""

    def should_compress(self, messages: List[Dict]) -> bool:
        """判断是否超过 75% 窗口阈值 (混合模式核心入口)"""

    async def force_compress(self, messages: List[Dict]) -> List[Dict]:
        """手动触发压缩 (混合模式支持)"""
```

### 3.3 cleaner.py - 前置清理器

```python
class Cleaner:
    """上下文前置清理器"""

    async def pre_process(self, messages: List[Dict]) -> List[Dict]:
        """执行完整的前置清理流程"""

    def _check_ttl(self, messages: List[Dict], current_time: float) -> List[Dict]:
        """检查工具结果是否过期"""

    def _soft_trim(self, messages: List[Dict]) -> List[Dict]:
        """软修剪: 超长结果保留首尾 1500 字符"""

    def _hard_clear(self, messages: List[Dict]) -> List[Dict]:
        """硬清除: 过期结果替换为 [Old result cleared]"""
```

### 3.4 compressor.py - 后置压缩器

```python
class Compressor:
    """上下文压缩器"""

    async def compress(self, messages: List[Dict], force: bool = False) -> List[Dict]:
        """执行摘要压缩"""

    def _should_compress(self, messages: List[Dict]) -> bool:
        """判断是否需要压缩"""

    def _partition_messages(self, messages: List[Dict]) -> tuple:
        """分块: 区分需要压缩和保留的消息"""

    async def _summarize_with_retry(self, messages: List[Dict]) -> str:
        """摘要压缩（带重试）"""

    def _replace_with_summary(self, old_messages, summary, kept_messages) -> List[Dict]:
        """用摘要替换旧消息"""
```

### 3.5 reinjector.py - 规则重注入器

```python
class RuleReinjector:
    """核心规则重注入器"""

    def reinject(self, messages: List[Dict]) -> List[Dict]:
        """压缩后重新注入核心规则"""

    def _has_recent_rules(self, messages: List[Dict]) -> bool:
        """检查最近是否已有规则消息"""
```

---

## 4. 集成方式

### 4.1 QueryEngine 修改

```python
# backend/app/core/query_engine.py

from .context.guard import ContextGuard, ContextConfig

class QueryEngine:
    def __init__(self, ...):
        # 新增: 上下文守卫
        self.context_guard = ContextGuard(
            config=ContextConfig(
                window_size=128000,
                rules_cache=ContextConfig.load_rules_at_startup(
                    Path("docs/superpowers/")
                )
            ),
            llm_client=self.llm_client
        )

    async def process(self, user_input: str, conversation_id: str, ...):
        # ... 阶段1-2 ...

        # === 阶段 3: 上下文前置清理 ===
        history = await self.context_guard.pre_process(history)

        # ... 阶段 4-6 ...

        # === 阶段 7: 上下文后置管理 ===
        history = await self.context_guard.post_process(history)

        # ... 阶段 8-9 ...
```

### 4.2 使用示例

```python
# 自动模式
guard = ContextGuard(config)
if guard.should_compress(messages):
    messages = await guard.post_process(messages)

# 手动模式
messages = await guard.force_compress(messages)
```

---

## 5. 配置说明

### 5.1 默认配置值

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `window_size` | 128000 | DeepSeek 上下文窗口 |
| `soft_trim_ratio` | 0.3 | 30% 触发软修剪 |
| `hard_clear_ratio` | 0.5 | 50% 触发硬清除 |
| `compress_threshold` | 0.75 | 75% 触发摘要压缩 |
| `tool_result_ttl_seconds` | 300 | 工具结果 5 分钟过期 |
| `max_tool_result_chars` | 4000 | 单条结果超过 4000 字符修剪 |

### 5.2 环境变量

可通过 `.env` 覆盖默认配置：

```bash
CONTEXT_WINDOW_SIZE=128000
COMPRESS_THRESHOLD=0.75
TOOL_RESULT_TTL=300
```

---

## 6. 测试计划

### 6.1 单元测试

- `test_config.py`: 配置加载和缓存测试
- `test_cleaner.py`: TTL检查、软修剪、硬清除测试
- `test_compressor.py`: 摘要压缩、重试逻辑测试
- `test_reinjector.py`: 规则重注入测试

### 6.2 集成测试

- `test_guard_integration.py`: ContextGuard 端到端测试
- `test_query_engine_integration.py`: QueryEngine 集成测试

---

## 7. 后续阶段

Phase 1 完成后，继续实现：

| Phase | 内容 |
|-------|------|
| Phase 2 | 主循环增强（三层记忆完善、多Agent派生、重试容错） |
| Phase 3 | 会话生命周期（完整初始化、异常分类、降级方案） |
| Phase 4 | 多Agent系统（子Agent派生、隔离会话、结果冒泡） |

---

## 8. 参考资料

- 统一工作流程 v2.0 设计文档
- OpenClaw 架构规范
- DeepSeek API 文档
