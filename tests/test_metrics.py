from dronetwin.metrics import build_report


def test_baseline_report(baseline_result):
    s = build_report(baseline_result).summary
    assert 0 < s["jph"] <= s["jph_ideal"] + 1e-9
    assert s["bottleneck"] == "ST10"
    assert s["pbs_starved_s"] == 0
    assert 0.6 < s["balance_loss"] < 0.9
    assert sum(s["mix_in"].values()) >= sum(s["mix_out"].values()) > 0


def test_consolidation_cuts_balance_loss(baseline_result, consolidated_result):
    a = build_report(baseline_result).summary
    b = build_report(consolidated_result).summary
    assert b["balance_loss"] < a["balance_loss"]
    assert b["stations"] < a["stations"]
