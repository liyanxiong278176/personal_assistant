"""
测试优化后的意图识别分类器

使用SHAP优化后的参数进行实际测试
"""

import pandas as pd
import yaml
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
import numpy as np


class OptimizedIntentClassifier:
    """使用优化参数的意图识别器"""

    def __init__(self, config_path="config/intent_keywords.yaml"):
        """加载优化配置"""

        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        self.keyword_weights = config["recommended_params"]["keyword_weights"]
        self.confidence_threshold = config["recommended_params"]["confidence_threshold"]
        self.keyword_importance = config["shap_analysis"]["keyword_importance"]

        print(f"✅ 加载配置成功: {config_path}")
        print(f"   关键词权重: {len(self.keyword_weights)} 个")
        print(f"   置信度阈值: {self.confidence_threshold}")

        # 初始化模型和特征提取器
        self.keywords = list(self.keyword_weights.keys())
        self.vectorizer = CountVectorizer(vocabulary=self.keywords)
        self.model = RandomForestClassifier(n_estimators=100, random_state=42)

        # 加载训练数据并训练模型
        self._train_model()

    def _train_model(self):
        """训练模型"""

        # 加载训练数据
        training_data = pd.read_csv("data/intent_training_data.csv")
        X_train = self.vectorizer.fit_transform(training_data["用户输入"])
        y_train = training_data["意图标签"]

        # 应用关键词权重到特征矩阵
        X_weighted = self._apply_weights(X_train)

        # 训练模型
        self.model.fit(X_weighted, y_train)

        train_accuracy = self.model.score(X_weighted, y_train)
        print(f"   模型训练完成，准确率: {train_accuracy:.2%}")

        self.intents = self.model.classes_

    def _apply_weights(self, X):
        """应用关键词权重"""

        X_weighted = X.copy()

        if hasattr(X_weighted, "toarray"):
            X_weighted = X_weighted.toarray()

        # 应用权重
        for i, keyword in enumerate(self.keywords):
            if keyword in self.keyword_weights:
                X_weighted[:, i] *= self.keyword_weights[keyword]

        return X_weighted

    def predict(self, user_input):
        """预测意图"""

        # 提取特征
        features = self.vectorizer.transform([user_input])
        features_weighted = self._apply_weights(features)

        # 预测
        intent = self.model.predict(features_weighted)[0]
        proba = self.model.predict_proba(features_weighted)[0]
        confidence = max(proba)

        # 判断是否需要澄清
        needs_clarification = confidence < self.confidence_threshold

        # 获取关键词匹配详情
        keyword_matches = {}
        feature_array = features.toarray()[0]
        for i, keyword in enumerate(self.keywords):
            if feature_array[i] > 0:
                keyword_matches[keyword] = {
                    "matched": True,
                    "weight": self.keyword_weights[keyword],
                    "importance": self.keyword_importance[keyword],
                }

        return {
            "intent": intent,
            "confidence": confidence,
            "needs_clarification": needs_clarification,
            "keyword_matches": keyword_matches,
            "all_intents_proba": dict(zip(self.intents, proba)),
        }

    def batch_test(self, test_cases):
        """批量测试"""

        results = []

        for case in test_cases:
            result = self.predict(case["input"])
            result["input"] = case["input"]
            result["expected"] = case["expected"]
            result["correct"] = result["intent"] == case["expected"]
            results.append(result)

        return results


def display_prediction_result(result):
    """美化显示预测结果"""

    print("\n" + "=" * 70)
    print(f"输入: {result['input']}")
    print("=" * 70)

    print(f"✓ 预测意图: {result['intent']}")
    print(f"✓ 置信度: {result['confidence']:.2%}")
    print(f"✓ 是否需要澄清: {result['needs_clarification']}")

    if "expected" in result:
        status = "✅ 正确" if result["correct"] else "❌ 错误"
        print(f"✓ 期望意图: {result['expected']} | {status}")

    print("\n匹配的关键词:")
    print("-" * 70)
    for kw, details in sorted(result["keyword_matches"].items(),
                             key=lambda x: x[1]["importance"], reverse=True):
        importance = "⭐⭐⭐" if details["importance"] > 0.03 else "⭐⭐" if details["importance"] > 0.02 else "⭐"
        print(f"{importance} {kw:8s}: 权重={details['weight']:.2f}, SHAP值={details['importance']:.4f}")

    print("\n各意图置信度分布:")
    print("-" * 70)
    for intent, prob in sorted(result["all_intents_proba"].items(), key=lambda x: x[1], reverse=True):
        bar = "█" * int(prob * 50)
        print(f"{intent:12s}: {prob:.2%} {bar}")


def test_classifier():
    """测试优化后的分类器"""

    print("=" * 70)
    print("测试优化后的意图识别分类器")
    print("=" * 70)

    # 初始化分类器
    classifier = OptimizedIntentClassifier()

    # 测试用例
    test_cases = [
        # 行程规划意图
        {"input": "帮我规划北京行程", "expected": "itinerary"},
        {"input": "规划上海旅游路线", "expected": "itinerary"},
        {"input": "我想规划杭州三日游", "expected": "itinerary"},
        {"input": "规划西安旅游攻略", "expected": "itinerary"},
        {"input": "聊聊北京行程", "expected": "itinerary"},

        # 景点/美食推荐意图
        {"input": "推荐上海景点", "expected": "query"},
        {"input": "推荐北京餐厅", "expected": "food"},
        {"input": "推荐杭州美食", "expected": "food"},
        {"input": "推荐成都酒店", "expected": "query"},
        {"input": "推荐特色餐厅", "expected": "food"},

        # 天气查询意图
        {"input": "查询北京天气", "expected": "weather"},
        {"input": "查询明天天气", "expected": "weather"},
        {"input": "聊聊成都天气", "expected": "weather"},
        {"input": "查询杭州天气", "expected": "weather"},
        {"input": "查询交通方式", "expected": "query"},

        # 闲聊意图
        {"input": "想聊聊天", "expected": "chat"},
        {"input": "随便聊聊", "expected": "chat"},
        {"input": "聊聊天吧", "expected": "chat"},
        {"input": "闲聊", "expected": "chat"},
        {"input": "聊一聊", "expected": "chat"},

        # 边界测试（混合关键词）
        {"input": "规划一下天气查询", "expected": "itinerary"},  # "规划"权重高
        {"input": "聊聊规划行程", "expected": "itinerary"},      # "规划"权重高
        {"input": "推荐规划路线", "expected": "itinerary"},      # "规划"权重高
    ]

    # 执行批量测试
    results = classifier.batch_test(test_cases)

    # 统计准��率
    correct_count = sum(1 for r in results if r["correct"])
    accuracy = correct_count / len(results)

    print("\n" + "=" * 70)
    print("批量测试结果汇总")
    print("=" * 70)
    print(f"总测试数: {len(results)}")
    print(f"正确预测: {correct_count}")
    print(f"准确率: {accuracy:.2%}")

    # 显示详细结果
    print("\n详细测试结果:")
    print("-" * 70)
    for i, result in enumerate(results, 1):
        status = "✅" if result["correct"] else "❌"
        clarif = "需澄清" if result["needs_clarification"] else "直接执行"
        print(f"{i:2d}. {status} | 输入: {result['input']:30s} | "
              f"预测: {result['intent']:12s} | 期望: {result['expected']:12s} | "
              f"置信度: {result['confidence']:.2%} | {clarif}")

    # 显示前5个成功案例的详细信息
    print("\n" + "=" * 70)
    print("成功案例详细分析（前5个）")
    print("=" * 70)

    success_cases = [r for r in results if r["correct"]][:5]
    for result in success_cases[:3]:  # 只显示3个避免太长
        display_prediction_result(result)

    # 显示失败案例（如果有）
    if correct_count < len(results):
        print("\n" + "=" * 70)
        print("失败案例分析")
        print("=" * 70)

        fail_cases = [r for r in results if not r["correct"]]
        for result in fail_cases[:2]:  # 只显示前2个失败案例
            display_prediction_result(result)

    # 演示单次预测
    print("\n" + "=" * 70)
    print("交互式预测演示")
    print("=" * 70)

    demo_inputs = [
        "帮我规划一个北京五日游",
        "聊聊上海的美食",
        "推荐一些特色餐厅",
    ]

    for input_text in demo_inputs:
        result = classifier.predict(input_text)
        display_prediction_result(result)

    print("\n" + "=" * 70)
    print("测试完成")
    print("=" * 70)

    return results


if __name__ == "__main__":
    results = test_classifier()

    # 可选：保存测试报告
    report_df = pd.DataFrame([
        {
            "输入": r["input"],
            "预测意图": r["intent"],
            "期望意图": r["expected"],
            "正确": r["correct"],
            "置信度": r["confidence"],
            "需要澄清": r["needs_clarification"],
        }
        for r in results
    ])

    report_df.to_csv("reports/intent_test_report.csv", index=False, encoding="utf-8")
    print(f"\n✅ 测试报告已保存: reports/intent_test_report.csv")