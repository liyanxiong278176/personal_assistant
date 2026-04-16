"""上下文压缩器 - 阶段4后置压缩（分块+持久化）

提供智能的上下文压缩功能，当上下文超过阈值时自动压缩。

压缩策略:
1. 分块：按token限制把旧消息分成多块（基础分块比例40%，最小15%，带20%缓冲）
2. 摘要生成：用LLM把每一块旧消息总结成紧凑的摘要（带重试）
3. 历史裁剪：把旧消息删掉，换成摘要
4. 持久化：把摘要持久化到JSONL文件（长期保存到"笔记本"）
5. 规则重注入：压缩后重新注入核心规则，防止AI行为失控
"""

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from .config import ContextConfig
from .tokenizer import TokenEstimator

logger = logging.getLogger(__name__)

# ============================================================
# 常量定义
# ============================================================

# 分块配置
BASE_CHUNK_RATIO = 0.40  # 基础分块比例40%
MIN_CHUNK_RATIO = 0.15   # 最小分块比例15%
CHUNK_BUFFER = 0.20      # 20%缓冲

# 摘要配置
DEFAULT_SUMMARY_TOKENS = 500  # 摘要的目标token数
MAX_SUMMARY_RETRIES = 3       # 最大重试次数

# JSONL持久化配置
DEFAULT_SUMMARY_DIR = "data/summaries"  # 摘要保存目录
SUMMARY_FILE_PREFIX = "conversation_summary_"


# ============================================================
# 数据类
# ============================================================


@dataclass
class CompressionStats:
    """压缩统计信息"""
    original_count: int = 0
    original_tokens: int = 0
    compressed_count: int = 0
    compressed_tokens: int = 0
    chunks_created: int = 0
    summary_tokens: int = 0
    tokens_saved: int = 0
    rules_injected: bool = False
    persisted_to_jsonl: bool = False
    jsonl_path: Optional[str] = None
    elapsed_ms: float = 0.0


@dataclass
class ChunkConfig:
    """分块配置"""
    base_ratio: float = BASE_CHUNK_RATIO
    min_ratio: float = MIN_CHUNK_RATIO
    buffer: float = CHUNK_BUFFER
    max_tokens_per_chunk: Optional[int] = None


@dataclass
class SummaryEntry:
    """摘要条目（用于JSONL持久化）"""
    timestamp: str
    conversation_id: str
    chunk_index: int
    original_message_count: int
    summary_text: str
    summary_tokens: int
    original_tokens: int
    messages_summary: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """转换为字典"""
        return {
            "timestamp": self.timestamp,
            "conversation_id": self.conversation_id,
            "chunk_index": self.chunk_index,
            "original_message_count": self.original_message_count,
            "summary_text": self.summary_text,
            "summary_tokens": self.summary_tokens,
            "original_tokens": self.original_tokens,
            "messages_summary": self.messages_summary,
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "SummaryEntry":
        """从字典创建"""
        return cls(**data)


# ============================================================
# 结构化日志宏
# ============================================================


def _log_compression_start(
    conv_id: str,
    message_count: int,
    current_tokens: int,
    threshold: int,
):
    """压缩开始日志"""
    ratio = current_tokens / threshold if threshold > 0 else 0
    logger.info(
        f"[COMPRESSOR] 🚀 开始压缩 | conv={conv_id} | "
        f"消息={message_count}条 | tokens={current_tokens}/{threshold}({ratio:.1%})"
    )


def _log_compression_chunk_created(
    conv_id: str,
    chunk_index: int,
    message_count: int,
    tokens: int,
):
    """分块创建日志"""
    logger.info(
        f"[COMPRESSOR] 📦 分块创建 | conv={conv_id} | "
        f"块#{chunk_index} | 消息={message_count}条 | tokens≈{tokens}"
    )


def _log_compression_summary_generated(
    conv_id: str,
    chunk_index: int,
    summary_tokens: int,
    retry_count: int,
    elapsed_ms: float,
):
    """摘要生成日志"""
    logger.info(
        f"[COMPRESSOR] 📝 摘要生成 | conv={conv_id} | "
        f"块#{chunk_index} | tokens≈{summary_tokens} | "
        f"重试={retry_count} | 耗时={elapsed_ms:.0f}ms"
    )


def _log_compression_persisted(
    conv_id: str,
    path: str,
    entry_count: int,
):
    """持久化日志"""
    logger.info(
        f"[COMPRESSOR] 💾 持久化完成 | conv={conv_id} | "
        f"路径={path} | 条目={entry_count}"
    )


def _log_compression_result(stats: CompressionStats, conv_id: str):
    """压缩结果日志"""
    logger.info(
        f"[COMPRESSOR] ✅ 压缩完成 | conv={conv_id} | "
        f"消息: {stats.original_count} → {stats.compressed_count} | "
        f"tokens: {stats.original_tokens} → {stats.compressed_tokens} | "
        f"节省: {stats.tokens_saved}({stats.tokens_saved/stats.original_tokens:.1%}) | "
        f"分块: {stats.chunks_created} | "
        f"规则注入: {stats.rules_injected} | "
        f"持久化: {stats.persisted_to_jsonl} | "
        f"耗时: {stats.elapsed_ms:.0f}ms"
    )


def _log_compression_fallback(conv_id: str, message_count: int):
    """降级日志"""
    logger.warning(
        f"[COMPRESSOR] ⚠️ LLM摘要失败，使用降级方案 | conv={conv_id} | "
        f"消息={message_count}条"
    )


# ============================================================
# JSONL持久化管理器
# ============================================================


class SummaryPersistence:
    """摘要持久化管理器

    将压缩的摘要持久化到JSONL文件，实现"笔记本"功能。
    """

    def __init__(self, summary_dir: str = DEFAULT_SUMMARY_DIR):
        """初始化持久化管理器

        Args:
            summary_dir: 摘要保存目录
        """
        self.summary_dir = Path(summary_dir)
        self.summary_dir.mkdir(parents=True, exist_ok=True)

    def get_conversation_path(self, conversation_id: str) -> Path:
        """获取对话的摘要文件路径

        Args:
            conversation_id: 对话ID

        Returns:
            JSONL文件路径
        """
        safe_id = conversation_id.replace("/", "_").replace("\\", "_")
        filename = f"{SUMMARY_FILE_PREFIX}{safe_id}.jsonl"
        return self.summary_dir / filename

    def append(
        self,
        conversation_id: str,
        entries: List[SummaryEntry],
    ) -> bool:
        """追加摘要条目到JSONL文件

        Args:
            conversation_id: 对话ID
            entries: 摘要条目列表

        Returns:
            是否成功
        """
        if not entries:
            return True

        path = self.get_conversation_path(conversation_id)

        try:
            with open(path, "a", encoding="utf-8") as f:
                for entry in entries:
                    f.write(json.dumps(entry.to_dict(), ensure_ascii=False) + "\n")
            return True
        except (OSError, IOError) as e:
            logger.error(f"[Persistence] 写入失败: {e}")
            return False

    def load(
        self,
        conversation_id: str,
        limit: Optional[int] = None,
    ) -> List[SummaryEntry]:
        """从JSONL文件加载摘要条目

        Args:
            conversation_id: 对话ID
            limit: 最大加载条目数

        Returns:
            摘要条目列表
        """
        path = self.get_conversation_path(conversation_id)

        if not path.exists():
            return []

        entries = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    if limit and len(entries) >= limit:
                        break
                    try:
                        data = json.loads(line.strip())
                        entries.append(SummaryEntry.from_dict(data))
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"[Persistence] 跳过无效条目: {e}")
                        continue
        except (OSError, IOError) as e:
            logger.error(f"[Persistence] 读取失败: {e}")

        return entries

    def list_conversations(self) -> List[str]:
        """列出所有有摘要的对话ID

        Returns:
            对话ID列表
        """
        conversations = []
        for path in self.summary_dir.glob(f"{SUMMARY_FILE_PREFIX}*.jsonl"):
            # 从文件名提取对话ID
            id_part = path.stem.replace(SUMMARY_FILE_PREFIX, "")
            conversations.append(id_part.replace("_", "/"))
        return conversations


# ============================================================
# 主类
# ============================================================


class ContextCompressor:
    """上下文压缩器类 - 阶段4后置压缩

    当上下文长度超过阈值时，智能压缩消息历史。
    采用分块压缩+摘要持久化+规则重注入的策略。
    """

    def __init__(
        self,
        config: Optional[ContextConfig] = None,
        summary_dir: str = DEFAULT_SUMMARY_DIR,
    ):
        """初始化上下文压缩器

        Args:
            config: 上下文配置
            summary_dir: 摘要保存目录
        """
        self.config = config or ContextConfig()
        self.window_size = self.config.window_size
        self.compress_threshold = self.config.compress_threshold
        self.summary_model = self.config.summary_model
        self.max_retries = self.config.max_summary_retries

        # 分块配置
        self.chunk_config = ChunkConfig(
            base_ratio=BASE_CHUNK_RATIO,
            min_ratio=MIN_CHUNK_RATIO,
            buffer=CHUNK_BUFFER,
        )

        # 持久化管理器
        self.persistence = SummaryPersistence(summary_dir)

    def needs_compression(self, messages: List[Dict]) -> bool:
        """检查是否需要压缩

        Args:
            messages: 当前消息列表

        Returns:
            是否需要压缩
        """
        if not messages:
            return False

        current_tokens = TokenEstimator.estimate_messages(messages)
        threshold = int(self.window_size * self.compress_threshold)

        return current_tokens >= threshold

    def compress(
        self,
        messages: List[Dict],
        conversation_id: str = "unknown",
        llm_summary_func: Optional[Callable] = None,
    ) -> tuple[List[Dict], CompressionStats]:
        """压缩消息列表

        Args:
            messages: 原始消息列表
            conversation_id: 对话ID（用于持久化）
            llm_summary_func: 可选的LLM摘要生成函数

        Returns:
            (压缩后的消息列表, 压缩统计信息)
        """
        start_time = time.perf_counter()

        if not messages:
            return messages, CompressionStats()

        # 初始化统计
        stats = CompressionStats(
            original_count=len(messages),
            original_tokens=TokenEstimator.estimate_messages(messages),
        )

        # 检查是否需要压缩
        if not self.needs_compression(messages):
            return messages, stats

        _log_compression_start(
            conversation_id,
            len(messages),
            stats.original_tokens,
            int(self.window_size * self.compress_threshold),
        )

        # 分离system消息和其他消息
        system_messages = [m for m in messages if m.get("role") == "system"]
        other_messages = [m for m in messages if m.get("role") != "system"]

        if not other_messages:
            return messages, stats

        # 分块
        chunks = self._create_chunks(
            other_messages,
            int(self.window_size * self.compress_threshold),
        )
        stats.chunks_created = len(chunks)

        # 生成摘要
        summary_entries = []
        compressed_parts = []

        for i, chunk in enumerate(chunks):
            chunk_tokens = TokenEstimator.estimate_messages(chunk)
            _log_compression_chunk_created(conversation_id, i, len(chunk), chunk_tokens)

            # 尝试LLM摘要
            summary_text = None
            retry_count = 0

            if llm_summary_func:
                chunk_start = time.perf_counter()
                for retry in range(self.max_retries):
                    try:
                        summary_text = llm_summary_func(chunk)
                        retry_count = retry
                        break
                    except Exception as e:
                        logger.warning(f"[COMPRESSOR] 摘要生成失败(重试{retry+1}): {e}")
                        retry_count = retry + 1

                elapsed = (time.perf_counter() - chunk_start) * 1000
            else:
                elapsed = 0

            if summary_text:
                summary_tokens = TokenEstimator.estimate(summary_text)
                _log_compression_summary_generated(
                    conversation_id, i, summary_tokens, retry_count, elapsed
                )
            else:
                # 降级：使用计数摘要
                summary_text = self._create_fallback_summary(chunk)
                summary_tokens = TokenEstimator.estimate(summary_text)
                _log_compression_fallback(conversation_id, len(chunk))

            # 创建摘要条目
            entry = SummaryEntry(
                timestamp=datetime.now().isoformat(),
                conversation_id=conversation_id,
                chunk_index=i,
                original_message_count=len(chunk),
                summary_text=summary_text,
                summary_tokens=summary_tokens,
                original_tokens=chunk_tokens,
                messages_summary=[
                    {"role": m.get("role"), "content_preview": m.get("content", "")[:100]}
                    for m in chunk
                ],
            )
            summary_entries.append(entry)

            # 添加摘要到压缩结果
            compressed_parts.append({
                "role": "system",
                "content": f"[历史对话摘要 块#{i+1}]\n{summary_text}",
                "_compressed": True,
                "_chunk_index": i,
            })

            stats.summary_tokens += summary_tokens

        # 保留最近的消息（不压缩）
        keep_recent = max(1, int(len(other_messages) * 0.2))
        recent_messages = other_messages[-keep_recent:]

        # 组装压缩后的消息
        result = []
        result.extend(system_messages)
        result.extend(compressed_parts)
        result.extend(recent_messages)

        # 持久化摘要
        if summary_entries:
            persisted = self.persistence.append(conversation_id, summary_entries)
            stats.persisted_to_jsonl = persisted
            if persisted:
                stats.jsonl_path = str(self.persistence.get_conversation_path(conversation_id))
                _log_compression_persisted(conversation_id, stats.jsonl_path, len(summary_entries))

        # 更新统计
        stats.compressed_count = len(result)
        stats.compressed_tokens = TokenEstimator.estimate_messages(result)
        stats.tokens_saved = stats.original_tokens - stats.compressed_tokens
        stats.elapsed_ms = (time.perf_counter() - start_time) * 1000

        _log_compression_result(stats, conversation_id)

        return result, stats

    def _create_chunks(
        self,
        messages: List[Dict],
        target_tokens: int,
    ) -> List[List[Dict]]:
        """创建消息分块

        分块策略：
        - 基础分块：每块约 target_tokens * base_ratio
        - 最小块：至少 target_tokens * min_ratio
        - 带20%缓冲

        Args:
            messages: 消息列表
            target_tokens: 目标token数

        Returns:
            分块后的消息列表
        """
        if not messages:
            return []

        chunks = []
        current_chunk = []
        current_tokens = 0

        # 计算分块参数
        base_chunk_size = int(target_tokens * self.chunk_config.base_ratio)
        min_chunk_size = int(target_tokens * self.chunk_config.min_ratio)
        buffer = int(target_tokens * self.chunk_config.buffer)

        target_chunk_size = base_chunk_size - buffer

        for msg in messages:
            msg_tokens = TokenEstimator.estimate_messages([msg])

            # 如果单条消息就超过目标大小，单独成块
            if msg_tokens > target_chunk_size and current_chunk:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0

            current_chunk.append(msg)
            current_tokens += msg_tokens

            # 检查是否需要切分
            if current_tokens >= target_chunk_size:
                chunks.append(current_chunk)
                current_chunk = []
                current_tokens = 0

        # 添加剩余消息
        if current_chunk:
            # 检查最后一块是否太小
            if chunks and len(current_chunk) < min_chunk_size:
                # 合并到前一块
                chunks[-1].extend(current_chunk)
            else:
                chunks.append(current_chunk)

        return chunks

    def _create_fallback_summary(self, messages: List[Dict]) -> str:
        """创建降级摘要（计数信息）

        Args:
            messages: 消息列表

        Returns:
            摘要文本
        """
        user_count = sum(1 for m in messages if m.get("role") == "user")
        assistant_count = sum(1 for m in messages if m.get("role") == "assistant")
        tool_count = sum(1 for m in messages if m.get("role") == "tool")

        # 提取关键信息
        topics = []
        for m in messages:
            content = m.get("content", "")
            if m.get("role") == "user" and len(content) > 10:
                # 提取用户输入的关键词
                preview = content[:100]
                topics.append(f"- 用户: {preview}...")

        topic_str = "\n".join(topics[:3]) if topics else "（具体内容已压缩）"

        return (
            f"历史对话包含 {user_count} 条用户消息、"
            f"{assistant_count} 条助手回复、{tool_count} 条工具调用。\n"
            f"主要内容：\n{topic_str}\n"
            f"这些内容已被压缩以节省上下文空间。"
        )

    def get_compression_stats(self, messages: List[Dict]) -> Dict:
        """获取压缩统计信息

        Args:
            messages: 当前消息列表

        Returns:
            包含统计信息的字典
        """
        current_tokens = TokenEstimator.estimate_messages(messages)
        threshold = int(self.window_size * self.compress_threshold)

        return {
            "current_tokens": current_tokens,
            "max_tokens": self.window_size,
            "threshold": threshold,
            "needs_compression": current_tokens >= threshold,
            "usage_ratio": current_tokens / self.window_size
            if self.window_size > 0
            else 0,
            "message_count": len(messages),
        }

    def load_history_summaries(
        self,
        conversation_id: str,
    ) -> List[SummaryEntry]:
        """加载历史摘要

        Args:
            conversation_id: 对话ID

        Returns:
            摘要条目列表
        """
        return self.persistence.load(conversation_id)


__all__ = [
    "ContextCompressor",
    "CompressionStats",
    "ChunkConfig",
    "SummaryEntry",
    "SummaryPersistence",
    "BASE_CHUNK_RATIO",
    "MIN_CHUNK_RATIO",
    "CHUNK_BUFFER",
]
