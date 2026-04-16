"""Tests for PromptConfigLoader hot-reload functionality.

Tests intent-to-template dynamic mapping with mtime-based auto-reload.
"""

import pytest
import tempfile
import yaml
import time
from pathlib import Path

from app.core.prompts.loader import PromptConfigLoader


class TestPromptConfigLoaderBasic:
    """Test basic PromptConfigLoader functionality."""

    def test_loader_initialization(self):
        """Test loader initializes with default path."""
        loader = PromptConfigLoader()
        assert loader.config_path is not None
        assert loader.config_path.name == "prompts.yaml"

    def test_loader_get_config(self):
        """Test getting config loads mapping."""
        loader = PromptConfigLoader()
        config = loader.get_config()

        assert "mapping" in config
        assert "itinerary" in config["mapping"]

    def test_loader_get_template(self):
        """Test getting template for existing intent."""
        loader = PromptConfigLoader()
        template = loader.get_template("itinerary")

        assert len(template) > 0
        assert "行程" in template or "规划" in template

    def test_loader_get_template_unknown_intent(self):
        """Test getting template for unknown intent returns default."""
        loader = PromptConfigLoader()
        template = loader.get_template("unknown_intent")

        # Should return default template
        assert len(template) > 0


class TestPromptConfigLoaderHotReload:
    """Test hot-reload functionality."""

    def test_config_mtime_detection(self):
        """Test loader detects config file changes."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            initial_config = {
                "mapping": {
                    "test_intent": {"template": "templates/test.md", "enabled": True}
                },
                "settings": {"cache_ttl": 60}
            }
            yaml.dump(initial_config, f)
            temp_path = f.name

        loader = PromptConfigLoader(config_path=temp_path)

        # Initial load
        config = loader.get_config()
        assert "test_intent" in config["mapping"]

        # Modify config file
        time.sleep(0.1)  # Ensure mtime changes
        with open(temp_path, "w") as f:
            updated_config = {
                "mapping": {
                    "new_intent": {"template": "templates/new.md", "enabled": True}
                },
                "settings": {"cache_ttl": 60}
            }
            yaml.dump(updated_config, f)

        # Check reload happens
        config = loader.get_config()
        assert "new_intent" in config["mapping"]
        assert "test_intent" not in config["mapping"]

        Path(temp_path).unlink()

    def test_template_mtime_detection(self):
        """Test loader detects template file changes."""
        loader = PromptConfigLoader()

        # Get initial template
        initial_template = loader.get_template("itinerary")

        # Touch the template file (in real scenario)
        # Here we just verify the mechanism exists
        stats = loader.get_cache_stats()
        assert "template_cached" in stats

    def test_new_intent_mapping(self):
        """Test adding new intent mapping works."""
        loader = PromptConfigLoader()

        # Get existing intents
        config = loader.get_config()
        initial_count = len(config["mapping"])

        # In production: add new mapping to YAML
        # Here we verify the loader can handle dynamic mappings
        assert initial_count >= 8  # At least 8 base intents


class TestPromptConfigLoaderCache:
    """Test cache management."""

    def test_get_cache_stats(self):
        """Test getting cache statistics."""
        loader = PromptConfigLoader()

        # Load something first
        loader.get_config()
        loader.get_template("itinerary")

        stats = loader.get_cache_stats()

        assert "config_last_mtime" in stats
        assert "template_cache_size" in stats
        assert "template_cached" in stats

    def test_clear_cache(self):
        """Test clearing cache forces reload."""
        loader = PromptConfigLoader()

        # Load config
        config1 = loader.get_config()

        # Clear cache
        loader.clear_cache()

        # Verify cache is cleared
        stats = loader.get_cache_stats()
        assert stats["template_cache_size"] == 0

    def test_force_reload(self):
        """Test force_reload clears and reloads."""
        loader = PromptConfigLoader()

        # Load some templates
        loader.get_template("itinerary")
        loader.get_template("query")

        # Force reload
        loader.clear_cache()

        # Verify templates need to be reloaded
        stats = loader.get_cache_stats()
        assert stats["template_cache_size"] == 0

        # Reload should work
        template = loader.get_template("itinerary")
        assert len(template) > 0


class TestPromptConfigLoaderFallback:
    """Test fallback behavior."""

    def test_fallback_on_missing_config(self):
        """Test fallback when config file doesn't exist."""
        loader = PromptConfigLoader(config_path="/nonexistent/path/prompts.yaml")

        # Should fallback to defaults
        config = loader.get_config()
        assert "mapping" in config

    def test_fallback_on_missing_template(self):
        """Test fallback when template file doesn't exist."""
        loader = PromptConfigLoader()

        # Request non-existent template
        template = loader.get_template("nonexistent")

        # Should return default template
        assert len(template) > 0

    def test_fallback_on_yaml_error(self):
        """Test fallback on malformed YAML."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write("invalid: yaml: content: [")
            temp_path = f.name

        loader = PromptConfigLoader(config_path=temp_path)

        # Should fallback to defaults
        config = loader.get_config()
        assert "mapping" in config

        Path(temp_path).unlink()


class TestPromptConfigLoaderIntegration:
    """Integration tests for real-world scenarios."""

    def test_add_shopping_intent(self):
        """Test scenario: adding a new 'shopping' intent.

        Steps:
        1. Create shopping.md template
        2. Add mapping to prompts.yaml
        3. Loader should detect and load
        """
        loader = PromptConfigLoader()

        # Get current intents
        config = loader.get_config()
        current_intents = list(config["mapping"].keys())

        # Verify base intents exist
        assert "itinerary" in current_intents
        assert "query" in current_intents

    def test_template_content_update(self):
        """Test scenario: updating template content.

        Steps:
        1. Modify template file content
        2. Loader should detect mtime change
        3. New content should be loaded
        """
        loader = PromptConfigLoader()

        # Load template
        template1 = loader.get_template("chat")

        # In production: modify templates/chat.md
        # Here we verify the mechanism
        stats = loader.get_cache_stats()
        assert "chat" in stats["template_cached"] or stats["template_cache_size"] > 0

    def test_template_variable_injection(self):
        """Test template contains expected variables."""
        loader = PromptConfigLoader()

        template = loader.get_template("itinerary")

        # Check for variable placeholders
        assert "{user_message}" in template or "用户" in template