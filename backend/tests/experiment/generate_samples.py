"""测试样本生成器

生成用于实验的测试样本集。
"""

import json
import random
from typing import List, Dict
from pathlib import Path


class SampleGenerator:
    """测试样本生成器"""

    # 意图类型模板
    TEMPLATES = {
        "itinerary": {
            "templates": [
                "帮我规划{destination}{days}日游",
                "制定{destination}旅游计划",
                "想去{destination}玩{days}天",
                "{destination}有什么好玩的",
                "推荐{destination}的旅游路线",
                "{destination}{days}天行程安排",
                "我想去{destination}旅游",
                "{destination}旅游攻略",
                "帮我安排{destination}之行",
                "{destination}景点推荐"
            ],
            "destinations": ["北京", "上海", "杭州", "成都", "西安", "南京", "广州", "深圳", "重庆", "武汉"],
            "days": ["一", "二", "三", "五", "七"]
        },
        "query": {
            "templates": [
                "{destination}今天天气怎么样",
                "{destination}明天会下雨吗",
                "怎么去{destination}",
                "{destination}有什么景点",
                "{destination}门票价格",
                "{destination}开放时间",
                "{destination}到{destination2}多远",
                "{destination}交通指南",
                "{destination}景点地址",
                "{destination}这几天天气"
            ],
            "destinations": ["北京", "上海", "杭州", "成都", "西安"],
            "destinations2": ["天津", "苏州", "重庆", "武汉", "广州"]
        },
        "chat": {
            "templates": [
                "你好",
                "在吗",
                "谢谢",
                "哈哈",
                "再见",
                "早上好",
                "晚上好",
                "嗨",
                "嘿",
                "你好啊"
            ],
            "destinations": [],
            "days": []
        },
        "hotel": {
            "templates": [
                "帮我找{destination}的酒店",
                "{destination}有什么好住的",
                "{destination}民宿推荐",
                "{destination}经济型酒店",
                "{destination}住宿攻略",
                "在{destination}住哪里好",
                "{destination}酒店预订",
                "{destination}便宜的住宿"
            ],
            "destinations": ["北京", "上海", "杭州", "成都"],
            "days": []
        },
        "food": {
            "templates": [
                "{destination}有什么好吃的",
                "{destination}美食推荐",
                "{destination}特色菜",
                "{destination}小吃街",
                "{destination}餐厅推荐",
                "{destination}必吃美食",
                "{destination}有什么特产",
                "{destination}美食攻略"
            ],
            "destinations": ["北京", "上海", "成都", "广州", "重庆"],
            "days": []
        },
        "budget": {
            "templates": [
                "{destination}{days}日游大概多少钱",
                "{destination}旅游预算",
                "去{destination}要花多少钱",
                "{destination}便宜旅游攻略",
                "{destination}穷游",
                "{destination}旅游费用",
                "{destination}一日游多少钱",
                "{destination}经济游"
            ],
            "destinations": ["北京", "上海", "杭州", "成都"],
            "days": ["一", "二", "三", "五"]
        },
        "transport": {
            "templates": [
                "怎么去{destination}",
                "{destination}交通指南",
                "到{destination}坐什么车",
                "{destination}有高铁吗",
                "{destination}飞机票",
                "{destination}怎么走",
                "{destination}自驾路线",
                "{destination}交通攻略"
            ],
            "destinations": ["北京", "上海", "杭州", "成都", "西安"],
            "days": []
        },
        "image": {
            "templates": [
                "识别这张图片",
                "这是什么地方",
                "这是哪里",
                "图片中是哪",
                "帮我看看这张照片",
                "识别景点"
            ],
            "destinations": [],
            "days": []
        }
    }

    # 模糊表达样本（用于测试边界情况）
    AMBIGUOUS_TEMPLATES = {
        "itinerary": [
            "我想去一个有美食的地方玩几天",
            "推荐个好玩的短期旅行",
            "计划一次放松的旅行",
            "想出去玩几天"
        ],
        "query": [
            "那里天气怎么样",
            "这个地方怎么去",
            "那边有什么好玩的",
            "这个景点门票多少钱"
        ]
    }

    # 边界情况样本
    EDGE_CASE_TEMPLATES = {
        "chat": [
            "",
            " ",
            "？？？",
            "ok",
            "好的",
            "嗯",
            "啊",
            "..."
        ],
        "itinerary": [
            "规划行程",  # 极短
            "帮我规划北京三日游，我们要去故宫、长城、颐和园，还有天坛，另外我们喜欢吃辣的菜，预算控制在3000元以内，希望住在市中心交通便利的地方，另外还想了解一下当地有什么特色小吃可以推荐的"  # 极长
        ]
    }

    @classmethod
    def generate(
        cls,
        total: int = 500,
        distribution: Dict[str, float] = None,
        seed: int = 42
    ) -> List[Dict]:
        """生成测试样本

        Args:
            total: 总样本数
            distribution: 意图类型分布比例，默认均匀分布
            seed: 随机种子

        Returns:
            样本列表
        """
        random.seed(seed)

        if distribution is None:
            # 默认分布：接近实际使用场景
            distribution = {
                "itinerary": 0.30,
                "query": 0.25,
                "chat": 0.20,
                "hotel": 0.10,
                "food": 0.05,
                "budget": 0.05,
                "transport": 0.03,
                "image": 0.02
            }

        samples = []

        for intent, ratio in distribution.items():
            count = int(total * ratio)
            intent_samples = cls._generate_intent_samples(intent, count)
            samples.extend(intent_samples)

        # 添加一些模糊表达和边界情况
        ambiguous_count = int(total * 0.05)  # 5% 模糊样本
        edge_count = int(total * 0.02)  # 2% 边界样本

        samples.extend(cls._generate_ambiguous_samples(ambiguous_count))
        samples.extend(cls._generate_edge_case_samples(edge_count))

        # 打乱顺序
        random.shuffle(samples)

        # 重新分配ID
        for i, sample in enumerate(samples):
            sample["id"] = f"sample_{i:04d}"

        return samples

    @classmethod
    def _generate_intent_samples(cls, intent: str, count: int) -> List[Dict]:
        """生成特定意图的样本"""
        samples = []
        config = cls.TEMPLATES.get(intent, cls.TEMPLATES["chat"])

        for i in range(count):
            template = random.choice(config["templates"])

            # 填充模板
            try:
                dests = config.get("destinations", ["北京"])
                dests2 = config.get("destinations2", dests)
                days_list = config.get("days", [""])

                message = template.format(
                    destination=random.choice(dests) if dests else "",
                    destination2=random.choice(dests2) if dests2 else "",
                    days=random.choice(days_list) if days_list else ""
                )
            except (KeyError, IndexError):
                # 模板不需要某些参数或列表为空
                message = template

            samples.append({
                "id": f"{intent}_{i:04d}",
                "message": message,
                "intent": intent,
                "category": "high_frequency"
            })

        return samples

    @classmethod
    def _generate_ambiguous_samples(cls, count: int) -> List[Dict]:
        """生成模糊表达样本"""
        samples = []
        all_templates = []

        for intent, templates in cls.AMBIGUOUS_TEMPLATES.items():
            for template in templates:
                all_templates.append((template, intent))

        for i in range(count):
            if all_templates:
                template, intent = random.choice(all_templates)
                samples.append({
                    "id": f"ambiguous_{i:04d}",
                    "message": template,
                    "intent": intent,
                    "category": "ambiguous"
                })

        return samples

    @classmethod
    def _generate_edge_case_samples(cls, count: int) -> List[Dict]:
        """生成边界情况样本"""
        samples = []
        all_templates = []

        for intent, templates in cls.EDGE_CASE_TEMPLATES.items():
            for template in templates:
                all_templates.append((template, intent))

        for i in range(count):
            if all_templates:
                template, intent = random.choice(all_templates)
                samples.append({
                    "id": f"edge_{i:04d}",
                    "message": template,
                    "intent": intent,
                    "category": "edge_case"
                })

        return samples

    @classmethod
    def save(cls, samples: List[Dict], filepath: str = None):
        """保存样本到文件

        Args:
            samples: 样本列表
            filepath: 保存路径，默认为tests/experiment/samples.jsonl
        """
        if filepath is None:
            filepath = "tests/experiment/samples.jsonl"

        filepath = Path(filepath)
        filepath.parent.mkdir(parents=True, exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            for sample in samples:
                f.write(json.dumps(sample, ensure_ascii=False) + '\n')

        print(f"[OK] Saved {len(samples)} samples to: {filepath}")

    @classmethod
    def load(cls, filepath: str = None) -> List[Dict]:
        """从文件加载样本

        Args:
            filepath: 样本文件路径

        Returns:
            样本列表
        """
        if filepath is None:
            filepath = "tests/experiment/samples.jsonl"

        filepath = Path(filepath)

        if not filepath.exists():
            # 如果文件不存在，生成并保存
            print(f"[WARN] Sample file not exists, generating...")
            samples = cls.generate()
            cls.save(samples, str(filepath))
            return samples

        samples = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    samples.append(json.loads(line))

        print(f"[OK] Loaded {len(samples)} samples")
        return samples


def generate_samples_command():
    """命令行入口：生成样本"""
    import argparse

    parser = argparse.ArgumentParser(description="生成实验测试样本")
    parser.add_argument("-n", "--count", type=int, default=500, help="样本数量")
    parser.add_argument("-o", "--output", type=str, default="tests/experiment/samples.jsonl", help="输出文件路径")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")

    args = parser.parse_args()

    samples = SampleGenerator.generate(total=args.count, seed=args.seed)
    SampleGenerator.save(samples, args.output)

    # 打印分布统计
    intent_counts = {}
    for s in samples:
        intent = s["intent"]
        intent_counts[intent] = intent_counts.get(intent, 0) + 1

    print("\n样本分布:")
    for intent, count in sorted(intent_counts.items()):
        print(f"  {intent}: {count} ({count/len(samples):.1%})")


if __name__ == "__main__":
    generate_samples_command()
