"""核心规则重注入 - 阶段7

在压缩后重新注入核心规则，防止 AI 行为失控。
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


# ============================================================
# 结构化日志宏
# ============================================================


def _log_reinject_decision(skipped: bool, reason: str):
    """规则注入决策日志"""
    if skipped:
        logger.debug(f"[REINJECTOR] ⏭️ 跳过注入 | 原因={reason}")
    else:
        logger.debug(f"[REINJECTOR] ✅ 允许注入")


def _log_reinject_window_check(window: int, has_rules: bool):
    """窗口检查日志"""
    logger.debug(
        f"[REINJECTOR] 🔍 窗口检查 | 窗口={window} | 近期有规则={has_rules}"
    )


def _log_reinject_interval_check(interval: int, messages_since: int):
    """间隔检查日志"""
    allowed = messages_since >= interval
    symbol = "✅" if allowed else "⏳"
    logger.debug(
        f"[REINJECTOR] ⏱️ 间隔检查 | 间隔要求={interval} | "
        f"距上次注入={messages_since}条 | {symbol}"
    )


def _log_reinject_result(position: int, input_count: int, output_count: int,
                         rules_size: int, insert_after_compressed: bool):
    """注入结果日志"""
    action = "摘要后" if insert_after_compressed else "开头"
    logger.info(
        f"[REINJECTOR] 📥 规则注入完成 | "
        f"输入={input_count}条 → 输出={output_count}条 | "
        f"注入位置={action}(pos={position}) | "
        f"规则大小≈{rules_size}字符"
    )


def _log_reinject_skip(reason: str, messages_count: int):
    """跳过注入日志"""
    logger.debug(
        f"[REINJECTOR] ⏭️ 跳过注入 | 原因={reason} | 消息数={messages_count}"
    )


def _get_injected_rules_from_cache(
    rules_cache: Dict[str, str], rules_files: List[str]
) -> str:
    """从缓存中获取格式化的规则字符串

    Args:
        rules_cache: 规则文件缓存
        rules_files: 规则文件列表（决定格式和顺序）

    Returns:
        格式化的规则字符串
    """
    if not rules_cache:
        return ""

    parts = []
    for filename in rules_files:
        if filename in rules_cache:
            content = rules_cache[filename]
            if content:
                parts.append(f"### {filename}\n{content}")

    return "\n\n".join(parts)


class RuleReinjector:
    """核心规则重注入器

    在压缩后重新注入核心规则，防止 AI 行为失控。

    职责:
    1. 判断是否需要重新注入规则
    2. 在压缩摘要后插入规则，无摘要则插入到开头
    3. 遵守重注入间隔和窗口控制
    """

    def __init__(self, config):
        """初始化规则重注入器

        Args:
            config: ContextConfig 实例
        """
        self.config = config
        self._last_reinject_position = -1

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

        # 如果第一条消息已经是规则
        if messages[0].get("_rules_reinjected"):
            if self._last_reinject_position >= 0:
                messages_since = len(messages) - self._last_reinject_position
                if messages_since < self.config.rules_reinject_interval:
                    _log_reinject_skip(f"第一条已是规则且间隔不足({messages_since}<{self.config.rules_reinject_interval})", len(messages))
                    return messages
            else:
                _log_reinject_skip("第一条已是规则(输入自带)", len(messages))
                return messages

        # 检查是否需要注入
        if not self._should_reinject(messages, rules_cache):
            _log_reinject_skip("should_reinject返回False", len(messages))
            return messages

        rules = _get_injected_rules_from_cache(rules_cache, self.config.rules_files)
        if not rules:
            _log_reinject_skip("规则缓存为空", len(messages))
            return messages

        # 构建规则消息
        rule_msg = {"role": "system", "content": rules, "_rules_reinjected": True}

        # 找到合适的插入位置（摘要后，当前对话前）
        result: List[Dict] = []
        inserted = False
        insert_after_compressed = False

        for i, msg in enumerate(messages):
            result.append(msg)

            # 在压缩摘要后插入
            if not inserted and msg.get("_compressed"):
                result.append(rule_msg)
                self._last_reinject_position = i
                inserted = True
                insert_after_compressed = True

        # 如果没找到摘要，插入到开头
        if not inserted:
            result.insert(0, rule_msg)
            self._last_reinject_position = 0

        _log_reinject_result(
            self._last_reinject_position,
            len(messages), len(result),
            len(rules), insert_after_compressed
        )

        return result

    def _should_reinject(
        self, messages: List[Dict], rules_cache: Dict[str, str]
    ) -> bool:
        """判断是否需要重新注入规则

        规则:
        1. 规则缓存非空
        2. 最近 N 条消息中没有规则消息（跳过 position-0，由 reinject 提前处理）
        3. 距离上次注入至少 N 条消息
        """
        if not rules_cache:
            _log_reinject_decision(True, "规则缓存为空")
            return False

        # 检查最近的消息（跳过 position-0）
        window = self.config.rules_reinject_window
        recent = messages[-window:] if len(messages) >= window else messages

        has_recent_rules = False
        for m in recent[1:]:
            if m.get("_rules_reinjected"):
                has_recent_rules = True
                break

        _log_reinject_window_check(window, has_recent_rules)
        if has_recent_rules:
            _log_reinject_decision(True, "近期消息中已有规则")
            return False

        # 检查距离上次注入的消息数
        if self._last_reinject_position >= 0:
            messages_since = len(messages) - self._last_reinject_position
            _log_reinject_interval_check(self.config.rules_reinject_interval, messages_since)
            if messages_since < self.config.rules_reinject_interval:
                _log_reinject_decision(True, f"间隔不足({messages_since}<{self.config.rules_reinject_interval})")
                return False

        _log_reinject_decision(False, "通过所有检查")
        return True


__all__ = ["RuleReinjector"]
