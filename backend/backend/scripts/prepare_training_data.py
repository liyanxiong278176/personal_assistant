"""
准备意图识别训练数据

生成示例训练数据用于SHAP值分析
"""

import pandas as pd
import os

def prepare_training_data():
    """生成意图识别训练数据"""

    # 创建训练数据
    training_data = pd.DataFrame({
        "用户输入": [
            "帮我规划北京行程",
            "规划上海旅游路线",
            "我想规划杭州三日游",
            "帮我规划成都旅行",
            "规划西安旅游攻略",

            "聊聊北京旅游",
            "聊聊上海景点",
            "聊聊杭州美食",
            "聊聊成都天气",
            "聊聊西安行程",

            "推荐上海景点",
            "推荐北京餐厅",
            "推荐杭州美食",
            "推荐成都酒店",
            "推荐西安特产",

            "查询北京天气",
            "查询明天天气",
            "查询上海天气",
            "查询杭州天气",
            "查询成都天气",

            "想聊聊天",
            "随便聊聊",
            "聊聊天吧",
            "聊一聊",
            "闲聊",

            "帮我推荐餐厅",
            "推荐美食餐厅",
            "推荐附近餐厅",
            "推荐好吃的餐厅",
            "推荐特色餐厅",

            "查询交通路线",
            "查询地铁线路",
            "查询公交路线",
            "查询怎么去",
            "查询交通方式",

            "规划路线",
            "规划行程路线",
            "规划旅游路线",
            "规划出行路线",
            "规划最佳路线",
        ],
        "意图标签": [
            # itinerary（行程规划）- 5条
            "itinerary", "itinerary", "itinerary", "itinerary", "itinerary",

            # itinerary（包含"聊聊"但仍是行程）- 5条
            "itinerary", "itinerary", "food", "weather", "itinerary",

            # query（景点/美食/酒店推荐）- 5条
            "query", "food", "food", "query", "query",

            # weather（天气查询）- 5条
            "weather", "weather", "weather", "weather", "weather",

            # chat（闲聊）- 5条
            "chat", "chat", "chat", "chat", "chat",

            # food（美食推荐）- 5条
            "food", "food", "food", "food", "food",

            # query（交通查询）- 5条
            "query", "query", "query", "query", "query",

            # itinerary（路线规划）- 5条
            "itinerary", "itinerary", "itinerary", "itinerary", "itinerary",
        ]
    })

    # 确保目录存在
    os.makedirs("data", exist_ok=True)

    # 保存到CSV
    output_path = "data/intent_training_data.csv"
    training_data.to_csv(output_path, index=False, encoding="utf-8")

    print(f"✅ 训练数据已生成: {output_path}")
    print(f"   总样本数: {len(training_data)}")
    print(f"   意图分布:")
    print(training_data["意图标签"].value_counts())

    return training_data

if __name__ == "__main__":
    data = prepare_training_data()
    print("\n数据预览:")
    print(data.head(10))