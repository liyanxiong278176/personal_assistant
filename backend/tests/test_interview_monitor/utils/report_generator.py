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
        return {
            "timestamp": datetime.now().isoformat(),
            "test_suite": "all",
            "security": results.get("security", {}),
            "intent": results.get("intent", {}),
            "memory": results.get("memory", {}),
            "context": results.get("context", {}),
        }
