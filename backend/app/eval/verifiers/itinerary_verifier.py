"""行程规划验证器 — 规则检查 + 评分"""
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class VerificationResult:
    """验证结果

    Attributes:
        score: 0-100分
        passed: score >= 80 为通过
        checkpoints: 通过的检查项列表
        failed_items: 未通过的检查项列表
        feedback: 给 LLM 的修正反馈
        iteration_number: 当前迭代次数
        result_type: 结果类型标识
    """
    score: int  # 0-100
    passed: bool  # score >= 80
    checkpoints: List[str] = field(default_factory=list)
    failed_items: List[str] = field(default_factory=list)
    feedback: str = ""  # 给 LLM 的修正反馈
    iteration_number: int = 1
    result_type: str = "itinerary"


class ItineraryVerifier:
    """行程规划验证器

    规则:
    - 必填字段 (40分): 目的地、日程、交通
    - 逻辑一致性 (30分): 日期结构、内容充实
    - 质量评分 (30分): 推荐理由、预算、详情
    """

    # 常见中国城市列表（用于目的地检测）
    COMMON_DESTINATIONS = [
        "北京", "上海", "广州", "深圳", "杭州", "成都", "西安", "重庆",
        "南京", "武汉", "厦门", "青岛", "大连", "三亚", "桂林", "丽江",
        "拉萨", "乌鲁木齐", "哈尔滨", "昆明", "苏州", "天津", "长沙",
        "郑州", "沈阳", "济南", "福州", "南宁", "贵阳", "兰州", "银川",
        "西宁", "海口", "呼和浩特", "石家庄", "太原", "长春", "南昌",
        "目的地", "景点", "景区", "去", "游览", "参观", "玩", "旅行",
    ]

    # 日期结构关键词
    DAY_KEYWORDS = [
        "第一天", "第二天", "第三天", "第四天", "第五天",
        "day 1", "day 2", "day 3", "day 4", "day 5",
        "第1天", "第2天", "第3天", "第4天", "第5天",
        "日程", "行程", "安排", "时间表",
    ]

    # 交通方式关键词
    TRANSPORT_KEYWORDS = [
        "火车", "高铁", "动车", "飞机", "自驾", "大巴", "客车",
        "地铁", "公交", "出租车", "网约车", "步行", "骑行",
        "交通", "前往", "到达", "出发", "返程",
    ]

    # 质量关键词
    QUALITY_KEYWORDS = [
        "推荐", "建议", "最佳", "必去", "特色", "著名", "知名",
        "美食", "小吃", "特产", "购物", "住宿", "酒店", "民宿",
    ]

    # 预算相关关键词
    BUDGET_KEYWORDS = [
        "预算", "花费", "费用", "价格", "票价", "门票", "住宿费",
        "餐饮费", "交通费", "总计", "大约", "左右", "元", "¥",
    ]

    # === Class-level constants for magic numbers ===
    # Score thresholds for feedback tiers
    SCORE_THRESHOLD_LOW = 40
    SCORE_THRESHOLD_MEDIUM = 60
    # Maximum content length tiers for quality scoring
    CONTENT_LENGTH_MINIMAL = 100
    CONTENT_LENGTH_BASIC = 200
    CONTENT_LENGTH_MODERATE = 300
    CONTENT_LENGTH_DETAILED = 500

    def __init__(self, pass_threshold: int = 80, max_iterations: int = 3):
        """初始化验证器

        Args:
            pass_threshold: 通过阈值，默认80分
            max_iterations: 最大迭代次数，默认3次

        Raises:
            ValueError: pass_threshold 不在 0-100 范围内
        """
        if not 0 <= pass_threshold <= 100:
            raise ValueError(
                f"pass_threshold must be between 0 and 100, got {pass_threshold}"
            )
        self.pass_threshold = pass_threshold
        self.max_iterations = max_iterations

    def verify(self, plan_text: str, **kwargs) -> VerificationResult:
        """验证行程规划文本

        Args:
            plan_text: LLM 生成的行程规划文本
            **kwargs: 额外参数（如用户原始需求，用于更精准的反馈）

        Returns:
            VerificationResult: 验证结果
        """
        if not plan_text:
            return VerificationResult(
                score=0,
                passed=False,
                failed_items=["✗ 行程为空"],
                feedback="请生成完整的行程规划。",
                iteration_number=kwargs.get("iteration_number", 1)
            )

        plan_lower = plan_text.lower()
        score = 0
        checkpoints = []
        failed_items = []

        # === 必填字段 (40分) ===
        # 1. 目的地检测 (15分)
        has_destination = any(
            kw in plan_text for kw in self.COMMON_DESTINATIONS
        )
        if has_destination:
            checkpoints.append("✓ 包含目的地")
            score += 15
        else:
            failed_items.append("✗ 缺少目的地信息")
            score += 0

        # 2. 日程结构检测 (15分)
        has_days = any(kw in plan_text for kw in self.DAY_KEYWORDS)
        if has_days:
            checkpoints.append("✓ 包含日程安排")
            score += 15
        else:
            failed_items.append("✗ 缺少日程安排")
            score += 0

        # 3. 交通信息 (10分)
        has_transport = any(kw in plan_text for kw in self.TRANSPORT_KEYWORDS)
        if has_transport:
            checkpoints.append("✓ 包含交通信息")
            score += 10
        else:
            failed_items.append("✗ 缺少交通信息")
            score += 0

        # === 逻辑一致性 (30分) ===
        # 4. 日期结构 (15分)
        has_day_structure = any(kw in plan_text for kw in ["第一天", "第二天", "day 1", "day 2", "第1天", "第2天"])
        if has_day_structure:
            checkpoints.append("✓ 日期结构清晰")
            score += 15
        else:
            failed_items.append("✗ 日期结构不清晰")
            score += 0

        # 5. 内容充实度 (15分)
        content_length = len(plan_text)
        if content_length > self.CONTENT_LENGTH_BASIC:
            checkpoints.append("✓ 内容充实")
            score += 15
        elif content_length > self.CONTENT_LENGTH_MINIMAL:
            checkpoints.append("~ 内容基本充实")
            score += 8
            failed_items.append("~ 内容略显简略")
        else:
            failed_items.append("✗ 行程过于简略")
            score += 0

        # === 质量评分 (30分) ===
        quality_score = 0

        # 6. 推荐性词语 (10分)
        has_recommendation = any(kw in plan_lower for kw in ["推荐", "建议", "最佳", "必去", "特色"])
        if has_recommendation:
            quality_score += 10

        # 7. 预算信息 (10分)
        has_budget = any(kw in plan_text for kw in self.BUDGET_KEYWORDS)
        if has_budget:
            quality_score += 10

        # 8. 详细程度 (10分)
        if content_length > self.CONTENT_LENGTH_DETAILED:
            quality_score += 10
        elif content_length > self.CONTENT_LENGTH_MODERATE:
            quality_score += 5

        score += quality_score
        score = min(score, 100)

        # 确保通过状态基于阈值
        passed = score >= self.pass_threshold

        # 生成反馈
        feedback = self._generate_feedback(
            failed_items=failed_items,
            score=score,
            plan_text=plan_text,
            iteration_number=kwargs.get("iteration_number", 1)
        )

        return VerificationResult(
            score=score,
            passed=passed,
            checkpoints=checkpoints,
            failed_items=failed_items,
            feedback=feedback,
            iteration_number=kwargs.get("iteration_number", 1),
            result_type="itinerary"
        )

    def _generate_feedback(
        self,
        failed_items: List[str],
        score: int,
        plan_text: str,
        iteration_number: int
    ) -> str:
        """生成给 LLM 的修正反馈

        Args:
            failed_items: 未通过的检查项
            score: 当前得分
            plan_text: 原始行程文本
            iteration_number: 当前迭代次数

        Returns:
            反馈文本
        """
        if not failed_items:
            return ""

        # 提取关键失败项（去掉前缀符号）
        key_failures = [
            item.replace("✗ ", "").replace("~ ", "")
            for item in failed_items[:3]
        ]

        if score < self.SCORE_THRESHOLD_LOW:
            # 低分：严重缺失
            feedback = (
                f"行程不完整，缺少关键信息：{', '.join(key_failures)}。"
                f"请补充目的地、具体日程安排和交通方式。"
            )
        elif score < self.SCORE_THRESHOLD_MEDIUM:
            # 中低分：基本结构有，内容不足
            feedback = (
                f"行程规划需要完善：{', '.join(key_failures)}。"
                f"建议增加每天的详细活动安排和具体景点信息。"
            )
        elif score < self.pass_threshold:
            # 接近及格：有细节但不完整
            feedback = (
                f"行程规划较为完整，但可以进一步优化：{', '.join(key_failures)}。"
                f"建议补充预算估算和更多实用建议。"
            )
        else:
            # 高分但未通过（阈值调高时）
            feedback = f"行程规划质量良好，建议优化：{', '.join(key_failures)}。"

        return feedback

    async def verify_with_retry(
        self,
        plan_text: str,
        llm_callback: Optional[Callable[..., Awaitable[str]]] = None,
        **kwargs
    ) -> VerificationResult:
        """带重试的验证（预留接口）

        当验证不通过时，可以调用 llm_callback 重新生成。

        Args:
            plan_text: 初始行程文本
            llm_callback: 可选的 LLM 回调函数，接收反馈并返回新文本
            **kwargs: 额外参数

        Returns:
            最终验证结果
        """
        iteration = 0
        current_plan = plan_text
        seen_signatures = set()

        while iteration < self.max_iterations:
            iteration += 1
            result = self.verify(current_plan, iteration_number=iteration, **kwargs)

            if result.passed:
                logger.info(
                    f"[ItineraryVerifier] ✅ 验证通过 | "
                    f"iter={iteration} | score={result.score}"
                )
                return result

            # 检测反馈循环（避免相同反馈无限重试）
            feedback_sig = f"{result.feedback[:50]}_{len(current_plan)}"
            if feedback_sig in seen_signatures:
                logger.warning(
                    f"[ItineraryVerifier] ⚠️ 反馈无变化，停止迭代 | "
                    f"iter={iteration} | score={result.score}"
                )
                break
            seen_signatures.add(feedback_sig)

            logger.warning(
                f"[ItineraryVerifier] ❌ 验证未通过 | "
                f"iter={iteration} | score={result.score} | {result.feedback}"
            )

            # 如果提供了回调，尝试重新生成
            if llm_callback:
                try:
                    current_plan = await llm_callback(result.feedback, current_plan)
                except Exception as e:
                    logger.error(f"[ItineraryVerifier] LLM 回调失败: {e}")
                    break
            else:
                # 无回调，直接返回当前结果
                # TODO: 真实迭代重试需要重新调用 LLM，当前版本标记失败供后续优化
                break

        return result
