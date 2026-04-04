# Phase 3: 会话生命周期 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 QueryEngine 基础上添加会话生命周期管理，包括 Step 0 初始化、异常分类器、差异化重试和降级机制。

**Architecture:** 在现有 QueryEngine 6步工作流程外围包装会话初始化和重试循环，使用 PostgreSQL 持久化会话状态，支持连接恢复。

**Tech Stack:** FastAPI, asyncpg, PostgreSQL, asyncio, Pydantic

---

## File Structure

```
backend/app/core/session/
├── __init__.py              # 模块导出
├── state.py                 # SessionState 数据模型
├── error_classifier.py      # ErrorClassifier + 枚举定义
├── retry_manager.py         # RetryManager
├── fallback.py              # FallbackHandler
├── initializer.py           # SessionInitializer（依赖以上组件）
└── recovery.py              # 会话恢复逻辑

backend/app/core/
├── __init__.py              # 添加 session 模块导出

backend/app/db/
├── postgres.py              # 添加 session_states 表创建
├── session_repo.py          # 会话状态仓储

backend/tests/core/session/
├── __init__.py
├── test_state.py
├── test_error_classifier.py
├── test_retry_manager.py
├── test_fallback.py
├── test_initializer.py
└── test_recovery.py
```

---

## Task 1: 创建数据库表和基础操作

**Dependencies:** None (first task)

**Files:**
- Modify: `backend/app/db/postgres.py` (添加 session_states 表创建)
- Create: `backend/app/db/session_repo.py` (会话状态仓储)

- [ ] **Step 1: 在 postgres.py 中添加 session_states 表创建**

在 `_create_tables_if_not_exists` 方法末尾添加：

```python
# Create session_states table (per Phase 3: 会话生命周期)
await conn.execute("""
    CREATE TABLE IF NOT EXISTS session_states (
        session_id UUID PRIMARY KEY,
        user_id UUID NOT NULL,
        conversation_id UUID NOT NULL,
        core_state JSONB DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        updated_at TIMESTAMPTZ DEFAULT NOW(),
        last_activity TIMESTAMPTZ DEFAULT NOW()
)
""")

await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_session_states_user 
    ON session_states(user_id)
""")

await conn.execute("""
    CREATE INDEX IF NOT EXISTS idx_session_states_conv 
    ON session_states(conversation_id)
""")
```

- [ ] **Step 2: 创建 SessionRepository 类**

```python
# backend/app/db/session_repo.py
from typing import Optional, Dict, Any
from uuid import UUID
import json
import asyncpg

from app.db.postgres import Database

class SessionRepository:
    """会话状态仓储"""
    
    async def save_state(
        self, 
        session_id: UUID, 
        user_id: UUID, 
        conversation_id: UUID, 
        core_state: Dict[str, Any]
    ) -> None:
        async with Database.connection() as conn:
            await conn.execute("""
                INSERT INTO session_states (session_id, user_id, conversation_id, core_state)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (session_id) DO UPDATE SET
                    core_state = $4,
                    updated_at = NOW(),
                    last_activity = NOW()
            """, session_id, user_id, conversation_id, json.dumps(core_state))

    async def get_state(self, session_id: UUID) -> Optional[Dict[str, Any]]:
        async with Database.connection() as conn:
            row = await conn.fetchrow("""
                SELECT core_state FROM session_states WHERE session_id = $1
            """, session_id)
            return json.loads(row["core_state"]) if row else None

    async def update_activity(self, session_id: UUID) -> None:
        async with Database.connection() as conn:
            await conn.execute("""
                UPDATE session_states SET last_activity = NOW() WHERE session_id = $1
            """, session_id)

# 模块级实例
session_repo = SessionRepository()
```

- [ ] **Step 3: 运行测试验证表创建**

```bash
cd backend && python -c "
import asyncio
from app.db.postgres import Database
asyncio.run(Database.connect())
print('Tables created successfully')
"
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/db/postgres.py backend/app/db/session_repo.py
git commit -m "feat(phase3): add session_states table and repository"
```

---

## Task 2: 实现 ErrorClassifier

**Dependencies:** None (独立组件)

**Files:**
- Create: `backend/app/core/session/state.py` (基础枚举定义)
- Create: `backend/app/core/session/error_classifier.py`
- Create: `backend/tests/core/session/test_error_classifier.py`

- [ ] **Step 1: 创建基础枚举定义 (state.py)**

```python
# backend/app/core/session/state.py
from enum import Enum
from typing import Optional, Tuple
from pydantic import BaseModel
from uuid import UUID

class ErrorCategory(Enum):
    """错误类别"""
    TRANSIENT = "transient"      # 临时错误（网络、超时）
    VALIDATION = "validation"    # 验证错误（参数、格式）
    PERMISSION = "permission"    # 权限错误（API密钥、访问）
    FATAL = "fatal"             # 致命错误（不可恢复）

class RecoveryStrategy(Enum):
    """恢复策略"""
    RETRY = "retry"                      # 立即重试
    RETRY_BACKOFF = "retry_backoff"      # 退避重试
    DEGRADE = "degrade"                  # 降级响应
    SKIP = "skip"                        # 跳过该步骤
    FAIL = "fail"                        # 立即失败

class SessionState(BaseModel):
    """会话状态"""
    session_id: UUID
    user_id: UUID
    conversation_id: UUID
    context_window_size: int = 128000
    soft_trim_ratio: float = 0.3
    hard_clear_ratio: float = 0.5
    max_spawn_depth: int = 2
    max_concurrent: int = 8
    max_children: int = 5
```

- [ ] **Step 2: 实现 ErrorClassifier**

```python
# backend/app/core/session/error_classifier.py
import asyncio
import logging
from typing import Dict, Tuple

from .state import ErrorCategory, RecoveryStrategy

logger = logging.getLogger(__name__)

# 预设分类规则
PRESET_RULES = {
    # 临时错误 - 可重试
    TimeoutError: (ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY, 3),
    ConnectionError: (ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY, 3),
    asyncio.TimeoutError: (ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY_BACKOFF, 2),
    
    # 验证错误 - 降级处理
    ValueError: (ErrorCategory.VALIDATION, RecoveryStrategy.DEGRADE, 0),
    
    # 权限错误 - 立即失败
    PermissionError: (ErrorCategory.PERMISSION, RecoveryStrategy.FAIL, 0),
}

class ErrorClassification:
    """错误分类结果"""
    def __init__(
        self, 
        category: ErrorCategory, 
        strategy: RecoveryStrategy, 
        max_retries: int
    ):
        self.category = category
        self.strategy = strategy
        self.max_retries = max_retries

class ErrorClassifier:
    """异常分类器
    
    根据异常类型决定恢复策略和最大重试次数。
    支持预定义规则 + 可配置覆盖。
    """
    
    def __init__(self, custom_rules: Optional[Dict[str, Tuple[ErrorCategory, RecoveryStrategy, int]]] = None):
        """初始化分类器
        
        Args:
            custom_rules: 自定义规则 {异常类型名: (类别, 策略, 最大重试)}
        """
        from typing import Optional, Tuple
        
        self._preset_rules = dict(PRESET_RULES)
        self._custom_rules = custom_rules or {}
        logger.info(f"[ErrorClassifier] 初始化完成 | 预设规则={len(self._preset_rules)}, 自定义={len(self._custom_rules)}")
    
    def classify(self, error: Exception) -> ErrorClassification:
        """分类异常
        
        Args:
            error: 异常实例
            
        Returns:
            ErrorClassification: 分类结果
        """
        error_type = type(error)
        error_name = error_type.__name__
        
        # 检查自定义规则
        if error_name in self._custom_rules:
            category, strategy, max_retries = self._custom_rules[error_name]
            return ErrorClassification(category, strategy, max_retries)
        
        # 检查预设规则（包括父类）
        for rule_type, (category, strategy, max_retries) in self._preset_rules.items():
            if isinstance(error, rule_type):
                logger.debug(f"[ErrorClassifier] 分类: {error_name} → {category.value}/{strategy.value}")
                return ErrorClassification(category, strategy, max_retries)
        
        # 默认：临时错误，重试1次
        logger.warning(f"[ErrorClassifier] 未知异常类型: {error_name}, 使用默认分类")
        return ErrorClassification(ErrorCategory.TRANSIENT, RecoveryStrategy.RETRY, 1)
```

- [ ] **Step 3: 编写测试**

```python
# backend/tests/core/session/test_error_classifier.py
import pytest
from app.core.session.error_classifier import ErrorClassifier, ErrorClassification
from app.core.session.state import ErrorCategory, RecoveryStrategy

def test_timeout_error_classification():
    classifier = ErrorClassifier()
    error = TimeoutError("Request timeout")
    
    result = classifier.classify(error)
    
    assert result.category == ErrorCategory.TRANSIENT
    assert result.strategy == RecoveryStrategy.RETRY
    assert result.max_retries == 3

def test_validation_error_classification():
    classifier = ErrorClassifier()
    error = ValueError("Invalid parameter")
    
    result = classifier.classify(error)
    
    assert result.category == ErrorCategory.VALIDATION
    assert result.strategy == RecoveryStrategy.DEGRADE
    assert result.max_retries == 0

def test_permission_error_classification():
    classifier = ErrorClassifier()
    error = PermissionError("Access denied")
    
    result = classifier.classify(error)
    
    assert result.category == ErrorCategory.PERMISSION
    assert result.strategy == RecoveryStrategy.FAIL
    assert result.max_retries == 0

def test_unknown_error_default_classification():
    classifier = ErrorClassifier()
    error = RuntimeError("Unknown error")
    
    result = classifier.classify(error)
    
    assert result.category == ErrorCategory.TRANSIENT
    assert result.strategy == RecoveryStrategy.RETRY
    assert result.max_retries == 1
```

- [ ] **Step 4: 运行测试**

```bash
cd backend && pytest tests/core/session/test_error_classifier.py -v
```

- [ ] **Step 5: 提交**

```bash
git add backend/app/core/session/state.py backend/app/core/session/error_classifier.py tests/core/session/test_error_classifier.py
git commit -m "feat(phase3): implement ErrorClassifier with preset and custom rules"
```

---

## Task 3: 实现 RetryManager

**Dependencies:** Task 2 (ErrorClassifier)

**Files:**
- Create: `backend/app/core/session/retry_manager.py`
- Create: `backend/tests/core/session/test_retry_manager.py`

- [ ] **Step 1: 实现 RetryManager**

```python
# backend/app/core/session/retry_manager.py
import asyncio
import logging
from typing import Dict

from .state import ErrorCategory, RecoveryStrategy
from .error_classifier import ErrorClassifier, ErrorClassification

logger = logging.getLogger(__name__)

class RetryPolicy:
    """重试策略配置"""
    def __init__(
        self,
        max_total_retries: int = 5,
        backoff_base: float = 1.0,
        backoff_max: float = 4.0
    ):
        self.max_total_retries = max_total_retries
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max

class RetryManager:
    """重试管理器
    
    跟踪重试次数，根据错误分类决定是否继续重试。
    """
    
    def __init__(
        self, 
        error_classifier: ErrorClassifier,
        policy: RetryPolicy = None
    ):
        """初始化重试管理器
        
        Args:
            error_classifier: 异常分类器
            policy: 重试策略配置
        """
        self._classifier = error_classifier
        self._policy = policy or RetryPolicy()
        self._retry_counts: Dict[str, int] = {}  # {conversation_id: count}
        self._last_errors: Dict[str, Exception] = {}  # {conversation_id: last_error}
    
    def should_retry(self, conversation_id: str, error: Exception) -> Tuple[bool, int]:
        """判断是否应该重试
        
        Args:
            conversation_id: 会话ID
            error: 发生的异常
            
        Returns:
            (should_retry, retry_count): (是否重试, 当前重试次数)
        """
        classification = self._classifier.classify(error)
        current_count = self._retry_counts.get(conversation_id, 0)
        
        # 记录错误
        self._last_errors[conversation_id] = error
        
        # 检查策略是否允许重试
        if classification.strategy == RecoveryStrategy.FAIL:
            logger.info(f"[RetryManager] 策略=FAIL, 不重试")
            return False, current_count
        
        if classification.strategy == RecoveryStrategy.SKIP:
            logger.info(f"[RetryManager] 策略=SKIP, 跳过重试")
            return False, current_count
        
        # 检查是否超过最大重试次数
        max_allowed = min(classification.max_retries, self._policy.max_total_retries)
        if current_count >= max_allowed:
            logger.warning(f"[RetryManager] 达到最大重试次数: {current_count} >= {max_allowed}")
            return False, current_count
        
        # 可以重试
        self._retry_counts[conversation_id] = current_count + 1
        logger.info(f"[RetryManager] 允许重试: {current_count + 1}/{max_allowed}")
        return True, current_count + 1
    
    async def apply_backoff(self, retry_count: int) -> None:
        """应用退避延迟
        
        Args:
            retry_count: 当前重试次数
        """
        if retry_count <= 0:
            return
        
        delay = min(
            self._policy.backoff_base * (2 ** (retry_count - 1)),
            self._policy.backoff_max
        )
        logger.info(f"[RetryManager] 退避延迟: {delay}s")
        await asyncio.sleep(delay)
    
    def reset(self, conversation_id: str) -> None:
        """重置会话的重试状态
        
        Args:
            conversation_id: 会话ID
        """
        self._retry_counts.pop(conversation_id, None)
        self._last_errors.pop(conversation_id, None)
        logger.debug(f"[RetryManager] 重置重试状态: conv={conversation_id}")
    
    def get_retry_count(self, conversation_id: str) -> int:
        """获取当前重试次数
        
        Args:
            conversation_id: 会话ID
            
        Returns:
            当前重试次数
        """
        return self._retry_counts.get(conversation_id, 0)
    
    def get_last_error(self, conversation_id: str) -> Exception:
        """获取最后一次错误
        
        Args:
            conversation_id: 会话ID
            
        Returns:
            最后一次发生的异常
        """
        return self._last_errors.get(conversation_id)
```

- [ ] **Step 2: 编写测试**

```python
# backend/tests/core/session/test_retry_manager.py
import pytest
import asyncio
from app.core.session.retry_manager import RetryManager, RetryPolicy
from app.core.session.error_classifier import ErrorClassifier

@pytest.mark.asyncio
async def test_transient_error_retry():
    classifier = ErrorClassifier()
    manager = RetryManager(classifier)
    conv_id = "test-conv"
    
    error = TimeoutError("Timeout")
    
    # 第一次：允许重试
    should_retry, count = manager.should_retry(conv_id, error)
    assert should_retry is True
    assert count == 1
    
    # 第二次：允许重试
    should_retry, count = manager.should_retry(conv_id, error)
    assert should_retry is True
    assert count == 2
    
    # 第三次：允许重试
    should_retry, count = manager.should_retry(conv_id, error)
    assert should_retry is True
    assert count == 3
    
    # 第四次：超过最大重试次数
    should_retry, count = manager.should_retry(conv_id, error)
    assert should_retry is False
    assert count == 3

@pytest.mark.asyncio
async def test_validation_error_no_retry():
    classifier = ErrorClassifier()
    manager = RetryManager(classifier)
    conv_id = "test-conv"
    
    error = ValueError("Invalid")
    
    should_retry, count = manager.should_retry(conv_id, error)
    assert should_retry is False  # VALIDATION 错误不重试
    assert count == 0

@pytest.mark.asyncio
async def test_backoff_delay():
    classifier = ErrorClassifier()
    policy = RetryPolicy(backoff_base=0.01, backoff_max=0.05)
    manager = RetryManager(classifier, policy)
    
    start = asyncio.get_event_loop().time()
    await manager.apply_backoff(2)
    elapsed = asyncio.get_event_loop().time() - start
    
    # 2^1 * 0.01 = 0.02s
    assert 0.015 < elapsed < 0.03

def test_reset():
    classifier = ErrorClassifier()
    manager = RetryManager(classifier)
    conv_id = "test-conv"
    
    error = TimeoutError("Timeout")
    manager.should_retry(conv_id, error)
    assert manager.get_retry_count(conv_id) == 1
    
    manager.reset(conv_id)
    assert manager.get_retry_count(conv_id) == 0
```

- [ ] **Step 3: 运行测试**

```bash
cd backend && pytest tests/core/session/test_retry_manager.py -v
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/session/retry_manager.py tests/core/session/test_retry_manager.py
git commit -m "feat(phase3): implement RetryManager with backoff support"
```

---

## Task 4: 实现 FallbackHandler

**Dependencies:** None (独立组件)

**Files:**
- Create: `backend/app/core/session/fallback.py`
- Create: `backend/tests/core/session/test_fallback.py`

- [ ] **Step 1: 实现 FallbackHandler**

```python
# backend/app/core/session/fallback.py
import logging
from typing import Dict, Any, Optional

from .state import ErrorCategory

logger = logging.getLogger(__name__)

# 降级响应模板
FALLBACK_MESSAGES = {
    "weather": "天气查询暂时不可用，基于历史平均数据为您规划行程。",
    "map": "地图功能暂不可用，以下是文字版路线描述。",
    "partial": "部分信息获取失败，已为您生成基于可用信息的行程。",
    "memory": "记忆服务暂不可用，本次对话偏好不会被保存。",
    "llm": "AI服务暂时繁忙，请稍后再试。",
    "default": "服务暂时不可用，请稍后再试。"
}

class FallbackResponse:
    """降级响应"""
    def __init__(
        self,
        should_degrade: bool,
        message: str,
        partial_results: Optional[Dict[str, Any]] = None
    ):
        self.should_degrade = should_degrade
        self.message = message
        self.partial_results = partial_results or {}

class FallbackHandler:
    """降级处理器
    
    根据错误类型生成降级响应，支持部分结果降级。
    """
    
    def __init__(self, custom_messages: Optional[Dict[str, str]] = None):
        """初始化降级处理器
        
        Args:
            custom_messages: 自定义降级消息
        """
        self._messages = {**FALLBACK_MESSAGES, **(custom_messages or {})}
        logger.info("[FallbackHandler] 初始化完成")
    
    def get_fallback(
        self, 
        error: Exception, 
        context: Optional[Dict[str, Any]] = None
    ) -> FallbackResponse:
        """获取降级响应
        
        Args:
            error: 发生的异常
            context: 错误上下文（包含部分结果等）
            
        Returns:
            FallbackResponse: 降级响应
        """
        error_type = type(error).__name__
        logger.info(f"[FallbackHandler] 生成降级响应: {error_type}")
        
        # 根据错误类型选择消息
        message_key = "default"
        partial_results = {}
        
        # 从上下文中提取部分结果
        if context:
            partial_results = context.get("partial_results", {})
            
            # 根据可用的部分结果调整消息
            if "weather" in partial_results and "map" not in partial_results:
                message_key = "map"
            elif "map" in partial_results and "weather" not in partial_results:
                message_key = "weather"
            elif partial_results:
                message_key = "partial"
        
        # 特殊错误类型的消息
        if "TimeoutError" in error_type or "ConnectionError" in error_type:
            if "llm" in str(error).lower() or "openai" in str(error).lower():
                message_key = "llm"
        elif "memory" in error_type.lower() or "chroma" in error_type.lower():
            message_key = "memory"
        
        message = self._messages.get(message_key, self._messages["default"])
        
        return FallbackResponse(
            should_degrade=True,
            message=message,
            partial_results=partial_results
        )
    
    def format_response(self, fallback: FallbackResponse) -> str:
        """格式化降级响应用于输出
        
        Args:
            fallback: 降级响应对象
            
        Returns:
            格式化的响应文本
        """
        if fallback.partial_results:
            # 有部分结果时，友好地展示
            parts = [fallback.message]
            if fallback.partial_results.get("weather"):
                parts.append(f"\n\n✓ 已获取天气信息")
            if fallback.partial_results.get("map"):
                parts.append(f"\n\n✓ 已获取路线信息")
            return "".join(parts)
        
        return fallback.message
```

- [ ] **Step 2: 编写测试**

```python
# backend/tests/core/session/test_fallback.py
import pytest
from app.core.session.fallback import FallbackHandler, FallbackResponse, FALLBACK_MESSAGES

def test_get_fallback_default():
    handler = FallbackHandler()
    error = Exception("Unknown error")
    
    result = handler.get_fallback(error)
    
    assert result.should_degrade is True
    assert "暂时不可用" in result.message

def test_get_fallback_with_context():
    handler = FallbackHandler()
    error = TimeoutError("Weather API timeout")
    context = {"partial_results": {"weather": "晴天 25°C"}}
    
    result = handler.get_fallback(error, context)
    
    assert result.should_degrade is True
    assert "地图" in result.message or "部分" in result.message

def test_format_response_with_partial():
    handler = FallbackHandler()
    fallback = FallbackResponse(
        should_degrade=True,
        message="部分信息获取失败",
        partial_results={"weather": "晴天", "map": "路线A"}
    )
    
    formatted = handler.format_response(fallback)
    
    assert "部分信息获取失败" in formatted
    assert "天气" in formatted or "路线" in formatted

def test_custom_messages():
    custom = {"weather": "天气功能维护中"}
    handler = FallbackHandler(custom_messages=custom)
    error = Exception("Weather error")
    
    result = handler.get_fallback(error)
    
    assert "维护中" in result.message
```

- [ ] **Step 3: 运行测试**

```bash
cd backend && pytest tests/core/session/test_fallback.py -v
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/session/fallback.py tests/core/session/test_fallback.py
git commit -m "feat(phase3): implement FallbackHandler with partial result support"
```

---

## Task 5: 实现 SessionInitializer (Step 0)

**Dependencies:** Task 1 (session_repo), Task 2 (ErrorClassifier), Task 3 (RetryManager), Task 4 (FallbackHandler)

**Files:**
- Create: `backend/app/core/session/initializer.py`
- Create: `backend/app/core/session/recovery.py`
- Modify: `backend/app/core/__init__.py` (导出 session 模块)
- Create: `backend/tests/core/session/test_initializer.py`

- [ ] **Step 1: 实现会话恢复逻辑**

```python
# backend/app/core/session/recovery.py
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

class SessionRecovery:
    """会话恢复逻辑"""
    
    async def recover(
        self,
        conversation_id: str,
        user_id: str
    ) -> Optional[Dict[str, Any]]:
        """尝试恢复会话状态
        
        Args:
            conversation_id: 会话ID
            user_id: 用户ID
            
        Returns:
            恢复的状态字典，如果无法恢复则返回None
        """
        try:
            from app.db.session_repo import session_repo
            from uuid import UUID
            import json
            
            # 查找该用户和会话的旧状态
            async with Database.connection() as conn:
                row = await conn.fetchrow("""
                    SELECT core_state, updated_at 
                    FROM session_states 
                    WHERE user_id = $1 AND conversation_id = $2
                    ORDER BY updated_at DESC 
                    LIMIT 1
                """, UUID(user_id), UUID(conversation_id))
                
                if row:
                    core_state = json.loads(row["core_state"])
                    logger.info(f"[SessionRecovery] 找到旧会话状态 | updated_at={row['updated_at']}")
                    
                    # 只恢复核心配置，不恢复临时状态
                    return {
                        k: v for k, v in core_state.items()
                        if k in [
                            "context_window_size", "soft_trim_ratio", 
                            "hard_clear_ratio", "max_spawn_depth"
                        ]
                    }
            
            logger.info("[SessionRecovery] 无旧会话状态可恢复")
            return None
            
        except Exception as e:
            logger.warning(f"[SessionRecovery] 恢复失败: {e}")
            return None
```

- [ ] **Step 2: 实现 SessionInitializer**

```python
# backend/app/core/session/initializer.py
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import UUID, uuid4

from .state import SessionState
from .error_classifier import ErrorClassifier
from .retry_manager import RetryManager, RetryPolicy
from .fallback import FallbackHandler
from .recovery import SessionRecovery

logger = logging.getLogger(__name__)

class SessionInitializer:
    """会话初始化器 (Step 0)
    
    在 WebSocket 连接建立时执行一次，完成：
    - 上下文窗口配置
    - 核心文件注入
    - 创建隔离会话
    - 初始化核心组件
    - 会话恢复（可选）
    """
    
    def __init__(
        self,
        config_path: Optional[Path] = None,
        custom_rules: Optional[Dict[str, Any]] = None
    ):
        """初始化
        
        Args:
            config_path: 配置文件路径
            custom_rules: 自定义异常分类规则
        """
        self._config_path = config_path
        self._config = self._load_config()
        
        # 初始化核心组件
        self._error_classifier = ErrorClassifier(custom_rules)
        self._retry_manager = RetryManager(self._error_classifier)
        self._fallback_handler = FallbackHandler()
        self._recovery = SessionRecovery()
        
        # 会话状态缓存
        self._active_sessions: Dict[str, SessionState] = {}
        
        logger.info("[SessionInitializer] 初始化完成")
    
    def _load_config(self) -> Dict[str, Any]:
        """加载配置文件
        
        Returns:
            配置字典
        """
        import json
        
        default_config = {
            "context_window_size": 128000,
            "soft_trim_ratio": 0.3,
            "hard_clear_ratio": 0.5,
            "max_spawn_depth": 2,
            "max_concurrent": 8,
            "max_children": 5
        }
        
        if self._config_path and self._config_path.exists():
            with open(self._config_path, 'r', encoding='utf-8') as f:
                user_config = json.load(f)
                default_config.update(user_config)
                logger.info(f"[SessionInitializer] 已加载配置: {self._config_path}")
        
        return default_config
    
    async def initialize(
        self,
        conversation_id: str,
        user_id: str
    ) -> SessionState:
        """初始化会话 (Step 0)
        
        Args:
            conversation_id: 会话ID
            user_id: 用户ID
            
        Returns:
            SessionState: 会话状态对象
        """
        from app.db.session_repo import session_repo
        
        session_id = str(uuid4())
        logger.info(f"[SessionInitializer] Step 0: 初始化会话 | session={session_id} | conv={conversation_id} | user={user_id}")
        
        # 0.1: 上下文窗口配置
        logger.info("[SessionInitializer] 0.1 上下文窗口配置")
        state = SessionState(
            session_id=UUID(session_id),
            user_id=UUID(user_id),
            conversation_id=UUID(conversation_id),
            context_window_size=self._config["context_window_size"],
            soft_trim_ratio=self._config["soft_trim_ratio"],
            hard_clear_ratio=self._config["hard_clear_ratio"],
            max_spawn_depth=self._config["max_spawn_depth"],
            max_concurrent=self._config["max_concurrent"],
            max_children=self._config["max_children"]
        )
        
        # 0.2: 核心文件注入（TODO: 后续实现）
        logger.info("[SessionInitializer] 0.2 核心文件注入 (待实现)")
        
        # 0.3: 创建隔离会话
        logger.info("[SessionInitializer] 0.3 创建隔离会话")
        self._active_sessions[session_id] = state
        
        # 0.4: 初始化核心组件已在 __init__ 中完成
        logger.info("[SessionInitializer] 0.4 核心组件已就绪")
        
        # 0.5: 尝试会话恢复
        logger.info("[SessionInitializer] 0.5 尝试会话恢复")
        recovered = await self._recovery.recover(conversation_id, user_id)
        if recovered:
            logger.info(f"[SessionInitializer] ✓ 会话已恢复: {conversation_id}")
            # 合并恢复的状态
            for key, value in recovered.items():
                if hasattr(state, key):
                    setattr(state, key, value)
        
        # 持久化会话状态
        await session_repo.save_state(
            state.session_id,
            state.user_id,
            state.conversation_id,
            state.model_dump()
        )
        
        logger.info(f"[SessionInitializer] ✓ Step 0 完成 | session={session_id}")
        return state
    
    def get_state(self, session_id: str) -> Optional[SessionState]:
        """获取会话状态
        
        Args:
            session_id: 会话ID
            
        Returns:
            会话状态或None
        """
        return self._active_sessions.get(session_id)
    
    @property
    def error_classifier(self) -> ErrorClassifier:
        return self._error_classifier
    
    @property
    def retry_manager(self) -> RetryManager:
        return self._retry_manager
    
    @property
    def fallback_handler(self) -> FallbackHandler:
        return self._fallback_handler
```

- [ ] **Step 3: 更新 core/__init__.py 导出**

```python
# 在 backend/app/core/__init__.py 末尾添加
from .session import (
    SessionInitializer,
    SessionState,
    ErrorCategory,
    RecoveryStrategy,
    ErrorClassifier,
    RetryManager,
    RetryPolicy,
    FallbackHandler,
    FallbackResponse,
)

__all__.update([
    "SessionInitializer",
    "SessionState",
    "ErrorCategory",
    "RecoveryStrategy",
    "ErrorClassifier",
    "RetryManager",
    "RetryPolicy",
    "FallbackHandler",
    "FallbackResponse",
])
```

- [ ] **Step 4: 编写测试**

```python
# backend/tests/core/session/test_initializer.py
import pytest
from app.core.session.initializer import SessionInitializer
from app.core.session.state import SessionState

@pytest.mark.asyncio
async def test_initialize_session():
    initializer = SessionInitializer()
    
    state = await initializer.initialize("test-conv", "test-user")
    
    assert isinstance(state, SessionState)
    assert state.user_id == "test-user"
    assert state.conversation_id == "test-conv"
    assert state.context_window_size == 128000

@pytest.mark.asyncio
async def test_get_state():
    initializer = SessionInitializer()
    
    state = await initializer.initialize("test-conv", "test-user")
    session_id = str(state.session_id)
    
    retrieved = initializer.get_state(session_id)
    
    assert retrieved is state  # 同一个对象
```

- [ ] **Step 5: 运行测试**

```bash
cd backend && pytest tests/core/session/test_initializer.py -v
```

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/session/initializer.py backend/app/core/session/recovery.py backend/app/core/__init__.py tests/core/session/test_initializer.py
git commit -m "feat(phase3): implement SessionInitializer (Step 0)"
```

---

## Task 6: 集成到 QueryEngine

**Dependencies:** Task 5 (SessionInitializer 及所有组件)

**Files:**
- Modify: `backend/app/core/query_engine.py` (添加会话生命周期组件和重试循环)
- Modify: `backend/app/api/chat.py` (WebSocket 连接时调用初始化)

- [ ] **Step 1: 在 QueryEngine.__init__ 中添加会话生命周期组件**

在 `QueryEngine.__init__` 方法中，在 `self._conversation_history` 初始化之后添加：

```python
# 在 QueryEngine.__init__ 末尾，初始化会话生命周期组件
from .session import SessionInitializer

# ... existing code ...

# 初始化会话生命周期管理
self._session_initializer = SessionInitializer(
    config_path=config_path,
    custom_rules=custom_rules
)
self._max_total_retries = 5

logger.info(
    f"[QueryEngine] 🚀 初始化完成 | "
    f"工具数量={len(self._tool_registry.list_tools())} | "
    f"LLM客户端={'已配置' if llm_client else '未配置'} | "
    f"会话生命周期={'已启用' if self._session_initializer else '未启用'}"
)
```

- [ ] **Step 2: 在 process 方法中包装重试循环**

在 `process` 方法开头包装重试逻辑：

```python
async def process(
    self,
    user_input: str,
    conversation_id: str,
    user_id: Optional[str] = None
) -> AsyncIterator[str]:
    """统一处理流程 - 带重试循环
    
    主循环（最多5次重试）：
    - 执行 6 步流程
    - 失败时分类异常
    - 根据策略决定重试或降级
    """
    total_start = time.perf_counter()
    self._current_message = user_input
    
    retry_manager = self._session_initializer.retry_manager
    
    # 主循环（最多5次重试）
    while retry_manager.get_retry_count(conversation_id) < self._max_total_retries:
        try:
            # ===== 原 6 步流程保持不变 =====
            # ... (保持现有的 STAGE_0_INIT 到 STAGE_8_MEMORY 的完整逻辑)
            # 当成功执行到完成时，break 并重置重试计数
            
            # 成功：重置重试计数并退出
            retry_manager.reset(conversation_id)
            
            # 记录工作流程总摘要（原逻辑末尾）
            log_workflow_summary(...)
            
            logger.info(f"[WORKFLOW] 🏁 ====== 工作流程完成 ======")
            return  # 成功退出
            
        except Exception as e:
            should_retry, count = retry_manager.should_retry(conversation_id, e)
            
            if not should_retry:
                # 不允许重试，返回降级响应
                logger.error(f"[WORKFLOW] ❌ 不可恢复错误: {e}")
                fallback = self._session_initializer.fallback_handler.get_fallback(e)
                yield fallback.message
                return
            
            # 允许重试，应用退避延迟
            logger.info(f"[WORKFLOW] 🔄 重试 ({count}/{self._max_total_retries}) | error={type(e).__name__}")
            await retry_manager.apply_backoff(count)
    
    # 超过最大重试次数
    last_error = retry_manager.get_last_error(conversation_id)
    if last_error:
        logger.error(f"[WORKFLOW] ❌ 超过最大重试次数: {last_error}")
        fallback = self._session_initializer.fallback_handler.get_fallback(last_error)
        yield fallback.message
    
    logger.info(f"[WORKFLOW] ⚠️ 交付降级响应")
```

- [ ] **Step 3: 在 WebSocket 连接建立时调用初始化**

在 `chat.py` 的 `websocket_chat_endpoint` 中，连接建立后立即初始化：

```python
async def websocket_chat_endpoint(websocket: WebSocket) -> None:
    """WebSocket endpoint for chat with streaming LLM responses."""
    conn_id = await manager.connect(websocket)
    engine = get_query_engine()
    
    try:
        # 连接建立后立即执行 Step 0 会话初始化
        conversation_id = None  # 首次消息时会创建
        user_id = None  # 首次消息时会设置
        
        try:
            # 使用临时 ID 进行初始化，首条消息时会更新
            await engine._session_initializer.initialize(
                conversation_id or "temp",
                user_id or "anonymous"
            )
            websocket._session_initialized = True
        except Exception as e:
            logger.warning(f"[Chat] 会话初始化失败: {e}")
            websocket._session_initialized = False
        
        while True:
            # ... 现有的消息处理逻辑保持不变 ...
```

- [ ] **Step 4: 提交**

```bash
git add backend/app/core/query_engine.py backend/app/api/chat.py
git commit -m "feat(phase3): integrate session lifecycle into QueryEngine with retry loop"
```

---

## Task 7: 更新模块导出和测试套件

**Dependencies:** Task 1-6 (所有前置任务)

**Files:**
- Modify: `backend/app/core/session/__init__.py`
- Create: `backend/tests/core/session/__init__.py`

- [ ] **Step 1: 更新 session/__init__.py 导出**

```python
# backend/app/core/session/__init__.py
from .initializer import SessionInitializer
from .state import SessionState, ErrorCategory, RecoveryStrategy
from .error_classifier import ErrorClassifier
from .retry_manager import RetryManager, RetryPolicy
from .fallback import FallbackHandler, FallbackResponse
from .recovery import SessionRecovery

__all__ = [
    "SessionInitializer",
    "SessionState",
    "ErrorCategory",
    "RecoveryStrategy",
    "ErrorClassifier",
    "RetryManager",
    "RetryPolicy",
    "FallbackHandler",
    "FallbackResponse",
    "SessionRecovery",
]
```

- [ ] **Step 2: 创建 tests/core/session/__init__.py**

```python
# backend/tests/core/session/__init__.py
```

- [ ] **Step 3: 运行完整测试套件**

```bash
cd backend && pytest tests/core/session/ -v
```

- [ ] **Step 4: 运行 QueryEngine 集成测试**

```bash
cd backend && pytest tests/core/integration/test_query_engine.py -v
```

- [ ] **Step 5: 启动服务器验证**

```bash
cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- [ ] **Step 6: 提交**

```bash
git add backend/app/core/session/__init__.py tests/core/session/__init__.py
git commit -m "feat(phase3): complete session lifecycle implementation"
```

---

## 实现检查清单

- [ ] session_states 表已创建
- [ ] ErrorClassifier 正确分类异常
- [ ] RetryManager 正确跟踪重试次数
- ] FallbackHandler 生成友好的降级响应
- ] SessionInitializer 在连接时执行
- [ ] QueryEngine.process 包装在重试循环中
- [ ] 所有测试通过
- [ ] 服务器可以正常启动

---

## 参考文档

- 设计文档: `docs/superpowers/specs/2026-04-04-session-lifecycle-design.md`
- 现有 QueryEngine: `backend/app/core/query_engine.py`
- 错误定义: `backend/app/core/errors.py`
- 数据库连接: `backend/app/db/postgres.py`

---

*Phase 3: 会话生命周期*
*实现计划版本: 2.0*
*日期: 2026-04-04*
