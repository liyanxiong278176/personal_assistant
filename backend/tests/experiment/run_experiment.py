"""LLM调用减少率实验 - 主执行脚本

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

        logger.info(f"开始实验，样本量: {len(samples)}")

        # 初始化分类器
        control = PureLLMClassifier(self.llm_client)
        experiment = ThreeTierClassifier(self.llm_client)
        collector = ExperimentDataCollector()

        # 执行实验
        for i, sample in enumerate(samples):
            if (i + 1) % 50 == 0 or i == 0:
                logger.info(f"进度: {i + 1}/{len(samples)}")

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

        logger.info("实验完成!")
        return collector

    def print_report(self, collector: ExperimentDataCollector):
        """打印实验报告"""
        metrics = collector.calculate_metrics()

        print("\n" + "=" * 70)
        print(" " * 20 + "LLM调用减少率实验报告")
        print("=" * 70)

        print(f"\n📊 样本信息")
        print(f"  样本量: {metrics['sample_size']}")
        print(f"  执行时间: {metrics.get('elapsed_seconds', 0):.2f}秒")

        print(f"\n🔍 LLM调用对比")
        print(f"  对照组调用次数: {metrics['control']['llm_calls']}")
        print(f"  实验组调用次数: {metrics['experiment']['llm_calls']}")
        print(f"  节省调用次数: {metrics['reduction']['absolute_saved']}")
        print(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        print(f"  LLM调用减少率: {metrics['reduction']['percentage']}")
        print(f"  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        print(f"\n📈 准确性对比")
        print(f"  对照组准确率: {metrics['accuracy']['control']:.2%}")
        print(f"  实验组准确率: {metrics['accuracy']['experiment']:.2%}")
        diff = metrics['accuracy']['difference']
        print(f"  准确率差异: {diff:+.2%}")

        print(f"\n🎯 实验组分层命中情况")
        for tier, rate in metrics['tier_breakdown'].items():
            tier_name = {"cache": "缓存层", "rule": "关键词层", "llm": "LLM降层"}
            print(f"  {tier_name.get(tier, tier)}: {rate:.2%}")

        # 按意图类型统计
        print(f"\n📋 按意图类型统计")
        for intent, stats in sorted(metrics['by_intent'].items()):
            intent_name = {
                "itinerary": "行程规划",
                "query": "信息查询",
                "chat": "普通对话",
                "hotel": "酒店预订",
                "food": "美食推荐",
                "budget": "预算规划",
                "transport": "交通出行",
                "image": "图片识别"
            }.get(intent, intent)
            llm_rate = stats['llm_calls'] / stats['total'] if stats['total'] > 0 else 0
            print(f"  {intent_name}: LLM调用率 {llm_rate:.1%} ({stats['llm_calls']}/{stats['total']})")

        # 按类别统计
        print(f"\n📁 按样本类别统计")
        for category, stats in sorted(metrics['by_category'].items()):
            llm_rate = stats['llm_calls'] / stats['total'] if stats['total'] > 0 else 0
            print(f"  {category}: LLM调用率 {llm_rate:.1%} ({stats['llm_calls']}/{stats['total']})")

        # 结论
        print(f"\n🎯 实验结论")
        reduction = metrics['reduction']['rate']
        accuracy_loss = metrics['accuracy']['difference']

        if reduction >= 0.6 and accuracy_loss <= 0.02:
            verdict = "✅ 优秀 - 三级分类器效果显著，准确率损失可接受"
        elif reduction >= 0.4 and accuracy_loss <= 0.03:
            verdict = "✅ 良好 - 有实际应用价值"
        elif reduction >= 0.2 and accuracy_loss <= 0.05:
            verdict = "⚠️ 一般 - 建议优化关键词规则"
        else:
            verdict = "❌ 需要改进 - 效果不达预期"

        print(f"  {verdict}")

        # 统计显著性
        print(f"\n📊 统计显著性")
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
        print(f"  Z统计量: {z:.2f}")
        print(f"  显著性: {'是 (p < 0.05)' if abs(z) >= 1.96 else '否'}")

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

        # 保存文本报告
        report_path = output_dir / f"report_{timestamp}.txt"
        self._save_text_report(collector, report_path)

        # 保存Markdown报告
        md_path = output_dir / f"report_{timestamp}.md"
        self._save_markdown_report(collector, md_path)

        return str(md_path)

    def _save_text_report(self, collector: ExperimentDataCollector, filepath: Path):
        """保存文本报告"""
        metrics = collector.calculate_metrics()

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("LLM调用减少率实验报告\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"样本量: {metrics['sample_size']}\n\n")

            f.write("一、LLM调用对比\n")
            f.write("-" * 40 + "\n")
            f.write(f"对照组调用次数: {metrics['control']['llm_calls']}\n")
            f.write(f"实验组调用次数: {metrics['experiment']['llm_calls']}\n")
            f.write(f"减少率: {metrics['reduction']['percentage']}\n\n")

            f.write("二、准确性对比\n")
            f.write("-" * 40 + "\n")
            f.write(f"对照组准确率: {metrics['accuracy']['control']:.2%}\n")
            f.write(f"实验组准确率: {metrics['accuracy']['experiment']:.2%}\n")
            f.write(f"差异: {metrics['accuracy']['difference']:+.2%}\n\n")

            f.write("三、分层命中情况\n")
            f.write("-" * 40 + "\n")
            for tier, rate in metrics['tier_breakdown'].items():
                f.write(f"{tier}: {rate:.2%}\n")

        logger.info(f"文本报告已保存: {filepath}")

    def _save_markdown_report(self, collector: ExperimentDataCollector, filepath: Path):
        """保存Markdown报告"""
        metrics = collector.calculate_metrics()

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write("# LLM调用减少率实验报告\n\n")
            f.write(f"**生成时间**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**样本量**: {metrics['sample_size']}\n\n")

            f.write("## 一、核心结论\n\n")
            reduction = metrics['reduction']['rate']
            f.write(f"- **LLM调用减少率**: **{metrics['reduction']['percentage']}**\n")
            f.write(f"- **对照组准确率**: {metrics['accuracy']['control']:.2%}\n")
            f.write(f"- **实验组准确率**: {metrics['accuracy']['experiment']:.2%}\n")
            f.write(f"- **准确率损失**: {metrics['accuracy']['difference']:+.2%}\n\n")

            f.write("## 二、LLM调用对比\n\n")
            f.write("| 指标 | 对照组 | 实验组 |\n")
            f.write("|------|--------|--------|\n")
            f.write(f"| LLM调用次数 | {metrics['control']['llm_calls']} | {metrics['experiment']['llm_calls']} |\n")
            f.write(f"| 平均每样本调用 | {metrics['control']['avg_calls_per_sample']:.2f} | {metrics['experiment']['avg_calls_per_sample']:.2f} |\n\n")

            f.write("## 三、分层命中情况\n\n")
            f.write("| 层级 | 占比 |\n")
            f.write("|------|------|\n")
            tier_names = {"cache": "缓存层", "rule": "关键词层", "llm": "LLM降级"}
            for tier, rate in metrics['tier_breakdown'].items():
                f.write(f"| {tier_names.get(tier, tier)} | {rate:.2%} |\n")
            f.write("\n")

            f.write("## 四、按意图类型分析\n\n")
            f.write("| 意图类型 | 样本数 | LLM调用次数 | LLM调用率 |\n")
            f.write("|----------|--------|-------------|-----------|\n")
            for intent, stats in sorted(metrics['by_intent'].items()):
                llm_rate = stats['llm_calls'] / stats['total'] if stats['total'] > 0 else 0
                f.write(f"| {intent} | {stats['total']} | {stats['llm_calls']} | {llm_rate:.1%} |\n")
            f.write("\n")

            f.write("## 五、错误分析\n\n")
            misclassified = collector.get_misclassified()
            f.write(f"错误分类样本数: {len(misclassified)}\n\n")

            if misclassified:
                f.write("### 错误案例（前10个）\n\n")
                for i, case in enumerate(misclassified[:10], 1):
                    f.write(f"{i}. **{case['sample_id']}**\n")
                    f.write(f"   - 输入: {case['message'][:50]}...\n")
                    f.write(f"   - 期望: {case['expected']}, 预测: {case['predicted']}\n")
                    f.write(f"   - 置信度: {case['confidence']:.2f}, 层级: {case['tier']}\n")
                    f.write(f"   - 类别: {case['category']}\n\n")

        logger.info(f"Markdown报告已保存: {filepath}")


async def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description="运行LLM调用减少率实验")
    parser.add_argument("-n", "--sample-size", type=int, default=500, help="样本数量")
    parser.add_argument("--regenerate", action="store_true", help="重新生成样本")
    parser.add_argument("--output", type=str, default="tests/experiment/results", help="输出目录")
    parser.add_argument("--mock", action="store_true", help="使用模拟模式（不调用真实LLM）")

    args = parser.parse_args()

    # 加载或生成样本
    if args.regenerate:
        print("🔄 重新生成样本...")
        samples = SampleGenerator.generate(total=args.sample_size)
        SampleGenerator.save(samples)
    else:
        samples = SampleGenerator.load()
        if args.sample_size and len(samples) > args.sample_size:
            samples = samples[:args.sample_size]

    # 初始化LLM客户端
    llm_client = None
    if not args.mock:
        try:
            from app.core.llm import LLMClient
            llm_client = LLMClient()
            print("✅ 使用真实LLM客户端")
        except Exception as e:
            print(f"⚠️ LLM客户端初始化失败: {e}")
            print("💡 使用模拟模式继续实验")
            args.mock = True

    # 运行实验
    runner = ExperimentRunner(llm_client)
    collector = await runner.run(samples)

    # 打印报告
    runner.print_report(collector)

    # 保存报告
    report_path = runner.save_report(collector, args.output)
    print(f"\n✅ 报告已保存到: {report_path}")


if __name__ == "__main__":
    asyncio.run(main())
