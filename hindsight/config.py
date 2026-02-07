"""Configuration management for Hindsight."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False

logger = logging.getLogger(__name__)

DEFAULT_CONFIG_DIR = Path.home() / ".hindsight"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"

DEFAULT_CONFIG: Dict[str, Any] = {
    "api": {
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "timeout": 30,
        "max_retries": 3,
    },
    "analysis": {
        "max_commits": 50,
        "max_file_size": 1_048_576,
        "excluded_patterns": ["*.pyc", "__pycache__/*", ".git/*"],
    },
    "output": {
        "format": "terminal",
        "color": True,
        "verbose": False,
    },
    "cache": {
        "enabled": True,
        "ttl": 3600,
        "max_size": 100,
    },
}


@dataclass
class ApiConfig:
    provider: str = "anthropic"
    model: str = "claude-sonnet-4-20250514"
    timeout: int = 30
    max_retries: int = 3


@dataclass
class AnalysisConfig:
    max_commits: int = 50
    max_file_size: int = 1_048_576
    excluded_patterns: List[str] = field(
        default_factory=lambda: ["*.pyc", "__pycache__/*", ".git/*"]
    )


@dataclass
class OutputConfig:
    format: str = "terminal"
    color: bool = True
    verbose: bool = False


@dataclass
class CacheConfig:
    enabled: bool = True
    ttl: int = 3600
    max_size: int = 100


@dataclass
class Config:
    api: ApiConfig = field(default_factory=ApiConfig)
    analysis: AnalysisConfig = field(default_factory=AnalysisConfig)
    output: OutputConfig = field(default_factory=OutputConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    config_dir: Path = DEFAULT_CONFIG_DIR

    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> Config:
        """Load configuration from file, env vars, and defaults."""
        config = cls()
        path = config_path or DEFAULT_CONFIG_FILE

        if path.exists() and HAS_YAML:
            try:
                with open(path) as f:
                    data = yaml.safe_load(f) or {}
                config = cls._from_dict(data)
                config.config_dir = path.parent
            except Exception as e:
                logger.warning("Failed to load config from %s: %s", path, e)

        # Environment variable overrides
        api_key = os.environ.get("HINDSIGHT_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if api_key:
            # Key is read at runtime, not stored in config
            pass

        model = os.environ.get("HINDSIGHT_MODEL")
        if model:
            config.api.model = model

        return config

    @classmethod
    def _from_dict(cls, data: Dict[str, Any]) -> Config:
        config = cls()
        if "api" in data:
            api = data["api"]
            config.api = ApiConfig(
                provider=api.get("provider", config.api.provider),
                model=api.get("model", config.api.model),
                timeout=api.get("timeout", config.api.timeout),
                max_retries=api.get("max_retries", config.api.max_retries),
            )
        if "analysis" in data:
            a = data["analysis"]
            config.analysis = AnalysisConfig(
                max_commits=a.get("max_commits", config.analysis.max_commits),
                max_file_size=a.get("max_file_size", config.analysis.max_file_size),
                excluded_patterns=a.get("excluded_patterns", config.analysis.excluded_patterns),
            )
        if "output" in data:
            o = data["output"]
            config.output = OutputConfig(
                format=o.get("format", config.output.format),
                color=o.get("color", config.output.color),
                verbose=o.get("verbose", config.output.verbose),
            )
        if "cache" in data:
            c = data["cache"]
            config.cache = CacheConfig(
                enabled=c.get("enabled", config.cache.enabled),
                ttl=c.get("ttl", config.cache.ttl),
                max_size=c.get("max_size", config.cache.max_size),
            )
        return config

    def save(self, config_path: Optional[Path] = None) -> None:
        """Save current configuration to file."""
        path = config_path or (self.config_dir / "config.yaml")
        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "api": {
                "provider": self.api.provider,
                "model": self.api.model,
                "timeout": self.api.timeout,
                "max_retries": self.api.max_retries,
            },
            "analysis": {
                "max_commits": self.analysis.max_commits,
                "max_file_size": self.analysis.max_file_size,
                "excluded_patterns": self.analysis.excluded_patterns,
            },
            "output": {
                "format": self.output.format,
                "color": self.output.color,
                "verbose": self.output.verbose,
            },
            "cache": {
                "enabled": self.cache.enabled,
                "ttl": self.cache.ttl,
                "max_size": self.cache.max_size,
            },
        }

        if HAS_YAML:
            with open(path, "w") as f:
                yaml.dump(data, f, default_flow_style=False)
        else:
            # Fallback: write as simple key-value format
            import json
            with open(path, "w") as f:
                json.dump(data, f, indent=2)

        # Restrict permissions
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def validate(self) -> List[str]:
        """Validate configuration and return list of issues."""
        issues = []
        if self.api.timeout < 1:
            issues.append("API timeout must be at least 1 second")
        if self.api.max_retries < 0:
            issues.append("max_retries must be non-negative")
        if self.analysis.max_commits < 1:
            issues.append("max_commits must be at least 1")
        if self.analysis.max_file_size < 1:
            issues.append("max_file_size must be at least 1 byte")
        return issues


def get_api_key() -> Optional[str]:
    """Get API key from environment variables."""
    return os.environ.get("HINDSIGHT_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")


def setup_logging(config: Config) -> None:
    """Configure logging based on config."""
    log_dir = config.config_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    level = logging.DEBUG if config.output.verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "hindsight.log"),
            logging.StreamHandler() if config.output.verbose else logging.NullHandler(),
        ],
    )
