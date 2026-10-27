"""FX_DESK_DATA_ROOT redirects medallion paths away from the code checkout."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture
def fresh_config_module(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FX_DESK_DATA_ROOT", str(tmp_path))
    sys.modules.pop("scripts.extract.config", None)
    mod = importlib.import_module("scripts.extract.config")
    yield mod
    sys.modules.pop("scripts.extract.config", None)
    importlib.import_module("scripts.extract.config")


def test_project_root_for_data_honors_env(fresh_config_module):
    mod = fresh_config_module
    assert mod.project_root_for_data() == mod.project_root_for_data().resolve()
    assert mod.GOLD_MART_DIR == mod.project_root_for_data() / "data" / "gold" / "mart"
    assert mod.BRONZE_WEEKLY_DIR == mod.project_root_for_data() / "data" / "bronze" / "weekly"


def test_project_root_defaults_to_repo_without_env(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("FX_DESK_DATA_ROOT", raising=False)
    sys.modules.pop("scripts.extract.config", None)
    mod = importlib.import_module("scripts.extract.config")
    assert mod.project_root_for_data() == mod.REPO_ROOT
