"""Independent replications (one simulated day each, different seeds) for KPI spread and per-day review."""
from __future__ import annotations

import dataclasses
import os
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

from .catalog import Config
from .metrics import build_report
from .paced_line import PacedLine

DAILY_KPIS = ["shipped", "jph", "takt_attainment", "line_stop_s", "balance_loss",
              "colour_mismatch_detected", "repairs", "torque_nok"]


def _day_row(k: int, summary: dict) -> dict:
    row = {"day": k + 1, "seed": summary["seed"], **{key: summary[key] for key in DAILY_KPIS},
           "bottleneck": summary["bottleneck"]}
    row.update({f"load_{a}": v for a, v in summary["takt_load"].items()})
    row.update({f"util_{a}": v for a, v in summary["utilization"].items()})
    return row


def _simulate_day(args) -> dict:
    cfg, k = args
    c = dataclasses.replace(cfg, scenario={**cfg.scenario, "seed": cfg.scenario["seed"] + k})
    return _day_row(k, build_report(PacedLine(c).run()).summary)


def run_replications(cfg: Config, days: int = 20, first: dict | None = None, workers: int | None = None,
                     executor: ProcessPoolExecutor | None = None) -> pd.DataFrame:
    """One row per simulated day; seed = scenario seed + day index (same seeds across scenarios).

    Per-station columns: `load_<station>` (takt load, may exceed 1) and `util_<station>` (time-based, <= 1).
    `first`: the summary of a run already made with the scenario seed (day 1), so it is not simulated twice.
    Days are independent (own seed), so they run in parallel processes; results do not depend on `workers`.
    """
    todo = [k for k in range(days) if not (k == 0 and first is not None)]
    jobs = [(cfg, k) for k in todo]
    workers = min(len(todo), os.cpu_count() or 1) if workers is None else workers
    if executor is not None:
        rows = list(executor.map(_simulate_day, jobs))
    elif workers > 1 and len(todo) >= 8:          # small runs (tests) stay in-process: spawning costs more
        with ProcessPoolExecutor(max_workers=workers) as ex:
            rows = list(ex.map(_simulate_day, jobs))
    else:
        rows = [_simulate_day(j) for j in jobs]
    if first is not None and days > 0:
        rows.insert(0, _day_row(0, first))
    return pd.DataFrame(rows)


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    cols = [c for c in DAILY_KPIS if c in df.columns]
    return df[cols].agg(["mean", "std", "min", "max"]).T.round(3)
