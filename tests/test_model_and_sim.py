"""The simulation, the features and the model: the guarantees the product relies on."""
from dataclasses import replace

import numpy as np
import pytest

from offerguard import evaluate as ev
from offerguard import experiments as ex
from offerguard.config import BASE, Policy
from offerguard.features import FEATURES, build_features
from offerguard.model import KINDS, UpliftModel
from offerguard.simulate import Simulation

SMALL = replace(BASE, weeks_warmup=2, weeks_learning=4, weeks_live=3)


@pytest.fixture(scope="module")
def sim():
    return Simulation(SMALL).run_until_live()


@pytest.fixture(scope="module")
def model():
    logs = [ex.brand_log(SMALL, 7000 + i) for i in range(4)]
    return ex.fit(logs)


def test_outcomes_are_consistent_across_actions(sim):
    c = sim.carts
    assert (c.sn <= c.ss).all() and (c.ss <= c.sf).all()
    assert (c.p_none <= c.p_small + 1e-12).all() and (c.p_small <= c.p_full + 1e-12).all()


def test_learning_phase_is_randomised(sim):
    log = sim.learning_log()
    shares = log.action.value_counts(normalize=True)
    assert len(shares) == 3 and shares.min() > 0.28


def test_model_never_sees_hidden_truth_or_uncertain_links(sim):
    forbidden = {"type", "p_none", "p_small", "p_full", "sn", "ss", "sf", "tw", "il", "im", "hk", "dup"}
    assert not forbidden & set(FEATURES)
    X = build_features(sim.learning_log())
    assert list(X.columns) == FEATURES


def test_possible_links_never_change_the_inputs(sim):
    c = sim.carts
    possible = c[c.il == 1]
    assert len(possible) > 0
    assert (possible.linked == 0).all()
    assert (possible.pa == possible.pa_acct).all() and (possible.po == possible.po_acct).all()


@pytest.mark.parametrize("kind", list(KINDS))
def test_bigger_offer_never_lowers_predicted_chance(sim, kind):
    log = sim.learning_log()
    p = UpliftModel(kind).fit(build_features(log), log.action, log.bought).predict(build_features(log))
    assert p.shape == (len(log), 3)
    assert (np.diff(p, axis=1) >= -1e-12).all()
    assert ((p >= 0) & (p <= 1)).all()


def test_live_phase_runs_end_to_end(model):
    s = Simulation(SMALL).run_until_live().run_live(model, Policy())
    live = s.live_carts()
    assert live.en.notna().all()
    assert (live.action[live.oo == 1] == -1).all()
    table = ev.strategy_table(live)
    assert {"reminder", "discount_all", "offer_guard", "oracle"} <= set(table)
    # Perfect foresight is the ceiling: nothing beats it in expectation.
    assert table["oracle"]["exp_net"] >= max(t["exp_net"] for k, t in table.items() if k != "oracle") - 1e-6


def test_safety_net_trips_when_behaviour_shifts(model):
    drift = replace(SMALL, drift_week=1, drift_p0_mult=0.4, drift_lift_mult=0.2, weeks_live=4)
    s = Simulation(drift).run_until_live().run_live(model, Policy(), monitor_days=14)
    assert any(a["tripped"] for a in s.alerts)
    live = s.live_carts()
    assert (live["mode"] == "cold").any()
