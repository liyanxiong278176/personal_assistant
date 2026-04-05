"""Slot Extractor - Extract structured parameters from user messages

This module extracts travel-related slots from user messages including:
- Destination (city name or multiple cities)
- Date range (start_date, end_date)
- Number of days (explicitly mentioned)
- Number of travelers
- Budget level
- Service needs (hotel, weather, etc.)
"""

import re
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List

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
    """槽位提取结果 - 增强版支持多Agent"""
    # 单个目的地（向后兼容）
    destination: Optional[str] = None
    # 多目的地列表（新增）
    destinations: Optional[List[str]] = None

    # 日期相关
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    # 显式提到的天数（新增）
    days: Optional[int] = None

    # 人数
    travelers: Optional[int] = None

    # 预算相关（新增）
    budget: Optional[str] = None  # low/medium/high 或具体金额
    budget_amount: Optional[int] = None  # 具体金额

    # 服务需求（新增）
    need_hotel: bool = False
    need_weather: bool = False
    need_route: bool = False
    need_food: bool = False

    # 兴趣标签
    interests: Optional[List[str]] = None

    @property
    def has_required_slots(self) -> bool:
        """是否有必填槽位（目的地 + 日期）"""
        dest = self.destinations if self.destinations else self.destination
        date_info = self.days or (self.start_date and self.end_date)
        return bool(dest and date_info)

    @property
    def num_days(self) -> Optional[int]:
        """行程天数"""
        if self.days:
            return self.days
        if self.start_date and self.end_date:
            start = datetime.strptime(self.start_date, "%Y-%m-%d").date()
            end = datetime.strptime(self.end_date, "%Y-%m-%d").date()
            return (end - start).days + 1
        return None

    @property
    def complexity_score(self) -> int:
        """计算复杂度分数（供多Agent决策使用）"""
        score = 0

        # 目的地数量
        if self.destinations:
            if len(self.destinations) > 1:
                score += 2
            elif len(self.destinations) == 1:
                score += 1
        elif self.destination:
            score += 1

        # 服务需求
        if self.need_hotel:
            score += 1
        if self.need_weather:
            score += 1
        if self.budget or self.budget_amount:
            score += 1

        # 天数
        days = self.num_days or 0
        if days > 3:
            score += 1
        elif days > 1:
            score += 0.5

        return min(int(score), 10)


class SlotExtractor:
    """槽位提取器 - 从用户消息中提取结构化参数（增强版）"""

    # 常见中国城市列表
    COMMON_CITIES = [
        "北京", "上海", "广州", "深圳", "杭州", "成都", "西安", "重庆",
        "南京", "苏州", "厦门", "青岛", "大连", "三亚", "桂林", "丽江",
        "拉萨", "乌鲁木齐", "武汉", "长沙", "郑州", "天津", "哈尔滨",
        "沈阳", "济南", "昆明", "贵阳", "兰州", "西宁", "南宁",
        "宁波", "无锡", "常州", "扬州", "烟台", "威海", "泰安",
        "黄山", "九寨沟", "张家界", "大理", "香格里拉",
        "西双版纳", "海口", "珠海", "北海", "呼伦贝尔",
        "银川", "太原", "合肥", "南昌", "福州", "温州",
        "嘉兴", "绍兴", "金华", "台州", "丽水", "衢州",
        "舟山", "湖州", "嘉兴", "泉州", "漳州", "龙岩",
        "三明", "南平", "莆田", "景德镇", "萍乡", "新余",
        "鹰潭", "赣州", "宜春", "上饶", "吉安", "抚州",
        "开封", "洛阳", "安阳", "新乡", "焦作", "濮阳",
        "许昌", "漯河", "三门峡", "南阳", "商丘", "信阳",
        "周口", "驻马店", "宜昌", "襄阳", "鄂州", "荆门",
        "孝感", "荆州", "黄冈", "咸宁", "随州", "恩施",
        "丹江口", "神农架", "十堰", "仙桃", "天门", "潜江",
        "荆州", "黄石", "大冶", "咸宁", "鄂州", "黄冈",
        "孝感", "随州", "荆门", "荆州", "宜昌", "襄阳",
        "铜仁", "遵义", "毕节", "六盘水", "安顺", "黔西南",
        "黔东南", "黔南", "凉山", "甘孜", "阿坝", "攀枝花",
        "绵阳", "德阳", "广元", "遂宁", "内江", "乐山",
        "南充", "眉山", "雅安", "广安", "达州", "巴中",
        "资阳", "自贡", "泸州", "宜宾",
        # 简称/别名
        "蓉", "渝", "沪", "京", "津", "冀", "晋", "蒙", "辽", "吉",
        "黑", "苏", "浙", "皖", "闽", "赣", "鲁", "豫", "鄂", "湘",
        "粤", "桂", "琼", "川", "贵", "云", "藏", "陕", "甘", "青",
        "宁", "新", "港", "澳", "台",
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

    # 预算关键词映射
    BUDGET_KEYWORDS = {
        "低": ["便宜", "经济", "实惠", "穷游", "预算有限", "没钱"],
        "中": ["舒适", "中等", "标准", "正常"],
        "高": ["豪华", "高端", "奢华", "五星", "品质"],
    }

    def __init__(self, current_date: Optional[date] = None):
        """初始化

        Args:
            current_date: 当前日期（用于测试时注入）
        """
        self._current_date = current_date or datetime.now().date()

    def extract(self, message: str) -> SlotResult:
        """提取所有槽位"""
        logger.debug(f"[SlotExtractor] 开始提取槽位 | 消息长度={len(message)}")

        # 提取日期
        start_date, end_date, num_days = self._parse_dates(message)

        # 提取目的地
        destinations = self._extract_destinations(message)
        destination = destinations[0] if destinations else None

        # 构建结果
        result = SlotResult(
            destination=destination,
            destinations=destinations if len(destinations) > 1 else None,
            start_date=start_date,
            end_date=end_date,
            days=num_days if num_days > 0 else None,
            travelers=self._extract_travelers(message),
            budget=self._extract_budget_level(message),
            budget_amount=self._extract_budget_amount(message),
            need_hotel=self._extract_need_hotel(message),
            need_weather=self._extract_need_weather(message),
            need_route=self._extract_need_route(message),
            need_food=self._extract_need_food(message),
            interests=self._extract_interests(message),
        )

        # 记录提取结果
        logger.info(
            f"[SlotExtractor] ✅ 提取完成 | "
            f"destinations={result.destinations or result.destination} | "
            f"days={result.days} | "
            f"need_hotel={result.need_hotel} | "
            f"need_weather={result.need_weather} | "
            f"budget={result.budget or result.budget_amount} | "
            f"复杂度={result.complexity_score}"
        )

        return result

    def _extract_destinations(self, message: str) -> List[str]:
        """提取所有目的地城市（支持多个）"""
        found_cities = []

        # 特殊处理：组合简称（如"北上广深"、"江浙沪"等）
        combined_abbreviations = {
            "北上广深": ["北京", "上海", "广州", "深圳"],
            "北上广": ["北京", "上海", "广州"],
            "京津冀": ["北京", "天津", "石家庄"],
            "江浙沪": ["南京", "苏州", "杭州", "上海"],
            "长三角": ["上海", "南京", "杭州", "苏州", "宁波"],
            "珠三角": ["广州", "深圳", "珠海", "佛山", "东莞"],
            "粤港澳": ["广州", "深圳", "珠海", "香港", "澳门"],
            "西南": ["成都", "重庆", "昆明", "贵阳"],
            "西北": ["西安", "兰州", "银川", "西宁"],
            "东北": ["哈尔滨", "长春", "沈阳", "大连"],
            "华中": ["武汉", "长沙", "郑州"],
        }

        # 先检查组合简称
        for abbr, cities in combined_abbreviations.items():
            if abbr in message:
                logger.debug(f"[SlotExtractor] 识别到组合简称: {abbr} -> {cities}")
                return cities

        # 使用分隔符识别多个城市：顿号、逗号、和、还有、以及
        # 先检查是否有分隔符
        separators = r'[、,，和与及]+'
        if re.search(separators, message):
            # 分割消息
            parts = re.split(separators, message)
            for part in parts:
                # 遍历所有城市，不要break，确保找到该部分中的所有城市
                for city in self.COMMON_CITIES:
                    if city in part and city not in found_cities:
                        found_cities.append(city)

        # 如果分隔符方法没找到，尝试直接匹配
        if not found_cities:
            for city in self.COMMON_CITIES:
                if city in message:
                    found_cities.append(city)
                # 限制最多找到5个城市
                if len(found_cities) >= 5:
                    break

        if found_cities:
            logger.debug(f"[SlotExtractor] 提取到目的地: {found_cities}")
            return found_cities

        return []

    def _extract_need_hotel(self, message: str) -> bool:
        """检查是否需要酒店"""
        keywords = [
            "酒店", "住宿", "住", "宾馆", "旅店", "民宿",
            "睡觉", "过夜", "住店", "房间", "预订", "预定"
        ]
        return any(keyword in message for keyword in keywords)

    def _extract_need_weather(self, message: str) -> bool:
        """检查是否需要天气"""
        keywords = [
            "天气", "气温", "温度", "下雨", "晴天", "阴天",
            "气候", "穿衣", "带衣服", "冷热"
        ]
        return any(keyword in message for keyword in keywords)

    def _extract_need_route(self, message: str) -> bool:
        """检查是否需要路线规划"""
        keywords = [
            "路线", "行程", "怎么走", "怎么去", "交通",
            "路线图", "路线规划", "交通方式"
        ]
        return any(keyword in message for keyword in keywords)

    def _extract_need_food(self, message: str) -> bool:
        """检查是否需要美食推荐"""
        keywords = [
            "美食", "吃", "特色菜", "餐厅", "小吃",
            "推荐菜", "当地菜", "特产"
        ]
        return any(keyword in message for keyword in keywords)

    def _extract_budget_level(self, message: str) -> Optional[str]:
        """提取预算档次"""
        for level, keywords in self.BUDGET_KEYWORDS.items():
            if any(keyword in message for keyword in keywords):
                return level
        return None

    def _extract_budget_amount(self, message: str) -> Optional[int]:
        """提取具体预算金额"""
        # 中文数字映射
        chinese_num_map = {
            "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "壹": 1, "贰": 2, "叁": 3, "肆": 4, "伍": 5,
            "陆": 6, "柒": 7, "捌": 8, "玖": 9, "拾": 10,
        }

        # 匹配 "5000元", "3k", "1万", "2000块钱", "预算8000", "五万", "三万" 等
        patterns = [
            r'预算\s*(\d+)',  # "预算8000"
            r'(\d+)\s*[元块钱]',
            r'(\d+)\s*[kK]',  # 3k, 5K
            r'(\d+)\s*[wW万]',  # 1万, 2万
            r'([一二三四五六七八九十壹贰叁肆伍陆柒捌玖拾]+)\s*[万wW]',  # "五万", "三万"
        ]

        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                amount_str = match.group(1)

                # 处理中文数字
                if amount_str in chinese_num_map:
                    amount = chinese_num_map[amount_str]
                else:
                    try:
                        amount = int(amount_str)
                    except ValueError:
                        continue

                # 处理单位
                if '万' in message or 'w' in message or 'W' in message:
                    amount *= 10000
                elif 'k' in message or 'K' in message:
                    amount *= 1000

                if amount > 0:
                    logger.debug(f"[SlotExtractor] 提取预算金额: {amount}")
                    return amount
        return None

    def _parse_dates(self, message: str) -> tuple[Optional[str], Optional[str], int]:
        """解析日期，返回 (start_date, end_date, num_days)

        优先级:
        1. 节假日 (五一, 国庆等)
        2. 日期范围 (4月5日-4月10日)
        3. 月日 (3月15日)
        4. 相对日期 (明天, 下周等)
        5. 显式天数 (5天, 七日游, 三天两夜)
        """
        current_year = self._current_date.year

        # 优先级0: 显式天数 (新增)
        day_patterns = [
            r'(\d+)\s*[天日]',  # "5天", "7日"
            r'([一二三四五六七八九十百千]+)\s*[天日]',  # "五天", "七天"
            r'([一二三四五六七八九十百千]+)\s*日游',  # "七日游"
        ]
        chinese_num_map = {
            "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
            "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
            "百": 100, "千": 1000
        }

        for pattern in day_patterns:
            match = re.search(pattern, message)
            if match:
                num_str = match.group(1)
                # 转换中文数字
                if num_str in chinese_num_map:
                    days = chinese_num_map[num_str]
                else:
                    days = int(num_str)

                # 检查是否是 "两夜" 情况，通常两夜等于三天
                if "两夜" in message or "二夜" in message:
                    days = max(days, 3)
                elif "三夜" in message:
                    days = max(days, 4)

                logger.info(f"[SlotExtractor] 解析天数: {days}")
                return None, None, days

        # 优先级1: 节假日
        for holiday_name, (month, start_day, days_count) in self.HOLIDAYS.items():
            if holiday_name in message:
                try:
                    start = date(current_year, month, start_day)
                    end = start + timedelta(days=days_count - 1)
                    logger.info(f"[SlotExtractor] 解析节假日: '{holiday_name}'")
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
                logger.info(f"[SlotExtractor] 解析日期范围: {num_days}天")
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
                logger.info(f"[SlotExtractor] 解析月日: {date_str}")
                return date_str, date_str, 1
            except ValueError:
                pass

        # 默认: 无日期
        return None, None, 0

    def _extract_travelers(self, message: str) -> Optional[int]:
        """提取出行人数"""
        # 匹配 "X人", "X个人", "我们X个", "X位" 等
        patterns = [
            r'(\d+)\s*[个人位]',
            r'(\d+)\s*人',
            r'我们\s*(\d+)\s*个',
        ]
        for pattern in patterns:
            match = re.search(pattern, message)
            if match:
                return int(match.group(1))
        return None

    def _extract_interests(self, message: str) -> Optional[List[str]]:
        """提取兴趣标签"""
        interest_keywords = {
            "历史": ["历史", "古迹", "博物馆", "文物", "寺庙", "古建筑"],
            "自然": ["自然", "风景", "山水", "公园", "湖泊", "山脉"],
            "美食": ["美食", "小吃", "特色菜", "餐厅"],
            "购物": ["购物", "商场", "买", "特产"],
            "娱乐": ["娱乐", "游乐场", "主题公园", "酒吧"],
            "文化": ["文化", "艺术", "展览", "表演"],
            "户外": ["户外", "爬山", "徒步", "露营", "烧烤"],
        }

        found = []
        for interest, keywords in interest_keywords.items():
            if any(keyword in message for keyword in keywords):
                found.append(interest)

        return found if found else None
