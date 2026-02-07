"""Unit tests for cache management."""

import json
import time

import pytest

from hindsight.cache import CacheManager


@pytest.fixture
def cache(tmp_path):
    return CacheManager(cache_dir=tmp_path / "cache", ttl=60, max_size_mb=10)


class TestCacheOperations:
    def test_set_and_get(self, cache):
        cache.set("git_analysis", "key1", {"result": "value"})
        result = cache.get("git_analysis", "key1")
        assert result == {"result": "value"}

    def test_get_nonexistent(self, cache):
        assert cache.get("git_analysis", "missing") is None

    def test_invalidate(self, cache):
        cache.set("git_analysis", "key1", {"x": 1})
        cache.invalidate("git_analysis", "key1")
        assert cache.get("git_analysis", "key1") is None

    def test_expired_entry(self, tmp_path):
        cache = CacheManager(cache_dir=tmp_path / "cache", ttl=0)
        cache.set("git_analysis", "key1", {"x": 1})
        time.sleep(0.1)
        assert cache.get("git_analysis", "key1") is None

    def test_clear_specific_type(self, cache):
        cache.set("git_analysis", "k1", {"a": 1})
        cache.set("ai_responses", "k2", {"b": 2})
        count = cache.clear("git_analysis")
        assert count == 1
        assert cache.get("git_analysis", "k1") is None
        assert cache.get("ai_responses", "k2") == {"b": 2}

    def test_clear_all(self, cache):
        cache.set("git_analysis", "k1", {"a": 1})
        cache.set("ai_responses", "k2", {"b": 2})
        count = cache.clear()
        assert count == 2

    def test_cleanup_expired(self, tmp_path):
        cache = CacheManager(cache_dir=tmp_path / "cache", ttl=0)
        cache.set("git_analysis", "k1", {"a": 1})
        cache.set("git_analysis", "k2", {"b": 2})
        time.sleep(0.1)
        count = cache.cleanup_expired()
        assert count == 2

    def test_different_keys_dont_collide(self, cache):
        cache.set("git_analysis", "key1", {"a": 1})
        cache.set("git_analysis", "key2", {"b": 2})
        assert cache.get("git_analysis", "key1") == {"a": 1}
        assert cache.get("git_analysis", "key2") == {"b": 2}
