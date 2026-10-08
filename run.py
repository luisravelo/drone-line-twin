"""Run the drone GA line DES: terminal telemetry, KPIs, replications and the HTML line viewer."""
from __future__ import annotations

import argparse
import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from dronetwin.catalog import load_config
from dronetwin.export.state_feed import write_state_feed
from dronetwin.export.viewer import scenario_payload, write_viewer
from dronetwin.metrics import build_report
from dronetwin.paced_line import PacedLine
from dronetwin.replications import run_replications, summarise
from dronetwin.telemetry import format_status


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--scenarios", nargs="+", default=["baseline", "consolidated", "growth_8pos", "growth_6pos"])
    ap.add_argument("--config", default="config")
    ap.add_argument("--out", default="out")
    ap.add_argument("--days", type=int, default=20, help="replications per scenario")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    payloads = []
    pool = ProcessPoolExecutor(max_workers=min(os.cpu_count() or 1, 12))   # one pool for every scenario's days
    for name in args.scenarios:
        cfg = load_config(Path(args.config), name)
        line = PacedLine(cfg)
        if not args.quiet:
            print(f"\n=== {name} | takt {cfg.scenario['takt_s']} s | {len(cfg.stations)} positions ===")
            line.every(3600, lambda l: print(format_status(l), flush=True))
        result = line.run()
        report = build_report(result)
        reps = run_replications(cfg, days=args.days, first=report.summary, executor=pool)   # day 1 = this run
        result.events.to_csv(out / f"events_{name}.csv", index=False)
        result.cycles.to_csv(out / f"cycles_{name}.csv", index=False)
        reps.to_csv(out / f"replications_{name}.csv", index=False)
        write_state_feed(result, out / f"state_feed_{name}.json")
        (out / f"kpis_{name}.json").write_text(json.dumps(report.summary, indent=2), encoding="utf-8")
        payloads.append(scenario_payload(result, report, reps))
        s = report.summary
        print(f"{name}: shipped {s['shipped']} ({s['jph']} JPH vs {s['jph_ideal']} ideal) | "
              f"takt attainment {s['takt_attainment']:.0%} | balance loss {s['balance_loss']:.0%} | "
              f"heaviest {s['bottleneck']} | colour catches {s['colour_mismatch_detected']}")
        print(summarise(reps).to_string())
    pool.shutdown()
    write_viewer(payloads, out / "line_viewer.html")
    print(f"\nViewer: {(out / 'line_viewer.html').resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
