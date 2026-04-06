"""高德地图 (Amap) API service for map data.

References:
- 02-RESEARCH.md: 高德地图 API integration pattern
- TOOL-02: Amap/Baidu Map API integration
- TOOL-05: Agent autonomously calls map API for locations/routes
- PERS-03: User can search destinations and activities

API Docs: https://lbs.amap.com/api/webservice/guide/api/search
Free Tier: 2,000-5,000 requests/day for personal developers
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List

import httpx

# Configuration
AMAP_API_KEY = os.getenv("AMAP_API_KEY", "9b42cd0a72b507c5a3e87f1e93babb03")
AMAP_BASE_URL = "https://restapi.amap.com/v3"

# Cache settings (per research: 15 min TTL for POI data)
MAP_CACHE_TTL = int(os.getenv("MAP_CACHE_TTL", "900"))  # 15 minutes default

# 高德地图 POI types (simplified subset)
POI_TYPES = {
    "tourist": "110000",      # Tourist attractions
    "museum": "110101",       # Museums
    "park": "110102",         # Parks
    "hotel": "100000",        # Hotels
    "restaurant": "050000",   # Restaurants
    "shopping": "060000",     # Shopping
    "transport": "150000",    # Transportation
}

logger = logging.getLogger(__name__)


class AmapService:
    """Async 高德地图 API client with caching."""

    def __init__(self):
        self._client: Optional[httpx.AsyncClient] = None
        self._cache: Dict[str, tuple[Any, datetime]] = {}

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client with connection pooling."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(10.0),
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
                event_hooks={"response": [self._log_response]}
            )
        return self._client

    async def _log_response(self, response: httpx.Response) -> None:
        """统一 HTTP 响应日志，格式与 httpx 默认一致"""
        try:
            status = response.status_code
            method = response.request.method
            url = str(response.request.url)
            elapsed = response.elapsed.total_seconds() * 1000
            logger.info(
                f"[TOOL:HTTP] {method} {url} \"HTTP/1.1 {status}\" | {elapsed:.0f}ms"
            )
        except Exception:
            pass

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
        expiry = datetime.utcnow() + timedelta(seconds=MAP_CACHE_TTL)
        self._cache[key] = (data, expiry)

    async def search_poi(
        self,
        keywords: str,
        city: str,
        poi_type: Optional[str] = None,
        limit: int = 20
    ) -> Dict[str, Any]:
        """搜索POI (Point of Interest).

        Args:
            keywords: Search keywords (e.g., "故宫", "博物馆")
            city: City name or city code (e.g., "北京", "上海")
            poi_type: POI type code (optional, uses POI_TYPES if string key)
            limit: Number of results (max 25 per 高德地图 API)

        Returns:
            POI search results with name, address, location, etc.
        """
        logger.info(f"[Amap] ===== POI Search Request =====")
        logger.info(f"[Amap] Keywords: {keywords}, City: {city}, Limit: {limit}")

        if not AMAP_API_KEY:
            logger.error("[Amap] ✗ API_KEY not configured!")
            return {"error": "AMAP_API_KEY not configured"}

        # Validate limit
        limit = min(limit, 25)

        # Map POI type string to code
        if poi_type and poi_type in POI_TYPES:
            poi_type = POI_TYPES[poi_type]

        # Check cache
        cache_key = f"poi:{city}:{keywords}:{poi_type}:{limit}"
        cached = self._get_cache(cache_key)
        if cached:
            logger.info(f"[Amap] Cache HIT - POI search: {keywords}")
            return cached

        logger.info(f"[Amap] → Calling POI search API")
        logger.info(f"[Amap]    URL: {AMAP_BASE_URL}/place/text")

        try:
            client = await self._get_client()
            params = {
                "key": AMAP_API_KEY,
                "keywords": keywords,
                "city": city,
                "output": "json",
                "offset": limit,
                "extensions": "all"  # Get detailed info
            }

            if poi_type:
                params["types"] = poi_type

            response = await client.get(f"{AMAP_BASE_URL}/place/text", params=params)
            response.raise_for_status()
            data = response.json()

            logger.info(f"[Amap] ← Response status: {data.get('status')}")

            if data.get("status") == "1" and data.get("pois"):
                results = []
                for poi in data["pois"][:limit]:
                    # Parse location from "lng,lat" format
                    location = poi.get("location", "")
                    lng, lat = "", ""
                    if location:
                        parts = location.split(",")
                        if len(parts) == 2:
                            lng, lat = parts

                    results.append({
                        "id": poi["id"],
                        "name": poi["name"],
                        "address": poi.get("address", ""),
                        "location": {
                            "lng": lng,
                            "lat": lat
                        },
                        "tel": poi.get("tel", ""),
                        "type": poi.get("type", ""),
                        "rating": poi.get("business_ext", {}).get("rating"),
                        "cost": poi.get("business_ext", {}).get("cost"),
                        "distance": poi.get("distance"),
                    })

                logger.info(f"[Amap] ✓ Success - found {len(results)} POIs")
                if results:
                    logger.info(f"[Amap]     First result: {results[0]['name']}")
                self._set_cache(cache_key, {"results": results, "count": len(results)})
                return {"results": results, "count": len(results)}
            else:
                logger.warning(f"[Amap] ✗ API error - status: {data.get('status')}, info: {data.get('info')}")
                return {"error": f"POI search failed: {data.get('info', 'Unknown error')}"}

        except httpx.HTTPStatusError as e:
            logger.error(f"[Amap] ✗ HTTP error {e.response.status_code}")
            return {"error": f"HTTP {e.response.status_code}"}
        except httpx.HTTPError as e:
            logger.error(f"[Amap] ✗ Network error: {e}")
            return {"error": str(e)}
        except Exception as e:
            logger.error(f"[Amap] ✗ Unexpected error: {e}")
            return {"error": str(e)}

    async def geocode(self, address: str, city: Optional[str] = None) -> Dict[str, Any]:
        """Convert address to coordinates (geocoding).

        Args:
            address: Address string
            city: City name (optional, improves accuracy)

        Returns:
            Coordinates (lng, lat) and formatted address
        """
        if not AMAP_API_KEY:
            return {"error": "AMAP_API_KEY not configured"}

        # Check cache
        cache_key = f"geocode:{address}:{city or ''}"
        cached = self._get_cache(cache_key)
        if cached:
            logger.info(f"Cache hit for geocode: {address}")
            return cached

        try:
            client = await self._get_client()
            params = {
                "key": AMAP_API_KEY,
                "address": address,
                "output": "json"
            }

            if city:
                params["city"] = city

            response = await client.get(f"{AMAP_BASE_URL}/geocode/geo", params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "1" and data.get("geocodes"):
                geocode = data["geocodes"][0]
                location = geocode.get("location", "")
                lng, lat = "", ""
                if location:
                    parts = location.split(",")
                    if len(parts) == 2:
                        lng, lat = parts

                result = {
                    "formatted_address": geocode.get("formatted_address", address),
                    "location": {
                        "lng": lng,
                        "lat": lat
                    },
                    "level": geocode.get("level", ""),
                    "city": geocode.get("city", ""),
                    "province": geocode.get("province", "")
                }
                self._set_cache(cache_key, result)
                return result
            else:
                return {"error": f"Geocoding failed: {data.get('info', 'Unknown error')}"}

        except httpx.HTTPError as e:
            logger.error(f"高德地图 geocoding error: {e}")
            return {"error": str(e)}

    async def plan_driving_route(
        self,
        origin: tuple[float, float],
        destination: tuple[float, float],
        strategy: int = 10
    ) -> Dict[str, Any]:
        """Plan driving route between two points.

        Args:
            origin: Origin coordinates (lng, lat)
            destination: Destination coordinates (lng, lat)
            strategy: Route strategy
                10: Avoid congestion (default)
                11: Time shortest, distance shortest, avoid congestion
                13: No highways
                14: Avoid tolls

        Returns:
            Route with distance, duration, tolls, and steps
        """
        if not AMAP_API_KEY:
            return {"error": "AMAP_API_KEY not configured"}

        # Check cache
        cache_key = f"route:{origin[0]},{origin[1]}:{destination[0]},{destination[1]}:{strategy}"
        cached = self._get_cache(cache_key)
        if cached:
            logger.info(f"Cache hit for route planning")
            return cached

        try:
            client = await self._get_client()
            params = {
                "key": AMAP_API_KEY,
                "origin": f"{origin[0]},{origin[1]}",
                "destination": f"{destination[0]},{destination[1]}",
                "extensions": "all",
                "strategy": strategy,
                "output": "json"
            }

            response = await client.get(f"{AMAP_BASE_URL}/direction/driving", params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("status") == "1" and data.get("route") and data["route"].get("paths"):
                path = data["route"]["paths"][0]

                # Extract polyline for map display
                polyline = self._extract_polyline(path)

                result = {
                    "distance": int(path.get("distance", "0")),  # meters
                    "duration": int(path.get("duration", "0")),  # seconds
                    "tolls": int(path.get("tolls", "0")),  # cost in yuan
                    "distance_km": round(int(path.get("distance", "0")) / 1000, 2),
                    "duration_min": round(int(path.get("duration", "0")) / 60, 1),
                    "polyline": polyline,
                    "steps": self._parse_steps(path.get("steps", []))
                }
                self._set_cache(cache_key, result)
                return result
            else:
                return {"error": f"Route planning failed: {data.get('info', 'Unknown error')}"}

        except httpx.HTTPError as e:
            logger.error(f"高德地图 route planning error: {e}")
            return {"error": str(e)}

    def _extract_polyline(self, path: dict) -> str:
        """Extract polyline from route path for map display."""
        # 高德地图 returns polyline as "step" instruction
        # For frontend map, we'll return the encoded polyline if available
        return path.get("polyline", "")

    def _parse_steps(self, steps: List[dict]) -> List[dict]:
        """Parse route steps into readable instructions."""
        parsed = []
        for step in steps:
            parsed.append({
                "instruction": step.get("instruction", ""),
                "distance": int(step.get("distance", "0")),
                "duration": int(step.get("duration", "0")),
                "action": step.get("action", ""),
                "road_name": step.get("road", "")
            })
        return parsed

    async def get_city_adcode(self, city: str) -> Optional[str]:
        """获取城市adcode，用于天气查询等API.

        Args:
            city: 城市名称 (e.g., "北京", "上海", "Beijing")

        Returns:
            城市adcode字符串，如果未找到返回None
        """
        if not AMAP_API_KEY:
            logger.error("[Amap] ✗ API_KEY not configured!")
            return None

        # Check cache
        cache_key = f"adcode:{city}"
        cached = self._get_cache(cache_key)
        if cached:
            logger.info(f"[Amap] Cache HIT - adcode: {city} → {cached}")
            return cached

        logger.info(f"[Amap] → Getting adcode for city: {city}")

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
                    logger.info(f"[Amap] ✓ Success - adcode: {city} → {adcode}")
                    self._set_cache(cache_key, adcode)
                    return adcode
                else:
                    # 尝试从citycode获取
                    citycode = geocode.get("citycode", "")
                    if citycode:
                        logger.info(f"[Amap] ✓ Using citycode: {city} → {citycode}")
                        self._set_cache(cache_key, citycode)
                        return citycode

            logger.warning(f"[Amap] ✗ City not found: {city}")
            return None

        except httpx.HTTPStatusError as e:
            logger.error(f"[Amap] ✗ HTTP error {e.response.status_code}")
        except httpx.HTTPError as e:
            logger.error(f"[Amap] ✗ Network error: {e}")
        except Exception as e:
            logger.error(f"[Amap] ✗ Unexpected error: {e}")

        return None


# Global map service instance
map_service = AmapService()
