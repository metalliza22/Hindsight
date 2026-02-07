"""Cache management for Hindsight analysis results."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class CacheManager:
    """Simple file-based cache for analysis results."""

    def __init__(self, cache_dir: Path, ttl: int = 3600, max_size_mb: int = 100):
        self.cache_dir = cache_dir
        self.ttl = ttl
        self.max_size_mb = max_size_mb
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        for subdir in ("git_analysis", "intent_extraction", "ai_responses"):
            (self.cache_dir / subdir).mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _make_key(data: str) -> str:
        return hashlib.sha256(data.encode()).hexdigest()[:32]

    def get(self, cache_type: str, key: str) -> Optional[Dict[str, Any]]:
        """Retrieve a cached value if it exists and hasn't expired."""
        path = self.cache_dir / cache_type / f"{self._make_key(key)}.json"
        if not path.exists():
            return None
        try:
            with open(path) as f:
                entry = json.load(f)
            if time.time() - entry.get("timestamp", 0) > self.ttl:
                path.unlink(missing_ok=True)
                return None
            return entry.get("data")
        except (json.JSONDecodeError, OSError) as e:
            logger.debug("Cache read error for %s/%s: %s", cache_type, key, e)
            return None

    def set(self, cache_type: str, key: str, data: Any) -> None:
        """Store a value in the cache."""
        path = self.cache_dir / cache_type / f"{self._make_key(key)}.json"
        try:
            entry = {"timestamp": time.time(), "data": data}
            with open(path, "w") as f:
                json.dump(entry, f)
        except (OSError, TypeError) as e:
            logger.debug("Cache write error for %s/%s: %s", cache_type, key, e)

    def invalidate(self, cache_type: str, key: str) -> None:
        """Remove a specific cache entry."""
        path = self.cache_dir / cache_type / f"{self._make_key(key)}.json"
        path.unlink(missing_ok=True)

    def clear(self, cache_type: Optional[str] = None) -> int:
        """Clear cache entries. Returns number of entries removed."""
        count = 0
        if cache_type:
            target = self.cache_dir / cache_type
            if target.exists():
                for f in target.glob("*.json"):
                    f.unlink()
                    count += 1
        else:
            for subdir in self.cache_dir.iterdir():
                if subdir.is_dir():
                    for f in subdir.glob("*.json"):
                        f.unlink()
                        count += 1
        return count

    def cleanup_expired(self) -> int:
        """Remove all expired cache entries. Returns number removed."""
        count = 0
        now = time.time()
        for subdir in self.cache_dir.iterdir():
            if not subdir.is_dir():
                continue
            for f in subdir.glob("*.json"):
                try:
                    with open(f) as fh:
                        entry = json.load(fh)
                    if now - entry.get("timestamp", 0) > self.ttl:
                        f.unlink()
                        count += 1
                except (json.JSONDecodeError, OSError):
                    f.unlink(missing_ok=True)
                    count += 1
        return count
