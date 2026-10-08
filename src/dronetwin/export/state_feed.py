"""Compact state feed for 3D replay (Blender): skillet keyframes, unit records, station states, line stops.

Times are sim seconds. A skillet MOVE is logged when the index finishes, so the replay animates the move over
the `index_s` seconds before each keyframe. Positions are the sim's logical line metres; the 3D scene maps
station ids to its own layout, so table size does not leak into the sim.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

STATION_EVENTS = {"STATE", "ELEMENT_START", "TORQUE_NOK", "LINE_STOP", "LINE_RESUME", "INSPECT_OK", "INSPECT_NOK"}


def _num(v):
    return None if pd.isna(v) else round(float(v), 3)


def _str(v):
    return None if pd.isna(v) else str(v)


def state_feed(result) -> dict:
    cfg, ev = result.cfg, result.events
    sc = cfg.scenario
    sk_ids = sorted(ev.loc[ev.event == "MOVE", "asset_id"].unique())

    skillets = {s: [] for s in sk_ids}
    for r in ev[ev.event == "MOVE"].itertuples():
        skillets[r.asset_id].append([_num(r.t), _num(r.x), _num(r.y), _str(r.serial)])

    units: dict[str, dict] = {}
    first = {"RELEASE": "release", "PRINT_START": "print", "PAINT_START": "paint", "PBS_IN": "pbs_in",
             "LOAD": "load", "SHIP": "ship", "REPAIR": "repair",
             "TRANSFER": "transfer", "BELT_IN": "belt_in", "PICK": "pick"}
    for r in ev[ev.event.isin(list(first) + ["INSPECT_NOK"])].itertuples():
        if pd.isna(r.serial):
            continue
        u = units.setdefault(r.serial, {"sku": _str(r.sku)})
        if r.event == "RELEASE":
            sku = next(s for s in cfg.skus if s.code == r.sku)
            u.update(model=sku.model, colour=sku.colour, prop=sku.prop, battery=sku.battery, controller=_str(r.pn))
        if r.event == "INSPECT_NOK":
            u["defect"] = "colour_mismatch"
        elif r.event == "PRINT_START" and not pd.isna(r.value):
            u["printer"] = int(r.value)
            u.setdefault("print", _num(r.t))
        else:
            u.setdefault(first[r.event], _num(r.t))

    stations = {s.asset_id: [] for s in cfg.stations}
    for r in ev[ev.event.isin(STATION_EVENTS) & ev.asset_id.isin(list(stations))].itertuples():
        label = r.state if r.event == "STATE" else r.event
        stations[r.asset_id].append([_num(r.t), _str(label), _str(r.serial), _str(r.pn)])

    stops = []
    open_stop: dict[str, float] = {}
    for r in ev[ev.event.isin(["LINE_STOP", "LINE_RESUME"])].itertuples():
        if r.event == "LINE_STOP":
            open_stop.setdefault("t", r.t)
        else:
            stops.append([_num(open_stop.pop("t", r.t - r.value)), _num(r.t), r.asset_id])

    pbs = [[_num(r.t), int(r.value)] for r in ev[ev.event.isin(["PBS_IN", "LOAD"]) & ev.value.notna()].itertuples()]

    return {
        "meta": {"scenario": sc["name"], "takt_s": sc["takt_s"], "index_s": sc["index_s"],
                 "window_s": [result.t0, result.t1], "shift_start_clock": sc.get("shift_start_clock"),
                 "stations": [{"id": s.asset_id, "name": s.name, "x": s.xy[0], "y": s.xy[1]} for s in cfg.stations],
                 "repair": {"id": cfg.repair.asset_id, "x": cfg.repair.xy[0], "y": cfg.repair.xy[1]},
                 "skillets": sk_ids},
        "skillets": skillets, "units": units, "stations": stations, "line_stops": stops, "pbs_count": pbs,
    }


def write_state_feed(result, path: Path) -> dict:
    feed = state_feed(result)
    Path(path).write_text(json.dumps(feed, separators=(",", ":")), encoding="utf-8")
    return feed
