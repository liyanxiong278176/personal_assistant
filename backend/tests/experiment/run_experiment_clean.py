"""LLM调用减少率实验 - 主执行脚本 (无emoji版本)

运行对照实验，比较纯LLM方案和三级分类器的LLM调用次数。
"""

import asyncio
import sys
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

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

from tests.experiment.pure_llm_classifier import PureLLMClassifier
from tests.experiment.three_tier_classifier import ThreeTierClassifier
from tests.experiment.data_collector import ExperimentDataCollector
from tests.experiment.generate_samples import SampleGenerator


class ExperimentRunner:
    """实验运行器"""

    def __init__(self, llm_client=None):
        """初始化实验运行器

        Args:
            llm_client: LLM客户端实例，如果为None则使用模拟模式
        """
        self.llm_client = llm_client

    async def run(
        self,
        samples: list,
        sample_size: Optional[int] = None
    ) -> ExperimentDataCollector:
        """运行实验

        Args:
            samples: 测试样本列表
            sample_size: 使用的样本数量，None表示全部

        Returns:
            ExperimentDataCollector: 收集的实验数据
        """
        if sample_size:
            samples = samples[:sample_size]

        logger.info(f"Starting experiment with {len(samples)} samples")

        # 初始化分类器
        control = PureLLMClassifier(self.llm_client)
        experiment = ThreeTierClassifier(self.llm_client)
        collector = ExperimentDataCollector()

        # 执行实验
        for i, sample in enumerate(samples):
            if (i + 1) % 50 == 0 or i == 0:
                logger.info(f"Progress: {i + 1}/{len(samples)}")

            message = sample["message"]
            expected = sample["intent"]
            sample_id = sample["id"]
            category = sample.get("category", "default")

            # 对照组分类
            control_result = await control.classify(message)

            # 实验组分类
            experiment_result = await experiment.classify(message)

            # 记录结果
            collector.add(
                sample_id=sample_id,
                message=message,
                expected=expected,
                control_result=control_result,
                experiment_result=experiment_result,
                category=category
            )

        logger.info("Experiment completed!")
        return collector

    def print_report(self, collector: ExperimentDataCollector):
        """打印实验报告"""
        metrics = collector.calculate_metrics()

        print("\n" + "=" * 70)
        print(" " * 20 + "LLM Reduction Rate Experiment Report")
        print("=" * 70)

        print(f"\n[Sample Info]")
        print(f"  Sample Size: {metrics['sample_size']}")
        print(f"  Execution Time: {metrics.get('elapsed_seconds', 0):.2f}s")

        print(f"\n[LLM Calls Comparison]")
        print(f"  Control Group Calls: {metrics['control']['llm_calls']}")
        print(f"  Experiment Group Calls: {metrics['experiment']['llm_calls']}")
        print(f"  Saved Calls: {metrics['reduction']['absolute_saved']}")
        print(f"  " + "-" * 50)
        print(f"  LLM Call Reduction Rate: {metrics['reduction']['rate']:.2%}")
        print(f"  " + "-" * 50)

        print(f"\n[Accuracy Comparison]")
        print(f"  Control Accuracy: {metrics['accuracy']['control']:.2%}")
        print(f"  Experiment Accuracy: {metrics['accuracy']['experiment']:.2%}")
        diff = metrics['accuracy']['difference']
        print(f"  Accuracy Difference: {diff:+.2%}")

        print(f"\n[Tier Hit Rates]")
        for tier, rate in metrics['tier_breakdown'].items():
            tier_name = {"cache": "Cache Layer", "rule": "Rule Layer", "llm": "LLM Fallback"}
            print(f"  {tier_name.get(tier, tier)}: {rate:.2%}")

        # 按意图类型统计
        print(f"\n[By Intent Type]")
        for intent, stats in sorted(metrics['by_intent'].items()):
            intent_name = {
                "itinerary": "Itinerary Planning",
                "query": "Info Query",
                "chat": "Chat",
                "hotel": "Hotel Booking",
                "food": "Food Recommendation",
                "budget": "Budget Planning",
                "transport": "Transport",
                "image": "Image Recognition"
            }.get(intent, intent)
            llm_rate = stats['llm_calls'] / stats['total'] if stats['total'] > 0 else 0
            print(f"  {intent_name}: LLM Call Rate {llm_rate:.1%} ({stats['llm_calls']}/{stats['total']})")

        # 按类别统计
        print(f"\n[By Sample Category]")
        for category, stats in sorted(metrics['by_category'].items()):
            llm_rate = stats['llm_calls'] / stats['total'] if stats['total'] > 0 else 0
            print(f"  {category}: LLM Call Rate {llm_rate:.1%} ({stats['llm_calls']}/{stats['total']})")

        # 结论
        print(f"\n[Conclusion]")
        reduction = metrics['reduction']['rate']
        accuracy_loss = metrics['accuracy']['difference']

        if reduction >= 0.6 and accuracy_loss <= 0.02:
            verdict = "[OK] Excellent - Three-tier classifier shows significant effect"
        elif reduction >= 0.4 and accuracy_loss <= 0.03:
            verdict = "[OK] Good - Has practical value"
        elif reduction >= 0.2 and accuracy_loss <= 0.05:
            verdict = "[WARN] Fair - Recommend optimizing keyword rules"
        else:
            verdict = "[FAIL] Needs Improvement - Effect below expectation"

        print(f"  {verdict}")

        # 统计显著性
        print(f"\n[Statistical Significance]")
        # 简化的配对t检验（假设每组样本独立）
        from math import sqrt
        n = metrics['sample_size']
        # 简化计算：使用二项分布近似
        control_rate = 1.0  # 对照组每次都调用
        experiment_rate = metrics['experiment']['avg_calls_per_sample']
        pooled_rate = (control_rate + experiment_rate) / 2
        se = sqrt(pooled_rate * (1 - pooled_rate) / n)
        z = (control_rate - experiment_rate) / se if se > 0 else 0
        # z > 1.96 表示 p < 0.05
        print(f"  Z-statistic: {z:.2f}")
        print(f"  Significant: {'Yes (p < 0.05)' if abs(z) >= 1.96 else 'No'}")

        print("\n" + "=" * 70)

        return metrics

    def save_report(
        self,
        collector: ExperimentDataCollector,
        output_dir: str = None
    ) -> str:
        """保存实验报告

        Returns:
            报告文件路径
        """
        if output_dir is None:
            output_dir = "tests/experiment/results"

        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # 保存JSON数据
        json_path = output_dir / f"experiment_{timestamp}.json"
        collector.save(str(json_path))

        # 保存Markdown报告
        md_path = output_dir / f"report_{timestamp}.md"
        self._save_markdown_report(collector, md_path)

        return str(md_path)

    def _save_markdown_report(self, collector: ExperimentDataCollector, filepath: Path):
        """保存Markdown报告"""
        metrics = collector.calculate_metrics()

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("# LLM Call Reduction Rate Experiment Report\n\n")
            f.write(f"**Generated**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Sample Size**: {metrics['sample_size']}\n\n")

            f.write("## 1. Core Results\n\n")
            reduction = metrics['reduction']['rate']
            f.write(f"- **LLM Call Reduction Rate**: **{reduction:.2%}**\n")
            f.write(f"- **Control Accuracy**: {metrics['accuracy']['control']:.2%}\n")
            f.write(f"- **Experiment Accuracy**: {metrics['accuracy']['experiment']:.2%}\n")
            f.write(f"- **Accuracy Difference**: {metrics['accuracy']['difference']:+.2%}\n\n")

            f.write("## 2. LLM Call Comparison\n\n")
            f.write("| Metric | Control | Experiment |\n")
            f.write("|--------|---------|-----------|\n")
            f.write(f"| LLM Calls | {metrics['control']['llm_calls']} | {metrics['experiment']['llm_calls']} |\n")
            f.write(f"| Avg Calls/Sample | {metrics['control']['avg_calls_per_sample']:.2f} | {metrics['experiment']['avg_calls_per_sample']:.2f} |\n\n")

            f.write("## 3. Tier Breakdown\n\n")
            f.write("| Tier | Rate |\n")
            f.write("|------|------|\n")
            tier_names = {"cache": "Cache Layer", "rule": "Rule Layer", "llm": "LLM Fallback"}
            for tier, rate in metrics['tier_breakdown'].items():
                f.write(f"| {tier_names.get(tier, tier)} | {rate:.2%} |\n")
            f.write("\n")

            f.write("## 4. Analysis by Intent Type\n\n")
            f.write("| Intent | Samples | LLM Calls | LLM Rate |\n")
            f.write("|--------|--------|-----------|----------|\n")
            for intent, stats in sorted(metrics['by_intent'].items()):
                llm_rate = stats['llm_calls'] / stats['total'] if stats['total'] > 0 else 0
                f.write(f"| {intent} | {stats['total']} | {stats['llm_calls']} | {llm_rate:.1%} |\n")
            f.write("\n")

            f.write("## 5. Error Analysis\n\n")
            misclassified = collector.get_misclassified()
            f.write(f"Misclassified samples: {len(misclassified)}\n\n")

            if misclassified:
                f.write("### Error Cases (Top 10)\n\n")
                for i, case in enumerate(misclassified[:10], 1):
                    f.write(f"{i}. **{case['sample_id']}**\n")
                    f.write(f"   - Input: {case['message'][:50]}...\n")
                    f.write(f"   - Expected: {case['expected']}, Predicted: {case['predicted']}\n")
                    f.write(f"   - Confidence: {case['confidence']:.2f}, Tier: {case['tier']}\n")
                    f.write(f"   - Category: {case['category']}\n\n")

        logger.info(f"Markdown report saved: {filepath}")


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="Run LLM Call Reduction Experiment")
    parser.add_argument("-n", "--sample-size", type=int, default=500, help="Sample count")
    parser.add_argument("--regenerate", action="store_true", help="Regenerate samples")
    parser.add_argument("--output", type=str, default="tests/experiment/results", help="Output directory")
    parser.add_argument("--mock", action="store_true", help="Use mock mode (no real LLM)")

    args = parser.parse_args()

    # 加载或生成样本
    if args.regenerate:
        print("[INFO] Regenerating samples...")
        samples = SampleGenerator.generate(total=args.sample_size)
        SampleGenerator.save(samples)
    else:
        samples = SampleGenerator.load()
        if args.sample_size and len(samples) > args.sample_size:
            samples = samples[:args.sample_size]

    # 添加缓存测试：将前15%的样本重复出现，模拟用户重复提问
    # 确保原始样本和重复样本成对出现，以便测试缓存
    cache_test_size = int(len(samples) * 0.15)
    cache_samples = samples[:cache_test_size]

    # 构建新的样本列表：非重复样本 + 成对的(原始,重复)
    non_cache_samples = samples[cache_test_size:]
    paired_samples = []

    for sample in cache_samples:
        # 先添加原始样本
        paired_samples.append(sample)
        # 紧接着添加重复样本
        duplicate = sample.copy()
        duplicate["id"] = f"{sample['id']}_repeat"
        duplicate["category"] = "cache_test"
        paired_samples.append(duplicate)

    # 重新组合：非缓存样本 + 成对样本
    samples = non_cache_samples + paired_samples
    original_count = len(non_cache_samples) + cache_test_size

    print(f"[INFO] Added {len(cache_samples)} duplicate samples for cache testing (paired)")
    print(f"[INFO] Total samples: {len(samples)} (original: {original_count}, duplicates: {len(cache_samples)})")

    # 初始化LLM客户端
    llm_client = None
    if not args.mock:
        try:
            from app.core.llm import LLMClient
            llm_client = LLMClient()
            print("[OK] Using real LLM client")
        except Exception as e:
            print(f"[WARN] LLM client init failed: {e}")
            print("[INFO] Using mock mode")
            args.mock = True

    # 运行实验
    runner = ExperimentRunner(llm_client)
    collector = await runner.run(samples)

    # 打印报告
    runner.print_report(collector)

    # 保存报告
    report_path = runner.save_report(collector, args.output)
    print(f"\n[OK] Report saved to: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
