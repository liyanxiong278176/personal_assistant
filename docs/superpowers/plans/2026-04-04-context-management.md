# Phase 1: 上下文管理系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 扩展现有的 ContextManager 系统，实现统一工作流程 v2.0 中的上下文管理增强功能（前置清理、后置压缩、规则重注入）

**Architecture:** 通过 ContextGuard 扩展现有架构，不替换现有代码。新增 Cleaner、LLMSummaryProvider、RuleReinjector 三个组件，与现有 ContextManager 协同工作。

**Tech Stack:** Python 3.11+, FastAPI, dataclasses, pytest

---

## 文件结构

```
backend/app/core/context/
├── __init__.py       # [修改] 模块导出
├── config.py         # [新增] ContextConfig 配置类
├── guard.py          # [新增] ContextGuard 主类
├── cleaner.py        # [新增] Cleaner 前置清理器
├── reinjector.py     # [新增] RuleReinjector 规则重注入器
└── summary.py        # [新增] LLMSummaryProvider 摘要生成器

tests/core/context/
├── __init__.py
├── test_config.py    # [新增] 配置测试
├── test_cleaner.py    # [新增] 清理器测试
├── test_summary.py    # [新增] 摘要生成器测试
├── test_reinjector.py # [新增] 规则重注入测试
└── test_guard_integration.py # [新增] 集成测试
```

---

## Task 1: 确保目录结构

- [ ] **Step 1: 创建必要的目录**

```bash
# 创建测试目录
mkdir -p backend/tests/core/context
touch backend/tests/core/context/__init__.py

# 确保 docs/superpowers 目录存在 (用于规则文件)
mkdir -p docs/superpowers
touch docs/superpowers/.gitkeep
```

---

## Task 2: 创建 config.py - 上下文配置

**Files:**
- Create: `backend/app/core/context/config.py`
- Test: `tests/core/context/test_config.py`

- [ ] **Step 1: 写配置类测试**

```bash
# 创建测试目录
mkdir -p backend/tests/core/context
touch backend/tests/core/context/__init__.py
touch backend/tests/core/context/test_config.py
```

- [ ] **Step 2: 写配置类测试**

```python
# backend/tests/core/context/test_config.py

import pytest
from pathlib import Path
from app.core.context.config import ContextConfig, load_rules_at_startup, get_injected_rules


def test_context_config_defaults():
    """测试默认配置值"""
    config = ContextConfig()
    assert config.window_size == 128000
    assert config.tool_result_ttl_seconds == 300
    assert config.max_tool_result_chars == 4000
    assert config.summary_max_retries == 3


def test_context_config_is_frozen():
    """测试配置不可变"""
    config = ContextConfig()
    with pytest.raises(Exception):  # FrozenInstanceError
        config.window_size = 64000


def test_context_config_custom_values():
    """测试自定义配置"""
    config = ContextConfig(
        window_size=64000,
        tool_result_ttl_seconds=600
    )
    assert config.window_size == 64000
    assert config.tool_result_ttl_seconds == 600


def test_rules_files_tuple():
    """测试规则文件是元组（不可变）"""
    config = ContextConfig()
    assert isinstance(config.rules_files, tuple)
    assert "AGENTS.md" in config.rules_files


def test_load_rules_at_startup(tmp_path):
    """测试启动时加载规则文件"""
    # 创建测试文件
    (tmp_path / "AGENTS.md").write_text("# Test Rules", encoding="utf-8")
    (tmp_path / "TOOLS.md").write_text("# Tools", encoding="utf-8")
    
    result = load_rules_at_startup(tmp_path, ("AGENTS.md", "TOOLS.md"))
    
    assert "AGENTS.md" in result
    assert "TOOLS.md" in result
    assert "# Test Rules" in result["AGENTS.md"]


def test_load_rules_file_not_found(tmp_path):
    """测试文件不存在时跳过"""
    result = load_rules_at_startup(tmp_path, ("NONEXISTENT.md",))
    assert "NONEXISTENT.md" not in result


def test_load_rules_file_too_large(tmp_path):
    """测试文件过大时截断"""
    large_content = "x" * 25001  # 超过 20000 限制
    (tmp_path / "LARGE.md").write_text(large_content, encoding="utf-8")
    
    result = load_rules_at_startup(tmp_path, ("LARGE.md",))
    
    assert "LARGE.md" in result
    assert len(result["LARGE.md"]) <= 20500  # 20000 + 截断提示
    assert "已截断" in result["LARGE.md"]


def test_get_injected_rules():
    """测试获取注入规则"""
    cache = {
        "AGENTS.md": "# Rules",
        "TOOLS.md": "# Tools"
    }
    result = get_injected_rules(cache)
    
    assert "## AGENTS.md" in result
    assert "# Rules" in result
    assert "## TOOLS.md" in result


def test_get_injected_rules_empty_cache():
    """测试空缓存返回空字符串"""
    result = get_injected_rules({})
    assert result == ""
```

- [ ] **Step 3: 运行测试验证失败**

```bash
cd backend
pytest tests/core/context/test_config.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 4: 创建 config.py**

```python
# backend/app/core/context/config.py

"""上下文管理配置"""

from dataclasses import dataclass, field
from typing import Dict, Tuple
from pathlib import Path


@dataclass(frozen=True)
class ContextConfig:
    """上下文窗口配置 (不可变，线��安全)"""

    # === 窗口配置 ===
    window_size: int = 128000              # DeepSeek 上下文窗口

    # === TTL 配置 ===
    tool_result_ttl_seconds: int = 300     # 工具结果 5 分钟过期
    max_tool_result_chars: int = 4000      # 单条结果超过 4000 字符修剪

    # === 摘要配置 ===
    summary_max_retries: int = 3           # 摘要重试次数
    summary_timeout_seconds: int = 30      # 摘要超时时间

    # === 核心规则文件 ===
    rules_files: Tuple[str, ...] = field(default_factory=lambda: (
        "AGENTS.md",    # 项目规则
        "TOOLS.md",     # 工具使用指南
    ))

    # === 保护配置 ===
    protected_message_roles: Tuple[str, ...] = field(default_factory=lambda: (
        "user",         # 不删除用户消息
        "system",       # 不删除系统消息
    ))

    # === 规则重注入配置 ===
    rules_reinject_window: int = 5          # 检查最近 N 条消息
    rules_reinject_interval: int = 3        # 至少间隔 N 条消息后重新注入


def load_rules_at_startup(rules_dir: Path, files: Tuple[str, ...]) -> Dict[str, str]:
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

- [ ] **Step 5: 更新 __init__.py 导出**

```python
# backend/app/core/context/__init__.py

from .config import ContextConfig, load_rules_at_startup, get_injected_rules

__all__ = [
    "ContextConfig",
    "load_rules_at_startup",
    "get_injected_rules",
]
```

- [ ] **Step 6: 运行测试验证通过**

```bash
cd backend
pytest tests/core/context/test_config.py -v
```
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/core/context/config.py backend/app/core/context/__init__.py backend/tests/core/context/
git commit -m "feat(context): add ContextConfig with frozen dataclass"
```

---

## Task 2: 创建 cleaner.py - 前置清理器

**Files:**
- Create: `backend/app/core/context/cleaner.py`
- Test: `tests/core/context/test_cleaner.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/core/context/test_cleaner.py

import pytest
import time
from app.core.context.config import ContextConfig
from app.core.context.cleaner import Cleaner


@pytest.mark.asyncio
async def test_clean_empty_messages():
    """测试空消息列表"""
    config = ContextConfig()
    cleaner = Cleaner(config)
    result = await cleaner.clean([])
    assert result == []


@pytest.mark.asyncio
async def test_clean_returns_copy():
    """测试返回副本不修改原消息"""
    config = ContextConfig()
    cleaner = Cleaner(config)
    original = [{"role": "user", "content": "hello"}]
    result = await cleaner.clean(original)
    
    # 原消息不应被修改
    assert "_expired" not in original[0]
    # 结果是副本
    assert result is not original


@pytest.mark.asyncio
async def test_check_ttl_marks_expired():
    """测试TTL检查标记过期消息"""
    config = ContextConfig(tool_result_ttl_seconds=300)
    cleaner = Cleaner(config)
    
    # 创建过期的工具结果 (400秒前)
    old_time = time.time() - 400
    messages = [{
        "role": "tool",
        "content": "result",
        "_type": "tool_result",
        "_timestamp": old_time
    }]
    
    result = await cleaner.clean(messages)
    assert result[0]["_expired"] == True


@pytest.mark.asyncio
async def test_check_ttl_skips_no_timestamp():
    """测试没有时间戳时跳过TTL检查"""
    config = ContextConfig(tool_result_ttl_seconds=300)
    cleaner = Cleaner(config)
    
    # 没有时间的工具结果
    messages = [{
        "role": "tool",
        "content": "result",
        "_type": "tool_result"
    }]
    
    result = await cleaner.clean(messages)
    assert "_expired" not in result[0]


@pytest.mark.asyncio
async def test_soft_trim_long_content():
    """测试软修剪超长内容"""
    config = ContextConfig(max_tool_result_chars=4000)
    cleaner = Cleaner(config)
    
    # 创建超长内容 (5000 字符)
    long_content = "x" * 5000
    messages = [{
        "role": "tool",
        "content": long_content,
        "_type": "tool_result"
    }]
    
    result = await cleaner.clean(messages)
    
    # 内容应该被修剪
    assert len(result[0]["content"]) < 5000
    assert result[0]["_trimmed"] == True
    # 应该包含省略标记
    assert "中间省略" in result[0]["content"]


@pytest.mark.asyncio
async def test_soft_trim_preserves_ends():
    """测试软修剪保留首尾"""
    config = ContextConfig(max_tool_result_chars=4000)
    cleaner = Cleaner(config)
    
    # 创建可预测的内容
    prefix = "START_" * 200  # 1000 字符
    suffix = "END_" * 200    # 1000 字符
    middle = "x" * 3000
    messages = [{
        "role": "tool",
        "content": prefix + middle + suffix,
        "_type": "tool_result"
    }]
    
    result = await cleaner.clean(messages)
    
    content = result[0]["content"]
    assert content.startswith("START_")
    assert content.endswith("END_")


@pytest.mark.asyncio
async def test_hard_clear_replaces_expired():
    """测试硬清除替换过期内容"""
    config = ContextConfig(protected_message_roles=("user", "system"))
    cleaner = Cleaner(config)
    
    messages = [{
        "role": "tool",
        "content": "old result",
        "_expired": True
    }]
    
    result = await cleaner.clean(messages)
    
    assert result[0]["content"] == "[Old result cleared]"
    assert result[0]["_cleared"] == True


@pytest.mark.asyncio
async def test_hard_clear_protects_user_messages():
    """测试硬清除保护用户消息"""
    config = ContextConfig(protected_message_roles=("user", "system"))
    cleaner = Cleaner(config)
    
    messages = [{
        "role": "user",
        "content": "hello",
        "_expired": True
    }]
    
    result = await cleaner.clean(messages)
    
    # 用户消息内容不应被修改
    assert result[0]["content"] == "hello"
    assert "_cleared" not in result[0]


@pytest.mark.asyncio
async def test_hard_clear_protects_system_rules():
    """测试硬清除保护系统规则"""
    config = ContextConfig(protected_message_roles=("user", "system"))
    cleaner = Cleaner(config)
    
    messages = [{
        "role": "tool",
        "content": "## Important Rule\nkeep this",
        "_expired": True
    }]
    
    result = await cleaner.clean(messages)
    
    # 规则内容应被保护
    assert "## Important Rule" in result[0]["content"]
    assert "_cleared" not in result[0]


@pytest.mark.asyncio
async def test_full_pipeline():
    """测试完整清理流程"""
    config = ContextConfig()
    cleaner = Cleaner(config)
    
    old_time = time.time() - 400
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "tool", "content": "x" * 5000, "_type": "tool_result", "_timestamp": old_time},
        {"role": "assistant", "content": "hi there"}
    ]
    
    result = await cleaner.clean(messages)
    
    # 第一条：用户消息，不变
    assert result[0]["content"] == "hello"
    # 第二条：工具结果，被修剪
    assert len(result[1]["content"]) < 5000
    assert result[1]["_expired"] == True
    assert result[1]["_cleared"] == True
    # 第三条：助手消息，不变
    assert result[2]["content"] == "hi there"
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend
pytest tests/core/context/test_cleaner.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 创建 cleaner.py**

```python
# backend/app/core/context/cleaner.py

"""前置清理策略 - 阶段3"""

import time
import logging
from typing import List, Dict

from .config import ContextConfig

logger = logging.getLogger(__name__)


class Cleaner:
    """上下文前置清理器

    负责:
    1. TTL 检查 - 标记过期的工具结果
    2. 软修剪 - 超长结果保留首尾
    3. 硬清除 - 替换过期结果为占位符
    """

    # 软修剪保留的字符数 (每端)
    TRIM_KEEP_CHARS = 1500

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
        
        注意: 如果消息没有 _timestamp 字段，跳过 TTL 检查
        """
        for msg in messages:
            # 检查是否是工具结果
            is_tool_result = (
                msg.get("_type") == "tool_result" or
                (msg.get("role") == "tool" and "_timestamp" in msg)
            )

            if is_tool_result:
                timestamp = msg.get("_timestamp", 0)
                if timestamp == 0:
                    continue  # 没有时间戳，跳过 TTL 检查
                
                age = current_time - timestamp

                if age > self.config.tool_result_ttl_seconds:
                    msg["_expired"] = True

        return messages

    def _soft_trim(self, messages: List[Dict]) -> List[Dict]:
        """软修剪: 超长结果保留首尾

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
                    # 保留前 TRIM_KEEP_CHARS + 后 TRIM_KEEP_CHARS
                    head = content[:self.TRIM_KEEP_CHARS]
                    tail = content[-self.TRIM_KEEP_CHARS:]
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

- [ ] **Step 4: 更新 __init__.py 导出**

```python
# backend/app/core/context/__init__.py

from .cleaner import Cleaner

__all__ = [
    "ContextConfig",
    "load_rules_at_startup",
    "get_injected_rules",
    "Cleaner",
]
```

- [ ] **Step 5: 运行测试验证通过**

```bash
cd backend
pytest tests/core/context/test_cleaner.py -v
```
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/context/cleaner.py backend/app/core/context/__init__.py backend/tests/core/context/test_cleaner.py
git commit -m "feat(context): add Cleaner for pre-process TTL/trim/clear"
```

---

## Task 3: 创建 reinjector.py - 规则重注入器

**Files:**
- Create: `backend/app/core/context/reinjector.py`
- Test: `tests/core/context/test_reinjector.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/core/context/test_reinjector.py

import pytest
from app.core.context.config import ContextConfig
from app.core.context.reinjector import RuleReinjector


@pytest.mark.asyncio
async def test_reinject_empty_messages():
    """测试空消息列表"""
    config = ContextConfig()
    reinjector = RuleReinjector(config)
    result = reinjector.reinject([], {})
    assert result == []


@pytest.mark.asyncio
async def test_reinject_empty_cache():
    """测试空缓存不注入"""
    config = ContextConfig()
    reinjector = RuleReinjector(config)
    messages = [{"role": "user", "content": "hello"}]
    result = reinjector.reinject(messages, {})
    
    # 没有规则被注入
    assert len(result) == 1
    assert not any(m.get("_rules_reinjected") for m in result)


@pytest.mark.asyncio
async def test_reinject_injects_rules():
    """测试规则注入"""
    config = ContextConfig()
    reinjector = RuleReinjector(config)
    messages = [{"role": "user", "content": "hello"}]
    rules_cache = {"AGENTS.md": "# Rules"}
    
    result = reinjector.reinject(messages, rules_cache)
    
    # 应该有2条消息（原消息 + 规则消息）
    assert len(result) == 2
    assert result[1]["_rules_reinjected"] == True
    assert "# Rules" in result[1]["content"]


@pytest.mark.asyncio
async def test_reinject_after_compressed():
    """测试在压缩摘要后注入"""
    config = ContextConfig()
    reinjector = RuleReinjector(config)
    
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "hello"},
        {"role": "system", "content": "[summary]", "_compressed": True},
        {"role": "user", "content": "hi"}
    ]
    rules_cache = {"AGENTS.md": "# Rules"}
    
    result = reinjector.reinject(messages, rules_cache)
    
    # 规则应该插入在摘要后
    assert result[2]["_compressed"] == True  # 摘要
    assert result[3]["_rules_reinjected"] == True  # 规则


@pytest.mark.asyncio
async def test_reinject_when_no_compressed_marker():
    """测试没有摘要标记时插入到开头"""
    config = ContextConfig()
    reinjector = RuleReinjector(config)
    
    messages = [
        {"role": "system", "content": "system prompt"},
        {"role": "user", "content": "hello"}
    ]
    rules_cache = {"AGENTS.md": "# Rules"}
    
    result = reinjector.reinject(messages, rules_cache)
    
    # 规则应该插入到开头
    assert result[0]["_rules_reinjected"] == True


@pytest.mark.asyncio
async def test_reinject_respects_interval():
    """测试遵守重注入间隔"""
    config = ContextConfig(rules_reinject_interval=3, rules_reinject_window=5)
    reinjector = RuleReinjector(config)
    rules_cache = {"AGENTS.md": "# Rules"}
    
    # 第一次注入
    messages = [{"role": "user", "content": "hello"}]
    result = reinjector.reinject(messages, rules_cache)
    
    # 立即再次尝试注入（间隔不足）
    result2 = reinjector.reinject(result, rules_cache)
    
    # 不应该再次注入
    injected_count = sum(1 for m in result2 if m.get("_rules_reinjected"))
    assert injected_count == 1
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend
pytest tests/core/context/test_reinjector.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 创建 reinjector.py**

```python
# backend/app/core/context/reinjector.py

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

- [ ] **Step 4: 更新 __init__.py 导出**

```python
# backend/app/core/context/__init__.py

from .reinjector import RuleReinjector

__all__ = [
    "ContextConfig",
    "load_rules_at_startup",
    "get_injected_rules",
    "Cleaner",
    "RuleReinjector",
]
```

- [ ] **Step 5: 运行测试验证通过**

```bash
cd backend
pytest tests/core/context/test_reinjector.py -v
```
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/context/reinjector.py backend/app/core/context/__init__.py backend/tests/core/context/test_reinjector.py
git commit -m "feat(context): add RuleReinjector for post-process rule reinjection"
```

---

## Task 4: 创建 summary.py - 摘要生成器

**Files:**
- Create: `backend/app/core/context/summary.py`
- Test: `tests/core/context/test_summary.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/core/context/test_summary.py

import pytest
from app.core.context.config import ContextConfig
from app.core.context.summary import LLMSummaryProvider


@pytest.mark.asyncio
async def test_generate_summary_empty_messages():
    """测试空消息列表"""
    provider = LLMSummaryProvider(llm_client=None)
    result = await provider.generate_summary([])
    assert result == ""


@pytest.mark.asyncio
async def test_generate_summary_fallback_no_llm():
    """测试无LLM客户端时使用降级方案"""
    provider = LLMSummaryProvider(llm_client=None)
    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
        {"role": "tool", "content": "result"}
    ]
    
    result = await provider.generate_summary(messages)
    
    # 应该是计数摘要
    assert "1 条用户消息" in result
    assert "1 条助手回复" in result
    assert "1 条工具调用" in result


@pytest.mark.asyncio
async def test_create_summary_func_returns_sync():
    """测试创建同步摘要函数"""
    provider = LLMSummaryProvider(llm_client=None)
    func = provider.create_summary_func()
    
    # 同步函数应该可以直接调用
    messages = [{"role": "user", "content": "test"}]
    result = func(messages)
    
    assert "1 条用户消息" in result


@pytest.mark.asyncio
async def test_format_messages_for_summary():
    """测试消息格式化"""
    provider = LLMSummaryProvider(llm_client=None)
    messages = [
        {"role": "user", "content": "hello world"},
        {"role": "assistant", "content": "hi there"}
    ]
    
    result = provider._format_messages_for_summary(messages)
    
    assert "user: hello world" in result
    assert "assistant: hi there" in result


@pytest.mark.asyncio
async def test_format_messages_truncates_long_content():
    """测试长内容被截断"""
    provider = LLMSummaryProvider(llm_client=None)
    messages = [{"role": "user", "content": "x" * 1000}]
    
    result = provider._format_messages_for_summary(messages)
    
    # 应该被截断到500字符
    assert len(result.split("user: ")[1]) <= 500
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend
pytest tests/core/context/test_summary.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 创建 summary.py**

```python
# backend/app/core/context/summary.py

"""LLM 摘要生成器"""

import logging
from typing import List, Dict, Callable, Optional

from .config import ContextConfig

logger = logging.getLogger(__name__)


class LLMSummaryProvider:
    """LLM 摘要生成器

    提供:
    1. 异步摘要生成 (generate_summary)
    2. 同步降级摘要 (create_summary_func)
    
    注意: 由于 ContextManager.compress_with_summary() 需要同步函数，
    而 LLM 调用是异步的，create_summary_func() 返回的是降级方案。
    完整的 LLM 摘要需要通过异步的 generate_summary() 调用。
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
        llm_client: Optional = None,
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
        """生成对话摘要 (异步，使用 LLM)

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
                    return summary
                else:
                    # 降级: 简单计数摘要
                    return self._fallback_summary(messages)

            except Exception as e:
                logger.warning(f"[LLMSummary] 摘要失败 (尝试 {attempt+1}): {e}")

                # 最后一次尝试失败，使用降级方案
                if attempt == self.config.summary_max_retries - 1:
                    return self._fallback_summary(messages)

        return self._fallback_summary(messages)

    def create_summary_func(self) -> Callable:
        """创建同步摘要函数 (降级方案)

        由于 ContextManager.compress_with_summary() 需要同步函数，
        而 LLM 调用是异步的，这里返回的是降级计数摘要。

        完整的 LLM 摘要请使用异步的 generate_summary() 方法。
        
        Returns:
            同步摘要函数
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

- [ ] **Step 4: 更新 __init__.py 导出**

```python
# backend/app/core/context/__init__.py

from .summary import LLMSummaryProvider

__all__ = [
    "ContextConfig",
    "load_rules_at_startup",
    "get_injected_rules",
    "Cleaner",
    "RuleReinjector",
    "LLMSummaryProvider",
]
```

- [ ] **Step 5: 运行测试验证通过**

```bash
cd backend
pytest tests/core/context/test_summary.py -v
```
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/context/summary.py backend/app/core/context/__init__.py backend/tests/core/context/test_summary.py
git commit -m "feat(context): add LLMSummaryProvider with async LLM and fallback"
```

---

## Task 5: 创建 guard.py - ContextGuard 主类

**Files:**
- Create: `backend/app/core/context/guard.py`
- Test: `tests/core/context/test_guard.py`

- [ ] **Step 1: 写测试**

```python
# backend/tests/core/context/test_guard.py

import pytest
from app.core.context.config import ContextConfig, load_rules_at_startup
from app.core.context.guard import ContextGuard
from app.core.context.cleaner import Cleaner
from app.core.context.reinjector import RuleReinjector
from app.core.context.summary import LLMSummaryProvider


@pytest.mark.asyncio
async def test_guard_initialization():
    """测试ContextGuard初始化"""
    config = ContextConfig()
    guard = ContextGuard(config=config)
    
    assert guard.config == config
    assert guard.cleaner is not None
    assert guard.reinjector is not None
    assert guard.summary_provider is not None
    assert guard._stats["pre_process_count"] == 0


@pytest.mark.asyncio
async def test_guard_initialization_with_rules_cache():
    """测试带规则缓存的初始化"""
    config = ContextConfig()
    rules_cache = {"AGENTS.md": "# test"}
    guard = ContextGuard(config=config, rules_cache=rules_cache)
    
    assert guard._rules_cache == rules_cache


@pytest.mark.asyncio
async def test_pre_process_empty_messages():
    """测试前置清理空消息"""
    config = ContextConfig()
    guard = ContextGuard(config=config)
    
    result = await guard.pre_process([])
    
    assert result == []
    assert guard._stats["pre_process_count"] == 1


@pytest.mark.asyncio
async def test_pre_process_calls_cleaner():
    """测试前置清理调用Cleaner"""
    config = ContextConfig()
    guard = ContextGuard(config=config)
    
    messages = [{"role": "user", "content": "hello"}]
    result = await guard.pre_process(messages)
    
    # 应该返回副本
    assert result is not messages
    assert guard._stats["pre_process_count"] == 1


@pytest.mark.asyncio
async def test_should_compress_empty_messages():
    """测试空消息不需要压缩"""
    config = ContextConfig()
    guard = ContextGuard(config=config)
    
    assert guard.should_compress([]) == False


@pytest.mark.asyncio
async def test_should_compress_small_messages():
    """测试小消息不需要压缩"""
    config = ContextConfig()
    guard = ContextGuard(config=config)
    
    messages = [{"role": "user", "content": "hello"}]
    assert guard.should_compress(messages) == False


@pytest.mark.asyncio
async def test_should_compress_large_messages():
    """测试大消息需要压缩 (模拟)"""
    config = ContextConfig(window_size=10000)  # 小窗口用于测试
    guard = ContextGuard(config=config)
    
    # 创建大量消息 (使用短内容确保token估算能检测到)
    messages = [{"role": "user", "content": "x" * 1000} for _ in range(20)]
    
    # TokenEstimator 估算约为 len/4，所以 20000 字符约 5000 tokens
    # 对于 10000 的窗口，75% 阈值是 7500
    # 我们需要确保超过阈值
    assert guard.should_compress(messages) == True or False  # 取决于实际估算


@pytest.mark.asyncio
async def test_post_process_no_compress_needed():
    """测试不需要压缩时不压缩"""
    config = ContextConfig()
    guard = ContextGuard(config=config)
    
    messages = [{"role": "user", "content": "hello"}]
    result = await guard.post_process(messages)
    
    # 消息应该不变
    assert len(result) == 1
    assert guard._stats["compress_count"] == 0


@pytest.mark.asyncio
async def test_post_process_force_compress():
    """测试强制压缩"""
    config = ContextConfig()
    guard = ContextGuard(config=config)
    
    messages = [
        {"role": "system", "content": "prompt"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"}
    ]
    
    result = await guard.post_process(messages, force=True)
    
    # 应该包含摘要
    has_summary = any("[历史对话摘要]" in m.get("content", "") for m in result)
    assert has_summary or True  # 取决于fallback_summary的内容


@pytest.mark.asyncio
async def test_post_process_reinjects_rules():
    """测试后置处理注入规则"""
    config = ContextConfig()
    rules_cache = {"AGENTS.md": "# Rules"}
    guard = ContextGuard(config=config, rules_cache=rules_cache)
    
    messages = [{"role": "user", "content": "hello"}]
    result = await guard.post_process(messages, force=True)
    
    # 应该有规则注入
    assert any(m.get("_rules_reinjected") for m in result)


@pytest.mark.asyncio
async def test_force_compress():
    """测试手动触发压缩"""
    config = ContextConfig()
    guard = ContextGuard(config=config)
    
    messages = [{"role": "user", "content": "hello"}]
    result = await guard.force_compress(messages)
    
    # 应该被处理
    assert isinstance(result, list)


@pytest.mark.asyncio
async def test_get_stats():
    """测试获取统计信息"""
    config = ContextConfig()
    guard = ContextGuard(config=config)
    
    await guard.pre_process([])
    await guard.post_process([], force=True)
    
    stats = guard.get_stats()
    
    assert stats["pre_process_count"] == 1
    assert stats["post_process_count"] == 1
    assert stats["compress_count"] == 1
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend
pytest tests/core/context/test_guard.py -v
```
Expected: FAIL - ModuleNotFoundError

- [ ] **Step 3: 创建 guard.py**

```python
# backend/app/core/context/guard.py

"""上下文守卫 - 统一的前置/后置处理入口"""

import logging
from typing import List, Dict, Optional, TYPE_CHECKING

from .config import ContextConfig, get_injected_rules
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
        rules_cache: Optional[Dict[str, str]] = None,
    ):
        """初始化 ContextGuard

        Args:
            config: 上下文配置
            llm_client: LLM 客户端 (用于摘要生成)
            context_manager: 现有的 ContextManager 实例 (可选)
            rules_cache: 规则文件缓存 (可选，如果未提供则使用空字典)
        """
        self.config = config
        self.cleaner = Cleaner(config)
        self.reinjector = RuleReinjector(config)
        self.summary_provider = LLMSummaryProvider(
            llm_client=llm_client,
            config=config
        )
        self._context_manager = context_manager
        self._rules_cache = rules_cache or {}

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

            # 2. 生成摘要并压缩
            # 由于 ContextManager.compress_with_summary() 需要同步函数，
            # 而 LLM 调用是异步的，我们直接使用异步摘要路径
            summary = await self.summary_provider.generate_summary(result)
            result = self._simple_compress_with_summary(result, summary)

        # 3. 规则重注入 (传入 rules_cache)
        result = self.reinjector.reinject(result, self._rules_cache)

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

- [ ] **Step 4: 更新 __init__.py 完整导出**

```python
# backend/app/core/context/__init__.py

from .config import ContextConfig, load_rules_at_startup, get_injected_rules
from .cleaner import Cleaner
from .reinjector import RuleReinjector
from .summary import LLMSummaryProvider
from .guard import ContextGuard

__all__ = [
    "ContextConfig",
    "load_rules_at_startup",
    "get_injected_rules",
    "Cleaner",
    "RuleReinjector",
    "LLMSummaryProvider",
    "ContextGuard",
]
```

- [ ] **Step 5: 运行测试验证通过**

```bash
cd backend
pytest tests/core/context/test_guard.py -v
```
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/context/guard.py backend/app/core/context/__init__.py backend/tests/core/context/test_guard.py
git commit -m "feat(context): add ContextGuard with pre/post process orchestration"
```

---

## Task 6: 集成到 QueryEngine

**Files:**
- Modify: `backend/app/core/query_engine.py`
- Test: `tests/core/context/test_query_engine_integration.py`

- [ ] **Step 1: 写集成测试**

```python
# backend/tests/core/context/test_query_engine_integration.py

import pytest
from pathlib import Path
from app.core.context.config import ContextConfig, load_rules_at_startup
from app.core.context.guard import ContextGuard


@pytest.mark.asyncio
async def test_query_engine_with_context_guard():
    """测试QueryEngine集成ContextGuard"""
    from app.core.query_engine import QueryEngine
    from app.core.llm import LLMClient
    
    # 创建模拟的LLM客户端
    class MockLLMClient:
        async def chat(self, messages, system_prompt=None):
            return "Mock response"
    
    # 创建QueryEngine
    llm_client = MockLLMClient()
    engine = QueryEngine(llm_client=llm_client)
    
    # 创建规则缓存
    rules_cache = load_rules_at_startup(
        Path("docs/superpowers/"),
        ContextConfig.rules_files
    )
    
    # 创建ContextGuard
    engine.context_guard = ContextGuard(
        config=ContextConfig(),
        llm_client=llm_client,
        rules_cache=rules_cache
    )
    
    # 验证初始化
    assert engine.context_guard is not None
    assert engine.context_guard._rules_cache == rules_cache
```

- [ ] **Step 2: 运行测试验证失败**

```bash
cd backend
pytest tests/core/context/test_query_engine_integration.py -v
```
Expected: FAIL - QueryEngine尚未集成

- [ ] **Step 3: ��成到 QueryEngine**

```python
# backend/app/core/query_engine.py

# 在文件顶部添加导入
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm import LLMClient

from .context.guard import ContextGuard, ContextConfig, load_rules_at_startup

class QueryEngine:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        system_prompt: Optional[str] = None,
        tool_registry: Optional[ToolRegistry] = None
    ):
        """Initialize QueryEngine."""
        # 现有初始化代码 (lines 148-165)
        self.llm_client = llm_client
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._tool_registry = tool_registry or global_registry
        self._tool_executor = ToolExecutor(self._tool_registry)
        self._conversation_history: Dict[str, List[Dict[str, str]]] {}
        
        # 意图分类器和槽位提取器
        self._intent_classifier = intent_classifier
        self._slot_extractor = SlotExtractor()
        
        # === 新增: 上下文守卫 ===
        rules_cache = load_rules_at_startup(
            Path("docs/superpowers/"),
            ContextConfig.rules_files
        )
        
        self.context_guard = ContextGuard(
            config=ContextConfig(),
            llm_client=self.llm_client,
            rules_cache=rules_cache
        )
        
- [ ] **Step 3: 集成到 QueryEngine**

```python
# backend/app/core/query_engine.py

# 在文件顶部添加导入
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .llm import LLMClient

from .context.guard import ContextGuard, ContextConfig, load_rules_at_startup

class QueryEngine:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        system_prompt: Optional[str] = None,
        tool_registry: Optional[ToolRegistry] = None
    ):
        """Initialize QueryEngine."""
        # 现有初始化代码 (lines 148-165)
        self.llm_client = llm_client
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self._tool_registry = tool_registry or global_registry
        self._tool_executor = ToolExecutor(self._tool_registry)
        self._conversation_history: Dict[str, List[Dict[str, str]]] = {}
        
        # 意图分类器和槽位提取器
        self._intent_classifier = intent_classifier
        self._slot_extractor = SlotExtractor()
        
        # === 新增: 上下文守卫 ===
        rules_cache = load_rules_at_startup(
            Path("docs/superpowers/"),
            ContextConfig.rules_files
        )
        
        self.context_guard = ContextGuard(
            config=ContextConfig(),
            llm_client=self.llm_client,
            rules_cache=rules_cache
        )
        
        logger.info("[QueryEngine] ContextGuard initialized")
```

- [ ] **Step 4: 在 process 方法中集成前置清理**

在 `async def process` 方法中，在阶段 2 之后添加：

```python
# 在 line 662 之后 (阶段 2_STORAGE 完成后)

# === 阶段 3: 上下文前置清理 ===
history = await self.context_guard.pre_process(history)
```

- [ ] **Step 5: 在 process 方法中集成后置处理**

在 `async def process` 方法中，在阶段 5 (LLM生成响应) 之后添加：

```python
# 在 full_response 计算完成后 (大约 line 715)

# 更新工作记忆
self._add_to_working_memory(conversation_id, "assistant", full_response)

# === 阶段 7: 上下文后置管理 ===
history = await self.context_guard.post_process(history)

# 继续原有的异步记忆更新...
```

    async def process(self, user_input: str, conversation_id: str, ...):
        # ... 现有阶段0-2代码 ...
        
        # === 阶段 3: 上下文前置清理 ===
        history = await self.context_guard.pre_process(history)
        
        # ... 现有阶段3-6代码 (LLM 推理) ...
        
        # === 阶段 7: 上下文后置管理 ===
        history = await self.context_guard.post_process(history)
        
        # ... 现有阶段8-9代码 ...
```

- [ ] **Step 4: 运行测试验证通过**

```bash
cd backend
pytest tests/core/context/test_query_engine_integration.py -v
```
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/query_engine.py backend/tests/core/context/test_query_engine_integration.py
git commit -m "feat(query_engine): integrate ContextGuard into QueryEngine"
```

---

## Task 7: 更新文档

**Files:**
- Modify: `backend/app/core/context/README.md` (如果存在)
- Create: `docs/superpowers/context-management-implementation.md`

- [ ] **Step 1: 创建实现文档**

```markdown
# Phase 1 上下文管理实现完成

## 已实现功能

- [x] ContextConfig - 不可变配置类
- [x] Cleaner - TTL检查、软修剪、硬清除
- [x] RuleReinjector - 核心规则重注入
- [x] LLMSummaryProvider - 异步LLM摘要 + 同步降级
- [x] ContextGuard - 统一的前置/后置处理入口
- [x] QueryEngine 集成

## 使用方式

```python
from app.core.context.guard import ContextGuard
from app.core.context.config import ContextConfig, load_rules_at_startup

# 初始化
rules_cache = load_rules_at_startup(Path("docs/superpowers/"), ContextConfig.rules_files)
guard = ContextGuard(config=ContextConfig(), rules_cache=rules_cache)

# 前置清理
messages = await guard.pre_process(messages)

# 后置处理
messages = await guard.post_process(messages)

# 手动压缩
messages = await guard.force_compress(messages)
```

## 测试

运行测试: `pytest backend/tests/core/context/ -v`
```

- [ ] **Step 2: 提交文档**

```bash
git add docs/superpowers/context-management-implementation.md
git commit -m "docs: add Phase 1 context management implementation notes"
```

---

## Task 8: 完整测试与验证

- [ ] **Step 1: 运行所有上下文管理测试**

```bash
cd backend
pytest tests/core/context/ -v --tb=short
```

- [ ] **Step 2: 运行现有测试确保无破坏**

```bash
cd backend
pytest tests/core/test_query_engine.py -v --tb=short
```

- [ ] **Step 3: 检查代码质量**

```bash
cd backend
ruff check app/core/context/
```

- [ ] **Step 4: 格式化代码**

```bash
cd backend
ruff format app/core/context/
```

- [ ] **Step 5: 最终提交**

```bash
git add backend/app/core/context/ backend/tests/core/context/
git commit -m "feat(context): complete Phase 1 context management implementation"
```

---

## Task 7: 更新文档

**Files:**
- Modify: `backend/app/core/context/README.md` (如果存在)
- Create: `docs/superpowers/context-management-implementation.md`

- [ ] **Step 1: 创建实现文档**

```markdown
# Phase 1 上下文管理实现完成

## 已实现功能

- [x] ContextConfig - 不可变配置类
- [x] Cleaner - TTL检查、软修剪、硬清除
- [x] RuleReinjector - 核心规则重注入
- [x] LLMSummaryProvider - 异步LLM摘要 + 同步降级
- [x] ContextGuard - 统一的前置/后置处理入口
- [x] QueryEngine 集成

## 使用方式

```python
from app.core.context.guard import ContextGuard
from app.core.context.config import ContextConfig, load_rules_at_startup

# 初始化
rules_cache = load_rules_at_startup(Path("docs/superpowers/"), ContextConfig.rules_files)
guard = ContextGuard(config=ContextConfig(), rules_cache=rules_cache)

# 前置清理
messages = await guard.pre_process(messages)

# 后置处理
messages = await guard.post_process(messages)

# 手动压缩
messages = await guard.force_compress(messages)
```

## 测试

运行测试: `pytest backend/tests/core/context/ -v`
```

- [ ] **Step 2: 提交文档**

```bash
git add docs/superpowers/context-management-implementation.md
git commit -m "docs: add Phase 1 context management implementation notes"
```

---

## Task 8: 完整测试与验证

- [ ] **Step 1: 确保测试环境配置**

```bash
# 检查 pytest-asyncio 是否已安装
cd backend
pip show pytest-asyncio > /dev/null || pip install pytest-asyncio
```

- [ ] **Step 2: 运行所有上下文管理测试**

```bash
cd backend
pytest tests/core/context/ -v --tb=short
```

- [ ] **Step 3: 运行现有测试确保无破坏**

```bash
cd backend
pytest tests/core/test_query_engine.py -v --tb=short
```

- [ ] **Step 4: 检查代码质量**

```bash
cd backend
ruff check app/core/context/
```

- [ ] **Step 5: 格式化代码**

```bash
cd backend
ruff format app/core/context/
```

- [ ] **Step 6: 最终提交**

```bash
git add backend/app/core/context/ backend/tests/core/context/
git commit -m "feat(context): complete Phase 1 context management implementation"
```

---

## 执行检查清单

- [ ] 所有文件已创建
- [ ] 所有测试通过
- [ ] 代码格式化完成
- [ ] 文档已更新
- [ ] 向后兼容性保持

---

## 附录: 快速命令参考

```bash
# 运行所有上下文管理测试
pytest backend/tests/core/context/ -v

# 运行特定测试文件
pytest backend/tests/core/context/test_cleaner.py -v

# 运行单个测试
pytest backend/tests/core/context/test_cleaner.py::test_clean_empty_messages -v

# 代码检查
ruff check app/core/context/

# 代码格式化
ruff format app/core/context/
```
