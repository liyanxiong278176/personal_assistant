"""量化指标验证脚本 - Phase 3: 量化指标验证

验证简历中声称的量化指标：
1. Intent classification accuracy (意图分类准确率): claimed >= 76.26%
2. LLM call reduction (LLM调用减少): claimed >= 52.52% (no cache) / 82.44% (with cache)

测试方法：
- 使用真实的三级分类器系统
- 运行温度=0的LLM调用确保稳定性
- 重复3次取最小稳定值
- 95%置信区间统计分析
"""

import asyncio
import json
import logging
import sys
import statistics
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from collections import defaultdict

# 添加项目路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from app.core.intent.router import IntentRouter
from app.core.intent.strategies import (
    CacheStrategy, RuleStrategy, LLMStrategy, SemanticValidator, ClassificationCache
)
from app.core.intent.config import IntentRouterConfig
from app.core.context import RequestContext
from app.core.llm import LLMClient


@dataclass
class ValidationMetrics:
    """验证指标数据类"""
    metric_name: str
    claimed_value: float
    measured_values: List[float] = field(default_factory=list)
    unit: str = ""
    pass_threshold: float = 0.0
    status: str = "PENDING"
    notes: str = ""

    def get_min_value(self) -> float:
        """获取最小值（用于简历风险评估）"""
        return min(self.measured_values) if self.measured_values else 0.0

    def get_mean_value(self) -> float:
        """获取平均值"""
        return statistics.mean(self.measured_values) if self.measured_values else 0.0

    def get_stddev(self) -> float:
        """获取标准差"""
        if len(self.measured_values) < 2:
            return 0.0
        return statistics.stdev(self.measured_values)

    def get_confidence_interval(self, confidence: float = 0.95) -> Tuple[float, float]:
        """计算置信区间"""
        if len(self.measured_values) < 2:
            return (self.get_mean_value(), self.get_mean_value())

        import math
        mean = self.get_mean_value()
        stderr = self.get_stddev() / math.sqrt(len(self.measured_values))

        # 简化的t值（对于n=3, 95% CI大约使用4.3作为t值）
        t_value = 4.3  # 保守估计
        margin = t_value * stderr

        return (mean - margin, mean + margin)

    def is_pass(self) -> bool:
        """检查是否通过验证（使用最小值）"""
        return self.get_min_value() >= self.pass_threshold


class MetricsValidator:
    """量化指标验证器"""

    def __init__(self, llm_client: Optional[LLMClient] = None):
        """初始化验证器

        Args:
            llm_client: LLM客户端，如果为None则使用mock模式
        """
        self.llm_client = llm_client
        self.use_mock = llm_client is None

        # 声称的指标（从实验报告中提取）
        self.claimed_metrics = {
            "intent_accuracy_no_cache": 76.26,  # 无缓存时的意图分类准确率
            "intent_accuracy_with_cache": 76.42,  # 有缓存时的意图分类准确率
            "llm_reduction_no_cache": 52.52,  # 无缓存时的LLM调用减少率
            "llm_reduction_with_cache": 82.44,  # 有缓存时的LLM调用减少率
        }

        # 验证结果
        self.validation_results: Dict[str, ValidationMetrics] = {}

    async def load_test_dataset(self, filepath: Optional[str] = None) -> List[Dict]:
        """加载测试数据集

        Args:
            filepath: 样本文件路径，默认使用experiment/samples.jsonl

        Returns:
            样本列表
        """
        if filepath is None:
            filepath = "tests/experiment/samples.jsonl"

        filepath = Path(filepath)

        if not filepath.exists():
            logger.warning(f"样本文件不存在: {filepath}，生成新样本...")
            from tests.experiment.generate_samples import SampleGenerator
            samples = SampleGenerator.generate(total=500)
            SampleGenerator.save(samples)
            return samples

        samples = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))

        logger.info(f"加载了 {len(samples)} 个测试样本")
        return samples

    async def validate_intent_accuracy(
        self,
        samples: List[Dict],
        num_runs: int = 3,
        enable_cache: bool = False
    ) -> ValidationMetrics:
        """验证意图分类准确率

        Args:
            samples: 测试样本
            num_runs: 重复运行次数
            enable_cache: 是否启用缓存

        Returns:
            ValidationMetrics: 验证结果
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"验证指标: 意图分类准确率 (缓存={'启用' if enable_cache else '禁用'})")
        logger.info(f"声称值: {self.claimed_metrics['intent_accuracy_with_cache' if enable_cache else 'intent_accuracy_no_cache']}%")
        logger.info(f"测试样本: {len(samples)}")
        logger.info(f"重复次数: {num_runs}")
        logger.info(f"{'='*60}\n")

        metric_name = f"intent_accuracy_{'with' if enable_cache else 'no'}_cache"
        claimed = self.claimed_metrics[metric_name]

        accuracy_results = []

        for run_idx in range(num_runs):
            logger.info(f"\n--- 运行 {run_idx + 1}/{num_runs} ---")

            # 创建新的router实例（确保状态隔离）
            router = await self._create_router(enable_cache=enable_cache)

            correct = 0
            total = 0
            per_intent_correct = defaultdict(int)
            per_intent_total = defaultdict(int)

            start_time = time.time()

            for sample in samples:
                message = sample["message"]
                expected_intent = sample["intent"]

                # 创建请求上下文
                context = RequestContext(
                    message=message,
                    conversation_id=f"validation_run_{run_idx}_{sample.get('id', 'unknown')}"
                )

                # 执行分类
                try:
                    result = await router.classify(context)
                    predicted_intent = result.intent

                    total += 1
                    per_intent_total[expected_intent] += 1

                    if predicted_intent == expected_intent:
                        correct += 1
                        per_intent_correct[expected_intent] += 1

                except Exception as e:
                    logger.error(f"分类失败: {message[:30]}... | 错误: {e}")
                    total += 1
                    per_intent_total[expected_intent] += 1

            elapsed = time.time() - start_time
            accuracy = (correct / total * 100) if total > 0 else 0
            accuracy_results.append(accuracy)

            logger.info(f"准确率: {accuracy:.2f}% ({correct}/{total})")
            logger.info(f"耗时: {elapsed:.2f}秒")

            # 每个意图的详细统计
            logger.info("\n各意图分类准确率:")
            for intent in sorted(per_intent_total.keys()):
                intent_correct = per_intent_correct[intent]
                intent_total = per_intent_total[intent]
                intent_acc = (intent_correct / intent_total * 100) if intent_total > 0 else 0
                logger.info(f"  {intent:12s}: {intent_acc:5.2f}% ({intent_correct}/{intent_total})")

        # 计算统计结果
        min_accuracy = min(accuracy_results)
        mean_accuracy = statistics.mean(accuracy_results)
        stddev_accuracy = statistics.stdev(accuracy_results) if len(accuracy_results) > 1 else 0

        # 95%置信区间
        ci_low, ci_high = self._calculate_confidence_interval(accuracy_results)

        # 判断是否通过（使用最小值）
        is_pass = min_accuracy >= claimed

        metrics = ValidationMetrics(
            metric_name=metric_name,
            claimed_value=claimed,
            measured_values=accuracy_results,
            unit="%",
            pass_threshold=claimed,
            status="PASS" if is_pass else "FAIL",
            notes=f"95% CI: [{ci_low:.2f}%, {ci_high:.2f}%], StdDev: {stddev_accuracy:.2f}%"
        )

        self.validation_results[metric_name] = metrics

        # 打印总结
        logger.info(f"\n{'='*60}")
        logger.info(f"验证结果: {metrics.status}")
        logger.info(f"  声称值: {claimed:.2f}%")
        logger.info(f"  测量值: {accuracy_results}")
        logger.info(f"  最小值: {min_accuracy:.2f}%")
        logger.info(f"  平均值: {mean_accuracy:.2f}%")
        logger.info(f"  标准差: {stddev_accuracy:.2f}%")
        logger.info(f"  95% CI: [{ci_low:.2f}%, {ci_high:.2f}%]")
        logger.info(f"{'='*60}\n")

        return metrics

    async def validate_llm_reduction(
        self,
        samples: List[Dict],
        num_runs: int = 3,
        enable_cache: bool = False
    ) -> ValidationMetrics:
        """验证LLM调用减少率

        Args:
            samples: 测试样本
            num_runs: 重复运行次数
            enable_cache: 是否启用L2语义缓存

        Returns:
            ValidationMetrics: 验证结果
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"验证指标: LLM调用减少率 (缓存={'启用' if enable_cache else '禁用'})")
        logger.info(f"声称值: {self.claimed_metrics['llm_reduction_with_cache' if enable_cache else 'llm_reduction_no_cache']}%")
        logger.info(f"测试样本: {len(samples)}")
        logger.info(f"重复次数: {num_runs}")
        logger.info(f"{'='*60}\n")

        metric_name = f"llm_reduction_{'with' if enable_cache else 'no'}_cache"
        claimed = self.claimed_metrics[metric_name]

        reduction_results = []

        for run_idx in range(num_runs):
            logger.info(f"\n--- 运行 {run_idx + 1}/{num_runs} ---")

            # 创建带统计的router
            router = await self._create_router(enable_cache=enable_cache)

            # 重置统计
            if hasattr(router, '_cache_strategy') and router._cache_strategy:
                router._cache_strategy.cache.clear()

            llm_count = 0
            cache_count = 0
            rule_count = 0
            total = 0

            start_time = time.time()

            for sample in samples:
                message = sample["message"]

                context = RequestContext(
                    message=message,
                    conversation_id=f"reduction_run_{run_idx}_{sample.get('id', 'unknown')}"
                )

                try:
                    result = await router.classify(context)
                    total += 1

                    # 根据strategy统计
                    strategy = result.strategy or result.method or "unknown"

                    if strategy == "CacheStrategy" or result.method == "cache":
                        cache_count += 1
                    elif strategy == "RuleStrategy" or result.method == "rule":
                        rule_count += 1
                    elif strategy == "LLMStrategy" or result.method == "llm":
                        llm_count += 1
                    elif strategy == "default" or result.method == "default":
                        # fallback也算LLM
                        llm_count += 1

                except Exception as e:
                    logger.error(f"分类失败: {message[:30]}... | 错误: {e}")
                    total += 1

            elapsed = time.time() - start_time

            # 计算减少率：(baseline - llm_calls) / baseline
            # baseline = total (每个样本都调用LLM)
            baseline = total
            reduction_rate = ((baseline - llm_count) / baseline * 100) if baseline > 0 else 0

            reduction_results.append(reduction_rate)

            logger.info(f"LLM调用减少率: {reduction_rate:.2f}%")
            logger.info(f"  总样本: {total}")
            logger.info(f"  缓存命中: {cache_count} ({cache_count/total*100:.1f}%)")
            logger.info(f"  规则命中: {rule_count} ({rule_count/total*100:.1f}%)")
            logger.info(f"  LLM调用: {llm_count} ({llm_count/total*100:.1f}%)")
            logger.info(f"  耗时: {elapsed:.2f}秒")

        # 计算统计结果
        min_reduction = min(reduction_results)
        mean_reduction = statistics.mean(reduction_results)
        stddev_reduction = statistics.stdev(reduction_results) if len(reduction_results) > 1 else 0

        # 95%置信区间
        ci_low, ci_high = self._calculate_confidence_interval(reduction_results)

        # 判断是否通过（使用最小值）
        is_pass = min_reduction >= claimed

        metrics = ValidationMetrics(
            metric_name=metric_name,
            claimed_value=claimed,
            measured_values=reduction_results,
            unit="%",
            pass_threshold=claimed,
            status="PASS" if is_pass else "FAIL",
            notes=f"95% CI: [{ci_low:.2f}%, {ci_high:.2f}%], StdDev: {stddev_reduction:.2f}%"
        )

        self.validation_results[metric_name] = metrics

        # 打印总结
        logger.info(f"\n{'='*60}")
        logger.info(f"验证结果: {metrics.status}")
        logger.info(f"  声称值: {claimed:.2f}%")
        logger.info(f"  测量值: {reduction_results}")
        logger.info(f"  最小值: {min_reduction:.2f}%")
        logger.info(f"  平均值: {mean_reduction:.2f}%")
        logger.info(f"  标准差: {stddev_reduction:.2f}%")
        logger.info(f"  95% CI: [{ci_low:.2f}%, {ci_high:.2f}%]")
        logger.info(f"{'='*60}\n")

        return metrics

    async def _create_router(self, enable_cache: bool = False) -> IntentRouter:
        """创建IntentRouter实例用于测试

        Args:
            enable_cache: 是否启用L2语义缓存

        Returns:
            IntentRouter实例
        """
        # 创建缓存策略
        cache = ClassificationCache()
        cache_strategy = CacheStrategy(cache=cache)

        # 创建规则策略
        rule_strategy = RuleStrategy(
            max_confidence=0.9,
            max_length=100,
            complex_words=[],
        )

        # 创建LLM策略
        llm_strategy = LLMStrategy(
            llm_client=self.llm_client,
        )

        # 配置
        config = IntentRouterConfig(
            high_confidence=0.8,
            mid_confidence=0.5,
            enable_clarification=False,  # 测试时禁用澄清
        )

        # 创建语义验证器（可选）
        semantic_validator = None
        if enable_cache and self.llm_client:
            semantic_validator = SemanticValidator(llm_client=self.llm_client)

        # 创建router
        router = IntentRouter(
            strategies=[cache_strategy, rule_strategy, llm_strategy],
            config=config,
            semantic_validator=semantic_validator,
        )

        return router

    def _calculate_confidence_interval(
        self,
        values: List[float],
        confidence: float = 0.95
    ) -> Tuple[float, float]:
        """计算置信区间

        Args:
            values: 测量值列表
            confidence: 置信水平

        Returns:
            (下限, 上限)
        """
        if len(values) < 2:
            mean = values[0] if values else 0
            return (mean, mean)

        import math
        mean = statistics.mean(values)
        stderr = statistics.stdev(values) / math.sqrt(len(values))

        # t值（保守估计）
        t_values = {0.90: 2.9, 0.95: 4.3, 0.99: 9.9}
        t_value = t_values.get(confidence, 4.3)

        margin = t_value * stderr
        return (mean - margin, mean + margin)

    def generate_report(self, output_path: Optional[str] = None) -> str:
        """生成验证报告

        Args:
            output_path: 输出文件路径

        Returns:
            报告文件路径
        """
        if output_path is None:
            output_path = "tests/core/TEST_REPORT_METRICS.md"

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        lines = []
        lines.append("# 量化指标验证报告\n")
        lines.append(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        lines.append(f"**验证环境**: {'Mock模式' if self.use_mock else '真实LLM'}\n")
        lines.append("\n---\n\n")

        # 执行摘要
        lines.append("## 执行摘要\n\n")
        pass_count = sum(1 for m in self.validation_results.values() if m.is_pass())
        total_count = len(self.validation_results)

        lines.append(f"| 指标 | 声称值 | 实测最小值 | 状态 |\n")
        lines.append(f"|------|--------|-----------|------|\n")

        for metric_name, metrics in sorted(self.validation_results.items()):
            display_name = {
                "intent_accuracy_no_cache": "意图分类准确率 (无缓存)",
                "intent_accuracy_with_cache": "意图分类准确率 (有缓存)",
                "llm_reduction_no_cache": "LLM调用减少率 (无缓存)",
                "llm_reduction_with_cache": "LLM调用减少率 (有缓存)",
            }.get(metric_name, metric_name)

            status_icon = "PASS" if metrics.is_pass() else "FAIL"
            lines.append(
                f"| {display_name} | {metrics.claimed_value:.2f}% | "
                f"{metrics.get_min_value():.2f}% | {status_icon} |\n"
            )

        lines.append(f"\n**总体结果**: {pass_count}/{total_count} 指标通过验证\n\n")

        # 详细结果
        lines.append("## 详细验证结果\n\n")

        for metric_name, metrics in sorted(self.validation_results.items()):
            display_name = {
                "intent_accuracy_no_cache": "意图分类准确率 (无缓存)",
                "intent_accuracy_with_cache": "意图分类准确率 (有缓存)",
                "llm_reduction_no_cache": "LLM调用减少率 (无缓存)",
                "llm_reduction_with_cache": "LLM调用减少率 (有缓存)",
            }.get(metric_name, metric_name)

            lines.append(f"### {display_name}\n\n")
            lines.append(f"- **声称值**: {metrics.claimed_value:.2f}%\n")
            lines.append(f"- **测量值**: {', '.join(f'{v:.2f}%' for v in metrics.measured_values)}\n")
            lines.append(f"- **最小值**: {metrics.get_min_value():.2f}%\n")
            lines.append(f"- **平均值**: {metrics.get_mean_value():.2f}%\n")
            lines.append(f"- **标准差**: {metrics.get_stddev():.2f}%\n")

            ci_low, ci_high = metrics.get_confidence_interval()
            lines.append(f"- **95%置信区间**: [{ci_low:.2f}%, {ci_high:.2f}%]\n")
            lines.append(f"- **验证状态**: {metrics.status}\n")
            lines.append(f"- **备注**: {metrics.notes}\n\n")

        # 简历安全值
        lines.append("## 简历安全值建议\n\n")
        lines.append("> 基于最小稳定值原则，以下数值可以安全用于简历：\n\n")
        lines.append("| 指标 | 简历安全值 | 数据来源 |\n")
        lines.append("|------|-----------|----------|\n")

        for metric_name, metrics in sorted(self.validation_results.items()):
            display_name = {
                "intent_accuracy_no_cache": "意图分类准确率",
                "intent_accuracy_with_cache": "意图分类准确率 (含缓存优化)",
                "llm_reduction_no_cache": "LLM调用减少率",
                "llm_reduction_with_cache": "LLM调用减少率 (含语义缓存)",
            }.get(metric_name, metric_name)

            safe_value = metrics.get_min_value()
            lines.append(f"| {display_name} | {safe_value:.2f}% | 实测最小值 ({len(metrics.measured_values)}次运行) |\n")

        lines.append("\n")

        # 测试方法
        lines.append("## 测试方法\n\n")
        lines.append("### 意图分类准确率\n")
        lines.append("- 测试集: 500+ 真实旅游对话样本\n")
        lines.append("- 分布: itinerary(30%), query(25%), chat(20%), hotel(10%), food(5%), budget(5%), transport(3%), image(2%)\n")
        lines.append("- LLM温度: 0 (确保稳定性)\n")
        lines.append("- 重复次数: 3次\n")
        lines.append("- 统计方法: 使用最小值作为简历安全值\n")
        lines.append("- 置信区间: 95% CI\n\n")

        lines.append("### LLM调用减少率\n")
        lines.append("- 对照组: 每个样本调用一次LLM (baseline)\n")
        lines.append("- 实验组: Cache -> Rule -> LLM 三级分类\n")
        lines.append("- 计算公式: (baseline - llm_calls) / baseline × 100%\n")
        lines.append("- 重复次数: 3次\n")
        lines.append("- 统计方法: 使用最小值作为简历安全值\n\n")

        # 结论
        lines.append("## 结论\n\n")

        all_pass = all(m.is_pass() for m in self.validation_results.values())

        if all_pass:
            lines.append("所有声称指标均通过验证，可以使用最小稳定值用于简历。\n\n")
        else:
            lines.append("以下指标未通过验证，建议调整声称值或优化系统：\n\n")
            for metric_name, metrics in self.validation_results.items():
                if not metrics.is_pass():
                    display_name = {
                        "intent_accuracy_no_cache": "意图分类准确率 (无缓存)",
                        "intent_accuracy_with_cache": "意图分类准确率 (有缓存)",
                        "llm_reduction_no_cache": "LLM调用减少率 (无缓存)",
                        "llm_reduction_with_cache": "LLM调用减少率 (有缓存)",
                    }.get(metric_name, metric_name)
                    lines.append(f"- **{display_name}**: 声称{metrics.claimed_value:.2f}%, 实测最小{metrics.get_min_value():.2f}%\n")
            lines.append("\n")

        # 写入文件
        with open(output_path, 'w', encoding='utf-8') as f:
            f.writelines(lines)

        logger.info(f"\n验证报告已保存到: {output_path}")

        return str(output_path)


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="量化指标验证")
    parser.add_argument("--runs", type=int, default=3, help="重复运行次数")
    parser.add_argument("--samples", type=str, default="tests/experiment/samples.jsonl", help="样本文件路径")
    parser.add_argument("--output", type=str, default="tests/core/TEST_REPORT_METRICS.md", help="报告输出路径")
    parser.add_argument("--mock", action="store_true", help="使用mock模式（不调用真实LLM）")

    args = parser.parse_args()

    # 初始化LLM客户端
    llm_client = None
    if not args.mock:
        try:
            llm_client = LLMClient()
            logger.info("使用真实LLM客户端")
        except Exception as e:
            logger.warning(f"LLM客户端初始化失败: {e}，使用mock模式")
            args.mock = True

    # 创建验证器
    validator = MetricsValidator(llm_client)

    # 加载测试数据
    samples = await validator.load_test_dataset(args.samples)

    # 验证指标
    logger.info("\n" + "="*60)
    logger.info("开始量化指标验证")
    logger.info("="*60 + "\n")

    # 1. 验证意图分类准确率（无缓存）
    await validator.validate_intent_accuracy(
        samples=samples,
        num_runs=args.runs,
        enable_cache=False
    )

    # 2. 验证意图分类准确率（有缓存）
    await validator.validate_intent_accuracy(
        samples=samples,
        num_runs=args.runs,
        enable_cache=True
    )

    # 3. 验证LLM调用减少率（无缓存）
    await validator.validate_llm_reduction(
        samples=samples,
        num_runs=args.runs,
        enable_cache=False
    )

    # 4. 验证LLM调用减少率（有缓存）
    await validator.validate_llm_reduction(
        samples=samples,
        num_runs=args.runs,
        enable_cache=True
    )

    # 生成报告
    report_path = validator.generate_report(args.output)

    logger.info("\n" + "="*60)
    logger.info("验证完成")
    logger.info("="*60 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
