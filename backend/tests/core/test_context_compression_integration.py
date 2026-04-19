"""上下文管理集成测试 - 模拟多轮对话测试压缩策略

这个测试模拟真实的多轮对话场景，验证：
1. 压缩阈值前的状态（不需要压缩，前端进度条不打勾）
2. 压缩阈值后的自动压缩（前端显示压缩状态）
3. 窗口占满时的系统处理
4. 前置清理、推理时守卫、后置压缩、流式兜底等机制的工作
"""

import asyncio
import logging
from typing import List, Dict
from datetime import datetime
from app.core.context_mgmt.guard import ContextGuard
from app.core.context_mgmt.config import get_default_config
from app.core.context_mgmt.tokenizer import TokenEstimator

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ContextCompressionTester:
    """上下文压缩测试器"""

    def __init__(self, window_size: int = 4000, compress_threshold: float = 0.8):
        """初始化测试器

        Args:
            window_size: 上下文窗口大小（默认4000 tokens）
            compress_threshold: 压缩阈值（默认0.8，即80%时触发）
        """
        # 创建新的配置实例而不是修改默认配置
        from app.core.context_mgmt.config import ContextConfig
        self.config = ContextConfig(
            window_size=window_size,
            compress_threshold=compress_threshold
        )

        self.guard = ContextGuard(config=self.config)
        self.guard.set_conv_id("test_conversation")

        # 测试统计
        self.test_stats = {
            "round": 0,
            "messages": [],
            "compression_triggered": False,
            "total_messages": 0,
            "compression_round": None,
        }

    def create_test_message(self, role: str, content: str) -> Dict:
        """创建测试消息

        Args:
            role: 消息角色（user/assistant/system/tool）
            content: 消息内容

        Returns:
            消息字典
        """
        return {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        }

    async def simulate_conversation_round(self, user_input: str, assistant_response: str) -> Dict:
        """模拟一轮对话

        Args:
            user_input: 用户输入
            assistant_response: 助手回复

        Returns:
            本轮的统计信息
        """
        self.test_stats["round"] += 1
        round_num = self.test_stats["round"]

        logger.info(f"\n{'='*60}")
        logger.info(f"第 {round_num} 轮对话开始")
        logger.info(f"{'='*60}")

        # 添加用户消息
        user_msg = self.create_test_message("user", user_input)
        self.test_stats["messages"].append(user_msg)

        # 添加助手消息
        assistant_msg = self.create_test_message("assistant", assistant_response)
        self.test_stats["messages"].append(assistant_msg)

        # 前置清理
        logger.info(f"📥 执行前置清理...")
        cleaned, was_cleaned = await self.guard.pre_process(self.test_stats["messages"])
        logger.info(f"前置清理结果: {'执行了清理' if was_cleaned else '无需清理'}")

        # 获取当前token统计
        current_tokens = TokenEstimator.estimate_messages(cleaned)
        threshold = int(self.config.window_size * self.config.compress_threshold)
        usage_ratio = current_tokens / self.config.window_size

        logger.info(f"📊 当前状态:")
        logger.info(f"  消息数: {len(cleaned)}")
        logger.info(f"  Tokens: {current_tokens}/{self.config.window_size} ({usage_ratio:.1%})")
        logger.info(f"  压缩阈值: {threshold} ({self.config.compress_threshold:.1%})")

        # 检查是否需要压缩
        needs_compression = self.guard.should_compress(cleaned)
        logger.info(f"🔍 压缩检查: {'需要压缩' if needs_compression else '无需压缩'}")

        # 后置处理（可能触发压缩）
        logger.info(f"📤 执行后置处理...")
        processed, was_compressed = await self.guard.post_process(cleaned)
        logger.info(f"后置处理结果: {'执行了压缩' if was_compressed else '无需压缩'}")

        # 更新消息列表
        self.test_stats["messages"] = processed
        self.test_stats["total_messages"] += 2

        # 记录压缩触发
        if was_compressed and not self.test_stats["compression_triggered"]:
            self.test_stats["compression_triggered"] = True
            self.test_stats["compression_round"] = round_num

        # 获取最终统计
        final_tokens = TokenEstimator.estimate_messages(processed)
        guard_stats = self.guard.get_stats()

        # 返回本轮统计
        round_stats = {
            "round": round_num,
            "messages_count": len(processed),
            "tokens_before": current_tokens,
            "tokens_after": final_tokens,
            "usage_ratio": usage_ratio,
            "threshold": threshold,
            "needs_compression": needs_compression,
            "was_compressed": was_compressed,
            "cleaned": was_cleaned,
            "current_phase": guard_stats.get("current_phase", "idle"),
        }

        self._log_round_summary(round_stats)

        return round_stats

    def _log_round_summary(self, stats: Dict):
        """输出本轮总结

        Args:
            stats: 本轮统计信息
        """
        logger.info(f"\n📋 第 {stats['round']} 轮总结:")
        logger.info(f"  消息数: {stats['messages_count']}")
        logger.info(f"  Token变化: {stats['tokens_before']} → {stats['tokens_after']}")
        logger.info(f"  使用率: {stats['usage_ratio']:.1%} (阈值: {stats['threshold']})")
        logger.info(f"  清理: {'✅' if stats['cleaned'] else '❌'}")
        logger.info(f"  压缩: {'✅' if stats['was_compressed'] else '❌'}")
        logger.info(f"  当前阶段: {stats['current_phase']}")

        # 前端状态模拟
        if stats['was_compressed']:
            logger.info(f"  🎨 前端状态: 进度条显示 [✓] 压缩完成")
        elif stats['usage_ratio'] > 0.6:
            logger.info(f"  🎨 前端状态: 进度条显示 [{int(stats['usage_ratio']*100)}%] 逐步接近阈值")
        else:
            logger.info(f"  🎨 前端状态: 进度条显示 [{int(stats['usage_ratio']*100)}%] 正常")

    async def run_comprehensive_test(self):
        """运行全面的压缩测试"""
        logger.info("🚀 开始上下文压缩全面测试")
        logger.info(f"配置: 窗口大小={self.config.window_size}, 压缩阈值={self.config.compress_threshold:.1%}")

        # 准备不同长度的测试消息
        short_conversations = [
            ("你好", "你好！有什么我可以帮助你的吗？"),
            ("今天天气怎么样", "我需要知道你的位置才能查询天气"),
            ("我在北京", "北京今天晴天，温度20-28度，适宜出行"),
        ]

        medium_conversations = [
            ("请帮我规划一个3天的北京旅行行程", "好的，我来为你规划3天的北京行程。第一天可以游览故宫和天安门；第二天可以爬长城；第三天可以逛颐和园。"),
            ("第一天想去哪些景点", "第一天推荐：上午天安门广场，下午故宫，晚上王府井大街。这样可以充分感受北京的历史文化"),
            ("第二天呢", "第二天八达岭长城，建议早起避免人流高峰。可以体验缆车上下，节省体力"),
        ]

        long_conversations = [
            ("请详细介绍故宫的历史", "故宫，旧称紫禁城，是中国明清两代的皇家宫殿，位于北京中轴线的中心。故宫以三大殿为中心，占地面积约72万平方米，建筑面积约15万平方米，有大小宫殿七十多座，房屋九千余间。"),
            ("故宫有哪些珍贵的文物", "故宫博物院藏有大量珍贵文物，包括书画、陶瓷、青铜器、玉器等。著名的《清明上河图》、《千里江山图》等都收藏于此。据统计，故宫藏品总数超过180万件（套）"),
            ("推荐一些详细的参观路线", "推荐经典游览路线：午门 → 太和殿 → 中和殿 → 保和殿 → 乾清宫 → 坤宁宫 → 御花园。这条路线可以游览故宫的主要建筑，全程约3-4小时。建议提前在线预约门票，携带身份证件"),
        ]

        # 超长消息（用于测试压缩）
        extra_long_content = """
        这是一段很长的内容，用于测试上下文压缩功能。在实际应用中，可能存在以下场景：
        1. 用户进行多轮对话，累计大量上下文信息
        2. 系统调用工具返回大量数据
        3. 助手生成详细的回复内容
        4. 用户上传文档或图片进行识别分析

        上下文管理的重要性：
        - 保持在模型的token限制内
        - 保留重要的对话历史
        - 及时清理过期的工具结果
        - 在合适的时机进行压缩

        压缩策略包括：
        - 前置清理：清理过期的工具调用结果
        - 后置压缩：将旧消息摘要化
        - 规则重注入：确保核心规则不被遗忘
        - 流式兜底：在生成过程中动态调整
        """ * 10  # 重复10次增加长度

        # 阶段1：正常对话（不应触发压缩）
        logger.info(f"\n{'#'*60}")
        logger.info("# 阶段1: 正常对话 - 不应触发压缩")
        logger.info(f"{'#'*60}")

        for user_input, assistant_response in short_conversations:
            await self.simulate_conversation_round(user_input, assistant_response)

        # 阶段2：中等长度对话（逐步接近阈值）
        logger.info(f"\n{'#'*60}")
        logger.info("# 阶段2: 中等长度对话 - 逐步接近阈值")
        logger.info(f"{'#'*60}")

        for user_input, assistant_response in medium_conversations:
            await self.simulate_conversation_round(user_input, assistant_response)

        # 阶段3：长对话（可能触发压缩）
        logger.info(f"\n{'#'*60}")
        logger.info("# 阶段3: 长对话 - 可能触发压缩")
        logger.info(f"{'#'*60}")

        for user_input, assistant_response in long_conversations:
            await self.simulate_conversation_round(user_input, assistant_response)

        # 阶段4：超长对话（必定触发压缩）
        logger.info(f"\n{'#'*60}")
        logger.info("# 阶段4: 超长对话 - 必定触发压缩")
        logger.info(f"{'#'*60}")

        await self.simulate_conversation_round("请详细介绍一下中国旅游景点的历史和文化", extra_long_content)
        await self.simulate_conversation_round("还想了解更多景点信息", extra_long_content)

        # 测试总结
        self._log_test_summary()

    def _log_test_summary(self):
        """输出测试总结"""
        logger.info(f"\n{'='*60}")
        logger.info("🎯 测试总结")
        logger.info(f"{'='*60}")

        stats = self.guard.get_stats()

        logger.info(f"总轮次: {self.test_stats['round']}")
        logger.info(f"总消息数: {self.test_stats['total_messages']}")
        logger.info(f"压缩触发轮次: {self.test_stats['compression_round'] or '未触发'}")
        logger.info(f"当前消息数: {len(self.test_stats['messages'])}")
        logger.info(f"当前tokens: {stats.get('current_tokens', 0)}")
        logger.info(f"窗口大小: {stats.get('window_size', 0)}")
        logger.info(f"压缩阈值: {stats.get('compress_threshold', 0):.1%}")

        logger.info(f"\n处理统计:")
        logger.info(f"  前置清理次数: {stats.get('pre_process_count', 0)}")
        logger.info(f"  后置处理次数: {stats.get('post_process_count', 0)}")
        logger.info(f"  压缩触发次数: {stats.get('compression_triggered_count', 0)}")
        logger.info(f"  强制压缩次数: {stats.get('force_compress_count', 0)}")

        logger.info(f"\n清理统计:")
        logger.info(f"  过期清理: {stats.get('total_expired_cleaned', 0)}")
        logger.info(f"  软修剪: {stats.get('total_trimmed', 0)}")
        logger.info(f"  硬清除: {stats.get('total_cleared', 0)}")

        # 验证结果
        self._verify_results()

    def _verify_results(self):
        """验证测试结果"""
        logger.info(f"\n✅ 验证结果:")

        # 检查压缩是否在预期时触发
        threshold_round = int(1 / (1 - self.config.compress_threshold)) + 1
        if self.test_stats['compression_triggered']:
            if self.test_stats['compression_round'] >= threshold_round - 2:
                logger.info(f"✅ 压缩在合适的时机触发（第{self.test_stats['compression_round']}轮）")
            else:
                logger.warning(f"⚠️ 压缩触发过早（第{self.test_stats['compression_round']}轮，预期约{threshold_round}轮）")
        else:
            if self.test_stats['round'] < threshold_round:
                logger.info(f"✅ 压缩未提前触发（当前{self.test_stats['round']}轮，阈值约{threshold_round}轮）")
            else:
                logger.warning(f"⚠️ 压缩应该触发但未触发")

        # 检查当前token是否在限制内
        stats = self.guard.get_stats()
        current_tokens = stats.get('current_tokens', 0)
        window_size = stats.get('window_size', self.config.window_size)

        if current_tokens <= window_size:
            logger.info(f"✅ Token数量在窗口限制内（{current_tokens}/{window_size}）")
        else:
            logger.warning(f"⚠️ Token数量超出窗口限制（{current_tokens}/{window_size}）")


async def main():
    """主测试函数"""
    # 运行测试（默认窗口4000，80%触发压缩）
    tester = ContextCompressionTester(window_size=4000, compress_threshold=0.8)
    await tester.run_comprehensive_test()

    # 可以调整参数进行不同场景的测试
    # tester = ContextCompressionTester(window_size=2000, compress_threshold=0.7)
    # await tester.run_comprehensive_test()


if __name__ == "__main__":
    asyncio.run(main())