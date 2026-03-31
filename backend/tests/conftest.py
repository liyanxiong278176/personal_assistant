"""Shared pytest fixtures for testing."""

import os
import pytest

# Set test environment variables
os.environ.update({
    "QWEATHER_API_KEY": "test_key_12345",
    "AMAP_API_KEY": "test_amap_key_12345",
    "DASHSCOPE_API_KEY": "test_dashscope_key_12345",
})


@pytest.fixture
def mock_weather_response():
    """Mock QWeather API response."""
    return {
        "code": "200",
        "now": {
            "temp": "25",
            "feelsLike": "26",
            "text": "晴",
            "windDir": "东南风",
            "windScale": "3",
            "humidity": "65",
            "precip": "0.0",
            "obsTime": "2026-03-30T12:00+08:00"
        }
    }


@pytest.fixture
def mock_city_lookup_response():
    """Mock QWeather city lookup response."""
    return {
        "code": "200",
        "location": [{
            "id": "101010100",
            "name": "北京",
            "adm2": "北京",
            "adm1": "北京",
            "country": "中国"
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
