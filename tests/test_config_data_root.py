"""FX_DESK_DATA_ROOT redirects medallion paths away from the code checkout."""

from __future__ import annotations

import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


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


def test_weekly_job_reads_data_root_from_dotenv(tmp_path: Path):
    env_root = tmp_path / "from-dotenv"
    dotenv = tmp_path / ".env"
    dotenv.write_text(f"FX_DESK_DATA_ROOT={env_root}\n")
    env = {k: v for k, v in os.environ.items() if k != "FX_DESK_DATA_ROOT"}
    env["FX_DESK_DOTENV"] = str(dotenv)
    code = (
        "import scripts.run_weekly_abcd; "
        "from scripts.extract.config import GOLD_MART_DIR; print(GOLD_MART_DIR)"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    mart = Path(result.stdout.strip().splitlines()[-1])
    assert mart == env_root.resolve() / "data" / "gold" / "mart"
