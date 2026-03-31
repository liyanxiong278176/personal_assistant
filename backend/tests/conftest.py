"""Shared pytest fixtures for testing."""

import os
import pytest

# Set test environment variables
# 只使用高德地图API（天气+地图+POI搜索共用一个key）
os.environ.update({
    "AMAP_API_KEY": "test_amap_key_12345",
    "DASHSCOPE_API_KEY": "test_dashscope_key_12345",
})


@pytest.fixture
def mock_weather_response():
    """Mock 高德天气 API response."""
    return {
        "status": "1",
        "lives": {
            "province": "北京",
            "city": "北京市",
            "adcode": "110000",
            "weather": "晴",
            "temperature": "25",
            "winddirection": "东南",
            "windpower": "3",
            "humidity": "65",
            "reporttime": "2026-03-30 12:00:00"
        },
        "forecasts": [
            {
                "city": "北京市",
                "adcode": "110000",
                "province": "北京",
                "reporttime": "2026-03-30 12:00:00",
                "casts": [
                    {
                        "date": "2026-03-30",
                        "week": "今日",
                        "dayweather": "晴",
                        "nightweather": "晴",
                        "daytemp": "25",
                        "nighttemp": "15",
                        "daywind": "东南",
                        "nightwind": "东南",
                        "daypower": "3",
                        "nightpower": "3"
                    }
                ]
            }
        ]
    }


@pytest.fixture
def mock_city_lookup_response():
    """Mock 高德地图 city lookup response."""
    return {
        "status": "1",
        "info": "OK",
        "infocode": "10000",
        "count": "1",
        "geocodes": [{
            "formatted_address": "北京市",
            "country": "中国",
            "province": "北京",
            "citycode": "010",
            "adcode": "110000"
        }]
    }


@pytest.fixture
def mock_embeddings():
    """Mock embeddings for testing (avoid loading models)."""
    class MockEmbeddings:
        def embed_documents(self, texts):
            # Return deterministic mock embeddings
            return [[0.1] * 384 for _ in texts]

        def embed_query(self, text):
            return [0.1] * 384

    return MockEmbeddings()
