"""KPIs for the GA paced line: JPH, takt attainment, line stops, balance, torque NOK, quality, mix."""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class Report:
    summary: dict
    work_mean: dict
    stops: pd.Series
    cycles: pd.DataFrame


def build_report(r) -> Report:
    ev, cy, t0, t1 = r.events, r.cycles, r.t0, r.t1
    sc = r.cfg.scenario
    win = (ev.t >= t0) & (ev.t < t1)
    cw = cy[(cy.end > t0) & (cy.end <= t1)]
    hours = (t1 - t0) / 3600.0
    ids = [s.asset_id for s in r.cfg.stations]
    available = sc["takt_s"] - sc["index_s"]
    ship = ev[win & (ev.event == "SHIP")]
    rel = ev[win & (ev.event == "RELEASE")]
    work = {a: float(cw[f"work_{a}"].mean()) for a in ids}
    elapsed = float((cw.end - cw.start).sum())
    stops = cw[cw.stop_s > 0].groupby("stop_station").stop_s.sum().reindex(ids, fill_value=0.0)
    tq = ev[win & ev.event.isin(["TORQUE_OK", "TORQUE_NOK"])]
    ok = tq[tq.event == "TORQUE_OK"].groupby("asset_id").size()
    nok = tq[tq.event == "TORQUE_NOK"].groupby("asset_id").size()
    summary = {
        "scenario": sc["name"], "seed": sc["seed"], "takt_s": sc["takt_s"], "window_s": [t0, t1],
        "stations": len(ids),
        "shipped": int(len(ship)), "jph": round(len(ship) / hours, 2), "jph_ideal": round(3600.0 / sc["takt_s"], 2),
        "cycles": int(len(cw)),
        "takt_attainment": round(float((cw.stop_s == 0).mean()), 3) if len(cw) else None,
        "line_stop_s": round(float(cw.stop_s.sum()), 1),
        "line_stop_by_station_s": {k: round(float(v), 1) for k, v in stops.items() if v > 0},
        "bottleneck": str(stops.idxmax()) if stops.sum() > 0 else max(work, key=work.get),
        "work_content_mean_s": {k: round(v, 1) for k, v in work.items()},
        # Takt load: planned-capacity check, can exceed 1 when a station cannot make takt.
        "takt_load": {k: round(v / available, 3) for k, v in work.items()},
        # Utilization: busy time / actual elapsed cycle time, capped at 1 by construction (line stops stretch cycles).
        "utilization": {a: round(float(cw[f"work_{a}"].fillna(0).sum() / elapsed), 3) for a in ids} if elapsed > 0 else {},
        "balance_loss": round(1 - sum(work.values()) / (len(ids) * available), 3),
        "torque_nok_rate": {k: round(float(nok.get(k, 0)) / float(ok[k]), 4) for k in ok.index},
        "torque_nok": int(nok.sum()),
        "colour_mismatch_detected": int((win & (ev.event == "INSPECT_NOK")).sum()),
        "repairs": int((win & (ev.event == "REPAIR")).sum()),
        "pbs_starved_s": round(float(cw.pbs_starved_s.sum()), 1),
        "mix_in": {k: int(v) for k, v in rel.sku.value_counts().items()},
        "mix_out": {k: int(v) for k, v in ship.sku.value_counts().items()},
    }
    return Report(summary, work, stops, cw)
