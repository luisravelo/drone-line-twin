from dronetwin.replications import run_replications, summarise


def test_replications_vary_and_are_reproducible(baseline_cfg):
    a = run_replications(baseline_cfg, days=5)
    b = run_replications(baseline_cfg, days=5)
    assert list(a.seed) == [42, 43, 44, 45, 46]
    assert a.equals(b)
    assert a.torque_nok.nunique() > 1
    s = summarise(a)
    assert {"mean", "std", "min", "max"} <= set(s.columns)
    assert 75 <= s.loc["shipped", "mean"] <= 80


def test_per_day_station_columns(baseline_cfg):
    df = run_replications(baseline_cfg, days=3)
    assert {"day", "seed", "bottleneck", "load_ST10", "util_ST10"} <= set(df.columns)
    assert (df[[c for c in df.columns if c.startswith("util_")]] <= 1.0 + 1e-9).all().all()
