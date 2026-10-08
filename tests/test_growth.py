from pathlib import Path

from dronetwin.catalog import load_config
from dronetwin.metrics import build_report
from dronetwin.paced_line import PacedLine

CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_growth_needs_the_rebalanced_line():
    old = build_report(PacedLine(load_config(CONFIG, "growth_8pos")).run()).summary
    new = build_report(PacedLine(load_config(CONFIG, "growth_6pos")).run()).summary
    assert old["bottleneck"] == "ST10" and old["takt_attainment"] < 0.1   # 184 s > 154 s every cycle
    assert new["shipped"] > old["shipped"]
    assert new["shipped"] >= 0.95 * 180
    assert new["takt_attainment"] >= 0.75 and new["line_stop_s"] < 1800   # realistic CV: frequent short stops


def test_takt_load_vs_utilization():
    s = build_report(PacedLine(load_config(CONFIG, "growth_8pos")).run()).summary
    assert s["takt_load"]["ST10"] > 1.15            # ST10 cannot make takt
    assert all(0 <= u <= 1.0 + 1e-9 for u in s["utilization"].values())
    assert s["utilization"]["ST10"] > 0.9           # the true bottleneck is almost never idle
