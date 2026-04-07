"""SecurityFilter - 检测和阻止提示词注入攻击

提供安全过滤功能，检测：
1. 常见注入模式（如 "[INST]", "忽略以上", "越狱"等）
2. 特殊令牌转义（防止模型混淆）

这是提示词处理管道的第一层过滤器，在任何其他处理之前执行。
"""

import logging
import re
from typing import TYPE_CHECKING, List, Optional, Set, Tuple

from app.core.prompts.pipeline.base import IPromptFilter
from app.core.prompts.providers.base import PromptFilterResult

if TYPE_CHECKING:
    from app.core.context import RequestContext


class SecurityFilter(IPromptFilter):
    """安全过滤器 - 检测和阻止提示词注入攻击

    检测模式包括：
    - 结构化注入：[INST], <|im_start|>, <<SYS>> 等
    - 中英文注入指令："忽略以上", "ignore previous", "越狱" 等
    - 系统提示覆盖："系统提示", "system prompt" 等

    同时转义特殊令牌以防止模型混淆。
    """

    # 注入检测模式 - 检测这些模式意味着潜在的攻击
    INJECTION_PATTERNS: Set[str] = {
        # 结构化注入 - LLM 特殊令牌（区分大小写）
        "[INST]",
        "[/INST]",
        "<|im_start|>",
        "<|im_end|>",
        "<<SYS>>",
        "<</SYS>>",
        "",
        "<|end_of_text|>",
        "<|start_header_id|>",
        "<|end_header_id|>",
        # 中文注入模式（不区分大小写）
        "忽略以上",
        "忽略之前的",
        "忽略所有",
        "系统提示",
        "系统指令",
        "越狱",
        "jailbreak",
        # 英文注入模式（不区分大小写）
        "ignore previous",
        "ignore above",
        "ignore all",
        "disregard all",
        "forget previous",
        "forget everything",
        "new instructions",
        "override instructions",
        "system prompt",
        # 角色切换攻击（不区分大小写）
        "act as",
        "pretend to be",
        "you are now",
        "roleplay as",
        # DAN 模式攻击（不区分大小写）
        "dan mode",
        "developer mode",
        "unfiltered mode",
        # 间接注入（不区分大小写）
        "translate the following",
        "repeat the above",
        "summarize this",
    }

    # 需要转义的特殊令牌 - 这些不是攻击，但需要转义以避免混淆
    SPECIAL_TOKENS: Set[str] = {
        "<|im_start|>",
        "<|im_end|>",
        "[INST]",
        "[/INST]",
        "<<SYS>>",
        "<</SYS>>",
        "",
        "<|end_of_text|>",
        "<|start_header_id|>",
        "<|end_header_id|>",
        "<system>",
        "</system>",
        "<user>",
        "</user>",
        "<assistant>",
        "</assistant>",
    }

    # 编译正则表达式以提高性能
    _case_sensitive_regex: Optional[re.Pattern] = None
    _case_insensitive_regex: Optional[re.Pattern] = None
    _token_escape_map: Optional[dict] = None

    def __init__(self, enable_logging: bool = True) -> None:
        """初始化安全过滤器

        Args:
            enable_logging: 是否启用安全事件日志记录
        """
        self.enable_logging = enable_logging
        self._setup_patterns()
        self._logger = logging.getLogger(__name__)

    def _setup_patterns(self) -> None:
        """设置编译后的正则表达式模式

        延迟编译模式以提高启动性能。
        """
        if SecurityFilter._case_sensitive_regex is None:
            # 区分大小写的模式（特殊令牌）
            # 注意过滤掉空字符串（如 BOS token）
            case_sensitive_patterns = [
                re.escape("[INST]"),
                re.escape("[/INST]"),
                re.escape("<|im_start|>"),
                re.escape("<|im_end|>"),
                re.escape("<<SYS>>"),
                re.escape("<</SYS>>"),
                # Skip empty BOS token - re.escape("") = ""
                # re.escape(""),
                re.escape("<|end_of_text|>"),
                re.escape("<|start_header_id|>"),
                re.escape("<|end_header_id|>"),
            ]

            # 添加来自 INJECTION_PATTERNS 的自定义模式（不区分大小写的除外）
            # 检查是否有包含特殊字符的模式（可能是自定义添加的）
            custom_case_sensitive = set()
            for pattern in self.INJECTION_PATTERNS:
                # 跳过空模式和已经在默认列表中的模式
                if not pattern:
                    continue
                # 跳过已知的不区分大小写模式
                if pattern.lower() in {
                    "忽略以上", "忽略之前的", "忽略所有", "系统提示", "系统指令", "越狱",
                    "jailbreak", "ignore previous", "ignore above", "ignore all",
                    "disregard all", "forget previous", "forget everything",
                    "new instructions", "override instructions", "system prompt",
                    "act as", "pretend to be", "you are now", "roleplay as",
                    "dan mode", "developer mode", "unfiltered mode",
                    "translate the following", "repeat the above", "summarize this",
                }:
                    continue
                # 添加包含特殊字符的模式（可能是正则表达式或特殊令牌）
                if any(c in pattern for c in r'[]<>|'):
                    custom_case_sensitive.add(re.escape(pattern))

            case_sensitive_patterns.extend(custom_case_sensitive)
            # 过滤掉空模式
            case_sensitive_patterns = [p for p in case_sensitive_patterns if p]
            SecurityFilter._case_sensitive_regex = re.compile(
                "|".join(f"(?:{p})" for p in case_sensitive_patterns),
                flags=re.DOTALL | re.MULTILINE,
            )

        if SecurityFilter._case_insensitive_regex is None:
            # 不区分大小写的模式（文本注入）
            case_insensitive_patterns = [
                # 中文模式
                "忽略以上",
                "忽略之前的",
                "忽略所有",
                "系统提示",
                "系统指令",
                "越狱",
                "jailbreak",
                # 英文模式
                r"ignore\s+previous",
                r"ignore\s+above",
                r"ignore\s+all",
                r"disregard\s+(?:all|the\s+above)",
                r"forget\s+previous",
                r"forget\s+everything",
                r"new\s+instructions",
                r"override\s+(?:system\s+)?instructions",
                r"system\s+prompt",
                r"act\s+as",
                r"pretend\s+to\s+be",
                r"you\s+are\s+now",
                r"roleplay\s+as",
                r"dan\s+mode",
                r"developer\s+mode",
                r"unfiltered\s+mode",
                r"translate\s+the\s+following",
                r"repeat\s+the\s+above",
                r"summarize\s+this",
            ]

            # 添加自定义的不区分大小写模式
            # 这些是纯文本模式，没有特殊正则字符
            for pattern in self.INJECTION_PATTERNS:
                if not pattern:
                    continue
                # 只添加不包含特殊正则字符的模式（作为文本匹配）
                if not any(c in pattern for c in r'[]<>|()*+?{}^$'):
                    # 转义为正则表达式，匹配文本中的空格为 \s+
                    regex_pattern = r'\s+'.join(re.escape(word) for word in pattern.split())
                    case_insensitive_patterns.append(regex_pattern)

            SecurityFilter._case_insensitive_regex = re.compile(
                "|".join(f"(?:{p})" for p in case_insensitive_patterns),
                flags=re.DOTALL | re.MULTILINE | re.IGNORECASE,
            )

        if SecurityFilter._token_escape_map is None:
            # 创建转义映射
            SecurityFilter._token_escape_map = {
                "<": "&lt;",
                ">": "&gt;",
            }

    def _detect_injection(self, prompt: str) -> Tuple[bool, Optional[str]]:
        """检测提示词中的注入模式

        Args:
            prompt: 待检测的提示词内容

        Returns:
            (is_injection, detected_pattern): 是否检测到注入和检测到的模式
        """
        if SecurityFilter._case_sensitive_regex is None:
            self._setup_patterns()

        # 首先检查区分大小写的模式
        match = SecurityFilter._case_sensitive_regex.search(prompt)
        if match:
            detected = match.group(0)
            safe_detected = repr(detected[:100])  # 限制长度
            return True, safe_detected

        # 然后检查不区分大小写的模式
        match = SecurityFilter._case_insensitive_regex.search(prompt)
        if match:
            detected = match.group(0)
            safe_detected = repr(detected[:100])  # 限制长度
            return True, safe_detected

        return False, None

    def _escape_special_tokens(self, prompt: str) -> str:
        """转义特殊令牌以防止模型混淆

        Args:
            prompt: 待处理的提示词内容

        Returns:
            转义后的提示词内容
        """
        result = prompt

        # 检测并转义已知的特殊令牌
        # 按长度排序，优先匹配更长的令牌（避免部分匹配问题）
        for token in sorted(self.SPECIAL_TOKENS, key=len, reverse=True):
            if token in result:
                # 根据令牌类型选择转义策略
                if "<" in token or ">" in token:
                    # 尖括号令牌 - 转义尖括号
                    escaped = token.replace("<", "&lt;").replace(">", "&gt;")
                elif "[" in token or "]" in token:
                    # 方括号令牌 - 插入零宽字符或使用 HTML 实体
                    escaped = token.replace("[", "&lsqb;").replace("]", "&rsqb;")
                else:
                    # 其他令牌 - 使用通用转义
                    escaped = "".join(f"&#{ord(c)};" for c in token)

                result = result.replace(token, escaped)

        return result

    def _log_security_event(
        self,
        event_type: str,
        user_id: Optional[str],
        details: dict,
    ) -> None:
        """记录安全事件

        Args:
            event_type: 事件类型（injection_detected, tokens_escaped）
            user_id: 用户 ID
            details: 事件详情
        """
        if not self.enable_logging:
            return

        log_data = {
            "event_type": event_type,
            "user_id": user_id,
            **details,
        }

        if event_type == "injection_detected":
            self._logger.warning("Security event: %s", log_data)
        else:
            self._logger.info("Security event: %s", log_data)

    async def process(
        self,
        prompt: str,
        context: "RequestContext",
    ) -> PromptFilterResult:
        """处理提示词内容，检测注入并转义特殊令牌

        Args:
            prompt: 待处理的提示词内容
            context: 请求上下文

        Returns:
            PromptFilterResult: 过滤结果
        """
        # 1. 检测注入攻击
        is_injection, detected_pattern = self._detect_injection(prompt)

        if is_injection:
            self._log_security_event(
                "injection_detected",
                context.user_id,
                {
                    "detected_pattern": detected_pattern,
                    "prompt_length": len(prompt),
                    "conversation_id": context.conversation_id,
                },
            )

            return PromptFilterResult(
                success=False,
                content="",  # 不返回任何内容
                error=f"Potential prompt injection detected: {detected_pattern}",
                should_fallback=True,  # 建议回退到安全默认行为
            )

        # 2. 转义特殊令牌
        escaped_content = self._escape_special_tokens(prompt)

        # 3. 检查是否有内容被转义
        if escaped_content != prompt:
            self._log_security_event(
                "tokens_escaped",
                context.user_id,
                {
                    "original_length": len(prompt),
                    "escaped_length": len(escaped_content),
                    "conversation_id": context.conversation_id,
                },
            )

            return PromptFilterResult(
                success=True,
                content=escaped_content,
                warning="Special tokens were escaped to prevent model confusion",
            )

        # 4. 内容安全，无需修改
        return PromptFilterResult(
            success=True,
            content=prompt,
        )


class SecurityFilterConfig:
    """安全过滤器配置

    提供默认配置和配置验证。
    """

    # 默认注入模式（可以通过配置覆盖）
    DEFAULT_INJECTION_PATTERNS = SecurityFilter.INJECTION_PATTERNS

    # 默认特殊令牌（可以通过配置覆盖）
    DEFAULT_SPECIAL_TOKENS = SecurityFilter.SPECIAL_TOKENS

    @classmethod
    def create_filter(
        cls,
        custom_patterns: Optional[Set[str]] = None,
        custom_tokens: Optional[Set[str]] = None,
        enable_logging: bool = True,
    ) -> SecurityFilter:
        """创建带有自定义配置的安全过滤器

        Args:
            custom_patterns: 自定义注入检测模式（支持正则表达式）
            custom_tokens: 自定义需要转义的特殊令牌
            enable_logging: 是否启用日志记录

        Returns:
            配置好的 SecurityFilter 实例
        """
        # 先添加自定义模式到集合
        if custom_patterns is not None:
            SecurityFilter.INJECTION_PATTERNS.update(custom_patterns)

        if custom_tokens is not None:
            SecurityFilter.SPECIAL_TOKENS.update(custom_tokens)

        # 重置编译的正则表达式
        SecurityFilter._case_sensitive_regex = None
        SecurityFilter._case_insensitive_regex = None

        # 创建过滤器（会重新编译正则表达式）
        filter_obj = SecurityFilter(enable_logging=enable_logging)

        return filter_obj
