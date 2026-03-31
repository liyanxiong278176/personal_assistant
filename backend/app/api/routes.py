"""Route planning API endpoints.

References:
- ITIN-03: Itinerary visualized on map with routes and POI locations
- PERS-03: User can search destinations and activities
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.services.map_service import map_service

router = APIRouter(prefix="/api/routes", tags=["routes"])
logger = logging.getLogger(__name__)


class RouteRequest(BaseModel):
    """Route planning request."""
    origin: str = Field(..., description="Starting location name")
    destination: str = Field(..., description="Ending location name")
    city: Optional[str] = Field(None, description="City name for better accuracy")
    strategy: int = Field(10, description="Route strategy: 10=avoid congestion, 11=shortest, 13=no highways, 14=avoid tolls")


class MultiPointRouteRequest(BaseModel):
    """Multi-point route planning request."""
    locations: List[str] = Field(..., min_length=2, description="List of location names in order")
    city: Optional[str] = Field(None, description="City name")
    strategy: int = Field(10, description="Route strategy")


@router.post("/plan")
async def plan_route(request: RouteRequest) -> dict:
    """Plan a driving route between two locations.

    Args:
        request: Route request with origin, destination, city

    Returns:
        Route with distance, duration, polyline, and steps
    """
    try:
        # Geocode origin
        origin_result = await map_service.geocode(request.origin, request.city)
        if "error" in origin_result:
            raise HTTPException(status_code=400, detail=f"起点解析失败: {origin_result['error']}")

        # Geocode destination
        dest_result = await map_service.geocode(request.destination, request.city)
        if "error" in dest_result:
            raise HTTPException(status_code=400, detail=f"终点解析失败: {dest_result['error']}")

        # Get coordinates
        origin_coords = (
            float(origin_result["location"]["lng"]),
            float(origin_result["location"]["lat"])
        )
        dest_coords = (
            float(dest_result["location"]["lng"]),
            float(dest_result["location"]["lat"])
        )

        # Plan route
        route_result = await map_service.plan_driving_route(
            origin_coords,
            dest_coords,
            request.strategy
        )

        if "error" in route_result:
            raise HTTPException(status_code=500, detail=route_result["error"])

        return {
            "origin": {
                "name": request.origin,
                "formatted_address": origin_result["formatted_address"],
                "coordinates": origin_result["location"]
            },
            "destination": {
                "name": request.destination,
                "formatted_address": dest_result["formatted_address"],
                "coordinates": dest_result["location"]
            },
            "route": route_result
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Route planning error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/multi-point")
async def plan_multi_point_route(request: MultiPointRouteRequest) -> dict:
    """Plan a route through multiple waypoints.

    Args:
        request: Multi-point route request with locations list

    Returns:
        Route segments and total summary
    """
    try:
        if len(request.locations) < 2:
            raise HTTPException(status_code=400, detail="至少需要2个地点")

        # Geocode all locations
        waypoints = []
        for location in request.locations:
            result = await map_service.geocode(location, request.city)
            if "error" in result:
                raise HTTPException(status_code=400, detail=f"地点解析失败 '{location}': {result['error']}")

            waypoints.append({
                "name": location,
                "formatted_address": result["formatted_address"],
                "coordinates": result["location"]
            })

        # Plan route segments
        segments = []
        total_distance = 0
        total_duration = 0
        all_polylines = []

        for i in range(len(waypoints) - 1):
            origin_coords = (
                float(waypoints[i]["coordinates"]["lng"]),
                float(waypoints[i]["coordinates"]["lat"])
            )
            dest_coords = (
                float(waypoints[i + 1]["coordinates"]["lng"]),
                float(waypoints[i + 1]["coordinates"]["lat"])
            )

            segment = await map_service.plan_driving_route(
                origin_coords,
                dest_coords,
                request.strategy
            )

            if "error" in segment:
                raise HTTPException(status_code=500, detail=f"路段规划失败: {segment['error']}")

            segments.append({
                "from": waypoints[i]["name"],
                "to": waypoints[i + 1]["name"],
                "distance_km": segment["distance_km"],
                "duration_min": segment["duration_min"],
                "polyline": segment.get("polyline", "")
            })

            total_distance += segment["distance_km"]
            total_duration += segment["duration_min"]

            if segment.get("polyline"):
                all_polylines.append(segment["polyline"])

        return {
            "waypoints": waypoints,
            "segments": segments,
            "summary": {
                "total_distance_km": round(total_distance, 2),
                "total_duration_min": round(total_duration, 1),
                "total_hours": round(total_duration / 60, 1)
            },
            "polylines": all_polylines
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Multi-point route error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/search-location")
async def search_locations(
    keywords: str = Query(..., description="Search keywords"),
    city: str = Query(..., description="City name"),
    category: str = Query(None, description="POI category: hotel, restaurant, shopping, etc.")
) -> dict:
    """Search for locations by keywords.

    Args:
        keywords: Search keywords
        city: City name
        category: Optional POI category filter

    Returns:
        List of matching locations
    """
    try:
        result = await map_service.search_poi(
            keywords=keywords,
            city=city,
            poi_type=category,
            limit=20
        )

        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Location search error: {e}")
        raise HTTPException(status_code=500, detail=str(e))
