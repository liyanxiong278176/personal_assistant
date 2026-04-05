"""Session initializer (Step 0) for Phase 3: 会话生命周期."""

import logging
from pathlib import Path
from typing import Dict, Any, Optional
from uuid import UUID, uuid4

from .state import SessionState
from .error_classifier import ErrorClassifier
from .retry_manager import RetryManager, RetryPolicy
from .fallback import FallbackHandler
from .recovery import SessionRecovery
from .structured_logger import SessionPhase, PhaseLogger, log_event, LogLevel

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
            "max_children": 5,
        }

        if self._config_path and self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                user_config = json.load(f)
                default_config.update(user_config)
                logger.info(
                    f"[SessionInitializer] 已加载配置: {self._config_path}"
                )

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

        # 安全的UUID转换：如果无效则生成新的UUID
        def safe_uuid(value: str, prefix: str = "temp") -> UUID:
            """安全转换字符串为UUID，无效时生成新UUID"""
            try:
                return UUID(value)
            except (ValueError, AttributeError):
                # 生成基于字符串的确定性UUID（使用namespace）
                import hashlib
                hash_bytes = hashlib.md5(f"{prefix}:{value}".encode()).digest()
                return UUID(bytes=hash_bytes[:16])

        # 转换ID为UUID格式
        conv_uuid = safe_uuid(conversation_id, "conv")
        user_uuid = safe_uuid(user_id, "user")
        session_id = str(uuid4())

        # 使用结构化日志记录初始化阶段
        phase_logger = PhaseLogger(
            SessionPhase.INIT,
            conversation_id=conversation_id,
            user_id=user_id
        )

        phase_logger.start(
            context_window_size=self._config["context_window_size"],
            soft_trim_ratio=self._config["soft_trim_ratio"]
        )

        logger.info(
            f"[SessionInitializer] Step 0: 初始化会话 | session={session_id} "
            f"| conv={conversation_id} | user={user_id}"
        )

        # 0.1: 上下文窗口配置
        logger.info("[SessionInitializer] 0.1 上下文窗口配置")
        state = SessionState(
            session_id=UUID(session_id),
            user_id=user_uuid,
            conversation_id=conv_uuid,
            context_window_size=self._config["context_window_size"],
            soft_trim_ratio=self._config["soft_trim_ratio"],
            hard_clear_ratio=self._config["hard_clear_ratio"],
            max_spawn_depth=self._config["max_spawn_depth"],
            max_concurrent=self._config["max_concurrent"],
            max_children=self._config["max_children"],
        )

        # 0.2: 核心文件注入（TODO: 后续实现）
        logger.info("[SessionInitializer] 0.2 核心文件注入 (待实现)")

        # 0.3: 创建隔离会话
        logger.info("[SessionInitializer] 0.3 创建隔离会话")
        self._active_sessions[session_id] = state

        # 0.4: 初始化核心组件已在 __init__ 中完成
        logger.info("[SessionInitializer] 0.4 核心组件已就绪")

        # 0.5: 尝试会话恢复（使用安全版本，避免 DB 连接冲突）
        logger.info("[SessionInitializer] 0.5 尝试会话恢复")
        recovered = await self._recovery.recover_safe(conversation_id, user_id)
        if recovered:
            logger.info(
                f"[SessionInitializer] ✓ 会话已恢复: {conversation_id}"
            )
            # 合并恢复的状态
            for key, value in recovered.items():
                if hasattr(state, key):
                    setattr(state, key, value)

        # 持久化会话状态（安全模式，不因DB错误而失败）
        try:
            await session_repo.save_state(
                state.session_id,
                state.user_id,
                state.conversation_id,
                state.model_dump(),
            )
            logger.debug(f"[SessionInitializer] 会话状态已持久化")
        except Exception as db_error:
            # 数据库错误不应阻止会话初始化
            logger.warning(
                f"[SessionInitializer] 会话状态持久化失败（非致命）: {db_error}"
            )
            # 记录结构化日志
            log_event(
                LogLevel.WARNING,
                SessionPhase.INIT,
                "会话状态持久化失败（非致命）",
                error_type=type(db_error).__name__,
                error_message=str(db_error)
            )

        logger.info(
            f"[SessionInitializer] ✓ Step 0 完成 | session={session_id}"
        )

        phase_logger.end(
            session_id=session_id,
            state_configured=True,
            state_persisted=True,
            recovered=bool(recovered)
        )

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
