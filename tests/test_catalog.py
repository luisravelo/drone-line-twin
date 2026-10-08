from pathlib import Path

import pytest

from dronetwin.catalog import load_config

CONFIG = Path(__file__).resolve().parents[1] / "config"


@pytest.fixture(scope="module")
def cfg():
    return load_config(CONFIG, "baseline")


def test_twelve_valid_skus(cfg):
    codes = [s.code for s in cfg.skus]
    assert len(codes) == 12 and len(set(codes)) == 12
    assert "A-BLK-TRI" in codes and "B-SLV-BI-LR" in codes
    assert not any(c.startswith("A-") and c.endswith("-LR") for c in codes)


def test_controller_matches_frame_colour(cfg):
    sku = [s for s in cfg.skus if s.code == "B-YEL-BI-STD"][0]
    kit = cfg.kit(sku)
    assert kit["controller"] == "PN-ESC-FC-STACK-YEL"
    assert kit["prop"] == "PN-PROP-5-BI" and kit["battery"] == "PN-BAT-6S" and kit["frame"] == "MODEL_B"


def test_work_content_matches_spec(cfg):
    w = cfg.work_content_mean()
    assert w["ST10"] == pytest.approx(184)
    assert w["ST20"] == pytest.approx(83)
    assert w["ST50"] == pytest.approx(60)
    assert w["ST70"] == pytest.approx(110)
    assert max(w, key=w.get) == "ST10"


def test_assets_and_layout(cfg):
    assert cfg.assets["ST10"][0] == "/World/Mesa/DroneLine/GA/ST10"
    assert cfg.stations[1].xy == (1.2, 0.0)
    assert cfg.stations[-1].inspect is True
    assert sum(1 for a in cfg.assets if a.startswith("SK")) == 10


def test_consolidated_line_loads(cfg):
    c = load_config(CONFIG, "consolidated")
    w = c.work_content_mean()
    assert [s.asset_id for s in c.stations] == ["ST00", "ST10", "ST20", "ST70"]
    assert w["ST10"] == pytest.approx(267) and w["ST20"] == pytest.approx(180)


def test_six_position_line_is_balanced_for_growth():
    c = load_config(CONFIG, "growth_6pos")
    w = c.work_content_mean()
    assert [s.asset_id for s in c.stations] == ["ST00", "ST10", "ST20", "ST30", "ST40", "ST50"]
    assert w == pytest.approx({"ST00": 65, "ST10": 92, "ST20": 92, "ST30": 123, "ST40": 100, "ST50": 110})
    available = c.scenario["takt_s"] - c.scenario["index_s"]
    assert max(w.values()) <= 0.85 * available          # realistic pace: no station above ~85 % of takt
