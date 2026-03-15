"""Tests for configuration loading and merging."""

import tempfile
from pathlib import Path

import pytest

from nba_watchability import config as config_module
from nba_watchability.exceptions import ConfigError


class TestDefaultConfig:
    def test_loads_without_error(self):
        cfg = config_module.load()
        assert cfg is not None

    def test_default_weights(self):
        cfg = config_module.load()
        assert cfg.weights.closeness == 30.0
        assert cfg.weights.lead_changes == 25.0
        assert cfg.weights.anomalies == 20.0
        assert cfg.weights.team_quality == 15.0
        assert cfg.weights.clutch == 20.0
        assert not hasattr(cfg.weights, "overtime")

    def test_default_breakpoints_sorted(self):
        cfg = config_module.load()
        bps = cfg.scoring.closeness.breakpoints
        assert len(bps) > 0
        for i in range(len(bps) - 1):
            assert bps[i].margin <= bps[i + 1].margin

    def test_elite_threshold_above_floor(self):
        cfg = config_module.load()
        assert cfg.scoring.team_quality.elite_threshold > cfg.scoring.team_quality.floor_threshold

    def test_default_http_config(self):
        cfg = config_module.load()
        assert cfg.http.request_delay == 2.0
        assert cfg.http.timeout == 15


class TestUserOverride:
    def test_override_weight(self):
        toml = "[weights]\ncloseness = 99\n"
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write(toml)
            path = f.name
        cfg = config_module.load(path)
        assert cfg.weights.closeness == 99.0
        # Other weights should remain at defaults
        assert cfg.weights.lead_changes == 25.0

    def test_override_http_delay(self):
        toml = "[http]\nrequest_delay = 5.0\n"
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write(toml)
            path = f.name
        cfg = config_module.load(path)
        assert cfg.http.request_delay == 5.0

    def test_nonexistent_file_raises_config_error(self):
        with pytest.raises(ConfigError) as exc_info:
            config_module.load("/nonexistent/path/config.toml")
        assert "not found" in str(exc_info.value)

    def test_invalid_toml_raises_config_error(self):
        with tempfile.NamedTemporaryFile(suffix=".toml", mode="w", delete=False) as f:
            f.write("this is not valid toml ][[[")
            path = f.name
        with pytest.raises(ConfigError):
            config_module.load(path)
