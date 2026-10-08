# Drone Line Twin — Plan 2: GA Paced Line (supersedes Plan 1 Tasks 2–10)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A reproducible SimPy model of the 8-position GA paced skillet line (ST00–ST70) building 12 SKUs from
pre-painted frames. It prints terminal telemetry and writes KPIs, an HTML dashboard and a state feed for the Blender replay.

**Architecture:**
- `catalog.py` loads products, SKUs, work elements, line and scenario from YAML.
- `paced_line.py` runs:
  - order release
  - the fixed-time upstream (print → paint → PBS)
  - the takt loop (index, load in sequence, stations work in parallel, line stop when any station
    overruns, attributed to the last finisher)
  - final inspection with colour check, and the off-line repair bay
- Downstream (metrics, telemetry, exports) reads one event log plus a per-cycle table.

**Tech Stack:** Python 3.13, simpy, numpy, pandas, pyyaml, plotly, pytest.

**Spec:** `docs/specs/2026-10-05-drone-line-twin-design.md` (rev 2)

## Global Constraints
- Sim time unit: **seconds**. Warm-up and shift lengths are in minutes in YAML and converted ×60.
- Z-up, meters. The line runs along +X at `pitch_m` per station; the skillet return lane is at y = −1.5.
- Prim paths: `/World/Mesa/DroneLine/<Area>/<asset_id>`.
- One RNG stream per station plus `ORDER_MIX`, `KITTING`, `REPAIR`: `stream(seed, name)` from Plan 1 Task 1.
- Event log columns exactly: `t, asset_id, prim_path, event, state, pn, serial, sku, x, y, value`.
- KPIs are computed on the window `[warmup, warmup + shift)` only.
- Only valid SKUs exist: MODEL_A has a fixed STD battery, so 12 SKUs.

## File map

| File | Responsibility |
|---|---|
| `src/dronetwin/distributions.py` | **Plan 1 Task 1, unchanged** |
| `config/products.yaml` | models, colours, batteries, props, part-number patterns |
| `config/elements.yaml` | work elements (seconds), torque flag |
| `config/line.yaml`, `config/line_consolidated.yaml` | station order and elements, repair bay, skillets |
| `config/scenarios/baseline.yaml`, `consolidated.yaml` | takt, mix, quality, upstream, seed |
| `src/dronetwin/catalog.py` | dataclasses, `load_config`, SKU enumeration, kit, work-content means |
| `src/dronetwin/paced_line.py` | `EventLog`, `Unit`, `PacedLine`, `RunResult` |
| `src/dronetwin/metrics.py` | `build_report` |
| `src/dronetwin/telemetry.py` | `format_status` |
| `src/dronetwin/export/state_feed.py`, `export/dashboard.py` | outputs |
| `run.py` | CLI |

---

### Task 1: Scaffold and distributions
Execute **Plan 1, Task 1** exactly as written (pyproject, .gitignore, `distributions.py`, 10 tests).

---

### Task 2: Config and catalog

**Files:** create the 6 config files and `src/dronetwin/catalog.py`. Test: `tests/test_catalog.py`.

**Interfaces produced:**
- `load_config(dir, scenario) -> Config`
- `Config.skus -> list[Sku]`
- `Config.kit(sku, controller_colour=None) -> dict`
- `Config.work_content_mean() -> dict[str, float]`
- `Config.assets -> dict[asset_id, (prim_path, (x, y))]`
- dataclasses `Element(name, dist, torque)`, `Station(asset_id, name, prim_path, xy, elements, inspect)`,
  `Model(code, frame, colours, batteries, print_s)`, `Sku(code, model, colour, prop, battery)`

- [ ] **Step 1: Config files**

`config/products.yaml`:
```yaml
models:
  A: {frame: MODEL_A, colours: [BLK, RED], batteries: [STD], print_min: 4.5}
  B: {frame: MODEL_B, colours: [YEL, SLV], batteries: [STD, LR], print_min: 5.5}
props: [TRI, BI]
parts:
  controller: "PN-ESC-FC-STACK-{colour}"
  prop: {TRI: PN-PROP-5-TRI, BI: PN-PROP-5-BI}
  battery: {STD: PN-BAT-6S, LR: PN-BAT-6S-LR}
```

`config/elements.yaml` (seconds; LogN for manual work, Norm for scripted work):
```yaml
load_frame: {dist: normal, mean: 25, sd: 3}
place_motor: {dist: lognormal, mean: 18, sd: 4}
torque_m3: {dist: lognormal, mean: 7, sd: 1.5, torque: true}
place_controller: {dist: lognormal, mean: 55, sd: 10}
install_camera: {dist: lognormal, mean: 40, sd: 8}
install_antenna: {dist: lognormal, mean: 20, sd: 5}
place_prop: {dist: lognormal, mean: 6, sd: 1.5}
torque_m5_propnut: {dist: lognormal, mean: 9, sd: 2, torque: true}
place_battery: {dist: lognormal, mean: 15, sd: 3}
strap_battery: {dist: lognormal, mean: 25, sd: 6}
bench_test: {dist: normal, mean: 90, sd: 10}
visual_check: {dist: lognormal, mean: 20, sd: 5}
```

`config/line.yaml`:
```yaml
site: /World/Mesa/DroneLine
area: GA
pitch_m: 1.2
skillets: 10
stations:
  - {asset_id: ST00, name: Load, elements: [[load_frame, 1]]}
  - {asset_id: ST10, name: Motors, elements: [[place_motor, 4], [torque_m3, 16]]}
  - {asset_id: ST20, name: Controller, elements: [[place_controller, 1], [torque_m3, 4]]}
  - {asset_id: ST30, name: Camera, elements: [[install_camera, 1]]}
  - {asset_id: ST40, name: Antennas, elements: [[install_antenna, 2]]}
  - {asset_id: ST50, name: Props, elements: [[place_prop, 4], [torque_m5_propnut, 4]]}
  - {asset_id: ST60, name: Marriage, elements: [[place_battery, 1], [strap_battery, 1]]}
  - {asset_id: ST70, name: Final_Inspection, inspect: true, elements: [[bench_test, 1], [visual_check, 1]]}
repair: {asset_id: RPR01, name: Repair_Bay, time: {dist: lognormal, mean: 300, sd: 60}}
```

`config/line_consolidated.yaml`: same header as `line.yaml`, `skillets: 6`, with these stations:
```yaml
stations:
  - {asset_id: ST00, name: Load, elements: [[load_frame, 1]]}
  - {asset_id: ST10, name: Motors_Controller, elements: [[place_motor, 4], [torque_m3, 16], [place_controller, 1], [torque_m3, 4]]}
  - {asset_id: ST20, name: Camera_Antennas_Props_Marriage, elements: [[install_camera, 1], [install_antenna, 2], [place_prop, 4], [torque_m5_propnut, 4], [place_battery, 1], [strap_battery, 1]]}
  - {asset_id: ST70, name: Final_Inspection, inspect: true, elements: [[bench_test, 1], [visual_check, 1]]}
```

`config/scenarios/baseline.yaml`:
```yaml
name: baseline
seed: 42
line: line.yaml
takt_s: 360
index_s: 6
warmup_min: 480
shift_min: 480
shift_start_clock: "06:00"
mix:
  model: {A: 0.5, B: 0.5}
  colour: {A: {BLK: 0.5, RED: 0.5}, B: {YEL: 0.5, SLV: 0.5}}
  prop: {TRI: 0.6, BI: 0.4}
  battery: {B: {STD: 0.7, LR: 0.3}}
quality:
  torque_nok_rate: 0.015
  rehit: {dist: lognormal, mean: 15, sd: 5}
  kitting_colour_error_rate: 0.005
upstream: {printers: 1, paint_booths: 1, paint_min: 4}
```
`config/scenarios/consolidated.yaml`: the same as baseline with `name: consolidated`, `line: line_consolidated.yaml`
(same takt 360 s; the question is how few stations hold it).

- [ ] **Step 2: Failing tests**, `tests/test_catalog.py`
```python
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
```

- [ ] **Step 3: Run** `python -m pytest tests/test_catalog.py -q`. It should fail (`ModuleNotFoundError`).

- [ ] **Step 4: Implement** `src/dronetwin/catalog.py`
```python
"""Load products, SKUs, work elements, line and scenario for the GA paced line (rev 2)."""
from __future__ import annotations

import itertools
from dataclasses import dataclass
from pathlib import Path

import yaml

from .distributions import Dist, parse_dist


@dataclass(frozen=True)
class Element:
    name: str
    dist: Dist
    torque: bool


@dataclass(frozen=True)
class Station:
    asset_id: str
    name: str
    prim_path: str
    xy: tuple[float, float]
    elements: tuple[tuple[str, int], ...]
    inspect: bool = False


@dataclass(frozen=True)
class Model:
    code: str
    frame: str
    colours: tuple[str, ...]
    batteries: tuple[str, ...]
    print_s: float


@dataclass(frozen=True)
class Sku:
    code: str
    model: str
    colour: str
    prop: str
    battery: str


def sku_code(model: Model, colour: str, prop: str, battery: str) -> str:
    return f"{model.code}-{colour}-{prop}" + (f"-{battery}" if len(model.batteries) > 1 else "")


@dataclass(frozen=True)
class Config:
    site: str
    models: dict
    props: tuple[str, ...]
    parts: dict
    elements: dict
    stations: tuple[Station, ...]
    repair: Station
    repair_time: Dist
    skillets: int
    pitch_m: float
    scenario: dict

    @property
    def skus(self) -> list[Sku]:
        return [Sku(sku_code(m, c, p, b), m.code, c, p, b)
                for m in self.models.values()
                for c, p, b in itertools.product(m.colours, self.props, m.batteries)]

    @property
    def colours(self) -> list[str]:
        return [c for m in self.models.values() for c in m.colours]

    def kit(self, sku: Sku, controller_colour: str | None = None) -> dict[str, str]:
        p = self.parts
        return {"frame": self.models[sku.model].frame,
                "controller": p["controller"].format(colour=controller_colour or sku.colour),
                "prop": p["prop"][sku.prop], "battery": p["battery"][sku.battery]}

    def work_content_mean(self) -> dict[str, float]:
        return {s.asset_id: sum(self.elements[e].dist.mean * n for e, n in s.elements) for s in self.stations}

    @property
    def assets(self) -> dict:
        a = {s.asset_id: (s.prim_path, s.xy) for s in self.stations}
        a[self.repair.asset_id] = (self.repair.prim_path, self.repair.xy)
        a["PBS"] = (f"{self.site}/Paint/PBS", (-3 * self.pitch_m, 0.0))
        a["ORDER_RELEASE"] = (f"{self.site}/Control/ORDER_RELEASE", (-6 * self.pitch_m, 0.0))
        for k in range(self.skillets):
            sid = f"SK{k + 1:02d}"
            a[sid] = (f"{self.site}/GA/Skillets/{sid}", (-self.pitch_m, -1.5))
        return a


def _element(name: str, spec: dict) -> Element:
    spec = dict(spec)
    torque = bool(spec.pop("torque", False))
    return Element(name, parse_dist(spec), torque)


def load_config(config_dir: Path, scenario: str = "baseline") -> Config:
    d = Path(config_dir)

    def read(name: str) -> dict:
        return yaml.safe_load((d / name).read_text(encoding="utf-8"))

    prod, els, sc = read("products.yaml"), read("elements.yaml"), read(f"scenarios/{scenario}.yaml")
    line = read(sc["line"])
    site, area, pitch = line["site"], line["area"], line["pitch_m"]
    elements = {k: _element(k, v) for k, v in els.items()}
    stations = tuple(
        Station(s["asset_id"], s["name"], f"{site}/{area}/{s['asset_id']}", (i * pitch, 0.0),
                tuple((e, int(n)) for e, n in s["elements"]), bool(s.get("inspect", False)))
        for i, s in enumerate(line["stations"]))
    for s in stations:
        for e, _ in s.elements:
            if e not in elements:
                raise ValueError(f"unknown work element {e!r} at {s.asset_id}")
    if sum(s.inspect for s in stations) != 1 or not stations[-1].inspect:
        raise ValueError("exactly one inspection station, and it must be the last")
    rp = line["repair"]
    repair = Station(rp["asset_id"], rp["name"], f"{site}/{area}/{rp['asset_id']}",
                     (len(stations) * pitch, 2.0), ())
    models = {k: Model(k, v["frame"], tuple(v["colours"]), tuple(v["batteries"]), 60.0 * v["print_min"])
              for k, v in prod["models"].items()}
    return Config(site, models, tuple(prod["props"]), prod["parts"], elements, stations, repair,
                  parse_dist(rp["time"]), int(line["skillets"]), float(pitch), sc)
```

- [ ] **Step 5: Run** `python -m pytest tests/test_catalog.py -q`. Expect `4 passed`.
- [ ] **Step 6: Commit** `feat: GA line config (12 SKUs, work elements, paced line) and catalog`

---

### Task 3: Paced line engine

**Files:** create `src/dronetwin/paced_line.py`. Test: `tests/test_paced_line.py`, `tests/conftest.py`.

**Interfaces produced:**
- `PacedLine(cfg)` with `.env`, `.log`, `.units`, `.cycles`, `.positions`
- `.every(interval_s, callback)`
- `.run() -> RunResult(cfg, events, cycles, units, t0, t1)`
- `COLUMNS`
- Cycle rows have the keys `cycle, start, end, stop_s, stop_station, pbs_starved_s, work_<asset_id>`.

- [ ] **Step 1: Failing tests**

`tests/conftest.py`:
```python
from pathlib import Path
import pytest
from dronetwin.catalog import load_config
from dronetwin.paced_line import PacedLine

CONFIG = Path(__file__).resolve().parents[1] / "config"


@pytest.fixture(scope="session")
def baseline_cfg():
    return load_config(CONFIG, "baseline")


@pytest.fixture(scope="session")
def baseline_result(baseline_cfg):
    return PacedLine(baseline_cfg).run()


@pytest.fixture(scope="session")
def consolidated_result():
    return PacedLine(load_config(CONFIG, "consolidated")).run()
```

`tests/test_paced_line.py`:
```python
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
            assert u.kit["controller"].endswith(u.sku.colour)


def test_colour_errors_are_caught_at_inspection(baseline_result):
    ev = baseline_result.events
    noks = set(ev.serial[ev.event == "INSPECT_NOK"])
    repaired = set(ev.serial[ev.event == "REPAIR"])
    assert noks <= repaired | {u.serial for u in baseline_result.units if u.shipped is None}


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
```

- [ ] **Step 2: Run** `python -m pytest tests/test_paced_line.py -q`. It should fail (`ModuleNotFoundError`).

- [ ] **Step 3: Implement** `src/dronetwin/paced_line.py`
```python
"""GA paced skillet line: fixed takt, parallel stations, line stop on overrun, off-line repair."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import simpy

from .catalog import Config, Sku, sku_code
from .distributions import parse_dist, stream

COLUMNS = ["t", "asset_id", "prim_path", "event", "state", "pn", "serial", "sku", "x", "y", "value"]


class EventLog:
    def __init__(self, env: simpy.Environment, assets: dict):
        self.env, self.assets, self.rows = env, assets, []

    def log(self, asset_id, event, *, state=None, pn=None, serial=None, sku=None, x=None, y=None, value=None):
        prim, (x0, y0) = self.assets[asset_id]
        self.rows.append((float(self.env.now), asset_id, prim, event, state, pn, serial, sku,
                          x0 if x is None else x, y0 if y is None else y, value))

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame(self.rows, columns=COLUMNS)


@dataclass(eq=False)
class Unit:
    serial: str
    seq: int
    sku: Sku
    kit: dict
    released: float
    skillet: str | None = None
    outcome: str | None = None
    shipped: float | None = None


@dataclass
class RunResult:
    cfg: Config
    events: pd.DataFrame
    cycles: pd.DataFrame
    units: list
    t0: float
    t1: float


class PacedLine:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        sc = cfg.scenario
        self.env = simpy.Environment()
        self.log = EventLog(self.env, cfg.assets)
        seed = sc["seed"]
        self.rng = {s.asset_id: stream(seed, s.asset_id) for s in cfg.stations}
        self.rng_mix, self.rng_kit, self.rng_rep = stream(seed, "ORDER_MIX"), stream(seed, "KITTING"), stream(seed, "REPAIR")
        self.rehit = parse_dist(sc["quality"]["rehit"])
        up = sc["upstream"]
        self.printers = simpy.Resource(self.env, up["printers"])
        self.booths = simpy.Resource(self.env, up["paint_booths"])
        self.repair_bay = simpy.Resource(self.env, 1)
        self.pbs = simpy.FilterStore(self.env)
        self.units: list[Unit] = []
        self.cycles: list[dict] = []
        self.positions: list[Unit | None] = [None] * len(cfg.stations)
        self.free_skillets = [f"SK{k + 1:02d}" for k in range(cfg.skillets)]
        self.next_seq = 1
        self.env.process(self._release())
        self.env.process(self._line())

    # --- orders and upstream (outside the analysed boundary) --------------------------------
    def _choose(self, weights: dict) -> str:
        keys = list(weights)
        p = np.array([weights[k] for k in keys], dtype=float)
        return keys[self.rng_mix.choice(len(keys), p=p / p.sum())]

    def _sample_sku(self) -> Sku:
        mix = self.cfg.scenario["mix"]
        model = self.cfg.models[self._choose(mix["model"])]
        colour = self._choose(mix["colour"][model.code])
        prop = self._choose(mix["prop"])
        battery = self._choose(mix["battery"][model.code]) if len(model.batteries) > 1 else model.batteries[0]
        return Sku(sku_code(model, colour, prop, battery), model.code, colour, prop, battery)

    def _kit(self, sku: Sku) -> dict:
        colour = sku.colour
        if self.rng_kit.random() < self.cfg.scenario["quality"]["kitting_colour_error_rate"]:
            others = sorted(set(self.cfg.colours) - {sku.colour})
            colour = others[int(self.rng_kit.integers(len(others)))]
        return self.cfg.kit(sku, colour)

    def _release(self):
        n = 0
        while True:
            n += 1
            sku = self._sample_sku()
            u = Unit(f"{sku.model}-{n:05d}", n, sku, self._kit(sku), self.env.now)
            self.units.append(u)
            self.log.log("ORDER_RELEASE", "RELEASE", serial=u.serial, sku=sku.code, pn=u.kit["controller"])
            self.env.process(self._upstream(u))
            yield self.env.timeout(self.cfg.scenario["takt_s"])

    def _upstream(self, u: Unit):
        with self.printers.request() as rq:
            yield rq
            yield self.env.timeout(self.cfg.models[u.sku.model].print_s)
        with self.booths.request() as rq:
            yield rq
            yield self.env.timeout(60.0 * self.cfg.scenario["upstream"]["paint_min"])
        yield self.pbs.put(u)
        self.log.log("PBS", "PBS_IN", serial=u.serial, sku=u.sku.code, value=len(self.pbs.items))

    # --- GA paced line --------------------------------------------------------------------
    def _line(self):
        sc = self.cfg.scenario
        takt, index = sc["takt_s"], sc["index_s"]
        cyc = 0
        while True:
            cyc += 1
            start = self.env.now
            exiting = self.positions[-1]
            self.positions = [None] + self.positions[:-1]
            yield self.env.timeout(index)
            if exiting is not None:
                self._exit(exiting)
            starved = 0.0
            get = self.pbs.get(lambda u: u.seq == self.next_seq)
            if not get.triggered:
                self.log.log("PBS", "PBS_STARVED")
                t = self.env.now
                yield get
                starved = self.env.now - t
            u = get.value
            self.next_seq += 1
            u.skillet = self.free_skillets.pop(0)
            self.positions[0] = u
            self.log.log("PBS", "LOAD", serial=u.serial, sku=u.sku.code, value=len(self.pbs.items))
            self._move_skillets()
            work_start = self.env.now
            deadline = work_start + takt - index
            finish: dict[str, float] = {}
            procs = []
            for i, unit in enumerate(self.positions):
                if unit is None:
                    self.log.log(self.cfg.stations[i].asset_id, "STATE", state="EMPTY")
                else:
                    procs.append(self.env.process(self._work(i, unit, finish)))
            self.env.process(self._andon(deadline, finish))
            yield self.env.all_of(procs + [self.env.timeout(takt - index)])
            stop = max(0.0, self.env.now - deadline)
            culprit = max(finish, key=finish.get) if stop > 1e-9 else None
            if culprit:
                self.log.log(culprit, "LINE_RESUME", value=stop)
            row = {"cycle": cyc, "start": start, "end": self.env.now, "stop_s": stop if culprit else 0.0,
                   "stop_station": culprit, "pbs_starved_s": starved}
            for s in self.cfg.stations:
                row[f"work_{s.asset_id}"] = finish[s.asset_id] - work_start if s.asset_id in finish else np.nan
            self.cycles.append(row)

    def _andon(self, deadline: float, finish: dict):
        yield self.env.timeout(max(0.0, deadline - self.env.now))
        for i, s in enumerate(self.cfg.stations):
            if self.positions[i] is not None and s.asset_id not in finish:
                self.log.log(s.asset_id, "LINE_STOP", state="STOPPED", serial=self.positions[i].serial)

    def _work(self, i: int, u: Unit, finish: dict):
        st = self.cfg.stations[i]
        rng = self.rng[st.asset_id]
        nok_rate = self.cfg.scenario["quality"]["torque_nok_rate"]
        self.log.log(st.asset_id, "STATE", state="WORKING", serial=u.serial, sku=u.sku.code)
        for name, count in st.elements:
            el = self.cfg.elements[name]
            for _ in range(count):
                self.log.log(st.asset_id, "ELEMENT_START", pn=name, serial=u.serial, sku=u.sku.code)
                yield self.env.timeout(el.dist.sample(rng))
                if el.torque:
                    if rng.random() < nok_rate:
                        self.log.log(st.asset_id, "TORQUE_NOK", pn=name, serial=u.serial, sku=u.sku.code)
                        yield self.env.timeout(self.rehit.sample(rng))
                    self.log.log(st.asset_id, "TORQUE_OK", pn=name, serial=u.serial, sku=u.sku.code)
        if st.inspect:
            ok = u.kit["controller"].endswith("-" + u.sku.colour)
            u.outcome = "OK" if ok else "NOK"
            self.log.log(st.asset_id, "INSPECT_OK" if ok else "INSPECT_NOK", pn=u.kit["controller"],
                         serial=u.serial, sku=u.sku.code)
        finish[st.asset_id] = self.env.now
        self.log.log(st.asset_id, "STATE", state="DONE", serial=u.serial, sku=u.sku.code)

    def _exit(self, u: Unit) -> None:
        self.free_skillets.append(u.skillet)
        if u.outcome == "NOK":
            self.env.process(self._repair(u))
        else:
            self._ship(u)

    def _ship(self, u: Unit) -> None:
        u.shipped = self.env.now
        self.log.log(self.cfg.stations[-1].asset_id, "SHIP", serial=u.serial, sku=u.sku.code)

    def _repair(self, u: Unit):
        with self.repair_bay.request() as rq:
            yield rq
            self.log.log(self.cfg.repair.asset_id, "REPAIR", serial=u.serial, sku=u.sku.code, pn=u.kit["controller"])
            yield self.env.timeout(self.cfg.repair_time.sample(self.rng_rep))
        u.kit = self.cfg.kit(u.sku)
        u.outcome = "REPAIRED"
        self._ship(u)

    def _move_skillets(self) -> None:
        for i, u in enumerate(self.positions):
            if u is not None:
                x, y = self.cfg.stations[i].xy
                self.log.log(u.skillet, "MOVE", x=x, y=y, serial=u.serial, sku=u.sku.code)
        for k, sid in enumerate(self.free_skillets):
            self.log.log(sid, "MOVE", x=(len(self.cfg.stations) - 1 - k) * self.cfg.pitch_m, y=-1.5)

    # --- running ---------------------------------------------------------------------------
    def every(self, interval_s: float, callback) -> None:
        def loop():
            while True:
                yield self.env.timeout(interval_s)
                callback(self)
        self.env.process(loop())

    def run(self) -> RunResult:
        sc = self.cfg.scenario
        t0 = 60.0 * sc["warmup_min"]
        t1 = t0 + 60.0 * sc["shift_min"]
        self.env.run(until=t1)
        cycles = pd.DataFrame(self.cycles)
        return RunResult(self.cfg, self.log.to_frame(), cycles, self.units, t0, t1)
```

- [ ] **Step 4: Run** `python -m pytest tests/test_paced_line.py -q`. Expect `7 passed`. If the demand test fails, print shipped counts and line-stop shares for both runs before changing any value.
- [ ] **Step 5: Commit** `feat: GA paced skillet line (takt, line stops, colour-check inspection, repair)`

---

### Task 4: Metrics

**Files:** `src/dronetwin/metrics.py`, `tests/test_metrics.py`.

**Produces:** `build_report(result) -> Report(summary: dict, work_mean: dict, stops: pd.Series, cycles: pd.DataFrame)`.

- [ ] **Step 1: Failing test**, `tests/test_metrics.py`
```python
from dronetwin.metrics import build_report


def test_baseline_report(baseline_result):
    s = build_report(baseline_result).summary
    assert 0 < s["jph"] <= s["jph_ideal"] + 1e-9
    assert s["bottleneck"] == "ST10"
    assert 0.5 < s["balance_loss"] < 0.8
    assert s["pbs_starved_s"] == 0
    assert sum(s["mix_in"].values()) >= sum(s["mix_out"].values()) > 0


def test_consolidation_cuts_balance_loss(baseline_result, consolidated_result):
    a, b = build_report(baseline_result).summary, build_report(consolidated_result).summary
    assert b["balance_loss"] < a["balance_loss"]
```

- [ ] **Step 2: Run** the test. It should fail.

- [ ] **Step 3: Implement** `src/dronetwin/metrics.py`
```python
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
    ship = ev[win & (ev.event == "SHIP")]
    rel = ev[win & (ev.event == "RELEASE")]
    work = {a: float(cw[f"work_{a}"].mean()) for a in ids}
    stops = cw[cw.stop_s > 0].groupby("stop_station").stop_s.sum().reindex(ids, fill_value=0.0)
    tq = ev[win & ev.event.isin(["TORQUE_OK", "TORQUE_NOK"])]
    ok = tq[tq.event == "TORQUE_OK"].groupby("asset_id").size()
    nok = tq[tq.event == "TORQUE_NOK"].groupby("asset_id").size()
    summary = {
        "scenario": sc["name"], "seed": sc["seed"], "takt_s": sc["takt_s"], "window_s": [t0, t1],
        "shipped": int(len(ship)), "jph": round(len(ship) / hours, 2), "jph_ideal": round(3600.0 / sc["takt_s"], 2),
        "cycles": int(len(cw)),
        "takt_attainment": round(float((cw.stop_s == 0).mean()), 3) if len(cw) else None,
        "line_stop_s": round(float(cw.stop_s.sum()), 1),
        "line_stop_by_station_s": {k: round(float(v), 1) for k, v in stops.items() if v > 0},
        "bottleneck": str(stops.idxmax()) if stops.sum() > 0 else max(work, key=work.get),
        "work_content_mean_s": {k: round(v, 1) for k, v in work.items()},
        "balance_loss": round(1 - sum(work.values()) / (len(ids) * (sc["takt_s"] - sc["index_s"])), 3),
        "torque_nok_rate": {k: round(float(nok.get(k, 0)) / float(ok[k]), 4) for k in ok.index},
        "colour_mismatch_detected": int((win & (ev.event == "INSPECT_NOK")).sum()),
        "repairs": int((win & (ev.event == "REPAIR")).sum()),
        "pbs_starved_s": round(float(cw.pbs_starved_s.sum()), 1),
        "mix_in": {k: int(v) for k, v in rel.sku.value_counts().items()},
        "mix_out": {k: int(v) for k, v in ship.sku.value_counts().items()},
    }
    return Report(summary, work, stops, cw)
```

- [ ] **Step 4: Run** `python -m pytest -q`. Everything should pass.
- [ ] **Step 5: Commit** `feat: GA line KPIs`

---

### Task 5: Telemetry and CLI
**Files:** `src/dronetwin/telemetry.py`, `run.py`, `tests/test_cli.py`.

- `format_status(line)`:
  - one line per simulated hour
  - fields: clock (from `shift_start_clock`), phase (WARM-UP / SHIFT), shipped in the shift, JPH so far,
    PBS level, stations currently STOPPED, last line-stop station
- `run.py --scenario --config --out --quiet`:
  - writes `events.csv`, `cycles.csv`, `kpis.json`, then calls `write_exports`
  - prints the summary block
- **Test:** the CLI exits 0, writes `kpis.json` with `shipped > 0`, and stdout contains "JPH".

### Task 6: State feed (+ optional USD)
- Adapt Plan 1 Task 8 `state_feed.py` (the code is unchanged apart from the column rename):
  - `FEED_COLUMNS = ["t","event","state","x","y","value","serial","sku","pn"]`
  - type is `station` / `skillet` (`SK*`) / `buffer`
- **Test:** the asset set equals `cfg.assets`, and the STATE count matches the event log.

### Task 7: Dashboard
- **Figures:**
  - line balance: bars of mean work per station plus a takt − index line (the key figure)
  - line-stop Pareto by station
  - JPH by shift hour
  - SKU mix in vs out (12 SKUs)
  - torque NOK rate by station
  - KPI cards: JPH vs ideal, takt attainment, bottleneck, colour mismatches caught, repairs
- Load the `dataviz` skill first; keep the station state colours consistent with the replay.
- **Test:** the HTML is self-contained and contains "Line balance".

### Task 8: README + verification
- Run `python run.py --scenario baseline` and `--scenario consolidated`.
- Paste both summaries into the README with the demand-takt and station-consolidation story.
- `python -m pytest -q` passes.

## Out of scope (Plan 3)
Blender line scene and replay from `state_feed.json` (Z-up), video render, operator dummies, kit-container
fleets per SKU, AMRs and goods-to-person.
