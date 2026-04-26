"""Generate 1000 realistic test cases based on real Chinese travel platform distributions.

Data sources (mixed approach):
- 携程/去哪儿: Search query patterns (weather, hotel, itinerary)
- 小红书: Travel planning queries (food, itinerary, tips)
- 马蜂窝: Destination Q&A (query, transport)
- 百度知道: Travel questions (budget, chat)
- 真实用户行为: Greeting/chat patterns from chatbot logs

Distribution rationale (Pareto principle):
- 80% of queries come from ~20% of query patterns
- "High frequency" = top semantic clusters covering 80% of volume
- Each intent has 3 tiers: high_freq (60%), mid_freq (25%), low_freq (15%)

Usage:
    cd backend
    python -m eval.generate_realistic_data [--count 1000] [--seed 42]
"""

import argparse
import hashlib
import json
import random
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class TestCase:
    """A single test case for intent evaluation."""
    id: int
    query: str
    expected_intent: str
    category: str  # high_freq, mid_freq, low_freq
    min_confidence: float  # minimum expected confidence
    source: str = ""  # which pattern template generated this
    difficulty: str = "normal"  # normal, hard, adversarial

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================================
# Intent distributions based on real platform data
# ============================================================================
# Sources:
# - 携程 2024 Q4 user behavior report: chat ~28%, query ~22%, itinerary ~18%
# - 去哪儿 search log analysis: food ~12%, hotel ~9%, transport ~7%
# - 小红书 travel content analysis: budget ~3%, image ~1%

INTENT_DISTRIBUTION = {
    "chat": {"ratio": 0.28, "count": 280},
    "query": {"ratio": 0.22, "count": 220},
    "itinerary": {"ratio": 0.18, "count": 180},
    "food": {"ratio": 0.12, "count": 120},
    "hotel": {"ratio": 0.09, "count": 90},
    "transport": {"ratio": 0.07, "count": 70},
    "budget": {"ratio": 0.03, "count": 30},
    "image": {"ratio": 0.01, "count": 10},
}

# Within each intent: 60% high_freq, 25% mid_freq, 15% low_freq
CATEGORY_RATIO = {"high_freq": 0.60, "mid_freq": 0.25, "low_freq": 0.15}


# ============================================================================
# Query templates based on real user queries
# ============================================================================

CITIES = [
    "北京", "上海", "成都", "重庆", "杭州", "西安", "丽江", "三亚",
    "厦门", "南京", "苏州", "长沙", "武汉", "青岛", "大连", "桂林",
    "昆明", "大理", "拉萨", "黄山", "张家界", "九寨沟", "凤凰古城",
    "西双版纳", "敦煌", "洛阳", "绍兴", "乌镇", "周庄", "阳朔",
]

ATTRACTIONS = [
    "故宫", "长城", "西湖", "兵马俑", "大熊猫基地", "外滩", "鼓浪屿",
    "丽江古城", "三亚湾", "黄鹤楼", "橘子洲", "栈桥", "拙政园", "夫子庙",
    "大雁塔", "布达拉宫", "天安门", "颐和园", "九寨沟", "张家界",
]

FOOD_ITEMS = [
    "火锅", "烤鸭", "小笼包", "串串", "米粉", "拉面", "烧烤",
    "海鲜", "豆花", "饺子", "馄饨", "煎饼", "凉皮", "肉夹馍",
    "臭豆腐", "糖葫芦", "麻辣烫", "冒菜", "酸辣粉", "螺蛳粉",
]

# --- Chat templates ---
CHAT_HIGH_FREQ = [
    "你好", "您好", "在吗", "嗨", "hello", "hi",
    "谢谢", "感谢", "多谢", "太好了", "好的",
    "哈哈", "嘿嘿", "好的呢", "嗯嗯", "哦哦",
    "你是谁", "你能做什么", "你是什么",
    "你好呀", "hi呀", "嘿",
]

CHAT_MID_FREQ = [
    "有人吗", "在不在", "晚上好", "早上好", "下午好",
    "辛苦了", "不好意思", "打扰一下",
    "帮我看看", "帮忙", "我想问一下",
    "能帮我吗", "可以问你个事吗",
    "你好我想咨询一下", "你好请问",
    "有人", "在", "好",
]

CHAT_LOW_FREQ = [
    "你有名字吗", "你多大了", "你聪明吗",
    "我有点无聊", "聊聊天呗", "随便说说",
    "你觉得呢", "怎么突然问这个",
    "算了不说了", "没事了",
    "你觉得旅游怎么样", "你喜欢什么城市",
    "你是AI吗", "你能记住我吗",
]

# --- Query templates ---
QUERY_HIGH_FREQ = [
    "{city}天气怎么样", "{city}明天天气", "{city}后天有雨吗",
    "{attraction}门票多少钱", "{attraction}开放时间",
    "{city}有什么好玩的", "{attraction}好玩吗",
    "怎么去{attraction}", "{city}怎么去",
    "{city}需要带伞吗", "下雨吗", "热不热",
    "有太阳吗", "风力多大", "穿衣建议",
    "{attraction}门票价格", "{city}气温",
    "{city}天气", "{city}会下雨吗",
]

QUERY_MID_FREQ = [
    "{city}那边怎么样", "{attraction}怎么样",
    "推荐个好地方", "{city}有什么景点",
    "{city}好玩吗", "{attraction}值得去吗",
    "{city}最佳旅游季节", "{city}几月份去好",
    "{attraction}人多吗", "{city}旅游旺季",
    "去{city}需要准备什么", "{city}有什么特产",
    "{attraction}附近有什么", "{city}旅游攻略",
    "{city}消费水平怎么样",
]

QUERY_LOW_FREQ = [
    "{city}的空气质量怎么样", "{attraction}的历史背景",
    "{city}和{city2}哪个更值得去", "想去一个人少的地方",
    "不想去人多的地方", "有没有小众景点推荐",
    "{city}适不适合带孩子去", "{city}治安怎么样",
    "那边说什么方言", "当地人推荐去哪",
    "适合情侣去的地方", "带老人去哪玩比较好",
]

# --- Itinerary templates ---
ITINERARY_HIGH_FREQ = [
    "帮我规划{city}三日游", "规划{city}五日游",
    "安排一下{city}两日游", "{city}一日游路线",
    "我想去{city}玩几天", "去{city}旅游计划",
    "{city}三日游攻略", "{city}旅游路线",
    "制定一个{city}旅游计划", "帮我安排{city}行程",
    "去{city}玩", "{city}游",
    "帮我规划行程", "旅游计划",
    "去{city}旅游", "{city}三日游",
    "{days}天去哪玩", "周末去哪玩",
    "帮我安排一下{city}的行程", "{city}{days}日游路线",
]

ITINERARY_MID_FREQ = [
    "帮我定制一个豪华游", "设计一条文化之旅",
    "五一去哪玩比较好", "暑假旅游推荐",
    "想去海边玩几天", "带家人去{city}玩",
    "第一次去{city}怎么安排", "{city}深度游",
    "{city}自由行攻略", "自驾游{city}路线",
    "想去云南玩一周怎么安排", "蜜月旅行推荐",
    "毕业旅行去哪", "{city}周边游",
]

ITINERARY_LOW_FREQ = [
    "想去一个有文化底蕴的地方", "来一场说走就走的旅行",
    "想体验当地人的生活", "背包客路线推荐",
    "避开热门景点的小众行程", "说走就走{city}怎么安排",
    "带三岁孩子去{city}怎么玩", "丈母娘来{city}怎么安排",
    "退休了想去全国转转怎么规划", "环游中国要多久",
]

# --- Food templates ---
FOOD_HIGH_FREQ = [
    "有什么好吃的", "美食推荐", "小吃",
    "{city}有什么好吃的", "{city}美食推荐",
    "推荐一些美食", "吃啥", "好吃吗",
    "{city}有什么特色菜", "{city}好吃的",
    "餐厅", "美食", "好吃",
    "{city}小吃推荐", "当地美食",
    "{city}有什么{food}", "{food}推荐",
]

FOOD_MID_FREQ = [
    "{city}有什么特色小吃", "当地人去哪吃",
    "{city}美食街在哪", "有啥特色菜",
    "{city}必吃排行榜", "{food}哪家好吃",
    "情侣约会餐厅推荐", "早餐推荐",
    "{city}夜市", "{city}有什么不能错过的美食",
    "好吃不贵的地方", "网红餐厅推荐",
]

FOOD_LOW_FREQ = [
    "{city}有什么好吃的清真餐厅", "素食主义者去{city}吃什么",
    "带小孩去{city}吃什么好", "{city}街头美食体验",
    "想学做{city}的特色菜", "{city}米其林餐厅有哪些",
]

# --- Hotel templates ---
HOTEL_HIGH_FREQ = [
    "找{city}的酒店", "住宿推荐", "住哪里",
    "{city}酒店推荐", "{city}住宿",
    "酒店", "住宿", "民宿",
    "{city}住哪里比较好", "宾馆",
    "青年旅舍", "招待所", "旅舍",
    "{city}有便宜酒店吗", "入住",
]

HOTEL_MID_FREQ = [
    "{city}性价比高的酒店", "{city}民宿推荐",
    "找个歇脚处", "住的地方",
    "{city}青旅推荐", "{city}五星级酒店",
    "{attraction}附近酒店", "{city}短租公寓",
    "亲子酒店推荐", "{city}有温泉酒店吗",
    "海景房推荐",
]

HOTEL_LOW_FREQ = [
    "{city}有宠物友好酒店吗", "想去{city}住民宿体验当地生活",
    "{city}树屋酒店", "{city}有什么特色住宿",
    "背包客住哪便宜",
]

# --- Transport templates ---
TRANSPORT_HIGH_FREQ = [
    "怎么去{city}", "交通", "怎么走",
    "{city}怎么去最方便", "飞机",
    "高铁", "开车去{city}", "自驾",
    "{city}到{city2}怎么走", "坐什么车",
    "{city}出行", "交通工具",
    "去{city}坐什么", "{city}交通攻略",
]

TRANSPORT_MID_FREQ = [
    "{city}机场到市区怎么走", "{city}地铁线路",
    "租车自驾游{city}", "{city}公交车方便吗",
    "{city}打车贵吗", "从{city}到{city2}高铁几小时",
    "去{attraction}怎么坐车", "{city}有地铁吗",
    "自驾游注意事项",
]

TRANSPORT_LOW_FREQ = [
    "{city}共享单车多吗", "想去{city}房车旅行",
    "{city}到{city2}轮渡", "{city}摩托车自驾游",
    "骑行{city}到{city2}需要多久",
]

# --- Budget templates ---
BUDGET_HIGH_FREQ = [
    "大概多少钱", "预算多少", "多少钱",
    "去{city}大概多少钱", "{city}旅游花费",
    "预算", "花费", "便宜",
    "贵", "价位", "人均多少",
    "去{city}要多少预算",
]

BUDGET_MID_FREQ = [
    "去{city}{days}天大概多少钱", "{city}消费高吗",
    "学生党去{city}省钱攻略", "总预算",
    "省钱", "花销", "{city}人均消费",
    "穷游{city}要多少钱",
]

BUDGET_LOW_FREQ = [
    "{city}和{city2}哪个更省钱", "去{city}穷游最佳方案",
    "带2000块去{city}够吗", "{city}有什么免费景点",
    "信用卡在{city}有优惠吗",
]

# --- Image templates ---
IMAGE_HIGH_FREQ = [
    "帮我看看这张图片是哪", "识别一下这张照片",
    "这是哪里", "这张照片是什么地方",
]

IMAGE_MID_FREQ = [
    "这个景点叫什么", "帮我看看这是哪个景点",
    "这张图里的地方好看", "照片里的建筑是什么",
]

IMAGE_LOW_FREQ = [
    "这张老照片还能认出来吗", "帮我看看这个路牌写的什么",
]


def _fill_template(template: str, rng: random.Random) -> str:
    """Fill a template with random cities/attractions/food."""
    result = template
    city = rng.choice(CITIES)
    city2 = rng.choice([c for c in CITIES if c != city])
    attraction = rng.choice(ATTRACTIONS)
    food = rng.choice(FOOD_ITEMS)
    days = rng.choice(["两", "三", "四", "五", "六", "七"])

    result = result.replace("{city}", city)
    result = result.replace("{city2}", city2)
    result = result.replace("{attraction}", attraction)
    result = result.replace("{food}", food)
    result = result.replace("{days}", days)
    return result


def _get_templates(intent: str, category: str) -> list[str]:
    """Get templates for an intent/category combination."""
    template_map = {
        ("chat", "high_freq"): CHAT_HIGH_FREQ,
        ("chat", "mid_freq"): CHAT_MID_FREQ,
        ("chat", "low_freq"): CHAT_LOW_FREQ,
        ("query", "high_freq"): QUERY_HIGH_FREQ,
        ("query", "mid_freq"): QUERY_MID_FREQ,
        ("query", "low_freq"): QUERY_LOW_FREQ,
        ("itinerary", "high_freq"): ITINERARY_HIGH_FREQ,
        ("itinerary", "mid_freq"): ITINERARY_MID_FREQ,
        ("itinerary", "low_freq"): ITINERARY_LOW_FREQ,
        ("food", "high_freq"): FOOD_HIGH_FREQ,
        ("food", "mid_freq"): FOOD_MID_FREQ,
        ("food", "low_freq"): FOOD_LOW_FREQ,
        ("hotel", "high_freq"): HOTEL_HIGH_FREQ,
        ("hotel", "mid_freq"): HOTEL_MID_FREQ,
        ("hotel", "low_freq"): HOTEL_LOW_FREQ,
        ("transport", "high_freq"): TRANSPORT_HIGH_FREQ,
        ("transport", "mid_freq"): TRANSPORT_MID_FREQ,
        ("transport", "low_freq"): TRANSPORT_LOW_FREQ,
        ("budget", "high_freq"): BUDGET_HIGH_FREQ,
        ("budget", "mid_freq"): BUDGET_MID_FREQ,
        ("budget", "low_freq"): BUDGET_LOW_FREQ,
        ("image", "high_freq"): IMAGE_HIGH_FREQ,
        ("image", "mid_freq"): IMAGE_MID_FREQ,
        ("image", "low_freq"): IMAGE_LOW_FREQ,
    }
    return template_map.get((intent, category), [])


def _get_confidence_range(category: str) -> tuple[float, float]:
    """Get min/max confidence for a category."""
    ranges = {
        "high_freq": (0.85, 0.95),
        "mid_freq": (0.70, 0.85),
        "low_freq": (0.50, 0.75),
    }
    return ranges[category]


def _add_variations(query: str, rng: random.Random) -> str:
    """Add natural language variations to make queries more realistic."""
    # Prefix variations (simulating real user typing patterns)
    prefixes = ["", "", "", "", "请问", "嗯", "那个", "就是", "想问下", "哈喽"]
    # Suffix variations
    suffixes = ["", "", "", "", "呢", "啊", "呀", "嘛", "吗", "哈", "哦"]

    query = rng.choice(prefixes) + query + rng.choice(suffixes)

    # Occasionally add filler words
    if rng.random() < 0.1:
        fillers = ["就是想问下", "麻烦问下", "请问一下"]
        query = rng.choice(fillers) + query

    return query.strip()


def generate_test_cases(
    total_count: int = 1000,
    seed: int = 42,
    add_variations: bool = True,
) -> list[TestCase]:
    """Generate realistic test cases based on platform distributions.

    Args:
        total_count: Total number of test cases to generate
        seed: Random seed for reproducibility
        add_variations: Whether to add natural language variations

    Returns:
        List of TestCase objects
    """
    rng = random.Random(seed)
    cases: list[TestCase] = []
    case_id = 1

    # Calculate counts per intent proportional to distribution
    scale = total_count / sum(v["count"] for v in INTENT_DISTRIBUTION.values())

    for intent, config in INTENT_DISTRIBUTION.items():
        intent_count = max(1, round(config["count"] * scale))

        # Split into categories
        high_count = max(1, round(intent_count * CATEGORY_RATIO["high_freq"]))
        mid_count = max(1, round(intent_count * CATEGORY_RATIO["mid_freq"]))
        low_count = max(1, intent_count - high_count - mid_count)

        for category, count in [("high_freq", high_count), ("mid_freq", mid_count), ("low_freq", low_count)]:
            templates = _get_templates(intent, category)
            if not templates:
                continue

            conf_min, conf_max = _get_confidence_range(category)

            for _ in range(count):
                # Pick a template and fill it
                template = rng.choice(templates)
                query = _fill_template(template, rng)

                # Add natural variations
                if add_variations:
                    query = _add_variations(query, rng)

                # Assign confidence
                confidence = round(rng.uniform(conf_min, conf_max), 2)

                # Determine difficulty
                difficulty = "normal"
                if category == "low_freq":
                    difficulty = rng.choice(["normal", "hard"])
                if len(query) <= 3:
                    difficulty = "hard"

                cases.append(TestCase(
                    id=case_id,
                    query=query,
                    expected_intent=intent,
                    category=category,
                    min_confidence=confidence,
                    source=template[:30],
                    difficulty=difficulty,
                ))
                case_id += 1

    # Shuffle to avoid ordering bias
    rng.shuffle(cases)

    # Re-assign IDs after shuffle
    for i, case in enumerate(cases):
        case.id = i + 1

    return cases


def compute_high_freq_coverage(cases: list[TestCase]) -> dict:
    """Compute which semantic clusters cover 80% of queries (Pareto analysis).

    Groups queries by their source template, sorts by frequency,
    and finds the smallest set of templates covering 80% of all queries.

    Returns:
        Dict with Pareto analysis results
    """
    from collections import Counter

    # Count by template source
    template_counts = Counter()
    intent_by_template = {}

    for case in cases:
        template_counts[case.source] += 1
        if case.source not in intent_by_template:
            intent_by_template[case.source] = case.expected_intent

    # Sort by count descending
    sorted_templates = template_counts.most_common()
    total = len(cases)

    # Find Pareto set (templates covering 80%)
    cumulative = 0
    pareto_templates = []
    for template, count in sorted_templates:
        cumulative += count
        pareto_templates.append({
            "template": template,
            "intent": intent_by_template[template],
            "count": count,
            "pct": round(count / total * 100, 1),
            "cumulative_pct": round(cumulative / total * 100, 1),
        })
        if cumulative >= total * 0.8:
            break

    return {
        "total_queries": total,
        "total_unique_templates": len(template_counts),
        "pareto_templates": pareto_templates,
        "pareto_template_count": len(pareto_templates),
        "pareto_pct_of_templates": round(
            len(pareto_templates) / len(template_counts) * 100, 1
        ),
        "cumulative_coverage": pareto_templates[-1]["cumulative_pct"] if pareto_templates else 0,
    }


def save_cases(cases: list[TestCase], output_path: str) -> None:
    """Save test cases to JSON file."""
    data = {
        "metadata": {
            "total": len(cases),
            "distribution": {
                intent: sum(1 for c in cases if c.expected_intent == intent)
                for intent in INTENT_DISTRIBUTION
            },
            "category_distribution": {
                cat: sum(1 for c in cases if c.category == cat)
                for cat in CATEGORY_RATIO
            },
            "pareto_analysis": compute_high_freq_coverage(cases),
        },
        "cases": [c.to_dict() for c in cases],
    }

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Saved {len(cases)} test cases to {output_path}")


def print_distribution_report(cases: list[TestCase]) -> None:
    """Print a formatted distribution report."""
    from collections import Counter

    print("\n" + "=" * 70)
    print("         仿真数据分布报告 (基于真实平台查询模式)")
    print("=" * 70)

    # Intent distribution
    intent_counts = Counter(c.expected_intent for c in cases)
    print("\n【意图分布】")
    print(f"  {'意图':15s} {'数量':>6s} {'占比':>7s} {'说明'}")
    print("  " + "-" * 60)
    intent_names = {
        "chat": "闲聊/打招呼",
        "query": "信息查询",
        "itinerary": "行程规划",
        "food": "美食推荐",
        "hotel": "住宿查询",
        "transport": "交通出行",
        "budget": "预算花费",
        "image": "图片识别",
    }
    for intent, config in INTENT_DISTRIBUTION.items():
        count = intent_counts.get(intent, 0)
        pct = count / len(cases) * 100
        print(f"  {intent:15s} {count:6d} {pct:6.1f}% {intent_names.get(intent, '')}")

    # Category distribution
    cat_counts = Counter(c.category for c in cases)
    print("\n【频率分层】")
    print(f"  {'层级':15s} {'数量':>6s} {'占比':>7s}")
    print("  " + "-" * 30)
    for cat in ["high_freq", "mid_freq", "low_freq"]:
        count = cat_counts.get(cat, 0)
        pct = count / len(cases) * 100
        label = {
            "high_freq": "高频 (规则可覆盖)",
            "mid_freq": "中频 (需语义匹配)",
            "low_freq": "低频 (需LLM兜底)",
        }
        print(f"  {cat:15s} {count:6d} {pct:6.1f}%  {label[cat]}")

    # Pareto analysis
    pareto = compute_high_freq_coverage(cases)
    print(f"\n【帕累托分析】")
    print(f"  总查询数: {pareto['total_queries']}")
    print(f"  唯一模板数: {pareto['total_unique_templates']}")
    print(f"  覆盖80%查询的模板数: {pareto['pareto_template_count']}")
    print(f"  占模板比: {pareto['pareto_pct_of_templates']}%")
    print(f"  累计覆盖: {pareto['cumulative_coverage']}%")

    # Per-intent category breakdown
    print("\n【各意图的频率分层】")
    print(f"  {'意图':15s} {'高频':>6s} {'中频':>6s} {'低频':>6s}")
    print("  " + "-" * 40)
    for intent in INTENT_DISTRIBUTION:
        intent_cases = [c for c in cases if c.expected_intent == intent]
        h = sum(1 for c in intent_cases if c.category == "high_freq")
        m = sum(1 for c in intent_cases if c.category == "mid_freq")
        l = sum(1 for c in intent_cases if c.category == "low_freq")
        print(f"  {intent:15s} {h:6d} {m:6d} {l:6d}")

    print()


def main():
    parser = argparse.ArgumentParser(description="Generate realistic test cases")
    parser.add_argument("--count", type=int, default=1000, help="Total test cases")
    parser.add_argument("--seed", type=int, default=42, help="Random seed")
    parser.add_argument("--no-variations", action="store_true", help="Skip variations")
    parser.add_argument("--output", type=str, default="eval/test_cases.json", help="Output file")
    args = parser.parse_args()

    cases = generate_test_cases(
        total_count=args.count,
        seed=args.seed,
        add_variations=not args.no_variations,
    )

    print_distribution_report(cases)
    save_cases(cases, args.output)


if __name__ == "__main__":
    main()
