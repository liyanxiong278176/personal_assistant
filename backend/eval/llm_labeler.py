"""Label and augment travel queries using DeepSeek API directly.

Calls DeepSeek API via httpx (no LLMClient dependency).
Outputs labeled_queries.json with 1000 cases.

Usage:
    cd backend
    DEEPSEEK_API_KEY=xxx python -u -m eval.llm_labeler
"""

import asyncio
import json
import os
import sys
import io
import random
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import httpx

DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"
INTENTS = ["itinerary", "query", "hotel", "food", "budget", "transport", "chat", "image"]

PERSONAS = [
    "大学生（学生党，预算有限，喜欢穷游和打卡网红景点）",
    "亲子游家长（带3-10岁孩子，关注安全和亲子设施）",
    "情侣/新婚（蜜月旅行，关注浪漫景点和高品质住宿）",
    "商务出差（工作间隙短途游，关注效率和交通便利）",
    "���发族（60岁以上退休旅行，关注舒适和节奏慢）",
    "背包客（独自旅行，喜欢探险和当地体验）",
    "家庭出游（三代同堂，老少兼顾的行程需求）",
    "美食爱好者（专门为吃而旅行，关注当地特色美食）",
]

LABEL_PROMPT = """对以下旅游查询分类。只能返回JSON，无其他文字。
意图: itinerary/query/hotel/food/budget/transport/chat/image
频��: high_freq(简短常见)/mid_freq(具体详细)/low_freq(复杂少见)
格式: {{"intent":"xxx","category":"xxx","confidence":0.9}}
查询: {query}"""

AUGMENT_PROMPT = """模拟「{persona}」用户生成20条真实旅游查询。
覆盖: 行程规划/信息查询/住宿/美食/预算/交通。口语化，5-50字。
只返回JSON数组，无其他文字:
[{{"query":"xxx","intent":"xxx","category":"high_freq/mid_freq/low_freq"}}]
意图: itinerary/query/hotel/food/budget/transport/chat/image"""


async def call_deepseek(api_key: str, prompt: str, max_retries: int = 3) -> str:
    """Direct DeepSeek API call with retries."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "deepseek-v4-flash",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 2048,
    }

    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(DEEPSEEK_URL, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
            else:
                raise

    return ""


def parse_json_response(text: str):
    """Parse JSON from LLM response, handling markdown code blocks."""
    if "```" in text:
        parts = text.split("```")
        for part in parts[1:]:
            clean = part.strip()
            if clean.startswith("json"):
                clean = clean[4:].strip()
            if clean.startswith("{") or clean.startswith("["):
                text = clean
                break
    return json.loads(text.strip())


def normalize_category(cat: str) -> str:
    """Fix LLM category format inconsistencies."""
    cat = cat.lower().replace("freq", "_freq").replace("__", "_")
    if cat not in ("high_freq", "mid_freq", "low_freq"):
        cat = "mid_freq"
    return cat


async def label_queries(queries: list[dict], api_key: str) -> list[dict]:
    """Label all scraped queries with intent + category."""
    labeled = []
    total = len(queries)

    print(f"\n标注 {total} 条真实query...")
    for i, q in enumerate(queries):
        prompt = LABEL_PROMPT.format(query=q["query"])
        try:
            text = await call_deepseek(api_key, prompt)
            result = parse_json_response(text)
            labeled.append({
                "query": q["query"],
                "intent": result.get("intent", "chat"),
                "category": normalize_category(result.get("category", "mid_freq")),
                "confidence": result.get("confidence", 0.8),
                "source": "ctrip",
                "persona": "",
                "answers": q.get("answers", 0),
            })
        except Exception as e:
            labeled.append({
                "query": q["query"],
                "intent": "chat",
                "category": "low_freq",
                "confidence": 0.3,
                "source": "ctrip",
                "persona": "",
                "answers": q.get("answers", 0),
                "label_error": str(e),
            })

        if (i + 1) % 10 == 0:
            print(f"  进度: {i+1}/{total} ({(i+1)/total*100:.0f}%)", flush=True)

    print(f"  完成: {total}/{total}", flush=True)
    return labeled


async def augment_queries(
    target_count: int,
    labeled: list[dict],
    api_key: str,
) -> list[dict]:
    """Generate augmented queries using diverse personas."""
    # Calculate intent gaps
    intent_counts = Counter(q["intent"] for q in labeled)
    total_labeled = len(labeled)
    target_total = total_labeled + target_count

    target_dist = {
        "chat": 0.28, "query": 0.22, "itinerary": 0.18,
        "food": 0.12, "hotel": 0.09, "transport": 0.07,
        "budget": 0.03, "image": 0.01,
    }

    augment_needs = {}
    for intent in INTENTS:
        current = intent_counts.get(intent, 0)
        target_n = round(target_dist[intent] * target_total)
        augment_needs[intent] = max(0, target_n - current)

    print(f"\n需要补充的意图:", flush=True)
    for intent, need in sorted(augment_needs.items(), key=lambda x: -x[1]):
        if need > 0:
            print(f"  {intent}: +{need}", flush=True)

    augmented = []
    generated = 0
    batch_idx = 0
    rng = random.Random(42)
    errors = 0

    while generated < target_count and batch_idx < 100 and errors < 10:
        persona = PERSONAS[batch_idx % len(PERSONAS)]
        batch_idx += 1

        prompt = AUGMENT_PROMPT.format(persona=persona)
        try:
            text = await call_deepseek(api_key, prompt)
            items = parse_json_response(text)
            if not isinstance(items, list):
                items = []
        except Exception as e:
            print(f"  batch {batch_idx} 失败: {e}", flush=True)
            errors += 1
            await asyncio.sleep(3)
            continue

        batch_added = 0
        for item in items:
            if generated >= target_count:
                break
            if not item.get("query"):
                continue

            intent = item.get("intent", "chat")
            query = item["query"].strip()
            if len(query) < 3:
                continue

            augmented.append({
                "query": query,
                "intent": intent,
                "category": normalize_category(item.get("category", "mid_freq")),
                "confidence": 0.85,
                "source": "llm_augmented",
                "persona": persona.split("（")[0],
            })
            generated += 1
            batch_added += 1

        print(f"  batch {batch_idx}: +{batch_added} (累计 {generated}/{target_count})", flush=True)
        errors = 0  # Reset error counter on success
        await asyncio.sleep(1)

    return augmented[:target_count]


async def main():
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误: DEEPSEEK_API_KEY 未设置")
        print("用法: DEEPSEEK_API_KEY=xxx python -u -m eval.llm_labeler")
        return

    # Load scraped queries
    raw_path = Path(__file__).parent / "raw_queries.json"
    if not raw_path.exists():
        print("错误: eval/raw_queries.json 不存在，请先运行 scraper")
        return

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    raw_queries = raw_data["queries"]
    print(f"加载 {len(raw_queries)} 条爬取的query", flush=True)

    # Step A: Label
    labeled = await label_queries(raw_queries, api_key)

    intent_dist = Counter(q["intent"] for q in labeled)
    print(f"\n标注后意图分布:", flush=True)
    for intent, count in intent_dist.most_common():
        print(f"  {intent}: {count}", flush=True)

    # Step B: Augment
    target_augment = 1000 - len(labeled)
    print(f"\n需要LLM增强: {target_augment} 条", flush=True)
    augmented = await augment_queries(target_augment, labeled, api_key)

    # Step C: Merge
    all_queries = labeled + augmented
    rng = random.Random(42)
    rng.shuffle(all_queries)

    for i, q in enumerate(all_queries):
        q["id"] = i + 1

    # Save
    output_path = Path(__file__).parent / "labeled_queries.json"
    output_data = {
        "metadata": {
            "total": len(all_queries),
            "ctrip_real": len(labeled),
            "llm_augmented": len(augmented),
            "intent_distribution": dict(Counter(q["intent"] for q in all_queries)),
            "category_distribution": dict(Counter(q["category"] for q in all_queries)),
        },
        "queries": all_queries,
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # Summary
    print(f"\n{'='*60}", flush=True)
    print(f"  数据集生成完成", flush=True)
    print(f"{'='*60}", flush=True)
    print(f"  总计: {len(all_queries)} 条", flush=True)
    print(f"  真实数据: {len(labeled)} 条 (携程爬取)", flush=True)
    print(f"  LLM增强: {len(augmented)} 条", flush=True)
    print(f"\n  意图分布:", flush=True)
    final_dist = Counter(q["intent"] for q in all_queries)
    for intent, count in final_dist.most_common():
        print(f"    {intent}: {count} ({count/len(all_queries)*100:.1f}%)", flush=True)
    print(f"\n  已保存到: {output_path}", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
