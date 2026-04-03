"""Slot Extractor - Extract structured parameters from user messages

This module extracts travel-related slots from user messages including:
- Destination (city name)
- Date range (start_date, end_date)
- Number of travelers
- Budget level
- Interest tags
"""

import re
import logging
from datetime import datetime, date, timedelta
from typing import Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class DateRange(BaseModel):
    """日期范围"""
    start_date: str  # YYYY-MM-DD
    end_date: str  # YYYY-MM-DD

    @property
    def num_days(self) -> int:
        """计算天数"""
        start = datetime.strptime(self.start_date, "%Y-%m-%d").date()
        end = datetime.strptime(self.end_date, "%Y-%m-%d").date()
        return (end - start).days + 1


class SlotResult(BaseModel):
    """槽位提取结果"""
    destination: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    travelers: Optional[int] = None
    budget: Optional[str] = None  # low/medium/high
    interests: Optional[list[str]] = None

    @property
    def has_required_slots(self) -> bool:
        """是否有必填槽位（目的地 + 日期）"""
        return bool(self.destination and self.start_date)

    @property
    def num_days(self) -> Optional[int]:
        """行程天数"""
        if self.start_date and self.end_date:
            start = datetime.strptime(self.start_date, "%Y-%m-%d").date()
            end = datetime.strptime(self.end_date, "%Y-%m-%d").date()
            return (end - start).days + 1
        return None


class SlotExtractor:
    """槽位提取器 - 从用户消息中提取结构化参数"""

    # 常见中国城市列表
    COMMON_CITIES = [
        "北京", "上海", "广州", "深圳", "杭州", "成都", "西安", "重庆",
        "南京", "苏州", "厦门", "青岛", "大连", "三亚", "桂林", "丽江",
        "拉萨", "乌鲁木齐", "武汉", "长沙", "郑州", "天津", "哈尔滨",
        "沈阳", "济南", "昆明", "贵阳", "兰州", "西宁", "南宁",
        "宁波", "无锡", "常州", "扬州", "烟台", "威海", "泰安",
        "黄山", "九寨沟", "张家界", "桂林", "丽江", "大理", "香格里拉",
        "西双版纳", "三亚", "海口", "珠海", "北海", "青岛", "大连",
    ]

    # 节假日配置 (month, start_day, days_count) - 2026年
    HOLIDAYS = {
        "元旦": (1, 1, 1),
        "春节": (2, 17, 7),
        "清明": (4, 4, 3),
        "劳动节": (5, 1, 5),
        "五一": (5, 1, 5),
        "端午": (5, 31, 3),
        "中秋": (9, 25, 3),
        "国庆节": (10, 1, 7),
        "国庆": (10, 1, 7),
    }

    def __init__(self, current_date: Optional[date] = None):
        """初始化

        Args:
            current_date: 当前日期（用于测试时注入）
        """
        self._current_date = current_date or datetime.now().date()

    def extract(self, message: str) -> SlotResult:
        """提取所有槽位"""
        start_date, end_date, _ = self._parse_dates(message)

        return SlotResult(
            destination=self._extract_destination(message),
            start_date=start_date,
            end_date=end_date,
            travelers=self._extract_travelers(message),
        )

    def _extract_destination(self, message: str) -> Optional[str]:
        """提取目的地城市"""
        # 模式1: "去/到/在 [城市] 旅游/玩/行程"
        patterns = [
            r'(?:去|到|在)([^，。！？\s]{2,6}?)(?:旅游|玩|行程|攻略)',
            r'([^，。！？\s]{2,6}?)(?:旅游|行程|攻略)',
        ]
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                city = match.group(1).strip()
                # 验证是否为常见城市
                if city in self.COMMON_CITIES:
                    logger.debug(f"[SlotExtractor] Extracted destination: {city}")
                    return city

        # 模式2: 直接匹配常见城市名
        for city in self.COMMON_CITIES:
            if city in message:
                logger.debug(f"[SlotExtractor] Found city: {city}")
                return city

        return None

    def _parse_dates(self, message: str) -> tuple[Optional[str], Optional[str], int]:
        """解析日期，返回 (start_date, end_date, num_days)

        优先级:
        1. 节假日 (五一, 国庆等)
        2. 日期范围 (4月5日-4月10日)
        3. 月日 (3月15日)
        4. 相对日期 (明天, 下周等)
        """
        current_year = self._current_date.year

        # 优先级1: 节假日
        for holiday_name, (month, start_day, days_count) in self.HOLIDAYS.items():
            if holiday_name in message:
                try:
                    start = date(current_year, month, start_day)
                    end = start + timedelta(days=days_count - 1)
                    logger.info(f"[SlotExtractor] Parsed holiday '{holiday_name}'")
                    return (
                        start.strftime("%Y-%m-%d"),
                        end.strftime("%Y-%m-%d"),
                        days_count
                    )
                except ValueError:
                    pass

        # 优先级2: 日期范围 "4月5日到4月10日"
        range_pattern = r'(\d{1,2})[月\.](\d{1,2})[日号]\s*(?:到|至|-|—|~)\s*(\d{1,2})[月\.](\d{1,2})[日号]'
        match = re.search(range_pattern, message)
        if match:
            try:
                m1, d1, m2, d2 = int(match.group(1)), int(match.group(2)), int(match.group(3)), int(match.group(4))
                start = date(current_year, m1, d1)
                end = date(current_year, m2, d2)
                if end < start:
                    end = date(current_year + 1, m2, d2)
                num_days = (end - start).days + 1
                logger.info(f"[SlotExtractor] Parsed date range")
                return (
                    start.strftime("%Y-%m-%d"),
                    end.strftime("%Y-%m-%d"),
                    num_days
                )
            except ValueError:
                pass

        # 优先级3: 月日 "3月15日"
        month_day_pattern = r'(\d{1,2})[月\.\-](\d{1,2})[日号](?!\s*(?:到|至|-|—|~))'
        match = re.search(month_day_pattern, message)
        if match:
            try:
                month, day = int(match.group(1)), int(match.group(2))
                target = date(current_year, month, day)
                # 如果日期已过，使用明年
                if target < self._current_date:
                    target = date(current_year + 1, month, day)
                date_str = target.strftime("%Y-%m-%d")
                logger.info(f"[SlotExtractor] Parsed month/day: {date_str}")
                return date_str, date_str, 1
            except ValueError:
                pass

        # 默认: 无日期
        return None, None, 0

    def _extract_travelers(self, message: str) -> Optional[int]:
        """提取出行人数"""
        # 匹配 "X人", "X个人", "我们X个" 等
        patterns = [
            r'(\d+)\s*[个人]',
            r'(\d+)\s*人',
            r'我们\s*(\d+)\s*个',
        ]
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return int(match.group(1))
        return None
