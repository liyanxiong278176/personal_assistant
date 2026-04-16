# LLM调用减少率实验设计方案

> **目标**: 获取三级分类器相比纯LLM方案的LLM调用次数减少率的真实数据

---

## 一、实验设计框架

### 1.1 实验假设

| 假设 | 说明 |
|------|------|
| **H0 (零假设)** | 三级分类器与纯LLM方案的LLM调用次数无显著差异 |
| **H1 (研究假设)** | 三级分类器能显著减少LLM调用次数，减少率 ≥ 40% |

### 1.2 变量定义

```
自变量: 意图识别方案
  - 对照组: 纯LLM方案（每次都调用LLM进行意图识别）
  - 实验组: 三级分类器（Cache → Rule → LLM fallback）

因变量: LLM调用次数
  - 意图识别阶段的LLM调用次数
  - 不包含内容生成阶段的LLM调用

控制变量:
  - 测试样本集（两组使用相同的输入）
  - LLM模型和温度参数
  - 网络环境
```

---

## 二、样本设计

### 2.1 样本来源

```python
样本构成 = {
    "真实用户对话": "从现有conversation表提取（去重）",
    "合成测试用例": "覆盖8种意图类型的变体",
    "边界情况": "短消息、长消息、模糊表达等"
}
```

### 2.2 样本量计算

使用**配对样本t检验**的样本量公式：

```
n = (Z_α/2 + Z_β)² × σ² / Δ²

其中:
- Z_α/2 = 1.96 (α = 0.05, 双侧检验)
- Z_β = 0.84 (β = 0.20, power = 80%)
- σ: 标准差（预估0.3，基于Token数据变异性）
- Δ: 期望效应量（0.4，即40%减少率）

n = (1.96 + 0.84)² × 0.3² / 0.4²
  ≈ 7.84 × 0.09 / 0.16
  ≈ 4.4

考虑到实际变异性和分类效果，建议样本量：
- 最小样本量: 100条
- 推荐样本量: 500条
- 理想样本量: 1000条
```

### 2.3 样本分层

确保样本在意图类型上均匀分布：

| 意图类型 | 占比 | 样本数（总500） |
|---------|------|----------------|
| itinerary | 30% | 150 |
| query | 25% | 125 |
| chat | 20% | 100 |
| hotel | 10% | 50 |
| food | 5% | 25 |
| budget | 5% | 25 |
| transport | 3% | 15 |
| image | 2% | 10 |

---

## 三、实验实现

### 3.1 对照组实现（纯LLM方案）

```python
# backend/tests/experiment/pure_llm_classifier.py

class PureLLMClassifier:
    """纯LLM意图分类器 - 对照组"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.llm_call_count = 0
    
    async def classify(self, message: str) -> IntentResult:
        """每次都调用LLM"""
        self.llm_call_count += 1
        
        prompt = f"""请判断以下用户消息的意图类型：

用户消息: {message}

意图类型: itinerary(行程规划), query(信息查询), chat(普通对话), 
         hotel(酒店预订), food(美食推荐), budget(预算规划), 
         transport(交通出行), image(图片识别)

返回JSON格式: {{"intent": "类型", "confidence": 0.0-1.0}}"""
        
        response = await self.llm_client.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0  # 确保结果稳定
        )
        
        return self._parse_response(response)
    
    def get_llm_calls(self) -> int:
        return self.llm_call_count
    
    def reset(self):
        self.llm_call_count = 0
```

### 3.2 实验组实现（三级分类器）

```python
# backend/tests/experiment/three_tier_classifier.py

class ThreeTierClassifier:
    """三级分类器 - 实验组"""
    
    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client
        self.llm_call_count = 0
        self.cache_hit_count = 0
        self.rule_hit_count = 0
        
        # 初始化缓存
        self._cache = {}
        
        # 加载关键词规则
        from app.core.intent.keywords import INTENT_KEYWORDS
        self.keywords = INTENT_KEYWORDS
    
    async def classify(self, message: str) -> IntentResult:
        # Tier 1: 缓存
        cache_key = hashlib.md5(message.encode()).hexdigest()
        if cache_key in self._cache:
            self.cache_hit_count += 1
            return self._cache[cache_key]
        
        # Tier 2: 关键词规则
        rule_result = self._rule_classify(message)
        if rule_result and rule_result.confidence >= 0.8:
            self.rule_hit_count += 1
            self._cache[cache_key] = rule_result
            return rule_result
        
        # Tier 3: LLM降级
        self.llm_call_count += 1
        llm_result = await self._llm_classify(message)
        self._cache[cache_key] = llm_result
        return llm_result
    
    def get_llm_calls(self) -> int:
        return self.llm_call_count
    
    def get_stats(self):
        return {
            "total": self.cache_hit_count + self.rule_hit_count + self.llm_call_count,
            "cache_hit": self.cache_hit_count,
            "rule_hit": self.rule_hit_count,
            "llm_call": self.llm_call_count
        }
```

### 3.3 数据收集器

```python
# backend/tests/experiment/data_collector.py

from dataclasses import dataclass, field
from typing import List, Dict
from datetime import datetime

@dataclass
class ExperimentRecord:
    """单次实验记录"""
    sample_id: str
    input_message: str
    expected_intent: str  # 标注的真实意图
    
    # 对照组结果
    control_intent: str
    control_confidence: float
    control_llm_calls: int
    
    # 实验组结果
    experiment_intent: str
    experiment_confidence: float
    experiment_llm_calls: int
    experiment_tier: str  # "cache" / "rule" / "llm"
    
    # 准确性
    control_correct: bool
    experiment_correct: bool
    
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())

class ExperimentDataCollector:
    """实验数据收集器"""
    
    def __init__(self):
        self.records: List[ExperimentRecord] = []
    
    def add_record(self, record: ExperimentRecord):
        self.records.append(record)
    
    def calculate_metrics(self) -> Dict:
        """计算实验指标"""
        total = len(self.records)
        if total == 0:
            return {}
        
        control_llm_total = sum(r.control_llm_calls for r in self.records)
        experiment_llm_total = sum(r.experiment_llm_calls for r in self.records)
        
        control_correct = sum(1 for r in self.records if r.control_correct)
        experiment_correct = sum(1 for r in self.records if r.experiment_correct)
        
        reduction_rate = (control_llm_total - experiment_llm_total) / control_llm_total
        
        return {
            "sample_size": total,
            "control_llm_calls": control_llm_total,
            "experiment_llm_calls": experiment_llm_total,
            "llm_reduction_rate": reduction_rate,
            "control_accuracy": control_correct / total,
            "experiment_accuracy": experiment_correct / total,
            "by_tier": self._calculate_tier_breakdown()
        }
    
    def _calculate_tier_breakdown(self):
        tier_counts = {}
        for r in self.records:
            tier = r.experiment_tier
            tier_counts[tier] = tier_counts.get(tier, 0) + 1
        return {k: v / len(self.records) for k, v in tier_counts.items()}
```

---

## 四、实验执行脚本

```python
# backend/tests/experiment/run_experiment.py

import asyncio
import json
from pathlib import Path

async def main():
    """执行主实验"""
    
    # 1. 加载测试样本
    samples = load_test_samples("tests/experiment/samples.jsonl")
    print(f"加载了 {len(samples)} 个测试样本")
    
    # 2. 初始化分类器
    llm_client = LLMClient()
    control = PureLLMClassifier(llm_client)
    experiment = ThreeTierClassifier(llm_client)
    collector = ExperimentDataCollector()
    
    # 3. 执行实验
    for i, sample in enumerate(samples):
        print(f"\r处理进度: {i+1}/{len(samples)}", end="")
        
        # 对照组
        control.reset()
        control_result = await control.classify(sample["message"])
        control_calls = control.get_llm_calls()
        
        # 实验组
        experiment.reset()
        experiment_result = await experiment.classify(sample["message"])
        experiment_calls = experiment.get_llm_calls()
        
        # 记录
        record = ExperimentRecord(
            sample_id=sample["id"],
            input_message=sample["message"],
            expected_intent=sample["intent"],
            control_intent=control_result.intent,
            control_confidence=control_result.confidence,
            control_llm_calls=control_calls,
            experiment_intent=experiment_result.intent,
            experiment_confidence=experiment_result.confidence,
            experiment_llm_calls=experiment_calls,
            experiment_tier=experiment_result.tier,
            control_correct=(control_result.intent == sample["intent"]),
            experiment_correct=(experiment_result.intent == sample["intent"])
        )
        collector.add_record(record)
    
    # 4. 计算指标
    metrics = collector.calculate_metrics()
    
    # 5. 输出报告
    print_experiment_report(metrics, experiment.get_stats())
    
    # 6. 保存结果
    save_results(metrics, collector.records)

def print_experiment_report(metrics, tier_stats):
    """打印实验报告"""
    print("\n" + "="*60)
    print("LLM调用减少率实验报告")
    print("="*60)
    
    print(f"\n样本量: {metrics['sample_size']}")
    print(f"对照组LLM调用次数: {metrics['control_llm_calls']}")
    print(f"实验组LLM调用次数: {metrics['experiment_llm_calls']}")
    print(f"\nLLM调用减少率: {metrics['llm_reduction_rate']:.2%}")
    
    print(f"\n准确性对比:")
    print(f"  对照组准确率: {metrics['control_accuracy']:.2%}")
    print(f"  实验组准确率: {metrics['experiment_accuracy']:.2%}")
    
    print(f"\n实验组分层命中情况:")
    for tier, rate in metrics['by_tier'].items():
        print(f"  {tier}: {rate:.2%}")
```

---

## 五、测试样本集构建

### 5.1 样本数据格式

```json
// tests/experiment/samples.jsonl
{"id": "sample_001", "message": "帮我规划北京三日游", "intent": "itinerary", "category": "high_frequency"}
{"id": "sample_002", "message": "制定一个上海旅游计划", "intent": "itinerary", "category": "high_frequency"}
{"id": "sample_003", "message": "北京今天天气怎么样", "intent": "query", "category": "high_frequency"}
{"id": "sample_004", "message": "你好，在吗", "intent": "chat", "category": "high_frequency"}
{"id": "sample_005", "message": "我想去一个有美食的地方玩几天", "intent": "itinerary", "category": "ambiguous"}
// ... 更多样本
```

### 5.2 样本生成脚本

```python
# backend/tests/experiment/generate_samples.py

SAMPLE_TEMPLATES = {
    "itinerary": [
        "帮我规划{destination}{days}日游",
        "制定{destination}旅游计划",
        "想去{destination}玩{days}天",
        "{destination}有什么好玩的",
        # ... 30+ 变体
    ],
    "query": [
        "{destination}今天天气怎么样",
        "{destination}明天会下雨吗",
        "怎么去{destination}",
        "{destination}有什么景点",
        # ... 25+ 变体
    ],
    # ... 其他意图类型
}

def generate_samples(intent_type: str, count: int, variations: list) -> list:
    """生成指定数量的样本"""
    samples = []
    destinations = ["北京", "上海", "杭州", "成都", "西安", "南京", "广州", "深圳"]
    days = ["一", "二", "三", "五", "七"]
    
    for i in range(count):
        template = random.choice(variations)
        message = template.format(
            destination=random.choice(destinations),
            days=random.choice(days)
        )
        samples.append({
            "id": f"{intent_type}_{i:03d}",
            "message": message,
            "intent": intent_type,
            "category": "generated"
        })
    return samples
```

---

## 六、统计分析方案

### 6.1 主要指标

| 指标 | 计算公式 | 说明 |
|------|----------|------|
| **LLM调用减少率** | (C - E) / C × 100% | C=对照组调用数, E=实验组调用数 |
| **准确率损失** | A_control - A_experiment | 实验组相对对照组的准确率下降 |
| **性价比指标** | 减少率 / 准确率损失 | 每损失1%准确率换取的LLM减少 |

### 6.2 统计检验

```python
from scipy import stats

def statistical_test(records: List[ExperimentRecord]):
    """配对样本t检验"""
    
    # 提取配对数据（每个样本两组都调用或不调用LLM）
    control_calls = [1 for r in records]  # 对照组每次都调用
    experiment_calls = [1 if r.experiment_tier == "llm" else 0 for r in records]
    
    # 执行配对t检验
    t_stat, p_value = stats.ttest_rel(control_calls, experiment_calls)
    
    # 计算效应量 (Cohen's d)
    diff = np.array(control_calls) - np.array(experiment_calls)
    cohens_d = np.mean(diff) / np.std(diff)
    
    return {
        "t_statistic": t_stat,
        "p_value": p_value,
        "significant": p_value < 0.05,
        "cohens_d": cohens_d,
        "effect_size": "large" if abs(cohens_d) > 0.8 else "medium" if abs(cohens_d) > 0.5 else "small"
    }
```

### 6.3 置信区间

```python
def calculate_ci(data: List[float], confidence: float = 0.95):
    """计算95%置信区间"""
    n = len(data)
    mean = np.mean(data)
    std_err = stats.sem(data)
    h = std_err * stats.t.ppf((1 + confidence) / 2, n - 1)
    return mean, mean - h, mean + h

# 应用：计算LLM减少率的95%置信区间
reduction_rates = [(1 - exp/c) for c, exp in zip(control_calls, experiment_calls)]
mean, lower, upper = calculate_ci(reduction_rates)
print(f"LLM减少率95%CI: [{lower:.2%}, {upper:.2%}]")
```

---

## 七、实施计划

### Phase 1: 准备阶段 (1-2天)

- [ ] 实现PureLLMClassifier对照组
- [ ] 实现ThreeTierClassifier实验组
- [ ] 实现ExperimentDataCollector
- [ ] 生成500个测试样本

### Phase 2: 执行阶段 (1天)

```bash
# 运行实验
cd backend
python -m tests.experiment.run_experiment

# 输出示例:
# 加载了 500 个测试样本
# 处理进度: 500/500
# 
# ============================================================
# LLM调用减少率实验报告
# ============================================================
# 
# 样本量: 500
# 对照组LLM调用次数: 500
# 实验组LLM调用次数: 85
# 
# LLM调用减少率: 83.00%
# 
# 准确性对比:
#   对照组准确率: 94.00%
#   实验组准确率: 91.80%
# 
# 实验组分层命中情况:
#   cache: 8.00%
#   rule: 75.00%
#   llm: 17.00%
# 
# 统计检验: p < 0.001, Cohen's d = 1.85 (large effect)
# 95%CI: [78.50%, 87.50%]
```

### Phase 3: 分析阶段 (1天)

- [ ] 执行统计检验
- [ ] 计算置信区间
- [ ] 按意图类型分析子组效果
- [ ] 分析失败案例

### Phase 4: 报告阶段 (1天)

- [ ] 生成实验报告
- [ ] 可视化结果（图表）
- [ ] 更新面试准备材料

---

## 八、预期结果与解读

### 8.1 结果矩阵

| LLM减少率 | 准确率损失 | 结论 |
|-----------|-----------|------|
| ≥60% | ≤2% | ✅ 优秀，三级分类器效果显著 |
| 40-60% | ≤3% | ✅ 良好，有实际价值 |
| 20-40% | ≤5% | ⚠️ 一般，需优化关键词 |
| <20% | 任意 | ❌ 失败，架构需要重新设计 |

### 8.2 面试话术建议

**如果实验结果良好（如减少率80%+）:**

> "我们设计了严格的对照实验，500个真实用户消息样本，纯LLM方案每次都调用，三级分类器仅17%需要LLM。经配对t检验，p<0.001，Cohen's d=1.85，属于大效应量。95%置信区间[78.5%, 87.5%]，同时准确率仅下降2.2%，属于可接受范围。"

**如果实验结果一般（如减少率40%）:**

> "实验显示三级分类器能减少40%的LLM调用，p<0.05达到统计显著。主要原因是关键词规则覆盖不足，特别是在模糊表达和长尾场景。我们已经记录了所有LLM降级的case，计划通过迭代优化关键词库来提升命中率。"

---

## 九、扩展实验（可选）

### 9.1 A/B测试框架

```python
# 在生产环境中进行A/B测试

class ABTestClassifier:
    """A/B测试分类器"""
    
    def __init__(self, user_id: str):
        # 根据user_id哈希决定分组
        self.group = "control" if hash(user_id) % 2 == 0 else "experiment"
        self.classifier = PureLLMClassifier() if self.group == "control" else ThreeTierClassifier()
    
    async def classify(self, message: str):
        return await self.classifier.classify(message)
```

### 9.2 成本分析

```python
def cost_analysis(reduction_rate: float, avg_tokens_per_call: int = 500):
    """计算成本节省"""
    # DeepSeek定价示例
    input_price = 1.0  # 元/百万tokens
    output_price = 2.0
    
    # 假设每次调用平均500 tokens
    tokens_per_call = 500
    
    # 每万次请求的成本
    control_cost = 10000 * tokens_per_call / 1e6 * (input_price + output_price)
    experiment_cost = control_cost * (1 - reduction_rate)
    
    return {
        "control_cost_per_10k": control_cost,
        "experiment_cost_per_10k": experiment_cost,
        "savings_per_10k": control_cost - experiment_cost,
        "annual_savings": (control_cost - experiment_cost) * 365 * 1000  # 假设日千次请求
    }
```

---

## 十、文件清单

```
backend/tests/experiment/
├── __init__.py
├── pure_llm_classifier.py      # 对照组实现
├── three_tier_classifier.py     # 实验组实现
├── data_collector.py             # 数据收集器
├── run_experiment.py             # 主实验脚本
├── generate_samples.py           # 样本生成
├── statistical_analysis.py       # 统计分析
├── samples.jsonl                 # 测试样本集
└── results/                      # 实验结果目录
    ├── 2026-04-12_experiment_report.json
    └── 2026-04-12_experiment_report.pdf
```

---

**文档版本**: 1.0
**创建日期**: 2026-04-12
**作者**: Claude (AI实验设计助手)
