"""Scoring: what each strategy earned, and whether the model can be trusted.

Two kinds of number appear here and it matters which is which.

  Observable   what a live system could measure: outcomes of the action it
               took, the holdout comparison, calibration.
  Simulation   only possible because the simulation knows what every shopper
               would have done under every action: replaying other
               strategies on the same carts, the perfect-foresight ceiling,
               and "expected" margins that average out luck.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import policy as pol
from .config import Policy
from .simulate import calibration_gap, predicted_vs_actual

Z95 = 1.96


def carried_out(live: pd.DataFrame) -> pd.Series:
    """Carts the agent has already acted on: not opted out, not in the last-24-hour queue."""
    t = pd.to_datetime(live.t)
    return (live.oo == 0) & ~(t > t.max() - pd.Timedelta(days=1))


def _totals(df: pd.DataFrame, action, cold=None) -> dict:
    """Realised result of taking `action` on every cart in df."""
    cold = np.zeros(len(df), bool) if cold is None else np.asarray(cold)
    o = pol.outcome(action, df.v, df.m, df.sn, df.ss, df.sf)
    oc = pol.outcome(np.zeros(len(df), int), df.v, df.m, df.sn, df.ss, df.sf, cold=True)
    bought = np.where(cold, oc["bought"], o["bought"])
    disc = np.where(cold, oc["disc"], o["disc"])
    net = np.where(cold, oc["net"], o["net"])
    n = len(df)
    return {"n": n, "orders": int(bought.sum()), "rate": float(bought.mean()),
            "disc": float(disc.sum()), "comm": float(pol.CONTACT_COST * n), "net": float(net.sum())}


def expected_margin(df: pd.DataFrame, action, holdout_share: float = 0.0) -> np.ndarray:
    """Per-cart expected net margin under the true probabilities (simulation only).

    `holdout_share` withholds that fraction of offers, as the live policy does.
    """
    action = np.asarray(action)
    P = np.column_stack([df.p_none, df.p_small, df.p_full])
    v, m = df.v.to_numpy(float), df.m.to_numpy(float)
    offer = P[np.arange(len(df)), action] * (m - v * pol.RATE[action])
    plain = P[:, 0] * m
    mix = np.where(action > 0, (1 - holdout_share) * offer + holdout_share * plain, plain)
    return mix - pol.CONTACT_COST


def expected_orders(df: pd.DataFrame, action, holdout_share: float = 0.0) -> float:
    action = np.asarray(action)
    P = np.column_stack([df.p_none, df.p_small, df.p_full])
    p = P[np.arange(len(df)), action]
    return float(np.where(action > 0, (1 - holdout_share) * p + holdout_share * P[:, 0], P[:, 0]).sum())


def expected_discount(df: pd.DataFrame, action, holdout_share: float = 0.0) -> float:
    action = np.asarray(action)
    P = np.column_stack([df.p_none, df.p_small, df.p_full])
    spend = P[np.arange(len(df)), action] * df.v.to_numpy(float) * pol.RATE[action]
    return float(((1 - holdout_share) * spend).sum())


def oracle_action(df: pd.DataFrame, policy: Policy = Policy()) -> np.ndarray:
    """The best decision for each cart if the true probabilities were known."""
    rec, _ = pol.recommend(df.v, df.m, df.p_none, df.p_small, df.p_full, policy)
    return rec


def strategies(df: pd.DataFrame) -> dict:
    """Action per cart for each fixed strategy the dashboard compares against."""
    n = len(df)
    return {
        "reminder": pol.fixed_action(n, pol.NONE),
        "discount_all": pol.fixed_action(n, pol.FULL),
        "rule_value": pol.rule_high_value(df.v),
        "rule_first": pol.rule_first_abandonment(df.pa),
    }


STRATEGY_LABELS = {
    "reminder": "Reminder only",
    "discount_all": "Discount everyone 10%",
    "rule_value": "10% on carts of Rs 1,000 or more",
    "rule_first": "10% on first abandonment only",
    "offer_guard": "Offer Guard",
    "oracle": "Perfect foresight (upper bound)",
}


def strategy_table(live: pd.DataFrame, policy: Policy = Policy()) -> dict:
    """Realised and expected results for every strategy on the carried-out carts."""
    df = live[carried_out(live)].reset_index(drop=True)
    out = {}
    for name, act in strategies(df).items():
        out[name] = _totals(df, act)
        out[name]["exp_net"] = float(expected_margin(df, act).sum())
        out[name]["exp_orders"] = expected_orders(df, act)
        out[name]["exp_disc"] = expected_discount(df, act)
    og_action = df.action.to_numpy()
    out["offer_guard"] = _totals(df, og_action, cold=(df["mode"] == "cold").to_numpy())
    h = policy.hold / 100
    out["offer_guard"]["exp_net"] = float(expected_margin(df, df.rec.to_numpy(), h).sum())
    out["offer_guard"]["exp_orders"] = expected_orders(df, df.rec.to_numpy(), h)
    out["offer_guard"]["exp_disc"] = expected_discount(df, df.rec.to_numpy(), h)
    out["offer_guard"]["exp_net_no_holdout"] = float(expected_margin(df, df.rec.to_numpy()).sum())
    orc = oracle_action(df, policy)
    out["oracle"] = _totals(df, orc)
    out["oracle"]["exp_net"] = float(expected_margin(df, orc).sum())
    out["oracle"]["exp_orders"] = expected_orders(df, orc)
    out["oracle"]["exp_disc"] = expected_discount(df, orc)
    base = out["reminder"]
    for t in out.values():
        t["inc_orders"] = t["orders"] - base["orders"]
        t["inc_margin"] = t["net"] - base["net"]
        t["exp_inc_margin"] = t["exp_net"] - base["exp_net"]
        t["disc_per_inc_order"] = t["disc"] / t["inc_orders"] if t["inc_orders"] > 0 else None
    return out


def holdout_readout(live: pd.DataFrame) -> dict:
    """What the holdout measured, next to the truth the simulation knows."""
    df = live[carried_out(live) & (live.rec > 0) & (live["mode"] == "live")]
    treated, held = df[~df.holdout], df[df.holdout]
    if not len(treated) or not len(held):
        return {"n_treated": len(treated), "n_held": len(held)}
    bt = pol.outcome(treated.action, treated.v, treated.m, treated.sn, treated.ss, treated.sf)
    bh = pol.outcome(held.action, held.v, held.m, held.sn, held.ss, held.sf)
    p1, p0 = bt["bought"].mean(), bh["bought"].mean()
    se = np.sqrt(p1 * (1 - p1) / len(treated) + p0 * (1 - p0) / len(held))
    # Incremental margin: what an offer adds per offered cart, net of the discount itself.
    dm = bt["net"].mean() - bh["net"].mean()
    se_m = np.sqrt(bt["net"].var(ddof=1) / len(treated) + bh["net"].var(ddof=1) / len(held))
    all_carts = int(carried_out(live).sum())
    P = np.column_stack([df.p_none, df.p_small, df.p_full])
    rec = df.rec.to_numpy()
    true_lift = float((P[np.arange(len(df)), rec] - P[:, 0]).mean())
    est_lift = float((np.choose(treated.rec.to_numpy(), [treated.en, treated.es, treated.ef]) - treated.en).mean())
    scale = len(treated) / all_carts
    return {
        "n_treated": int(len(treated)), "n_held": int(len(held)),
        "rate_treated": float(p1), "rate_held": float(p0),
        "lift": float(p1 - p0), "lift_lo": float(p1 - p0 - Z95 * se), "lift_hi": float(p1 - p0 + Z95 * se),
        "true_lift": true_lift, "model_lift": est_lift,
        "share_not_needed": float(p0 / p1) if p1 else None,
        "inc_margin_per_offer": float(dm), "inc_margin_per_offer_se": float(se_m),
        "inc_margin_per_cart": float(dm * scale),
        "inc_margin_per_cart_lo": float((dm - Z95 * se_m) * scale),
        "inc_margin_per_cart_hi": float((dm + Z95 * se_m) * scale),
    }


def calibration(live: pd.DataFrame) -> dict:
    df = live[carried_out(live) & (live["mode"] == "live")]
    gap, bands = calibration_gap(*predicted_vs_actual(df))
    return {"gap": float(gap), "bands": bands, "n": int(len(df))}


def uplift_by_quintile(live: pd.DataFrame) -> list[dict]:
    """Does the model rank shoppers by how much a 10% offer moves them?

    Carts are sorted by predicted lift and cut into five equal groups; a
    useful model shows true lift rising from the first group to the last.
    """
    df = live[live.oo == 0].copy()
    df["pred"] = df.ef - df.en
    df["true"] = df.p_full - df.p_none
    df["q"] = pd.qcut(df.pred.rank(method="first"), 5, labels=False)
    out = []
    for q, g in df.groupby("q"):
        out.append({"group": int(q) + 1, "n": int(len(g)), "predicted": float(g.pred.mean()),
                    "actual": float(g.true.mean())})
    return out


def decision_mix(live: pd.DataFrame) -> dict:
    df = live[carried_out(live) | (live.oo == 1)]
    return {
        "full": int(((df.action == pol.FULL)).sum()),
        "small": int(((df.action == pol.SMALL)).sum()),
        "none": int(((df.action == pol.NONE) & ~df.holdout).sum()),
        "holdout": int(df.holdout.sum()),
        "optout": int((df.oo == 1).sum()),
    }


def by_hidden_type(live: pd.DataFrame) -> list[dict]:
    """Recommendation mix per hidden shopper type (simulation only): where the model is right and wrong."""
    df = live[live.oo == 0].copy()
    df["best"] = oracle_action(df)
    out = []
    for typ, g in df.groupby("type"):
        out.append({"type": typ, "n": int(len(g)),
                    "none": float((g.rec == 0).mean()), "small": float((g.rec == 1).mean()),
                    "full": float((g.rec == 2).mean()), "agrees_with_best": float((g.rec == g.best).mean())})
    return out
