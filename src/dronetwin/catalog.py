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
        a["PRINTER01"] = (f"{self.site}/Print/PRINTER01", (-9 * self.pitch_m, 0.0))
        a["PAINT01"] = (f"{self.site}/Paint/PAINT01", (-6 * self.pitch_m, 0.0))
        a["ORDER_RELEASE"] = (f"{self.site}/Control/ORDER_RELEASE", (-6 * self.pitch_m, 0.0))
        a["KUKA2"] = (f"{self.site}/Paint/KUKA2", (-7 * self.pitch_m, 0.0))
        a["KUKA1"] = (f"{self.site}/GA/KUKA1", (-0.5 * self.pitch_m, 0.0))
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
        Station(s["asset_id"], s["name"], f"{site}/{area}/{s['asset_id']}", (round(i * pitch, 6), 0.0),
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
                     (round(len(stations) * pitch, 6), 2.0), ())
    models = {k: Model(k, v["frame"], tuple(v["colours"]), tuple(v["batteries"]), 60.0 * v["print_min"])
              for k, v in prod["models"].items()}
    return Config(site, models, tuple(prod["props"]), prod["parts"], elements, stations, repair,
                  parse_dist(rp["time"]), int(line["skillets"]), float(pitch), sc)
