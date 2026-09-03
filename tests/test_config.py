from pathlib import Path

import pytest

from pipeline.config import Config, ConfigError


def test_load_reads_yaml(tmp_path):
    (tmp_path / "config.yaml").write_text("llm:\n  model: m\n", encoding="utf-8")
    config = Config.load(tmp_path)
    assert config.data["llm"]["model"] == "m"


def test_load_missing_config_raises(tmp_path):
    with pytest.raises(ConfigError):
        Config.load(tmp_path)


def test_env_missing_raises(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("x: 1", encoding="utf-8")
    monkeypatch.delenv("NOPE_KEY", raising=False)
    with pytest.raises(ConfigError):
        Config.load(tmp_path).env("NOPE_KEY")
