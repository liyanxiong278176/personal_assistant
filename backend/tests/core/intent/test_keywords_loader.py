"""Tests for KeywordsLoader hot-reload functionality."""

import pytest
import tempfile
import yaml
from pathlib import Path

from app.core.intent.keywords_loader import KeywordsLoader


class TestKeywordsLoaderBasic:
    """Test basic KeywordsLoader functionality."""

    def test_loader_initialization(self):
        """Test loader initializes with default path."""
        loader = KeywordsLoader()
        assert loader.config_path is not None
        assert loader.config_path.name == "keywords.yaml"

    def test_loader_get_keywords(self):
        """Test getting keywords for an intent."""
        loader = KeywordsLoader()
        keywords = loader.get_keywords("itinerary")

        # Should have positive keywords
        positive = keywords.get("positive", {})
        assert "规划" in positive
        assert positive["规划"] > 0

    def test_loader_get_patterns(self):
        """Test getting patterns for an intent."""
        loader = KeywordsLoader()
        patterns = loader.get_patterns("itinerary")

        assert isinstance(patterns, list)
        assert len(patterns) > 0

    def test_loader_get_all_keywords(self):
        """Test getting all keywords."""
        loader = KeywordsLoader()
        all_keywords = loader.get_all_keywords()

        # Should have 8 intent types
        assert len(all_keywords) == 8
        assert "itinerary" in all_keywords
        assert "query" in all_keywords
        assert "chat" in all_keywords

    def test_loader_get_all_patterns(self):
        """Test getting all patterns."""
        loader = KeywordsLoader()
        all_patterns = loader.get_all_patterns()

        assert isinstance(all_patterns, dict)
        assert len(all_patterns) > 0


class TestKeywordsLoaderExclusion:
    """Test negative keywords (exclusion rules) functionality."""

    def test_get_negative_keywords(self):
        """Test getting negative keywords for query intent."""
        loader = KeywordsLoader()
        negative = loader.get_negative_keywords("query")

        # Query intent should have exclusion rules for "真好", "去玩"
        assert len(negative) > 0
        assert "真好" in negative or "去玩" in negative

    def test_negative_keywords_are_negative_values(self):
        """Test that negative keywords have negative weights."""
        loader = KeywordsLoader()
        negative = loader.get_negative_keywords("query")

        for keyword, weight in negative.items():
            assert weight < 0, f"Negative keyword '{keyword}' should have negative weight"

    def test_get_positive_keywords(self):
        """Test getting positive keywords."""
        loader = KeywordsLoader()
        positive = loader.get_positive_keywords("itinerary")

        assert len(positive) > 0
        for keyword, weight in positive.items():
            assert weight > 0, f"Positive keyword '{keyword}' should have positive weight"


class TestKeywordsLoaderHotReload:
    """Test hot-reload functionality."""

    def test_hot_reload_with_file_change(self):
        """Test that loader detects file changes."""
        # Create a temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            initial_config = {
                "keywords": {
                    "test_intent": {"positive": {"测试": 0.5}}
                },
                "patterns": {}
            }
            yaml.dump(initial_config, f)
            temp_path = f.name

        loader = KeywordsLoader(config_path=temp_path)

        # Initial load
        keywords = loader.get_keywords("test_intent")
        assert "测试" in keywords.get("positive", {})

        # Modify file
        with open(temp_path, "w") as f:
            updated_config = {
                "keywords": {
                    "test_intent": {"positive": {"新测试": 0.6}}
                },
                "patterns": {}
            }
            yaml.dump(updated_config, f)

        # Force reload
        loader.force_reload()

        # Check updated content
        keywords = loader.get_keywords("test_intent")
        assert "新测试" in keywords.get("positive", {})

        # Cleanup
        Path(temp_path).unlink()

    def test_force_reload(self):
        """Test explicit force_reload method."""
        loader = KeywordsLoader()
        stats = loader.force_reload()

        assert stats["loaded"] is True
        assert stats["keywords_count"] == 8

    def test_clear_cache(self):
        """Test clearing cache."""
        loader = KeywordsLoader()
        loader.clear_cache()

        assert loader._loaded is False
        assert len(loader._keywords_cache) == 0

        # After clear, next get should reload
        keywords = loader.get_keywords("itinerary")
        assert len(keywords) > 0


class TestKeywordsLoaderCacheStats:
    """Test cache statistics."""

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        loader = KeywordsLoader()
        stats = loader.get_cache_stats()

        assert "config_path" in stats
        assert "keywords_count" in stats
        assert "patterns_count" in stats
        assert "loaded" in stats


class TestKeywordsLoaderFallback:
    """Test fallback behavior."""

    def test_fallback_on_missing_file(self):
        """Test fallback when config file doesn't exist."""
        loader = KeywordsLoader(config_path="/nonexistent/path/keywords.yaml")

        # Should still load defaults
        keywords = loader.get_keywords("itinerary")
        assert len(keywords) > 0

    def test_fallback_on_yaml_error(self):
        """Test fallback on malformed YAML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_path = f.name

        loader = KeywordsLoader(config_path=temp_path)

        # Should fallback to defaults
        keywords = loader.get_keywords("itinerary")
        assert len(keywords) > 0

        Path(temp_path).unlink()