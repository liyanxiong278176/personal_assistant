"""高德地图天气 API service for weather data.

References:
- 02-RESEARCH.md: 高德地图 API integration pattern
- ITIN-04: AI queries real-time weather and factors into itinerary
- TOOL-04: Agent autonomously calls weather API

API Docs: https://lbs.amap.com/api/webservice/guide/api/weatherinfo
使用高德天气API，与地图API共用同一个key，无需单独申请

优势:
1. 复用AMAP_API_KEY，无需额外申请
2. 数据与POI查询统一来源
3. 4天天气预报足够使用
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

import httpx

# Configuration - 使用高德地图API Key
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "")
AMAP_BASE_URL = "https://restapi.amap.com/v3"

# Cache settings (天气数据变化较慢，可以缓存更久)
WEATHER_CACHE_TTL = int(os.getenv("WEATHER_CACHE_TTL", "1800"))  # 30 minutes default

logger = logging.getLogger(__name__)


class AmapWeatherService:
    """Async 高德天气 API client with caching.

    使用高德地图天气API，与地图服务共用同一个key。
    """

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, tuple[Any, datetime]] = {}  # (data, expiry)

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client with connection pooling."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _get_cache(self, key: str) -> Optional[Any]:
        """Get cached data if not expired."""
        if key in self._cache:
            data, expiry = self._cache[key]
            if datetime.utcnow() < expiry:
                return data
            else:
                del self._cache[key]
        return None

    def _set_cache(self, key: str, data: Any) -> None:
        """Cache data with TTL."""
        expiry = datetime.utcnow() + timedelta(seconds=WEATHER_CACHE_TTL)
        self._cache[key] = (data, expiry)

    async def _get_city_adcode(self, city: str) -> Optional[str]:
        """获取城市adcode用于天气查询.

        Args:
            city: City name (e.g., "北京", "上海", "Beijing")

        Returns:
            城市adcode字符串，如果未找到返回None
        """
        cache_key = f"weather_adcode:{city}"
        cached = self._get_cache(cache_key)
        if cached:
            logger.info(f"[AmapWeather] Cache HIT - adcode: {city}")
            return cached

        if not AMAP_API_KEY:
            logger.error("[AmapWeather] ✗ AMAP_API_KEY not configured!")
            return None

        logger.info(f"[AmapWeather] → Getting adcode for city: {city}")

        try:
            client = await self._get_client()
            # 使用地理编码API获取城市adcode
            params = {
                "key": AMAP_API_KEY,
                "address": city,
                "output": "json"
            }

            response = await client.get(f"{AMAP_BASE_URL}/geocode/geo", params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "1" and data.get("geocodes"):
                geocode = data["geocodes"][0]
                adcode = geocode.get("adcode", "")
                if adcode:
                    logger.info(f"[AmapWeather] ✓ Success - adcode: {city} → {adcode}")
                    self._set_cache(cache_key, adcode)
                    return adcode
                else:
                    # 尝试从citycode获取
                    citycode = geocode.get("citycode", "")
                    if citycode:
                        logger.info(f"[AmapWeather] ✓ Using citycode: {city} → {citycode}")
                        self._set_cache(cache_key, citycode)
                        return citycode

            logger.warning(f"[AmapWeather] ✗ City not found: {city}")
            return None

        except httpx.HTTPStatusError as e:
            logger.error(f"[AmapWeather] ✗ HTTP error {e.response.status_code}")
        except httpx.HTTPError as e:
            logger.error(f"[AmapWeather] ✗ Network error: {e}")
        except Exception as e:
            logger.error(f"[AmapWeather] ✗ Unexpected error: {e}")

        return None

    async def get_realtime_weather(self, city: str) -> Dict[str, Any]:
        """获取当前天气状况.

        Args:
            city: City name (e.g., "北京", "上海")

        Returns:
            天气数据字典，包含温度、天气状况、湿度、风力等
            如果API调用失败返回错误字典
        """
        logger.info(f"[AmapWeather] ===== Realtime Weather Request =====")
        logger.info(f"[AmapWeather] City: {city}")

        if not AMAP_API_KEY:
            logger.error("[AmapWeather] ✗ AMAP_API_KEY not configured!")
            return {"error": "AMAP_API_KEY not configured"}

        adcode = await self._get_city_adcode(city)
        if not adcode:
            logger.error(f"[AmapWeather] ✗ Could not get adcode for {city}")
            return {"error": f"City not found: {city}"}

        # Check cache
        cache_key = f"weather_now:{adcode}"
        cached = self._get_cache(cache_key)
        if cached:
            logger.info(f"[AmapWeather] Cache HIT - realtime weather: {city}")
            return cached

        logger.info(f"[AmapWeather] → Calling realtime weather API")
        logger.info(f"[AmapWeather]    URL: {AMAP_BASE_URL}/weather/weatherInfo")

        try:
            client = await self._get_client()
            response = await client.get(
                f"{AMAP_BASE_URL}/weather/weatherInfo",
                params={"city": adcode, "key": AMAP_API_KEY, "extensions": "base"}
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"[AmapWeather] ← Response status: {data.get('status')}")

            if data.get("status") == "1" and data.get("lives"):
                live = data["lives"][0]
                weather = {
                    "city": live.get("city", city),
                    "province": live.get("province", ""),
                    "adcode": adcode,
                    "temp": live.get("temperature", ""),  # 温度
                    "weather": live.get("weather", ""),  # 天气现象
                    "wind_direction": live.get("winddirection", ""),  # 风向
                    "wind_power": live.get("windpower", ""),  # 风力级别
                    "humidity": live.get("humidity", ""),  # 湿度
                    "report_time": live.get("reporttime", ""),  # 数据发布时间
                }
                logger.info(f"[AmapWeather] ✓ Success - {weather['city']}: {weather['temp']}°C, {weather['weather']}")
                self._set_cache(cache_key, weather)
                return weather
            else:
                logger.warning(f"[AmapWeather] ✗ API error - status: {data.get('status')}, info: {data.get('info')}")
                return {"error": f"Weather API error: {data.get('info', 'Unknown error')}"}

        except httpx.HTTPStatusError as e:
            logger.error(f"[AmapWeather] ✗ HTTP error {e.response.status_code}")
            return {"error": f"HTTP {e.response.status_code}"}
        except httpx.HTTPError as e:
            logger.error(f"[AmapWeather] ✗ Network error: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"[AmapWeather] ✗ Unexpected error: {e}")
            return {"error": str(e)}

    async def get_weather_forecast(
        self, city: str, days: int = 4
    ) -> Dict[str, Any]:
        """获取天气预报.

        Args:
            city: City name (e.g., "北京", "上海")
            days: Number of days (高德支持4天预报)

        Returns:
            预报数据字典，包含每日天气状况
        """
        logger.info(f"[AmapWeather] ===== Weather Forecast Request =====")
        logger.info(f"[AmapWeather] City: {city}, Days: {days}")

        if not AMAP_API_KEY:
            logger.error("[AmapWeather] ✗ AMAP_API_KEY not configured!")
            return {"error": "AMAP_API_KEY not configured"}

        # 高德天气API最多支持4天预报
        days = min(days, 4)

        adcode = await self._get_city_adcode(city)
        if not adcode:
            logger.error(f"[AmapWeather] ✗ Could not get adcode for {city}")
            return {"error": f"City not found: {city}"}

        # Check cache
        cache_key = f"weather_forecast:{adcode}"
        cached = self._get_cache(cache_key)
        if cached:
            logger.info(f"[AmapWeather] Cache HIT - forecast: {city}")
            return cached

        logger.info(f"[AmapWeather] → Calling forecast API")
        logger.info(f"[AmapWeather]    URL: {AMAP_BASE_URL}/weather/weatherInfo")

        try:
            client = await self._get_client()
            response = await client.get(
                f"{AMAP_BASE_URL}/weather/weatherInfo",
                params={"city": adcode, "key": AMAP_API_KEY, "extensions": "all"}
            )
            response.raise_for_status()
            data = response.json()

            logger.info(f"[AmapWeather] ← Response status: {data.get('status')}")

            if data.get("status") == "1" and data.get("forecasts"):
                forecast_data = data["forecasts"][0]
                casts = forecast_data.get("casts", [])

                forecast = {
                    "city": forecast_data.get("city", city),
                    "adcode": adcode,
                    "province": forecast_data.get("province", ""),
                    "report_time": forecast_data.get("reporttime", ""),
                    "days": len(casts),
                    "forecasts": [
                        {
                            "date": cast.get("date", ""),
                            "week": cast.get("week", ""),
                            "day_weather": cast.get("dayweather", ""),  # 白天天气
                            "night_weather": cast.get("nightweather", ""),  # 晚上天气
                            "temp_max": cast.get("daytemp", ""),  # 白天温度
                            "temp_min": cast.get("nighttemp", ""),  # 晚上温度
                            "wind_direction_day": cast.get("daywind", ""),  # 白天风向
                            "wind_direction_night": cast.get("nightwind", ""),  # 晚上风向
                            "wind_power_day": cast.get("daypower", ""),  # 白天风力
                            "wind_power_night": cast.get("nightpower", ""),  # 晚上风力
                        }
                        for cast in casts[:days]
                    ]
                }

                logger.info(f"[AmapWeather] ✓ Success - got {len(forecast['forecasts'])} days forecast")
                if forecast['forecasts']:
                    first_day = forecast['forecasts'][0]
                    logger.info(f"[AmapWeather]     Day 1: {first_day['date']} - {first_day['day_weather']}, {first_day['temp_min']}~{first_day['temp_max']}°C")

                self._set_cache(cache_key, forecast)
                return forecast
            else:
                logger.warning(f"[AmapWeather] ✗ API error - status: {data.get('status')}, info: {data.get('info')}")
                return {"error": f"Weather API error: {data.get('info', 'Unknown error')}"}

        except httpx.HTTPStatusError as e:
            logger.error(f"[AmapWeather] ✗ HTTP error {e.response.status_code}")
            return {"error": f"HTTP {e.response.status_code}"}
        except httpx.HTTPError as e:
            logger.error(f"[AmapWeather] ✗ Network error: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"[AmapWeather] ✗ Unexpected error: {e}")
            return {"error": str(e)}


# Global weather service instance
weather_service = AmapWeatherService()
