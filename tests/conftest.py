from pathlib import Path

import pytest

from dronetwin.catalog import load_config
from dronetwin.paced_line import PacedLine

CONFIG = Path(__file__).resolve().parents[1] / "config"


@pytest.fixture(scope="session")
def baseline_cfg():
    return load_config(CONFIG, "baseline")


@pytest.fixture(scope="session")
def baseline_result(baseline_cfg):
    return PacedLine(baseline_cfg).run()


@pytest.fixture(scope="session")
def consolidated_result():
    return PacedLine(load_config(CONFIG, "consolidated")).run()
