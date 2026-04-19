"""结构化中文日志记录器 - 记忆管理系统专用

为记忆的"生老病死"全生命周期提供结构化、可读性强的中文日志。

日志阶段：
1. 📝 工作记忆：消息进入、队列状态、token使用
2. 💾 情节记忆：存储成功、Redis同步、会话恢复
3. 🔍 记忆检索：关键词提取、混合评分、场景感知
4. 📈 记忆晋升：规则评估、LLM评估、分数融合
5. 💎 语义记忆：写入成功、向量生成、冲突处理
6. 🔄 记忆更新：强化、衰减、合并、覆盖、清除
"""

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import UUID

logger = logging.getLogger(__name__)


class ChineseStructuredLogger:
    """结构化中文日志记录器。

    为记忆管理系统提供人类可读的中文日志，同时输出机器可解析的JSON。

    示例输出：
        [💾 情节记忆] ✅ 存储成功 | 用户=user_123 | 会话=conv_456 | 类型=偏好 | 内容="喜欢自然风光"
    """

    def __init__(self, component_name: str = "记忆管理"):
        """初始化日志记录器。

        Args:
            component_name: 组件名称，用于日志前缀
        """
        self.component = component_name

    # ========================================================================
    # 阶段1: 📝 工作记忆 (Working Memory)
    # ========================================================================

    def log_working_memory_entry(
        self,
        role: str,
        content: str,
        tokens: int,
        queue_size: int,
        total_tokens: int,
        max_tokens: int,
    ):
        """记录工作记忆进入。

        Args:
            role: 角色（user/assistant/system）
            content: 消息内容
            tokens: Token数量
            queue_size: 当前队列大小
            total_tokens: 总Token数
            max_tokens: 最大Token限制
        """
        status_emoji = "✅" if total_tokens <= max_tokens else "⚠️"

        log_data = {
            "阶段": "📝 工作记忆",
            "操作": "消息进入",
            "状态": status_emoji,
            "角色": role,
            "内容预览": content[:50] + "..." if len(content) > 50 else content,
            "Token数": tokens,
            "队列大小": f"{queue_size}条",
            "总Token": f"{total_tokens}/{max_tokens}",
            "时间戳": datetime.now().isoformat(),
        }

        message = (
            f"[📝 工作记忆] {status_emoji} 消息进入 | "
            f"角色={role} | "
            f"Token={tokens} | "
            f"队列={queue_size}条 | "
            f"总Token={total_tokens}/{max_tokens}"
        )

        logger.info(message)
        self._write_json(log_data)

    def log_working_memory_trim(
        self,
        removed_count: int,
        removed_tokens: int,
        remaining_count: int,
        remaining_tokens: int,
    ):
        """记录工作记忆裁剪。

        Args:
            removed_count: 移除的消息数
            removed_tokens: 移除的Token数
            remaining_count: 剩余消息数
            remaining_tokens: 剩余Token数
        """
        log_data = {
            "阶段": "📝 工作记忆",
            "操作": "队列裁剪",
            "状态": "✂️",
            "移除消息": removed_count,
            "移除Token": removed_tokens,
            "剩余消息": remaining_count,
            "剩余Token": remaining_tokens,
            "时间戳": datetime.now().isoformat(),
        }

        message = (
            f"[📝 工作记忆] ✂️ 队列裁剪 | "
            f"移除={removed_count}条({removed_tokens}tokens) | "
            f"剩余={remaining_count}条({remaining_tokens}tokens)"
        )

        logger.info(message)
        self._write_json(log_data)

    # ========================================================================
    # 阶段2: 💾 情节记忆 (Episodic Memory)
    # ========================================================================

    def log_episodic_storage(
        self,
        user_id: str,
        conversation_id: UUID,
        memory_type: str,
        content: str,
        redis_success: bool,
        redis_mode: str = "unknown",
    ):
        """记录情节记忆存储。

        Args:
            user_id: 用户ID
            conversation_id: 会话ID
            memory_type: 记忆类型
            content: 记忆内容
            redis_success: Redis是否成功
            redis_mode: Redis模式（redis/memory）
        """
        status_emoji = "✅" if redis_success else "⚠️"

        log_data = {
            "阶段": "💾 情节记忆",
            "操作": "存储",
            "状态": status_emoji,
            "用户ID": user_id,
            "会话ID": str(conversation_id),
            "类型": memory_type,
            "内容预览": content[:50] + "..." if len(content) > 50 else content,
            "Redis状态": "成功" if redis_success else "降级",
            "Redis模式": redis_mode,
            "时间戳": datetime.now().isoformat(),
        }

        message = (
            f"[💾 情节记忆] {status_emoji} 存储成功 | "
            f"用户={user_id} | "
            f"会话={str(conversation_id)[:8]}... | "
            f"类型={memory_type} | "
            f"Redis={'✓' if redis_success else '⚠️降级'}"
        )

        logger.info(message)
        self._write_json(log_data)

    # ========================================================================
    # 阶段3: 🔍 记忆检索 (Memory Retrieval)
    # ========================================================================

    def log_memory_retrieval_start(
        self,
        query: str,
        keywords: list[str],
        scenario: str,
        threshold: float,
    ):
        """记录记忆检索开始。

        Args:
            query: 查询内容
            keywords: 提取的关键词
            scenario: 检索场景（strict/normal/fuzzy）
            threshold: 阈值
        """
        scenario_names = {
            "strict": "严格场景（价格/地址）",
            "normal": "普通场景（日常对话）",
            "fuzzy": "模糊场景（推荐/闲聊）",
        }

        log_data = {
            "阶段": "🔍 记忆检索",
            "操作": "开始检索",
            "状态": "🔍",
            "查询内容": query[:50] + "..." if len(query) > 50 else query,
            "关键词": keywords,
            "场景": scenario_names.get(scenario, scenario),
            "阈值": threshold,
            "时间戳": datetime.now().isoformat(),
        }

        message = (
            f"[🔍 记忆检索] 🔍 开始检索 | "
            f"关键词={keywords} | "
            f"场景={scenario_names.get(scenario, scenario)} | "
            f"阈值={threshold}"
        )

        logger.info(message)
        self._write_json(log_data)

    def log_memory_retrieval_result(
        self,
        total_retrieved: int,
        passed_threshold: int,
        top_score: float,
        elapsed_ms: float,
    ):
        """记录记忆检索结果。

        Args:
            total_retrieved: 总检索数
            passed_threshold: 通过阈值数量
            top_score: 最高分数
            elapsed_ms: 耗时（毫秒）
        """
        log_data = {
            "阶段": "🔍 记忆检索",
            "操作": "检索完成",
            "状态": "✅",
            "总检索数": total_retrieved,
            "通过阈值": passed_threshold,
            "最高分": f"{top_score:.3f}",
            "耗时": f"{elapsed_ms:.2f}ms",
            "时间戳": datetime.now().isoformat(),
        }

        message = (
            f"[🔍 记忆检索] ✅ 检索完成 | "
            f"召回={total_retrieved}条 | "
            f"过滤后={passed_threshold}条 | "
            f"最高分={top_score:.3f} | "
            f"耗时={elapsed_ms:.2f}ms"
        )

        logger.info(message)
        self._write_json(log_data)

    # ========================================================================
    # 阶段5: 💎 语义记忆 (Semantic Memory)
    # ========================================================================

    def log_semantic_storage(
        self,
        memory_id: str,
        memory_type: str,
        content: str,
        vector_dim: int,
        conflict_detected: bool,
        conflict_resolved: bool,
        elapsed_ms: float,
    ):
        """记录语义记忆存储。

        Args:
            memory_id: 记忆ID
            memory_type: 记忆类型
            content: 记忆内容
            vector_dim: 向量维度
            conflict_detected: 是否检测到冲突
            conflict_resolved: 冲突是否已解决
            elapsed_ms: 耗时（毫秒）
        """
        conflict_emoji = "⚠️" if conflict_detected else ""
        resolved_emoji = "✓" if conflict_resolved else "✗" if conflict_detected else ""

        log_data = {
            "阶段": "💎 语义记忆",
            "操作": "存储",
            "状态": f"✅{conflict_emoji}{resolved_emoji}",
            "记忆ID": memory_id,
            "类型": memory_type,
            "内容预览": content[:50] + "..." if len(content) > 50 else content,
            "向量维度": vector_dim,
            "冲突检测": conflict_detected,
            "冲突解决": conflict_resolved,
            "耗时": f"{elapsed_ms:.2f}ms",
            "时间戳": datetime.now().isoformat(),
        }

        message = (
            f"[💎 语义记忆] ✅{conflict_emoji}{resolved_emoji} 存储成功 | "
            f"ID={memory_id[:16]}... | "
            f"类型={memory_type} | "
            f"向量={vector_dim}维 | "
            f"耗时={elapsed_ms:.2f}ms"
        )

        logger.info(message)
        self._write_json(log_data)

    # ========================================================================
    # 阶段6: 🔄 记忆更新 (Memory Lifecycle)
    # ========================================================================

    def log_memory_reinforce(
        self,
        memory_id: str,
        old_strength: float,
        new_strength: float,
        access_count: int,
    ):
        """记录记忆强化。

        Args:
            memory_id: 记忆ID
            old_strength: 原强度
            new_strength: 新强度
            access_count: 访问次数
        """
        log_data = {
            "阶段": "🔄 记忆生命周期",
            "操作": "强化",
            "状态": "💪",
            "记忆ID": memory_id[:16] + "...",
            "原强度": f"{old_strength:.3f}",
            "新强度": f"{new_strength:.3f}",
            "访问次数": access_count,
            "时间戳": datetime.now().isoformat(),
        }

        message = (
            f"[🔄 记忆生命周期] 💪 强化 | "
            f"ID={memory_id[:16]}... | "
            f"强度={old_strength:.3f}→{new_strength:.3f} | "
            f"访问第{access_count}次"
        )

        logger.debug(message)
        self._write_json(log_data)

    def log_memory_merge(
        self,
        old_memory_id: str,
        new_memory_id: str,
        old_content: str,
        new_content: str,
        merged_content: str,
    ):
        """记录记忆合并。

        Args:
            old_memory_id: 旧记忆ID
            new_memory_id: 新记忆ID
            old_content: 旧内容
            new_content: 新内容
            merged_content: 合并后内容
        """
        log_data = {
            "阶段": "🔄 记忆生命周期",
            "操作": "合并",
            "状态": "🔗",
            "旧记忆ID": old_memory_id[:16] + "...",
            "新记忆ID": new_memory_id[:16] + "...",
            "旧内容": old_content,
            "新内容": new_content,
            "合并内容": merged_content,
            "时间戳": datetime.now().isoformat(),
        }

        message = (
            f"[🔄 记忆生命周期] 🔗 合并 | "
            f"旧=\"{old_content[:30]}...\" | "
            f"新=\"{new_content[:30]}...\" | "
            f"合并=\"{merged_content[:30]}...\""
        )

        logger.info(message)
        self._write_json(log_data)

    def log_memory_cleanup(
        self,
        reason: str,
        removed_count: int,
        remaining_count: int,
    ):
        """记录记忆清除。

        Args:
            reason: 清除原因（strength_low/ttl_expired/duplicate）
            removed_count: 移除数量
            remaining_count: 剩余数量
        """
        reason_names = {
            "strength_low": "强度过低(<0.3)",
            "ttl_expired": "TTL过期",
            "duplicate": "重复记忆",
            "conflict_override": "冲突覆盖",
        }

        log_data = {
            "阶段": "🔄 记忆生命周期",
            "操作": "清除",
            "状态": "🗑️",
            "原因": reason_names.get(reason, reason),
            "移除数量": removed_count,
            "剩余数量": remaining_count,
            "时间戳": datetime.now().isoformat(),
        }

        message = (
            f"[🔄 记忆生命周期] 🗑️ 清除 | "
            f"原因={reason_names.get(reason, reason)} | "
            f"移除={removed_count}条 | "
            f"剩余={remaining_count}条"
        )

        logger.info(message)
        self._write_json(log_data)

    # ========================================================================
    # 工具方法
    # ========================================================================

    def _write_json(self, data: Dict[str, Any]):
        """写入JSON格式的结构化日志。

        Args:
            data: 日志数据字典
        """
        try:
            # 输出到单独的日志文件
            json_logger = logging.getLogger("memory_json")
            json_logger.info(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            # JSON写入失败不影响主流程
            logger.debug(f"[结构化日志] JSON写入失败: {e}")


# 全局单例
_memory_logger: Optional[ChineseStructuredLogger] = None


def get_memory_logger() -> ChineseStructuredLogger:
    """获取记忆日志记录器单例。"""
    global _memory_logger
    if _memory_logger is None:
        _memory_logger = ChineseStructuredLogger()
    return _memory_logger
