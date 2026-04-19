# backend/tests/test_interview_monitor/utils/intent_generator.py
"""Intent query data generator for INT-01~05 tests"""

import random
from typing import List, Tuple


class IntentQueryGenerator:
    """意图查询数据生成器 - 旅行助手场景

    生成各种意图类型的查询样本，用于测试意图分类器。
    支持的意图类型: itinerary, query, hotel, food, budget, transport, chat, image
    """

    # 各意图类型的核心关键词
    KEYWORDS = {
        "itinerary": ["规划", "行程", "安排", "旅游", "游玩", "旅行", "制定", "推荐路线", "几天游"],
        "query": ["天气", "开放时间", "门票", "怎么去", "在哪里", "几点", "价格", "查询"],
        "hotel": ["酒店", "住宿", "住哪里", "民宿", "旅馆", "宾馆", "房间", "预订"],
        "food": ["美食", "餐厅", "好吃的", "特色菜", "小吃", "美食街", "推荐餐厅"],
        "budget": ["预算", "多少钱", "花费", "费用", "价格", "成本", "大概多少"],
        "transport": ["交通", "高铁", "飞机", "火车", "自驾", "怎么去", "出行方式"],
        "chat": ["你好", "谢谢", "在吗", "好的", "了解", "好的"],
        "image": ["图片", "照片", "这张", "这个景点", "识别"],
    }

    # 各意图类型的句式模板
    TEMPLATES = {
        "itinerary": [
            "帮我规划{}天{}行程",
            "去{}旅游怎么安排",
            "制定一个{}日游计划",
            "{}旅行需要几天合适",
            "帮我安排{}的{}日游",
            "推荐一条{}三日游路线",
            "{}周末{}天去哪玩好",
            "去{}玩{}天怎么规划",
            "给我做一个{}的自由行计划",
            "{}到{}旅游{}天行程安排",
        ],
        "query": [
            "{}天气怎么样",
            "{}有什么景点推荐",
            "{}开放时间是什么时候",
            "{}门票多少钱",
            "{}怎么去最方便",
            "{}在哪个位置",
            "{}几点开门",
            "{}需要提前预约吗",
            "{}游玩大概多久",
            "{}有什么注意事项",
        ],
        "hotel": [
            "帮我推荐{}的酒店",
            "{}住宿哪里好",
            "{}民宿推荐",
            "在{}找一家酒店",
            "{}附近酒店价格",
            "{}酒店预订",
            "推荐{}性价比高的酒店",
            "{}有什么好的住宿",
            "在{}住一晚推荐",
            "{}家庭房推荐",
        ],
        "food": [
            "{}有什么特色美食",
            "推荐{}的餐厅",
            "{}必吃的小吃有哪些",
            "{}美食街在哪里",
            "{}有什么好吃的",
            "去{}必尝的美食",
            "{}地道餐厅推荐",
            "{}早餐去哪里吃",
            "{}夜宵推荐",
            "{}美食攻略",
        ],
        "budget": [
            "去{}大概需要多少钱",
            "{}三日游预算多少",
            "{}旅行费用清单",
            "{}自助游要花多少钱",
            "{}跟团游价格",
            "{}往返机票多少钱",
            "{}酒店价格多少",
            "{}门票总共多少钱",
            "{}吃饭预算多少",
            "{}穷游需要多少钱",
        ],
        "transport": [
            "去{}坐高铁还是飞机",
            "{}怎么去最方便",
            "{}交通方式有哪些",
            "到{}坐什么车",
            "{}高铁票多少钱",
            "{}机场大巴时刻表",
            "{}自驾游路线推荐",
            "{}公共交通指南",
            "去{}开车多久",
            "{}打车方便吗",
        ],
        "chat": [
            "你好",
            "谢谢",
            "在吗",
            "好的",
            "了解",
            "好的知道了",
            "收到",
            "好的谢谢",
            "可以",
            "没问题",
        ],
        "image": [
            "帮我看看这张图片",
            "识别一下这个地点",
            "这是哪里",
            "图片里的景点叫什么",
            "这张照片是哪里",
            "帮我看看这是什么地方",
            "识别图片中的位置",
            "这是什么建筑",
            "这张照片是哪里拍的",
            "看看这张图片的景点信息",
        ],
    }

    # 各意图类型的目标地点/目的地
    DESTINATIONS = [
        "北京", "上海", "杭州", "成都", "西安", "重庆", "厦门", "青岛",
        "三亚", "广州", "深圳", "南京", "苏州", "丽江", "大理", "桂林",
        "黄山", "张家界", "九寨沟", "西藏", "新疆", "云南", "四川",
        "日本", "泰国", "韩国", "新加坡", "美国", "欧洲",
    ]

    # 时间/天数
    DURATIONS = ["1", "2", "3", "4", "5", "7", "10"]

    def __init__(self, seed: int = 42):
        """初始化生成器

        Args:
            seed: 随机种子，确保测试可复现
        """
        self._rng = random.Random(seed)
        self._destinations = self.DESTINATIONS
        self._durations = self.DURATIONS

    def generate_query(self, intent: str) -> str:
        """生成单条意图查询

        Args:
            intent: 意图类型

        Returns:
            查询文本字符串
        """
        templates = self.TEMPLATES.get(intent, self.TEMPLATES["chat"])
        template = self._rng.choice(templates)

        # 填充模板变量
        try:
            if "{}" in template:
                if self._rng.random() < 0.3 and intent != "chat":
                    # 30%概率不带地点的简短查询 (测试规则匹配)
                    return template.split("{")[0]
                return template.format(
                    self._rng.choice(self._destinations),
                    self._rng.choice(self._durations),
                )
            return template
        except (IndexError, KeyError):
            # 如果模板变量不匹配，返回默认查询
            return self._rng.choice(self.KEYWORDS.get(intent, ["测试查询"]))

    def generate_queries(
        self,
        intent: str,
        count: int,
        include_short: bool = True,
    ) -> List[Tuple[str, str]]:
        """生成多条意图查询

        Args:
            intent: 意图类型
            count: 生成数量
            include_short: 是否包含短查询 (用于测试规则匹配边界)

        Returns:
            List[Tuple[query_text, intent]]
        """
        samples = []
        for i in range(count):
            if include_short and i % 5 == 0:
                # 每5条包含一条短查询 (测试规则策略)
                keywords = self.KEYWORDS.get(intent, ["查询"])
                query = self._rng.choice(keywords)
            else:
                query = self.generate_query(intent)
            samples.append((query, intent))
        return samples

    def generate_all_intent_queries(
        self,
        per_intent: int,
        intents: List[str] = None,
    ) -> List[Tuple[str, str]]:
        """生成所有意图类型的查询

        Args:
            per_intent: 每种意图类型的查询数量
            intents: 意图类型列表 (默认全部)

        Returns:
            所有查询的列表
        """
        if intents is None:
            intents = ["itinerary", "query", "hotel", "food", "budget", "transport"]

        samples = []
        for intent in intents:
            samples.extend(self.generate_queries(intent, per_intent))
        return samples

    def generate_high_frequency_queries(self, count: int) -> List[Tuple[str, str]]:
        """生成高频查询样本 (用于INT-01缓存命中率测试)

        高频查询特点: 重复度高，模式固定
        - 50种核心查询 × N次重复 = count条

        Args:
            count: 总查询数量

        Returns:
            List[Tuple[query_text, expected_intent]]
        """
        # 核心高频查询池 (每种意图10条)
        core_queries = []

        intent_mapping = {
            "itinerary": "帮我规划北京3日游",
            "query": "北京天气怎么样",
            "hotel": "推荐北京的酒店",
            "food": "北京有什么特色美食",
            "budget": "去北京大概多少钱",
            "transport": "去北京怎么坐车",
        }

        for intent, query in intent_mapping.items():
            core_queries.append((query, intent))
            core_queries.append((f"{query}，还有呢", intent))
            core_queries.append((f"换个方案：{query}", intent))
            core_queries.append((f"再说一个：{query}", intent))
            core_queries.append((f"重新推荐{query[2:]}", intent))

        # 如果需要更多，循环使用核心查询
        result = []
        for i in range(count):
            query, intent = core_queries[i % len(core_queries)]
            # 轻微变化以测试缓存的模糊匹配能力
            if i >= len(core_queries) and i % 7 == 0:
                query = query + "吗"
            result.append((query, intent))

        return result

    def generate_mixed_queries(self, count: int) -> List[Tuple[str, str]]:
        """生成混合意图查询 (用于INT-05对比实验)

        混合意图特点: 多样化，模拟真实用户输入
        - 覆盖所有意图类型
        - 包含边界情况

        Args:
            count: 查询数量

        Returns:
            List[Tuple[query_text, expected_intent]]
        """
        all_intents = ["itinerary", "query", "hotel", "food", "budget", "transport"]
        result = []

        for i in range(count):
            intent = all_intents[i % len(all_intents)]
            if i % 10 == 0:
                # 10%短查询 (测试规则策略边界)
                keywords = self.KEYWORDS.get(intent, ["查询"])
                query = self._rng.choice(keywords)
            elif i % 10 == 1:
                # 10%长查询 (测试LLM策略)
                query = self.generate_query(intent) + "，顺便问一下还有别的推荐吗"
            else:
                query = self.generate_query(intent)
            result.append((query, intent))

        return result

    def generate_rule_test_queries(self, count: int) -> List[Tuple[str, str]]:
        """生成规则匹配测试查询 (用于INT-03)

        规则匹配特点:
        - 短查询为主 (len < 50)
        - 包含明确关键词
        - 测试各种关键词组合

        Args:
            count: 查询数量

        Returns:
            List[Tuple[query_text, expected_intent]]
        """
        all_intents = ["itinerary", "query", "hotel", "food", "budget", "transport"]
        result = []

        for i in range(count):
            intent = all_intents[i % len(all_intents)]
            # 生成短查询 (主要是关键词)
            keywords = self.KEYWORDS.get(intent, [])
            if keywords:
                query = self._rng.choice(keywords)
            else:
                query = self._rng.choice(self.TEMPLATES.get(intent, ["查询"]))
            result.append((query, intent))

        return result

    def generate_llm_fallback_queries(self, count: int) -> List[Tuple[str, str]]:
        """生成需要LLM fallback的查询 (用于INT-04)

        LLM fallback特点:
        - 复杂的查询
        - 包含多种意图关键词 (需要澄清)
        - 边界/模糊查询

        Args:
            count: 查询数量

        Returns:
            List[Tuple[query_text, expected_intent]]
        """
        all_intents = ["itinerary", "query", "hotel", "food", "budget", "transport"]
        result = []

        # 复杂/模糊查询模板
        complex_templates = [
            "我想去{}旅游，不知道怎么安排行程比较合适，大概需要几天时间合适？",
            "周末想去{}玩两天，有什么好玩的地方推荐吗？需要提前准备什么？",
            "{}和{}哪个更好玩？给个建议呗",
            "有没有适合一家三口{}日游的方案？预算不要太贵",
            "第一次去{}，有什么必去的景点和需要注意的事项？",
        ]

        for i in range(count):
            intent = all_intents[i % len(all_intents)]
            if i % 3 == 0:
                # 1/3使用复杂模板
                template = self._rng.choice(complex_templates)
                query = template.format(
                    self._rng.choice(self._destinations),
                    self._rng.choice(self._destinations),
                    self._rng.choice(self._durations),
                )
            else:
                # 2/3使用普通查询 (模拟cache miss的情况)
                query = self.generate_query(intent)
                # 添加干扰词使其更复杂
                if "?" not in query:
                    query = query + "，有什么建议吗"
            result.append((query, intent))

        return result
