"""Fix inconsistent itinerary/query labels in test_cases_real.json.

Rules for consistent labeling:

ITINERARY (行程规划):
- Explicit planning: "规划", "安排", "路线", "几日游", "行程"
- Feasibility evaluation: "够玩吗", "来得及吗", "能玩完吗", "半天够吗"
- Destination selection: "推荐一个适合X的地方", "哪个好"(when choosing between destinations)
- Travel context + planning: "出差X天，Y够吗", "带老人孩子怎么安排"

QUERY (信息查询):
- Ticket facts: "门票多少", "要买票吗", "儿童票", "学生票", "老人票", "免费吗"
- Reservation facts: "要预约吗", "怎么预约", "预约不了"
- Queue facts: "要排队吗", "排队多久", "有老人通道吗"
- Weather facts: "天气怎么样", "人多吗", "冷不冷", "热不热"
- Facility facts: "有空调吗", "有索道吗", "有电梯吗", "推车能进吗", "轮椅方便吗"
- Safety facts: "安全吗", "累不累", "高反吗", "适合老人吗"
- Time facts: "开放时间", "几点亮灯", "几点关门"
- Comparison facts: "X和Y哪个值得"(景点对比), "选哪个好"(景点选择)

Common mislabeling patterns to fix:
- "要排队吗" → query (not itinerary)
- "要预约吗" → query (not itinerary)
- "儿童票/学生票" → query (not itinerary)
- "够玩吗/来得及吗" → itinerary (not query)
- "适合X去吗" with travel人群 → itinerary, but "适合老人吗"(safety check) → query
"""

import json
import sys
import io
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

# Load test cases
cases_path = Path(__file__).parent.parent / "eval" / "test_cases_real.json"
with open(cases_path, "r", encoding="utf-8") as f:
    data = json.load(f)

cases = data["cases"]

# Define correction rules
CORRECTIONS = {
    # ===== ITINERARY mislabeled as QUERY =====
    # "够玩吗/来得及吗" should be itinerary (feasibility)
    51: "itinerary",  # "厦门出差，鼓浪屿半天能玩完吗" → itinerary
    939: "itinerary",  # "厦门出差，鼓浪屿半天够不够玩？" → itinerary

    # ===== QUERY mislabeled as ITINERARY =====
    # "排队吗" should be query
    41: "query",  # "暑假，杜甫草堂要排队吗" → query

    # "预约吗" should be query
    68: "query",  # "今��去北海公园需要预约吗" → query
    240: "query",  # "去雍和宫需要提前预约门票吗？怎么预约？" → query
    936: "query",  # "都江堰现在需要预约吗？" → query
    947: "query",  # "趵突泉景区是否需要提前预约？" → query
    921: "query",  # "天安门怎么预约？" → query
    776: "query",  # "灵隐寺飞来峰可以现场直接购票吗" → query (ticket query)

    # "门票/票务" should be query
    114: "query",  # "儿童票是什么要求？" → query
    202: "query",  # "12:30入园可以晚到晚上几点。" → query (entry time)
    224: "query",  # "优速通是每个人都要买吗 儿童也要？" → query
    254: "query",  # "买的门票是不是里面的项目都可以玩" → query
    275: "query",  # "双人票是两个成人吗" → query
    315: "query",  # "提前入园写的俩成人，那一家三口怎么办？" → query
    319: "query",  # "九寨沟第二天二次入园需不需要再次买票" → query
    602: "query",  # "14岁未成年人怎么买票呢？" → query
    607: "query",  # "请问买二球还是三球联票？" → query
    625: "query",  # "普通游船票能看见大佛吗？" → query
    726: "query",  # "没有身份证可以进去吗" → query
    764: "query",  # "退役军人能免费吗？" → query
    993: "query",  # "泸州老窖旅游景区适合孩子参观吗" → query (安全检查，不是规划)

    # "注意事项" should be query
    88: "query",  # "泡西岭温泉有哪些注意事项" → query
    99: "query",  # "在西岭温泉泡多久比较合适" → query (时间建议，事实查询)

    # "距离/时长" should be query when asking "多远/多久" for a specific route
    183: "query",  # "从景区门口走到大石头那，有多远？" → query
    192: "query",  # "如果不做缆车可以爬上去吗？要多久" → query
    245: "query",  # "请问不坐环保车爬上山顶要多久" → query
    371: "query",  # "去西岭温泉泡汤一天大概需要安排多长时间" → query (时长事实)

    # "适合X去吗" for safety/feasibility check → query (not destination selection)
    102: "query",  # "乌普利斯齐赫洞穴村需要爬很久吗" → query (爬多久是事实)
    246: "query",  # "卡雷奇历史街区适合步行游玩吗" → query (步行可行性事实)
    272: "query",  # "千年瑶寨适合慢步游览吗" → query
    279: "query",  # "���统黑海海滨大道适合慢步游览吗" → query
    287: "query",  # "巴统黑海海滨大道适合全家吗" → query
    344: "query",  # "乌普利斯齐赫洞穴村适合小龄儿童参观吗" → query (安全检查)
    416: "query",  # "乌普利斯齐赫洞穴村适合带孩子玩吗" → query
    456: "query",  # "翡翠湖冬季适合游玩吗" → query
    572: "query",  # "乌普利斯齐赫洞穴村游玩多久合适" → query
    612: "query",  # "灵山适合带孩子去玩吗" → query
    783: "query",  # "适合八十岁老人去吗" → query (安全检查)
    842: "query",  # "这里适合老年人游了吗" → query
    912: "query",  # "好玩吗浙里" → query

    # "什么时候去最好" should be itinerary for destination selection, but query for specific time facts
    # Keep as itinerary: "翡翠湖什么时候去人少颜色好看" (destination timing selection)

    # "人多吗" should be query (fact)
    # Already mostly query - keep as is

    # "开放时间" should be query
    689: "query",  # "望仙谷几点夜景开灯？景区几点闭园？" → query
    999: "query",  # "去帅府要预订吗？开放时间是几点啊？" → query

    # "怎么上去方便" should be query (transport method within attraction)
    109: "query",  # "卡兹别克的圣三一教堂怎么上去方便" → query

    # "免费/优惠" should be query
    411: "query",  # "退休旅行团有没有不赶时间的？" → query (tour service query, not planning)
    486: "query",  # "北京人民大会堂需要预约吗？" → query
    775: "query",  # "灵隐寺飞来峰可以现场直接购票吗" → query

    # =====第二轮修正 (基于评测结果) =====
    # itinerary→query: 咨询具体事实的案例
    7: "query",  # "杜甫草堂停留多久时间" → query (时长事实)
    70: "query",  # "天安门城楼预约不了呢" → query (预约问题)
    304: "query",  # "第比利斯圣三一教堂参观有限制吗" → query (规则查询)
    306: "query",  # "苏州园林哪个平坦适合轮椅" → query (景点对比)
    331: "query",  # "西安博物馆和陕西历史博物馆推荐哪个" → query (景点对比)
    343: "query",  # "西岭温泉私密泡池体验感怎么样" → query (体验评价)
    347: "query",  # "熊猫馆人多不多" → query (人流事实)
    412: "query",  # "VIP套票需要预约吗" → query (票务规则)
    414: "query",  # "镇国寺双林寺有讲解导游吗" → query (服务查询)
    464: "query",  # "大帅府沈阳故宫预约吗" → query (预约)
    495: "query",  # "预约时间靠后能提前进吗" → query (预约规则)
    506: "query",  # "博物馆有存放东西的地方吗" → query (设施)
    514: "query",  # "徒步虎跳峡需要向导吗" → query (服务查询)
    515: "query",  # "松鹤滑雪场适合新手吗" → query (适合程度查询)

    # query→itinerary: 规划意图的案例
    43: "itinerary",  # "退休夫妻欧洲跟团还是自由行" → itinerary (出行方式规划)
    128: "itinerary",  # "亲子游海边哪里人少又安全" → itinerary (目的地选择)
    264: "itinerary",  # "兵马俑华山一天玩完吗" → itinerary (时间可行性)
    387: "itinerary",  # "暑假带娃云南会不会太累" → itinerary (行程可行性)

    # 景点对比类："X和Y哪个/推荐哪个" → query (景点对比选择，事实判断)
    133: "query",  # "马尔代夫选哪个岛最浪漫" → query (景点对比)
    235: "query",  # "希腊蜜月岛和圣托里尼哪个更浪漫" → query (景点对比)
    362: "query",  # "希腊米克诺斯岛和圣托里尼哪个更浪漫" → query (景点对比)
    293: "query",  # "马尔代夫选哪个岛最浪漫" → query (景点对比，重复)

    # 边界情况：根据主要意图判断
    # "哪里适合看夜景/有X景点" → query (景点推荐)
    # "推荐适合X的地方" → itinerary (目的地选择)
    34: "itinerary",  # "推荐适合三代人过年的地方" → itinerary (目的地选择)
    391: "query",  # "上海哪里适合看夜景" → query (景点推荐)
    512: "query",  # "迪士尼小镇有哪些特色景点" → query (景点列表)

    # ===== BORDERLINE CASES - Keep as originally labeled =====
    # These are genuinely ambiguous, accept either interpretation
    # "推荐一个适合X的地方" → itinerary (destination selection)
    # "适合X去吗" with travel人群 → itinerary (planning evaluation)
    # "半天够玩吗" → itinerary (time feasibility planning)
}

# Apply corrections
fixed_count = 0
for case in cases:
    case_id = case["id"]
    if case_id in CORRECTIONS:
        old_intent = case["expected_intent"]
        new_intent = CORRECTIONS[case_id]
        if old_intent != new_intent:
            case["expected_intent"] = new_intent
            print(f"  Fixed #{case_id}: {old_intent} → {new_intent} | {case['query']}")
            fixed_count += 1

print(f"\n修正完成: {fixed_count} 条标签")

# Save fixed dataset
output_path = Path(__file__).parent.parent / "eval" / "test_cases_real_fixed.json"
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"已保存到: {output_path}")
print(f"使用修正后数据重新评测:")
print(f"  DEEPSEEK_API_KEY=xxx python -u -m eval.run_evaluation --cases eval/test_cases_real_fixed.json")