"""LangChain tools for map data retrieval.

References:
- TOOL-02: Amap/Baidu Map API integration
- TOOL-05: Agent autonomously calls map API for locations/routes
- PERS-03: User can search destinations and activities
- 02-RESEARCH.md: LangChain @tool decorator pattern
"""

import json
import logging
from typing import Literal

from langchain_core.tools import tool

from app.services.map_service import map_service

logger = logging.getLogger(__name__)


@tool
async def search_attraction(
    city: str,
    attraction_type: str = "景点",
    keywords: str = ""
) -> str:
    """搜索指定城市的景点信息.

    可以根据景点类型（如博物馆、公园、古迹）或关键词搜索景点。

    Args:
        city: 城市名称，如"北京"、"上海"、"杭州"
        attraction_type: 景点类型，如"博物馆"、"公园"、"古迹"、"景点"
        keywords: 搜索关键词（可选），如"故宫"、"西湖"

    Returns:
        JSON格式的景点列表字符串，包含名称、地址、评分等信息
    """
    logger.info(f"Tool called: search_attraction for city={city}, type={attraction_type}, keywords={keywords}")

    # Build search keywords
    search_keywords = keywords or attraction_type

    result = await map_service.search_poi(
        keywords=search_keywords,
        city=city,
        poi_type="tourist" if attraction_type == "景点" else None,
        limit=10
    )

    if "error" in result:
        return json.dumps({"error": result["error"]}, ensure_ascii=False)

    # Format for LLM consumption
    attractions = []
    for poi in result["results"]:
        attractions.append({
            "name": poi["name"],
            "address": poi["address"],
            "rating": poi.get("rating", "N/A"),
            "tel": poi.get("tel", "N/A"),
            "type": poi.get("type", ""),
            "summary": f"{poi['name']} - {poi['address']} (评分: {poi.get('rating', 'N/A')})"
        })

    return json.dumps({
        "city": city,
        "count": result["count"],
        "attractions": attractions,
        "summary": f"在{city}找到{result['count']}个{attraction_type}：\n" + "\n".join([a["summary"] for a in attractions[:5]])
    }, ensure_ascii=False)


@tool
async def search_poi(
    city: str,
    keywords: str,
    category: Literal["hotel", "restaurant", "shopping", "transport"] = "hotel"
) -> str:
    """搜索指定城市的POI信息（酒店、餐厅、商场等）.

    Args:
        city: 城市名称，如"北京"、"上海"
        keywords: 搜索关键词，如"希尔顿"、"海底捞"
        category: POI类别 - hotel(酒店)、restaurant(餐厅)、shopping(商场)、transport(交通)

    Returns:
        JSON格式的POI列表字符串
    """
    logger.info(f"Tool called: search_poi for city={city}, keywords={keywords}, category={category}")

    result = await map_service.search_poi(
        keywords=keywords,
        city=city,
        poi_type=category,
        limit=10
    )

    if "error" in result:
        return json.dumps({"error": result["error"]}, ensure_ascii=False)

    # Format for LLM consumption
    pois = []
    for poi in result["results"]:
        pois.append({
            "name": poi["name"],
            "address": poi["address"],
            "tel": poi.get("tel", "N/A"),
            "distance": poi.get("distance"),
            "summary": f"{poi['name']} - {poi['address']}"
        })

    category_names = {
        "hotel": "酒店",
        "restaurant": "餐厅",
        "shopping": "商场",
        "transport": "交通"
    }

    return json.dumps({
        "city": city,
        "category": category_names[category],
        "count": result["count"],
        "pois": pois,
        "summary": f"在{city}找到{result['count']}家{category_names[category]}：\n" + "\n".join([p["summary"] for p in pois[:5]])
    }, ensure_ascii=False)


@tool
async def get_location_coords(address: str, city: str = "") -> str:
    """获取地址的经纬度坐标.

    用于将地址转换为地图坐标，便于在地图上标记位置。

    Args:
        address: 地址，如"天安门"、"故宫博物院"
        city: 城市名称（可选，提高精度），如"北京"

    Returns:
        JSON格式的坐标信息字符串
    """
    logger.info(f"Tool called: get_location_coords for address={address}, city={city}")

    result = await map_service.geocode(address, city if city else None)

    if "error" in result:
        return json.dumps({"error": result["error"]}, ensure_ascii=False)

    lng = result["location"]["lng"]
    lat = result["location"]["lat"]

    return json.dumps({
        "address": result["formatted_address"],
        "lng": lng,
        "lat": lat,
        "coords": f"({lng}, {lat})",
        "summary": f"{result['formatted_address']} 的坐标是 ({lng}, {lat})"
    }, ensure_ascii=False)


@tool
async def plan_route(
    origin: str,
    destination: str,
    city: str = ""
) -> str:
    """规划两个地点之间的驾车路线.

    用于计算景点之间的距离、时间和路线建议。

    Args:
        origin: 起点地址或地名，如"天安门"
        destination: 终点地址或地名，如"颐和园"
        city: 城市名称（可选），如"北京"

    Returns:
        JSON格式的路线规划信息字符串，包含距离、时间、费用等
    """
    logger.info(f"Tool called: plan_route from {origin} to {destination}")

    # First geocode both locations
    origin_result = await map_service.geocode(origin, city if city else None)
    if "error" in origin_result:
        return json.dumps({"error": f"起点解析失败: {origin_result['error']}"}, ensure_ascii=False)

    dest_result = await map_service.geocode(destination, city if city else None)
    if "error" in dest_result:
        return json.dumps({"error": f"终点解析失败: {dest_result['error']}"}, ensure_ascii=False)

    # Get coordinates
    origin_coords = (float(origin_result["location"]["lng"]), float(origin_result["location"]["lat"]))
    dest_coords = (float(dest_result["location"]["lng"]), float(dest_result["location"]["lat"]))

    # Plan route
    route_result = await map_service.plan_driving_route(origin_coords, dest_coords)

    if "error" in route_result:
        return json.dumps({"error": route_result["error"]}, ensure_ascii=False)

    # Format for LLM consumption
    return json.dumps({
        "origin": origin_result["formatted_address"],
        "destination": dest_result["formatted_address"],
        "distance_km": route_result["distance_km"],
        "duration_min": route_result["duration_min"],
        "tolls": route_result["tolls"],
        "summary": f"从{origin_result['formatted_address']}到{dest_result['formatted_address']}："
                   f"距离{route_result['distance_km']}公里，"
                   f"预计{route_result['duration_min']}分钟，"
                   f"过路费{route_result['tolls']}元"
    }, ensure_ascii=False)
