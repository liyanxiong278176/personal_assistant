# SHAP值候选值定义 - 完整操作指南

## 实战教程：如何在意图识别系统中使用SHAP值

---

## 准备工作

### 1. 安装依赖

```bash
pip install shap scikit-learn numpy pandas
```

---

## 第一阶段：数据准备

### 步骤1：准备训练数据

```python
import pandas as pd
import numpy as np

# 示例：意图识别训练数据
training_data = pd.DataFrame({
    "用户输入": [
        "帮我规划北京行程",
        "聊聊北京旅游",
        "推荐上海景点",
        "查询北京天气",
        "规划上海旅游路线",
        "想聊聊天",
        "帮我推荐餐厅",
        "查询明天天气",
    ],
    "意图标签": [
        "itinerary",   # 行程规划
        "itinerary",   # 行程规划
        "query",       # 景点查询
        "weather",     # 天气查询
        "itinerary",   # 行程规划
        "chat",        # 闲聊
        "food",        # 美食推荐
        "weather",     # 天气查询
    ]
})

print(training_data)
```

---

### 步骤2：关键词提取和特征工程

```python
from sklearn.feature_extraction.text import CountVectorizer

# 定义关键词列表（业务定义的关键词）
keywords = ["规划", "聊聊", "推荐", "查询", "行程", "旅游", "景点", "天气", "餐厅", "聊天"]

# 创建关键词特征矩阵
vectorizer = CountVectorizer(vocabulary=keywords)
X_train = vectorizer.fit_transform(training_data["用户输入"])

# 转换为DataFrame查看
X_train_df = pd.DataFrame(X_train.toarray(), columns=keywords)
print("特征矩阵：")
print(X_train_df)

# 输出示例：
#    规划  聊聊  推荐  查询  行程  旅游  景点  天气  餐厅  聊天
# 0   1    0    0    0    1    0    0    0    0    0   # "帮我规划北京行程"
# 1   0    1    0    0    0    1    0    0    0    0   # "聊聊北京旅游"
# 2   0    0    1    0    0    0    1    0    0    0   # "推荐上海景点"
# 3   0    0    0    1    0    0    0    1    0    0   # "查询北京天气"
# ...

y_train = training_data["意图标签"]
```

---

## 第二阶段：训练模型和计算SHAP值

### 步骤3：训练意图识别模型

```python
from sklearn.ensemble import RandomForestClassifier

# 训练随机森林模型（示例）
model = RandomForestClassifier(
    n_estimators=100,
    random_state=42,
)
model.fit(X_train, y_train)

# 验证模型准确率
accuracy = model.score(X_train, y_train)
print(f"训练集准确率: {accuracy:.2%}")
```

---

### 步骤4：计算SHAP值（核心步骤）

```python
import shap

# 创建SHAP解释器
explainer = shap.TreeExplainer(model)

# 对训练数据计算SHAP值
shap_values = explainer.shap_values(X_train)

# 注意：shap_values 是一个列表，每个元素对应一个类别
# 我们取主要类别（假设是 itinerary）的SHAP值
intent_index = model.classes_.tolist().index("itinerary")  # 获取"行程规划"类别的索引
shap_values_intent = shap_values[intent_index]

# 计算每个关键词的平均SHAP值（绝对值）
avg_shap_values = np.abs(shap_values_intent).mean(axis=0)

# 创建关键词-SHAP值映射
keyword_shap = dict(zip(keywords, avg_shap_values))

print("关键词SHAP值分析：")
for keyword, shap_val in sorted(keyword_shap.items(), key=lambda x: x[1], reverse=True):
    print(f"  {keyword:8s}: {shap_val:.3f}")

# 输出示例：
# 关键词SHAP值分析：
#   规划    : 0.042  # ⭐ 最重要
#   行程    : 0.035  # 重要
#   推荐    : 0.028
#   查询    : 0.025
#   聊聊    : 0.018  # 次要
#   天气    : 0.015
#   旅游    : 0.012
#   景点    : 0.010
#   餐厅    : 0.008
#   聊天    : 0.005  # 不重要
```

---

## 第三阶段：设定候选值范围

### 步骤5：根据SHAP值自动生成候选值

```python
def generate_candidate_ranges(keyword_shap, thresholds=None):
    """根据SHAP值自动生成候选值范围

    Args:
        keyword_shap: 关键词-SHAP值映射字典
        thresholds: SHAP值分类阈值（可选）

    Returns:
        候选值范围字典
    """

    if thresholds is None:
        # 默认阈值（根据数据分布调整）
        thresholds = {
            "important": 0.03,   # 重要特征
            "medium": 0.02,      # 中等重要
            "minor": 0.01,       # 次要特征
        }

    candidates = {}

    for keyword, shap_val in keyword_shap.items():

        # 分类1: 重要关键词（SHAP > 0.03）
        if shap_val > thresholds["important"]:
            # 精细搜索：权重应该较高
            candidates[keyword] = [0.6, 0.7, 0.8, 0.85]

        # 分类2: 中等重要（SHAP ∈ [0.02, 0.03]）
        elif shap_val > thresholds["medium"]:
            # 适中搜索：中等权重
            candidates[keyword] = [0.4, 0.5, 0.6]

        # 分类3: 次要关键词（SHAP ∈ [0.01, 0.02]）
        elif shap_val > thresholds["minor"]:
            # 粗略搜索：较低权重
            candidates[keyword] = [0.2, 0.3, 0.4]

        # 分类4: 不重要（SHAP < 0.01）
        else:
            # 极低权重或排除
            candidates[keyword] = [0.0, 0.1, 0.2]

    return candidates

# 使用示例
candidate_ranges = generate_candidate_ranges(keyword_shap)

print("\n生成的候选值范围：")
for keyword, candidates in sorted(candidate_ranges.items(), key=lambda x: keyword_shap[x[0]], reverse=True):
    print(f"  {keyword:8s}: {candidates}")

# 输出：
# 生成的候选值范围：
#   规划    : [0.6, 0.7, 0.8, 0.85]
#   行程    : [0.6, 0.7, 0.8, 0.85]
#   推荐    : [0.4, 0.5, 0.6]
#   查询    : [0.4, 0.5, 0.6]
#   聊聊    : [0.2, 0.3, 0.4]
#   天气    : [0.2, 0.3, 0.4]
#   旅游    : [0.2, 0.3, 0.4]
#   景点    : [0.0, 0.1, 0.2]
#   餐厅    : [0.0, 0.1, 0.2]
#   聊天    : [0.0, 0.1, 0.2]
```

---

## 第四阶段：超参数搜索

### 步骤6：构建自定义模型（支持关键词权重）

```python
from sklearn.base import BaseEstimator, ClassifierMixin

class WeightedIntentClassifier(BaseEstimator, ClassifierMixin):
    """支持关键词权重的意图识别器"""

    def __init__(self, keyword_weights=None, confidence_threshold=0.8):
        self.keyword_weights = keyword_weights or {}
        self.confidence_threshold = confidence_threshold
        self.base_model = RandomForestClassifier(n_estimators=100, random_state=42)

    def fit(self, X, y):
        # 应用关键词权重到特征矩阵
        X_weighted = self._apply_weights(X)
        self.base_model.fit(X_weighted, y)
        return self

    def predict(self, X):
        X_weighted = self._apply_weights(X)
        return self.base_model.predict(X_weighted)

    def predict_proba(self, X):
        X_weighted = self._apply_weights(X)
        return self.base_model.predict_proba(X_weighted)

    def _apply_weights(self, X):
        """应用关键词权重"""
        X_weighted = X.copy()

        # 如果是稀疏矩阵，转换为密集矩阵
        if hasattr(X_weighted, "toarray"):
            X_weighted = X_weighted.toarray()

        # 应用权重
        for i, keyword in enumerate(self.keywords):
            if keyword in self.keyword_weights:
                X_weighted[:, i] *= self.keyword_weights[keyword]

        return X_weighted

    def set_keywords(self, keywords):
        """设置关键词列表"""
        self.keywords = keywords

# 测试自定义模型
model = WeightedIntentClassifier()
model.set_keywords(keywords)
model.fit(X_train, y_train)

accuracy = model.score(X_train, y_train)
print(f"初始模型准确率: {accuracy:.2%}")
```

---

### 步骤7：网格搜索最佳参数

```python
from sklearn.model_selection import GridSearchCV, cross_val_score

# 准备测试数据（示例）
X_test = vectorizer.transform([
    "规划上海行程",
    "聊聊北京天气",
    "推荐美食餐厅",
])
y_test = ["itinerary", "weather", "food"]

# 构建参数网格
param_grid = {
    # 关键词权重候选值（来自步骤5）
    "keyword_weights": [
        # 从candidate_ranges中选择几个典型组合
        {"规划": 0.7, "行程": 0.7, "聊聊": 0.3, "天气": 0.3, "推荐": 0.5},
        {"规划": 0.8, "行程": 0.8, "聊聊": 0.2, "天气": 0.2, "推荐": 0.6},
        {"规划": 0.85, "行程": 0.85, "聊聊": 0.4, "天气": 0.4, "推荐": 0.5},
    ],
    # 置信度阈值候选值
    "confidence_threshold": [0.75, 0.8, 0.85, 0.9],
}

# 注意：GridSearchCV 不直接支持字典参数，需要自定义搜索
# 这里使用手动网格搜索

def manual_grid_search(X_train, y_train, candidate_ranges, confidence_candidates):
    """手动网格搜索"""

    best_score = 0
    best_params = None

    # 测试不同的关键词权重组合
    test_keywords = ["规划", "行程", "聊聊", "天气", "推荐"]  # 只测试关键关键词

    results = []

    for weight_combo in [
        {"规划": 0.7, "行程": 0.7, "聊聊": 0.3, "天气": 0.3, "推荐": 0.5},
        {"规划": 0.8, "行程": 0.8, "聊聊": 0.2, "天气": 0.2, "推荐": 0.6},
        {"规划": 0.85, "行程": 0.85, "聊聊": 0.4, "天气": 0.4, "推荐": 0.5},
    ]:
        for conf_thresh in confidence_candidates:

            # 训练模型
            model = WeightedIntentClassifier(
                keyword_weights=weight_combo,
                confidence_threshold=conf_thresh,
            )
            model.set_keywords(test_keywords)
            model.fit(X_train, y_train)

            # 评估准确率
            score = model.score(X_train, y_train)

            results.append({
                "weights": weight_combo,
                "threshold": conf_thresh,
                "accuracy": score,
            })

            if score > best_score:
                best_score = score
                best_params = {
                    "keyword_weights": weight_combo,
                    "confidence_threshold": conf_thresh,
                }

    return best_params, best_score, results

# 执行搜索
best_params, best_score, results = manual_grid_search(
    X_train,
    y_train,
    candidate_ranges,
    [0.75, 0.8, 0.85, 0.9],
)

print("\n网格搜索结果：")
for result in results:
    print(f"权重组合: {result['weights']}")
    print(f"置信度阈值: {result['threshold']}")
    print(f"准确率: {result['accuracy']:.2%}")
    print()

print(f"\n✅ 最佳参数：")
print(f"关键词权重: {best_params['keyword_weights']}")
print(f"置信度阈值: {best_params['confidence_threshold']}")
print(f"最佳准确率: {best_score:.2%}")
```

---

## 第五阶段：应用最佳参数

### 步骤8：保存最佳参数到配置文件

```python
import yaml

# 保存到配置文件
config = {
    "intent_keywords": {
        "weights": best_params["keyword_weights"],
        "confidence_threshold": best_params["confidence_threshold"],
    },
    "shap_analysis": {
        "keyword_importance": keyword_shap,
        "candidate_ranges": candidate_ranges,
    },
}

with open("config/intent_keywords.yaml", "w") as f:
    yaml.dump(config, f, allow_unicode=True)

print("\n配置已保存到 config/intent_keywords.yaml")
```

---

### 步骤9：集成到意图识别系统

```python
# 在意图识别器中使用最佳参数

class ProductionIntentClassifier:
    """生产环境意图识别器（使用优化后的参数）"""

    def __init__(self, config_path="config/intent_keywords.yaml"):
        # 加载配置
        with open(config_path) as f:
            config = yaml.safe_load(f)

        self.keyword_weights = config["intent_keywords"]["weights"]
        self.confidence_threshold = config["intent_keywords"]["confidence_threshold"]

        # 加载模型
        self.model = WeightedIntentClassifier(
            keyword_weights=self.keyword_weights,
            confidence_threshold=self.confidence_threshold,
        )
        self.model.set_keywords(list(self.keyword_weights.keys()))
        self.model.fit(X_train, y_train)  # 使用历史数据训练

        self.vectorizer = CountVectorizer(vocabulary=self.keyword_weights.keys())

    def predict_intent(self, user_input):
        """预测用户意图"""

        # 提取关键词特征
        features = self.vectorizer.transform([user_input])

        # 预测意图和置信度
        intent = self.model.predict(features)[0]
        proba = self.model.predict_proba(features)[0]
        confidence = max(proba)

        # 判断是否需要澄清
        needs_clarification = confidence < self.confidence_threshold

        return {
            "intent": intent,
            "confidence": confidence,
            "needs_clarification": needs_clarification,
        }

# 测试生产环境模型
classifier = ProductionIntentClassifier()

test_inputs = [
    "帮我规划北京行程",
    "聊聊北京天气",
    "推荐美食餐厅",
]

print("\n生产环境测试：")
for user_input in test_inputs:
    result = classifier.predict_intent(user_input)
    print(f"输入: {user_input}")
    print(f"  意图: {result['intent']}")
    print(f"  置信度: {result['confidence']:.2%}")
    print(f"  需要澄清: {result['needs_clarification']}")
    print()
```

---

## 完整自动化脚本

将所有步骤整合为一个自动化脚本：

```python
# backend/scripts/optimize_intent_keywords.py

import shap
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
import yaml

def optimize_intent_keywords(training_data_path, output_config_path):
    """自动化SHAP值分析和候选值生成"""

    # === 阶段1: 数据准备 ===
    print("=== 阶段1: 加载训练数据 ===")
    training_data = pd.read_csv(training_data_path)

    keywords = ["规划", "聊聊", "推荐", "查询", "行程", "旅游", "景点", "天气", "餐厅", "聊天"]
    vectorizer = CountVectorizer(vocabulary=keywords)
    X_train = vectorizer.fit_transform(training_data["用户输入"])
    y_train = training_data["意图标签"]

    # === 阶段2: 训练模型 ===
    print("\n=== 阶段2: 训练模型 ===")
    model = RandomForestClassifier(n_estimators=100, random_state=42)
    model.fit(X_train, y_train)
    print(f"训练集准确率: {model.score(X_train, y_train):.2%}")

    # === 阶段3: SHAP值分析 ===
    print("\n=== 阶段3: 计算SHAP值 ===")
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_train)

    # 取主要意图类别的SHAP值
    main_intent = "itinerary"
    intent_index = model.classes_.tolist().index(main_intent)
    avg_shap = np.abs(shap_values[intent_index]).mean(axis=0)

    keyword_shap = dict(zip(keywords, avg_shap))
    print("关键词重要性分析：")
    for kw, val in sorted(keyword_shap.items(), key=lambda x: x[1], reverse=True):
        print(f"  {kw:8s}: {val:.3f}")

    # === 阶段4: 生成候选值 ===
    print("\n=== 阶段4: 生成候选值范围 ===")
    candidate_ranges = generate_candidate_ranges(keyword_shap)
    for kw, cand in sorted(candidate_ranges.items(), key=lambda x: keyword_shap[x[0]], reverse=True):
        print(f"  {kw:8s}: {cand}")

    # === 阶段5: 保存配置 ===
    print("\n=== 阶段5: 保存配置 ===")
    config = {
        "keyword_weights": keyword_shap,
        "candidate_ranges": candidate_ranges,
        "confidence_threshold_options": [0.75, 0.8, 0.85, 0.9],
    }

    with open(output_config_path, "w") as f:
        yaml.dump(config, f, allow_unicode=True)

    print(f"✅ 配置已保存到: {output_config_path}")

    return keyword_shap, candidate_ranges

# 运行自动化脚本
if __name__ == "__main__":
    keyword_shap, candidates = optimize_intent_keywords(
        "data/intent_training_data.csv",
        "config/intent_keywords.yaml",
    )
```

---

## 使用流程总结

```
【步骤1】准备训练数据 → 用户输入 + 意图标签

【步骤2】提取关键词特征 → CountVectorizer

【步骤3】训练模型 → RandomForestClassifier

【步骤4】计算SHAP值 → shap.TreeExplainer

【步骤5】生成候选值 → 根据SHAP值大小分类

【步骤6】网格搜索 → 测试不同权重组合

【步骤7】保存最佳参数 → YAML配置文件

【步骤8】集成到生产系统 → ProductionIntentClassifier
```

---

## 实际执行命令

```bash
# 1. 准备数据
cd backend
python scripts/prepare_training_data.py

# 2. 运行优化脚本
python scripts/optimize_intent_keywords.py

# 3. 查看生成的配置
cat config/intent_keywords.yaml

# 4. 测试生产模型
python scripts/test_intent_classifier.py
```

---

这就是完整的可操作流程！从数据准备到生产应用，每个步骤都有可执行代码。