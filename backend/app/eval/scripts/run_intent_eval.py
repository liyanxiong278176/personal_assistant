"""意图评估 CLI — python -m app.eval.scripts.run_intent_eval"""
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# 确保 backend 根目录在 sys.path 中
backend_root = Path(__file__).parent.parent.parent.parent
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from app.eval.evaluators import IntentEvaluator
from app.eval.storage import EvalStorage
from app.core.llm import LLMClient
from app.core.query_engine import QueryEngine


async def main():
    print("意图分类评估中...")

    # 初始化 LLM 和 QueryEngine
    llm = LLMClient()
    engine = QueryEngine(llm_client=llm)

    # 使用 IntentRouter 进行评估
    evaluator = IntentEvaluator(
        classifier=engine._intent_router,
        test_data_dir=Path(__file__).parent.parent / "test_data",
    )

    # 执行评估
    metrics = await evaluator.evaluate()
    print(evaluator.print_report(metrics))

    # 保存结果到数据库
    storage = EvalStorage()
    await storage.init_db()

    result = {
        "eval_type": "intent",
        "eval_name": "意图分类准确率",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "intent_total": metrics.total,
        "intent_correct": metrics.correct,
        "intent_accuracy": metrics.accuracy,
        "intent_basic_accuracy": metrics.basic_accuracy,
        "intent_edge_accuracy": metrics.edge_accuracy,
        "confusion_matrix": str(metrics.confusion),
        "detailed_results": json.dumps({
            "confusion_matrix": metrics.confusion,
            "basic_accuracy": metrics.basic_accuracy,
            "edge_accuracy": metrics.edge_accuracy,
            "total": metrics.total,
            "correct": metrics.correct,
        }),
    }

    await storage.save_evaluation_result(result)
    print("\n结果已保存到 eval.db")


if __name__ == "__main__":
    asyncio.run(main())
