"""Full 3-level evaluation: Cache → Rule → LLM fallback.

Uses httpx directly for LLM calls to avoid LLMClient network issues.

Usage:
    cd backend
    DEEPSEEK_API_KEY=xxx python -u -m eval.run_full_eval3
"""

import asyncio
import json
import os
import sys
import io
import time
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).parent.parent))

import httpx

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

INTENT_SYSTEM_PROMPT = """你是旅游助手意图分类专家。判断用户真实意图，避免误判为chat。

【关键规则】chat极为严格——只有问候、感谢、非旅游闲聊才算chat。
任何旅游相关问题（景点、住宿、交通、价格、天气）都不是chat！

【意图判定优先级】（按重要性排序）：
1. budget: 含"多少钱"、"花"、"够吗"、"预算"、"贵"、"便宜"、"省钱"
   例: "去大理玩三天要花多少钱" → budget (不是itinerary)

2. hotel: 含"酒店"、"住宿"、"房间"、"空调"、"暖气"、"水压"、"卫生间"、"干净"、"吵"
   例: "有空调吗" → hotel (不是chat)
   例: "标间的床可以拼吗" → hotel

3. transport: 含"怎么去"、"坐车"、"打车"、"地铁"、"高铁"、"飞机"、"班车"、"停车"
   例: "从机场怎么坐车到酒店" → transport

4. query: 含"天气"、"门票"、"排队"、"预约"、"开放时间"、"买票"、"累不累"、"值得"、"安全"
   例: "排队多久" → query (不是chat)
   例: "张家界爬山累不累" → query

5. food: 含"餐厅"、"小吃"、"火锅"、"烤鸭"、"肉夹馍"、"夜市"、"吃啥"、"好吃的"
   例: "哪家火锅最正宗" → food

6. itinerary: 含"规划"、"行程"、"路线"、"安排"、"几日游"、明确的目的地+游玩
   例: "帮我规划北京三日游" → itinerary

7. image: 含"照片"、"图片"、"识别"、"这是哪"

8. chat: 仅限问候("你好"、"在吗")、感谢("谢谢")、非旅游闲聊
   例: "你好" → chat
   例: "谢谢" → chat
   例: "有空调吗" → hotel (不是chat！)

【消歧规则】：
- 多关键词时，按优先级判断（budget > hotel > transport > query > food > itinerary）
- 口语化短句（<10字），根据核心意图词判断，不是chat

【返回格式】JSON: {"intent":"xxx","confidence":0.9}

【常见误判警示】：
✗ "有空调吗" → chat ✗ 应为hotel
✗ "排队多久" → chat ✗ 应为query
✗ "打车多少钱" → chat ✗ 应为transport或budget
✗ "玩三天要多少钱" → itinerary ✗ 应为budget
✓ "你好"、"谢谢"、"哈哈" → chat ✓ 正确"""


async def llm_classify(api_key: str, message: str, max_retries: int = 2) -> dict:
    """Direct LLM intent classification via httpx."""
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [
            {"role": "system", "content": INTENT_SYSTEM_PROMPT},
            {"role": "user", "content": message},
        ],
        "temperature": 0.1,
        "max_tokens": 100,
    }

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(DEEPSEEK_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                text = data["choices"][0]["message"]["content"].strip()
                if "```" in text:
                    text = text.split("```")[1]
                    if text.startswith("json"):
                        text = text[4:]
                    text = text.strip()
                result = json.loads(text)
                return {
                    "intent": result.get("intent", "chat"),
                    "confidence": min(1.0, max(0.0, result.get("confidence", 0.7))),
                    "method": "llm",
                    "reasoning": "",
                    "strategy": "LLMStrategy",
                }
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
            else:
                return {
                    "intent": "chat",
                    "confidence": 0.3,
                    "method": "llm_error",
                    "reasoning": str(e),
                    "strategy": "LLMStrategy",
                }
    return {"intent": "chat", "confidence": 0.3, "method": "llm_error", "reasoning": "", "strategy": "LLMStrategy"}


async def run_full_eval(cases_path: str, api_key: str):
    """Run 3-level evaluation: cache → rule → LLM."""
    with open(cases_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    cases = data["cases"]
    print(f"\n加载 {len(cases)} 条测试用例...")
    print(f"三级分类器: Cache → Rule → LLM\n")

    from app.core.intent import IntentRouter, RuleStrategy
    from app.core.intent.strategies.cache import CacheStrategy, ClassificationCache
    from app.core.context import RequestContext

    # Build rule-only router for first two levels
    classification_cache = ClassificationCache(max_size=1000)
    cache_strategy = CacheStrategy(cache=classification_cache)
    rule_strategy = RuleStrategy(max_confidence=0.85)
    router = IntentRouter(strategies=[cache_strategy, rule_strategy])

    # Metrics
    total = len(cases)
    correct = 0
    strategy_counts = Counter()
    latency_by_strategy = defaultdict(list)
    category_stats = defaultdict(lambda: {"correct": 0, "total": 0})
    intent_stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "total": 0, "correct": 0})
    errors = []
    confusion = defaultdict(lambda: defaultdict(int))

    llm_calls = 0
    llm_correct = 0

    for i, case in enumerate(cases):
        if (i + 1) % 100 == 0:
            print(f"  进度: {i+1}/{total}... (LLM调用: {llm_calls})", flush=True)

        start = time.perf_counter()
        ctx = RequestContext(message=case["query"])

        # Level 1+2: Cache → Rule
        rule_result = await router.classify(ctx)
        rule_confidence = rule_result.confidence
        rule_strategy_name = rule_result.strategy or rule_result.method or "RuleStrategy"

        # Level 3: LLM fallback for low/medium confidence
        if rule_confidence >= 0.8:
            # High confidence from cache/rule, accept
            predicted = rule_result.intent
            strategy = rule_strategy_name
            confidence = rule_confidence
        else:
            # Low/medium confidence, try LLM
            llm_result = await llm_classify(api_key, case["query"])
            llm_calls += 1
            predicted = llm_result["intent"]
            strategy = "LLMStrategy"
            confidence = llm_result["confidence"]

        latency_ms = (time.perf_counter() - start) * 1000
        expected = case["expected_intent"]
        is_correct = predicted == expected

        if is_correct:
            correct += 1
        else:
            errors.append({
                "case_id": case["id"],
                "query": case["query"],
                "expected": expected,
                "predicted": predicted,
                "strategy": strategy,
                "confidence": confidence,
                "category": case["category"],
            })

        # Update stats
        strategy_counts[strategy] += 1
        latency_by_strategy[strategy].append(latency_ms)
        category_stats[case["category"]]["total"] += 1
        if is_correct:
            category_stats[case["category"]]["correct"] += 1

        intent_stats[expected]["total"] += 1
        if is_correct:
            intent_stats[expected]["correct"] += 1
            intent_stats[expected]["tp"] += 1
        else:
            intent_stats[expected]["fn"] += 1
            intent_stats[predicted]["fp"] += 1

        confusion[expected][predicted] += 1

    # === Report ===
    accuracy = correct / total * 100
    print(f"\n{'='*70}")
    print(f"         三级分类器完整评估报告 (真实数据1000条)")
    print(f"{'='*70}")

    print(f"\n【总体指标】")
    print(f"  测试用例: {total} 条")
    print(f"  正确分类: {correct} 条")
    print(f"  整体准确率: {accuracy:.1f}%")

    print(f"\n【各意图 F1 分数】")
    print(f"  {'意图':12s} {'数量':>5s} {'准确率':>7s} {'精确率':>7s} {'召回率':>7s} {'F1':>7s}")
    print("  " + "-" * 50)
    for intent in sorted(intent_stats.keys()):
        s = intent_stats[intent]
        tp, fp, fn = s["tp"], s["fp"], s["fn"]
        prec = tp / (tp + fp) if (tp + fp) > 0 else 0
        rec = tp / (tp + fn) if (tp + fn) > 0 else 0
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
        acc = s["correct"] / s["total"] * 100 if s["total"] > 0 else 0
        print(f"  {intent:12s} {s['total']:5d} {acc:6.1f}% {prec:6.1%} {rec:6.1%} {f1:6.1%}")

    print(f"\n【频率分层准确率】")
    for cat in ["high_freq", "mid_freq", "low_freq"]:
        s = category_stats[cat]
        acc = s["correct"] / s["total"] * 100 if s["total"] > 0 else 0
        print(f"  {cat:12s} {s['total']:5d} {s['correct']:5d} {acc:6.1f}%")

    print(f"\n【策略分布】")
    no_llm = strategy_counts.get("CacheStrategy", 0) + strategy_counts.get("RuleStrategy", 0)
    llm_total = strategy_counts.get("LLMStrategy", 0)
    print(f"  Cache命中:      {strategy_counts.get('CacheStrategy', 0)}")
    print(f"  Rule命中:       {strategy_counts.get('RuleStrategy', 0)}")
    print(f"  LLM调用:       {llm_total}")
    print(f"  LLM减少率:     {no_llm/total*100:.1f}% (无需LLM的比例)")

    print(f"\n  平均延迟:")
    for strat, lats in latency_by_strategy.items():
        avg = sum(lats) / len(lats)
        print(f"    {strat}: {avg:.1f}ms")

    # High freq coverage
    hf = category_stats["high_freq"]
    hf_acc = hf["correct"] / hf["total"] * 100 if hf["total"] > 0 else 0
    print(f"\n【高频查询覆盖】")
    print(f"  准确率: {hf_acc:.1f}% {'✅' if hf_acc >= 80 else '❌'}")

    # Confusion top errors
    print(f"\n【混淆矩阵 - 前8错误】")
    error_pairs = []
    for exp, pred_map in confusion.items():
        for pred, count in pred_map.items():
            if exp != pred:
                error_pairs.append((exp, pred, count))
    error_pairs.sort(key=lambda x: -x[2])
    print(f"  {'期望':12s} -> {'实际':12s} {'次数':>5s}")
    print("  " + "-" * 35)
    for exp, pred, count in error_pairs[:8]:
        print(f"  {exp:12s} -> {pred:12s} {count:5d}")

    # Cost
    cost_per_llm = 0.001
    print(f"\n【成本估算】")
    print(f"  全LLM基线: ¥{total * cost_per_llm:.3f}")
    print(f"  实际成本:  ¥{llm_total * cost_per_llm:.3f}")
    print(f"  节省:     {(1 - llm_total/total)*100:.1f}%")

    print(f"\n{'='*70}")
    print(f"【面试指标】")
    print(f"  准确率: {accuracy:.1f}% (Cache+Rule+LLM三级)")
    print(f"  高频覆盖: {hf_acc:.1f}%")
    print(f"  LLM减少: {no_llm/total*100:.1f}%")
    print(f"  平均延迟: Rule {sum(latency_by_strategy.get('RuleStrategy', []))/max(1,len(latency_by_strategy.get('RuleStrategy', []))):.1f}ms / LLM {sum(latency_by_strategy.get('LLMStrategy', []))/max(1,len(latency_by_strategy.get('LLMStrategy', []))):.1f}ms")
    print(f"{'='*70}\n")

    # Save results
    output = {
        "summary": {
            "total": total, "correct": correct, "accuracy": accuracy,
            "strategy_distribution": dict(strategy_counts),
            "llm_reduction_pct": no_llm / total * 100,
            "high_freq_accuracy": hf_acc,
        },
        "errors": errors,
        "confusion_matrix": {k: dict(v) for k, v in confusion.items()},
    }
    out_path = Path(__file__).parent / "eval_results_3level.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    print(f"详细结果: {out_path}")


if __name__ == "__main__":
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("用法: DEEPSEEK_API_KEY=xxx python -u -m eval.run_full_eval3")
        sys.exit(1)
    asyncio.run(run_full_eval("eval/test_cases_real.json", api_key))
