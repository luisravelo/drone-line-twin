from pathlib import Path

from dronetwin.catalog import load_config
from dronetwin.paced_line import PacedLine

CONFIG = Path(__file__).resolve().parents[1] / "config"


def test_pull_builds_buffer_and_prints_on_order():
    r = PacedLine(load_config(CONFIG, "growth_6pos")).run()
    ev = r.events
    first_pick = ev[ev.event == "PICK"].t.min()
    buffered = (ev[(ev.event == "PBS_IN") & (ev.t <= first_pick)]).shape[0]
    assert buffered >= 4                                     # buffer built before the first load
    rel = ev[ev.event == "RELEASE"].set_index("serial").t
    pr = ev[ev.event == "PRINT_START"].set_index("serial").t
    assert ((pr - rel.reindex(pr.index)) >= 0).all()           # the customer order triggers the print
    order = ev[ev.event == "PRINT_START"].sort_values("t").serial.tolist()
    assert order == sorted(order, key=lambda s: int(s.split("-")[1]))   # printed in order sequence
