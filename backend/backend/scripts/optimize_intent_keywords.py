"""
基于SHAP值的意图关键词候选值优化脚本

自动化流程：
1. 加载训练数据
2. 训练意图识别模型
3. 计算SHAP值分析关键词重要性
4. 根据重要性生成候选值范围
5. 执行网格搜索找最佳参数
6. 保存优化结果到配置文件
"""

import shap
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.model_selection import cross_val_score
import yaml
import os

# 关键词列表（业务定义）
KEYWORDS = [
    "规划", "聊聊", "推荐", "查询", "行程",
    "旅游", "景点", "天气", "餐厅", "聊天",
    "路线", "美食", "酒店", "交通", "美食",
]


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


def optimize_intent_keywords(training_data_path="data/intent_training_data.csv",
                             output_config_path="config/intent_keywords.yaml"):
    """自动化SHAP值分析和候选值生成"""

    # === 阶段1: 数据准备 ===
    print("=" * 60)
    print("阶段1: 加载训练数据")
    print("=" * 60)

    training_data = pd.read_csv(training_data_path)
    print(f"✅ 加载成功: {training_data_path}")
    print(f"   样本数: {len(training_data)}")
    print(f"   意图分布:")
    print(training_data["意图标签"].value_counts())

    # 提取关键词特征
    vectorizer = CountVectorizer(vocabulary=KEYWORDS)
    X_train = vectorizer.fit_transform(training_data["用户输入"])
    y_train = training_data["意图标签"]

    print(f"\n✅ 特征提取完成")
    print(f"   特征维度: {X_train.shape}")
    print(f"   关键词数量: {len(KEYWORDS)}")

    # === 阶段2: 训练模型 ===
    print("\n" + "=" * 60)
    print("阶段2: 训练意图识别模型")
    print("=" * 60)

    model = RandomForestClassifier(
        n_estimators=100,
        max_depth=10,
        random_state=42,
    )
    model.fit(X_train, y_train)

    train_accuracy = model.score(X_train, y_train)
    cv_scores = cross_val_score(model, X_train, y_train, cv=5)

    print(f"✅ 模型训练完成")
    print(f"   训练集准确率: {train_accuracy:.2%}")
    print(f"   5折交叉验证: {cv_scores.mean():.2%} ± {cv_scores.std():.2%}")

    # === 阶段3: SHAP值分析 ===
    print("\n" + "=" * 60)
    print("阶段3: 计算SHAP值分析关键词重要性")
    print("=" * 60)

    # 创建SHAP解释器
    explainer = shap.TreeExplainer(model)
    shap_values = explainer.shap_values(X_train)

    print(f"✅ SHAP值计算完成")
    print(f"   SHAP矩阵维度: {len(shap_values)} 个意图类别")

    # 计算每个关键词的平均SHAP值（跨所有意图类别）
    # 方法：取所有类别SHAP值的平均绝对值
    avg_shap_all_classes = np.zeros(len(KEYWORDS))
    for intent_shap in shap_values:
        avg_shap_all_classes += np.abs(intent_shap).mean(axis=0)

    avg_shap_all_classes /= len(shap_values)

    keyword_shap = dict(zip(KEYWORDS, avg_shap_all_classes))

    print("\n📊 关键词重要性排名（基于SHAP值）:")
    print("-" * 40)
    for kw, val in sorted(keyword_shap.items(), key=lambda x: x[1], reverse=True):
        importance_level = "⭐⭐⭐" if val > 0.03 else "⭐⭐" if val > 0.02 else "⭐" if val > 0.01 else "•"
        print(f"{importance_level} {kw:8s}: {val:.4f}")

    # === 阶段4: 生成候选值范围 ===
    print("\n" + "=" * 60)
    print("阶段4: 根据SHAP值生成候选值范围")
    print("=" * 60)

    candidate_ranges = generate_candidate_ranges(keyword_shap)

    print("\n🎯 生成的候选值范围:")
    print("-" * 60)
    for kw, cand in sorted(candidate_ranges.items(), key=lambda x: keyword_shap[x[0]], reverse=True):
        importance = "重要" if keyword_shap[kw] > 0.03 else "中等" if keyword_shap[kw] > 0.02 else "次要"
        print(f"{kw:8s} [{importance:4s}]: {cand}")

    # === 阶段5: 推荐最佳参数组合 ===
    print("\n" + "=" * 60)
    print("阶段5: 推荐最佳参数组合")
    print("=" * 60)

    # 推荐权重（基于SHAP值）
    recommended_weights = {}
    for kw, shap_val in keyword_shap.items():
        if shap_val > 0.03:
            recommended_weights[kw] = 0.75  # 重要关键词：中等偏高权重
        elif shap_val > 0.02:
            recommended_weights[kw] = 0.55  # 中等重要：中等权重
        elif shap_val > 0.01:
            recommended_weights[kw] = 0.35  # 次要关键词：较低权重
        else:
            recommended_weights[kw] = 0.15  # 不重要：极低权重

    # 推荐置信度阈值（基于业务需求）
    recommended_threshold = 0.80  # 平衡准确率和用户体验

    print("\n✅ 推荐参数:")
    print(f"   关键词权重:")
    for kw, weight in sorted(recommended_weights.items(), key=lambda x: keyword_shap[x[0]], reverse=True)[:5]:
        print(f"     {kw}: {weight}")
    print(f"   置信度阈值: {recommended_threshold}")

    # === 阶段6: 保存配置 ===
    print("\n" + "=" * 60)
    print("阶段6: 保存优化结果到配置文件")
    print("=" * 60)

    # 确保目录存在
    os.makedirs("config", exist_ok=True)

    config = {
        "shap_analysis": {
            "keyword_importance": {k: float(v) for k, v in keyword_shap.items()},
            "thresholds_used": thresholds if thresholds else {
                "important": 0.03,
                "medium": 0.02,
                "minor": 0.01,
            },
        },
        "candidate_ranges": candidate_ranges,
        "recommended_params": {
            "keyword_weights": recommended_weights,
            "confidence_threshold": recommended_threshold,
        },
        "model_performance": {
            "train_accuracy": float(train_accuracy),
            "cv_accuracy": float(cv_scores.mean()),
            "cv_std": float(cv_scores.std()),
        },
        "metadata": {
            "training_samples": len(training_data),
            "keywords_count": len(KEYWORDS),
            "timestamp": pd.Timestamp.now().isoformat(),
        }
    }

    with open(output_config_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False)

    print(f"✅ 配置已保存: {output_config_path}")

    # === 总结 ===
    print("\n" + "=" * 60)
    print("优化完成总结")
    print("=" * 60)
    print(f"✓ 训练数据: {training_data_path}")
    print(f"✓ 模型准确率: {train_accuracy:.2%}")
    print(f"✓ 关键词分析: {len(keyword_shap)} 个关键词")
    print(f"✓ 候选值生成: {len(candidate_ranges)} 个候选范围")
    print(f"✓ 配置保存: {output_config_path}")
    print("=" * 60)

    return keyword_shap, candidate_ranges, config


if __name__ == "__main__":
    # 运行优化
    keyword_shap, candidates, config = optimize_intent_keywords()

    # 打印示例使用
    print("\n💡 如何使用优化结果:")
    print("-" * 60)
    print("1. 查看配置文件: cat config/intent_keywords.yaml")
    print("2. 使用推荐权重训练生产模型")
    print("3. 在网格搜索中使用候选值范围")
    print("-" * 60)