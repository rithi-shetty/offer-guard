"""Experiments that test the product's claims instead of assuming them.

Each function answers one question a sceptical reviewer would ask:

  model_bakeoff     Which model, and could a real team have told them apart?
  learning_curve    How much randomised evidence before the model beats a rule?
  signal_value      What is each signal worth in rupees?
  stress_tests      In which worlds does Offer Guard stop helping?
  robustness        Is the headline result luck from one random seed?
  pilot_power       Can the proposed pilot actually detect the effect?
"""
from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
from sklearn.metrics import log_loss
from sklearn.model_selection import KFold

from . import evaluate as ev
from . import policy as pol
from .config import BASE, SCENARIOS, Policy, World
from .features import GROUPS, build_features
from .model import KINDS, UpliftModel
from .simulate import Simulation

DEFAULT_KIND = "two_part"


# ------------------------------------------------------------------ building blocks
def brand_log(world: World, seed: int) -> pd.DataFrame:
    """Randomised learning-phase log from one comparable brand (no shopper identities are kept)."""
    sim = Simulation(replace(world, seed=seed, weeks_live=0)).run_until_live()
    cols = ["v", "m", "reason", "pa", "po", "pbo", "pf", "orders", "linked", "pa_acct", "po_acct", "pbo_acct",
            "pf_acct", "orders_acct", "action", "bought", "p_none", "p_small", "p_full"]
    return sim.learning_log()[cols].reset_index(drop=True)


def brand_bank(world: World, n: int, first_seed: int = 1000) -> list[pd.DataFrame]:
    return [brand_log(world, first_seed + i) for i in range(n)]


def fit(logs: list[pd.DataFrame], kind: str = DEFAULT_KIND, use_links: bool = True, drop=()) -> UpliftModel:
    data = pd.concat(logs, ignore_index=True)
    X = build_features(data, use_links=use_links).drop(columns=list(drop))
    return UpliftModel(kind).fit(X, data.action, data.bought)


def recommend_with(model: UpliftModel, carts: pd.DataFrame, policy: Policy = Policy(), use_links: bool = True):
    p = np.round(model.predict(build_features(carts, use_links=use_links)), 3)
    rec, _ = pol.recommend(carts.v, carts.m, p[:, 0], p[:, 1], p[:, 2], policy)
    return rec, p


def run_brand(world: World, model: UpliftModel, policy: Policy = Policy(), safety_net: bool = True) -> Simulation:
    return Simulation(world).run_until_live().run_live(model, policy, safety_net=safety_net)


# ------------------------------------------------------------------ 1. model choice
def model_bakeoff(logs: list[pd.DataFrame], policy: Policy = Policy(), folds: int = 5) -> dict:
    """Score every candidate the way a real team could: on held-out randomised carts.

    Observable scores (no hidden truth needed):
      log_loss      how well it predicts purchases                (lower is better)
      cal_gap       predicted vs actual purchase rate, in points  (lower is better)
      lift_spread   actual lift of a 10% offer among the fifth of carts the model
                    rates most persuadable, minus the fifth it rates least
                    persuadable. A model that cannot rank scores about zero.
      edge          margin per cart of its decisions versus "discount everyone",
                    estimated by inverse-propensity weighting: keep the carts
                    whose random action happens to match the model's choice.
    Simulation-only:
      true_edge     the same margin computed from the true probabilities.
    """
    from .simulate import calibration_gap
    data = pd.concat(logs, ignore_index=True)
    X = build_features(data)
    a, y = data.action.to_numpy(), data.bought.to_numpy()
    v, m = data.v.to_numpy(float), data.m.to_numpy(float)
    realised = np.where(y == 1, m - v * pol.RATE[a], 0.0) - pol.CONTACT_COST
    baseline_ips = np.where(a == pol.FULL, 3.0, 0.0) * realised          # "discount everyone"
    baseline_true = ev.expected_margin(data, np.full(len(data), pol.FULL))
    rows = []
    for kind in KINDS:
        oof = np.zeros((len(y), 3))
        for tr, te in KFold(folds, shuffle=True, random_state=0).split(X):
            oof[te] = UpliftModel(kind).fit(X.iloc[tr], a[tr], y[tr]).predict(X.iloc[te])
        own = oof[np.arange(len(y)), a]
        rec, _ = pol.recommend(v, m, oof[:, 0], oof[:, 1], oof[:, 2], policy)
        edge = np.where(rec == a, 3.0, 0.0) * realised - baseline_ips
        # Lift ranking: observed (10% minus reminder) purchase rate by fifth of predicted lift.
        fifth = pd.qcut(pd.Series(oof[:, 2] - oof[:, 0]).rank(method="first"), 5, labels=False).to_numpy()
        obs, se2 = [], []
        for q in (0, 4):
            t, c = y[(fifth == q) & (a == pol.FULL)], y[(fifth == q) & (a == pol.NONE)]
            obs.append(t.mean() - c.mean())
            se2.append(t.var() / len(t) + c.var() / len(c))
        rows.append({
            "kind": kind, "label": KINDS[kind],
            "log_loss": float(log_loss(y, own)),
            "cal_gap": float(calibration_gap(own, y)[0]),
            "lift_spread": float(obs[1] - obs[0]), "lift_spread_se": float(np.sqrt(sum(se2))),
            "edge": float(edge.mean()), "edge_se": float(edge.std(ddof=1) / np.sqrt(len(edge))),
            "true_edge": float((ev.expected_margin(data, rec) - baseline_true).mean()),
        })
    return {"n": int(len(data)), "rows": rows, "chosen": DEFAULT_KIND,
            "best_on_log_loss": min(rows, key=lambda r: r["log_loss"])["kind"],
            "best_on_edge": max(rows, key=lambda r: r["edge"])["kind"],
            "best_on_true_edge": max(rows, key=lambda r: r["true_edge"])["kind"]}


# ------------------------------------------------------------------ 2. how much data
def learning_curve(bank: list[pd.DataFrame], own_log: pd.DataFrame, live: pd.DataFrame,
                   sizes=(1, 2, 4, 8, 16, 32), reps: int = 6, policy: Policy = Policy(),
                   kind: str = DEFAULT_KIND) -> list[dict]:
    """Margin versus the number of comparable brands whose learning phase is pooled.

    One brand is the merchant itself. Evaluated on the merchant's live carts
    with true probabilities, so the only noise left is which brands were pooled.
    """
    df = live[ev.carried_out(live)].reset_index(drop=True)
    h = policy.hold / 100
    base_all = ev.expected_margin(df, np.full(len(df), pol.FULL)).sum()
    rng = np.random.default_rng(11)
    out = []
    for k in sizes:
        edges, edges_h = [], []
        for _ in range(reps if k < len(bank) + 1 else 1):
            others = [bank[i] for i in rng.choice(len(bank), k - 1, replace=False)]
            rec, _ = recommend_with(fit([own_log] + others, kind), df, policy)
            edges.append(ev.expected_margin(df, rec).sum() - base_all)
            edges_h.append(ev.expected_margin(df, rec, h).sum() - base_all)
        n_train = int(len(own_log) + np.mean([len(b) for b in bank]) * (k - 1))
        out.append({"brands": k, "carts": n_train,
                    "edge": float(np.mean(edges)), "edge_sd": float(np.std(edges)),
                    "edge_holdout": float(np.mean(edges_h)), "edge_holdout_sd": float(np.std(edges_h)),
                    "win_rate": float(np.mean(np.array(edges_h) > 0))})
    return out


# ------------------------------------------------------------------ 3. signal value
def signal_value(logs: list[pd.DataFrame], live: pd.DataFrame, policy: Policy = Policy(),
                 kind: str = DEFAULT_KIND) -> list[dict]:
    """Retrain with one group of signals removed; the drop in margin is what that signal is worth."""
    df = live[ev.carried_out(live)].reset_index(drop=True)
    full_rec, _ = recommend_with(fit(logs, kind), df, policy)
    full = ev.expected_margin(df, full_rec).sum()
    out = []
    for label, cols in GROUPS.items():
        rec, _ = recommend_with(fit(logs, kind, drop=cols), df, policy)
        out.append({"signal": label, "worth": float(full - ev.expected_margin(df, rec).sum())})
    rec, _ = recommend_with(fit(logs, kind, use_links=False), df, policy, use_links=False)
    out.append({"signal": "Confirmed account links", "worth": float(full - ev.expected_margin(df, rec).sum())})
    return sorted(out, key=lambda r: -r["worth"])


# ------------------------------------------------------------------ 4. stress tests
def stress_tests(pool: int = 16, policy: Policy = Policy(), kind: str = DEFAULT_KIND) -> list[dict]:
    """Re-run the whole pipeline in worlds where the assumptions are different."""
    out = []
    for name, world in SCENARIOS.items():
        own = brand_log(world, world.seed)
        model = fit([own] + brand_bank(world, pool - 1), kind)
        sim = run_brand(world, model, policy, safety_net=True)
        tab = ev.strategy_table(sim.live_carts(), policy)
        row = {"scenario": name,
               "reminder": tab["reminder"]["exp_net"], "discount_all": tab["discount_all"]["exp_net"],
               "offer_guard": tab["offer_guard"]["exp_net"], "oracle": tab["oracle"]["exp_net"],
               "og_disc": tab["offer_guard"]["exp_disc"], "all_disc": tab["discount_all"]["exp_disc"],
               "alerts": sim.alerts, "tripped_week": next((a["week"] for a in sim.alerts if a["tripped"]), None)}
        if world.drift_week is not None:
            # Same world without the safety net, to see what the fallback changed.
            off = run_brand(world, model, policy, safety_net=False).live_carts()
            row["no_net_realised"] = ev.strategy_table(off, policy)["offer_guard"]
            row["with_net_realised"] = tab["offer_guard"]
            row["discount_all_realised"] = tab["discount_all"]
        out.append(row)
    return out


# ------------------------------------------------------------------ 5. is it luck?
def robustness(seeds=range(20), pool: int = 16, bank_size: int = 40, policy: Policy = Policy(),
               kind: str = DEFAULT_KIND, world: World = BASE) -> dict:
    """Repeat the base case in freshly drawn worlds: new shoppers, new pooled brands, new outcomes."""
    bank = brand_bank(world, bank_size, first_seed=5000)
    rng = np.random.default_rng(3)
    rows = []
    for s in seeds:
        w = replace(world, seed=100 + s)
        others = [bank[i] for i in rng.choice(len(bank), pool - 1, replace=False)]
        sim = run_brand(w, fit([brand_log(w, w.seed)] + others, kind), policy)
        tab = ev.strategy_table(sim.live_carts(), policy)
        og, al = tab["offer_guard"], tab["discount_all"]
        rows.append({
            "seed": int(s),
            "edge_expected": og["exp_net"] - al["exp_net"],
            "edge_realised": og["net"] - al["net"],
            "edge_no_holdout": og["exp_net_no_holdout"] - al["exp_net"],
            "disc_saved": 1 - og["exp_disc"] / al["exp_disc"],
            "rate_gap": (og["exp_orders"] - al["exp_orders"]) / og["n"],
            "captured": (og["exp_net_no_holdout"] - al["exp_net"]) / (tab["oracle"]["exp_net"] - al["exp_net"]),
            "false_alarm": any(a["tripped"] for a in sim.alerts),
            "cal_gap": ev.calibration(sim.live_carts())["gap"],
        })
    df = pd.DataFrame(rows)
    q = lambda c: [float(df[c].quantile(x)) for x in (0.1, 0.5, 0.9)]
    return {"runs": rows, "n": len(rows), "pool": pool,
            "edge_expected": q("edge_expected"), "edge_realised": q("edge_realised"),
            "edge_no_holdout": q("edge_no_holdout"), "disc_saved": q("disc_saved"),
            "rate_gap": q("rate_gap"), "captured": q("captured"),
            "wins_expected": int((df.edge_expected > 0).sum()), "wins_realised": int((df.edge_realised > 0).sum()),
            "false_alarms": int(df.false_alarm.sum()), "cal_gap_max": float(df.cal_gap.max())}


# ------------------------------------------------------------------ 6. can the pilot see it?
def pilot_power(live: pd.DataFrame, policy: Policy = Policy(), alpha: float = 0.05, power: float = 0.80) -> dict:
    """Sample size for the proposed pilot: carts split at random between today's flow and Offer Guard.

    Uses per-cart outcomes from the live phase. Two questions:
      superiority      detect the margin-per-cart gain over "discount everyone"
      non-inferiority  show recovery rate is no more than 2 points lower
    """
    from scipy.stats import norm
    df = live[ev.carried_out(live) & (live["mode"] == "live")].reset_index(drop=True)
    h = policy.hold / 100
    og = pol.outcome(df.action, df.v, df.m, df.sn, df.ss, df.sf)
    al = pol.outcome(np.full(len(df), pol.FULL), df.v, df.m, df.sn, df.ss, df.sf)
    delta = float((ev.expected_margin(df, df.rec.to_numpy(), h) - ev.expected_margin(df, np.full(len(df), pol.FULL))).mean())
    sd = float(np.sqrt((og["net"].var(ddof=1) + al["net"].var(ddof=1)) / 2))
    z = norm.ppf(1 - alpha / 2) + norm.ppf(power)
    n_margin = int(np.ceil(2 * (z * sd / delta) ** 2)) if delta > 0 else None
    # Discount spend per cart: the same test on a much less noisy quantity.
    d_delta = float((al["disc"] - og["disc"]).mean())
    d_sd = float(np.sqrt((og["disc"].var(ddof=1) + al["disc"].var(ddof=1)) / 2))
    n_disc = int(np.ceil(2 * (z * d_sd / d_delta) ** 2)) if d_delta > 0 else None
    # Non-inferiority on recovery rate with a 2-point margin (one-sided).
    p_og = ev.expected_orders(df, df.rec.to_numpy(), h) / len(df)
    p_al = ev.expected_orders(df, np.full(len(df), pol.FULL)) / len(df)
    zn = norm.ppf(1 - alpha) + norm.ppf(power)
    slack = 0.02 - (p_al - p_og)
    n_rate = int(np.ceil(zn ** 2 * (p_og * (1 - p_og) + p_al * (1 - p_al)) / slack ** 2)) if slack > 0 else None
    weekly = len(df) / 8
    return {"margin_gain_per_cart": delta, "margin_sd": sd, "carts_per_arm_margin": n_margin,
            "disc_saving_per_cart": d_delta, "disc_sd": d_sd, "carts_per_arm_discount": n_disc,
            "rate_og": float(p_og), "rate_all": float(p_al), "rate_gap": float(p_og - p_al),
            "carts_per_arm_rate": n_rate, "carts_per_week_per_brand": float(weekly),
            "pilot_carts_per_arm": {b: int(b * weekly * 8 / 2) for b in (3, 5, 10, 20)}}


# ------------------------------------------------------------------ 7. the merchant's dial
def policy_frontier(live: pd.DataFrame, gains=(0, 2, 5, 10, 15, 20, 25, 30, 40, 50, 60),
                    policy: Policy = Policy()) -> list[dict]:
    """What the minimum-gain slider trades off: margin, orders and discount spend.

    Uses the model's own predictions already stored on each cart (as the
    Policy preview does) and scores them against the true probabilities.
    """
    df = live[ev.carried_out(live)].reset_index(drop=True)
    h = policy.hold / 100
    all10 = np.full(len(df), pol.FULL)
    base = {"net": ev.expected_margin(df, all10).sum(), "orders": ev.expected_orders(df, all10),
            "disc": ev.expected_discount(df, all10)}
    out = []
    for g in gains:
        p = replace(policy, gain=float(g))
        rec, _ = pol.recommend(df.v, df.m, df.en, df.es, df.ef, p)
        out.append({"gain": g,
                    "net_vs_all": float(ev.expected_margin(df, rec, h).sum() - base["net"]),
                    "orders_vs_all": float(ev.expected_orders(df, rec, h) - base["orders"]),
                    "disc_vs_all": float(ev.expected_discount(df, rec, h) - base["disc"]),
                    "offered": float((rec > 0).mean())})
    return out
