import numpy as np
import pandas as pd

from dronetwin.paced_line import PacedLine


def test_deterministic(baseline_cfg, baseline_result):
    pd.testing.assert_frame_equal(baseline_result.events, PacedLine(baseline_cfg).run().events)


def test_cycle_duration_is_index_plus_max_of_takt_and_work(baseline_result):
    sc = baseline_result.cfg.scenario
    cy = baseline_result.cycles.dropna(subset=["end"])
    work = cy[[c for c in cy.columns if c.startswith("work_")]].max(axis=1)
    expected = sc["index_s"] + cy.pbs_starved_s + np.maximum(sc["takt_s"] - sc["index_s"], work)
    assert np.allclose(cy.end - cy.start, expected, atol=1e-6)


def test_line_stops_are_attributed(baseline_result):
    cy = baseline_result.cycles
    stopped = cy[cy.stop_s > 0]
    assert stopped.stop_station.notna().all()
    ev = baseline_result.events
    assert np.isclose(ev[ev.event == "LINE_RESUME"].value.sum(), stopped.stop_s.sum())


def test_shipped_units_have_matching_controller(baseline_result):
    for u in baseline_result.units:
        if u.shipped is not None:
            assert u.kit["controller"].endswith("-" + u.sku.colour)


def test_colour_errors_are_caught_at_inspection(baseline_result):
    ev = baseline_result.events
    noks = set(ev.serial[ev.event == "INSPECT_NOK"])
    repaired = set(ev.serial[ev.event == "REPAIR"])
    unfinished = {u.serial for u in baseline_result.units if u.shipped is None}
    assert noks <= repaired | unfinished


def test_only_valid_skus_released(baseline_result):
    ev = baseline_result.events
    valid = {s.code for s in baseline_result.cfg.skus}
    assert set(ev.sku[ev.event == "RELEASE"]) <= valid


def test_demand_met_and_consolidation_holds_takt(baseline_result, consolidated_result):
    def shipped(r):
        ev = r.events
        return int(((ev.event == "SHIP") & (ev.t >= r.t0)).sum())
    assert 75 <= shipped(baseline_result) <= 80          # 80 jobs/day demand at 360 s takt
    assert shipped(consolidated_result) >= 0.9 * shipped(baseline_result)
