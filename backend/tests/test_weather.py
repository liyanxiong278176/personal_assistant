"""Tests for QWeather service and tools."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.services.weather_service import weather_service, QWeatherService
from app.tools.weather_tools import get_weather, get_weather_forecast


class TestQWeatherService:
    """Test QWeatherService class."""

    @pytest.mark.asyncio
    async def test_get_realtime_weather_success(self, mock_city_lookup_response, mock_weather_response):
        """Test successful weather retrieval."""
        # Create fresh service instance for test isolation
        service = QWeatherService()
        try:
            with patch("app.services.weather_service.httpx.AsyncClient") as mock_client_class:
                # Setup mock client
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                # Mock city lookup
                mock_city_resp = AsyncMock()
                mock_city_resp.json = AsyncMock(return_value=mock_city_lookup_response)
                mock_city_resp.raise_for_status = MagicMock()

                # Mock weather response
                mock_weather_resp = AsyncMock()
                mock_weather_resp.json = AsyncMock(return_value=mock_weather_response)
                mock_weather_resp.raise_for_status = MagicMock()

                mock_client.get.side_effect = [mock_city_resp, mock_weather_resp]

                result = await service.get_realtime_weather("北京")

                assert result["city"] == "北京"
                assert result["temp"] == "25"
                assert result["condition"] == "晴"
                assert result["humidity"] == "65"
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_get_weather_forecast_success(self, mock_city_lookup_response):
        """Test successful forecast retrieval."""
        mock_forecast_response = {
            "code": "200",
            "daily": [
                {
                    "fxDate": "2026-03-30",
                    "tempMax": "28",
                    "tempMin": "18",
                    "textDay": "晴",
                    "textNight": "多云",
                    "precip": "0.0",
                    "windDirDay": "东南风",
                    "windScaleDay": "3"
                },
                {
                    "fxDate": "2026-03-31",
                    "tempMax": "26",
                    "tempMin": "17",
                    "textDay": "多云",
                    "textNight": "阴",
                    "precip": "1.2",
                    "windDirDay": "东风",
                    "windScaleDay": "2"
                },
                {
                    "fxDate": "2026-04-01",
                    "tempMax": "24",
                    "tempMin": "16",
                    "textDay": "阴",
                    "textNight": "小雨",
                    "precip": "5.0",
                    "windDirDay": "东北风",
                    "windScaleDay": "4"
                }
            ]
        }

        service = QWeatherService()
        try:
            with patch("app.services.weather_service.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                mock_city_resp = AsyncMock()
                mock_city_resp.json = AsyncMock(return_value=mock_city_lookup_response)
                mock_city_resp.raise_for_status = MagicMock()

                mock_forecast_resp = AsyncMock()
                mock_forecast_resp.json = AsyncMock(return_value=mock_forecast_response)
                mock_forecast_resp.raise_for_status = MagicMock()

                mock_client.get.side_effect = [mock_city_resp, mock_forecast_resp]

                result = await service.get_weather_forecast("北京", days=3)

                assert result["city"] == "北京"
                assert result["days"] == 3
                assert len(result["forecasts"]) == 3
                assert result["forecasts"][0]["temp_max"] == "28"
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_city_not_found(self):
        """Test handling of non-existent city."""
        mock_response = {
            "code": "404",
            "location": []
        }

        service = QWeatherService()
        try:
            with patch("app.services.weather_service.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                mock_resp = AsyncMock()
                mock_resp.json = AsyncMock(return_value=mock_response)
                mock_resp.raise_for_status = MagicMock()

                mock_client.get.return_value = mock_resp

                result = await service.get_realtime_weather("不存在的城市")

                assert "error" in result
                assert "not found" in result["error"].lower()
        finally:
            await service.close()

    @pytest.mark.asyncio
    async def test_cache_functionality(self, mock_city_lookup_response, mock_weather_response):
        """Test that caching works and prevents duplicate API calls."""
        service = QWeatherService()
        try:
            with patch("app.services.weather_service.httpx.AsyncClient") as mock_client_class:
                mock_client = AsyncMock()
                mock_client_class.return_value = mock_client

                mock_city_resp = AsyncMock()
                mock_city_resp.json = AsyncMock(return_value=mock_city_lookup_response)
                mock_city_resp.raise_for_status = MagicMock()

                mock_weather_resp = AsyncMock()
                mock_weather_resp.json = AsyncMock(return_value=mock_weather_response)
                mock_weather_resp.raise_for_status = MagicMock()

                # First call: hits API
                mock_client.get.side_effect = [mock_city_resp, mock_weather_resp]
                result1 = await service.get_realtime_weather("北京")

                # Second call: should hit cache
                result2 = await service.get_realtime_weather("北京")

                assert result1 == result2
                # Only 2 calls (city + weather), not 4 more for second request
                assert mock_client.get.call_count == 2
        finally:
            await service.close()


class TestWeatherTools:
    """Test LangChain weather tools."""

    @pytest.mark.asyncio
    async def test_get_weather_tool(self, mock_city_lookup_response, mock_weather_response):
        """Test get_weather LangChain tool."""
        # Mock the service return value (already transformed from API response)
        service_return_value = {
            "city": "北京",
            "location_id": "101010100",
            "temp": "25",
            "feels_like": "26",
            "condition": "晴",
            "wind_dir": "东南风",
            "wind_scale": "3",
            "humidity": "65",
            "precip": "0.0",
            "obs_time": "2026-03-30T12:00+08:00"
        }

        with patch("app.tools.weather_tools.weather_service") as mock_service:
            mock_service.get_realtime_weather = AsyncMock(return_value=service_return_value)

            # Use ainvoke with dict input for LangChain tools
            result = await get_weather.ainvoke({"city": "北京"})

            assert "北京" in result
            assert "25" in result  # Temperature
            assert "晴" in result  # Weather condition

    @pytest.mark.asyncio
    async def test_get_weather_forecast_tool(self, mock_city_lookup_response):
        """Test get_weather_forecast LangChain tool."""
        mock_forecast_response = {
            "city": "北京",
            "location_id": "101010100",
            "days": 3,
            "forecasts": [
                {
                    "date": "2026-03-30",
                    "temp_max": "28",
                    "temp_min": "18",
                    "condition_day": "晴",
                    "condition_night": "多云",
                    "precip": "0.0",
                    "wind_dir_day": "东南风",
                    "wind_scale_day": "3"
                }
            ]
        }

        with patch("app.tools.weather_tools.weather_service") as mock_service:
            mock_service.get_weather_forecast = AsyncMock(return_value=mock_forecast_response)

            # Use ainvoke with dict input for LangChain tools
            result = await get_weather_forecast.ainvoke({"city": "北京", "days": 3})

            assert "北京" in result
            assert "forecast" in result.lower() or "预报" in result
