"""多Agent系统鲁棒性测试

测试场景：
- 10个正常规划聊天
- 10个不正常/边缘情况聊天
"""

import asyncio
import json
import time
from typing import List, Dict, Any
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# API配置
API_URL = "http://localhost:8000/api/agent/chat"


# 正常场景测试用例
NORMAL_TEST_CASES = [
    {
        "name": "简单目的地查询",
        "message": "我想去北京旅游",
        "expected_keywords": ["北京", "旅游", "行程"]
    },
    {
        "name": "多目的地规划",
        "message": "帮我规划北京、上海、杭州三天的行程",
        "expected_keywords": ["北京", "上海", "杭州", "三天"]
    },
    {
        "name": "需要酒店查询",
        "message": "我要去成都玩三天，需要预订酒店",
        "expected_keywords": ["成都", "酒店", "住宿"]
    },
    {
        "name": "天气查询",
        "message": "西安这周末天气怎么样？",
        "expected_keywords": ["西安", "天气", "温度"]
    },
    {
        "name": "预算规划",
        "message": "我有2000元预算，想去云南玩5天，经济实惠一点",
        "expected_keywords": ["预算", "云南", "5天", "经济"]
    },
    {
        "name": "完整规划（多Agent触发）",
        "message": "帮我规划一下去桂林旅游，需要酒店和天气信息，预算5000元玩4天",
        "expected_keywords": ["桂林", "酒店", "天气", "预算", "4天"]
    },
    {
        "name": "景点推荐",
        "message": "北京有哪些值得去的景点？",
        "expected_keywords": ["北京", "景点", "推荐"]
    },
    {
        "name": "路线规划",
        "message": "从北京到上海怎么走比较方便？",
        "expected_keywords": ["北京", "上海", "路线", "交通"]
    },
    {
        "name": "美食推荐",
        "message": "成都有什么特色美食？",
        "expected_keywords": ["成都", "美食", "特色"]
    },
    {
        "name": "跟团游",
        "message": "我想参加一个5天的旅游团，去云南，大概多少钱？",
        "expected_keywords": ["旅游团", "云南", "5天", "价格"]
    },
]

# 不正常/边缘情况测试用例
ABNORMAL_TEST_CASES = [
    {
        "name": "空消息",
        "message": "",
        "expected_behavior": "should_handle_gracefully"
    },
    {
        "name": "超长消息",
        "message": "我想去" + "旅游" * 500 + "，请帮我规划",
        "expected_behavior": "should_handle_gracefully"
    },
    {
        "name": "特殊字符",
        "message": "<script>alert('test')</script>想去北京旅游",
        "expected_behavior": "should_sanitize"
    },
    {
        "name": "无意义输入",
        "message": "asdfghjklzxcvbnm",
        "expected_behavior": "should_handle_gracefully"
    },
    {
        "name": "模糊目的地",
        "message": "我想去那个地方玩，你知道是哪里吗？",
        "expected_behavior": "should_ask_clarification"
    },
    {
        "name": "不合理的预算",
        "message": "我有10块钱想去欧洲玩一个月",
        "expected_behavior": "should_provide_realistic_feedback"
    },
    {
        "name": "不存在的地方",
        "message": "我想去火星旅游一周",
        "expected_behavior": "should_handle_unknown_location"
    },
    {
        "name": "混合语言",
        "message": "I want to go to 北京旅游 for 3 days",
        "expected_behavior": "should_handle_mixed_language"
    },
    {
        "name": "时间冲突",
        "message": "我想今天早上8点出发，今天晚上8点回来，去日本旅游",
        "expected_behavior": "should_handle_time_conflict"
    },
    {
        "name": "多轮复杂需求",
        "message": "我想去A地玩，然后去B地，但是不确定A和B是哪里，大概玩几天？",
        "expected_behavior": "should_ask_for_details"
    },
]


class RobustnessTester:
    """鲁棒性测试器"""

    def __init__(self, api_url: str):
        self.api_url = api_url
        self.results: List[Dict[str, Any]] = []

    def send_message(self, message: str, conversation_id: str = "test") -> Dict[str, Any]:
        """发送消息到API"""
        try:
            start_time = time.time()
            response = requests.post(
                self.api_url,
                json={
                    "message": message,
                    "conversation_id": conversation_id,
                    "user_id": "test_user"
                },
                timeout=30
            )
            elapsed = time.time() - start_time

            if response.status_code == 200:
                return {
                    "success": True,
                    "response": response.json().get("message", ""),
                    "elapsed": elapsed
                }
            else:
                return {
                    "success": False,
                    "error": f"HTTP {response.status_code}",
                    "elapsed": elapsed
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "elapsed": 0
            }

    def test_normal_case(self, case: Dict[str, Any], index: int) -> Dict[str, Any]:
        """测试正常场景"""
        logger.info(f"\n{'='*60}")
        logger.info(f"[正常测试 {index+1}/10] {case['name']}")
        logger.info(f"输入: {case['message'][:100]}...")

        result = self.send_message(case['message'], f"normal_{index}")

        result["test_name"] = case["name"]
        result["test_type"] = "normal"
        result["input_length"] = len(case["message"])

        if result["success"]:
            response_text = result["response"]
            result["response_length"] = len(response_text)

            # 检查关键词
            found_keywords = []
            for keyword in case.get("expected_keywords", []):
                if keyword in response_text:
                    found_keywords.append(keyword)

            result["found_keywords"] = found_keywords
            result["keyword_coverage"] = len(found_keywords) / len(case.get("expected_keywords", [])) if case.get("expected_keywords") else 1.0

            logger.info(f"✅ 成功 | 耗时={result['elapsed']:.2f}s | 响应长度={result['response_length']}")
            logger.info(f"关键词覆盖: {result['keyword_coverage']:.0%} ({found_keywords})")
        else:
            result["error"] = result.get("error", "Unknown error")
            logger.error(f"❌ 失败 | 错误: {result['error']}")

        return result

    def test_abnormal_case(self, case: Dict[str, Any], index: int) -> Dict[str, Any]:
        """测试不正常场景"""
        logger.info(f"\n{'='*60}")
        logger.info(f"[异常测试 {index+1}/10] {case['name']}")
        logger.info(f"输入: {case['message'][:100] if len(case['message']) > 100 else case['message']}...")

        result = self.send_message(case['message'], f"abnormal_{index}")

        result["test_name"] = case["name"]
        result["test_type"] = "abnormal"
        result["input_length"] = len(case["message"])
        result["expected_behavior"] = case.get("expected_behavior", "")

        if result["success"]:
            result["response_length"] = len(result["response"])
            logger.info(f"✅ 已处理 | 耗时={result['elapsed']:.2f}s | 响应长度={result['response_length']}")

            # 检查是否是合理的响应
            response = result["response"]
            if len(response) > 0:
                result["handled_gracefully"] = True
            else:
                result["handled_gracefully"] = False
                logger.warning(f"⚠️ 响应为空")
        else:
            result["handled_gracefully"] = False
            result["error"] = result.get("error", "Unknown error")
            logger.warning(f"⚠️ 请求失败 | 错误: {result['error']}")

        return result

    def run_all_tests(self) -> Dict[str, Any]:
        """运行所有测试"""
        logger.info("\n" + "="*80)
        logger.info("开始多Agent系统鲁棒性测试")
        logger.info("="*80)

        # 测试正常场景
        logger.info("\n## 正常场景测试 (10/10)")
        normal_results = []
        for i, case in enumerate(NORMAL_TEST_CASES):
            result = self.test_normal_case(case, i)
            normal_results.append(result)
            self.results.append(result)
            time.sleep(0.5)  # 避免请求过快

        # 测试异常场景
        logger.info("\n## 异常场景测试 (10/10)")
        abnormal_results = []
        for i, case in enumerate(ABNORMAL_TEST_CASES):
            result = self.test_abnormal_case(case, i)
            abnormal_results.append(result)
            self.results.append(result)
            time.sleep(0.5)

        # 汇总统计
        return self._summarize_results(normal_results, abnormal_results)

    def _summarize_results(self, normal_results: List[Dict], abnormal_results: List[Dict]) -> Dict[str, Any]:
        """汇总测试结果"""
        logger.info("\n" + "="*80)
        logger.info("测试结果汇总")
        logger.info("="*80)

        # 正常场景统计
        normal_success = sum(1 for r in normal_results if r["success"])
        normal_avg_time = sum(r["elapsed"] for r in normal_results if r["success"]) / max(normal_success, 1)
        normal_avg_coverage = sum(r.get("keyword_coverage", 0) for r in normal_results) / len(normal_results)

        logger.info(f"\n### 正常场景 (10/10)")
        logger.info(f"成功率: {normal_success}/10 ({normal_success*10}%)")
        logger.info(f"平均响应时间: {normal_avg_time:.2f}s")
        logger.info(f"平均关键词覆盖: {normal_avg_coverage:.0%}")

        # 异常场景统计
        abnormal_handled = sum(1 for r in abnormal_results if r.get("handled_gracefully", r.get("success", False)))
        abnormal_success = sum(1 for r in abnormal_results if r["success"])
        abnormal_avg_time = sum(r["elapsed"] for r in abnormal_results if r["success"]) / max(abnormal_success, 1)

        logger.info(f"\n### 异常场景 (10/10)")
        logger.info(f"优雅处理率: {abnormal_handled}/10 ({abnormal_handled*10}%)")
        logger.info(f"请求成功率: {abnormal_success}/10 ({abnormal_success*10}%)")
        if abnormal_success > 0:
            logger.info(f"平均响应时间: {abnormal_avg_time:.2f}s")

        # 总体评分
        total_score = (normal_success * 10 + abnormal_handled * 10) / 2  # 满分100
        logger.info(f"\n### 总体评分: {total_score}/100")

        # 详细结果
        logger.info(f"\n### 详细结果")
        for result in self.results:
            status = "✅" if result.get("success") or result.get("handled_gracefully") else "❌"
            logger.info(f"{status} {result['test_name']} | {result.get('elapsed', 0):.2f}s")

        return {
            "normal": {
                "success_rate": normal_success / 10,
                "avg_time": normal_avg_time,
                "keyword_coverage": normal_avg_coverage
            },
            "abnormal": {
                "handled_rate": abnormal_handled / 10,
                "success_rate": abnormal_success / 10,
                "avg_time": abnormal_avg_time
            },
            "total_score": total_score
        }


def main():
    """主函数"""
    print("\n" + "="*80)
    print("多Agent系统鲁棒性测试")
    print("="*80)
    print("\n确保后端服务器正在运行: python backend/run_server.py")
    print("\n按 Enter 开始测试...")
    input()

    tester = RobustnessTester(API_URL)
    results = tester.run_all_tests()

    # 保存结果
    with open("test_results.json", "w", encoding="utf-8") as f:
        json.dump({
            "summary": results,
            "details": tester.results
        }, f, ensure_ascii=False, indent=2)

    logger.info("\n测试完成！结果已保存到 test_results.json")


if __name__ == "__main__":
    main()
