"""A simulated merchant: shoppers, abandoned carts, and what each would do.

Timeline (default 20 weeks):

  warm-up   the merchant's old flow, 10% to every abandoned cart
  learning  offers are randomised, so the model gets unbiased evidence
  live      Offer Guard decides, with a random holdout for measurement

For every cart the simulation knows the true chance of buying under each of
the three actions, and draws one outcome per action from a single shared
random number. That lets us replay the *same* carts under any strategy, which
no real system can do. The model never sees any of it: it trains only on the
one action and one outcome that were logged for each learning-phase cart.

What the simulation leaves out is listed in docs/model-card.md. The main one:
shoppers here do not change their behaviour in response to past discounts, so
the long-run "learn to wait for the coupon" effect is not credited to any
strategy.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import replace

import numpy as np
import pandas as pd

from . import policy as pol
from .config import BASE, REASONS, Policy, World
from .features import build_features

WINDOW_DAYS = 30
CAL_BANDS = [(0, .05), (.05, .10), (.10, .20), (.20, .30), (.30, .40), (.40, .50), (.50, 1.01)]


def calibration_gap(pred, actual, min_n: int = 15):
    """Average gap between predicted and actual purchase rate, in probability points.

    Carts are grouped into bands by predicted probability; the gap in each
    band is weighted by how many carts it holds. Same definition as the
    dashboard's "Calibration gap".
    """
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    rows, tot, acc = [], 0, 0.0
    for lo, hi in CAL_BANDS:
        mask = (pred >= lo) & (pred < hi)
        n = int(mask.sum())
        if n < min_n:
            continue
        est, act = float(pred[mask].mean()), float(actual[mask].mean())
        rows.append({"lo": lo, "hi": hi, "n": n, "est": est, "act": act})
        tot += n
        acc += abs(est - act) * n
    return (acc / tot if tot else float("nan")), rows


class Simulation:
    def __init__(self, world: World = BASE):
        self.w = world
        self.rng = np.random.default_rng(world.seed)
        self.carts = self._build_carts()
        self._events = defaultdict(list)   # account id -> [(day, offered, bought)]
        self._day = 0
        self.alerts: list[dict] = []

    # ------------------------------------------------------------ the world
    def _build_carts(self) -> pd.DataFrame:
        w, rng = self.w, self.rng
        days = w.weeks_total * 7
        people = []   # (type, [cart times])
        for typ, (count, weekly) in w.residents.items():
            for _ in range(count):
                n = rng.poisson(weekly * w.weeks_total)
                people.append((typ, np.sort(rng.uniform(0, days, n))))
        for typ, (per_week, extra) in w.transients.items():
            for week in range(w.weeks_total):
                for _ in range(rng.poisson(per_week)):
                    first = rng.uniform(week * 7, week * 7 + 7)
                    later = first + rng.uniform(0.5, 21, rng.poisson(extra))
                    times = np.sort(np.concatenate([[first], later]))
                    people.append((typ, times[times < days]))

        # Account ids are shuffled so a second account looks like any other.
        n_alt = sum(1 for typ, _ in people if typ == "discount_seeker")
        ids = rng.permutation(len(people) + n_alt)
        next_id = iter(ids)
        reasons = [r for r in REASONS if r != "not_captured"]
        lo_v, hi_v = w.value_range
        rows = []
        for typ, times in people:
            main = f"S{next(next_id):04d}"
            has_alt = typ == "discount_seeker" and rng.random() < w.alt_account_share
            alt = f"S{next(next_id):04d}" if typ == "discount_seeker" else None
            contact = rng.choice([1, 2, 0], p=[w.alt_shared_contact[0], w.alt_shared_contact[1],
                                               1 - sum(w.alt_shared_contact)])
            eff_p0 = rng.lognormal(0, w.shopper_sd_p0)
            eff_lift = rng.lognormal(0, w.shopper_sd_lift)
            orders = rng.poisson(w.orders_180d[typ])
            probs = w.reason_given_type[typ]
            for t in times:
                use_alt = has_alt and rng.random() < w.alt_use
                v = int(round(float(np.clip(rng.lognormal(np.log(w.value_median), w.value_sd), lo_v, hi_v))))
                m = round(v * rng.uniform(*w.margin_rate), 2)
                true_reason = rng.choice(list(probs), p=list(probs.values()))
                seen = true_reason
                if rng.random() < w.reason_mislabel:
                    seen = rng.choice(reasons)
                if rng.random() >= w.heard_rate:
                    seen = "not_captured"
                # Identity signals.
                if use_alt:
                    im = int(contact)
                    tw = rng.beta(2, 5) if im else rng.uniform(0.15, 0.95)
                    il = 2 if (im or tw >= w.link_confirm_score) else (1 if tw >= w.link_possible_score else 0)
                else:
                    im, tw = 0, min(rng.beta(1.6, 12), w.link_confirm_score - 0.01)
                    il = 1 if tw >= w.link_possible_score else 0
                rows.append({
                    "day_f": t, "type": typ, "sid": alt if use_alt else main, "hk": main, "dup": int(use_alt),
                    "v": v, "m": m, "true_reason": true_reason, "reason": seen,
                    "im": im, "tw": round(float(tw), 2), "il": il,
                    "oo": int(rng.random() < w.optout_rate),
                    "orders_main": int(orders), "eff_p0": eff_p0, "eff_lift": eff_lift, "u": rng.random(),
                    "u_org": rng.random(),
                })
        df = pd.DataFrame(rows).sort_values("day_f", kind="stable").reset_index(drop=True)
        df["day"] = df.day_f.astype(int)
        live_day0 = (w.weeks_warmup + w.weeks_learning) * 7
        df["phase"] = np.where(df.day < w.weeks_warmup * 7, "warmup", np.where(df.day < live_day0, "learning", "live"))
        df["live_week"] = np.where(df.phase == "live", (df.day - live_day0) // 7 + 1, 0)
        start = pd.Timestamp(w.live_start) - pd.Timedelta(days=live_day0)
        df["t"] = (start + pd.to_timedelta((df.day_f * 1440).astype(int), unit="m")).dt.strftime("%Y-%m-%d %H:%M")
        live = df.phase == "live"
        df["id"] = ""
        df.loc[live, "id"] = [f"C{i:05d}" for i in range(int(live.sum()))]
        df.loc[~live, "id"] = [f"L{i:05d}" for i in range(int((~live).sum()))]
        self._true_probs(df)
        # One shared random number per cart gives consistent outcomes across actions:
        # anyone who buys after a reminder also buys with an offer.
        for col, p in (("sn", "p_none"), ("ss", "p_small"), ("sf", "p_full")):
            df[col] = (df.u < df[p]).astype(int)
        df["organic"] = (df.u_org < df.p_none * 0.6).astype(int)   # opted-out shoppers get no reminder
        for col in ("pa", "po", "pbo", "pf", "orders", "linked", "pa_acct", "po_acct", "pbo_acct", "pf_acct",
                    "orders_acct"):
            df[col] = 0
        for col in ("en", "es", "ef", "gain"):
            df[col] = np.nan
        df["action"], df["rec"], df["holdout"], df["mode"] = -9, 0, False, ""
        return df

    def _true_probs(self, df: pd.DataFrame) -> None:
        w = self.w
        if w.homogeneous:
            p0 = np.full(len(df), 0.20)
            l5, l10 = np.full(len(df), 0.03), np.full(len(df), 0.06)
        else:
            base = np.array([w.base[t] for t in df.type])
            lo, hi = w.value_lift_range
            span = np.log(w.value_range[1]) - np.log(w.value_range[0])
            value_mult = lo + (hi - lo) * (np.log(df.v) - np.log(w.value_range[0])) / span
            lift_mult = df.true_reason.map(w.reason_lift_mult).fillna(1.0).to_numpy() * value_mult * df.eff_lift
            p0 = base[:, 0] * df.true_reason.map(w.reason_p0_mult).fillna(1.0).to_numpy() * df.eff_p0
            l5, l10 = base[:, 1] * lift_mult, base[:, 2] * lift_mult
        if w.drift_week is not None:
            shifted = (df.live_week >= w.drift_week).to_numpy()
            p0 = np.where(shifted, p0 * w.drift_p0_mult, p0)
            l5 = np.where(shifted, l5 * w.drift_lift_mult, l5)
            l10 = np.where(shifted, l10 * w.drift_lift_mult, l10)
        p0 = np.clip(p0, 0.002, 0.95)
        df["p_none"] = p0
        df["p_small"] = np.clip(p0 + l5, 0, 0.97)
        df["p_full"] = np.maximum(np.clip(p0 + l10, 0, 0.98), df.p_small)

    # --------------------------------------------------------------- history
    def _history(self, accounts, day: int):
        pa = po = pbo = pf = 0
        for acct in accounts:
            for d, offered, bought in reversed(self._events[acct]):
                if d < day - WINDOW_DAYS:
                    break
                pa += 1
                po += offered
                pbo += offered and bought
                pf += (not offered) and bought
        return pa, po, pbo, pf

    def _fill_features(self, idx) -> None:
        c = self.carts
        cols = ["pa", "po", "pbo", "pf", "orders", "linked", "pa_acct", "po_acct", "pbo_acct", "pf_acct", "orders_acct"]
        out = []
        for day, sid, hk, il, orders_main in zip(c.day[idx], c.sid[idx], c.hk[idx], c.il[idx], c.orders_main[idx]):
            own = self._history([sid], day)
            own_orders = orders_main if sid == hk else 0
            # A confirmed link brings in the linked account's history. A "possible" link never does.
            if il == 2 and sid != hk:
                out.append((*self._history([sid, hk], day), orders_main, 1, *own, own_orders))
            else:
                out.append((*own, own_orders, 0, *own, own_orders))
        if out:
            c.loc[idx, cols] = np.array(out)

    def _log_events(self, idx) -> None:
        c = self.carts
        rows = zip(c.action[idx], c.sn[idx], c.ss[idx], c.sf[idx], c["mode"][idx], c.sid[idx], c.day[idx])
        for a, sn, ss, sf, mode, sid, day in rows:
            if a < 0:
                continue
            if mode == "cold":       # reminder first, 5% only if the reminder did not work
                offered, bought = not sn, bool(sn or ss)
            else:
                offered, bought = a > 0, bool((sn, ss, sf)[a])
            self._events[sid].append((day, bool(offered), bought))

    # ----------------------------------------------------------------- phases
    def run_until_live(self) -> "Simulation":
        """Warm-up (10% to everyone) and the randomised learning phase."""
        c, rng = self.carts, self.rng
        last = (self.w.weeks_warmup + self.w.weeks_learning) * 7
        for day in range(self._day, last):
            idx = c.index[c.day == day]
            self._fill_features(idx)
            if day < self.w.weeks_warmup * 7:
                act = np.full(len(idx), pol.FULL)
            else:
                act = rng.integers(0, 3, len(idx))
            c.loc[idx, "action"] = np.where(c.loc[idx, "oo"] == 1, -1, act)
            c.loc[idx, "mode"] = "warmup" if day < self.w.weeks_warmup * 7 else "random"
            self._log_events(idx)
        self._day = last
        return self

    def learning_log(self) -> pd.DataFrame:
        """What a real team would have after the learning phase: one action, one outcome per cart."""
        c = self.carts
        log = c[(c.phase == "learning") & (c.action >= 0)].copy()
        log["bought"] = np.choose(log.action.to_numpy(), [log.sn.to_numpy(), log.ss.to_numpy(), log.sf.to_numpy()])
        return log

    def run_live(self, model, policy: Policy = Policy(), safety_net: bool = True,
                 drift_limit: float = 0.05, monitor_days: int = 14) -> "Simulation":
        """Offer Guard decides. Predictions are rounded to 3 decimals, exactly as exported to the dashboard."""
        c = self.carts
        start = self._day
        fallback = False
        for day in range(start, self.w.weeks_total * 7):
            idx = c.index[c.day == day]
            if len(idx):
                self._fill_features(idx)
                batch = c.loc[idx]
                p = np.round(model.predict(build_features(batch)), 3)
                active = replace(policy, cold=True) if fallback else policy
                d = pol.decide(batch.id.tolist(), batch.v, batch.m, p[:, 0], p[:, 1], p[:, 2], batch.oo == 1, active)
                c.loc[idx, ["en", "es", "ef"]] = p
                c.loc[idx, "rec"], c.loc[idx, "holdout"] = d["rec"], d["holdout"]
                c.loc[idx, "action"], c.loc[idx, "gain"] = d["action"], d["gain"]
                c.loc[idx, "mode"] = "cold" if active.cold else "live"
                self._log_events(idx)
            # Safety net: at the end of each live week, compare the last two weeks of
            # predictions with what shoppers actually did.
            done = day - start + 1
            if done % 7 == 0 and done >= monitor_days and not fallback:
                recent = c[(c.phase == "live") & (c.day > day - monitor_days) & (c.day <= day)
                           & (c.action >= 0) & (c["mode"] == "live")]
                gap = drift_gap(*predicted_vs_actual(recent))
                self.alerts.append({"week": done // 7, "gap": gap, "n": int(len(recent)),
                                    "tripped": bool(gap > drift_limit)})
                if safety_net and gap > drift_limit:
                    fallback = True
        self._day = self.w.weeks_total * 7
        return self

    def live_carts(self) -> pd.DataFrame:
        return self.carts[self.carts.phase == "live"].copy().reset_index(drop=True)


def drift_gap(pred, actual) -> float:
    """Predicted minus actual purchase rate over a window, in probability points.

    This is the safety net's trigger. It is deliberately one number over all
    contacted carts: with about 850 carts in a two-week window its sampling
    noise is about 1.5 points, so a 5-point threshold almost never fires by
    chance. The banded calibration gap is sharper as a diagnostic but too
    noisy on a two-week window to act on automatically.
    """
    pred, actual = np.asarray(pred, float), np.asarray(actual, float)
    return float(abs(pred.mean() - actual.mean())) if len(pred) else 0.0


def predicted_vs_actual(df: pd.DataFrame):
    """Predicted probability for the action taken, and what the shopper did."""
    a = df.action.to_numpy()
    pred = np.choose(a, [df.en.to_numpy(), df.es.to_numpy(), df.ef.to_numpy()])
    actual = np.choose(a, [df.sn.to_numpy(), df.ss.to_numpy(), df.sf.to_numpy()])
    return pred, actual
