import logging
from ..llm import LLMClient
from ..intent.classifier import IntentResult

logger = logging.getLogger(__name__)

class ModelRouter:
    """模型路由器 - 根据意图和复杂度选择合适的模型"""

    # 模型配置
    SMALL_MODEL = "deepseek-chat"  # 或更便宜的模型
    LARGE_MODEL = "deepseek-reasoner"  # 或更强模型

    def __init__(
        self,
        small_client: LLMClient | None = None,
        large_client: LLMClient | None = None
    ):
        self._small_client = small_client or LLMClient(model=self.SMALL_MODEL)
        self._large_client = large_client or LLMClient(model=self.LARGE_MODEL)
        self.logger = logging.getLogger(__name__)

    def route(
        self,
        intent: IntentResult,
        is_complex: bool
    ) -> LLMClient:
        """根据意图和复杂度路由到合适的模型

        Args:
            intent: 意图分类结果
            is_complex: 是否为复杂查询

        Returns:
            配置好的 LLMClient
        """
        # 复杂规划 → 大模型
        if intent.intent == "itinerary" and is_complex:
            self.logger.info(f"[ModelRouter] Route to LARGE model: {intent.intent}, complex={is_complex}")
            return self._large_client

        # 其他全部 → 小模型
        self.logger.debug(f"[ModelRouter] Route to SMALL model: {intent.intent}, complex={is_complex}")
        return self._small_client
