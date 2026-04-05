"""查询复杂度检测模块"""

from dataclasses import dataclass
from typing import Optional, Callable, Any


@dataclass
class ComplexityResult:
    is_complex: bool
    reason: str
    score: float  # 0-1, 越高越复杂


def is_complex_query(
    message: str,
    extract_slots: Optional[Callable[[str], Any]] = None
) -> ComplexityResult:
    """检测查询是否复杂。

    Args:
        message: 用户输入的消息文本
        extract_slots: 可选的槽位提取函数，用于提取消息中的结构化信息

    Returns:
        ComplexityResult: 包含复杂度判断结果、原因和分数的数据类
    """
    score = 0.0
    reasons = []

    # 长度检测
    if len(message) > 30:
        score += 0.3
        reasons.append("消息较长")
    elif len(message) > 20:
        score += 0.1
        reasons.append("消息中等长度")

    # 槽位数量检测
    if extract_slots:
        slots = extract_slots(message)
        slot_count = sum([
            bool(getattr(slots, "destination", None)),
            bool(getattr(slots, "duration", None)),
            bool(getattr(slots, "budget", None)),
            bool(getattr(slots, "dates", None)),
        ])
        if slot_count >= 3:
            score += 0.5
            reasons.append(f"包含{slot_count}个槽位")
        elif slot_count >= 2:
            score += 0.2
            reasons.append(f"包含{slot_count}个槽位")

    # 关键词检测（复杂需求）
    complex_keywords = ["规划", "定制", "推荐", "安排", "设计"]
    if any(kw in message for kw in complex_keywords):
        score += 0.2
        reasons.append("包含规划类关键词")

    is_complex = score >= 0.5
    return ComplexityResult(
        is_complex=is_complex,
        reason="; ".join(reasons) if reasons else "简单查询",
        score=score
    )
