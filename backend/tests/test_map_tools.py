"""Tests for 高德地图 service and tools."""

import os
import pytest
from unittest.mock import AsyncMock, Mock, patch

from app.services.map_service import map_service
from app.tools.map_tools import search_attraction, search_poi, get_location_coords, plan_route


@pytest.fixture(autouse=True)
def mock_amap_api_key(monkeypatch):
    """Set a mock AMAP_API_KEY for all tests."""
    monkeypatch.setenv("AMAP_API_KEY", "test_api_key")
    yield


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear the map service cache before each test."""
    map_service._cache.clear()
    yield


@pytest.fixture
def mock_poi_response():
    """Mock 高德地图 POI search response."""
    return {
        "status": "1",
        "pois": [
            {
                "id": "B000A7BD6C",
                "name": "故宫博物院",
                "address": "北京市东城区景山前街4号",
                "location": "116.397128,39.917545",
                "tel": "010-85007421",
                "type": "风景名胜;风景名胜;博物馆",
                "business_ext": {
                    "rating": "4.8",
                    "cost": "60"
                }
            },
            {
                "id": "B000A7BD6D",
                "name": "天坛公园",
                "address": "北京市东城区天坛东里甲1号",
                "location": "116.410874,39.882692",
                "tel": "010-67028866",
                "type": "风景名胜;风景名胜;公园"
            }
        ]
    }


@pytest.fixture
def mock_geocode_response():
    """Mock 高德地图 geocode response."""
    return {
        "status": "1",
        "geocodes": [
            {
                "formatted_address": "北京市东城区景山前街4号",
                "location": "116.397128,39.917545",
                "level": "景点",
                "city": "北京市",
                "province": "北京市"
            }
        ]
    }


@pytest.fixture
def mock_route_response():
    """Mock 高德地图 route planning response."""
    return {
        "status": "1",
        "route": {
            "paths": [
                {
                    "distance": "15234",  # meters
                    "duration": "2345",   # seconds
                    "tolls": "0",
                    "polyline": "encoded_polyline_here",
                    "steps": [
                        {
                            "instruction": "向东行驶，进入景山前街",
                            "distance": "500",
                            "duration": "60",
                            "action": "左转",
                            "road": "景山前街"
                        }
                    ]
                }
            ]
        }
    }


class TestAmapService:
    """Test AmapService class."""

    @pytest.mark.asyncio
    async def test_search_poi_success(self, mock_poi_response):
        """Test successful POI search."""
        with patch("app.services.map_service.AMAP_API_KEY", "test_key"):
            with patch("app.services.map_service.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                # Create a mock response with sync json() method
                mock_resp = Mock()
                mock_resp.json = Mock(return_value=mock_poi_response)
                mock_resp.raise_for_status = Mock()

                mock_client.get = AsyncMock(return_value=mock_resp)

                result = await map_service.search_poi("故宫", "北京")

                assert result["count"] == 2
                assert result["results"][0]["name"] == "故宫博物院"
                assert result["results"][0]["location"]["lng"] == "116.397128"

    @pytest.mark.asyncio
    async def test_geocode_success(self, mock_geocode_response):
        """Test successful geocoding."""
        with patch("app.services.map_service.AMAP_API_KEY", "test_key"):
            with patch("app.services.map_service.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                mock_resp = Mock()
                mock_resp.json = Mock(return_value=mock_geocode_response)
                mock_resp.raise_for_status = Mock()

                mock_client.get = AsyncMock(return_value=mock_resp)

                result = await map_service.geocode("故宫博物院", "北京")

                assert result["formatted_address"] == "北京市东城区景山前街4号"
                assert result["location"]["lng"] == "116.397128"
                assert result["location"]["lat"] == "39.917545"

    @pytest.mark.asyncio
    async def test_plan_driving_route_success(self, mock_geocode_response, mock_route_response):
        """Test successful route planning."""
        with patch("app.services.map_service.AMAP_API_KEY", "test_key"):
            with patch("app.services.map_service.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                # Setup mock responses - route planning doesn't use geocode, just takes coords
                mock_route_resp = Mock()
                mock_route_resp.json = Mock(return_value=mock_route_response)
                mock_route_resp.raise_for_status = Mock()

                mock_client.get = AsyncMock(return_value=mock_route_resp)

                origin = (116.397128, 39.917545)
                destination = (116.410874, 39.882692)
                result = await map_service.plan_driving_route(origin, destination)

                assert "distance_km" in result
                assert result["distance_km"] == 15.23
                assert result["duration_min"] == 39.1  # 2345/60 = 39.0833, rounds to 39.1
                assert result["tolls"] == 0

    @pytest.mark.asyncio
    async def test_cache_functionality(self, mock_poi_response):
        """Test that caching works for POI search."""
        with patch("app.services.map_service.AMAP_API_KEY", "test_key"):
            with patch("app.services.map_service.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                mock_resp = Mock()
                mock_resp.json = Mock(return_value=mock_poi_response)
                mock_resp.raise_for_status = Mock()

                mock_client.get = AsyncMock(return_value=mock_resp)

                # First call: hits API
                result1 = await map_service.search_poi("故宫", "北京")

                # Second call: should hit cache
                result2 = await map_service.search_poi("故宫", "北京")

                assert result1 == result2
                # Only 1 call (not 2) due to cache
                assert mock_client.get.call_count == 1


class TestMapTools:
    """Test LangChain map tools."""

    @pytest.mark.asyncio
    async def test_search_attraction_tool(self, mock_poi_response):
        """Test search_attraction LangChain tool."""
        with patch("app.services.map_service.AMAP_API_KEY", "test_key"):
            with patch("app.services.map_service.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                mock_resp = Mock()
                mock_resp.json = Mock(return_value=mock_poi_response)
                mock_resp.raise_for_status = Mock()

                mock_client.get = AsyncMock(return_value=mock_resp)

                # Use invoke() instead of deprecated __call__
                result = await search_attraction.ainvoke({"city": "北京", "attraction_type": "景点", "keywords": ""})

                assert "北京" in result
                assert "故宫博物院" in result

    @pytest.mark.asyncio
    async def test_plan_route_tool(self, mock_geocode_response, mock_route_response):
        """Test plan_route LangChain tool."""
        with patch("app.services.map_service.AMAP_API_KEY", "test_key"):
            with patch("app.services.map_service.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                mock_geo_resp = Mock()
                mock_geo_resp.json = Mock(return_value=mock_geocode_response)
                mock_geo_resp.raise_for_status = Mock()

                mock_route_resp = Mock()
                mock_route_resp.json = Mock(return_value=mock_route_response)
                mock_route_resp.raise_for_status = Mock()

                mock_client.get = AsyncMock(side_effect=[
                    mock_geo_resp,
                    mock_geo_resp,
                    mock_route_resp
                ])

                # Use invoke() instead of deprecated __call__
                result = await plan_route.ainvoke({"origin": "故宫", "destination": "天坛", "city": "北京"})

                assert "公里" in result
                assert "分钟" in result
