# backend/tests/test_interview_monitor/utils/report_generator.py
import json
import gzip
from pathlib import Path
from datetime import datetime

class ReportGenerator:
    def __init__(self, results_dir: Path, compress: bool = True):
        """初始化报告生成器

        Args:
            results_dir: 结果目录路径
            compress: 是否启用gzip压缩（默认True）
        """
        self.results_dir = results_dir
        self.results_dir.mkdir(exist_ok=True)
        self.compress = compress

    def save_jsonl(self, test_type: str, data: list, timestamp: str) -> Path:
        """保存测试结果为JSONL格式

        注意: 压缩文件统一使用 .jsonl.gz 扩展名（不是 .json.gz）

        Args:
            test_type: 测试类型（security/intent/memory/context）
            data: 测试结果数据列表
            timestamp: 时间戳

        Returns:
            保存的文件路径
        """
        filename = f"{timestamp}_{test_type}_test.jsonl"
        if self.compress:
            filename += ".gz"
            path = self.results_dir / filename
            with gzip.open(path, "wt", encoding="utf-8") as f:
                for item in data:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        else:
            path = self.results_dir / filename
            with open(path, "w", encoding="utf-8") as f:
                for item in data:
                    f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return path

    def generate_summary(self, results: dict) -> dict:
        """生成测试摘要

        Args:
            results: 所有测试类型的汇总结果

        Returns:
            摘要字典
        """
        return {
            "timestamp": datetime.now().isoformat(),
            "test_suite": "all",
            "security": results.get("security", {}),
            "intent": results.get("intent", {}),
            "memory": results.get("memory", {}),
            "context": results.get("context", {}),
        }

    def save_summary(self, summary: dict, timestamp: str) -> Path:
        """保存测试摘要为JSON文件

        Args:
            summary: 摘要字典（由 generate_summary 生成）
            timestamp: 时间戳

        Returns:
            保存的文件路径
        """
        filename = f"{timestamp}_summary.json"
        if self.compress:
            filename += ".gz"
            path = self.results_dir / filename
            with gzip.open(path, "wt", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
        else:
            path = self.results_dir / filename
            with open(path, "w", encoding="utf-8") as f:
                json.dump(summary, f, ensure_ascii=False, indent=2)
        return path
