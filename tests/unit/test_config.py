"""Unit tests for configuration management."""

import json
import os

import pytest

from hindsight.config import Config, get_api_key, ApiConfig, AnalysisConfig


class TestConfigDefaults:
    def test_default_values(self):
        config = Config()
        assert config.api.provider == "anthropic"
        assert config.api.model == "claude-sonnet-4-20250514"
        assert config.api.timeout == 30
        assert config.api.max_retries == 3
        assert config.analysis.max_commits == 50
        assert config.analysis.max_file_size == 1_048_576
        assert config.output.color is True
        assert config.cache.enabled is True
        assert config.cache.ttl == 3600


class TestConfigValidation:
    def test_valid_config(self):
        config = Config()
        issues = config.validate()
        assert issues == []

    def test_invalid_timeout(self):
        config = Config()
        config.api.timeout = 0
        issues = config.validate()
        assert any("timeout" in i.lower() for i in issues)

    def test_invalid_max_commits(self):
        config = Config()
        config.analysis.max_commits = 0
        issues = config.validate()
        assert any("max_commits" in i.lower() for i in issues)

    def test_invalid_max_retries(self):
        config = Config()
        config.api.max_retries = -1
        issues = config.validate()
        assert any("max_retries" in i.lower() for i in issues)


class TestConfigSaveLoad:
    def test_save_and_load(self, tmp_path):
        config = Config()
        config.api.model = "test-model"
        config.analysis.max_commits = 25
        config_path = tmp_path / "config.json"
        config.save(config_path)
        assert config_path.exists()

    def test_save_creates_directory(self, tmp_path):
        config = Config()
        config_path = tmp_path / "subdir" / "config.json"
        config.save(config_path)
        assert config_path.exists()

    def test_load_nonexistent_file(self, tmp_path):
        config = Config.load(tmp_path / "nonexistent.yaml")
        # Should return defaults
        assert config.api.provider == "anthropic"


class TestConfigFromDict:
    def test_partial_dict(self):
        data = {"api": {"model": "custom-model"}}
        config = Config._from_dict(data)
        assert config.api.model == "custom-model"
        assert config.api.provider == "anthropic"  # default

    def test_empty_dict(self):
        config = Config._from_dict({})
        assert config.api.provider == "anthropic"

    def test_full_dict(self):
        data = {
            "api": {"provider": "test", "model": "m", "timeout": 10, "max_retries": 1},
            "analysis": {"max_commits": 20, "max_file_size": 500, "excluded_patterns": ["*.txt"]},
            "output": {"format": "json", "color": False, "verbose": True},
            "cache": {"enabled": False, "ttl": 100, "max_size": 10},
        }
        config = Config._from_dict(data)
        assert config.api.provider == "test"
        assert config.analysis.max_commits == 20
        assert config.output.verbose is True
        assert config.cache.enabled is False


class TestGetApiKey:
    def test_from_hindsight_env(self, monkeypatch):
        monkeypatch.setenv("HINDSIGHT_API_KEY", "hkey")
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert get_api_key() == "hkey"

    def test_from_anthropic_env(self, monkeypatch):
        monkeypatch.delenv("HINDSIGHT_API_KEY", raising=False)
        monkeypatch.setenv("ANTHROPIC_API_KEY", "akey")
        assert get_api_key() == "akey"

    def test_hindsight_takes_priority(self, monkeypatch):
        monkeypatch.setenv("HINDSIGHT_API_KEY", "hkey")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "akey")
        assert get_api_key() == "hkey"

    def test_no_key(self, monkeypatch):
        monkeypatch.delenv("HINDSIGHT_API_KEY", raising=False)
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        assert get_api_key() is None
