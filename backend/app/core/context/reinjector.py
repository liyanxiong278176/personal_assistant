"""核心规则重注入 - 阶段7

在压缩后重新注入核心规则，防止 AI 行为失控。
"""

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def _get_injected_rules_from_cache(
    rules_cache: Dict[str, str],
    rules_files: List[str]
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

    def reinject(
        self,
        messages: List[Dict],
        rules_cache: Dict[str, str]
    ) -> List[Dict]:
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
            # 判断来源：
            # - 如果上次注入位置已设置且 rules 位于该位置附近，说明是之前调用插入的，可以再次注入
            # - 如果上次注入位置未设置（=-1），说明是输入数据自带的，跳过避免重复
            if self._last_reinject_position >= 0:
                # 之前调用插入的：检查间隔
                messages_since = len(messages) - self._last_reinject_position
                if messages_since < self.config.rules_reinject_interval:
                    return messages
            else:
                # 输入自带的 rules，跳过
                return messages

        # 检查是否需要注入
        if not self._should_reinject(messages, rules_cache):
            return messages

        rules = _get_injected_rules_from_cache(
            rules_cache,
            self.config.rules_files
        )
        if not rules:
            return messages

        # 构建规则消息
        rule_msg = {
            "role": "system",
            "content": rules,
            "_rules_reinjected": True
        }

        # 找到合适的插入位置（摘要后，当前对话前）
        result: List[Dict] = []
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

        logger.debug(
            f"[RuleReinjector] Rules reinjected | Position: {self._last_reinject_position}"
        )

        return result

    def _should_reinject(
        self,
        messages: List[Dict],
        rules_cache: Dict[str, str]
    ) -> bool:
        """判断是否需要重新注入规则

        规则:
        1. 规则缓存非空
        2. 最近 N 条消息中没有规则消息（跳过 position-0，由 reinject 提前处理）
        3. 距离上次注入至少 N 条消息
        """
        if not rules_cache:
            return False

        # 检查最近的消息（跳过 position-0）
        window = self.config.rules_reinject_window
        recent = messages[-window:] if len(messages) >= window else messages

        for m in recent[1:]:
            if m.get("_rules_reinjected"):
                return False

        # 检查距离上次注入的消息数
        if self._last_reinject_position >= 0:
            messages_since = len(messages) - self._last_reinject_position
            if messages_since < self.config.rules_reinject_interval:
                return False

        return True


__all__ = ["RuleReinjector"]
