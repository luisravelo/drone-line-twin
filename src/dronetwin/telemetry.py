"""One-line live status for the terminal while the simulation runs."""
from __future__ import annotations

from .catalog import Config


def sim_clock(cfg: Config, t: float) -> str:
    h, m = map(int, cfg.scenario["shift_start_clock"].split(":"))
    total = (h * 3600 + m * 60 + (t - 60.0 * cfg.scenario["warmup_min"])) % 86400
    return f"{int(total // 3600):02d}:{int(total // 60) % 60:02d}"


def format_status(line) -> str:
    cfg, t = line.cfg, line.env.now
    t0 = 60.0 * cfg.scenario["warmup_min"]
    phase = "WARM-UP" if t < t0 else "SHIFT"
    shipped = sum(1 for u in line.units if u.shipped is not None and u.shipped >= t0)
    hours = (t - t0) / 3600.0
    jph = f"{shipped / hours:5.1f}" if hours > 0 else "    -"
    on_line = sum(1 for u in line.positions if u is not None)
    last_stop = next((c["stop_station"] for c in reversed(line.cycles) if c["stop_s"] > 0), "-")
    return (f"[{sim_clock(cfg, t)} {phase:<7}] shipped {shipped:3d}  JPH {jph}  on line {on_line}  "
            f"PBS {len(line.pbs.items):2d}  last stop {last_stop}")
