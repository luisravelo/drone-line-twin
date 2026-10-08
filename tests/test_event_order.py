def test_every_load_follows_its_pbs_in(baseline_result):
    """The replay rebuilds PBS contents from the log, so PBS_IN must precede LOAD for each body."""
    ev = baseline_result.events.reset_index(drop=True)
    first_in = ev[ev.event == "PBS_IN"].groupby("serial").apply(lambda g: g.index.min())
    loads = ev[ev.event == "LOAD"]
    assert all(first_in[s] < i for i, s in zip(loads.index, loads.serial))
