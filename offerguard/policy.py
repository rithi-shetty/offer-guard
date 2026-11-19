"""The decision engine: turns three predicted probabilities into one instruction.

This is the reference implementation. The dashboard carries a JavaScript port
of the same logic so the demo runs with no backend; it re-checks itself
against the decisions exported from here every time the page loads.

The rule, for each offer level k the merchant has enabled:

    value_k = P(buy | offer k) x (margin - discount_k)  -  P(buy | reminder) x margin

Offer the level with the highest value if it clears the merchant's minimum
gain; otherwise send a plain reminder. The second term is what makes this
different from "will they buy?": it charges the offer for every shopper who
would have bought anyway.
"""
from __future__ import annotations

import numpy as np

from .config import DISCOUNT, MSG_COST, MSGS, Policy

NONE, SMALL, FULL = 0, 1, 2            # action codes used in arrays
CODE = {"none": NONE, "small": SMALL, "full": FULL}
NAME = {v: k for k, v in CODE.items()}
RATE = np.array([DISCOUNT["none"], DISCOUNT["small"], DISCOUNT["full"]])
CONTACT_COST = MSG_COST * MSGS


def holdout_draw(cart_id: str) -> float:
    """Deterministic pseudo-random number in [0, 1) from a cart id.

    Using a hash instead of a random generator means a cart's holdout
    status never changes when the page reloads or the policy is edited, and
    the Python and JavaScript engines agree exactly.
    """
    mask = 0xFFFFFFFF
    h = 2166136261
    for ch in cart_id:
        h = ((h ^ ord(ch)) * 16777619) & mask
    h ^= h >> 13
    h = (h * 0x5BD1E995) & mask
    h ^= h >> 15
    return h / 4294967296


def offer_values(v, m, p_none, p_small, p_full):
    """Expected extra margin (rupees) from the 5% and 10% offers versus a reminder."""
    v, m = np.asarray(v, float), np.asarray(m, float)
    small = p_small * (m - v * DISCOUNT["small"]) - p_none * m
    full = p_full * (m - v * DISCOUNT["full"]) - p_none * m
    return small, full


def recommend(v, m, p_none, p_small, p_full, policy: Policy = Policy()):
    """Recommended action code per cart, plus the expected gain of the best enabled offer."""
    vs, vf = offer_values(v, m, p_none, p_small, p_full)
    n = len(np.atleast_1d(vs))
    best = np.full(n, -1)
    gain = np.full(n, -np.inf)
    if policy.small:
        best[:] = SMALL
        gain = np.array(vs, float).reshape(n)
    if policy.full:
        better = (best == -1) | (np.reshape(vf, n) > gain)
        best = np.where(better, FULL, best)
        gain = np.where(better, np.reshape(vf, n), gain)
    rec = np.where((best != -1) & (gain >= policy.gain), best, NONE)
    return rec, gain


def decide(cart_ids, v, m, p_none, p_small, p_full, optout, policy: Policy = Policy()):
    """Full decision for a batch of carts.

    Returns a dict of arrays:
      rec      what the model-plus-rule recommends (0/1/2)
      holdout  True where a would-be offer was randomly withheld for measurement
      action   what the agent is told to do (0/1/2); -1 means no outreach (opted out)
      gain     expected extra margin of the best enabled offer
    """
    rec, gain = recommend(v, m, p_none, p_small, p_full, policy)
    optout = np.asarray(optout, bool)
    if policy.cold:
        # New-merchant mode ignores per-shopper estimates entirely.
        action = np.where(optout, -1, NONE)
        return {"rec": rec, "holdout": np.zeros(len(rec), bool), "action": action, "gain": gain, "cold": True}
    draws = np.array([holdout_draw(c) for c in cart_ids])
    holdout = (rec != NONE) & (draws < policy.hold / 100) & ~optout
    action = np.where(holdout, NONE, rec)
    action = np.where(optout, -1, action)
    return {"rec": rec, "holdout": holdout, "action": action, "gain": gain, "cold": False}


def outcome(action, v, m, s_none, s_small, s_full, organic=None, cold: bool = False):
    """What happens once the agent has acted: purchase, discount paid, net margin.

    `s_*` are the simulated purchase outcomes under each action. A real system
    only ever observes the one for the action it took.
    """
    action = np.asarray(action)
    v, m = np.asarray(v, float), np.asarray(m, float)
    s = np.stack([np.asarray(s_none, bool), np.asarray(s_small, bool), np.asarray(s_full, bool)], axis=1)
    contacted = action >= 0
    a = np.where(contacted, action, 0)
    if cold:
        # Reminder first; the 5% offer follows only if the reminder did not work.
        bought = s[:, 0] | s[:, 1]
        disc = np.where(~s[:, 0] & s[:, 1], v * DISCOUNT["small"], 0.0)
    else:
        bought = s[np.arange(len(a)), a]
        disc = np.where(bought, v * RATE[a], 0.0)
    if organic is not None:
        bought = np.where(contacted, bought, np.asarray(organic, bool))
    else:
        bought = np.where(contacted, bought, False)
    disc = np.where(contacted, disc, 0.0)
    comm = np.where(contacted, CONTACT_COST, 0.0)
    net = np.where(bought, m - disc, 0.0) - comm
    return {"bought": bought, "disc": disc, "comm": comm, "net": net}


# ---------------------------------------------------------------- baselines
def fixed_action(n: int, code: int):
    return np.full(n, code)


def rule_high_value(v, threshold: float = 1000):
    """10% on carts of Rs 1,000 or more, reminder otherwise."""
    return np.where(np.asarray(v) >= threshold, FULL, NONE)


def rule_first_abandonment(prior_abandons):
    """10% the first time a shopper abandons in 30 days, reminder otherwise."""
    return np.where(np.asarray(prior_abandons) == 0, FULL, NONE)


# ------------------------------------------------- what the shopper is told
def message_for(action: int, cart_value: float) -> str | None:
    """The text the recovery agent sends. Reminders never mention a discount."""
    if action < 0:
        return None
    value = f"Rs {int(round(cart_value)):,}"
    if action == NONE:
        return (f"Hi there, you left items worth {value} in your cart. We have saved them for you, "
                "and checkout takes under a minute. Any questions before you order?")
    pct = int(round(RATE[action] * 100))
    return (f"Hi there, you left items worth {value} in your cart. We have saved them for you. "
            f"Complete your order today and get {pct}% off with code SAVE{pct}. "
            "Valid for 24 hours. T&Cs apply.")


def explain(action: int, rec: int, holdout: bool, gain: float, v: float, m: float,
            p_none: float, p_small: float, p_full: float, policy: Policy = Policy()) -> str:
    """Plain-language reason for a decision.

    Every number in the sentence comes from the calculation that produced the
    decision. Nothing is inferred after the fact, so the explanation cannot
    drift away from what the engine actually did.
    """
    pct = lambda x: f"{round(x * 100)}%"
    rs = lambda x: ("-Rs " if round(x) < 0 else "Rs ") + f"{abs(round(x)):,}"
    if action < 0:
        return "Shopper opted out of messages: no outreach."
    if policy.cold:
        return "New merchant mode: reminder first; a 5% offer follows only if there is no response."
    if holdout:
        return (f"Would receive a {pct(RATE[rec])} offer, but randomly held out "
                "to measure what discounts add.")
    if rec == NONE:
        if not (policy.small or policy.full):
            return "No offers are enabled in Policy; reminder only."
        top = max(p_small if policy.small else 0.0, p_full if policy.full else 0.0)
        return (f"A discount moves the chance of buying from {pct(p_none)} to {pct(top)} at most; "
                f"expected extra margin {rs(gain)} is below the {rs(policy.gain)} minimum. Reminder only.")
    p = p_small if rec == SMALL else p_full
    return (f"A {pct(RATE[rec])} offer raises the chance of buying from {pct(p_none)} to {pct(p)}; "
            f"expected extra margin {rs(gain)}.")
