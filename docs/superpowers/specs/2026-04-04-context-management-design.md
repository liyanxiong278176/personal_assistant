# Phase 1: 上下文管理系统设计规范

**日期**: 2026-04-04
**版本**: 1.1
**状态**: 设计阶段（审查后修订）

---

## 1. 概述

### 1.1 目标

**扩展现有的 `ContextManager` 系统**，实现统一工作流程 v2.0 中的上下文管理增强功能：

- **Step 0**: 会话初始化（上下文窗口配置、核心文件注入）
- **阶段 3**: 上下文前置清理（TTL检查、软修剪、硬清除）
- **阶段 7**: 上下文后置管理（增强摘要压缩、核心规则重注入）

### 1.2 架构定位

**重要**: 本设计是对现有 `ContextManager` 和 `ContextCompressor` 的**扩展**，不是替换。

```
┌─────────────────────────────────────────────────────────┐
│              现有架构 (保持不变)                         │
│  ┌────────────────┐         ┌────────────────────────┐  │
│  │ ContextManager │ ◄────── │ ContextCompressor     │  │
│  │                │         │ • compress()          │  │
│  │ • add_message()│         │ • compress_with_...() │  │
│  │ • get_messages()│         │ ��� needs_compaction()  │  │
│  │ • compress()   │         │ • TokenEstimator      │  │
│  └────────────────┘         └────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
                           │
                           ▼ 扩展
┌─────────────────────────────────────────────────────────┐
│              新增架构 (Phase 1)                          │
│  ┌────────────────┐         ┌────────────────────────┐  │
│  │ ContextGuard   │         │ Cleaner               │  │
│  │                │         │ • TTL检查             │  │
│  │ • pre_process()│         │ • 软修剪              │  │
│  │ • post_process()│         │ • 硬清除              │  │
│  │ • should_...() │         └────────────────────────┘  │
│  └────────────────┘                                    │
│  ┌────────────────┐         ┌────────────────────────┐  │
│  │ RuleReinjector │         │ LLMSummaryProvider    │  │
│  │ • reinject()   │         │ • generate_summary()  │  │
│  └────────────────┘         └────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
```

### 1.3 设计原则

1. **扩展而非替换**: 新功能通过 `ContextGuard` 扩展现有 `ContextManager`
2. **混合模式**: 支持自动+手动两种压缩触发方式
3. **启动缓存**: 核心规则文件在启动时加载到内存
4. **DeepSeek优先**: 摘要压缩使用项目已有的 DeepSeek API
5. **向后兼容**: 现有代码无需修改即可继续工作

---

## 2. 架构设计

### 2.1 模块结构

```
backend/app/core/context/
├── __init__.py       # 模块导出
├── manager.py        # [现有] ContextManager
├── compressor.py     # [现有] ContextCompressor
├── tokenizer.py      # [现有] TokenEstimator
├── config.py         # [新增] ContextConfig 配置类
├── guard.py          # [新增] ContextGuard 主类
├── cleaner.py        # [新增] Cleaner 前置清理器
├── reinjector.py     # [新增] RuleReinjector 规则重注入器
└── summary.py        # [新增] LLMSummaryProvider 摘要生成器
```

### 2.2 核心类图

```
┌─────────────────────────────────────────────────────────┐
│                    ContextGuard                         │
│                                                         │
│  config: ContextConfig                                 │
│  cleaner: Cleaner                                      │
│  reinjector: RuleReinjector                            │
│  summary_provider: LLMSummaryProvider                   │
│                                                         │
├─────────────────────────────────────────────────────────┤
│ pre_process(messages)   → List[Dict]                   │
│   • 调用 Cleaner 执行 TTL/修剪/清除                     │
│                                                         │
│ post_process(messages)  → List[Dict]                   │
│   • 调用 ContextManager.compress_with_summary()        │
│   • 调用 RuleReinjector.reinject()                      │
│                                                         │
│ should_compress(messages) → bool                       │
│   • 使用 TokenEstimator.estimate_messages()             │
│   • 阈值: window_size * 0.75                            │
│                                                         │
│ force_compress(messages) → List[Dict]                  │
│   • 手动触发压缩，忽略阈值                               │
└─────────────────────────────────────────────────────────┘
```

### 2.3 消息格式定义

所有消息遵循以下格式（与现有代码兼容）：

```python
{
    "role": "user" | "assistant" | "system" | "tool",
    "content": str,
    # 可选字段
    "name": str,              # 消息名称
    "_timestamp": float,      # 添加时间（用于TTL）
    "_type": str,             # 消息类型（如 "tool_result"）
    "_trimmed": bool,         # 是否已被修剪
    "_cleared": bool,         # 是否已被清除
    "_compressed": bool,      # 是否已被压缩
    "_rules_reinjected": bool # 规则是否已注入
}
```

### 2.4 处理流程

```
                    用户消息
                       │
                       ▼
    ┌───────────────────────────────────────┐
    │         阶段 3: 前置清理             │
    │  (新增 - ContextGuard.pre_process)   │
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
    │  (增强 - ContextGuard.post_process) │
    │  ┌────────────────────────────────┐  │
    │  │ 1. should_compress() 判断     │  │
    │  │    → 使用 TokenEstimator       │  │
    │  │ 2. 压缩 (调用现有方法)          │  │
    │  │    → ContextManager.compress   │
    │  │ 3. 规则重注入                  │  │
    │  │    → RuleReinjector.reinject   │  │
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
"""上下文管理配置"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from pathlib import Path


@dataclass(frozen=True)
class ContextConfig:
    """上下文窗口配置 (不可变，线程安全)"""

    # === 窗口配置 ===
    window_size: int = 128000              # DeepSeek 上下文窗口
    soft_trim_ratio: float = 0.3           # 30% 触发软修剪
    hard_clear_ratio: float = 0.5          # 50% 触发硬清除

    # === TTL 配置 ===
    tool_result_ttl_seconds: int = 300     # 工具结果 5 分钟过期
    max_tool_result_chars: int = 4000      # 单条结果超过 4000 字符修剪

    # === 摘要配置 ===
    summary_max_retries: int = 3           # 摘要重试次数
    summary_timeout_seconds: int = 30      # 摘要超时时间

    # === 核心规则文件 ===
    rules_files: tuple[str, ...] = field(default_factory=lambda: (
        "AGENTS.md",    # 项目规则
        "TOOLS.md",     # 工具使用指南
    ))

    # === 保护配置 ===
    protected_message_roles: tuple[str, ...] = field(default_factory=lambda: (
        "user",         # 不删除用户消息
        "system",       # 不删除系统消息
    ))

    # === 规则重注入配置 ===
    rules_reinject_window: int = 5          # 检查最近 N 条消息
    rules_reinject_interval: int = 3        # 至少间隔 N 条消息后重新注入


def load_rules_at_startup(rules_dir: Path, files: tuple[str, ...]) -> Dict[str, str]:
    """启动时加载核心规则文件到缓存 (同步，在应用启动时调用)

    Args:
        rules_dir: 规则文件目录路径
        files: 要加载的文件名列表

    Returns:
        文件名到内容的映射字典
    """
    cache = {}
    for filename in files:
        path = rules_dir / filename
        if path.exists():
            try:
                content = path.read_text(encoding="utf-8")
                # 限制单文件大小
                if len(content) <= 20000:
                    cache[filename] = content
                else:
                    # 截断过大的文件
                    cache[filename] = content[:20000] + "\n...[文件过长已截断]..."
            except Exception as e:
                # 文件读取失败不影响启动
                cache[filename] = f"# 规则文件加载失败: {e}"
    return cache


def get_injected_rules(rules_cache: Dict[str, str]) -> str:
    """获取需要注入的核心规则

    Args:
        rules_cache: 规则文件缓存字典

    Returns:
        格式化的规则字符串
    """
    if not rules_cache:
        return ""

    sections = []
    for name, content in rules_cache.items():
        sections.append(f"## {name}\n{content}\n")
    return "\n".join(sections)
```

### 3.2 guard.py - ContextGuard 主类

```python
"""上下文守卫 - 统一的前置/后置处理入口"""

import logging
from typing import List, Dict, Optional, TYPE_CHECKING

from .config import ContextConfig, load_rules_at_startup, get_injected_rules
from .cleaner import Cleaner
from .reinjector import RuleReinjector
from .summary import LLMSummaryProvider

if TYPE_CHECKING:
    from .manager import ContextManager
    from ..llm import LLMClient

logger = logging.getLogger(__name__)


class ContextGuard:
    """上下文守卫 - 扩展现有 ContextManager 的功能

    职责:
    - 前置清理: TTL检查、软修剪、硬清除
    - 后置管理: 压缩协调、规则重注入
    - 混合模式: 自动+手动压缩触发
    """

    def __init__(
        self,
        config: ContextConfig,
        llm_client: Optional["LLMClient"] = None,
        context_manager: Optional["ContextManager"] = None,
    ):
        """初始化 ContextGuard

        Args:
            config: 上下文配置
            llm_client: LLM 客户端 (用于摘要生成)
            context_manager: 现有的 ContextManager 实例 (可选)
        """
        self.config = config
        self.cleaner = Cleaner(config)
        self.reinjector = RuleReinjector(config)
        self.summary_provider = LLMSummaryProvider(
            llm_client=llm_client,
            config=config
        )
        self._context_manager = context_manager

        # 统计信息
        self._stats = {
            "pre_process_count": 0,
            "post_process_count": 0,
            "compress_count": 0,
        }

    async def pre_process(self, messages: List[Dict]) -> List[Dict]:
        """阶段3: 上下文前置清理

        在 LLM 推理前清理过期的工具结果

        Args:
            messages: 当前消息列表

        Returns:
            清理后的消息列表
        """
        self._stats["pre_process_count"] += 1
        result = await self.cleaner.clean(messages)

        logger.debug(
            f"[ContextGuard] pre_process | "
            f"输入: {len(messages)}条 | "
            f"输出: {len(result)}条"
        )

        return result

    async def post_process(
        self,
        messages: List[Dict],
        force: bool = False
    ) -> List[Dict]:
        """阶段7: 上下文后置管理

        在 LLM 推理后执行压缩和规则重注入

        Args:
            messages: 当前消息列表
            force: 是否强制压缩（忽略阈值）

        Returns:
            处理后的消息列表
        """
        self._stats["post_process_count"] += 1
        result = messages.copy()

        # 1. 判断是否需要压缩
        needs_compress = force or self.should_compress(result)

        if needs_compress:
            self._stats["compress_count"] += 1

            # 2. 生成摘要并压缩 (使用现有的 ContextManager)
            if self._context_manager:
                summary_func = self.summary_provider.create_summary_func()
                result, _ = self._context_manager.compress_with_summary(
                    summary_func=summary_func
                )
            else:
                # 降级: 简单的摘要生成
                summary = await self.summary_provider.generate_summary(result)
                result = self._simple_compress_with_summary(result, summary)

        # 3. 规则重注入
        result = self.reinjector.reinject(result)

        logger.debug(
            f"[ContextGuard] post_process | "
            f"输入: {len(messages)}条 | "
            f"输出: {len(result)}条 | "
            f"压缩: {needs_compress}"
        )

        return result

    def should_compress(self, messages: List[Dict]) -> bool:
        """判断是否超过 75% 窗口阈值 (混合模式核心入口)

        Args:
            messages: 当前消息列表

        Returns:
            是否需要压缩
        """
        from .tokenizer import TokenEstimator

        current_tokens = TokenEstimator.estimate_messages(messages)
        threshold = self.config.window_size * 0.75

        return current_tokens >= threshold

    async def force_compress(self, messages: List[Dict]) -> List[Dict]:
        """手动触发压缩 (混合模式支持)

        Args:
            messages: 当前消息列表

        Returns:
            压缩后的消息列表
        """
        return await self.post_process(messages, force=True)

    def _simple_compress_with_summary(
        self,
        messages: List[Dict],
        summary: str
    ) -> List[Dict]:
        """简单的摘要压缩 (降级方案)

        Args:
            messages: 原始消息列表
            summary: 摘要内容

        Returns:
            压缩后的消息列表
        """
        # 保留 system 消息
        system = [m for m in messages if m.get("role") == "system"]

        # 添加摘要
        if summary:
            system.append({
                "role": "system",
                "content": f"[历史对话摘要]\n{summary}",
                "_compressed": True
            })

        # 保留最近消息 (40%)
        keep_count = max(1, int(len(messages) * 0.4))
        recent = messages[-keep_count:]

        return system + recent

    def get_stats(self) -> Dict:
        """获取统计信息"""
        return self._stats.copy()
```

### 3.3 cleaner.py - 前置清理器

```python
"""前置清理策略 - 阶段3"""

import time
import logging
from typing import List, Dict, Any

from .config import ContextConfig

logger = logging.getLogger(__name__)


class Cleaner:
    """上下文前置清理器

    负责:
    1. TTL 检查 - 标记过期的工具结果
    2. 软修剪 - 超长结果保留首尾
    3. 硬清除 - 替换过期结果为占位符
    """

    def __init__(self, config: ContextConfig):
        self.config = config

    async def clean(self, messages: List[Dict]) -> List[Dict]:
        """执行完整的前置清理流程

        Args:
            messages: 当前消息列表

        Returns:
            清理后的消息列表
        """
        if not messages:
            return messages

        result = [m.copy() for m in messages]  # 避免修改原消息
        current_time = time.time()

        # Step 1: TTL 检查
        result = self._check_ttl(result, current_time)

        # Step 2: 软修剪
        result = self._soft_trim(result)

        # Step 3: 硬清除
        result = self._hard_clear(result)

        return result

    def _check_ttl(self, messages: List[Dict], current_time: float) -> List[Dict]:
        """检查工具结果是否过期

        工具结果通过 content 中的特殊标记或 _type 字段识别
        """
        for msg in messages:
            # 检查是否是工具结果
            is_tool_result = (
                msg.get("_type") == "tool_result" or
                (msg.get("role") == "tool" and "_timestamp" in msg)
            )

            if is_tool_result:
                timestamp = msg.get("_timestamp", 0)
                age = current_time - timestamp

                if age > self.config.tool_result_ttl_seconds:
                    msg["_expired"] = True

        return messages

    def _soft_trim(self, messages: List[Dict]) -> List[Dict]:
        """软修剪: 超长结果保留首尾

        触发条件: 上下文占用 > soft_trim_ratio (30%)
        执行动作: 单条结果 > max_tool_result_chars 时保留首尾
        """
        for msg in messages:
            if msg.get("_expired"):
                continue

            is_tool_result = (
                msg.get("_type") == "tool_result" or
                msg.get("role") == "tool"
            )

            if is_tool_result:
                content = msg.get("content", "")
                if len(content) > self.config.max_tool_result_chars:
                    # 保留前 1500 + 后 1500
                    head = content[:1500]
                    tail = content[-1500:]
                    msg["content"] = f"{head}\n...[中间省略]...\n{tail}"
                    msg["_trimmed"] = True

        return messages

    def _hard_clear(self, messages: List[Dict]) -> List[Dict]:
        """硬清除: 过期结果替换为占位符

        保护机制:
        - 不修改 user/assistant 消息
        - 跳过带图片标记的消息
        - 跳过核心规则消息
        """
        for msg in messages:
            if msg.get("_expired"):
                # 检查是否受保护
                if msg.get("role") in self.config.protected_message_roles:
                    continue

                if msg.get("content", "").startswith("## "):  # 可能是规则
                    continue

                msg["content"] = "[Old result cleared]"
                msg["_cleared"] = True

        return messages
```

### 3.4 summary.py - 摘要生成器

```python
"""LLM 摘要生成器"""

import logging
from typing import List, Dict, Callable, Optional

from .config import ContextConfig

logger = logging.getLogger(__name__)


class LLMSummaryProvider:
    """LLM 摘要生成器

    为 ContextManager.compress_with_summary() 提供摘要生成函数
    """

    # 默认摘要模板
    DEFAULT_SUMMARY_PROMPT = """请将以下对话内容压缩成简洁的摘要，保留：
1. 用户的核心意图和需求
2. 重要的工具调用结果
3. 关键的决策过程

对话内容：
{content}

摘要："""

    def __init__(
        self,
        llm_client: Optional["LLMClient"] = None,
        config: Optional[ContextConfig] = None,
    ):
        """初始化摘要生成器

        Args:
            llm_client: LLM 客户端
            config: 上下文配置
        """
        self.llm_client = llm_client
        self.config = config or ContextConfig()

    async def generate_summary(self, messages: List[Dict]) -> str:
        """生成对话摘要

        Args:
            messages: 要摘要的消息列表

        Returns:
            摘要文本
        """
        if not messages:
            return ""

        for attempt in range(self.config.summary_max_retries):
            try:
                # 构建摘要输入
                content = self._format_messages_for_summary(messages)
                prompt = self.DEFAULT_SUMMARY_PROMPT.format(content=content)

                # 调用 LLM
                if self.llm_client:
                    summary = await self.llm_client.chat(
                        messages=[{"role": "user", "content": prompt}],
                        system_prompt="你是一个专业的对话摘要助手。"
                    )
                else:
                    # 降级: 简单计数摘要
                    summary = self._fallback_summary(messages)

                return summary

            except Exception as e:
                logger.warning(f"[LLMSummary] 摘要失败 (尝试 {attempt+1}): {e}")

                # 最后一次尝试失败，使用降级方案
                if attempt == self.config.summary_max_retries - 1:
                    return self._fallback_summary(messages)

        return self._fallback_summary(messages)

    def create_summary_func(self) -> Callable:
        """创建同步摘要函数供 ContextManager 使用

        ContextManager.compress_with_summary() 需要一个同步函数，
        但我们的 LLM 调用是异步的。这里返回一个包装函数。
        """
        def sync_summary(messages: List[Dict]) -> str:
            """同步摘要函数 (降级为简单计数)"""
            return self._fallback_summary(messages)

        return sync_summary

    def _format_messages_for_summary(self, messages: List[Dict]) -> str:
        """格式化消息用于摘要输入"""
        lines = []
        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")[:500]  # 限制长度
            lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _fallback_summary(self, messages: List[Dict]) -> str:
        """降级摘要: 简单计数"""
        user_count = sum(1 for m in messages if m.get("role") == "user")
        assistant_count = sum(1 for m in messages if m.get("role") == "assistant")
        tool_count = sum(1 for m in messages if m.get("role") == "tool")

        return (
            f"历史对话包含 {user_count} 条用户消息、"
            f"{assistant_count} 条助手回复、"
            f"{tool_count} 条工具调用结果。"
            f"这些内容已被压缩以节省上下文空间。"
        )
```

### 3.5 reinjector.py - 规则重注入器

```python
"""核心规则重注入 - 阶段7"""

import logging
from typing import List, Dict

from .config import get_injected_rules

logger = logging.getLogger(__name__)


class RuleReinjector:
    """核心规则重注入器

    在压缩后重新注入核心规则，防止 AI 行为失控
    """

    def __init__(self, config):
        """初始化规则重注入器

        Args:
            config: ContextConfig 实例
        """
        self.config = config
        self._last_reinject_position = -1  # 上次注入的位置

    def reinject(self, messages: List[Dict], rules_cache: Dict[str, str]) -> List[Dict]:
        """压缩后重新注入核心规则

        Args:
            messages: 当前消息列表
            rules_cache: 规则文件缓存

        Returns:
            规则重注入后的消息列表
        """
        if not messages:
            return messages

        # 检查是否需要注入
        if not self._should_reinject(messages, rules_cache):
            return messages

        rules = get_injected_rules(rules_cache)
        if not rules:
            return messages

        # 构建规则消息
        rule_msg = {
            "role": "system",
            "content": rules,
            "_rules_reinjected": True
        }

        # 找到合适的插入位置（摘要后，当前对话前）
        result = []
        inserted = False

        for i, msg in enumerate(messages):
            result.append(msg)

            # 在压缩摘要后插入
            if not inserted and msg.get("_compressed"):
                result.append(rule_msg)
                self._last_reinject_position = i
                inserted = True

        # 如果没找到摘要，插入到开头
        if not inserted:
            result.insert(0, rule_msg)
            self._last_reinject_position = 0

        logger.debug(f"[RuleReinjector] 规则已注入 | 位置: {self._last_reinject_position}")

        return result

    def _should_reinject(self, messages: List[Dict], rules_cache: Dict[str, str]) -> bool:
        """判断是否需要重新注入规则

        规则:
        1. 规则缓存非空
        2. 最近 N 条消息中没有规则消息
        3. 距离上次注入至少 N 条消息
        """
        if not rules_cache:
            return False

        # 检查最近的消息
        recent = messages[-self.config.rules_reinject_window:]
        has_recent_rules = any(
            m.get("_rules_reinjected") for m in recent
        )

        if has_recent_rules:
            return False

        # 检查距离上次注入的消息数
        if self._last_reinject_position >= 0:
            messages_since = len(messages) - self._last_reinject_position
            if messages_since < self.config.rules_reinject_interval:
                return False

        return True
```

---

## 4. 集成方式

### 4.1 QueryEngine 修改

```python
# backend/app/core/query_engine.py

from .context.guard import ContextGuard, ContextConfig, load_rules_at_startup

class QueryEngine:
    def __init__(self, ...):
        # 新增: 上下文守卫
        rules_cache = load_rules_at_startup(
            Path("docs/superpowers/"),
            ContextConfig.rules_files
        )

        self.context_guard = ContextGuard(
            config=ContextConfig(rules_cache=rules_cache),
            llm_client=self.llm_client,
            context_manager=self.context_manager  # 传入现有的 ContextManager
        )

    async def process(self, user_input: str, conversation_id: str, ...):
        # ... 阶段1-2 ...

        # === 阶段 3: 上下文前置清理 ===
        history = await self.context_guard.pre_process(history)

        # ... 阶段 4-6 (LLM 推理) ...

        # === 阶段 7: 上下文后置管理 ===
        history = await self.context_guard.post_process(history)

        # ... 阶段 8-9 ...
```

### 4.2 使用示例

```python
# 自动模式 (基于阈值)
guard = ContextGuard(config, llm_client)
if guard.should_compress(messages):
    messages = await guard.post_process(messages)

# 手动模式 (强制触发)
messages = await guard.force_compress(messages)

# 获取统计信息
stats = guard.get_stats()
print(f"前置清理: {stats['pre_process_count']}次")
print(f"后置处理: {stats['post_process_count']}次")
print(f"压缩: {stats['compress_count']}次")
```

---

## 5. 配置说明

### 5.1 默认配置值

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `window_size` | 128000 | DeepSeek 上下文窗口 |
| `soft_trim_ratio` | 0.3 | 30% 触发软修剪 |
| `hard_clear_ratio` | 0.5 | 50% 触发硬清除 |
| `tool_result_ttl_seconds` | 300 | 工具结果 5 分钟过期 |
| `max_tool_result_chars` | 4000 | 单条结果超过 4000 字符修剪 |
| `summary_max_retries` | 3 | 摘要重试次数 |
| `rules_reinject_window` | 5 | 检查最近 5 条消息 |
| `rules_reinject_interval` | 3 | 至少间隔 3 条消息后重新注入 |

**注意**: 压缩阈值 75% 低于现有的 ContextManager 的 80%，这样前置清理会先触发，
减少需要完整压缩的频率。

### 5.2 环境变量

可通过 `.env` 覆盖默认配置：

```bash
CONTEXT_WINDOW_SIZE=128000
TOOL_RESULT_TTL=300
MAX_TOOL_RESULT_CHARS=4000
```

---

## 6. 错误处理策略

### 6.1 摘要生成失败

| 场景 | 处理方式 |
|------|---------|
| LLM 调用失败 | 重试最多 3 次 |
| 重试全部失败 | 降级为简单计数摘要 |
| 超时 | 返回降级摘要，记录错误 |

### 6.2 规则文件加载

| 场景 | 处理方式 |
|------|---------|
| 文件不存在 | 跳过，记录警告 |
| 文件过大 (>20000) | 截断，添加提示 |
| 读取失败 | 使用错误提示替代内容 |

### 6.3 前置清理

| 场景 | 处理方式 |
|------|---------|
| 消息列表为空 | 直接返回 |
| 缺少时间戳 | 跳过 TTL 检查 |
| 工具结果识别失败 | 跳过该消息 |

---

## 7. 测试计划

### 7.1 单元测试

| 测试文件 | 测试内容 |
|---------|---------|
| `test_config.py` | 配置加载、规则缓存、不可变性 |
| `test_cleaner.py` | TTL检查、软修剪、硬清除 |
| `test_summary.py` | 摘要生成、重试逻辑、降级方案 |
| `test_reinjector.py` | 规则重注入、位置判断 |

### 7.2 集成测试

| 测试文件 | 测试内容 |
|---------|---------|
| `test_guard_integration.py` | ContextGuard 端到端测试 |
| `test_query_engine_integration.py` | QueryEngine 集成测试 |

### 7.3 测试场景

```python
# 场景 1: 空消息列表
messages = []
result = await guard.pre_process(messages)
assert result == []

# 场景 2: TTL 过期
messages = [{
    "role": "tool",
    "content": "...",
    "_timestamp": time.time() - 400  # 400秒前
}]
result = await guard.pre_process(messages)
assert result[0]["_expired"] == True
assert result[0]["_cleared"] == True

# 场景 3: 超长结果软修剪
messages = [{
    "role": "tool",
    "content": "x" * 5000,
    "_type": "tool_result"
}]
result = await guard.pre_process(messages)
assert len(result[0]["content"]) < 5000
assert result[0]["_trimmed"] == True

# 场景 4: 压缩阈值触发
messages = create_large_messages(100000)  # 超过 75%
assert guard.should_compress(messages) == True

# 场景 5: 规则重注入
messages = [{"role": "user", "content": "hello"}]
result = guard.reinjector.reinject(messages, rules_cache)
assert any(m.get("_rules_reinjected") for m in result)
```

---

## 8. 可观测性

### 8.1 日志记录

```python
# 前置清理
logger.debug(f"[ContextGuard] pre_process | 输入: {n}条 | 输出: {m}条")
logger.info(f"[Cleaner] TTL过期: {expired}条 | 软修剪: {trimmed}条 | 硬清除: {cleared}条")

# 后置处理
logger.debug(f"[ContextGuard] post_process | 输入: {n}条 | 输出: {m}条 | 压缩: {needs}")
logger.info(f"[Compressor] 压缩完成 | {original}条 → {compressed}条 | 节省: {saved} tokens")

# 规则注入
logger.debug(f"[RuleReinjector] 规则已注入 | 位置: {position}")
```

### 8.2 统计指标

```python
{
    "pre_process_count": 100,      # 前置清理次数
    "post_process_count": 50,      # 后置处理次数
    "compress_count": 20,          # 压缩次数
    "total_tokens_saved": 50000,   # 累计节省的 tokens
    "avg_compress_time_ms": 150    # 平均压缩耗时
}
```

---

## 9. 后续阶段

Phase 1 完成后，继续实现：

| Phase | 内容 |
|-------|------|
| Phase 2 | 主循环增强（三层记忆完善、多Agent派生、重试容错） |
| Phase 3 | 会话生命周期（完整初始化、异常分类、降级方案） |
| Phase 4 | 多Agent系统（子Agent派生、隔离会话、结果冒泡） |

---

## 10. 变更历史

| 版本 | 日期 | 变更内容 |
|------|------|---------|
| 1.0 | 2026-04-04 | 初始设计 |
| 1.1 | 2026-04-04 | 审查后修订：明确扩展现有架构、添加错误处理、完善消息格式定义 |
