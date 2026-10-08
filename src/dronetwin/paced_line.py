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
    """Append-only event log; the single source of truth for metrics and exports."""

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
    buf_in: float | None = None          # entered the buffer conveyor (booth exit), pull mode


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
        self.rng_mix = stream(seed, "ORDER_MIX")
        self.rng_kit = stream(seed, "KITTING")
        self.rng_rep = stream(seed, "REPAIR")
        self.rehit = parse_dist(sc["quality"]["rehit"])
        up = sc["upstream"]
        self.printers = simpy.Resource(self.env, up["printers"])
        self.booths = simpy.Resource(self.env, up["paint_booths"])
        self.repair_bay = simpy.Resource(self.env, 1)
        self.pbs = simpy.FilterStore(self.env)
        # Pull mode: a customer order only starts printing when a kanban card is free (cards = buffer slots);
        # the card returns when KUKA1 takes the frame at ST00. Frames ride a paint conveyor and an accumulating
        # buffer conveyor, both at constant speed.
        self.pull = sc.get("pull")
        if self.pull:
            self.orders = simpy.Store(self.env)
            self.kanban = simpy.Container(self.env, init=self.pull["wip_cap"], capacity=self.pull["wip_cap"])
            self.printer_ids = simpy.Store(self.env)
            self.printer_ids.items.extend(range(up["printers"]))
            self.kuka2 = simpy.Resource(self.env, 1)
            self.belt_entry = simpy.Resource(self.env, 1)
            self.last_pick = -1e9
            self.started = False
            self.env.process(self._dispatch())
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
            if self.pull:
                yield self.orders.put(u)
            else:
                self.env.process(self._upstream(u))
            yield self.env.timeout(self.cfg.scenario["takt_s"])

    def _upstream(self, u: Unit):
        with self.printers.request() as rq:
            yield rq
            self.log.log("PRINTER01", "PRINT_START", serial=u.serial, sku=u.sku.code, pn=u.kit["frame"])
            yield self.env.timeout(self.cfg.models[u.sku.model].print_s)
        with self.booths.request() as rq:
            yield rq
            self.log.log("PAINT01", "PAINT_START", serial=u.serial, sku=u.sku.code, state=u.sku.colour)
            yield self.env.timeout(60.0 * self.cfg.scenario["upstream"]["paint_min"])
        # Log before the put: a waiting line takes the body in the same instant and must log LOAD after PBS_IN.
        self.log.log("PBS", "PBS_IN", serial=u.serial, sku=u.sku.code, value=len(self.pbs.items) + 1)
        yield self.pbs.put(u)

    def _dispatch(self):
        """Customer orders, in sequence, start printing as soon as a kanban card is free."""
        while True:
            u = yield self.orders.get()
            yield self.kanban.get(1)
            self.env.process(self._upstream_pull(u))

    def _upstream_pull(self, u: Unit):
        pl = self.pull
        pid = yield self.printer_ids.get()
        self.log.log("PRINTER01", "PRINT_START", serial=u.serial, sku=u.sku.code, pn=u.kit["frame"], value=pid)
        yield self.env.timeout(self.cfg.models[u.sku.model].print_s)
        with self.kuka2.request() as rq_robot, self.belt_entry.request() as rq_entry:
            yield rq_robot & rq_entry
            self.log.log("KUKA2", "TRANSFER", serial=u.serial, sku=u.sku.code, value=pid)
            yield self.env.timeout(pl["transfer_s"])
            yield self.printer_ids.put(pid)
            self.log.log("PAINT01", "BELT_IN", serial=u.serial, sku=u.sku.code)
            self.env.process(self._release_entry(pl["entry_spacing_s"]))
        yield self.env.timeout(pl["belt_to_booth_s"])
        self.log.log("PAINT01", "PAINT_START", serial=u.serial, sku=u.sku.code, state=u.sku.colour)
        yield self.env.timeout(60.0 * self.cfg.scenario["upstream"]["paint_min"])
        u.buf_in = self.env.now
        self.log.log("PBS", "PBS_IN", serial=u.serial, sku=u.sku.code, value=len(self.pbs.items) + 1)
        yield self.pbs.put(u)

    def _release_entry(self, hold):
        with self.belt_entry.request() as rq:      # the next frame waits until the previous one moved a pitch
            yield rq
            yield self.env.timeout(hold)

    def _pull_ready(self, u: Unit):
        """Buffer head arrival: travel to the queue tail, then the queue moves one pitch per pick."""
        pl = self.pull
        if not self.started:
            while len(self.pbs.items) + 1 < pl["start_buffer"]:     # build the buffer before the first load
                yield self.env.timeout(5)
            self.started = True
        head = max(u.buf_in + pl["buffer_travel_s"], self.last_pick + pl["buffer_index_s"])
        if head > self.env.now:
            yield self.env.timeout(head - self.env.now)

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
            if self.pull:
                t = self.env.now
                yield self.env.process(self._pull_ready(u))
                starved += self.env.now - t
                self.last_pick = self.env.now
                self.log.log("KUKA1", "PICK", serial=u.serial, sku=u.sku.code)
                yield self.kanban.put(1)
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
        return RunResult(self.cfg, self.log.to_frame(), pd.DataFrame(self.cycles), self.units, t0, t1)
