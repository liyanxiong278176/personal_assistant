"""Tests for PromptConfigLoader."""

import pytest
import yaml
from pathlib import Path
from app.core.prompts.loader import PromptConfigLoader


@pytest.fixture
def temp_config_dir(tmp_path):
    """Create a temporary config directory with test files."""
    config_dir = tmp_path / "prompts"
    config_dir.mkdir()
    templates_dir = config_dir / "templates"
    templates_dir.mkdir()

    # Create default config
    config_file = config_dir / "prompts.yaml"
    config_data = {
        "mapping": {
            "chat": {"template": "templates/chat.md", "enabled": True},
            "hotel": {"template": "templates/hotel.md", "enabled": True},
        },
        "settings": {"watch_interval": 1, "cache_ttl": 60}
    }
    with open(config_file, "w", encoding="utf-8") as f:
        yaml.dump(config_data, f)

    # Create template files
    (templates_dir / "chat.md").write_text("# Chat Template\n\nHello {user_message}", encoding="utf-8")
    (templates_dir / "hotel.md").write_text("# Hotel Template\n\nFind hotels", encoding="utf-8")

    return config_dir


class TestPromptConfigLoader:
    """Test PromptConfigLoader functionality."""

    def test_init_with_path(self, temp_config_dir):
        """Should initialize with given config path."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        assert loader.config_path == config_path

    def test_load_config_successfully(self, temp_config_dir):
        """Should load config from YAML file."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        config = loader.get_config()

        assert "mapping" in config
        assert "chat" in config["mapping"]
        assert config["mapping"]["chat"]["enabled"] is True

    def test_get_template_from_file(self, temp_config_dir):
        """Should load template content from file."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        template = loader.get_template("chat")

        assert "Hello {user_message}" in template

    def test_cache_template_after_first_load(self, temp_config_dir):
        """Should cache template after first load."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        # First load
        template1 = loader.get_template("chat")
        stats = loader.get_cache_stats()

        assert stats["template_cache_size"] == 1
        assert len(stats["template_cached"]) == 1

    def test_return_default_template_when_file_missing(self, temp_config_dir):
        """Should return default template when file is missing."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        template = loader.get_template("nonexistent")

        assert "你是一个 AI 助手" in template

    def test_clear_cache(self, temp_config_dir):
        """Should clear all caches."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        # Load something to populate cache
        loader.get_template("chat")
        loader.clear_cache()

        stats = loader.get_cache_stats()
        assert stats["template_cache_size"] == 0

    def test_hot_reload_on_config_change(self, temp_config_dir):
        """Should reload config when file is modified."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        # Initial load
        config1 = loader.get_config()
        initial_mtime = loader._last_mtime

        # Modify config
        import time
        time.sleep(0.01)  # Ensure different mtime
        with open(config_path, "w") as f:
            yaml.dump({"mapping": {"new": {"enabled": True}}}, f)

        # Should detect change
        assert loader._should_reload_config() is True

    def test_disabled_intent_returns_default(self, temp_config_dir):
        """Should return default template for disabled intents."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        # Modify config to disable hotel
        config_data = {
            "mapping": {
                "hotel": {"template": "templates/hotel.md", "enabled": False}
            }
        }
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        loader.clear_cache()
        template = loader.get_template("hotel")

        # Should return default, not file content
        assert "你是一个酒店推荐专家" in template

    def test_should_reload_template_detection(self, temp_config_dir):
        """Should correctly detect when template needs reload."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        template_path = temp_config_dir / "templates" / "chat.md"

        # First load - should reload
        assert loader._should_reload_template(template_path) is True

        # Load it
        loader._load_template(template_path)

        # Second check - should not reload (same mtime)
        assert loader._should_reload_template(template_path) is False

    def test_get_default_config_fallback(self, temp_config_dir):
        """Should return default config when file is missing."""
        # Point to non-existent file
        loader = PromptConfigLoader(str(temp_config_dir / "nonexistent.yaml"))

        config = loader.get_config()

        # Should have default mapping
        assert "mapping" in config
        assert "itinerary" in config["mapping"]
        assert "chat" in config["mapping"]

    def test_get_default_template_for_all_intents(self, temp_config_dir):
        """Should return default templates for all known intents."""
        loader = PromptConfigLoader(str(temp_config_dir / "prompts.yaml"))

        intents = ["itinerary", "query", "chat", "image", "hotel", "food", "budget", "transport"]

        for intent in intents:
            template = loader._get_default_template(intent)
            assert template, f"No default template for {intent}"
            assert "助手" in template, f"Default template for {intent} missing '助手'"

    def test_cache_stats_includes_last_mtime(self, temp_config_dir):
        """Cache stats should include formatted last modification time."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        # Load config to set mtime
        loader.get_config()

        stats = loader.get_cache_stats()

        assert stats["config_last_mtime"] is not None
        assert "T" in stats["config_last_mtime"]  # ISO format includes T

    def test_template_cached_in_cache_stats(self, temp_config_dir):
        """Template keys should appear in cache stats."""
        config_path = temp_config_dir / "prompts.yaml"
        loader = PromptConfigLoader(str(config_path))

        loader.get_template("chat")
        stats = loader.get_cache_stats()

        assert len(stats["template_cached"]) > 0
        assert any("chat.md" in path for path in stats["template_cached"])
