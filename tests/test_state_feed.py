from pathlib import Path

from dronetwin.catalog import load_config
from dronetwin.export.state_feed import state_feed
from dronetwin.paced_line import PacedLine

CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_state_feed_is_consistent_with_the_event_log():
    r = PacedLine(load_config(CONFIG, "growth_6pos")).run()
    f = state_feed(r)
    assert [s["id"] for s in f["meta"]["stations"]] == [s.asset_id for s in r.cfg.stations]
    assert len(f["meta"]["skillets"]) == r.cfg.skillets
    shipped = [u for u in f["units"].values() if "ship" in u]
    assert len(shipped) == (r.events.event == "SHIP").sum()
    assert all(u["controller"].endswith(u["colour"]) or u.get("defect") for u in f["units"].values() if "controller" in u)
    for keys in f["skillets"].values():                      # keyframes are time-ordered
        assert [k[0] for k in keys] == sorted(k[0] for k in keys)
    assert all(a <= b for a, b, _ in f["line_stops"])
