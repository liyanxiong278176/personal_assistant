"""Token 评估 CLI — python -m app.eval.scripts.run_token_eval"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保 backend 根目录在 sys.path 中
backend_root = Path(__file__).parent.parent.parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.eval.evaluators import TokenEvaluator
from app.eval.storage import EvalStorage


async def main():
    import argparse

    parser = argparse.ArgumentParser(description="Token 成本评估器")
    parser.add_argument(
        "--days", "-d",
        type=int,
        default=7,
        help="分析最近几天的数据 (默认: 7)"
    )
    parser.add_argument(
        "--db-path",
        type=str,
        default="data/eval.db",
        help="数据库路径 (默认: data/eval.db)"
    )
    args = parser.parse_args()

    print(f"Token 成本评估中... (最近 {args.days} 天)")

    # 初始化存储和评估器
    storage = EvalStorage(db_path=args.db_path)
    await storage.init_db()

    evaluator = TokenEvaluator(storage=storage)

    # 执行评估
    metrics = await evaluator.evaluate(days=args.days)
    print(evaluator.print_report(metrics))

    # 保存结果到数据库
    result = {
        "trace_id": f"token_eval_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}",
        "eval_type": "token",
        "eval_name": "Token 成本压缩率",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "total_trajectories": metrics.total,
        "compressed_trajectories": metrics.correct,
        "avg_tokens_before": metrics.avg_before,
        "avg_tokens_after": metrics.avg_after,
        "reduction_rate": metrics.reduction_rate,
        "overflow_count": metrics.overflow_count,
        "score": metrics.reduction_rate,  # 使用压缩率作为分数
        "passed": metrics.reduction_rate > 0.1,  # 压缩率 > 10% 视为通过
        "by_intent": metrics.by_intent,
    }

    await storage.save_evaluation_result(result)
    print("\n结果已保存到 eval.db")

    # 返回退出码
    if metrics.reduction_rate < 0:
        return 1  # 压缩率为负表示有问题
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
