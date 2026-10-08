import numpy as np
import pytest

from dronetwin.distributions import Dist, parse_dist, stream


def test_parse_const_none_and_mapping():
    assert parse_dist(None) is None
    assert parse_dist(14).sample(stream(1, "x")) == 14.0
    d = parse_dist({"dist": "triangular", "low": 1, "mode": 2, "high": 4})
    assert d.kind == "triangular"
    assert d.mean == pytest.approx(7 / 3)


@pytest.mark.parametrize("spec", [
    {"dist": "normal", "mean": 10, "sd": 1},
    {"dist": "lognormal", "mean": 12, "sd": 3},
    {"dist": "triangular", "low": 5, "mode": 8, "high": 15},
    {"dist": "uniform", "low": 0.5, "high": 1.0},
    {"dist": "exponential", "mean": 240},
])
def test_sample_mean_matches_declared_mean(spec):
    d = parse_dist(spec)
    rng = stream(7, "test")
    xs = np.array([d.sample(rng) for _ in range(20000)])
    assert xs.mean() == pytest.approx(d.mean, rel=0.03)


def test_lognormal_is_parameterised_by_mean_and_sd():
    d = parse_dist({"dist": "lognormal", "mean": 12, "sd": 3})
    rng = stream(3, "ln")
    xs = np.array([d.sample(rng) for _ in range(40000)])
    assert xs.std() == pytest.approx(3, rel=0.05)


def test_normal_is_floored_at_half_the_mean():
    d = parse_dist({"dist": "normal", "mean": 1, "sd": 5})
    rng = stream(1, "n")
    assert min(d.sample(rng) for _ in range(2000)) >= 0.5


def test_streams_are_reproducible_and_independent():
    assert stream(42, "CNC_01").random() == stream(42, "CNC_01").random()
    assert stream(42, "CNC_01").random() != stream(42, "SA2_01").random()


def test_unknown_distribution_raises():
    with pytest.raises(ValueError):
        Dist("weibull", {}).sample(stream(1, "x"))
