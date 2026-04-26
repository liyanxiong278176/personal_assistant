"""评估数据模型"""
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional, List
import json


@dataclass
class IntentResult:
    """意图识别结果"""
    intent: str
    confidence: float
    method: str = "llm"  # "cache" | "keyword" | "llm"


@dataclass
class TokenUsage:
    """Token 使用情况"""
    tokens_before: int
    tokens_after: int
    tokens_input: int
    tokens_output: int
    is_compressed: bool


@dataclass
class TrajectoryModel:
    """查询轨迹模型"""
    trace_id: str
    conversation_id: Optional[str]
    user_id: Optional[str]
    started_at: datetime
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    success: bool = True
    error_message: Optional[str] = None
    user_message: str = ""
    has_image: bool = False
    intent_type: Optional[str] = None
    intent_confidence: Optional[float] = None
    intent_method: Optional[str] = None
    tokens_input: Optional[int] = None
    tokens_output: Optional[int] = None
    tokens_before_compress: Optional[int] = None
    tokens_after_compress: Optional[int] = None
    is_compressed: bool = False
    tools_called: List[dict] = field(default_factory=list)
    verification_score: Optional[int] = None
    verification_passed: Optional[bool] = None
    iteration_count: int = 0

    def to_dict(self) -> dict:
        """转换为字典，用于存储到数据库"""
        d = asdict(self)
        d["started_at"] = self.started_at.isoformat()
        if self.completed_at:
            d["completed_at"] = self.completed_at.isoformat()
        d["tools_called"] = json.dumps(d["tools_called"])
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "TrajectoryModel":
        """从字典创建实例"""
        # 移除数据库自动生成的字段（如 id）
        data = {k: v for k, v in data.items() if k not in ("id", "created_at")}

        # Parse datetime fields
        if isinstance(data.get("started_at"), str):
            data["started_at"] = datetime.fromisoformat(data["started_at"])
        if data.get("completed_at") and isinstance(data["completed_at"], str):
            data["completed_at"] = datetime.fromisoformat(data["completed_at"])

        # Parse tools_called from JSON string
        if isinstance(data.get("tools_called"), str):
            data["tools_called"] = json.loads(data["tools_called"])

        # Convert SQLite integer booleans to Python bool
        for key in ("success", "has_image", "is_compressed", "verification_passed"):
            if key in data and isinstance(data[key], int):
                data[key] = bool(data[key])

        return cls(**data)
