"""ContextConfig - 上下文配置类

提供上下文管理相关的配置定义，包括窗口大小、修剪比例、TTL 设置等。
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List


@dataclass(frozen=True)
class ContextConfig:
    """上下文窗口配置

    定义了上下文管理的各种阈值和配置参数，用于控制上下文修剪、压缩和规则注入行为。

    Attributes:
        window_size: 上下文窗口大小（token 数），默认 128000（DeepSeek）
        soft_trim_ratio: 软修剪比例，默认 0.3（30% 窗口触发）
        hard_clear_ratio: 硬清除比例，默认 0.5（50% 窗口触发）
        compress_threshold: 压缩阈值，默认 0.75（75% 窗口触发摘要压缩）
        tool_result_ttl_seconds: 工具结果 TTL（秒），默认 300（5 分钟）
        max_tool_result_chars: 单条工具结果最大字符数，默认 4000
        summary_model: 摘要压缩使用的模型，默认 "deepseek-chat"
        max_summary_retries: 摘要压缩最大重试次数，默认 3
        rules_files: 核心规则文件列表，默认 ["AGENTS.md", "TOOLS.md"]
        rules_cache: 规则文件内容缓存，启动时加载
        protected_message_types: 受保护的消息类型，这些消息不会被修剪
        rules_reinject_window: 规则重注入窗口，检查最近 N 条消息是否有规则，默认 5
        rules_reinject_interval: 规则重注入间隔，至少间隔 N 条消息后重新注入，默认 3
    """

    # 窗口配置
    window_size: int = 128000
    soft_trim_ratio: float = 0.3
    hard_clear_ratio: float = 0.5
    compress_threshold: float = 0.75

    # TTL 配置
    tool_result_ttl_seconds: int = 300
    max_tool_result_chars: int = 4000

    # 摘要配置
    summary_model: str = "deepseek-chat"
    max_summary_retries: int = 3

    # 核心规则文件
    rules_files: List[str] = field(default_factory=lambda: ["AGENTS.md", "TOOLS.md"])
    rules_cache: Dict[str, str] = field(default_factory=dict)

    # 保护配置
    protected_message_types: List[str] = field(default_factory=lambda: ["user", "system", "image"])

    # 规则重注入配置
    rules_reinject_window: int = 5   # 检查最近 N 条消息是否有规则
    rules_reinject_interval: int = 3  # 至少间隔 N 条消息后重新注入

    @classmethod
    def load_rules_at_startup(cls, rules_dir: Path) -> Dict[str, str]:
        """启动时加载核心规则文件到缓存

        Args:
            rules_dir: 规则文件所在目录

        Returns:
            规则文件名到内容的映射字典
        """
        cache = {}
        rules_dir = Path(rules_dir)

        if not rules_dir.is_dir():
            return cache

        for filename in ["AGENTS.md", "TOOLS.md"]:
            file_path = rules_dir / filename
            if file_path.is_file():
                try:
                    content = file_path.read_text(encoding="utf-8")
                    cache[filename] = content
                except (OSError, UnicodeDecodeError):
                    # 跳过无法读取的文件
                    continue

        return cache

    def get_injected_rules(self) -> str:
        """获取需要注入的核心规则

        将缓存中的规则文件内容格式化为可注入的字符串。

        Returns:
            格式化的规则字符串，如果缓存为空则返回空字符串
        """
        if not self.rules_cache:
            return ""

        parts = []
        for filename in self.rules_files:
            if filename in self.rules_cache:
                content = self.rules_cache[filename]
                parts.append(f"### {filename}\n{content}")

        return "\n\n".join(parts)


def load_config_from_env() -> ContextConfig:
    """从环境变量加载配置

    支持的环境变量：
    - CONTEXT_WINDOW_SIZE: 上下文窗口大小
    - COMPRESS_THRESHOLD: 压缩阈值
    - TOOL_RESULT_TTL: 工具结果 TTL（秒）

    Returns:
        配置实例，环境变量未设置时使用默认值
    """
    window_size = _get_int_env("CONTEXT_WINDOW_SIZE", 128000)
    compress_threshold = _get_float_env("COMPRESS_THRESHOLD", 0.75)
    ttl = _get_int_env("TOOL_RESULT_TTL", 300)

    return ContextConfig(
        window_size=window_size,
        compress_threshold=compress_threshold,
        tool_result_ttl_seconds=ttl,
    )


def get_default_config() -> ContextConfig:
    """获取默认配置

    Returns:
        使用所有默认值的配置实例
    """
    return ContextConfig()


def _get_int_env(key: str, default: int) -> int:
    """从环境变量获取整数值

    Args:
        key: 环境变量名
        default: 默认值

    Returns:
        环境变量的整数值，解析失败时返回默认值
    """
    value = os.getenv(key)
    if value is None:
        return default

    try:
        return int(value)
    except ValueError:
        return default


def _get_float_env(key: str, default: float) -> float:
    """从环境变量获取浮点数值

    Args:
        key: 环境变量名
        default: 默认值

    Returns:
        环境变量的浮点数值，解析失败时返回默认值
    """
    value = os.getenv(key)
    if value is None:
        return default

    try:
        return float(value)
    except ValueError:
        return default


__all__ = [
    "ContextConfig",
    "load_config_from_env",
    "get_default_config",
]
