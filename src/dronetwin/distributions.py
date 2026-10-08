"""Seeded sampling of the time distributions declared in YAML."""
from __future__ import annotations

import math
import zlib
from dataclasses import dataclass
from functools import cached_property

import numpy as np


def stream(seed: int, name: str) -> np.random.Generator:
    """Independent, reproducible RNG stream per named asset (common random numbers)."""
    return np.random.default_rng([seed, zlib.crc32(name.encode())])


@dataclass(frozen=True, eq=False)
class Dist:
    kind: str
    params: dict

    def sample(self, rng: np.random.Generator) -> float:
        p = self.params
        if self.kind == "const":
            return float(p["value"])
        if self.kind == "normal":
            floor = p.get("floor", 0.5 * p["mean"])
            return float(max(floor, rng.normal(p["mean"], p["sd"])))
        if self.kind == "lognormal":
            mu, sigma = self._lognormal
            return float(rng.lognormal(mu, sigma))
        if self.kind == "triangular":
            return float(rng.triangular(p["low"], p["mode"], p["high"]))
        if self.kind == "uniform":
            return float(rng.uniform(p["low"], p["high"]))
        if self.kind == "exponential":
            return float(rng.exponential(p["mean"]))
        raise ValueError(f"unknown distribution {self.kind!r}")

    @cached_property
    def _lognormal(self) -> tuple[float, float]:
        """(mu, sigma) of the underlying normal, from the mean/sd given in YAML (computed once, not per sample)."""
        p = self.params
        sigma2 = math.log(1 + (p["sd"] / p["mean"]) ** 2)
        return math.log(p["mean"]) - sigma2 / 2, math.sqrt(sigma2)

    @property
    def mean(self) -> float:
        p = self.params
        if self.kind == "const":
            return float(p["value"])
        if self.kind in ("normal", "lognormal", "exponential"):
            return float(p["mean"])
        if self.kind == "triangular":
            return (p["low"] + p["mode"] + p["high"]) / 3
        if self.kind == "uniform":
            return (p["low"] + p["high"]) / 2
        raise ValueError(f"unknown distribution {self.kind!r}")


def parse_dist(spec) -> Dist | None:
    if spec is None:
        return None
    if isinstance(spec, (int, float)):
        return Dist("const", {"value": float(spec)})
    params = dict(spec)
    kind = params.pop("dist")
    return Dist(kind, params)
