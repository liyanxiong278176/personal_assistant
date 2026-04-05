"""内置工具 - 使用高德地图API

集成真实的天气查询、POI搜索、路线规划功能。
使用 app.services 中的 AmapService 和 AmapWeatherService。
"""

import logging
from .base import Tool
from .registry import global_registry

logger = logging.getLogger(__name__)


class WeatherTool(Tool):
    """天气查询工具 - 使用高德地图天气API"""

    @property
    def name(self) -> str:
        return "get_weather"

    @property
    def description(self) -> str:
        return "查询指定城市的天气情况（使用高德地图API），支持4天天气预报"

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, city: str, days: int = 4, **kwargs) -> dict:
        """使用高德天气API查询天气"""
        from app.services.weather_service import weather_service

        logger.info(f"[WeatherTool] 查询天气: city={city}, days={days}")

        # 获取天气预报
        forecast = await weather_service.get_weather_forecast(city, days)

        if "error" in forecast:
            logger.error(f"[WeatherTool] 查询失败: {forecast['error']}")
            return forecast

        # 格式化返回结果
        result = {
            "city": forecast.get("city", city),
            "report_time": forecast.get("report_time", ""),
            "forecast": []
        }

        for day in forecast.get("forecasts", []):
            result["forecast"].append({
                "date": day["date"],
                "week": day["week"],
                "weather": f"{day['day_weather']}转{day['night_weather']}",
                "temp_min": day["temp_min"],
                "temp_max": day["temp_max"],
                "wind": f"{day['wind_direction_day']}{day['wind_power_day']}",
                "tips": self._get_weather_tips(day["day_weather"])
            })

        logger.info(f"[WeatherTool] ✓ 成功获取 {len(result['forecast'])} 天天气预报")
        return result

    def _get_weather_tips(self, weather: str) -> str:
        """根据天气状况给出建议"""
        tips_map = {
            "晴": "天气晴朗，适合出行和拍照",
            "多云": "天气不错，适宜户外活动",
            "阴": "天气阴沉，可能需要降雨",
            "雨": "有雨，请带雨具",
            "雪": "有雪，注意保暖和路面湿滑",
            "雾": "有雾，注意行车安全",
            "沙尘": "有沙尘，请戴口罩",
        }
        for key, tip in tips_map.items():
            if key in weather:
                return tip
        return "适宜出行"


class POISearchTool(Tool):
    """景点搜索工具 - 使用高德地图POI搜索API"""

    @property
    def name(self) -> str:
        return "search_poi"

    @property
    def description(self) -> str:
        return "搜索指定城市的景点、餐厅、酒店等POI信息（使用高德地图API），最多返回25个结果"

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, keywords: str, city: str, limit: int = 10, **kwargs) -> dict:
        """使用高德地图API搜索POI"""
        from app.services.map_service import map_service

        logger.info(f"[POISearchTool] 搜索POI: city={city}, keywords={keywords}, limit={limit}")

        result = await map_service.search_poi(
            keywords=keywords,
            city=city,
            limit=min(limit, 25)
        )

        if "error" in result:
            logger.error(f"[POISearchTool] 搜索失败: {result['error']}")
            return result

        # 格式化POI结果
        pois = []
        for poi in result.get("results", []):
            pois.append({
                "name": poi["name"],
                "address": poi.get("address", ""),
                "type": poi.get("type", ""),
                "tel": poi.get("tel", "暂无电话"),
                "rating": poi.get("rating") or "暂无评分",
                "distance": poi.get("distance"),
                "location": poi.get("location", {})
            })

        logger.info(f"[POISearchTool] ✓ 成功找到 {len(pois)} 个POI")
        return {
            "city": city,
            "keywords": keywords,
            "count": len(pois),
            "results": pois
        }


class RoutePlanTool(Tool):
    """路线规划工具 - 使用高德地图路线规划API"""

    @property
    def name(self) -> str:
        return "plan_route"

    @property
    def description(self) -> str:
        return "规划多个地点之间的驾车路线（使用高德地图API），返回距离、时长、路费等信息"

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, destinations: list, origin: str = None, **kwargs) -> dict:
        """使用高德地图API规划路线"""
        from app.services.map_service import map_service

        logger.info(f"[RoutePlanTool] 规划路线: destinations={destinations}, origin={origin}")

        if len(destinations) < 2:
            return {
                "error": "至少需要2个目的地才能规划路线",
                "destinations": destinations
            }

        # 获取第一个和最后一个地点的坐标
        origin_city = origin or destinations[0]
        dest_city = destinations[-1]

        # 先地理编码获取坐标
        origin_coords = await map_service.geocode(origin_city)
        dest_coords = await map_service.geocode(dest_city)

        if "error" in origin_coords:
            logger.error(f"[RoutePlanTool] 获取起点坐标失败: {origin_coords['error']}")
            return {
                "error": f"无法找到起点: {origin_city}",
                "suggestion": "请检查城市名称是否正确"
            }

        if "error" in dest_coords:
            logger.error(f"[RoutePlanTool] 获取终点坐标失败: {dest_coords['error']}")
            return {
                "error": f"无法找到终点: {dest_city}",
                "suggestion": "请检查城市名称是否正确"
            }

        # 规划驾车路线
        origin_point = (float(origin_coords["location"]["lng"]), float(origin_coords["location"]["lat"]))
        dest_point = (float(dest_coords["location"]["lng"]), float(dest_coords["location"]["lat"]))

        route = await map_service.plan_driving_route(origin_point, dest_point)

        if "error" in route:
            logger.error(f"[RoutePlanTool] 路线规划失败: {route['error']}")
            return route

        # 格式化路线结果
        result = {
            "origin": origin_city,
            "destination": dest_city,
            "distance_km": route.get("distance_km", 0),
            "duration_hours": route.get("duration_min", 0) / 60,
            "tolls": route.get("tolls", 0),
            "summary": f"从{origin_city}到{dest_city}，约{route.get('distance_km', 0)}公里，{route.get('duration_min', 0) / 60:.1f}小时",
            "steps": route.get("steps", [])[:5]  # 只返回前5个步骤
        }

        logger.info(f"[RoutePlanTool] ✓ 路线规划成功: {result['summary']}")
        return result


class GeocodeTool(Tool):
    """地理编码工具 - 将地址转换为坐标"""

    @property
    def name(self) -> str:
        return "geocode"

    @property
    def description(self) -> str:
        return "将地址或地名转换为经纬度坐标（使用高德地图API）"

    @property
    def is_readonly(self) -> bool:
        return True

    @property
    def is_concurrency_safe(self) -> bool:
        return True

    async def execute(self, address: str, city: str = None, **kwargs) -> dict:
        """使用高德地图API进行地理编码"""
        from app.services.map_service import map_service

        logger.info(f"[GeocodeTool] 地理编码: address={address}, city={city}")

        result = await map_service.geocode(address, city)

        if "error" in result:
            logger.error(f"[GeocodeTool] 地理编码失败: {result['error']}")
            return result

        logger.info(f"[GeocodeTool] ✓ 成功: {result['formatted_address']} -> ({result['location']['lng']}, {result['location']['lat']})")
        return result


def register_builtin_tools():
    """注册所有内置工具到全局注册表"""
    tools = [
        WeatherTool(),
        POISearchTool(),
        RoutePlanTool(),
        GeocodeTool()
    ]

    for tool in tools:
        global_registry.register(tool)
        logger.info(f"[BuiltinTools] 已注册工具: {tool.name}")

    logger.info(f"[BuiltinTools] 内置工具注册完成 | 总数={len(tools)} | 使用高德地图API")
    return tools


# 自动注册（模块导入时）
register_builtin_tools()
