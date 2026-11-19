"""The decision rule: the part of Offer Guard a merchant has to be able to trust exactly."""
import numpy as np
import pytest

from offerguard import policy as pol
from offerguard.config import Policy


def test_value_formula_charges_for_shoppers_who_would_buy_anyway():
    # Rs 2,157 cart, Rs 1,329 margin, the "Arjun" example from the pitch deck.
    small, full = pol.offer_values([2157], [1329], 0.06, 0.10, 0.18)
    assert full[0] == pytest.approx(0.18 * (1329 - 215.7) - 0.06 * 1329)
    assert small[0] == pytest.approx(0.10 * (1329 - 107.85) - 0.06 * 1329)
    assert round(full[0]) == 121


def test_loyal_shopper_gets_a_reminder():
    # "Priya": 43% without an offer, 45% with 10%. The offer loses money.
    rec, gain = pol.recommend([2000], [1200], [0.43], [0.44], [0.45])
    assert rec[0] == pol.NONE
    assert gain[0] < 0


def test_persuadable_shopper_gets_the_offer():
    rec, _ = pol.recommend([2157], [1329], [0.06], [0.10], [0.18])
    assert rec[0] == pol.FULL


def test_minimum_gain_is_respected():
    args = ([2157], [1329], [0.06], [0.10], [0.18])
    assert pol.recommend(*args, Policy(gain=100))[0][0] == pol.FULL
    assert pol.recommend(*args, Policy(gain=150))[0][0] == pol.NONE


def test_disabled_offers_are_never_used():
    args = ([2157], [1329], [0.06], [0.10], [0.18])
    assert pol.recommend(*args, Policy(full=False))[0][0] in (pol.SMALL, pol.NONE)
    assert pol.recommend(*args, Policy(small=False, full=False))[0][0] == pol.NONE


def test_holdout_draw_is_deterministic_and_uniform():
    ids = [f"C{i:05d}" for i in range(20000)]
    draws = np.array([pol.holdout_draw(c) for c in ids])
    assert pol.holdout_draw("C00042") == pol.holdout_draw("C00042")
    assert ((draws >= 0) & (draws < 1)).all()
    assert abs((draws < 0.10).mean() - 0.10) < 0.01


def test_holdout_matches_the_dashboard_hash():
    # Values returned by the dashboard's JavaScript draw() in a browser for the same ids.
    expected = {"C00000": 0.1665730937384069, "C00001": 0.3672753549180925, "C03518": 0.10229784832336009,
                "L00007": 0.3065889326389879, "C99999": 0.8297214333433658}
    for cart_id, value in expected.items():
        assert pol.holdout_draw(cart_id) == pytest.approx(value, abs=1e-15)


def test_holdout_only_withholds_offers_and_never_touches_opted_out():
    n = 5000
    ids = [f"C{i:05d}" for i in range(n)]
    d = pol.decide(ids, np.full(n, 2000), np.full(n, 1200), np.full(n, .05), np.full(n, .10), np.full(n, .20),
                   np.r_[np.ones(100, bool), np.zeros(n - 100, bool)], Policy(hold=10))
    assert (d["action"][:100] == -1).all()
    assert not d["holdout"][:100].any()
    assert (d["action"][d["holdout"]] == pol.NONE).all()
    assert 0.08 < d["holdout"][100:].mean() < 0.12


def test_reminders_never_mention_a_discount():
    msg = pol.message_for(pol.NONE, 1500)
    assert "%" not in msg and "off" not in msg.lower() and "code" not in msg.lower()
    assert "10% off" in pol.message_for(pol.FULL, 1500)
    assert pol.message_for(-1, 1500) is None


def test_explanation_uses_the_numbers_behind_the_decision():
    text = pol.explain(pol.FULL, pol.FULL, False, 121.3, 2157, 1329, 0.06, 0.10, 0.18)
    assert "6%" in text and "18%" in text and "Rs 121" in text


def test_outcome_accounting():
    o = pol.outcome([pol.FULL, pol.NONE, -1], [1000, 1000, 1000], [600, 600, 600],
                    [0, 1, 1], [1, 1, 1], [1, 1, 1])
    assert list(o["bought"]) == [True, True, False]
    assert list(o["disc"]) == [100, 0, 0]
    assert o["net"][0] == pytest.approx(600 - 100 - pol.CONTACT_COST)
    assert o["net"][2] == 0
